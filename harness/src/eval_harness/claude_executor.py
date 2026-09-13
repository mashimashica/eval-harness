# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Claude Code subscription execution with confined file tools and fresh context."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from typing import Any, Iterator, Mapping

from .artifacts import copy_files, file_manifest
from .errors import HarnessError
from .executor import (
    AuthStatus,
    ExecutionRequest,
    ExecutionResult,
    ParsedCodexOutput,
    RuntimeSession,
    _stop_process_group,
)


def parse_claude_jsonl(stdout: str) -> ParsedCodexOutput:
    """Adapt the retained Claude agent's stream/result usage convention."""
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
            cost = event.get("total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                usage["cost_usd"] = float(cost)
    terminal = any(event.get("type") == "result" and event.get("subtype") == "success" for event in events)
    return ParsedCodexOutput(tuple(events), tuple(messages), final, usage, tuple(errors), terminal)


class ClaudeExecutor:
    """Account auth, safe mode and restricted file tools; shell execution is unsupported."""

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"

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
        if not request.model:
            raise HarnessError("an explicit Claude model is required")
        started = monotonic()
        stdout, stderr = "", ""
        status, error = "failed", None
        returncode: int | None = None
        with self._session(request.settings, request.cwd) as session:
            read_only = request.purpose == "evaluation"
            input_manifest = file_manifest(session.workspace)
            tools = "Read,Glob,Grep" if read_only else "Read,Write,Edit,Glob,Grep"
            command = self._base_command() + [
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
                "--tools",
                tools,
                "--allowedTools",
                tools,
                "--model",
                request.model,
                "--max-turns",
                str(request.settings.get("max_turns", 12)),
            ]
            effort = request.settings.get("reasoning_effort")
            if isinstance(effort, str):
                command += ["--effort", effort]
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
                        request.prompt, timeout=float(request.settings.get("timeout_seconds", 600))
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
                copy_files(session.workspace, request.cwd)
            except OSError as exc:
                error = str(exc)
        parsed = parse_claude_jsonl(stdout)
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
        if observed_models and observed_models != {request.model}:
            error = f"Claude model changed: requested {request.model}; observed {sorted(observed_models)}"
        if returncode == 0 and terminal and error is None:
            status = "completed"
        elif error is None:
            error = "Claude did not emit a successful terminal result"
        return ExecutionResult(
            tuple(command), returncode, status, monotonic() - started, stdout, stderr, parsed, error
        )
