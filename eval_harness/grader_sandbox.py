# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host-side policy and bounded process infrastructure for BigCodeBench.

The public preflight and grade entry points remain deliberately fail-closed
until the manifest and attestation implementation is added.  The policy
builder, lock and selector loop in this module are nevertheless complete
building blocks: they have no unsandboxed fallback and are useful to the real
boundary tests and the later attested launch path.
"""

from __future__ import annotations

import contextlib
import fcntl
import math
import os
import selectors
import signal
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final, Iterator, Sequence

from eval_harness.bigcodebench_runner import (
    INPUT_FIXED_BYTES,
    AuthenticatedOutputParser,
    BigCodeBenchGradeRequest,
    FrameType,
    GraderNativeResult,
    LimitKind,
    NativeSignal,
    NativeStatus,
    ProtocolError,
    parse_authenticated_output,
)


POLICY_REVISION: Final[str] = "bigcodebench-bwrap-v1"
BUBBLEWRAP_VERSION: Final[str] = "0.12.0"
RUNNER_GUEST_PATH: Final[str] = "/opt/bigcodebench/bigcodebench_runner.py"
VENDOR_GUEST_PATH: Final[str] = "/opt/bigcodebench/vendor"
NLTK_DATA_GUEST_PATH: Final[str] = "/opt/bigcodebench/nltk_data"
LOCK_PATH_TEMPLATE: Final[str] = "/tmp/nemo-gym-bigcodebench-grader-{uid}.lock"
DESCENDANT_SAMPLE_SECONDS: Final[float] = 0.025

_FIXED_ENVIRONMENT: Final[tuple[tuple[str, str], ...]] = (
    ("LANG", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
    ("TZ", "UTC"),
    ("HOME", "/tmp/home"),
    ("TMPDIR", "/tmp"),
    ("MPLBACKEND", "Agg"),
    ("NLTK_DATA", NLTK_DATA_GUEST_PATH),
    ("BIGCODEBENCH_NLTK_OFFLINE", POLICY_REVISION),
    ("XDG_CACHE_HOME", "/tmp/cache"),
    ("XDG_CONFIG_HOME", "/tmp/config"),
    ("XDG_DATA_HOME", "/tmp/data"),
    ("MPLCONFIGDIR", "/tmp/matplotlib"),
    ("NUMBA_CACHE_DIR", "/tmp/numba"),
    ("TORCH_HOME", "/tmp/torch"),
    ("HF_HOME", "/tmp/huggingface"),
    ("JOBLIB_TEMP_FOLDER", "/tmp/joblib"),
    ("CUDA_VISIBLE_DEVICES", ""),
    ("TOKENIZERS_PARALLELISM", "false"),
    ("OMP_NUM_THREADS", "1"),
    ("OPENBLAS_NUM_THREADS", "1"),
    ("MKL_NUM_THREADS", "1"),
    ("VECLIB_MAXIMUM_THREADS", "1"),
    ("NUMEXPR_NUM_THREADS", "1"),
    ("BLIS_NUM_THREADS", "1"),
    ("RAYON_NUM_THREADS", "1"),
    ("TF_NUM_INTRAOP_THREADS", "1"),
    ("TF_NUM_INTEROP_THREADS", "1"),
)

_SYSTEM_OPTIONAL_MOUNTS: Final[tuple[tuple[str, str], ...]] = (
    ("/etc/ld.so.cache", "/etc/ld.so.cache"),
    ("/etc/ssl/certs", "/etc/ssl/certs"),
    ("/etc/fonts", "/etc/fonts"),
    ("/etc/localtime", "/etc/localtime"),
)
_SYNTHETIC_ETC_FILES: Final[tuple[str, ...]] = ("hosts", "nsswitch.conf", "resolv.conf", "passwd", "group")
_TMP_DIRS: Final[tuple[str, ...]] = (
    "/tmp/home",
    "/tmp/work",
    "/tmp/cache",
    "/tmp/config",
    "/tmp/data",
    "/tmp/matplotlib",
    "/tmp/numba",
    "/tmp/torch",
    "/tmp/huggingface",
    "/tmp/joblib",
)


@dataclass(frozen=True, slots=True)
class GraderSandboxLimits:
    startup_seconds: float = 20.0
    candidate_wall_seconds: float = 250.0
    teardown_seconds: float = 5.0
    cpu_soft_seconds: int = 245
    cpu_hard_seconds: int = 250
    address_space_bytes: int = 8 * 1024**3
    data_bytes: int = 6 * 1024**3
    aggregate_rss_bytes: int = 6 * 1024**3
    stack_bytes: int = 10 * 1024**2
    file_bytes: int = 64 * 1024**2
    open_files: int = 256
    process_headroom: int = 32
    tmp_bytes: int = 512 * 1024**2
    shm_bytes: int = 64 * 1024**2
    stdin_bytes: int = 8 * 1024**2
    protocol_bytes: int = 16 * 1024
    diagnostic_bytes: int = 32 * 1024

    def __post_init__(self) -> None:
        for name in ("startup_seconds", "candidate_wall_seconds", "teardown_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} must be a finite positive number")
        for name in (
            "cpu_soft_seconds",
            "cpu_hard_seconds",
            "address_space_bytes",
            "data_bytes",
            "aggregate_rss_bytes",
            "stack_bytes",
            "file_bytes",
            "open_files",
            "process_headroom",
            "tmp_bytes",
            "shm_bytes",
            "stdin_bytes",
            "protocol_bytes",
            "diagnostic_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.cpu_soft_seconds > self.cpu_hard_seconds:
            raise ValueError("cpu_soft_seconds cannot exceed cpu_hard_seconds")


PRODUCTION_GRADER_LIMITS: Final[GraderSandboxLimits] = GraderSandboxLimits()


def _require_path(value: object, field: str) -> Path:
    if not isinstance(value, Path):
        raise TypeError(f"{field} must be a pathlib.Path")
    return value


@dataclass(frozen=True, slots=True)
class GraderSandboxSpec:
    resource_dir: Path
    bwrap_path: Path
    grader_python: Path
    forbidden_roots: tuple[Path, ...] = ()
    limits: GraderSandboxLimits = PRODUCTION_GRADER_LIMITS
    manifest_path: Path | None = None

    def __post_init__(self) -> None:
        _require_path(self.resource_dir, "resource_dir")
        _require_path(self.bwrap_path, "bwrap_path")
        _require_path(self.grader_python, "grader_python")
        if type(self.forbidden_roots) is not tuple:
            raise TypeError("forbidden_roots must be a tuple")
        for root in self.forbidden_roots:
            _require_path(root, "forbidden_roots item")
        if not isinstance(self.limits, GraderSandboxLimits):
            raise TypeError("limits must be GraderSandboxLimits")
        if self.manifest_path is not None:
            _require_path(self.manifest_path, "manifest_path")


@dataclass(frozen=True, slots=True)
class GraderSandboxPreflight:
    ok: bool
    sandbox_version: str | None
    policy_revision: str
    spec_sha256: str | None
    manifest_sha256: str | None
    attestation_sha256: str | None
    details: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.ok) is not bool:
            raise TypeError("ok must be a boolean")
        if self.sandbox_version is not None and type(self.sandbox_version) is not str:
            raise TypeError("sandbox_version must be a string or None")
        if type(self.policy_revision) is not str:
            raise TypeError("policy_revision must be a string")
        for name in ("spec_sha256", "manifest_sha256", "attestation_sha256"):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f"{name} must be a string or None")
        if type(self.details) is not tuple or any(type(item) is not str for item in self.details):
            raise TypeError("details must be a tuple of strings")


class GraderInfrastructureError(RuntimeError):
    """An evaluator or sandbox failure, distinct from a candidate result."""


@dataclass(frozen=True, slots=True)
class _ResolvedSandboxPaths:
    """Resolved host paths used by the one policy builder."""

    venv: Path
    base_prefix: Path
    runner: Path
    vendor: Path
    nltk_data: Path
    sandbox_etc: Path


def _real_path(path: Path, field: str, *, must_exist: bool = True) -> Path:
    """Resolve one trusted path, rejecting relative and unresolvable values."""

    if not path.is_absolute():
        raise GraderInfrastructureError(f"{field} is not an absolute path")
    try:
        resolved = path.resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise GraderInfrastructureError(f"{field} cannot be resolved") from exc
    if not resolved.is_absolute():
        raise GraderInfrastructureError(f"{field} is not an absolute path")
    return resolved


def _venv_base_prefix(venv: Path) -> Path:
    """Read the venv's trusted ``home`` value without consulting host env."""

    config = venv / "pyvenv.cfg"
    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise GraderInfrastructureError("grader interpreter metadata is unavailable") from exc
    for line in lines:
        name, separator, value = line.partition("=")
        if name.strip() == "home" and separator:
            home = Path(value.strip())
            if not home.is_absolute():
                raise GraderInfrastructureError("grader interpreter metadata is invalid")
            # pyvenv.cfg conventionally points at ``<prefix>/bin``.  Accept a
            # direct prefix too, but never infer a host prefix from sys.path.
            if home.name == "bin":
                home = home.parent
            return _real_path(home, "base interpreter prefix")
    raise GraderInfrastructureError("grader interpreter metadata is unavailable")


