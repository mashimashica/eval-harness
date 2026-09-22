# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared MCP capability service for GDPval creation, application, and evaluation.

This is a deliberately small stdio MCP implementation.  It does not import an MCP
SDK, candidate packages, or executor code.  The trusted parent process supplies a
private state directory and an explicit capability configuration; every tool call is
recorded before its result is returned to the participant runtime.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .capability_network import (
    HTTPExchange,
    NetworkClient,
    NetworkError,
    SearchAttempt,
    fetch_summary,
    json_summary,
    search_summary,
)
from .capability_sandbox import (
    MAX_SHELL_TIMEOUT_SECONDS,
    MAX_TOOL_TEXT_BYTES,
    SandboxError,
    SandboxPolicy,
    clean_environment,
    make_policy,
    run_sandboxed,
    terminate_active_processes,
    verify_policy,
)
from .errors import HarnessError

MAX_WHEEL_BYTES = 20 * 1024 * 1024
MAX_WHEEL_ENTRIES = 10_000
MAX_WHEEL_EXPANDED_BYTES = 200 * 1024 * 1024
MAX_WHEEL_FILE_BYTES = 100 * 1024 * 1024
MAX_VIEW_IMAGE_BYTES = 50 * 1024 * 1024
MAX_VIEW_IMAGE_DIMENSION = 20_000
MAX_VIEW_IMAGE_PIXELS = 100_000_000
MAX_REGION_COORDINATE = 20_000
CONTEXT_FOLDERS = ("reference_files", "skill", "creation_inputs", "creator_skills", "evidence")
CONFIG_KEYS = {
    "network_domains",
    "network_policy",
    "python",
    "python_roots",
    "package_paths",
    "tool_roots",
    "path",
    "office_rendering",
    "shell_timeout_seconds",
    "fetch_timeout_seconds",
    "fetch_max_bytes",
    "wheel_max_bytes",
}
_JOURNAL_LOCK = threading.RLock()


class CapabilityError(HarnessError):
    """A capability request failed closed."""


@dataclass(frozen=True)
class CapabilityConfig:
    """Validated JSON configuration passed by the trusted parent harness."""

    network_domains: tuple[str, ...]
    network_policy: str
    python: Path | None
    python_roots: tuple[Path, ...]
    package_paths: tuple[Path, ...]
    tool_roots: tuple[Path, ...]
    path: tuple[Path, ...]
    office_rendering: Mapping[str, str] | None
    shell_timeout_seconds: float
    fetch_timeout_seconds: float
    fetch_max_bytes: int
    wheel_max_bytes: int
    raw: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> CapabilityConfig:
        if not isinstance(value, Mapping):
            raise CapabilityError("capability config must be a JSON object")
        unknown = set(value) - CONFIG_KEYS
        if unknown:
            raise CapabilityError("unsupported capability config keys: " + ", ".join(sorted(map(str, unknown))))

        def strings(name: str) -> tuple[str, ...]:
            raw = value.get(name, [])
            if raw is None:
                return ()
            if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
                raise CapabilityError(f"{name} must be a list of strings")
            return tuple(raw)

        network_domains = strings("network_domains")
        network_policy = value.get("network_policy", "allowlist")
        if not isinstance(network_policy, str) or network_policy not in {"allowlist", "public_https"}:
            raise CapabilityError("network_policy must be allowlist or public_https")
        path_values = strings("path")
        python_roots = strings("python_roots")
        package_paths = strings("package_paths")
        tool_roots = strings("tool_roots")
        raw_python = value.get("python")
        if raw_python is not None and (not isinstance(raw_python, str) or not raw_python.strip()):
            raise CapabilityError("python must be an absolute interpreter path")

        def positive_number(name: str, default: float, maximum: float) -> float:
            raw = value.get(name, default)
            if (
                isinstance(raw, bool)
                or not isinstance(raw, (int, float))
                or not math.isfinite(raw)
                or raw <= 0
                or raw > maximum
            ):
                raise CapabilityError(f"{name} must be between 0 and {maximum}")
            return float(raw)

        shell_timeout = positive_number("shell_timeout_seconds", MAX_SHELL_TIMEOUT_SECONDS, MAX_SHELL_TIMEOUT_SECONDS)
        fetch_timeout = positive_number("fetch_timeout_seconds", 30.0, 30.0)

        def positive_integer(name: str, default: int, maximum: int) -> int:
            raw = value.get(name, default)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0 or raw > maximum:
                raise CapabilityError(f"{name} must be between 1 and {maximum}")
            return raw

        fetch_max_bytes = positive_integer("fetch_max_bytes", 20 * 1024 * 1024, 20 * 1024 * 1024)
        wheel_max_bytes = positive_integer("wheel_max_bytes", 20 * 1024 * 1024, MAX_WHEEL_BYTES)
        office = value.get("office_rendering")
        office_result: Mapping[str, str] | None
        if office is None:
            office_result = None
        elif (
            isinstance(office, Mapping)
            and set(office) == {"soffice", "pdftoppm"}
            and all(isinstance(item, str) and item.strip() for item in office.values())
        ):
            office_result = {str(key): str(item) for key, item in office.items()}
        else:
            raise CapabilityError("office_rendering requires exactly soffice and pdftoppm paths")

        # Preserve the source mapping immutably so receipts cannot be changed by a
        # caller after service construction.
        snapshot = json.loads(json.dumps(dict(value), ensure_ascii=False))
        return cls(
            network_domains=network_domains,
            network_policy=network_policy,
            python=Path(raw_python).expanduser() if isinstance(raw_python, str) else None,
            python_roots=tuple(Path(item).expanduser() for item in python_roots),
            package_paths=tuple(Path(item).expanduser() for item in package_paths),
            tool_roots=tuple(Path(item).expanduser() for item in tool_roots),
            path=tuple(Path(item).expanduser() for item in path_values),
            office_rendering=office_result,
            shell_timeout_seconds=shell_timeout,
            fetch_timeout_seconds=fetch_timeout,
            fetch_max_bytes=fetch_max_bytes,
            wheel_max_bytes=wheel_max_bytes,
            raw=snapshot,
        )

    @classmethod
    def from_file(cls, path: Path, *, workspace: Path, state: Path) -> CapabilityConfig:
        path = Path(path)
        if not path.is_absolute():
            raise CapabilityError("capability config path must be absolute")
        resolved = path.resolve(strict=True)
        if resolved.is_relative_to(workspace) or resolved.is_relative_to(state):
            raise CapabilityError("capability config must be outside workspace and private state")
        try:
            value = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CapabilityError(f"cannot read capability config {resolved}: {exc}") from exc
        if not isinstance(value, Mapping):
            raise CapabilityError("capability config must be a JSON object")
        return cls.from_mapping(value)


