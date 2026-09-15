# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Claude Code subscription execution with confined file tools and fresh context."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from typing import Any, Iterator, Mapping

from .artifacts import copy_files, copy_workspace_deliverables, file_manifest, sha256_bytes
from .errors import HarnessError
from .executor import (
    AuthStatus,
    ExecutionRequest,
    ExecutionResult,
    ParsedCodexOutput,
    RuntimeSession,
    _stop_process_group,
)
from .image_inputs import ImageInput, image_input_receipt, stage_image_inputs, validate_image_inputs
from .models import CLAUDE_DISPLAY_NAMES, CLAUDE_EFFORTS


def parse_claude_jsonl(stdout: str, *, require_structured_output: bool = False) -> ParsedCodexOutput:
    """Adapt Claude's stream/result events and canonicalize native JSON output."""
    events: list[dict[str, Any]] = []
    messages: list[str] = []
    errors: list[str] = []
    usage: dict[str, int | float | None] = {
        "input_tokens": None,
        "output_tokens": None,
        "cached_input_tokens": None,
        "cache_creation_input_tokens": None,
        "reasoning_tokens": None,
        "cost_usd": None,
    }
    final = ""
    structured_output: Any = None
    structured_output_seen = False
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        events.append(event)
        if event.get("type") == "assistant":
            content = (event.get("message") or {}).get("content", [])
            text = "".join(item.get("text", "") for item in content if item.get("type") == "text")
            if text:
                messages.append(text)
        if event.get("type") == "result":
            final = event.get("result", "") if isinstance(event.get("result"), str) else ""
            if "structured_output" in event:
                structured_output_seen = True
                structured_output = event.get("structured_output")
            if event.get("is_error") or event.get("subtype") != "success":
                errors.append(str(event.get("subtype") or "Claude result failed"))
            measured = event.get("usage") or {}
            for source, target in (
                ("input_tokens", "input_tokens"),
                ("output_tokens", "output_tokens"),
                ("cache_read_input_tokens", "cached_input_tokens"),
                ("cache_creation_input_tokens", "cache_creation_input_tokens"),
            ):
                value = measured.get(source)
                if isinstance(value, int) and not isinstance(value, bool):
                    usage[target] = value
            reasoning = (measured.get("output_tokens_details") or {}).get("thinking_tokens")
            if isinstance(reasoning, int) and not isinstance(reasoning, bool):
                usage["reasoning_tokens"] = reasoning
            cost = event.get("total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                # The CLI reports a token-price estimate even on an included
                # subscription. It does not expose an actual incremental bill.
                usage["reported_cost_usd"] = float(cost)
    if structured_output_seen:
        try:
            final = json.dumps(structured_output, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            final = ""
            errors.append(f"Claude structured output was not JSON-serializable: {exc}")
    elif require_structured_output:
        final = ""
        errors.append("Claude structured output was missing")
    terminal = any(event.get("type") == "result" and event.get("subtype") == "success" for event in events)
    return ParsedCodexOutput(tuple(events), tuple(messages), final, usage, tuple(errors), terminal)


class ClaudeExecutor:
    """Subscription sessions with restricted files or verified native Bash isolation."""

    _subscription_checked: dict[str, float] = {}

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"
        self._checked: dict[str, float] = {}

    def _subscription_access(self, settings: Mapping[str, Any]) -> None:
        """Read the native OAuth account status without model or billing calls."""
        oauth = self._credentials(settings)["claudeAiOauth"]
        token = oauth.get("accessToken")
        if not isinstance(token, str) or not token:
            raise HarnessError("Claude subscription access token unavailable; run claude auth login")
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        if monotonic() - self._subscription_checked.get(fingerprint, -1000) < 300:
            return
        data: dict[str, Any] = {}
        # The live profile states both active subscription and overage status;
        # polling the separate usage dashboard is unnecessary for eligibility.
        for endpoint in ("profile",):
            request = urllib.request.Request(
                "https://api.anthropic.com/api/oauth/" + endpoint,
                headers={
                    "Authorization": "Bearer " + token,
                    "anthropic-beta": "oauth-2025-04-20",
                    "User-Agent": "claude-code/2.1.270",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    data[endpoint] = json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise HarnessError("Claude subscription authentication expired; run claude auth login") from None
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After", "unspecified")
                    raise HarnessError(
                        f"Claude account metadata rate-limited; Retry-After={retry_after}. No model request sent"
                    ) from None
                raise HarnessError(f"Claude subscription preflight unavailable (HTTP {exc.code})") from None
            except (OSError, ValueError):
                raise HarnessError("Claude subscription preflight unavailable; no model request was sent") from None
        if any(not isinstance(value, dict) for value in data.values()):
            raise HarnessError("Claude account preflight returned an unsupported status format")
        organization = data["profile"].get("organization", {})
        if not isinstance(organization, dict):
            raise HarnessError("Claude account preflight could not confirm subscription-only billing")
        if organization.get("subscription_status") != "active":
            raise HarnessError("Claude requires an active subscription")
        if organization.get("has_extra_usage_enabled") is not False:
            raise HarnessError(
                "subscription-only execution requires Claude extra usage to be disabled; no request sent"
            )
        self._subscription_checked[fingerprint] = monotonic()

    def check_runtime(
        self, model: str | None, settings: Mapping[str, Any], purpose: str = "application"
    ) -> AuthStatus:
        """Verify exact native selection/effort with zero-generation local commands."""
        effort = settings.get("reasoning_effort")
        if model not in CLAUDE_EFFORTS:
            raise HarnessError(f"unsupported exact Claude model ID: {model}")
        if effort is not None and effort not in CLAUDE_EFFORTS[model]:
            raise HarnessError(f"unsupported reasoning_effort {effort!r} for {model}")
        key = json.dumps([model, settings, purpose], sort_keys=True)
        if monotonic() - self._checked.get(key, -1000) < 30:
            return AuthStatus(True, True, "Claude exact model/effort and subscription-only route verified")
        status = self.check_auth(settings)
        if not status.authenticated:
            raise HarnessError(status.detail)
        self._subscription_access(settings)
        with self._session(settings) as session:
            if settings.get("tool_mode") == "sandboxed_shell":
                with self._invocation(session, model, settings, purpose):
                    pass  # Native sandbox/toolchain preflight, no model generation.
            command = self._base_command() + [
                "--settings",
                json.dumps(self._model_settings(model)),
                "--print",
                "--output-format",
                "json",
                "--tools",
                "",
                "--model",
                model,
            ]
            if isinstance(effort, str):
                command += ["--effort", effort]
            checks = [("model", model, f"Set model to `{CLAUDE_DISPLAY_NAMES[model]}` for this session only")]
            if isinstance(effort, str):
                checks.append(("effort", effort, "Set effort level to " + effort + " ("))
            for name, value, expected in checks:
                try:
                    result = subprocess.run(
                        command,
                        input=f"/{name} {value}",
                        cwd=session.workspace,
                        env=session.environment,
                        capture_output=True,
                        text=True,
                        errors="replace",
                        timeout=25,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise HarnessError(f"Claude {name} preflight timed out; no model request was sent") from exc
                try:
                    payload = json.loads(result.stdout)
                except ValueError:
                    raise HarnessError(f"Claude {name} preflight did not return a local result") from None
                message = str(payload.get("result", ""))
                if (
                    result.returncode
                    or payload.get("num_turns") != 0
                    or payload.get("local_command") != name
                    or payload.get("modelUsage")
                    or payload.get("is_error")
                    or not message.startswith(expected)
                ):
                    raise HarnessError(f"Claude {name} unavailable for {model}: {message[:400]}")
        from .capability_environment import enabled

        if enabled(settings):
            from .capability_executor import check_capability_runtime

            check_capability_runtime(self, settings, purpose)
        self._checked[key] = monotonic()
        return AuthStatus(True, True, "Claude exact model/effort and subscription-only route verified")

    @staticmethod
    def _model_settings(model: str) -> dict[str, Any]:
        return {"switchModelsOnFlag": False, "fallbackModel": [], "availableModels": [model]}

    @contextmanager
    def _invocation(
        self, session: RuntimeSession, model: str, settings: Mapping[str, Any], purpose: str
    ) -> Iterator[tuple[list[str], dict[str, Any] | None]]:
        """Build the exact native permissions before allowing a participant call."""
        read_only = purpose == "evaluation"
        if settings.get("tool_mode", "files") == "files":
            names = "Read,Glob,Grep" if read_only else "Read,Write,Edit,Glob,Grep"
            yield (
                ["--settings", json.dumps(self._model_settings(model)), "--tools", names, "--allowedTools", names],
                None,
            )
            return
        from .claude_sandbox import DISALLOWED_TOOLS, copy_office_runtime, sandbox_settings, verify_sandbox

        if sys.platform != "darwin":
            raise HarnessError("Claude sandboxed_shell is verified on macOS only")
        runtime = session.workspace.parent / "runtime"
        wrapper = copy_office_runtime(runtime)
        # Long TMPDIR paths cause the native CLI to fall back to shared /tmp.
        original_environment = dict(session.environment)
        try:
            with tempfile.TemporaryDirectory(prefix="ehc-", dir="/private/tmp") as temporary:
                scratch = Path(temporary).resolve()
                session.environment.update(
                    {
                        "CLAUDE_CODE_TMPDIR": str(scratch),
                        "TMPDIR": str(scratch),
                        "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1",
                        "PYTHONNOUSERSITE": "1",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "PATH": str(wrapper.parent) + ":/usr/bin:/bin",
                    }
                )
                policy = {
                    **sandbox_settings(session, runtime, scratch, read_only=read_only),
                    **self._model_settings(model),
                }
                path = session.config_home / "invocation.json"
                path.write_text(json.dumps(policy, sort_keys=True))
                path.chmod(0o600)
                options = [
                    "--settings",
                    str(path),
                    "--tools=Bash",
                    "--allowedTools=Bash",
                    "--disallowedTools=" + DISALLOWED_TOOLS,
                ]
                native = verify_sandbox(self._base_command() + options, session)
                note = (
                    "Use only Bash in this isolated workspace. The command python-openpyxl runs an isolated Python 3.13 "
                    "with openpyxl for XLSX. Use canonical paths from pwd. No network access. "
                    + (
                        "You are a read-only evaluator: inspect saved files and report to stdout. Do not create, modify, recalculate, regenerate, or replace submissions. "
                        if read_only
                        else "Write deliverables in the workspace. The reference_files, skill, creation_inputs and creator_skills directories are read-only. "
                    )
                )
                options += ["--append-system-prompt", note]
                normalized = (
                    json.dumps(policy, sort_keys=True)
                    .replace(str(session.workspace.parent), "$SESSION")
                    .replace(str(scratch), "$CLI_TMP")
                    .replace(str(Path.home().resolve()), "$HOST_HOME")
                )
                receipt = {
                    "type": "harness.runtime",
                    "tool_mode": "sandboxed_shell",
                    "policy": json.loads(normalized),
                    "policy_sha256": sha256_bytes(normalized.encode()),
                    "python_version": sys.version,
                    "sandbox_enabled": native.get("enabled"),
                    "sandbox_strict": native.get("strictMode"),
                }
                yield options, receipt
        finally:
            session.environment.clear()
            session.environment.update(original_environment)

    def _credentials(self, settings: Mapping[str, Any]) -> dict[str, Any]:
        configured = settings.get("auth_source_home") or os.environ.get("CLAUDE_CONFIG_DIR")
        source = Path(str(configured)).expanduser() if configured else Path.home() / ".claude"
        credential_file = source / ".credentials.json"
        if credential_file.is_file():
            data = json.loads(credential_file.read_text())
        elif sys.platform == "darwin" and not configured:
            result = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=10,
                check=False,
            )
            if result.returncode:
                raise HarnessError("Claude subscription credentials unavailable; run claude auth login")
            data = json.loads(result.stdout)
        else:
            raise HarnessError("Claude subscription credentials unavailable; run claude auth login")
        if not isinstance(data, dict) or not isinstance(data.get("claudeAiOauth"), dict):
            raise HarnessError("Claude credentials must contain subscription OAuth authentication")
        # No API keys, provider settings, memory, plugins or user instructions are copied.
        return {"claudeAiOauth": data["claudeAiOauth"]}

    @contextmanager
    def _session(self, settings: Mapping[str, Any], source: Path | None = None) -> Iterator[RuntimeSession]:
        credentials = self._credentials(settings)
        with tempfile.TemporaryDirectory(prefix="eh-claude-") as directory:
            root = Path(directory).resolve()
            home, config_home, workspace = (root / name for name in ("home", "claude", "work"))
            for folder in (home, config_home, workspace):
                folder.mkdir(mode=0o700)
            if source is not None:
                copy_files(source, workspace)
            credential_file = config_home / ".credentials.json"
            credential_file.write_text(json.dumps(credentials))
            credential_file.chmod(0o600)
            environment = {
                "HOME": str(home),
                "CLAUDE_CONFIG_DIR": str(config_home),
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                "SHELL": "/bin/bash",
                "TMPDIR": str(root),
                "LANG": "en_US.UTF-8",
                "DISABLE_AUTOUPDATER": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "CLAUDE_CODE_DISABLE_1M_CONTEXT": "1",
                "CLAUDE_CODE_DISABLE_FAST_MODE": "1",
                "CLAUDE_CODE_MAX_RETRIES": "0",
                "CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY": "1",
            }
            yield RuntimeSession(environment, workspace, config_home)

    def _base_command(self) -> list[str]:
        return [self.binary, "--safe-mode", "--restricted", "--setting-sources", "", "--strict-mcp-config"]

    @staticmethod
    def _input_payload(prompt: str, images: tuple[ImageInput, ...]) -> str:
        """Encode an image request in Claude's native stream-json input format."""
        if not images:
            return prompt
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for index, image in enumerate(images, 1):
            label = f"Image {index}: {image.path}"
            # The evaluator prompt already carries this shared mapping.  Add
            # a block only for direct executor callers whose prompt lacks it.
            if label not in prompt:
                content.append({"type": "text", "text": label})
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(image.data).decode("ascii"),
                    },
                }
            )
        return (
            json.dumps(
                {
                    "type": "user",
                    "message": {"role": "user", "content": content},
                    "parent_tool_use_id": None,
                    "session_id": "",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
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
                if version.returncode or version.stdout.strip() != "2.1.270 (Claude Code)":
                    return AuthStatus(True, False, "supported participant runtime is Claude Code 2.1.270")
                result = subprocess.run(
                    self._base_command() + ["auth", "status"],
                    cwd=session.workspace,
                    env=session.environment,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=20,
                    check=False,
                )
                status = json.loads(result.stdout)
                authenticated = (
                    result.returncode == 0
                    and status.get("loggedIn") is True
                    and status.get("authMethod") == "claude.ai"
                    and status.get("apiProvider") == "firstParty"
                    and status.get("subscriptionType") in {"pro", "max", "team", "enterprise"}
                )
                # Deliberately omit account email and credential-bearing source output.
                detail = (
                    "Claude subscription login available" if authenticated else "Claude subscription login unavailable"
                )
                return AuthStatus(True, authenticated, detail)
        except FileNotFoundError:
            return AuthStatus(False, False, f"Claude executable not found: {self.binary}")
        except (OSError, ValueError, subprocess.TimeoutExpired, HarnessError):
            return AuthStatus(True, False, "Claude subscription login unavailable; run claude auth login")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        from .capability_environment import enabled

        if enabled(request.settings):
            from .capability_executor import execute_with_capabilities

            return execute_with_capabilities(self, request, "claude-code")
        image_inputs = validate_image_inputs(request.images, request.cwd, purpose=request.purpose)
        if not request.model:
            raise HarnessError("an explicit Claude model is required")
        self.check_runtime(request.model, request.settings, request.purpose)
        started = monotonic()
        stdout, stderr = "", ""
        status, error = "failed", None
        returncode: int | None = None
        with (
            self._session(request.settings, request.cwd) as session,
            self._invocation(session, request.model, request.settings, request.purpose) as (options, receipt),
        ):
            stage_image_inputs(session.workspace, image_inputs)
            read_only = request.purpose == "evaluation"
            input_manifest = file_manifest(session.workspace)
            command = (
                self._base_command()
                + options
                + [
                    "--disable-slash-commands",
                    "--print",
                    "--verbose",
                    "--output-format",
                    "stream-json",
                    "--no-session-persistence",
                    "--no-chrome",
                    "--permission-mode",
                    "dontAsk",
                    "--permission-prompts",
                    "none",
                    "--model",
                    request.model,
                    "--max-turns",
                    str(request.settings.get("max_turns", 12)),
                ]
            )
            effort = request.settings.get("reasoning_effort")
            if isinstance(effort, str):
                command += ["--effort", effort]
            if request.response_schema is not None:
                command += [
                    "--json-schema",
                    json.dumps(request.response_schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                ]
            if image_inputs:
                command += ["--input-format", "stream-json"]
            input_payload = self._input_payload(request.prompt, image_inputs)
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
                    stdout, stderr = process.communicate(
                        input_payload, timeout=float(request.settings.get("timeout_seconds", 600))
                    )
                    returncode = process.returncode
                except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                    _stop_process_group(process)
                    stdout, stderr = process.communicate()
                    returncode = process.returncode
                    status = "interrupted" if isinstance(exc, KeyboardInterrupt) else "timeout"
                    error = f"Claude {status} before completing the bounded invocation"
                if read_only and file_manifest(session.workspace) != input_manifest:
                    status, error = "failed", "evaluator modified the read-only input workspace"
                if not read_only:
                    if request.settings.get("tool_mode") == "sandboxed_shell":
                        from .claude_sandbox import CONTEXT_FOLDERS

                        copy_workspace_deliverables(session.workspace, request.cwd, exclude_top_level=CONTEXT_FOLDERS)
                    else:
                        copy_files(session.workspace, request.cwd)
            except (OSError, HarnessError) as exc:
                error = str(exc)
            if image_inputs:
                stdout = json.dumps(image_input_receipt(image_inputs), sort_keys=True) + "\n" + stdout
            if receipt is not None:
                stdout = json.dumps(receipt) + "\n" + stdout
        parsed = parse_claude_jsonl(stdout, require_structured_output=request.response_schema is not None)
        terminal = any(event.get("type") == "result" and event.get("subtype") == "success" for event in parsed.events)
        if parsed.errors:
            error = "; ".join(parsed.errors)
        observed_models = {
            str(event.get("model"))
            for event in parsed.events
            if event.get("type") == "system" and event.get("subtype") == "init" and event.get("model")
        }
        observed_models.update(
            str(event["message"]["model"])
            for event in parsed.events
            if event.get("type") == "assistant"
            and isinstance(event.get("message"), dict)
            and event["message"].get("model")
        )
        for event in parsed.events:
            if event.get("type") == "result" and isinstance(event.get("modelUsage"), dict):
                observed_models.update(str(model) for model in event["modelUsage"])
        if observed_models and observed_models != {request.model}:
            error = f"Claude model changed: requested {request.model}; observed {sorted(observed_models)}"
        if returncode == 0 and terminal and error is None:
            status = "completed"
        elif error is None:
            error = "Claude did not emit a successful terminal result"
        return ExecutionResult(
            tuple(command), returncode, status, monotonic() - started, stdout, stderr, parsed, error
        )