def _resolve_sandbox_paths(spec: GraderSandboxSpec) -> _ResolvedSandboxPaths:
    resource_dir = _real_path(spec.resource_dir, "resource directory")
    if spec.bwrap_path.is_symlink():
        raise GraderInfrastructureError("bubblewrap executable is a symlink")
    bwrap = _real_path(spec.bwrap_path, "bubblewrap executable")
    if not bwrap.is_file() or bwrap.is_symlink():
        raise GraderInfrastructureError("bubblewrap executable is not a regular file")
    if spec.grader_python.is_symlink():
        raise GraderInfrastructureError("grader interpreter is a symlink")
    grader_python = _real_path(spec.grader_python, "grader interpreter")
    if not grader_python.is_file() or grader_python.is_symlink():
        raise GraderInfrastructureError("grader interpreter is not a regular file")
    venv = _real_path(grader_python.parent.parent, "grader virtual environment")
    base_prefix = _venv_base_prefix(venv)
    runner = _real_path(Path(__file__).with_name("bigcodebench_runner.py"), "grader runner")
    vendor = _real_path(resource_dir / "vendor", "vendored grader")
    nltk_data = _real_path(resource_dir / "nltk_data", "grader data")
    sandbox_etc = _real_path(resource_dir / "sandbox_etc", "sandbox etc")
    paths = _ResolvedSandboxPaths(venv, base_prefix, runner, vendor, nltk_data, sandbox_etc)

    selected = (paths.venv, paths.base_prefix, paths.runner, paths.vendor, paths.nltk_data, paths.sandbox_etc)
    forbidden = tuple(_real_path(root, "forbidden root") for root in spec.forbidden_roots)
    for candidate in selected:
        for root in forbidden:
            if candidate == root or candidate.is_relative_to(root) or root.is_relative_to(candidate):
                raise GraderInfrastructureError("trusted mount intersects an untrusted root")
    # The policy requires these trees to be independently attested.  A nested
    # bind would make a later mutation observable through a second mount.
    disjoint = (paths.venv, paths.base_prefix, paths.vendor, paths.nltk_data)
    for index, candidate in enumerate(disjoint):
        for other in disjoint[index + 1 :]:
            if candidate == other or candidate.is_relative_to(other) or other.is_relative_to(candidate):
                raise GraderInfrastructureError("trusted mount trees are not disjoint")
    return paths