def _ensure_private_directory(path: Path, *, label: str) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise CapabilityError(f"{label} must be an absolute path")
    if path.exists() and path.is_symlink():
        raise CapabilityError(f"{label} must not be a symbolic link")
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)
    except OSError as exc:
        raise CapabilityError(f"cannot create private {label}: {path}: {exc}") from exc
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise CapabilityError(f"{label} is not a directory: {resolved}")
    if resolved.stat().st_mode & 0o077:
        try:
            resolved.chmod(0o700)
        except OSError as exc:
            raise CapabilityError(f"private {label} is accessible by another user: {resolved}") from exc
    return resolved


def _ensure_workspace(path: Path) -> Path:
    if not path.is_absolute():
        raise CapabilityError("workspace must be an absolute path")
    if path.is_symlink():
        raise CapabilityError("workspace must not be a symbolic link")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CapabilityError(f"workspace is unavailable: {path}: {exc}") from exc
    if not resolved.is_dir():
        raise CapabilityError(f"workspace is not a directory: {resolved}")
    return resolved


def _safe_workspace_path(root: Path, raw: str, *, label: str, must_exist: bool = True) -> Path:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise CapabilityError(f"{label} must be a non-empty path")
    value = Path(raw)
    candidate = value if value.is_absolute() else root / value
    candidate = Path(os.path.abspath(candidate))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise CapabilityError(f"{label} escapes the workspace") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise CapabilityError(f"{label} contains a symbolic link: {current}")
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise CapabilityError(f"{label} resolves outside the workspace")
    if must_exist and not resolved.exists():
        raise CapabilityError(f"{label} does not exist: {resolved}")
    return resolved


def _safe_derived_path(state: Path, raw: str) -> Path:
    value = Path(raw)
    if not value.is_absolute():
        value = state / value
    candidate = Path(os.path.abspath(value))
    derived_roots = tuple(state / name for name in ("derived", "inspection"))
    for root in derived_roots:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        return _safe_existing_no_symlink(candidate, label="derived image")
    raise CapabilityError("image path must be inside workspace or service-derived state")


def _safe_existing_no_symlink(path: Path, *, label: str) -> Path:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise CapabilityError(f"{label} contains a symbolic link: {current}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise CapabilityError(f"{label} is not a file: {resolved}")
    return resolved


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
        "utf-8"
    )


