# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Account-authenticated Codex CLI execution.

The executor intentionally invokes the native CLI rather than an OpenAI API
client.  Every call receives a temporary ``CODEX_HOME`` containing only the
account auth state and a harness-owned native permissions profile.  This keeps
participant and evaluator workspaces independent while allowing model calls to
use the user's subscription login.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Iterator, Mapping, Protocol

from .artifacts import copy_files, file_manifest
from .errors import HarnessError
from .image_inputs import (
    ImageInput,
    image_input_receipt,
    stage_image_inputs,
    validate_image_inputs,
)


@dataclass(frozen=True)
class AuthStatus:
    """Read-only result of ``codex login status``."""

    available: bool
    authenticated: bool
    detail: str
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ExecutionRequest:
    """One isolated Codex invocation."""

    prompt: str
    cwd: Path
    model: str | None
    settings: Mapping[str, Any]
    purpose: str
    response_schema: Mapping[str, Any] | None = None
    images: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ParsedCodexOutput:
    """Useful content extracted from Codex's JSONL event stream."""

    events: tuple[dict[str, Any], ...]
    assistant_messages: tuple[str, ...]
    final_text: str
    usage: dict[str, int | float | None]
    errors: tuple[str, ...]
    terminal_completed: bool


@dataclass(frozen=True)
class ExecutionResult:
    """Captured process output and normalized execution status."""

    command: tuple[str, ...]
    returncode: int | None
    status: str
    elapsed_seconds: float
    stdout: str
    stderr: str
    parsed: ParsedCodexOutput
    error: str | None = None


class Executor(Protocol):
    """Executor interface used by the pipeline and fake test executors."""

    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
        """Check account authentication without making a model call."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run one model invocation."""


def preflight_executor(executor: Executor, model: str | None, settings: Mapping[str, Any], purpose: str) -> AuthStatus:
    """Use a runtime's no-generation capability probe when it provides one."""
    checker = getattr(executor, "check_runtime", None)
    if checker is not None:
        status: AuthStatus = checker(model, settings, purpose)
    else:
        status = executor.check_auth(settings)
    if not status.available or not status.authenticated:
        raise HarnessError(f"runtime authentication is unavailable: {status.detail}")
    return status


def _toml_key(value: str) -> str:
    if value and all(char.isalnum() or char in "_-" for char in value):
        return value
    return json.dumps(value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value {type(value).__name__}")


def toml_dumps(mapping: Mapping[str, Any], prefix: str = "") -> str:
    """Serialize the small TOML subset used by the generated Codex config."""

    scalars: list[str] = []
    tables: list[tuple[str, Mapping[str, Any]]] = []
    array_tables: list[tuple[str, list[Mapping[str, Any]]]] = []
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            tables.append((str(key), value))
        elif isinstance(value, list) and value and all(isinstance(item, Mapping) for item in value):
            array_tables.append((str(key), [item for item in value if isinstance(item, Mapping)]))
        else:
            scalars.append(f"{_toml_key(str(key))} = {_toml_value(value)}")
    chunks: list[str] = []
    if scalars:
        chunks.append("\n".join(scalars))
    for key, table in tables:
        full_key = f"{prefix}.{_toml_key(key)}" if prefix else _toml_key(key)
        child = toml_dumps(table, full_key)
        chunks.append(f"[{full_key}]" + (f"\n{child}" if child else ""))
    for key, table_list in array_tables:
        full_key = f"{prefix}.{_toml_key(key)}" if prefix else _toml_key(key)
        for table in table_list:
            child = toml_dumps(table, full_key)
            chunks.append(f"[[{full_key}]]" + (f"\n{child}" if child else ""))
    return "\n\n".join(chunks) + ("\n" if chunks else "")


def _text_from_item(item: Mapping[str, Any]) -> str:
    text = item.get("text")
    if isinstance(text, str):
        return text
    content = item.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, Mapping):
                part_text = part.get("text")
                if isinstance(part_text, str):
                    parts.append(part_text)
        return "".join(parts)
    return ""