def _count_real_uid_processes() -> int:
    """Count processes owned by this real UID for the NPROC baseline."""

    proc_root = Path("/proc")
    uid = os.getuid()
    count = 0
    try:
        entries = tuple(proc_root.iterdir())
    except OSError as exc:
        raise GraderInfrastructureError("process baseline is unavailable") from exc
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        try:
            threads = _process_thread_count(entry, uid)
        except GraderInfrastructureError:
            raise
        if threads is not None:
            count += threads
    if count <= 0:
        raise GraderInfrastructureError("process baseline is invalid")
    return count


def _process_thread_count(entry: Path, uid: int) -> int | None:
    """Return a process's thread count when its real UID matches ``uid``."""

    try:
        status_lines = (entry / "status").read_text(encoding="utf-8", errors="replace").splitlines()
        uid_fields = next((line.split() for line in status_lines if line.startswith("Uid:")), None)
        thread_fields = next((line.split() for line in status_lines if line.startswith("Threads:")), None)
        if (
            uid_fields is None
            or len(uid_fields) < 2
            or not uid_fields[1].isdecimal()
            or thread_fields is None
            or len(thread_fields) < 2
            or not thread_fields[1].isdecimal()
            or int(thread_fields[1]) <= 0
        ):
            raise ValueError("invalid process status rows")
        return int(thread_fields[1]) if int(uid_fields[1]) == uid else 0
    except FileNotFoundError:
        # Processes can disappear between readdir and status read.
        return None
    except (OSError, UnicodeError, ValueError) as exc:
        try:
            entry.stat()
        except FileNotFoundError:
            return None
        except OSError as stat_exc:
            raise GraderInfrastructureError("process baseline observation failed") from stat_exc
        raise GraderInfrastructureError("process baseline observation failed") from exc


