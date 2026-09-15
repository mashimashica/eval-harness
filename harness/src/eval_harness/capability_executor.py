# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Connect the same capability service to isolated account-authenticated CLI sessions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from time import monotonic
from typing import Any, Mapping

from .artifacts import copy_workspace_deliverables, file_manifest
from .capability_environment import (
    CONTEXT_FOLDERS,
    TOOLS,
    CapabilityEnvironment,
    environment_prompt,
    prepare_environment,
)
from .errors import HarnessError
from .executor import (
    AuthStatus,
    ExecutionRequest,
    ExecutionResult,
    RuntimeSession,
    _generated_config,
    _stop_process_group,
    parse_codex_jsonl,
    toml_dumps,
)


def claude_capability_policy(session: RuntimeSession) -> dict[str, Any]:
    """Disable ambient customization while retaining the explicit local MCP service.

    Claude 2.1.270 --safe-mode disables even --mcp-config servers. The capability
    route uses its restricted configuration boundary with these pinned controls.
    """
    for flag in (
        "CLAUDE_CODE_DISABLE_CLAUDE_MDS",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
        "CLAUDE_CODE_DISABLE_ORG_MEMORY",
        "CLAUDE_CODE_DISABLE_BUNDLED_SKILLS",
        "CLAUDE_CODE_DISABLE_POLICY_SKILLS",
        "CLAUDE_CODE_DISABLE_HOOK_FORWARDING",
        "CLAUDE_CODE_SKIP_PLUGIN_MCP_SERVERS",
        "CLAUDE_CODE_DISABLE_PLUGIN_FORWARDING",
        "DISABLE_PLUGIN_AUTOLOAD",
    ):
        session.environment[flag] = "1"
    session.environment["ENABLE_CLAUDEAI_MCP_SERVERS"] = "false"
    session.environment["MCP_CONNECT_TIMEOUT_MS"] = "45000"
    session.environment["MCP_CONNECTION_NONBLOCKING"] = "false"
    session.environment["MCP_TOOL_TIMEOUT"] = "180000"
    return {"disableAllHooks": True, "disableBundledSkills": True}


def probe_environment(environment: CapabilityEnvironment, session: RuntimeSession) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [*environment.command, "--probe"],
            cwd=session.workspace,
            env=session.environment,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=45,
        )
        value = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f"shared capability preflight failed before model execution: {exc}") from exc
    if result.returncode or not isinstance(value, dict) or value.get("verified") is not True:
        raise HarnessError(f"shared capability preflight did not verify isolation: {result.stderr or value}")
    if not isinstance(value.get("tools"), list) or sorted(value["tools"]) != sorted(TOOLS):
        raise HarnessError("shared capability preflight is missing required tools")
    expected_rendering = environment.receipt["specification"].get("office_rendering")
    if expected_rendering is not None and value.get("office_rendering") != expected_rendering:
        raise HarnessError("shared capability preflight did not establish configured Office rendering")
    return value


def check_capability_runtime(executor: Any, settings: Mapping[str, Any], purpose: str) -> AuthStatus:
    with executor._session(settings) as session:
        prepared = prepare_environment(session.workspace, session.workspace.parent, settings, purpose)
        probe_environment(prepared, session)
    return AuthStatus(True, True, "account route and shared capability isolation verified; no model calls")


def _protected_manifest(workspace: Path, purpose: str) -> list[dict[str, Any]]:
    entries = file_manifest(workspace)
    if purpose == "evaluation":
        return [e for e in entries if Path(e["path"]).parts[0] not in {"scratch", ".tmp"}]
    return [e for e in entries if Path(e["path"]).parts[0] in CONTEXT_FOLDERS]