def parse_codex_jsonl(stdout: str) -> ParsedCodexOutput:
    """Parse Codex ``exec --json`` output while preserving usage gaps as null.

    Codex may emit several ``turn.completed`` records during a single command.
    Known usage counters are summed; if no usage record is present, all fields
    remain ``None`` so unavailable measurements are never presented as zero.
    """

    events: list[dict[str, Any]] = []
    messages: list[str] = []
    errors: list[str] = []
    usage: dict[str, int | float | None] = {
        "input_tokens": None,
        "output_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "cost_usd": None,
    }
    usage_seen = False
    terminal_completed = False
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        events.append(event)
        event_type = event.get("type")
        if event_type == "turn.completed":
            terminal_completed = True
            turn_usage = event.get("usage")
            if isinstance(turn_usage, Mapping):
                usage_seen = True
                for output_key, input_key in (
                    ("input_tokens", "input_tokens"),
                    ("output_tokens", "output_tokens"),
                    ("cached_input_tokens", "cached_input_tokens"),
                    ("reasoning_tokens", "reasoning_output_tokens"),
                ):
                    value = turn_usage.get(input_key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        prior = usage[output_key] or 0
                        usage[output_key] = prior + int(value)
            continue
        if event_type == "turn.failed":
            failure = event.get("error")
            if isinstance(failure, Mapping):
                message = failure.get("message")
            else:
                message = failure
            errors.append(str(message or "turn failed"))
            continue
        if event_type != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, Mapping):
            continue
        item_type = item.get("type")
        if item_type in {"agent_message", "message"}:
            text = _text_from_item(item)
            if text:
                messages.append(text)
        elif item_type == "error":
            errors.append(str(item.get("message") or "unknown error"))
    if not usage_seen:
        usage = {key: None for key in usage}
    return ParsedCodexOutput(
        events=tuple(events),
        assistant_messages=tuple(messages),
        final_text=messages[-1] if messages else "",
        usage=usage,
        errors=tuple(errors),
        terminal_completed=terminal_completed,
    )


_SYSTEM_SKILLS = ("imagegen", "openai-docs", "plugin-creator", "skill-creator", "skill-installer")


@dataclass(frozen=True)
class RuntimeSession:
    environment: dict[str, str]
    workspace: Path
    config_home: Path


def _generated_config(session: RuntimeSession, read_paths: list[str], read_only: bool = False) -> str:
    """Construct the pinned native CLI boundary; never merge ambient settings."""
    filesystem: dict[str, Any] = {":minimal": "read", ":workspace_roots": "read" if read_only else "write"}
    for path in read_paths:
        filesystem[str(Path(path).expanduser().absolute())] = "read"
        filesystem[str(Path(path).expanduser().resolve())] = "read"
    filesystem[str(session.config_home)] = "deny"
    config: dict[str, Any] = {
        "approval_policy": "never",
        "check_for_update_on_startup": False,
        "cli_auth_credentials_store": "file",
        "forced_login_method": "chatgpt",
        "default_permissions": "participant",
        "web_search": "disabled",
        "project_doc_max_bytes": 0,
        "allow_login_shell": False,
        "history": {"persistence": "none"},
        "permissions": {"participant": {"filesystem": filesystem, "network": {"enabled": False}}},
        "features": {
            "apps": False,
            "plugins": False,
            "hooks": False,
            "multi_agent": False,
            "browser_use": False,
            "computer_use": False,
            "memories": False,
            "shell_snapshot": False,
            "unbounded_connection_retries": False,
        },
        "shell_environment_policy": {
            "inherit": "none",
            "set": {key: session.environment[key] for key in ("HOME", "PATH", "TMPDIR")},
        },
    }
    result = toml_dumps(config)
    for name in _SYSTEM_SKILLS:
        skill_path = session.config_home / "skills" / ".system" / name / "SKILL.md"
        result += "\n[[skills.config]]\npath = " + json.dumps(str(skill_path)) + "\nenabled = false\n"
    return result