def _validate_process_limit(value: int) -> int:
    if type(value) is not int or value <= 0 or value > (2**63 - 1):
        raise GraderInfrastructureError("process limit is invalid")
    return value


def _build_bwrap_command(spec: GraderSandboxSpec, *, process_limit: int | None = None) -> tuple[str, ...]:
    """Build the sole supported bubblewrap command, with no fallback flags."""

    paths = _resolve_sandbox_paths(spec)
    limits = spec.limits
    baseline = _count_real_uid_processes() if process_limit is None else process_limit
    if process_limit is None:
        baseline = baseline + limits.process_headroom
    baseline = _validate_process_limit(baseline)

    command: list[str] = [
        str(spec.bwrap_path.resolve()),
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-net",
        "--unshare-uts",
        "--disable-userns",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--new-session",
        "--die-with-parent",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        str(limits.tmp_bytes),
        "--tmpfs",
        "/tmp",
        "--size",
        str(limits.shm_bytes),
        "--tmpfs",
        "/dev/shm",
    ]
    for directory in _TMP_DIRS:
        command.extend(("--dir", directory))
    command.append("--dir")
    command.append("/etc")

    # These are the only host paths visible in the mount namespace.  Every
    # bind is read-only and keeps its resolved host spelling in the guest.
    command.extend(("--ro-bind", str(paths.venv), str(paths.venv)))
    command.extend(("--ro-bind", str(paths.base_prefix), str(paths.base_prefix)))
    command.extend(("--ro-bind", str(paths.runner), RUNNER_GUEST_PATH))
    command.extend(("--ro-bind", str(paths.vendor), VENDOR_GUEST_PATH))
    command.extend(("--ro-bind", str(paths.nltk_data), NLTK_DATA_GUEST_PATH))
    command.extend(("--ro-bind", "/usr", "/usr"))
    for target, link in (("usr/bin", "/bin"), ("usr/sbin", "/sbin"), ("usr/lib", "/lib"), ("usr/lib64", "/lib64")):
        command.extend(("--symlink", target, link))
    for source, target in _SYSTEM_OPTIONAL_MOUNTS:
        if Path(source).exists():
            command.extend(("--ro-bind", source, target))
    for name in _SYNTHETIC_ETC_FILES:
        source_path = paths.sandbox_etc / name
        if not source_path.is_file() or source_path.is_symlink():
            raise GraderInfrastructureError("synthetic sandbox etc file is unavailable")
        command.extend(("--ro-bind", str(source_path), f"/etc/{name}"))
    command.extend(("--remount-ro", "/dev", "--remount-ro", "/"))

    environment = (("PATH", f"{paths.venv / 'bin'}:/usr/bin:/bin"),) + _FIXED_ENVIRONMENT
    for name, environment_value in environment:
        command.extend(("--setenv", name, environment_value))
    command.extend(("--chdir", "/tmp/work", str(spec.grader_python.resolve()), "-I", "-B", RUNNER_GUEST_PATH))
    cli_limits = (
        ("--cpu-soft-seconds", limits.cpu_soft_seconds),
        ("--cpu-hard-seconds", limits.cpu_hard_seconds),
        ("--address-space-bytes", limits.address_space_bytes),
        ("--data-bytes", limits.data_bytes),
        ("--stack-bytes", limits.stack_bytes),
        ("--file-bytes", limits.file_bytes),
        ("--open-files", limits.open_files),
        ("--processes", baseline),
    )
    for flag, limit_value in cli_limits:
        command.extend((flag, str(limit_value)))
    return tuple(command)