def finalize_interrupted_calls(state: Path) -> list[str]:
    """Append terminal failures for calls whose service process was interrupted.

    The controller calls this after terminating registered child processes and
    before exporting private state.  It lets the exported journal distinguish a
    killed or crashed operation from a call that was never attempted.
    """

    journal = Path(state).resolve() / "events.jsonl"
    if not journal.is_file():
        return []
    started: dict[str, dict[str, Any]] = {}
    terminal: set[str] = set()
    try:
        raw_journal = journal.read_bytes()
    except OSError as exc:
        raise CapabilityError(f"cannot read capability journal: {exc}") from exc
    raw_lines = raw_journal.splitlines(keepends=True)
    invalid_line_count = 0
    for raw_bytes in raw_lines:
        if not raw_bytes.endswith(b"\n"):
            invalid_line_count += 1
        raw = raw_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
        try:
            item = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(item, Mapping) or not isinstance(item.get("call_id"), str):
            continue
        call_id = item["call_id"]
        if item.get("event") == "started" and item.get("terminal") is False:
            started.setdefault(call_id, dict(item))
        elif item.get("event") == "finished" or item.get("terminal") is True:
            terminal.add(call_id)
    interrupted = [call_id for call_id in started if call_id not in terminal]
    if not interrupted and not invalid_line_count:
        return []
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _JOURNAL_LOCK, journal.open("ab") as handle:
            # A process kill can leave a partial final JSON object.  Keep that
            # evidence intact and ensure terminal records start on a new line.
            if raw_journal and not raw_journal.endswith(b"\n"):
                handle.write(b"\n")
            for call_id in interrupted:
                item = started[call_id]
                line = {
                    "event": "finished",
                    "terminal": True,
                    "call_id": call_id,
                    "tool": item.get("tool"),
                    "arguments": item.get("arguments", {}),
                    "started_at": item.get("started_at"),
                    "finished_at": now,
                    "elapsed_seconds": None,
                    "status": "interrupted",
                    "failure": {
                        "type": "InterruptedCall",
                        "message": "capability service was interrupted before the tool returned",
                    },
                    "journal_invalid_line_count": invalid_line_count,
                    "output_path": None,
                    "output_sha256": None,
                }
                handle.write(
                    (json.dumps(line, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
                )
            if invalid_line_count and not interrupted:
                warning = {
                    "event": "journal_warning",
                    "terminal": True,
                    "finished_at": now,
                    "journal_invalid_line_count": invalid_line_count,
                    "message": "capability journal contained an invalid or partial line",
                }
                handle.write(
                    (json.dumps(warning, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
                )
            handle.flush()
            os.fsync(handle.fileno())
        journal.chmod(0o600)
    except OSError as exc:
        raise CapabilityError(f"cannot finalize interrupted capability calls: {exc}") from exc
    return interrupted


class CapabilityService:
    """MCP stdio server exposing bounded participant/evaluator capabilities."""

    def __init__(
        self,
        workspace: Path,
        state: Path,
        role: str,
        config: CapabilityConfig | Mapping[str, Any],
        *,
        verify: bool = True,
    ) -> None:
        self.workspace = _ensure_workspace(Path(workspace))
        self.state = _ensure_private_directory(Path(state), label="capability state")
        if (
            self.state == self.workspace
            or self.state.is_relative_to(self.workspace)
            or self.workspace.is_relative_to(self.state)
        ):
            raise CapabilityError("private capability state must be outside workspace")
        if role not in {"creation", "application", "evaluation"}:
            raise CapabilityError(f"unsupported capability role: {role}")
        self.role = role
        self.config = config if isinstance(config, CapabilityConfig) else CapabilityConfig.from_mapping(config)
        self._lock = threading.RLock()
        self._counter = 0
        # Full operation records are kept separately from role/runtime-free
        # research evidence below.  The parent can export state/research to an
        # anonymous evaluator without leaking the rest of the session identity.
        self._journal_path = self.state / "events.jsonl"
        self._receipts = _ensure_private_directory(self.state / "receipts", label="receipts")
        self._outputs = _ensure_private_directory(self.state / "outputs", label="command outputs")
        self._research_state = _ensure_private_directory(self.state / "research", label="research evidence")
        self._network = self._research_state
        self._wheels = _ensure_private_directory(self.state / "wheels", label="wheel evidence")
        self._derived = _ensure_private_directory(self.state / "derived", label="derived evidence")
        _ensure_private_directory(self._derived / "images", label="derived images")
        self.scratch = self._prepare_scratch()
        self._research = self._prepare_research()
        self._packages = self._prepare_packages()
        self._prepare_contexts()
        self._policy: SandboxPolicy | None = None
        self._environment: dict[str, str] | None = None
        self._probe: dict[str, Any] | None = None
        self._probe_error: str | None = None
        self._inspection: Any = None
        # A previous service may have been interrupted while a shell group was
        # running.  Clean only PIDs registered by this private state directory.
        terminate_active_processes(self.state)
        self._load_inspection()
        try:
            self._policy = make_policy(
                self.workspace,
                self.scratch,
                self.role,
                self.config.raw,
                extra_protected=(self._research, self.workspace / "inspection", self._packages),
            )
            self._environment = clean_environment(self._policy, package_paths=(self._packages,))
            if verify:
                self._probe = verify_policy(self._policy, self.state / "probes")
        except (HarnessError, OSError) as exc:
            self._probe_error = str(exc)
            self._policy = self._policy if self._policy is not None else None
            if verify and isinstance(exc, (SandboxError, CapabilityError)):
                # Keep network/image/document tools usable, but never expose shell.
                self._probe = {"available": False, "verified": False, "error": str(exc)}

        self.network = NetworkClient(
            self.config.network_domains,
            network_policy=self.config.network_policy,
            max_bytes=self.config.fetch_max_bytes,
            timeout_seconds=self.config.fetch_timeout_seconds,
        )

    @classmethod
    def from_config_file(
        cls, workspace: Path, state: Path, role: str, config_path: Path, *, verify: bool = True
    ) -> CapabilityService:
        workspace_resolved = _ensure_workspace(Path(workspace))
        state_resolved = Path(state).expanduser()
        if not state_resolved.is_absolute():
            raise CapabilityError("private capability state must be an absolute path")
        if state_resolved.exists() and state_resolved.is_symlink():
            raise CapabilityError("private capability state must not be a symbolic link")
        state_resolved = state_resolved.resolve(strict=False)
        config = CapabilityConfig.from_file(
            Path(config_path).expanduser(), workspace=workspace_resolved, state=state_resolved
        )
        return cls(workspace_resolved, state_resolved, role, config, verify=verify)

    def _prepare_scratch(self) -> Path:
        if self.role == "evaluation":
            path = self.workspace / "scratch"
        else:
            path = self.workspace / ".capability-scratch"
        if path.exists() and path.is_symlink():
            raise CapabilityError(f"capability scratch must not be a symbolic link: {path}")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)
        return path.resolve(strict=True)

    def _prepare_research(self) -> Path:
        root = (self.scratch / "research") if self.role == "evaluation" else (self.workspace / "research")
        if root.exists() and root.is_symlink():
            raise CapabilityError(f"research directory must not be a symbolic link: {root}")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root.resolve(strict=True)

    def _prepare_packages(self) -> Path:
        root = (self.scratch / ".packages") if self.role == "evaluation" else (self.workspace / ".packages")
        if root.exists() and root.is_symlink():
            raise CapabilityError(f"package directory must not be a symbolic link: {root}")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root.resolve(strict=True)

    def _prepare_contexts(self) -> None:
        """Materialize empty protected context directories before shell exposure."""

        for name in CONTEXT_FOLDERS:
            path = self.workspace / name
            if path.exists() and path.is_symlink():
                raise CapabilityError(f"context directory must not be a symbolic link: {path}")
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Supplied files retain their bytes and mode; the directory itself is
            # constrained by the Seatbelt profile and this private mode.
            try:
                path.chmod(0o700)
            except OSError as exc:
                raise CapabilityError(f"cannot secure context directory: {path}: {exc}") from exc

    def _load_inspection(self) -> None:
        try:
            from .capability_inspection import InspectionTools
        except ImportError:
            return
        try:
            _ensure_private_directory(self.state / "inspection", label="inspection evidence")
            self._inspection = InspectionTools(self.workspace, self.state, self.config.raw)
        except Exception as exc:
            if self.config.office_rendering is not None:
                self._probe_error = f"document inspection unavailable: {exc}"
            self._inspection = None

    @property
    def shell_available(self) -> bool:
        return (
            self._policy is not None
            and self._environment is not None
            and bool(self._probe and self._probe.get("verified") is True)
        )

    @property
    def probe(self) -> dict[str, Any]:
        return dict(self._probe or {"available": False, "verified": False, "error": self._probe_error})

    def probe_result(self) -> dict[str, Any]:
        return {
            "verified": self.shell_available,
            "role": self.role,
            "workspace": str(self.workspace),
            "state": str(self.state),
            "shell": self.probe,
            "tools": [tool["name"] for tool in self.tool_definitions()],
            "network_domains": list(self.config.network_domains),
            "network_policy": self.config.network_policy,
            "office_rendering": dict(self.config.office_rendering) if self.config.office_rendering else None,
        }

    def _next_call_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"{self._counter:06d}-{uuid.uuid4().hex}"

    def _write_private(self, path: Path, data: bytes) -> None:
        if path.is_symlink():
            raise CapabilityError(f"private evidence path must not be a symbolic link: {path}")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        with path.open("wb") as handle:
            handle.write(data)
            handle.flush()
        path.chmod(0o600)

    def _copy_visible_research(self, call_id: str, suffix: str, data: bytes) -> Path:
        safe_suffix = "".join(char if char.isalnum() else "_" for char in suffix.lower())[:32] or "data"
        target = self._research / f"{call_id}.{safe_suffix}"
        # UUID call IDs make collisions improbable; exclusive creation avoids an
        # accidental overwrite if a caller reuses state.
        try:
            with target.open("xb") as handle:
                handle.write(data)
            target.chmod(0o400)
        except FileExistsError as exc:
            raise CapabilityError(f"research evidence path already exists: {target}") from exc
        return target

    def _save_receipt(self, call_id: str, receipt: Mapping[str, Any]) -> tuple[Path, str]:
        data = _json_bytes(receipt) + b"\n"
        path = self._receipts / f"{call_id}.json"
        self._write_private(path, data)
        return path, _sha256_bytes(data)

    def _journal(
        self,
        call_id: str,
        name: str,
        arguments: Mapping[str, Any],
        started: float,
        *,
        result: Any = None,
        error: BaseException | None = None,
        started_at: str | None = None,
    ) -> None:
        elapsed = time.monotonic() - started
        receipt: dict[str, Any] = {
            "call_id": call_id,
            "tool": name,
            "arguments": dict(arguments),
            "elapsed_seconds": elapsed,
            "failure": None,
        }
        if error is None:
            receipt["result"] = result
        else:
            receipt["failure"] = {"type": type(error).__name__, "message": str(error)}
        try:
            with self._lock:
                output_path, output_sha256 = self._save_receipt(call_id, receipt)
                line = {
                    "event": "finished",
                    "terminal": True,
                    "call_id": call_id,
                    "tool": name,
                    "arguments": dict(arguments),
                    "started_at": started_at,
                    "elapsed_seconds": elapsed,
                    "status": "completed" if error is None else "failed",
                    "failure": receipt["failure"],
                    "output_path": str(output_path),
                    "output_sha256": output_sha256,
                }
                encoded = json.dumps(line, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
                with self._journal_path.open("a", encoding="utf-8") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                self._journal_path.chmod(0o600)
        except OSError as exc:
            # Provenance failure is itself a hard failure.  Returning a capability
            # result that could not be journaled would make a run unverifiable.
            raise CapabilityError(f"cannot write capability journal: {exc}") from exc

    def _journal_started(self, call_id: str, name: str, arguments: Mapping[str, Any], started_at: str) -> None:
        """Persist the call intent before dispatch so an interrupted call is visible."""

        line = {
            "event": "started",
            "terminal": False,
            "call_id": call_id,
            "tool": name,
            "arguments": dict(arguments),
            "started_at": started_at,
        }
        try:
            with self._lock:
                with self._journal_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(line, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                self._journal_path.chmod(0o600)
        except OSError as exc:
            raise CapabilityError(f"cannot write capability journal: {exc}") from exc

    def _arguments(self, value: Any) -> Mapping[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise CapabilityError("tool arguments must be a JSON object")
        return value

    @staticmethod
    def _only(arguments: Mapping[str, Any], required: Iterable[str], optional: Iterable[str] = ()) -> None:
        keys = set(arguments)
        required_set = set(required)
        optional_set = set(optional)
        missing = required_set - keys
        unknown = keys - required_set - optional_set
        if missing:
            raise CapabilityError("missing tool arguments: " + ", ".join(sorted(missing)))
        if unknown:
            raise CapabilityError("unsupported tool arguments: " + ", ".join(sorted(map(str, unknown))))

    def _shell(self, arguments: Mapping[str, Any], call_id: str) -> dict[str, Any]:
        self._only(arguments, ("command",), ("timeout_seconds",))
        command = arguments["command"]
        if not isinstance(command, str) or not command.strip():
            raise CapabilityError("shell command must be a non-empty string")
        timeout_raw = arguments.get("timeout_seconds", self.config.shell_timeout_seconds)
        if isinstance(timeout_raw, bool) or not isinstance(timeout_raw, (int, float)):
            raise CapabilityError("timeout_seconds must be a positive number")
        timeout = float(timeout_raw)
        if timeout <= 0 or timeout > self.config.shell_timeout_seconds or timeout > MAX_SHELL_TIMEOUT_SECONDS:
            raise CapabilityError(f"timeout_seconds must be between 0 and {self.config.shell_timeout_seconds}")
        if not self.shell_available or self._policy is None or self._environment is None:
            raise CapabilityError("shell capability is unavailable until native isolation verification succeeds")
        result = run_sandboxed(
            command,
            policy=self._policy,
            environment=self._environment,
            output_dir=self._outputs,
            timeout_seconds=timeout,
            active_state=self.state,
        )
        value = result.as_dict()
        # Return the service-owned output locations and bounded previews; complete
        # streams remain available only in private state.
        value["call_id"] = call_id
        value["captured_stdout_path"] = ".harness_evidence/" + result.stdout_path.relative_to(self.state).as_posix()
        value["captured_stderr_path"] = ".harness_evidence/" + result.stderr_path.relative_to(self.state).as_posix()
        return value

    def _network_blob(self, body: bytes) -> tuple[Path, str]:
        body_hash = _sha256_bytes(body)
        blob = self._network / f"{body_hash}.bin"
        if blob.is_symlink():
            raise CapabilityError("research evidence path must not be a symbolic link")
        if not blob.exists():
            self._write_private(blob, body)
        return blob, body_hash

    def _exchange_evidence(self, exchanges: Sequence[HTTPExchange]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for exchange in exchanges:
            entry: dict[str, Any] = {
                "url": exchange.url,
                "retrieved_at": exchange.retrieved_at,
                "request_elapsed_seconds": exchange.elapsed_seconds,
                "status": exchange.status,
                "content_type": exchange.content_type,
                "body_complete": exchange.body_complete,
                "error": exchange.error,
                "location": exchange.location,
            }
            if exchange.body is not None:
                blob, body_hash = self._network_blob(exchange.body)
                entry.update({"bytes": len(exchange.body), "sha256": body_hash, "body_file": blob.name})
            evidence.append(entry)
        return evidence

    def _search_attempt_evidence(self, attempts: Sequence[SearchAttempt]) -> list[dict[str, Any]]:
        return [
            {
                "backend": attempt.backend,
                "requested_url": attempt.requested_url,
                "final_url": attempt.final_url,
                "redirects": list(attempt.redirects),
                "retrieved_at": attempt.retrieved_at,
                "request_elapsed_seconds": attempt.elapsed_seconds,
                "status": attempt.status,
                "error": attempt.error,
                "exchanges": self._exchange_evidence(attempt.exchanges),
            }
            for attempt in attempts
        ]

    def _fetch(self, arguments: Mapping[str, Any], call_id: str) -> dict[str, Any]:
        self._only(arguments, ("url",))
        request_started = time.monotonic()
        retrieved_at = datetime.now(timezone.utc).isoformat()
        try:
            response = self.network.fetch(arguments["url"])
        except NetworkError as exc:
            self._write_research_receipt(
                call_id,
                {
                    "type": "harness.research",
                    "requested_url": arguments["url"],
                    "final_url": exc.final_url,
                    "redirects": list(exc.redirects),
                    "retrieved_at": retrieved_at,
                    "request_elapsed_seconds": time.monotonic() - request_started,
                    "error": str(exc),
                    "exchanges": self._exchange_evidence(exc.exchanges),
                },
            )
            raise
        request_elapsed = time.monotonic() - request_started
        blob, body_hash = self._network_blob(response.body)
        suffix = ".bin"
        if (
            response.content_type.startswith("text/")
            or "json" in response.content_type
            or "xml" in response.content_type
        ):
            suffix = ".txt"
        visible = self._copy_visible_research(call_id, suffix, response.body)
        summary = fetch_summary(response, body_sha256=body_hash, visible_path=str(visible))
        summary["state_path"] = str(blob)
        summary["exchanges"] = self._exchange_evidence(response.exchanges)
        self._write_research_receipt(
            call_id,
            {
                "type": "harness.research",
                "retrieved_at": retrieved_at,
                "request_elapsed_seconds": request_elapsed,
                **fetch_summary(response, body_sha256=body_hash),
                "exchanges": summary["exchanges"],
            },
        )
        if response.status < 200 or response.status >= 300:
            summary["http_error"] = True
        return summary

    def _search(self, arguments: Mapping[str, Any], call_id: str) -> dict[str, Any]:
        self._only(arguments, ("query",))
        request_started = time.monotonic()
        retrieved_at = datetime.now(timezone.utc).isoformat()
        try:
            result = self.network.search(arguments["query"])
        except NetworkError as exc:
            self._write_research_receipt(
                call_id,
                {
                    "type": "harness.research",
                    "query": arguments["query"],
                    "retrieved_at": retrieved_at,
                    "request_elapsed_seconds": time.monotonic() - request_started,
                    "error": str(exc),
                    "attempts": self._search_attempt_evidence(exc.attempts),
                },
            )
            raise
        request_elapsed = time.monotonic() - request_started
        blob, body_hash = self._network_blob(result.response.body)
        attempts = self._search_attempt_evidence(result.attempts)
        visible = self._copy_visible_research(call_id, ".html", result.response.body)
        summary = search_summary(result, body_sha256=body_hash, visible_path=str(visible))
        summary["state_path"] = str(blob)
        summary["attempts"] = attempts
        self._write_research_receipt(
            call_id,
            {
                "type": "harness.research",
                "query": result.query,
                "backend": result.backend,
                "retrieved_at": retrieved_at,
                "request_elapsed_seconds": request_elapsed,
                **fetch_summary(result.response, body_sha256=body_hash),
                "results": list(result.results),
                "attempts": attempts,
            },
        )
        return summary

    def _write_research_receipt(self, call_id: str, value: Mapping[str, Any]) -> Path:
        """Write role/runtime-free provenance beside raw research bytes."""

        path = self._research_state / f"{call_id}.json"
        self._write_private(path, _json_bytes(value) + b"\n")
        return path

    def _view_image(self, arguments: Mapping[str, Any], call_id: str) -> list[dict[str, Any]]:
        self._only(arguments, ("path",), ("region",))
        raw_path = arguments["path"]
        if not isinstance(raw_path, str):
            raise CapabilityError("image path must be a string")
        try:
            path = _safe_workspace_path(self.workspace, raw_path, label="image path")
        except CapabilityError:
            path = _safe_derived_path(self.state, raw_path)
        size = path.stat().st_size
        if size <= 0 or size > MAX_VIEW_IMAGE_BYTES:
            raise CapabilityError("image exceeds the bounded view size")
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise CapabilityError("Pillow is unavailable for image viewing") from exc
        try:
            with Image.open(path) as source:
                width, height = source.size
                if (
                    width <= 0
                    or height <= 0
                    or width > MAX_VIEW_IMAGE_DIMENSION
                    or height > MAX_VIEW_IMAGE_DIMENSION
                    or width * height > MAX_VIEW_IMAGE_PIXELS
                ):
                    raise CapabilityError("image dimensions exceed the bounded view size")
                source.load()
                region = arguments.get("region")
                crop: list[int] | None = None
                image = source.copy()
                if region is not None:
                    if (
                        not isinstance(region, list)
                        or len(region) != 4
                        or any(isinstance(item, bool) or not isinstance(item, int) for item in region)
                    ):
                        raise CapabilityError("region must be [left, top, right, bottom] integer coordinates")
                    left, top, right, bottom = region
                    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                        raise CapabilityError("region must lie within image bounds")
                    crop = [left, top, right, bottom]
                    image = source.crop((left, top, right, bottom))
                output = io.BytesIO()
                image.save(output, format="PNG", optimize=False)
                encoded = output.getvalue()
                image_width, image_height = image.size
        except UnidentifiedImageError as exc:
            raise CapabilityError(f"file is not a decodable image: {path}") from exc
        except (OSError, Image.DecompressionBombError) as exc:
            raise CapabilityError(f"image could not be decoded: {path}: {exc}") from exc
        source_hash = _sha256_file(path)
        rendered_hash = _sha256_bytes(encoded)
        derived_path = self._derived / "images" / f"{call_id}.png"
        self._write_private(derived_path, encoded)
        metadata = {
            "call_id": call_id,
            "captured_path": ".harness_evidence/" + derived_path.relative_to(self.state).as_posix(),
            "path": str(path),
            "source_sha256": source_hash,
            "source_bytes": size,
            "width": width,
            "height": height,
            "crop": crop,
            "rendered_sha256": rendered_hash,
            "rendered_bytes": len(encoded),
            "rendered_width": image_width,
            "rendered_height": image_height,
            "state_path": str(derived_path),
        }
        return [
            {"type": "text", "text": json_summary(metadata)},
            {"type": "image", "data": base64.b64encode(encoded).decode("ascii"), "mimeType": "image/png"},
        ]

    def _install_wheel(self, arguments: Mapping[str, Any], call_id: str) -> dict[str, Any]:
        started = time.monotonic()
        self._only(arguments, ("url", "sha256"))
        url = arguments["url"]
        expected = arguments["sha256"]
        if not isinstance(url, str) or not isinstance(expected, str):
            raise CapabilityError("install_wheel requires string url and sha256")
        if len(expected) != 64 or any(char not in "0123456789abcdefABCDEF" for char in expected):
            raise CapabilityError("sha256 must be a 64-character hexadecimal digest")
        from urllib.parse import urlsplit

        parsed = urlsplit(url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise CapabilityError("wheel URL has an invalid port") from exc
        if parsed.scheme.lower() != "https" or parsed.hostname != "files.pythonhosted.org" or port not in (None, 443):
            raise CapabilityError("wheels may only be downloaded from files.pythonhosted.org over HTTPS")
        if not parsed.path.lower().endswith(".whl") or parsed.fragment:
            raise CapabilityError("install_wheel URL must name a .whl file and have no fragment")
        response = self.network.fetch(url)
        wheel_hash = _sha256_bytes(response.body)
        state_wheel = self._wheels / f"{wheel_hash}.whl"
        if state_wheel.is_symlink():
            raise CapabilityError("wheel evidence path must not be a symbolic link")
        if not state_wheel.exists():
            self._write_private(state_wheel, response.body)
        self._write_private(
            self._wheels / f"{call_id}.json",
            _json_bytes(
                {
                    **fetch_summary(response, body_sha256=wheel_hash),
                    "expected_sha256": expected.lower(),
                    "wheel_file": state_wheel.name,
                }
            )
            + b"\n",
        )
        if response.status < 200 or response.status >= 300:
            raise CapabilityError(f"wheel download returned HTTP {response.status}")
        if wheel_hash.lower() != expected.lower():
            raise CapabilityError("wheel SHA256 does not match the expected digest")
        if len(response.body) > self.config.wheel_max_bytes:
            raise CapabilityError("wheel exceeds the configured size limit")
        # Hold the service lock through staging/publication. Validation and CRC
        # reads cannot affect the import tree; publication tracks only new paths
        # so any later I/O failure removes them without touching earlier installs.
        with self._lock:
            try:
                with zipfile.ZipFile(io.BytesIO(response.body)) as package:
                    safe_entries = self._validate_wheel_entries(package)
                    with tempfile.TemporaryDirectory(prefix=".install-", dir=self._wheels) as staging_name:
                        staging = Path(staging_name)
                        extracted: list[str] = []
                        directories: set[Path] = set()
                        for entry in safe_entries:
                            relative = Path(entry.filename)
                            directories.update(parent for parent in relative.parents if parent != Path("."))
                            if entry.is_dir():
                                directories.add(relative)
                            destination = staging / relative
                            if entry.is_dir():
                                destination.mkdir(parents=True, exist_ok=True, mode=0o700)
                                # Reading explicit directory members also checks
                                # their CRC; hidden data in these is not ignored.
                                if package.read(entry):
                                    raise CapabilityError("wheel directory entries must be empty")
                                continue
                            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                            with package.open(entry) as source, destination.open("xb") as sink:
                                shutil.copyfileobj(source, sink, length=1024 * 1024)
                            destination.chmod(0o600)
                            extracted.append(entry.filename)
                        self._publish_wheel(staging, extracted, directories)
            except (zipfile.BadZipFile, EOFError, NotImplementedError, RuntimeError) as exc:
                raise CapabilityError(f"wheel is not a valid supported ZIP archive: {exc}") from exc
        return {
            "url": response.final_url,
            "requested_url": response.requested_url,
            "sha256": wheel_hash,
            "bytes": len(response.body),
            "state_path": str(state_wheel),
            "install_path": str(self._packages),
            "files": extracted,
            "file_count": len(extracted),
            "install_elapsed_seconds": time.monotonic() - started,
            "call_id": call_id,
        }

    def _validate_wheel_entries(self, package: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        entries = package.infolist()
        if not entries or len(entries) > MAX_WHEEL_ENTRIES:
            raise CapabilityError("wheel has too many or no archive entries")
        if self._packages.is_symlink() or not self._packages.is_dir():
            raise CapabilityError("package destination must be a directory without symbolic links")
        expanded = 0
        members: dict[str, bool] = {}
        for entry in entries:
            name = entry.orig_filename
            if not name or "\x00" in name or "\\" in name or name != entry.filename:
                raise CapabilityError("wheel contains an invalid archive path")
            path_name = name[:-1] if entry.is_dir() else name
            if not path_name or any(part in {"", ".", ".."} for part in path_name.split("/")):
                raise CapabilityError("wheel contains a traversal path")
            relative = Path(path_name)
            if relative.is_absolute():
                raise CapabilityError("wheel contains a traversal path")
            mode = (entry.external_attr >> 16) & 0o170000
            if mode not in {0, 0o040000 if entry.is_dir() else 0o100000}:
                raise CapabilityError("wheel links and special files are not allowed")
            if name.lower().endswith(".pth"):
                raise CapabilityError("wheel .pth files are not allowed")
            if entry.flag_bits & 1:
                raise CapabilityError("encrypted wheel members are not allowed")
            key = unicodedata.normalize("NFD", path_name).casefold()
            if key in members:
                raise CapabilityError("wheel contains duplicate archive destinations")
            members[key] = entry.is_dir()
            expanded += entry.file_size
            if entry.file_size > MAX_WHEEL_FILE_BYTES or expanded > MAX_WHEEL_EXPANDED_BYTES:
                raise CapabilityError("wheel expanded size exceeds the bounded limit")
            current = self._packages
            for part in relative.parts:
                current /= part
                if current.is_symlink():
                    raise CapabilityError(f"wheel destination contains a symbolic link: {current}")
                if current.exists() and (
                    not current.is_dir() or current == self._packages / relative and not entry.is_dir()
                ):
                    raise CapabilityError(f"wheel destination already exists: {current}")
        for key in members:
            for parent in Path(key).parents:
                if members.get(parent.as_posix()) is False:
                    raise CapabilityError("wheel file conflicts with an archive directory")
        return entries

    def _publish_wheel(self, staging: Path, files: Sequence[str], directories: set[Path]) -> None:
        created_files: list[Path] = []
        created_directories: list[Path] = []
        try:
            for relative in sorted(directories, key=lambda path: (len(path.parts), path.as_posix())):
                destination = self._packages / relative
                try:
                    destination.mkdir(mode=0o700)
                except FileExistsError:
                    if destination.is_symlink() or not destination.is_dir():
                        raise CapabilityError(f"wheel destination already exists: {destination}")
                else:
                    created_directories.append(destination)
            for name in files:
                destination = self._packages / name
                with destination.open("xb") as sink:
                    created_files.append(destination)
                    with (staging / name).open("rb") as source:
                        shutil.copyfileobj(source, sink, length=1024 * 1024)
                destination.chmod(0o600)
        except BaseException:
            for path in reversed(created_files):
                path.unlink()
            for path in reversed(created_directories):
                path.rmdir()
            raise

    def _inspection_call(self, name: str, arguments: Mapping[str, Any]) -> Any:
        if self._inspection is None:
            raise CapabilityError("document inspection capability is unavailable")
        if name == "inspect_document":
            self._only(arguments, ("path",))
            return self._inspection.inspect_document(arguments["path"])
        self._only(arguments, ("path", "pages"), ("region",))
        pages = arguments["pages"]
        if not isinstance(pages, list) or any(isinstance(item, bool) or not isinstance(item, int) for item in pages):
            raise CapabilityError("pages must be a list of integer page numbers")
        region = arguments.get("region")
        if region is not None and (
            not isinstance(region, list)
            or len(region) != 4
            or any(isinstance(item, bool) or not isinstance(item, int) for item in region)
        ):
            raise CapabilityError("region must be [left, top, right, bottom] integer coordinates")
        return self._inspection.render_pages(arguments["path"], pages, region)

    def _dispatch(self, name: str, arguments: Mapping[str, Any], call_id: str) -> Any:
        if name == "shell":
            return self._shell(arguments, call_id)
        if name == "fetch":
            return self._fetch(arguments, call_id)
        if name == "search":
            return self._search(arguments, call_id)
        if name == "view_image":
            return self._view_image(arguments, call_id)
        if name == "install_wheel":
            return self._install_wheel(arguments, call_id)
        if name in {"inspect_document", "render_pages"}:
            return self._inspection_call(name, arguments)
        raise CapabilityError(f"unknown capability tool: {name}")

    def invoke(self, name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        """Invoke one tool, journaling both successful and failed attempts."""

        call_id = self._next_call_id()
        args = self._arguments(arguments)
        started = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        self._journal_started(call_id, name, args, started_at)
        try:
            result = self._dispatch(name, args, call_id)
            if isinstance(result, dict):
                result["call_id"] = call_id
            elif isinstance(result, list) and name == "render_pages":
                result.append({"type": "text", "text": json_summary({"call_id": call_id})})
        except BaseException as exc:
            try:
                self._journal(call_id, name, args, started, error=exc, started_at=started_at)
            except BaseException:
                raise
            raise
        self._journal(call_id, name, args, started, result=result, started_at=started_at)
        return result

    def tool_definitions(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        if self.shell_available:
            tools.append(
                {
                    "name": "shell",
                    "description": (
                        "Run a bounded foreground shell operation in the isolated task workspace. "
                        "Shell builtins may prepare files; use explicit `exec` for one external program. "
                        "Process fork, background jobs, pipelines, and implicit subprocesses are denied."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"},
                            "timeout_seconds": {
                                "type": "number",
                                "minimum": 0.01,
                                "maximum": self.config.shell_timeout_seconds,
                            },
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                }
            )
        tools.extend(
            [
                {
                    "name": "fetch",
                    "description": "Fetch an anonymous public HTTPS URL permitted by the configured network policy, recording provenance.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "search",
                    "description": "Search the configured public unauthenticated web backend.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "view_image",
                    "description": "Decode and view an image from the workspace or derived service state.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "region": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "install_wheel",
                    "description": "Download and extract one SHA256-pinned wheel into the task package directory.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "sha256": {"type": "string", "pattern": "^[0-9a-fA-F]{64}$"},
                        },
                        "required": ["url", "sha256"],
                        "additionalProperties": False,
                    },
                },
            ]
        )
        if self._inspection is not None:
            tools.extend(
                [
                    {
                        "name": "inspect_document",
                        "description": "Inspect an Office document's structure and text without editing it.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                            "additionalProperties": False,
                        },
                    },
                    {
                        "name": "render_pages",
                        "description": "Render selected Office document pages or regions into native image content.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "pages": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                                "region": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 4,
                                    "maxItems": 4,
                                },
                            },
                            "required": ["path", "pages"],
                            "additionalProperties": False,
                        },
                    },
                ]
            )
        return tools

    @staticmethod
    def _text_content(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list) and all(
            isinstance(item, Mapping) and isinstance(item.get("type"), str) for item in value
        ):
            result: list[dict[str, Any]] = []
            for item in value:
                block = dict(item)
                text = block.get("text")
                if isinstance(text, str) and len(text.encode("utf-8")) > MAX_TOOL_TEXT_BYTES:
                    block["text"] = (
                        text.encode("utf-8")[:MAX_TOOL_TEXT_BYTES].decode("utf-8", errors="ignore")
                        + "\n[response truncated]"
                    )
                result.append(block)
            return result
        if isinstance(value, Mapping):
            text = json.dumps(dict(value), sort_keys=True, ensure_ascii=False, allow_nan=False)
        else:
            text = str(value)
        if len(text.encode("utf-8")) > MAX_TOOL_TEXT_BYTES:
            text = (
                text.encode("utf-8")[:MAX_TOOL_TEXT_BYTES].decode("utf-8", errors="ignore") + "\n[response truncated]"
            )
        return [{"type": "text", "text": text}]

    def handle_request(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC request or notification."""

        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": "invalid request"}}
        if request.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32600, "message": "invalid JSON-RPC version"},
            }
        is_notification = "id" not in request
        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "eval-harness-capability", "version": "0.1.0"},
                }
            elif method == "notifications/initialized":
                result = {}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tool_definitions()}
            elif method == "tools/call":
                params = request.get("params")
                if not isinstance(params, Mapping) or not isinstance(params.get("name"), str):
                    raise CapabilityError("tools/call requires params.name")
                arguments = params.get("arguments", {})
                result = {"content": self._text_content(self.invoke(params["name"], self._arguments(arguments)))}
            else:
                if is_notification:
                    return None
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}}
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except BaseException as exc:
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"isError": True, "content": [{"type": "text", "text": str(exc) or type(exc).__name__}]},
            }

    def run_stdio(self, stdin: Any = None, stdout: Any = None) -> int:
        """Serve newline-delimited JSON-RPC until stdin closes."""

        input_stream = stdin or sys.stdin
        output_stream = stdout or sys.stdout
        for raw_line in input_stream:
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8", errors="replace")
            line = str(raw_line).strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                if not isinstance(request, Mapping):
                    raise ValueError("request must be an object")
                response = self.handle_request(request)
            except (json.JSONDecodeError, ValueError) as exc:
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            if response is not None:
                output_stream.write(
                    json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
                )
                output_stream.flush()
        return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GDPval capability MCP service")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--role", required=True, choices=("creation", "application", "evaluation"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--probe", action="store_true", help="run native probes and print JSON without serving stdin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        service = CapabilityService.from_config_file(args.workspace, args.state, args.role, args.config, verify=True)
        if args.probe:
            print(json.dumps(service.probe_result(), ensure_ascii=False, sort_keys=True))
            return 0 if service.shell_available else 2
        return service.run_stdio()
    except (HarnessError, OSError, ValueError) as exc:
        if args.probe:
            print(json.dumps({"verified": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        else:
            print(f"capability service unavailable: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