def _stop_process_group(process: subprocess.Popen[str]) -> None:
    """Stop the CLI and children; a timed-out shell must not outlive its task."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class CodexExecutor:
    """Run a pinned Codex CLI with account auth in a fresh native sandbox."""

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.environ.get("CODEX_BIN") or shutil.which("codex") or "codex"

    def _source_auth_home(self, settings: Mapping[str, Any]) -> Path:
        configured = settings.get("auth_source_home")
        if isinstance(configured, str) and configured.strip():
            return Path(configured).expanduser().resolve()
        return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().resolve()

    @contextmanager
    def _session(
        self, settings: Mapping[str, Any], source: Path | None = None, *, read_only: bool = False
    ) -> Iterator[RuntimeSession]:
        if settings.get("toolchain_read_paths"):
            raise HarnessError(
                "filesystem overrides are unsupported; install tool dependencies in the harness environment"
            )
        with tempfile.TemporaryDirectory(prefix="eh-session-") as directory:
            root = Path(directory).resolve()
            home, config_home, workspace = (root / name for name in ("home", "codex", "work"))
            for folder in (home, config_home, workspace):
                folder.mkdir(mode=0o700)
            if source is not None:
                copy_files(source, workspace)
            (workspace / ".tmp").mkdir(exist_ok=True)
            source_auth = self._source_auth_home(settings) / "auth.json"
            if source_auth.is_file():
                auth = json.loads(source_auth.read_text())
                if auth.get("auth_mode") != "chatgpt":
                    raise HarnessError(
                        "Codex requires ChatGPT account authentication; API credentials are unsupported"
                    )
                shutil.copyfile(source_auth, config_home / "auth.json")
                (config_home / "auth.json").chmod(0o600)
            # PATH is configuration for tools, not inherited account/provider state.
            tool_paths = [
                str(Path(sys.executable).parent),
                "/opt/homebrew/bin",
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
            ]
            environment = {
                "HOME": str(home),
                "CODEX_HOME": str(config_home),
                "PATH": os.pathsep.join(tool_paths),
                "TMPDIR": str(workspace / ".tmp"),
                "SHELL": "/bin/bash",
                "LANG": "en_US.UTF-8",
            }
            session = RuntimeSession(environment, workspace, config_home)
            read_paths: list[str] = []
            # The installed Python runtime and its packages are explicit tool inputs.
            read_paths.extend(
                [str(Path(sys.prefix)), str(Path(sys.base_prefix)), str(Path(sys.executable).resolve().parent.parent)]
            )
            base = Path(sys.base_prefix)
            if base.name.startswith(("cpython-", "pypy-")) and base.parent.name == "python":
                # uv's minor-version alias is a sibling symlink of its versioned runtime.
                # Seatbelt needs the alias namespace as well as the resolved executable.
                read_paths.append(str(base.parent))
            (config_home / "config.toml").write_text(
                _generated_config(session, read_paths, read_only), encoding="utf-8"
            )
            yield session

    def _command(
        self,
        request: ExecutionRequest,
        *,
        output_schema_path: Path | None = None,
        image_inputs: tuple[ImageInput, ...] = (),
    ) -> list[str]:
        if not request.model:
            raise HarnessError("an explicit Codex model is required")
        command = [
            self.binary,
            "exec",
            "--strict-config",
            "--json",
            "--ephemeral",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--cd",
            str(request.cwd),
            "--color",
            "never",
            "--model",
            request.model,
        ]
        reasoning = request.settings.get("reasoning_effort")
        if isinstance(reasoning, str) and reasoning:
            command.extend(["-c", "model_reasoning_effort=" + json.dumps(reasoning)])
        if request.response_schema is not None:
            if output_schema_path is None:
                raise HarnessError("Codex output schema path is required for structured responses")
            command.extend(["--output-schema", str(output_schema_path)])
        for image in image_inputs:
            command.extend(["--image", str(request.cwd / image.path)])
        if image_inputs:
            # The explicit stdin positional tells the native CLI to consume
            # the request prompt from stdin after all repeatable image args.
            command.append("-")
        return command

    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
        """Check the same isolated file-backed account route used for execution."""
        try:
            with self._session(settings or {}) as session:
                version = subprocess.run(
                    [self.binary, "--version"],
                    env=session.environment,
                    cwd=session.workspace,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=15,
                    check=False,
                )
                if version.returncode or version.stdout.strip() != "codex-cli 0.154.0":
                    return AuthStatus(True, False, "supported participant runtime is standalone codex-cli 0.154.0")
                completed = subprocess.run(
                    [self.binary, "login", "status"],
                    cwd=session.workspace,
                    env=session.environment,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=15,
                    check=False,
                )
        except FileNotFoundError:
            return AuthStatus(False, False, f"Codex executable not found: {self.binary}")
        except (subprocess.TimeoutExpired, OSError, ValueError, HarnessError) as exc:
            return AuthStatus(True, False, str(exc))
        stdout, stderr = completed.stdout or "", completed.stderr or ""
        authenticated = completed.returncode == 0 and "Logged in using ChatGPT" in (stdout + stderr).splitlines()
        return AuthStatus(
            True,
            authenticated,
            "ChatGPT account login available" if authenticated else "Codex ChatGPT login unavailable",
            stdout,
            stderr,
        )

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Capture native output; only a terminal completed event establishes completion."""
        image_inputs = validate_image_inputs(request.images, request.cwd, purpose=request.purpose)
        timeout = float(request.settings.get("timeout_seconds", 600))
        started = monotonic()
        stdout, stderr = "", ""
        command: list[str] = []
        status, error = "failed", None
        returncode: int | None = None
        read_only = request.purpose == "evaluation"
        with self._session(request.settings, request.cwd, read_only=read_only) as session:
            stage_image_inputs(session.workspace, image_inputs)
            input_manifest = file_manifest(session.workspace)
            isolated = ExecutionRequest(
                request.prompt,
                session.workspace,
                request.model,
                request.settings,
                request.purpose,
                request.response_schema,
                request.images,
            )
            output_schema_path: Path | None = None
            if request.response_schema is not None:
                output_schema_path = session.config_home / "response-schema.json"
                output_schema_path.write_text(
                    json.dumps(request.response_schema, sort_keys=True, separators=(",", ":")), encoding="utf-8"
                )
                output_schema_path.chmod(0o600)
            command = self._command(isolated, output_schema_path=output_schema_path, image_inputs=image_inputs)
            try:
                process = subprocess.Popen(
                    command,
                    cwd=session.workspace,
                    env=session.environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    start_new_session=True,
                )
                try:
                    stdout, stderr = process.communicate(request.prompt, timeout=timeout)
                    returncode = process.returncode
                except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                    _stop_process_group(process)
                    stdout, stderr = process.communicate()
                    returncode = process.returncode
                    status = "interrupted" if isinstance(exc, KeyboardInterrupt) else "timeout"
                    error = f"{status} before completion (limit {timeout:g} seconds)"
                # Preserve partial artifacts as evidence, including on CLI failure.
                if read_only and file_manifest(session.workspace) != input_manifest:
                    status, error = "failed", "evaluator modified the read-only input workspace"
                shutil.rmtree(session.workspace / ".tmp", ignore_errors=True)
                # Preserve the historical no-image capture path.  Image
                # evaluations keep the caller's original bytes untouched even
                # when an evaluator attempts to modify its staged copy.
                if not read_only or not image_inputs:
                    copy_files(session.workspace, request.cwd)
            except OSError as exc:
                error = str(exc)
            if image_inputs:
                stdout = json.dumps(image_input_receipt(image_inputs), sort_keys=True) + "\n" + stdout
        parsed = parse_codex_jsonl(stdout)
        if parsed.errors:
            error = "; ".join(parsed.errors)
        terminal = any(event.get("type") == "turn.completed" for event in parsed.events)
        if returncode == 0 and terminal and not parsed.errors and error is None:
            status = "completed"
        elif error is None:
            error = "Codex did not emit a successful terminal turn.completed event"
        return ExecutionResult(
            tuple(command), returncode, status, monotonic() - started, stdout, stderr, parsed, error
        )


class MissingExecutor(HarnessError):
    """Raised when a caller requests an executor that is not connected."""