@contextlib.contextmanager
def _exclusive_grader_lock() -> Iterator[None]:
    """Hold the secure per-real-UID launch lock across a complete grade."""

    uid = os.getuid()
    path = Path(LOCK_PATH_TEMPLATE.format(uid=uid))
    flags = os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise GraderInfrastructureError("grader lock unavailable") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise GraderInfrastructureError("grader lock has unsafe metadata")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError as exc:
            raise GraderInfrastructureError("grader lock acquisition failed") from exc
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _proc_parent_map() -> dict[int, int]:
    """Read a host-visible PID parent map, failing on live unreadable rows."""

    result: dict[int, int] = {}
    try:
        entries = tuple(Path("/proc").iterdir())
    except OSError as exc:
        raise GraderInfrastructureError("process tree is unavailable") from exc
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        try:
            raw = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            tail = raw.rsplit(")", 1)[1].split()
            if len(tail) < 2:
                raise ValueError("short stat row")
            result[int(entry.name)] = int(tail[1])
        except FileNotFoundError:
            # A process can disappear between readdir and stat/read.
            continue
        except (OSError, UnicodeError, ValueError, IndexError) as exc:
            try:
                entry.stat()
            except FileNotFoundError:
                continue
            except OSError as stat_exc:
                raise GraderInfrastructureError("process tree observation failed") from stat_exc
            raise GraderInfrastructureError("process tree observation failed") from exc
    return result


def _descendant_pids(root_pid: int) -> set[int]:
    parents = _proc_parent_map()
    descendants: set[int] = set()
    frontier = [root_pid]
    while frontier:
        parent = frontier.pop()
        children = [pid for pid, ppid in parents.items() if ppid == parent and pid not in descendants]
        descendants.update(children)
        frontier.extend(children)
    return descendants


def _rss_bytes(pid: int) -> int:
    status_path = Path("/proc") / str(pid) / "status"
    try:
        lines = status_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return 0
    except (OSError, UnicodeError) as exc:
        raise GraderInfrastructureError("process memory observation failed") from exc
    state: str | None = None
    try:
        for line in lines:
            if line.startswith("State:"):
                fields = line.split()
                if len(fields) < 2:
                    raise ValueError("invalid process state row")
                state = fields[1]
            elif line.startswith("VmRSS:"):
                fields = line.split()
                if len(fields) >= 2 and fields[1].isdecimal():
                    return int(fields[1]) * 1024
                raise ValueError("invalid VmRSS row")
    except ValueError as exc:
        raise GraderInfrastructureError("process memory observation failed") from exc
    if state in {"Z", "X"}:
        return 0
    raise GraderInfrastructureError("process memory observation is incomplete")


def _sample_process_tree(root_pid: int) -> tuple[set[int], int]:
    descendants = _descendant_pids(root_pid)
    observed = descendants | {root_pid}
    return descendants, sum(_rss_bytes(pid) for pid in observed)


def _ensure_cleanup_deadline(existing: float | None, duration: float) -> float:
    if existing is not None:
        return existing
    return time.monotonic() + duration


