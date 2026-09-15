# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Native shell isolation for the participant/evaluator capability service.

The service is trusted harness code.  Candidate commands are run as children of a
fresh process group under macOS Seatbelt (``sandbox-exec``); the policy is generated
from explicit roots and never incorporates participant supplied settings.  Linux and
other platforms fail closed because a portable subprocess wrapper cannot establish
the same read and write boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .errors import HarnessError


class SandboxError(HarnessError):
    """The native shell boundary is unavailable or a command was rejected."""


SYSTEM_READ_ROOTS = (
    Path("/bin"),
    Path("/usr/bin"),
    Path("/usr/lib"),
    Path("/usr/share"),
    Path("/System/Library"),
    Path("/Library/Fonts"),
)
SYSTEM_READ_FILES = tuple(
    path.resolve() for path in (Path("/etc/mime.types"), Path("/etc/apache2/mime.types")) if path.is_file()
)
CONTEXT_FOLDERS = ("reference_files", "skill", "creation_inputs", "creator_skills", "evidence")
MAX_SHELL_TIMEOUT_SECONDS = 120.0
MAX_SHELL_COMMAND_CHARS = 1_000_000
MAX_SHELL_CAPTURE_BYTES = 64 * 1024 * 1024
MAX_TOOL_TEXT_BYTES = 64 * 1024

_ACTIVE_LOCK = threading.RLock()


@dataclass(frozen=True)
class SandboxPolicy:
    """Resolved roots used to create one Seatbelt profile."""

    workspace: Path
    scratch: Path
    interpreter: Path | None
    runtime_roots: tuple[Path, ...]
    package_paths: tuple[Path, ...]
    tool_roots: tuple[Path, ...]
    path_entries: tuple[Path, ...]
    writable_roots: tuple[Path, ...]
    protected_roots: tuple[Path, ...]


@dataclass(frozen=True)
class SandboxedCommandResult:
    """Captured command result; full streams are retained in ``stdout_path``/``stderr_path``."""

    command: tuple[str, ...]
    returncode: int | None
    status: str
    elapsed_seconds: float
    stdout: str
    stderr: str
    stdout_path: Path
    stderr_path: Path
    stdout_sha256: str
    stderr_sha256: str
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool
    profile_path: Path
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "status": self.status,
            "elapsed_seconds": self.elapsed_seconds,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
            "stdout_sha256": self.stdout_sha256,
            "stderr_sha256": self.stderr_sha256,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "profile_path": str(self.profile_path),
            "error": self.error,
        }


def _literal(path: Path) -> str:
    return json.dumps(str(path), ensure_ascii=True)