def execute_with_capabilities(executor: Any, request: ExecutionRequest, kind: str) -> ExecutionResult:
    """The native model process receives only MCP tools, never unrestricted host execution."""
    from .capability_sandbox import terminate_active_processes
    from .claude_executor import parse_claude_jsonl

    if request.images:
        raise HarnessError(
            "gdpval-v1 uses incremental render_pages/view_image; initial image attachments are unsupported"
        )
    if not request.model:
        raise HarnessError("an explicit model is required")
    started = monotonic()
    status, error, returncode = "failed", None, None
    stdout, stderr = "", ""
    command: list[str] = []
    # Account/model preflight is unchanged; no user configuration is inherited.
    if kind == "claude-code":
        executor.check_runtime(request.model, request.settings, request.purpose)
    else:
        auth = executor.check_auth(request.settings)
        if not auth.authenticated:
            raise HarnessError(auth.detail)
    with executor._session(request.settings, request.cwd) as session:
        prepared = prepare_environment(session.workspace, session.workspace.parent, request.settings, request.purpose)
        probe_environment(prepared, session)
        protected = _protected_manifest(session.workspace, request.purpose)
        prompt = request.prompt + environment_prompt(request.purpose)
        prompt += (
            "Allowed public HTTPS hostnames: "
            + ", ".join(prepared.receipt["specification"]["network_domains"])
            + ".\n"
        )
        (prepared.state / "effective_prompt.txt").write_text(prompt, encoding="utf-8")
        mcp = {"command": prepared.command[0], "args": list(prepared.command[1:])}
        if kind == "codex":
            config = _generated_config(session, [], read_only=True)
            # Override only the harness-generated tables, never merge ambient settings.
            config = config.replace(
                "[features]\n",
                "[features]\nshell_tool = false\nunified_exec = false\napply_patch_freeform = false\nview_image = false\n",
            )
            config += toml_dumps(
                {
                    "mcp_servers": {
                        "capabilities": {
                            **mcp,
                            "required": True,
                            "startup_timeout_sec": 45,
                            "tool_timeout_sec": 180,
                            # The owner authorizes these bounded work tools in the profile.
                            # Codex "auto" can still prompt and then fail with approval_policy=never.
                            "enabled_tools": list(TOOLS),
                            "default_tools_approval_mode": "approve",
                        }
                    },
                }
            )
            (session.config_home / "config.toml").write_text(config, encoding="utf-8")
            schema_path: Path | None = None
            if request.response_schema is not None:
                schema_path = session.config_home / "response-schema.json"
                schema_path.write_text(json.dumps(request.response_schema), encoding="utf-8")
            command = executor._command(
                ExecutionRequest(
                    prompt,
                    session.workspace,
                    request.model,
                    request.settings,
                    request.purpose,
                    request.response_schema,
                ),
                output_schema_path=schema_path,
            )
        else:
            mcp_path = session.config_home / "mcp.json"
            mcp_path.write_text(json.dumps({"mcpServers": {"capabilities": mcp}}), encoding="utf-8")
            policy = {**executor._model_settings(request.model), **claude_capability_policy(session)}
            command = [arg for arg in executor._base_command() if arg != "--safe-mode"] + [
                "--mcp-config",
                str(mcp_path),
                "--settings",
                json.dumps(policy),
                "--tools",
                "",
                "--allowedTools",
                "mcp__capabilities__*",
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
                str(request.settings.get("max_turns", 40)),
            ]
            if request.settings.get("reasoning_effort"):
                command += ["--effort", request.settings["reasoning_effort"]]
            if request.response_schema is not None:
                command += ["--json-schema", json.dumps(request.response_schema)]
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
                    prompt,
                    timeout=max(0.01, float(request.settings.get("timeout_seconds", 600)) - (monotonic() - started)),
                )
                returncode = process.returncode
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                _stop_process_group(process)
                stdout, stderr = process.communicate()
                returncode = process.returncode
                status = "interrupted" if isinstance(exc, KeyboardInterrupt) else "timeout"
                error = "capability session exceeded its execution boundary: " + status
            finally:
                _stop_process_group(process)
                # Workers run in separate process groups. Stop them before reading
                # originals or collecting outputs, including when the CLI exits early.
                terminate_active_processes(prepared.state)
            if protected != _protected_manifest(session.workspace, request.purpose):
                error = "capability session modified protected original inputs"
            if request.purpose != "evaluation":
                copy_workspace_deliverables(
                    session.workspace, request.cwd, exclude_top_level=(*CONTEXT_FOLDERS, "research", "scratch")
                )
        except OSError as exc:
            error = str(exc)
        finally:
            from .capability_service import finalize_interrupted_calls

            terminate_active_processes(prepared.state)
            finalize_interrupted_calls(prepared.state)
            receipt = prepared.capture(request.cwd)
            stdout = json.dumps(receipt, sort_keys=True) + "\n" + stdout
    parsed = (
        parse_codex_jsonl(stdout)
        if kind == "codex"
        else parse_claude_jsonl(stdout, require_structured_output=request.response_schema is not None)
    )
    if parsed.errors:
        error = "; ".join(parsed.errors)
    if kind == "claude-code":
        initial = next(
            (event for event in parsed.events if event.get("type") == "system" and event.get("subtype") == "init"),
            {},
        )
        expected_tools = {"mcp__capabilities__" + name for name in TOOLS}
        if request.response_schema is not None:
            # Claude's schema formatter has no filesystem or network capability.
            expected_tools.add("StructuredOutput")
        if set(initial.get("tools") or ()) != expected_tools or initial.get("plugins") or initial.get("skills"):
            error = "Claude did not expose exactly the declared capability tools without ambient customization"
        observed = set()
        for event in parsed.events:
            if event.get("type") == "assistant" and isinstance(event.get("message"), dict):
                model = event["message"].get("model")
                if model:
                    observed.add(model)
            if event.get("type") == "result" and isinstance(event.get("modelUsage"), dict):
                observed.update(event["modelUsage"])
        if observed and observed != {request.model}:
            error = f"Claude model changed: requested {request.model}; observed {sorted(observed)}"
    if returncode == 0 and parsed.terminal_completed and error is None:
        status = "completed"
    elif error is None:
        error = "CLI did not emit successful terminal completion"
    return ExecutionResult(tuple(command), returncode, status, monotonic() - started, stdout, stderr, parsed, error)