def _terminate_and_reap(process: subprocess.Popen[bytes], recorded: set[int], deadline: float) -> bool:
    """Kill only the outer bwrap PID and require its recorded tree to vanish."""

    killed = False
    try:
        if process.poll() is None:
            process.kill()
            killed = True
    except (OSError, ProcessLookupError) as exc:
        raise GraderInfrastructureError("sandbox termination failed") from exc
    _wait_for_cleanup(process, recorded, deadline)
    return killed and process.returncode == -signal.SIGKILL


def _wait_for_cleanup(process: subprocess.Popen[bytes], recorded: set[int], deadline: float) -> None:
    """Wait for the trusted process and every observed descendant to vanish."""

    while True:
        # Poll first so a failure to inspect the descendant tree never leaves
        # the outer process unreaped.  The observation error remains fatal.
        process_done = process.poll() is not None
        observation_error: GraderInfrastructureError | None = None
        live = {pid for pid in recorded if Path(f"/proc/{pid}").exists()}
        try:
            live.update(_descendant_pids(process.pid))
        except GraderInfrastructureError as exc:
            observation_error = exc
        if process_done and observation_error is not None:
            raise observation_error
        if process_done and not live:
            return
        if time.monotonic() >= deadline:
            if observation_error is not None:
                raise observation_error
            raise GraderInfrastructureError("sandbox descendants did not exit")
        time.sleep(min(DESCENDANT_SAMPLE_SECONDS, max(0.0, deadline - time.monotonic())))