def _resolve_existing(path: Path, *, label: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise SandboxError(f"{label} is unavailable: {path}: {exc}") from exc
    if path.is_symlink() and not path.exists():
        raise SandboxError(f"{label} is a dangling symbolic link: {path}")
    return resolved


def _validate_no_symlink(path: Path, *, label: str) -> Path:
    """Resolve an existing path while rejecting every symlink in its ancestry."""

    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            if current.is_symlink():
                # macOS exposes temporary directories through the stable /var
                # alias.  The alias is a fixed system link to /private/var and
                # does not permit a caller to redirect a task path.
                if current == Path("/var"):
                    continue
                raise SandboxError(f"{label} contains a symbolic link: {current}")
        except OSError as exc:
            raise SandboxError(f"cannot inspect {label}: {current}: {exc}") from exc
    return absolute.resolve(strict=False)


def _reject_broad_root(root: Path, *, workspace: Path, label: str) -> None:
    resolved = root.resolve(strict=False)
    broad = {
        Path("/"),
        Path.home().resolve(),
        Path("/Users"),
        Path("/private"),
        Path("/tmp"),
        Path("/var"),
        Path("/usr"),
        Path("/usr/local"),
        Path("/opt"),
        Path("/Applications"),
    }
    if resolved in broad:
        raise SandboxError(f"{label} is too broad: {resolved}")
    # A runtime root that contains the task workspace would silently grant access
    # to the surrounding repository or task collection.
    if workspace == resolved or workspace.is_relative_to(resolved) or resolved.is_relative_to(workspace):
        raise SandboxError(f"{label} overlaps the participant workspace: {resolved}")


def _normal_paths(value: Any, *, label: str, workspace: Path, must_be_dir: bool = True) -> tuple[Path, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SandboxError(f"{label} must be a list of absolute paths")
    result: list[Path] = []
    for raw in value:
        if not isinstance(raw, str) or not raw.strip():
            raise SandboxError(f"{label} entries must be non-empty absolute paths")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise SandboxError(f"{label} entries must be absolute: {raw!r}")
        resolved = _validate_no_symlink(path, label=label)
        if must_be_dir and not resolved.is_dir():
            raise SandboxError(f"{label} entry is not a directory: {resolved}")
        if not must_be_dir and not resolved.exists():
            raise SandboxError(f"{label} entry is unavailable: {resolved}")
        _reject_broad_root(resolved, workspace=workspace, label=label)
        if resolved not in result:
            result.append(resolved)
    return tuple(result)


def _normal_path_entries(value: Any, *, workspace: Path) -> tuple[Path, ...]:
    entries = _normal_paths(value, label="path", workspace=workspace)
    return entries or (Path("/usr/bin"), Path("/bin"))


def _normal_python(value: Any, *, workspace: Path) -> tuple[Path | None, tuple[Path, ...]]:
    if value is None:
        return None, ()
    if not isinstance(value, str) or not value.strip():
        raise SandboxError("python must be an absolute interpreter path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise SandboxError("python must be an absolute interpreter path")
    resolved = _validate_no_symlink(path, label="python")
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise SandboxError(f"python interpreter is not executable: {resolved}")
    _reject_broad_root(resolved.parent, workspace=workspace, label="python")
    # The parent runtime configuration normally supplies its root explicitly.  A
    # parent bin directory is still useful for minimal probes and tests.
    return resolved, (resolved.parent,)


def make_policy(
    workspace: Path,
    scratch: Path,
    role: str,
    config: Mapping[str, Any],
    *,
    extra_protected: Sequence[Path] = (),
) -> SandboxPolicy:
    """Resolve explicit capability roots into a policy object.

    ``role=evaluation`` grants writes only to ``workspace/scratch``.  Creation and
    application may write the task workspace, while context and service-owned
    directories remain denied below.
    """

    workspace = _validate_no_symlink(workspace, label="workspace")
    scratch = _validate_no_symlink(scratch, label="scratch")
    if not workspace.is_dir() or not scratch.is_dir() or not scratch.is_relative_to(workspace):
        raise SandboxError("scratch must be an existing directory within workspace")
    if role not in {"creation", "application", "evaluation"}:
        raise SandboxError(f"unsupported capability role: {role}")

    python, inferred_python_roots = _normal_python(config.get("python"), workspace=workspace)
    configured_runtime_roots = _normal_paths(config.get("python_roots"), label="python_roots", workspace=workspace)
    runtime_roots = tuple(dict.fromkeys((*configured_runtime_roots, *inferred_python_roots)))
    package_paths = _normal_paths(config.get("package_paths"), label="package_paths", workspace=workspace)
    tool_roots = _normal_paths(config.get("tool_roots"), label="tool_roots", workspace=workspace)
    path_entries = _normal_path_entries(config.get("path"), workspace=workspace)

    # A configured interpreter must be under an explicit runtime/package/tool root
    # or its private bin parent inferred above.  This prevents a config typo from
    # accidentally turning an arbitrary host executable into a capability.
    if python is not None:
        allowed_interpreter = any(
            python.is_relative_to(root) for root in (*runtime_roots, *package_paths, *tool_roots)
        )
        if not allowed_interpreter:
            raise SandboxError("python interpreter is outside the configured runtime roots")

    writable_roots: tuple[Path, ...]
    if role == "evaluation":
        writable_roots = (scratch,)
    else:
        writable_roots = (workspace, scratch)
    protected: list[Path] = []
    for name in CONTEXT_FOLDERS:
        candidate = workspace / name
        if candidate.exists():
            protected.append(_validate_no_symlink(candidate, label=f"protected context {name}"))
    protected.extend(extra_protected)
    # ``research``, ``inspection`` and ``.packages`` are service-owned outputs.
    # They remain readable to a task but are writable only through this trusted
    # service, so a shell cannot rewrite provenance after the fact.
    for candidate in (
        workspace / "research",
        workspace / "inspection",
        workspace / ".packages",
        scratch / "research",
        scratch / "inspection",
        scratch / ".packages",
    ):
        if candidate.exists():
            protected.append(_validate_no_symlink(candidate, label="service-owned path"))
    return SandboxPolicy(
        workspace=workspace,
        scratch=scratch,
        interpreter=python,
        runtime_roots=runtime_roots,
        package_paths=package_paths,
        tool_roots=tool_roots,
        path_entries=path_entries,
        writable_roots=tuple(dict.fromkeys(writable_roots)),
        protected_roots=tuple(dict.fromkeys(protected)),
    )


def sandbox_profile(policy: SandboxPolicy) -> str:
    """Generate a deny-by-default Seatbelt profile for ``policy``."""

    readable: list[Path] = list(SYSTEM_READ_ROOTS)
    readable += [policy.workspace, policy.scratch]
    readable += list(policy.runtime_roots)
    readable += list(policy.package_paths)
    readable += list(policy.tool_roots)
    readable += list(policy.path_entries)
    # Remove duplicates while preserving deterministic order.
    readable = list(dict.fromkeys(path.resolve() for path in readable))
    writable = list(dict.fromkeys(path.resolve() for path in policy.writable_roots))
    protected = list(dict.fromkeys(path.resolve() for path in policy.protected_roots))
    # Candidate code must not create a second process.  Shell commands are
    # therefore foreground operations: shell builtins may prepare a file, and
    # one explicitly requested executable may then replace the shell with
    # ``exec``.  Allowing the shell's normal fork path would let a detached
    # double-fork outlive the MCP call and defeat process-group cleanup.
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-exec*)",
        "(deny process-fork)",
        "(allow sysctl-read mach-lookup ipc-posix*)",
        "(allow file-read-metadata)",
        '(allow file-read* (literal "/"))',
        "(allow file-read* " + " ".join(f"(subpath {_literal(root)})" for root in readable) + ")",
        "(allow file-map-executable " + " ".join(f"(subpath {_literal(root)})" for root in readable) + ")",
    ]
    if SYSTEM_READ_FILES:
        lines.append(
            "(allow file-read* " + " ".join(f"(literal {_literal(path)})" for path in SYSTEM_READ_FILES) + ")"
        )
    if writable:
        lines.append("(allow file-write* " + " ".join(f"(subpath {_literal(root)})" for root in writable) + ")")
    if protected:
        lines.append("(deny file-write* " + " ".join(f"(subpath {_literal(root)})" for root in protected) + ")")
    lines.append(
        '(allow file-read* file-write* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))'
    )
    lines.append("(deny network*)")
    return "\n".join(lines) + "\n"


def clean_environment(policy: SandboxPolicy, *, package_paths: Sequence[Path] = ()) -> dict[str, str]:
    """Build the small environment visible to candidate shell processes."""

    temp_root = policy.scratch / ".capability-tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_root.chmod(0o700)
    path = os.pathsep.join(str(item) for item in policy.path_entries)
    packages = list(dict.fromkeys((*policy.package_paths, *package_paths)))
    # The service-created ``.packages`` directory is where individually selected
    # wheels are extracted.  It is appended for both direct interpreters and any
    # wrapper launched through the configured PATH.
    installed = (policy.scratch if policy.workspace == policy.scratch else policy.workspace) / ".packages"
    if policy.workspace.name == "scratch":
        installed = policy.workspace / ".packages"
    # In evaluation the writable root is ``workspace/scratch``; in other roles the
    # service uses ``workspace/.packages``.  The caller may pass the exact path too.
    if policy.scratch.name == "scratch" and policy.scratch.is_relative_to(policy.workspace):
        installed = policy.scratch / ".packages"
    packages.append(installed)
    package_path = os.pathsep.join(str(item) for item in dict.fromkeys(packages))
    environment = {
        "HOME": str(temp_root / "home"),
        "TMPDIR": str(temp_root),
        "PATH": path,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    (temp_root / "home").mkdir(parents=True, exist_ok=True)
    (temp_root / "home").chmod(0o700)
    if package_path:
        environment["PYTHONPATH"] = package_path
    return environment


def _descendant_pids(root_pid: int) -> set[int]:
    """Return a best-effort process tree snapshot without trusting candidate code."""

    try:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,ppid="],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    children: dict[int, list[int]] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            pid, parent = int(fields[0]), int(fields[1])
        except ValueError:
            continue
        children.setdefault(parent, []).append(pid)
    found: set[int] = set()
    queue = list(children.get(root_pid, ()))
    while queue:
        pid = queue.pop()
        if pid in found or pid == root_pid:
            continue
        found.add(pid)
        queue.extend(children.get(pid, ()))
    return found


def terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    """Kill the process group and descendants, including detached children when visible."""

    descendants = _descendant_pids(process.pid)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        # A foreground program may call ``setsid`` before a timeout.  macOS can
        # reject signalling that newly detached process group even though the
        # controller still owns the process; fall back to the registered root PID.
        try:
            os.kill(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    for pid in descendants:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    # A detached child can fork between the snapshot and the first kill.  Recheck
    # briefly while the parent is being reaped; this also prevents leaked shell jobs
    # from surviving a timeout in ordinary cases.
    for _ in range(3):
        time.sleep(0.02)
        for pid in _descendant_pids(process.pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _active_path(state: Path) -> Path:
    return Path(state).resolve() / "active-processes.json"


def _read_active(state: Path) -> list[dict[str, Any]]:
    path = _active_path(state)
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"processes": []}
    except (OSError, json.JSONDecodeError):
        # A malformed registry is safer treated as an empty registry than as a
        # source of arbitrary PIDs.  The parent still sees the command failure in
        # the operation receipt and can remove the private state on session abort.
        return []
    processes = value.get("processes") if isinstance(value, dict) else None
    if not isinstance(processes, list):
        return []
    result: list[dict[str, Any]] = []
    for item in processes:
        if not isinstance(item, dict):
            continue
        pid, pgid = item.get("pid"), item.get("pgid")
        if isinstance(pid, int) and isinstance(pgid, int) and pid > 1 and pgid > 1:
            members = item.get("members", ())
            if not isinstance(members, list):
                members = []
            valid_members = sorted({member for member in members if isinstance(member, int) and member > 1})
            result.append(
                {
                    "pid": pid,
                    "pgid": pgid,
                    "label": str(item.get("label", "shell")),
                    "started": item.get("started"),
                    "members": valid_members,
                }
            )
    return result


def _write_active(state: Path, processes: Sequence[Mapping[str, Any]]) -> None:
    path = _active_path(state)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = json.dumps({"version": 1, "processes": [dict(item) for item in processes]}, sort_keys=True).encode()
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _update_active_members(state: Path, pid: int, members: Sequence[int]) -> None:
    """Persist descendants observed while the root shell is still alive."""

    with _ACTIVE_LOCK:
        processes = _read_active(state)
        changed = False
        member_set = sorted({member for member in members if isinstance(member, int) and member > 1})
        for item in processes:
            if item.get("pid") == pid:
                if item.get("members") != member_set:
                    item["members"] = member_set
                    changed = True
                break
        if changed:
            _write_active(state, processes)


def register_active_process(state: Path, process: subprocess.Popen[Any], *, label: str = "shell") -> None:
    """Atomically register a shell process before waiting for its output."""

    try:
        pgid = os.getpgid(process.pid)
    except OSError:
        pgid = process.pid
    with _ACTIVE_LOCK:
        processes = _read_active(state)
        processes.append({"pid": process.pid, "pgid": pgid, "label": label, "started": time.time(), "members": []})
        _write_active(state, processes)


def unregister_active_process(state: Path, process: subprocess.Popen[Any]) -> None:
    """Remove a process only after its group has been reaped or killed."""

    with _ACTIVE_LOCK:
        processes = [item for item in _read_active(state) if item.get("pid") != process.pid]
        _write_active(state, processes)


def _kill_active_record(record: Mapping[str, Any]) -> None:
    pid, pgid = record.get("pid"), record.get("pgid")
    if not isinstance(pid, int) or not isinstance(pgid, int) or pid <= 1 or pgid <= 1:
        return
    # Capture children before killing the group; detached children are then killed
    # by PID as well.  Only PIDs recorded by this service are considered.
    descendants = _descendant_pids(pid)
    observed = record.get("members", ())
    if isinstance(observed, list):
        descendants.update(member for member in observed if isinstance(member, int) and member > 1)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    for child in descendants | {pid}:
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            pass


def terminate_active_processes(state: Path) -> None:
    """Kill all shell groups left by a crashed service and clear the registry.

    The parent executor can call this in its ``finally`` block before removing a
    temporary capability environment.  It is also safe to call at service startup
    to clean a previous interrupted session.
    """

    with _ACTIVE_LOCK:
        processes = _read_active(state)
        for record in processes:
            _kill_active_record(record)
        # Recheck descendants briefly while process groups are being reaped.
        for _ in range(3):
            time.sleep(0.02)
            for record in processes:
                _kill_active_record(record)
        _write_active(state, ())


class _Capture:
    def __init__(self, stream: Any, path: Path, max_bytes: int) -> None:
        self.stream = stream
        self.path = path
        self.max_bytes = max_bytes
        self.count = 0
        self.digest = hashlib.sha256()
        self.truncated = False
        self.thread = threading.Thread(target=self._run, name="capability-output", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("wb") as handle:
            while True:
                chunk = self.stream.read(64 * 1024)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8", errors="replace")
                self.count += len(chunk)
                self.digest.update(chunk)
                if handle.tell() < self.max_bytes:
                    remaining = self.max_bytes - handle.tell()
                    handle.write(chunk[:remaining])
                    if len(chunk) > remaining:
                        self.truncated = True
                else:
                    self.truncated = True
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def join(self) -> None:
        self.thread.join(timeout=5)

    def text(self) -> str:
        try:
            value = self.path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            value = ""
        if len(value.encode("utf-8")) > MAX_TOOL_TEXT_BYTES:
            encoded = value.encode("utf-8")[:MAX_TOOL_TEXT_BYTES]
            value = encoded.decode("utf-8", errors="ignore") + "\n[output truncated for tool response]"
        return value


def run_sandboxed(
    command: str,
    *,
    policy: SandboxPolicy,
    environment: Mapping[str, str],
    output_dir: Path,
    timeout_seconds: float,
    label: str = "shell",
    active_state: Path | None = None,
    arguments: Sequence[str] = (),
) -> SandboxedCommandResult:
    """Execute one command under the generated native profile."""

    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise SandboxError("native macOS sandbox-exec is unavailable; shell capability is disabled")
    if not isinstance(command, str) or not command.strip():
        raise SandboxError("shell command must be a non-empty string")
    if len(command) > MAX_SHELL_COMMAND_CHARS:
        raise SandboxError("shell command exceeds the maximum length")
    if timeout_seconds <= 0 or timeout_seconds > MAX_SHELL_TIMEOUT_SECONDS:
        raise SandboxError(f"shell timeout must be between 0 and {MAX_SHELL_TIMEOUT_SECONDS} seconds")
    output_dir = _validate_no_symlink(output_dir, label="shell output directory")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_dir.chmod(0o700)
    profile = sandbox_profile(policy)
    invocation = (
        "/usr/bin/sandbox-exec",
        "-p",
        profile,
        "/bin/sh",
        "-c",
        command,
        label,
        *arguments,
    )
    display_command = (
        "/usr/bin/sandbox-exec",
        "-p",
        "<private sandbox profile>",
        "/bin/sh",
        "-c",
        command,
        label,
        *arguments,
    )
    call_id = uuid.uuid4().hex
    stdout_path = output_dir / f"{call_id}.stdout.log"
    stderr_path = output_dir / f"{call_id}.stderr.log"
    profile_path = output_dir / f"{call_id}.sandbox.sb"
    try:
        profile_path.write_text(profile, encoding="utf-8")
        profile_path.chmod(0o600)
    except OSError as exc:
        raise SandboxError(f"could not save sandbox profile: {exc}") from exc
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            list(invocation),
            cwd=policy.workspace,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            start_new_session=True,
        )
    except OSError as exc:
        raise SandboxError(f"could not start sandboxed shell: {exc}") from exc
    if active_state is not None:
        try:
            register_active_process(active_state, process, label=label)
        except BaseException:
            terminate_process_tree(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            raise
    assert process.stdout is not None and process.stderr is not None
    observed_members: set[int] = set()
    monitor_stop = threading.Event()

    def monitor_process_tree() -> None:
        while not monitor_stop.wait(0.03):
            observed_members.update(_descendant_pids(process.pid))
            if active_state is not None:
                try:
                    _update_active_members(active_state, process.pid, sorted(observed_members))
                except OSError:
                    # The command itself remains bounded; the parent cleanup
                    # helper will retry if the registry becomes temporarily
                    # unavailable.
                    pass

    monitor = threading.Thread(target=monitor_process_tree, name="capability-process-monitor", daemon=True)
    monitor.start()
    stdout_capture = _Capture(process.stdout, stdout_path, MAX_SHELL_CAPTURE_BYTES)
    stderr_capture = _Capture(process.stderr, stderr_path, MAX_SHELL_CAPTURE_BYTES)
    stdout_capture.start()
    stderr_capture.start()
    timed_out = False
    error: str | None = None
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        error = "TimeoutExpired"
        terminate_process_tree(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            error = "TimeoutExpired; process did not exit after kill"
    except KeyboardInterrupt:
        error = "KeyboardInterrupt"
        terminate_process_tree(process)
        process.wait(timeout=5)
    # A successful shell can leave ``cmd &`` children behind after the shell
    # itself exits.  Kill the group before removing its registry entry so no
    # background task survives the capability call.
    monitor_stop.set()
    monitor.join(timeout=1)
    if active_state is not None:
        _update_active_members(active_state, process.pid, sorted(observed_members))
    terminate_process_tree(process)
    for member in observed_members:
        try:
            os.kill(member, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            pass
    stdout_capture.join()
    stderr_capture.join()
    elapsed = time.monotonic() - started
    status = "timeout" if timed_out else ("completed" if process.returncode == 0 else "failed")
    result = SandboxedCommandResult(
        command=display_command,
        returncode=process.returncode,
        status=status,
        elapsed_seconds=elapsed,
        stdout=stdout_capture.text(),
        stderr=stderr_capture.text(),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        stdout_sha256=stdout_capture.digest.hexdigest(),
        stderr_sha256=stderr_capture.digest.hexdigest(),
        stdout_bytes=stdout_capture.count,
        stderr_bytes=stderr_capture.count,
        stdout_truncated=stdout_capture.truncated,
        stderr_truncated=stderr_capture.truncated,
        profile_path=profile_path,
        error=error,
    )
    if active_state is not None:
        unregister_active_process(active_state, process)
    return result


def verify_policy(policy: SandboxPolicy, output_dir: Path) -> dict[str, Any]:
    """Run native read/write, no-fork, and network probes before shell exposure.

    The process boundary deliberately permits only ``exec`` after the service has
    created the shell.  This means a participant command may use shell builtins,
    then ``exec`` one foreground program; a second external command belongs in a
    later capability call or in the foreground program itself.
    """

    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise SandboxError("native macOS sandbox-exec is unavailable; no shell capability exposed")
    output_dir = _validate_no_symlink(output_dir, label="probe output directory")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_dir.chmod(0o700)
    probe_root = policy.scratch / (".capability-probe-" + uuid.uuid4().hex)
    probe_root.mkdir(parents=True, mode=0o700)
    allowed = probe_root / "allowed.txt"
    protected = probe_root / "protected.txt"
    protected.write_text("protected\n", encoding="utf-8")
    # ``tempfile`` otherwise honors a caller's TMPDIR.  A participant task may
    # intentionally set TMPDIR to its workspace, which would turn the outside
    # positive-control sentinel into an allowed path and invalidate the probe.
    outside_directory = Path(tempfile.mkdtemp(prefix="eval-harness-capability-outside-", dir="/private/tmp"))
    outside = outside_directory / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    # The listener lets the probe distinguish a denied network from a merely closed
    # port.  No participant or model call is involved.
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = str(listener.getsockname()[1])
    protected_policy = SandboxPolicy(
        workspace=policy.workspace,
        scratch=policy.scratch,
        interpreter=policy.interpreter,
        runtime_roots=policy.runtime_roots,
        package_paths=policy.package_paths,
        tool_roots=policy.tool_roots,
        path_entries=policy.path_entries,
        writable_roots=policy.writable_roots,
        protected_roots=tuple(dict.fromkeys((*policy.protected_roots, probe_root / "protected.txt"))),
    )
    probe_environment = clean_environment(protected_policy)

    def run_probe(command: str, *arguments: str, label: str) -> SandboxedCommandResult:
        return run_sandboxed(
            command,
            policy=protected_policy,
            environment=probe_environment,
            output_dir=output_dir,
            timeout_seconds=10,
            label=label,
            active_state=output_dir.parent,
            arguments=arguments,
        )

    # Do all file checks with shell builtins.  Command substitution and external
    # utilities would themselves require a fork under the hardened profile.
    file_script = "\n".join(
        [
            "set -eu",
            'IFS= read -r actual < "$1"',
            'test "$actual" = protected',
            'if IFS= read -r actual < "$2"; then exit 31; fi',
            'if printf changed >"$1" 2>/dev/null; then exit 32; fi',
            'printf allowed >"$3"',
            "printf capability-ok",
        ]
    )
    try:
        file_result = run_probe(file_script + "\n", str(protected), str(outside), str(allowed), label="probe-files")
        if (
            file_result.status != "completed"
            or file_result.returncode != 0
            or file_result.stdout.strip() != "capability-ok"
            or not allowed.is_file()
            or protected.read_text(encoding="utf-8") != "protected\n"
            or outside.read_text(encoding="utf-8") != "outside\n"
        ):
            raise SandboxError(
                "native file capability probe failed: "
                + json.dumps(file_result.as_dict(), sort_keys=True, default=str)
            )
        # A hard link would turn a protected inode into a writable workspace path
        # on filesystems where path-only write denial is insufficient.  Seatbelt's
        # default-deny file-link rule must reject the foreground ``ln`` call.
        hard_link = probe_root / "hard-link.txt"
        link_result = run_probe('exec /bin/ln "$1" "$2"', str(protected), str(hard_link), label="probe-hard-link")
        if link_result.status == "completed" or link_result.returncode in (None, 0) or hard_link.exists():
            raise SandboxError(
                "native hard-link capability probe failed: "
                + json.dumps(link_result.as_dict(), sort_keys=True, default=str)
            )
        if not Path("/usr/bin/nc").is_file():
            raise SandboxError("native network capability probe requires /usr/bin/nc")
        network_result = run_probe('exec /usr/bin/nc -z -w 1 127.0.0.1 "$1"', port, label="probe-network")
        listener.settimeout(0.2)
        try:
            listener.accept()
        except (TimeoutError, socket.timeout, OSError):
            pass
        else:
            raise SandboxError(
                "native network capability probe connected despite deny: "
                + json.dumps(network_result.as_dict(), sort_keys=True, default=str)
            )
        if network_result.status == "completed" or network_result.returncode in (None, 0):
            raise SandboxError(
                "native network capability probe failed: "
                + json.dumps(network_result.as_dict(), sort_keys=True, default=str)
            )
        # The shell's background path must be denied by the kernel, rather than
        # merely cleaned up by the parent process after a successful call.
        background_result = run_probe(": &", label="probe-no-fork")
        if background_result.status == "completed" or background_result.returncode in (None, 0):
            raise SandboxError(
                "native process-fork capability probe failed: "
                + json.dumps(background_result.as_dict(), sort_keys=True, default=str)
            )
        python_result: SandboxedCommandResult | None = None
        if policy.interpreter is not None:
            python_probe = """import os
import sys

def expect_fork_denied(name, operation):
    try:
        value = operation()
    except OSError:
        return
    if name == "fork" and value == 0:
        os._exit(42)
    raise SystemExit("sandbox unexpectedly allowed " + name)

expect_fork_denied("fork", os.fork)
expect_fork_denied(
    "posix_spawn",
    lambda: os.posix_spawn("/bin/true", ["/bin/true"], os.environ.copy()),
)
try:
    os.setsid()
    session = "setsid-ok"
except OSError:
    session = "setsid-denied"
print("no-fork-python-ok " + session)
"""
            python_command = f"exec {shlex.quote(str(policy.interpreter))} -c {shlex.quote(python_probe)}"
            python_result = run_probe(python_command, label="probe-python")
            if (
                python_result.status != "completed"
                or python_result.returncode != 0
                or not python_result.stdout.startswith("no-fork-python-ok ")
            ):
                raise SandboxError(
                    "native Python no-fork probe failed: "
                    + json.dumps(python_result.as_dict(), sort_keys=True, default=str)
                )
        return {
            "available": True,
            "verified": True,
            "platform": sys.platform,
            "sandbox": "/usr/bin/sandbox-exec",
            "process_fork": "denied",
            "process_exec": "foreground-only",
            "file_stdout_sha256": file_result.stdout_sha256,
            "file_stderr_sha256": file_result.stderr_sha256,
            "network_stdout_sha256": network_result.stdout_sha256,
            "network_stderr_sha256": network_result.stderr_sha256,
            "no_fork_stdout_sha256": background_result.stdout_sha256,
            "no_fork_stderr_sha256": background_result.stderr_sha256,
            "python_probe_stdout_sha256": python_result.stdout_sha256 if python_result is not None else None,
            "python_probe_stderr_sha256": python_result.stderr_sha256 if python_result is not None else None,
            "elapsed_seconds": sum(
                item.elapsed_seconds for item in (file_result, link_result, network_result, background_result)
            )
            + (python_result.elapsed_seconds if python_result is not None else 0.0),
        }
    finally:
        listener.close()
        shutil.rmtree(outside_directory, ignore_errors=True)
        shutil.rmtree(probe_root, ignore_errors=True)
