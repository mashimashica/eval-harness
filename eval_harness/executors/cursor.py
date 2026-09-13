# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from eval_harness.capabilities import ExecutorCapabilities, ExecutorInput, ExecutorOutput
from eval_harness.executors.base import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    Executor,
    PreflightResult,
)
from eval_harness.executors.output_protocol import (
    OutputProtocolError,
    parse_cursor_output,
    parse_cursor_status,
    parse_strict_json_object,
)
from eval_harness.failures import Failure, FailureImpact, FailureKind
from eval_harness.reasoning import ReasoningEffortOption


_API_ENV_VARS = {
    "CURSOR_API_KEY",
    "CURSOR_AUTH_TOKEN",
    "CURSOR_LOCAL_PROVIDER",
    "CURSOR_LOCAL_PROVIDER_URL",
    "CURSOR_USE_LOCAL_PROVIDER",
    "CURSOR_USE_BEDROCK",
    "CURSOR_BASE_URL",
    "CURSOR_API_BASE_URL",
    "CURSOR_API_URL",
    "CURSOR_BEDROCK_ENDPOINT",
    "CURSOR_BEDROCK_ENDPOINT_URL",
    "BEDROCK_ENDPOINT_URL",
    "AWS_BEDROCK_ENDPOINT_URL",
    "AWS_ENDPOINT_URL_BEDROCK",
}
_COMMAND_ENV = "EVAL_CURSOR_COMMAND"
_SUPPORTED_VERSION = "2026.09.10-fd3934a"
_VERSION_PATTERN = re.compile(r"(?<![A-Za-z0-9])2026\.09\.10-fd3934a(?![A-Za-z0-9-])")
_CURSOR_AUTH_STORE_RELATIVE_PATH = Path("cursor") / "auth.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _tree_digest(root: Path) -> str:
    if not isinstance(root, Path):
        raise TypeError("task input tree root must be a Path")
    digest = hashlib.sha256()
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise OSError("task input tree root cannot be inspected") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise OSError("task input tree root must be a real directory")

    def frame(entry_type: bytes, logical: bytes, content_length: int) -> None:
        digest.update(entry_type)
        digest.update(len(logical).to_bytes(8, "big"))
        digest.update(logical)
        digest.update(content_length.to_bytes(8, "big"))

    def visit(directory: Path, prefix: str) -> None:
        try:
            directory_info = directory.lstat()
            if stat.S_ISLNK(directory_info.st_mode) or not stat.S_ISDIR(directory_info.st_mode):
                raise OSError("task input tree contains a non-directory node")
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise OSError("task input tree cannot be traversed") from exc
        for entry in entries:
            logical_text = f"{prefix}/{entry.name}" if prefix else entry.name
            logical = os.fsencode(logical_text)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise OSError("task input tree entry cannot be inspected") from exc
            mode = info.st_mode
            if stat.S_ISLNK(mode):
                raise OSError("task input tree cannot contain symlinks")
            if stat.S_ISDIR(mode):
                frame(b"D", logical, 0)
                visit(Path(entry.path), logical_text)
                continue
            if not stat.S_ISREG(mode):
                raise OSError("task input tree can contain only directories and regular files")

            frame(b"F", logical, info.st_size)
            descriptor: int | None = None
            total = 0
            try:
                descriptor = os.open(entry.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_dev != info.st_dev
                    or opened.st_ino != info.st_ino
                    or opened.st_size != info.st_size
                ):
                    raise OSError("task input tree file changed during read")
                while True:
                    chunk = os.read(descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    digest.update(chunk)
                after = os.fstat(descriptor)
                if (
                    after.st_dev != opened.st_dev
                    or after.st_ino != opened.st_ino
                    or after.st_size != opened.st_size
                    or total != info.st_size
                ):
                    raise OSError("task input tree file changed during read")
            except OSError as exc:
                raise OSError("task input tree file cannot be read") from exc
            finally:
                if descriptor is not None:
                    os.close(descriptor)

    frame(b"D", b"", 0)
    visit(root, "")
    return digest.hexdigest()


def subscription_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for name in _API_ENV_VARS:
        env.pop(name, None)
    return env


def _version_is_supported(version: str | None) -> bool:
    return version is not None and _VERSION_PATTERN.search(version) is not None


def _platform_is_supported() -> bool:
    return sys.platform.startswith("linux") and platform.machine().lower() in {"x86_64", "amd64"}


def _cursor_auth_store_path() -> Path | None:
    configured_home = os.getenv("XDG_CONFIG_HOME")
    if configured_home:
        path = Path(configured_home)
        if not path.is_absolute():
            return None
        return path / _CURSOR_AUTH_STORE_RELATIVE_PATH
    return Path.home() / ".config" / _CURSOR_AUTH_STORE_RELATIVE_PATH


def _is_empty_optional_credential(value: object) -> bool:
    # The published Cursor file credential manager treats object/array values
    # as configured credentials (JavaScript truthiness), even when empty.
    # Only the absent/null and canonical empty-string forms mean unset.
    return value is None or (isinstance(value, str) and value == "")


def _cursor_auth_store_error() -> str | None:
    """Return a static error when the local Cursor store is not account-only."""

    path = _cursor_auth_store_path()
    if path is None:
        return "Cursor account auth store location is invalid"
    try:
        payload = parse_strict_json_object(path.read_bytes())
    except (OSError, OutputProtocolError):
        return "Cursor account auth store is unavailable or malformed"

    access_token = payload.get("accessToken")
    refresh_token = payload.get("refreshToken")
    if (
        not isinstance(access_token, str)
        or not access_token.strip()
        or not isinstance(refresh_token, str)
        or not refresh_token.strip()
    ):
        return "Cursor account auth store lacks both required account tokens"
    if access_token == refresh_token:
        return "Cursor account auth store contains equal account tokens"

    api_key = payload.get("apiKey")
    if not _is_empty_optional_credential(api_key):
        return "Cursor API-key authentication is not an account subscription"
    bedrock_credentials = payload.get("bedrockCredentials")
    if not _is_empty_optional_credential(bedrock_credentials):
        return "Cursor Bedrock authentication is not an account subscription"
    return None


class CursorExecutor(Executor):
    name = "cursor"
    runtime = "host-subprocess"
    invocation_mode = "agent -p"
    tool_permission_mode = "project allowlist + Cursor sandbox"
    reasoning_effort: ReasoningEffortOption = None
    capabilities = ExecutorCapabilities(
        inputs=frozenset({ExecutorInput.PROMPT_TEXT, ExecutorInput.WORKSPACE_FILES}),
        outputs=frozenset({ExecutorOutput.FINAL_TEXT, ExecutorOutput.ARTIFACT_FILES}),
    )

    def __init__(self, *, network_enabled: bool = False, command: str | None = None) -> None:
        if type(network_enabled) is not bool:
            raise TypeError("network_enabled must be a bool")
        self.network_access_enabled = network_enabled
        resolved_command = command or os.getenv(_COMMAND_ENV, "agent")
        if resolved_command is None:
            raise RuntimeError("Cursor Agent command could not be resolved")
        self.command = resolved_command
        self._version: str | None = None

    def version(self) -> str | None:
        try:
            result = subprocess.run(
                [self.command, "--version"],
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=10,
                env=subscription_environment(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        text = (result.stdout or result.stderr).strip()
        self._version = text or None
        return self._version

    def preflight(self) -> PreflightResult:
        if shutil.which(self.command) is None and not os.path.isfile(self.command):
            return PreflightResult(
                executor=self.name, ok=False, details=(f"Cursor Agent command not found: {self.command}",)
            )

        if not _platform_is_supported():
            return PreflightResult(
                executor=self.name,
                ok=False,
                details=("Cursor Agent support is limited to the published Linux x86_64 build",),
            )

        version = self.version()
        if not _version_is_supported(version):
            return PreflightResult(
                executor=self.name,
                ok=False,
                version=version,
                details=(f"Cursor Agent build must be exactly {_SUPPORTED_VERSION}",),
            )
        try:
            status = subprocess.run(
                [self.command, "status", "--format", "json"],
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
                env=subscription_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return PreflightResult(
                executor=self.name,
                ok=False,
                version=version,
                details=(f"could not inspect Cursor Agent login status: {exc}",),
            )

        raw = status.stdout or status.stderr
        if status.returncode != 0:
            return PreflightResult(
                executor=self.name,
                ok=False,
                version=version,
                details=("Cursor Agent status command failed; account authentication was not verified",),
            )
        try:
            parsed_status = parse_cursor_status(raw)
        except OutputProtocolError:
            return PreflightResult(
                executor=self.name,
                ok=False,
                version=version,
                auth_mode="unknown",
                details=("Cursor Agent status did not return the documented JSON schema",),
            )
        if not parsed_status.is_authenticated:
            return PreflightResult(
                executor=self.name,
                ok=False,
                version=version,
                auth_mode="cursor-account",
                details=("Cursor Agent account authentication is incomplete",),
            )

        auth_store_error = _cursor_auth_store_error()
        if auth_store_error is not None:
            return PreflightResult(
                executor=self.name,
                ok=False,
                version=version,
                auth_mode="unknown",
                details=(auth_store_error,),
            )

        return PreflightResult(
            executor=self.name,
            ok=True,
            version=version,
            auth_mode="cursor-account",
            details=("Cursor account login detected with alternate provider environment variables removed",),
        )

    def _write_workspace_policy(self, workspace: Path, readonly_task_inputs_path: Path | None = None) -> None:
        cursor_dir = workspace / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        network_default = "allow" if self.network_access_enabled else "deny"
        sandbox = {
            "type": "workspace_readwrite",
            "additionalReadwritePaths": [],
            "additionalReadonlyPaths": [str(readonly_task_inputs_path.resolve())] if readonly_task_inputs_path else [],
            "disableTmpWrite": True,
            "enableSharedBuildCache": False,
            "networkPolicy": {"default": network_default, "allow": [], "deny": []},
        }
        (cursor_dir / "sandbox.json").write_text(
            json.dumps(sandbox, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        deny = [
            "Mcp(*:*)",
            "Write(task_inputs/**)",
            "Read(.env*)",
            "Write(.env*)",
        ]
        if not self.network_access_enabled:
            deny.append("WebFetch(*)")
        cli_config = {
            "version": 1,
            "editor": {"vimMode": False},
            "permissions": {
                "allow": ["Shell(*)", "Read(**)", "Write(**)"],
                "deny": deny,
            },
        }
        (cursor_dir / "cli.json").write_text(
            json.dumps(cli_config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _isolate_task_inputs(self, workspace: Path) -> tuple[Path | None, str | None]:
        legacy = workspace / "reference_files"
        if legacy.is_symlink() or legacy.exists():
            raise ValueError("Cursor executor does not accept the legacy reference_files input namespace")

        visible = workspace / "task_inputs"
        if visible.is_symlink():
            raise ValueError("Cursor task_inputs input must be a real directory")
        if not visible.exists():
            return None, None
        if not visible.is_dir():
            raise ValueError("Cursor task_inputs input must be a real directory")

        protected = workspace.parent / "cursor-task-inputs-readonly"
        if protected.is_symlink() or protected.is_file():
            protected.unlink()
        elif protected.is_dir():
            shutil.rmtree(protected)
        visible.rename(protected)
        try:
            digest = _tree_digest(protected)
        except BaseException:
            try:
                self._restore_task_inputs(workspace, protected)
            except BaseException as restore_error:
                raise RuntimeError("Cursor task input isolation could not restore task_inputs") from restore_error
            raise
        try:
            visible.symlink_to(protected.resolve(), target_is_directory=True)
        except BaseException as exc:
            try:
                self._restore_task_inputs(workspace, protected)
            except BaseException as restore_error:
                raise RuntimeError(
                    "Cursor task input isolation requires directory symlink support; refusing to run with writable inputs"
                ) from restore_error
            if isinstance(exc, OSError):
                raise RuntimeError(
                    "Cursor task input isolation requires directory symlink support; refusing to run with writable inputs"
                ) from exc
            raise
        return protected, digest

    @staticmethod
    def _restore_task_inputs(workspace: Path, protected: Path | None) -> None:
        if protected is None:
            return
        visible = workspace / "task_inputs"
        try:
            protected_info = protected.lstat()
        except OSError as exc:
            raise RuntimeError("Cursor task input restoration requires a protected real directory") from exc
        if stat.S_ISLNK(protected_info.st_mode) or not stat.S_ISDIR(protected_info.st_mode):
            raise RuntimeError("Cursor task input restoration requires a protected real directory")
        if visible.is_symlink() or visible.is_file():
            visible.unlink()
        elif visible.is_dir():
            shutil.rmtree(visible)
        try:
            protected.rename(visible)
        except OSError as exc:
            raise RuntimeError("Cursor task input restoration could not restore the protected directory") from exc

    def build_command(self, request: ExecutionRequest) -> list[str]:
        command = [
            self.command,
            "-p",
            "--trust",
            "--workspace",
            str(request.workspace),
            "--output-format",
            "json",
            "--sandbox",
            "enabled",
        ]
        if request.model:
            command.extend(["--model", request.model])
        return command

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        request.workspace.mkdir(parents=True, exist_ok=True)
        request.deliverables_dir.mkdir(parents=True, exist_ok=True)
        request.executor_dir.mkdir(parents=True, exist_ok=True)
        protected_task_inputs, task_inputs_digest = self._isolate_task_inputs(request.workspace)

        started_at = _utc_now()
        stdout_path = request.executor_dir / "stdout.log"
        stderr_path = request.executor_dir / "stderr.log"
        exit_code: int | None = None
        status = ExecutionStatus.FAILED
        stdout = ""
        stderr = ""
        task_inputs_integrity_ok = True
        task_inputs_integrity_error: str | None = None
        restore_error: BaseException | None = None
        has_deliverable = False
        output_text: str | None = None
        protocol_error: str | None = None
        failure: Failure | None = None
        cleanup_interrupted = False
        preparation_complete = False
        log_persistence_errors: list[str] = []

        try:
            self._write_workspace_policy(request.workspace, protected_task_inputs)
            (request.executor_dir / "prompt.txt").write_text(request.task.prompt, encoding="utf-8")
            preparation_complete = True
            completed = subprocess.run(
                self.build_command(request),
                input=request.task.prompt,
                capture_output=True,
                text=True,
                errors="replace",
                cwd=request.workspace,
                env=subscription_environment(request.environment),
                timeout=request.timeout_seconds,
                check=False,
            )
            exit_code = completed.returncode
            stdout = _text(completed.stdout)
            stderr = _text(completed.stderr)
            if exit_code != 0 and failure is None:
                failure = Failure(FailureKind.PROCESS, "process_exit", FailureImpact.RUN)
            if exit_code == 0 and failure is None:
                try:
                    parsed = parse_cursor_output(stdout)
                except OutputProtocolError as exc:
                    failure = Failure(FailureKind.PROTOCOL, "output_protocol", FailureImpact.RUN)
                    protocol_error = exc.code.value
                else:
                    output_text = parsed.output_text
                    has_deliverable = request.deliverables_dir.is_dir() and any(
                        path.is_file() for path in request.deliverables_dir.rglob("*")
                    )
                    status = (
                        ExecutionStatus.COMPLETED
                        if output_text is not None or has_deliverable
                        else ExecutionStatus.NO_DELIVERABLE
                    )
        except subprocess.TimeoutExpired as exc:
            stdout = _text(exc.stdout)
            stderr = _text(exc.stderr)
            status = ExecutionStatus.TIMED_OUT
            failure = Failure(FailureKind.TIMEOUT, "timeout", FailureImpact.RUN)
        except KeyboardInterrupt:
            if not preparation_complete:
                raise
            status = ExecutionStatus.INTERRUPTED
            failure = Failure(FailureKind.INTERRUPTED, "interrupted", FailureImpact.RUN)
        except OSError as exc:
            if not preparation_complete:
                raise
            stderr = str(exc) + "\n"
            status = ExecutionStatus.FAILED
            failure = Failure(FailureKind.PROCESS, "process_spawn", FailureImpact.RUN)
        finally:
            if protected_task_inputs is not None and task_inputs_digest is not None:
                try:
                    observed_digest = _tree_digest(protected_task_inputs)
                except KeyboardInterrupt:
                    cleanup_interrupted = True
                    task_inputs_integrity_ok = False
                    task_inputs_integrity_error = "task input integrity check was interrupted"
                    if failure is None:
                        failure = Failure(FailureKind.INTERRUPTED, "interrupted", FailureImpact.RUN)
                        status = ExecutionStatus.INTERRUPTED
                    else:
                        task_inputs_integrity_error = "task input integrity check was interrupted after execution"
                except BaseException:
                    task_inputs_integrity_ok = False
                    task_inputs_integrity_error = "task input integrity could not be verified"
                    if failure is None:
                        failure = Failure(FailureKind.INTEGRITY, "task_input_integrity", FailureImpact.RUN)
                        status = ExecutionStatus.FAILED
                    else:
                        task_inputs_integrity_error = "task input integrity check failed after execution"
                else:
                    task_inputs_integrity_ok = observed_digest == task_inputs_digest
                    if not task_inputs_integrity_ok:
                        task_inputs_integrity_error = "task input tree changed during execution"
                        stderr += "\nCursor executor detected task-input mutation; failing closed.\n"
                        if failure is None:
                            failure = Failure(FailureKind.INTEGRITY, "task_input_mutation", FailureImpact.RUN)
                            status = ExecutionStatus.FAILED
                        else:
                            task_inputs_integrity_error = "task input tree changed after execution"
            try:
                self._restore_task_inputs(request.workspace, protected_task_inputs)
            except KeyboardInterrupt as exc:
                cleanup_interrupted = True
                restore_error = exc
                if failure is None:
                    failure = Failure(FailureKind.INTERRUPTED, "interrupted", FailureImpact.RUN)
                    status = ExecutionStatus.INTERRUPTED
            except Exception as exc:
                restore_error = exc
                if failure is None:
                    failure = Failure(FailureKind.INTEGRITY, "task_input_restore", FailureImpact.RUN)
                    status = ExecutionStatus.FAILED
            for log_path, log_name, content in (
                (stdout_path, "stdout.log", stdout),
                (stderr_path, "stderr.log", stderr),
            ):
                try:
                    log_path.write_text(content, encoding="utf-8")
                except OSError:
                    log_persistence_errors.append(log_name)
            if log_persistence_errors and failure is None:
                failure = Failure(FailureKind.PROCESS, "log_persistence", FailureImpact.RUN)
                status = ExecutionStatus.FAILED

        # Cleanup can discover a failure after the executor has parsed a valid
        # response.  Preserve the typed failure boundary by discarding every
        # output channel before constructing ExecutionResult.
        if failure is not None:
            output_text = None

        available_outputs: frozenset[ExecutorOutput] = (
            frozenset(
                output
                for output, present in (
                    (ExecutorOutput.FINAL_TEXT, output_text is not None),
                    (ExecutorOutput.ARTIFACT_FILES, True),
                )
                if present
            )
            if failure is None
            else frozenset()
        )
        metadata: dict[str, object] = {
            "sandbox": "enabled/workspace_readwrite",
            "tool_permission_mode": self.tool_permission_mode,
            "network_policy": "allow" if self.network_access_enabled else "deny",
            "cloud_execution": False,
            "structured_output": "json",
            "usage_mode": "cursor-account-usage",
            "task_inputs_isolation": "outside-workspace + additionalReadonlyPaths"
            if protected_task_inputs is not None
            else "none",
            "task_inputs_integrity_verified": task_inputs_integrity_ok,
            "task_inputs_cleanup_interrupted": cleanup_interrupted,
            "api_environment_removed": sorted(_API_ENV_VARS),
        }
        if task_inputs_integrity_error is not None:
            metadata["task_inputs_integrity_detail"] = task_inputs_integrity_error
        if restore_error is not None:
            metadata["task_inputs_restore_error"] = type(restore_error).__name__
        if log_persistence_errors:
            metadata["log_persistence_errors"] = list(log_persistence_errors)
        if protocol_error is not None:
            metadata["protocol_error"] = protocol_error
        return ExecutionResult(
            task_id=request.task.task_id,
            executor=self.name,
            executor_version=self._version or self.version(),
            invocation_mode=self.invocation_mode,
            auth_mode="cursor-account",
            workspace=request.workspace,
            deliverables_dir=request.deliverables_dir,
            status=status,
            started_at=started_at,
            finished_at=_utc_now(),
            exit_code=exit_code,
            available_outputs=available_outputs,
            failure=failure,
            output_text=output_text,
            metadata=metadata,
            runtime="host-subprocess",
            model_id=request.model or None,
            effective_reasoning_effort=None,
            effective_reasoning_effort_available=False,
        )