def _run_bounded_supervisor(
    command: Sequence[str],
    input_bytes: bytes,
    key: bytes,
    limits: GraderSandboxLimits,
) -> GraderNativeResult:
    """Run bwrap with one bounded nonblocking selector loop.

    This helper intentionally accepts an already encoded BCBI byte string and
    a per-run key.  Attestation, canonical request construction and public
    production wiring are added only in the following batch.
    """

    _validate_input_size(input_bytes, limits)
    try:
        process = subprocess.Popen(
            tuple(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            close_fds=True,
            pass_fds=(),
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        raise GraderInfrastructureError("sandbox launch failed") from exc
    output = bytearray()
    diagnostics = bytearray()
    recorded_descendants: set[int] = set()
    stdin = process.stdin
    stdout = process.stdout
    stderr = process.stderr
    selector: selectors.BaseSelector | None = None
    cleanup_started = False
    cleanup_deadline: float | None = None
    try:
        if stdin is None or stdout is None or stderr is None:
            raise GraderInfrastructureError("sandbox pipes unavailable")
        parser = AuthenticatedOutputParser(key)
        selector = selectors.DefaultSelector()
        started = False
        terminal = False
        enforced: LimitKind | None = None
        input_offset = 0
        stdin_open = bool(input_bytes)
        now = time.monotonic()
        deadline = now + limits.startup_seconds
        next_sample = now
        registered_streams: dict[str, IO[bytes]] = {"stdout": stdout, "stderr": stderr}
        for bound_stream, event_mask, name in (
            (stdout, selectors.EVENT_READ, "stdout"),
            (stderr, selectors.EVENT_READ, "stderr"),
        ):
            os.set_blocking(bound_stream.fileno(), False)
            selector.register(bound_stream, event_mask, name)
        os.set_blocking(stdin.fileno(), False)
        if stdin_open:
            registered_streams["stdin"] = stdin
            selector.register(stdin, selectors.EVENT_WRITE, "stdin")
        else:
            stdin.close()
            stdin_open = False

        while True:
            now = time.monotonic()
            process_alive = process.poll() is None
            if not process_alive:
                if cleanup_deadline is None:
                    cleanup_deadline = now + limits.teardown_seconds
                deadline = cleanup_deadline
                if now >= cleanup_deadline:
                    raise GraderInfrastructureError("trusted grader pipes did not close")
            if process_alive and now >= deadline:
                if not started:
                    raise GraderInfrastructureError("grader startup timed out")
                if terminal:
                    raise GraderInfrastructureError("grader teardown timed out")
                enforced = LimitKind.WALL
            if process_alive and enforced is None and now >= next_sample:
                descendants, rss = _sample_process_tree(process.pid)
                recorded_descendants.update(descendants)
                if not terminal:
                    if len(descendants) >= limits.process_headroom:
                        enforced = LimitKind.PROCESSES
                    elif rss >= limits.aggregate_rss_bytes:
                        enforced = LimitKind.MEMORY
                next_sample = now + DESCENDANT_SAMPLE_SECONDS
            if enforced is not None:
                # A sampled process tree can disappear between the sample and
                # this branch.  A dead trusted process is infrastructure, not
                # a candidate resource outcome.
                if process.poll() is not None:
                    enforced = None
                else:
                    cleanup_started = True
                    cleanup_deadline = _ensure_cleanup_deadline(cleanup_deadline, limits.teardown_seconds)
                    terminated = _terminate_and_reap(process, recorded_descendants, cleanup_deadline)
                    if not terminated:
                        raise GraderInfrastructureError("trusted grader exited during limit enforcement")
                    if not started:
                        raise GraderInfrastructureError("sandbox limit before grader start")
                    return GraderNativeResult(None, enforced)

            timeout = (
                max(0.0, deadline - now)
                if not process_alive
                else max(0.0, min(deadline - now, max(0.0, next_sample - now)))
            )
            ready_events = selector.select(timeout)
            for selected_key, mask in ready_events:
                stream_name = selected_key.data
                if not isinstance(stream_name, str):
                    raise GraderInfrastructureError("selector returned an unknown stream")
                ready_stream = registered_streams.get(stream_name)
                if ready_stream is None:
                    raise GraderInfrastructureError("selector returned an unknown stream")
                if stream_name == "stdin" and mask & selectors.EVENT_WRITE:
                    try:
                        written = os.write(ready_stream.fileno(), input_bytes[input_offset:])
                    except (BlockingIOError, InterruptedError):
                        continue
                    except BrokenPipeError:
                        selector.unregister(ready_stream)
                        ready_stream.close()
                        stdin_open = False
                        continue
                    if written <= 0:
                        raise GraderInfrastructureError("grader input write failed")
                    input_offset += written
                    if input_offset >= len(input_bytes):
                        selector.unregister(ready_stream)
                        ready_stream.close()
                        stdin_open = False
                elif stream_name in ("stdout", "stderr") and mask & selectors.EVENT_READ:
                    try:
                        chunk = os.read(ready_stream.fileno(), 64 * 1024)
                    except (BlockingIOError, InterruptedError):
                        continue
                    if not chunk:
                        selector.unregister(ready_stream)
                        ready_stream.close()
                        continue
                    if stream_name == "stdout":
                        if len(output) + len(chunk) > limits.protocol_bytes:
                            raise GraderInfrastructureError("grader protocol exceeds its size limit")
                        output.extend(chunk)
                        try:
                            frames = parser.feed(chunk)
                        except ProtocolError as exc:
                            raise GraderInfrastructureError("invalid grader protocol") from exc
                        for frame in frames:
                            if frame.frame_type is FrameType.START:
                                if started:
                                    raise GraderInfrastructureError("duplicate grader start")
                                started = True
                                deadline = time.monotonic() + limits.candidate_wall_seconds
                            elif frame.frame_type in (FrameType.RESULT, FrameType.ERROR):
                                terminal = True
                                terminal_deadline = time.monotonic() + limits.teardown_seconds
                                cleanup_deadline = (
                                    terminal_deadline
                                    if cleanup_deadline is None
                                    else min(cleanup_deadline, terminal_deadline)
                                )
                                deadline = cleanup_deadline
                    else:
                        if len(diagnostics) + len(chunk) > limits.diagnostic_bytes:
                            raise GraderInfrastructureError("grader diagnostics exceed its size limit")
                        diagnostics.extend(chunk)

            if process.poll() is not None and not selector.get_map():
                break
            # A process that closed stdout/stderr but left stdin registered is
            # not allowed to keep the host loop alive forever.
            if process.poll() is not None and stdin_open:
                selector.unregister(stdin)
                stdin.close()
                stdin_open = False
            if process.poll() is not None and not any(item.data != "stdin" for item in selector.get_map().values()):
                break
        try:
            parser.finish()
        except ProtocolError as exc:
            raise GraderInfrastructureError("invalid grader protocol") from exc
        if process.returncode != 0:
            raise GraderInfrastructureError("trusted grader exited unexpectedly")
        result = parse_grader_output(bytes(output), key)
        cleanup_started = True
        cleanup_deadline = _ensure_cleanup_deadline(cleanup_deadline, limits.teardown_seconds)
        _wait_for_cleanup(process, recorded_descendants, cleanup_deadline)
        return result
    except GraderInfrastructureError:
        if not cleanup_started:
            cleanup_started = True
            cleanup_deadline = _ensure_cleanup_deadline(cleanup_deadline, limits.teardown_seconds)
            _terminate_and_reap(process, recorded_descendants, cleanup_deadline)
        raise
    except Exception as exc:
        if not cleanup_started:
            cleanup_started = True
            cleanup_deadline = _ensure_cleanup_deadline(cleanup_deadline, limits.teardown_seconds)
            _terminate_and_reap(process, recorded_descendants, cleanup_deadline)
        raise GraderInfrastructureError("sandbox I/O failed") from exc
    finally:
        if selector is not None:
            selector.close()
        for stream in (stdin, stdout, stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass


def _validate_input_size(input_bytes: bytes, limits: GraderSandboxLimits) -> None:
    """Apply the payload-sized stdin limit while retaining BCBI framing bytes."""

    max_input_frame = limits.stdin_bytes + INPUT_FIXED_BYTES
    if type(input_bytes) is not bytes or len(input_bytes) > max_input_frame:
        raise GraderInfrastructureError("grader input exceeds its size limit")


def parse_grader_output(data: bytes, key: bytes) -> GraderNativeResult:
    """Authenticate a complete stream and map its terminal outcome.

    Native signal names are translated only after the authenticated RESULT has
    passed the protocol state machine.  Protocol, ERROR, and START-only
    streams are infrastructure failures and never become candidate scores.
    """

    try:
        frame = parse_authenticated_output(data, key)
    except ProtocolError as exc:
        raise GraderInfrastructureError("invalid grader protocol") from exc
    if frame.frame_type is FrameType.ERROR:
        raise GraderInfrastructureError("grader reported an infrastructure error")
    if frame.native_status is not None:
        return GraderNativeResult(frame.native_status)
    if frame.native_signal is NativeSignal.SIGXCPU:
        return GraderNativeResult(None, LimitKind.CPU)
    if frame.native_signal is NativeSignal.SIGXFSZ:
        return GraderNativeResult(None, LimitKind.FILE_SIZE)
    raise GraderInfrastructureError("grader result has no native outcome")


def preflight_bigcodebench_sandbox(spec: GraderSandboxSpec) -> GraderSandboxPreflight:
    """Fail closed until manifest, identity and namespace probes are bound."""

    del spec
    raise NotImplementedError("BigCodeBench sandbox attestation is not implemented in this batch")


def run_bigcodebench_sandbox(
    request: BigCodeBenchGradeRequest,
    *,
    spec: GraderSandboxSpec,
    preflight: GraderSandboxPreflight,
) -> GraderNativeResult:
    """Fail closed until the attested public launch seam is implemented."""

    del request, spec, preflight
    raise NotImplementedError("BigCodeBench sandbox launch is not implemented in this batch")


__all__ = [
    "BigCodeBenchGradeRequest",
    "GraderInfrastructureError",
    "GraderNativeResult",
    "GraderSandboxLimits",
    "GraderSandboxPreflight",
    "GraderSandboxSpec",
    "LimitKind",
    "NativeSignal",
    "NativeStatus",
    "POLICY_REVISION",
    "PRODUCTION_GRADER_LIMITS",
    "preflight_bigcodebench_sandbox",
    "parse_grader_output",
    "run_bigcodebench_sandbox",
]
