# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host-side policy, attestation and bounded process infrastructure.

The public entry points in this module are the only supported BigCodeBench
launch seam.  They bind the immutable policy manifest and the measured
namespace probe to one typed spec before handing an already-authenticated
request to the bounded supervisor below.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import platform
import selectors
import secrets
import signal
import socket
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final, Iterator, Mapping, Sequence, cast

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
    KEY_SIZE,
    encode_bcbi,
    parse_authenticated_output,
)


POLICY_REVISION: Final[str] = "bigcodebench-bwrap-v1"
BUBBLEWRAP_VERSION: Final[str] = "0.12.0"
RUNNER_GUEST_PATH: Final[str] = "/opt/bigcodebench/bigcodebench_runner.py"
VENDOR_GUEST_PATH: Final[str] = "/opt/bigcodebench/vendor"
NLTK_DATA_GUEST_PATH: Final[str] = "/opt/bigcodebench/nltk_data"
LOCK_PATH_TEMPLATE: Final[str] = "/tmp/nemo-gym-bigcodebench-grader-{uid}.lock"
DESCENDANT_SAMPLE_SECONDS: Final[float] = 0.025
SETUP_ROOT_ENV: Final[str] = "BIGCODEBENCH_GRADER_SETUP_ROOT"
SETUP_RUNTIME_DIR: Final[str] = "pr04-bigcodebench-runtime"
SETUP_RESOURCE_DIR: Final[str] = "pr04-bigcodebench-resources"
SETUP_VENV_DIR: Final[str] = "pr04-bigcodebench-venv"
SETUP_PREFIX_DIR: Final[str] = "pr04-cpython-3.11.16+20260901"
SETUP_BWRAP_DIR: Final[str] = "pr04-bwrap-0.12.0"

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


def _prepared_setup_layout() -> dict[str, Path]:
    """Resolve the one trusted provisioning root and its fixed children."""

    raw_root = os.environ.get(SETUP_ROOT_ENV)
    if not isinstance(raw_root, str) or not raw_root:
        raise GraderInfrastructureError("BigCodeBench setup root is unavailable")
    root = Path(raw_root)
    if not root.is_absolute():
        raise GraderInfrastructureError("BigCodeBench setup root is not absolute")
    try:
        resolved_root = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GraderInfrastructureError("BigCodeBench setup root is unavailable") from exc
    if resolved_root != root or root.is_symlink() or not root.is_dir():
        raise GraderInfrastructureError("BigCodeBench setup root is not a physical directory")
    layout = {
        "root": root,
        "runtime": root / SETUP_RUNTIME_DIR,
        "runtime_manifest": root / SETUP_RUNTIME_DIR / _RUNTIME_MANIFEST_NAME,
        "resource": root / SETUP_RESOURCE_DIR,
        "venv": root / SETUP_VENV_DIR,
        "prefix": root / SETUP_PREFIX_DIR,
        "bwrap": root / SETUP_BWRAP_DIR / "bin" / "bwrap",
    }
    for name, path in layout.items():
        if name in {"root", "runtime_manifest"}:
            continue
        try:
            if path.resolve(strict=True) != path or path.is_symlink():
                raise GraderInfrastructureError("BigCodeBench setup layout is not physical")
        except (OSError, RuntimeError) as exc:
            raise GraderInfrastructureError("BigCodeBench setup layout is incomplete") from exc
    if not layout["runtime_manifest"].is_file() or layout["runtime_manifest"].is_symlink():
        raise GraderInfrastructureError("BigCodeBench runtime manifest is unavailable")
    return layout


def resolve_bigcodebench_resource_dir() -> Path:
    """Return the provisioned resource root after validating its fixed layout."""

    layout = _prepared_setup_layout()
    values = load_canonical_manifest(layout["runtime_manifest"])
    resolved = _mapping(values.get("resolved_paths"), "runtime paths")
    expected = {
        "resource_dir": layout["resource"],
        "grader_venv": layout["venv"],
        "base_prefix": layout["prefix"],
        "nltk_data": layout["resource"] / "nltk_data",
        "bwrap": layout["bwrap"],
    }
    for name, path in expected.items():
        value = resolved.get(name)
        if not isinstance(value, str) or _real_path(Path(value), f"runtime {name}") != path:
            raise GraderInfrastructureError("BigCodeBench runtime paths are stale")
    return layout["resource"]


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


def canonical_json_bytes(value: object, *, final_newline: bool = False) -> bytes:
    """Encode one trusted JSON value with the PR04 canonical JSON rules."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as exc:
        raise GraderInfrastructureError("canonical JSON is invalid") from exc
    return encoded + (b"\n" if final_newline else b"")


def _hash_regular_file(path: Path, metadata: os.stat_result) -> str:
    if metadata.st_nlink != 1:
        raise GraderInfrastructureError("inventory contains a hard-linked regular file")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_nlink) != (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_nlink,
            ):
                raise GraderInfrastructureError("inventory file changed during hashing")
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            closed = os.fstat(stream.fileno())
    except GraderInfrastructureError:
        raise
    except (OSError, UnicodeError) as exc:
        raise GraderInfrastructureError("inventory file is unreadable") from exc
    if (closed.st_dev, closed.st_ino, closed.st_size, closed.st_nlink) != (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_nlink,
    ):
        raise GraderInfrastructureError("inventory file changed during hashing")
    return digest.hexdigest()


def _inventory_entries(root: Path, *, excluded_paths: frozenset[str] = frozenset()) -> tuple[dict[str, object], ...]:
    """Build the exact file/symlink inventory used by trusted manifests."""

    try:
        root_metadata = os.lstat(root)
    except OSError as exc:
        raise GraderInfrastructureError("inventory root is unavailable") from exc
    if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode):
        raise GraderInfrastructureError("inventory root is not a directory")
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GraderInfrastructureError("inventory root cannot be resolved") from exc

    entries: list[dict[str, object]] = []

    def visit(directory: Path) -> None:
        try:
            children = sorted(directory.iterdir(), key=lambda child: child.name)
        except (OSError, UnicodeError) as exc:
            raise GraderInfrastructureError("inventory directory is unreadable") from exc
        for child in children:
            relative = child.relative_to(root).as_posix()
            if relative in excluded_paths:
                continue
            try:
                metadata = os.lstat(child)
            except FileNotFoundError:
                raise GraderInfrastructureError("inventory changed during enumeration") from None
            except OSError as exc:
                raise GraderInfrastructureError("inventory entry is unavailable") from exc
            mode = metadata.st_mode
            if stat.S_ISDIR(mode):
                visit(child)
            elif stat.S_ISREG(mode):
                entries.append(
                    {
                        "path": relative,
                        "type": "file",
                        "mode": stat.S_IMODE(mode),
                        "size": metadata.st_size,
                        "sha256": _hash_regular_file(child, metadata),
                    }
                )
            elif stat.S_ISLNK(mode):
                try:
                    target = os.readlink(child)
                    target.encode("utf-8")
                    if os.path.isabs(target):
                        raise ValueError("absolute symlink")
                    resolved_target = (child.parent / target).resolve(strict=True)
                except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
                    raise GraderInfrastructureError("inventory symlink is unsafe") from exc
                if not resolved_target.is_relative_to(root):
                    raise GraderInfrastructureError("inventory symlink escapes root")
                entries.append({"path": relative, "type": "symlink", "target": target})
            else:
                raise GraderInfrastructureError("inventory contains a special file")

    visit(root)
    return tuple(sorted(entries, key=lambda entry: cast(str, entry["path"])))


def canonical_file_inventory(root: Path, *, excluded_paths: frozenset[str] = frozenset()) -> bytes:
    """Return the no-final-newline canonical inventory bytes for ``root``."""

    return canonical_json_bytes(list(_inventory_entries(root, excluded_paths=excluded_paths)))


def file_inventory_sha256(root: Path, *, excluded_paths: frozenset[str] = frozenset()) -> str:
    """Return the SHA-256 digest of a trusted tree's canonical inventory."""

    return hashlib.sha256(canonical_file_inventory(root, excluded_paths=excluded_paths)).hexdigest()


def load_canonical_manifest(path: Path, *, final_newline: bool = True) -> dict[str, object]:
    """Read one canonical JSON object and reject noncanonical or nonobject data."""

    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise GraderInfrastructureError("manifest is unreadable") from exc
    if not isinstance(value, dict):
        raise GraderInfrastructureError("manifest is not a JSON object")
    if canonical_json_bytes(value, final_newline=final_newline) != raw:
        raise GraderInfrastructureError("manifest is not canonical")
    return cast(dict[str, object], value)


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
    forbidden = tuple(_real_path(root, "forbidden root", must_exist=False) for root in spec.forbidden_roots)
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


def _build_bwrap_command(
    spec: GraderSandboxSpec,
    *,
    process_limit: int | None = None,
    program: Sequence[str] | None = None,
) -> tuple[str, ...]:
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
    if program is None:
        command.extend(("--chdir", "/tmp/work", str(spec.grader_python.resolve()), "-I", "-B", RUNNER_GUEST_PATH))
    else:
        if not program or any(type(item) is not str or not item for item in program):
            raise GraderInfrastructureError("sandbox probe command is invalid")
        command.extend(("--chdir", "/tmp/work", *program))
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
                    cleanup_deadline = min(deadline, now + limits.teardown_seconds)
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


_RUNTIME_MANIFEST_NAME: Final[str] = "runtime-manifest.json"
_ACCEPTED_MANIFEST_NAME: Final[str] = "grader-manifest.json"
_CANDIDATE_MANIFEST_NAME: Final[str] = "grader-manifest.candidate.json"
_PROBE_OUTPUT_BYTES: Final[int] = 16 * 1024
_ATTESTATION_CACHE: dict[tuple[str, str], tuple[str, dict[str, object]]] = {}


def _sha256_file(path: Path) -> str:
    """Hash one immutable regular file while checking its identity."""

    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise GraderInfrastructureError("trusted file is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise GraderInfrastructureError("trusted file is not regular")
    return _hash_regular_file(path, metadata)


def _manifest_digest(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise GraderInfrastructureError("manifest is unreadable") from exc
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise GraderInfrastructureError(f"{field} is invalid")
    return cast(Mapping[str, object], value)


def _manifest_file(spec: GraderSandboxSpec, paths: _ResolvedSandboxPaths) -> tuple[Path, dict[str, object]]:
    resource_dir = _real_path(spec.resource_dir, "resource directory")
    if spec.manifest_path is None:
        path = resource_dir / _ACCEPTED_MANIFEST_NAME
        accepted = True
    else:
        path = _real_path(spec.manifest_path, "manifest")
        accepted = path.name == _ACCEPTED_MANIFEST_NAME
        if path.name != _CANDIDATE_MANIFEST_NAME and not accepted:
            raise GraderInfrastructureError("manifest path is not an approved policy file")
    if not path.is_relative_to(resource_dir) or path.is_symlink() or not path.is_file():
        raise GraderInfrastructureError("manifest is outside the resource root")
    manifest = load_canonical_manifest(path)
    if manifest.get("schema_version") != 1 or manifest.get("policy_revision") != POLICY_REVISION:
        raise GraderInfrastructureError("manifest schema or policy revision is invalid")
    role = manifest.get("manifest_role")
    eligible = manifest.get("acceptance_eligible")
    audit = manifest.get("dependency_audit_state")
    if accepted:
        if role == "functional-boundary-candidate" or eligible is not True or audit not in {"clean", "passed"}:
            raise GraderInfrastructureError("accepted manifest is not eligible")
    else:
        if (
            path != resource_dir / _CANDIDATE_MANIFEST_NAME
            or role != "functional-boundary-candidate"
            or eligible is not False
            or audit != "blocked"
        ):
            raise GraderInfrastructureError("candidate manifest role is invalid")
    del paths
    return path, manifest


def _content_inventory_digest(root: Path) -> str:
    entries: list[dict[str, object]] = []
    for entry in _inventory_entries(root):
        if entry.get("type") != "file":
            raise GraderInfrastructureError("data inventory contains a non-file")
        entries.append({key: entry[key] for key in ("path", "sha256", "size")})
    return hashlib.sha256(canonical_json_bytes(entries)).hexdigest()


def _runtime_manifest(resource_dir: Path) -> tuple[Path, dict[str, object]] | None:
    """Load the one manifest rooted at the explicitly trusted resource root."""

    try:
        layout = _prepared_setup_layout()
    except GraderInfrastructureError:
        return None
    if layout["resource"] != resource_dir:
        raise GraderInfrastructureError("runtime resource is not the trusted prepared root")
    candidate = layout["runtime_manifest"]
    return candidate, load_canonical_manifest(candidate)


def _verify_runtime_manifest(
    runtime: tuple[Path, dict[str, object]] | None,
    *,
    resource_dir: Path,
    manifest_digest: str,
    paths: _ResolvedSandboxPaths,
    bwrap_path: Path,
) -> None:
    if runtime is None:
        raise GraderInfrastructureError("runtime manifest is unavailable")
    _, values = runtime
    if values.get("schema_version") != 1 or values.get("manifest_role") != "functional-boundary-candidate":
        raise GraderInfrastructureError("runtime manifest schema is invalid")
    if values.get("acceptance_eligible") is not False or values.get("dependency_audit_state") != "blocked":
        raise GraderInfrastructureError("runtime manifest eligibility is invalid")
    if values.get("policy_manifest_sha256") != manifest_digest:
        raise GraderInfrastructureError("runtime manifest policy identity is stale")
    candidate_manifest_digest = values.get("candidate_manifest_sha256")
    if candidate_manifest_digest != manifest_digest:
        raise GraderInfrastructureError("runtime candidate identity is stale")
    for field in (
        "bubblewrap_sha256",
        "build_package_record_sha256",
        "candidate_manifest_sha256",
        "grader_lock_sha256",
        "nltk_content_inventory_sha256",
        "nltk_data_full_inventory_sha256",
        "policy_manifest_sha256",
        "prefix_inventory_sha256",
        "grader_venv_inventory_sha256",
        "resource_inventory_sha256",
        "runner_bootstrap_sha256",
        "python_executable_sha256",
    ):
        if not isinstance(values.get(field), str) or len(cast(str, values[field])) != 64:
            raise GraderInfrastructureError("runtime manifest identity is incomplete")
    resolved = _mapping(values.get("resolved_paths"), "runtime paths")
    expected_paths = {
        "resource_dir": resource_dir,
        "grader_venv": paths.venv,
        "base_prefix": paths.base_prefix,
        "nltk_data": paths.nltk_data,
        "bwrap": bwrap_path,
    }
    for name, expected in expected_paths.items():
        actual = resolved.get(name)
        if not isinstance(actual, str):
            raise GraderInfrastructureError("runtime path identity is invalid")
        if expected is not None and _real_path(Path(actual), f"runtime {name}") != expected:
            raise GraderInfrastructureError("runtime path identity is stale")
    runtime_resource = values.get("resource_dir")
    if not isinstance(runtime_resource, str) or _real_path(Path(runtime_resource), "runtime resource") != resource_dir:
        raise GraderInfrastructureError("runtime resource identity is stale")
    if values.get("bubblewrap_path") != resolved.get("bwrap"):
        raise GraderInfrastructureError("runtime bubblewrap identity is stale")

    expected_resource_inventory = values.get("resource_inventory_sha256")
    resource_inventory = values.get("resource_inventory")
    if (
        not isinstance(expected_resource_inventory, str)
        or not isinstance(resource_inventory, list)
        or canonical_file_inventory(resource_dir) != canonical_json_bytes(resource_inventory)
        or file_inventory_sha256(resource_dir) != expected_resource_inventory
    ):
        raise GraderInfrastructureError("runtime inventory identity is stale")
    for field, root in (
        ("grader_venv_inventory_sha256", paths.venv),
        ("prefix_inventory_sha256", paths.base_prefix),
        ("nltk_data_full_inventory_sha256", paths.nltk_data),
    ):
        expected = values.get(field)
        inventory_name = field.removesuffix("_sha256")
        inventory = values.get(inventory_name)
        if (
            not isinstance(expected, str)
            or not isinstance(inventory, list)
            or canonical_file_inventory(root) != canonical_json_bytes(inventory)
            or file_inventory_sha256(root) != expected
        ):
            raise GraderInfrastructureError("runtime inventory identity is stale")
    expected_content = values.get("nltk_content_inventory_sha256")
    content_inventory = values.get("nltk_content_inventory")
    if (
        not isinstance(expected_content, str)
        or not isinstance(content_inventory, list)
        or hashlib.sha256(canonical_json_bytes(content_inventory)).hexdigest() != expected_content
        or _content_inventory_digest(paths.nltk_data) != expected_content
    ):
        raise GraderInfrastructureError("runtime data identity is stale")


def _verify_manifest_identities(
    manifest: Mapping[str, object],
    *,
    manifest_digest: str,
    paths: _ResolvedSandboxPaths,
    bwrap_path: Path,
    runtime_values: Mapping[str, object],
) -> dict[str, object]:
    """Recalculate all source identities that are observable at run time."""

    runner_digest = _sha256_file(paths.runner)
    bootstrap_digest = _sha256_file(Path(__file__).with_name("bigcodebench_sitecustomize.py"))
    expected_runner = manifest.get("runner_sha256")
    expected_bootstrap = manifest.get("bootstrap_sha256")
    if expected_runner != runner_digest or expected_bootstrap != bootstrap_digest:
        raise GraderInfrastructureError("grader source identity is stale")

    python_artifact = _mapping(manifest.get("python_artifact"), "Python policy")
    expected_python = python_artifact.get("executable_sha256")
    if not isinstance(expected_python, str):
        raise GraderInfrastructureError("Python policy is incomplete")
    python_digest = _sha256_file(paths.venv / "bin" / "python")
    if python_digest != expected_python:
        raise GraderInfrastructureError("grader interpreter identity is stale")

    expected_bwrap = runtime_values.get("bubblewrap_sha256")
    if not isinstance(expected_bwrap, str) or _sha256_file(bwrap_path) != expected_bwrap:
        raise GraderInfrastructureError("bubblewrap identity is stale")
    runtime_bootstrap = runtime_values.get("runner_bootstrap_sha256")
    if not isinstance(runtime_bootstrap, str) or runtime_bootstrap != bootstrap_digest:
        raise GraderInfrastructureError("installed bootstrap identity is stale")

    vendor_policy = _mapping(manifest.get("vendor_sha256"), "vendor policy")
    expected_vendor_paths = {
        "LICENSE",
        "VENDORING.md",
        "eval/__init__.py",
        "eval/_special_oracle.py",
        "eval/utils.py",
    }
    if set(vendor_policy) != expected_vendor_paths:
        raise GraderInfrastructureError("vendor policy is incomplete")
    vendor_root = paths.vendor / "bigcodebench"
    actual_vendor: dict[str, str] = {}
    for relative, expected in vendor_policy.items():
        if not isinstance(expected, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise GraderInfrastructureError("vendor policy is invalid")
        source = vendor_root / relative
        actual_vendor[relative] = _sha256_file(source)
        if actual_vendor[relative] != expected:
            raise GraderInfrastructureError("vendored grader identity is stale")

    nltk_policy = _mapping(manifest.get("nltk_data"), "NLTK policy")
    package_ids = nltk_policy.get("package_ids")
    expected_ids = {
        "averaged_perceptron_tagger",
        "averaged_perceptron_tagger_eng",
        "punkt",
        "punkt_tab",
        "stopwords",
        "vader_lexicon",
        "words",
    }
    if not isinstance(package_ids, list) or set(package_ids) != expected_ids or len(package_ids) != len(expected_ids):
        raise GraderInfrastructureError("NLTK package policy is invalid")
    content_digest = _content_inventory_digest(paths.nltk_data)
    if nltk_policy.get("prepared_tree_sha256") != content_digest:
        raise GraderInfrastructureError("NLTK content identity is stale")
    full_digest = file_inventory_sha256(paths.nltk_data)
    bwrap_digest = _sha256_file(bwrap_path)
    return {
        "manifest_sha256": manifest_digest,
        "runner_sha256": runner_digest,
        "bootstrap_sha256": bootstrap_digest,
        "vendor_sha256": actual_vendor,
        "nltk_content_inventory_sha256": content_digest,
        "nltk_data_full_inventory_sha256": full_digest,
        "bubblewrap_sha256": bwrap_digest,
        "python_executable_sha256": python_digest,
        "bubblewrap_sha256": expected_bwrap,
    }


def _spec_payload(
    spec: GraderSandboxSpec,
    *,
    paths: _ResolvedSandboxPaths,
    manifest_path: Path,
) -> dict[str, object]:
    limits = spec.limits
    return {
        "policy_revision": POLICY_REVISION,
        "manifest_path": str(manifest_path),
        "resource_dir": str(_real_path(spec.resource_dir, "resource directory")),
        "bwrap_path": str(_real_path(spec.bwrap_path, "bubblewrap executable")),
        "grader_python": str(_real_path(spec.grader_python, "grader interpreter")),
        "venv": str(paths.venv),
        "base_prefix": str(paths.base_prefix),
        "runner": str(paths.runner),
        "vendor": str(paths.vendor),
        "nltk_data": str(paths.nltk_data),
        "sandbox_etc": str(paths.sandbox_etc),
        "forbidden_roots": sorted(
            str(_real_path(root, "forbidden root", must_exist=False)) for root in spec.forbidden_roots
        ),
        "limits": {
            "startup_seconds": limits.startup_seconds,
            "candidate_wall_seconds": limits.candidate_wall_seconds,
            "teardown_seconds": limits.teardown_seconds,
            "cpu_soft_seconds": limits.cpu_soft_seconds,
            "cpu_hard_seconds": limits.cpu_hard_seconds,
            "address_space_bytes": limits.address_space_bytes,
            "data_bytes": limits.data_bytes,
            "aggregate_rss_bytes": limits.aggregate_rss_bytes,
            "stack_bytes": limits.stack_bytes,
            "file_bytes": limits.file_bytes,
            "open_files": limits.open_files,
            "process_headroom": limits.process_headroom,
            "tmp_bytes": limits.tmp_bytes,
            "shm_bytes": limits.shm_bytes,
            "stdin_bytes": limits.stdin_bytes,
            "protocol_bytes": limits.protocol_bytes,
            "diagnostic_bytes": limits.diagnostic_bytes,
        },
    }


def _digest_attestation(spec_digest: str, manifest_digest: str, facts: Mapping[str, object]) -> str:
    payload = {
        "schema_version": 1,
        "spec_sha256": spec_digest,
        "manifest_sha256": manifest_digest,
        "probe_facts": facts,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


_PROBE_SOURCE: Final[str] = r"""
import ctypes
import json
import os
import platform
import resource
import socket
import sys
import sysconfig

_SECRET_KEY = __PR04_SECRET_KEY__
_SENTINEL = __PR04_SENTINEL__
_IPV4 = __PR04_IPV4__
_IPV6 = __PR04_IPV6__
_UNIX = __PR04_UNIX__
_EXPECTED = __PR04_LIMITS__


def _caps():
    rows = {}
    with open("/proc/self/status", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith(("NoNewPrivs:", "CapInh:", "CapPrm:", "CapEff:", "CapAmb:")):
                fields = line.split()
                if len(fields) == 2:
                    rows[fields[0]] = fields[1]
    return rows


def _write(path, data=b"probe"):
    try:
        with open(path, "wb") as stream:
            stream.write(data)
        return True
    except OSError:
        return False


def _connect(address, family):
    if not address:
        return False
    try:
        with socket.socket(family, socket.SOCK_STREAM) as client:
            client.settimeout(0.15)
            client.connect(address)
        return True
    except OSError:
        return False


def _mounts():
    mounts = {}
    with open("/proc/self/mountinfo", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            left, separator, right = line.rstrip("\n").partition(" - ")
            fields = left.split()
            if not separator or len(fields) < 6:
                continue
            mount_point = fields[4]
            mounts[mount_point] = {
                "readonly": "rw" not in fields[5].split(","),
                "filesystem": right.split()[0] if right.split() else "",
            }
    return mounts


def _nested_userns_disabled():
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        return libc.unshare(0x10000000) != 0
    except (AttributeError, OSError):
        return False


def _rlimits():
    names = {
        "cpu": resource.RLIMIT_CPU,
        "as": resource.RLIMIT_AS,
        "data": resource.RLIMIT_DATA,
        "stack": resource.RLIMIT_STACK,
        "fsize": resource.RLIMIT_FSIZE,
        "nofile": resource.RLIMIT_NOFILE,
        "core": resource.RLIMIT_CORE,
        "nproc": resource.RLIMIT_NPROC,
    }
    result = {}
    for name, limit_id in names.items():
        try:
            result[name] = list(resource.getrlimit(limit_id))
        except (OSError, ValueError):
            result[name] = None
    return result


def _install_limits():
    names = {
        "cpu": resource.RLIMIT_CPU,
        "as": resource.RLIMIT_AS,
        "data": resource.RLIMIT_DATA,
        "stack": resource.RLIMIT_STACK,
        "fsize": resource.RLIMIT_FSIZE,
        "nofile": resource.RLIMIT_NOFILE,
        "core": resource.RLIMIT_CORE,
        "nproc": resource.RLIMIT_NPROC,
    }
    for name, bound in _EXPECTED.items():
        try:
            resource.setrlimit(names[name], tuple(bound))
            if list(resource.getrlimit(names[name])) != list(bound):
                return False
        except (OSError, ValueError, KeyError):
            return False
    return True


def _nltk_facts():
    import nltk

    package_paths = {
        "averaged_perceptron_tagger": "taggers/averaged_perceptron_tagger",
        "averaged_perceptron_tagger_eng": "taggers/averaged_perceptron_tagger_eng",
        "punkt": "tokenizers/punkt",
        "punkt_tab": "tokenizers/punkt_tab",
        "stopwords": "corpora/stopwords",
        "vader_lexicon": "sentiment/vader_lexicon.zip",
        "words": "corpora/words",
    }
    statuses = {}
    for name, path in package_paths.items():
        try:
            nltk.data.find(path)
            statuses[name] = True
        except LookupError:
            statuses[name] = False
    try:
        lookup_ok = bool(nltk.corpus.stopwords.words("english"))
    except (LookupError, OSError):
        lookup_ok = False
    downloader = __import__("nltk.downloader", fromlist=["_downloader"])._downloader
    return {
        "path": list(nltk.data.path),
        "url": downloader._url,
        "download_dir": downloader.download_dir,
        "statuses": statuses,
        "lookup": lookup_ok,
    }


def _main():
    limits_ok = _install_limits()
    namespaces = {name: os.stat("/proc/self/ns/" + name).st_ino for name in ("mnt", "user", "pid", "net", "ipc", "uts")}
    mounts = _mounts()
    tmp_path = "/tmp/work/.bcb-preflight"
    tmp_ok = _write(tmp_path)
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    try:
        sentinel_visible = os.path.exists(_SENTINEL)
        sentinel_write = _write(_SENTINEL)
    except OSError:
        sentinel_visible = True
        sentinel_write = True
    try:
        fds = [int(name) for name in os.listdir("/proc/self/fd") if name.isdecimal()]
    except OSError:
        fds = [-1]
    facts = {
        "system": platform.system(),
        "machine": platform.machine(),
        "os_release": {
            "id": next((line.split("=", 1)[1].strip('"') for line in open("/etc/os-release", encoding="utf-8", errors="replace") if line.startswith("ID=")), ""),
            "version_id": next((line.split("=", 1)[1].strip('"') for line in open("/etc/os-release", encoding="utf-8", errors="replace") if line.startswith("VERSION_ID=")), ""),
        },
        "namespaces": namespaces,
        "caps": _caps(),
        "nested_userns_disabled": _nested_userns_disabled(),
        "pid_is_one": os.getpid() == 1,
        "mounts": mounts,
        "root_write": _write("/.bcb-preflight"),
        "dev_write": _write("/dev/.bcb-preflight"),
        "usr_write": _write("/usr/.bcb-preflight"),
        "opt_write": _write("/opt/.bcb-preflight"),
        "tmp_write": tmp_ok,
        "sentinel_visible": sentinel_visible,
        "sentinel_write": sentinel_write,
        "secret_absent": _SECRET_KEY not in os.environ,
        "extra_fds": any(fd > 2 for fd in fds),
        "isolated": bool(sys.flags.isolated and sys.flags.no_user_site),
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "soabi": sysconfig.get_config_var("SOABI"),
        "listener_ipv4": _connect(_IPV4, socket.AF_INET),
        "listener_ipv6": _connect(_IPV6, socket.AF_INET6),
        "listener_unix": _connect(_UNIX, socket.AF_UNIX),
        "limits_ok": limits_ok,
        "rlimits": _rlimits(),
        "nltk": _nltk_facts(),
    }
    print(json.dumps(facts, sort_keys=True, separators=(",", ":")))


_main()
"""


def _run_bounded_probe(command: Sequence[str], timeout: float, output_limit: int) -> bytes:
    """Capture one trusted probe with bounded nonblocking I/O and cleanup."""

    try:
        process = subprocess.Popen(
            tuple(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            close_fds=True,
            pass_fds=(),
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        raise GraderInfrastructureError("sandbox policy probe failed") from exc
    stdout = process.stdout
    stderr = process.stderr
    if stdout is None or stderr is None:
        process.kill()
        process.wait(timeout=max(0.1, timeout))
        raise GraderInfrastructureError("sandbox policy probe pipes are unavailable")
    selector = selectors.DefaultSelector()
    output = bytearray()
    streams: dict[int, IO[bytes]] = {stdout.fileno(): stdout, stderr.fileno(): stderr}
    try:
        for stream in (stdout, stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                try:
                    if process.poll() is None:
                        process.kill()
                finally:
                    process.wait(timeout=max(0.1, timeout))
                raise GraderInfrastructureError("sandbox policy probe timed out")
            for selected_key, _ in selector.select(remaining):
                stream = streams.get(selected_key.fd)
                if stream is None:
                    raise GraderInfrastructureError("sandbox policy probe stream is invalid")
                try:
                    chunk = os.read(stream.fileno(), 64 * 1024)
                except (BlockingIOError, InterruptedError):
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if stream is stdout:
                    if len(output) + len(chunk) > output_limit:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=max(0.1, timeout))
                        raise GraderInfrastructureError("sandbox policy probe output is too large")
                    output.extend(chunk)
        if process.wait(timeout=max(0.1, deadline - time.monotonic())) != 0:
            raise GraderInfrastructureError("sandbox policy probe failed")
        return bytes(output)
    except GraderInfrastructureError:
        raise
    except (OSError, subprocess.TimeoutExpired) as exc:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=max(0.1, timeout))
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise GraderInfrastructureError("sandbox policy probe failed") from exc
    finally:
        selector.close()
        for stream in (stdout, stderr):
            try:
                stream.close()
            except OSError:
                pass


def _run_policy_probe(spec: GraderSandboxSpec, paths: _ResolvedSandboxPaths) -> dict[str, object]:
    namespace_names = ("mnt", "user", "pid", "net", "ipc", "uts")
    try:
        parent_namespaces = {name: os.stat(f"/proc/self/ns/{name}").st_ino for name in namespace_names}
    except OSError as exc:
        raise GraderInfrastructureError("host namespace probe is unavailable") from exc

    probe_temp = tempfile.mkdtemp(prefix="pr04-bcb-probe-", dir="/tmp")
    sentinel = Path(probe_temp) / "outside-sentinel"
    try:
        sentinel.write_bytes(b"sentinel")
        ipv4_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ipv4_socket.bind(("127.0.0.1", 0))
        ipv4_socket.listen(1)
        ipv4 = ipv4_socket.getsockname()
    except OSError as exc:
        raise GraderInfrastructureError("sandbox listener probe is unavailable") from exc
    ipv6_socket: socket.socket | None = None
    ipv6: tuple[str, int, int, int] | None = None
    try:
        try:
            ipv6_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            ipv6_socket.bind(("::1", 0))
            ipv6_socket.listen(1)
            ipv6 = ipv6_socket.getsockname()
        except OSError:
            if ipv6_socket is not None:
                ipv6_socket.close()
                ipv6_socket = None
        unix_path = Path(probe_temp) / "listener.sock"
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        unix_socket.bind(str(unix_path))
        unix_socket.listen(1)
        secret_key = f"PR04_PROBE_{secrets.token_hex(8)}"
        previous_secret = os.environ.get(secret_key)
        os.environ[secret_key] = secrets.token_hex(16)
        process_limit = _count_real_uid_processes() + spec.limits.process_headroom
        expected_limits = {
            "cpu": [spec.limits.cpu_soft_seconds, spec.limits.cpu_hard_seconds],
            "as": [spec.limits.address_space_bytes, spec.limits.address_space_bytes],
            "data": [spec.limits.data_bytes, spec.limits.data_bytes],
            "stack": [spec.limits.stack_bytes, spec.limits.stack_bytes],
            "fsize": [spec.limits.file_bytes, spec.limits.file_bytes],
            "nofile": [spec.limits.open_files, spec.limits.open_files],
            "core": [0, 0],
            "nproc": [process_limit, process_limit],
        }
        source = (
            _PROBE_SOURCE.replace("__PR04_SECRET_KEY__", repr(secret_key))
            .replace("__PR04_SENTINEL__", repr(str(sentinel)))
            .replace("__PR04_IPV4__", repr(ipv4))
            .replace("__PR04_IPV6__", repr(ipv6))
            .replace("__PR04_UNIX__", repr(str(unix_path)))
            .replace("__PR04_LIMITS__", repr(expected_limits))
        )
        program = (str(spec.grader_python), "-I", "-B", "-c", source)
        command = _build_bwrap_command(spec, process_limit=process_limit, program=program)
        output = _run_bounded_probe(command, max(1.0, min(20.0, spec.limits.startup_seconds)), _PROBE_OUTPUT_BYTES)
        finally:
            if previous_secret is None:
                os.environ.pop(secret_key, None)
            else:
                os.environ[secret_key] = previous_secret
        try:
            facts_value = json.loads(output.decode("utf-8", errors="replace"))
        except (UnicodeError, ValueError) as exc:
            raise GraderInfrastructureError("sandbox probe returned invalid facts") from exc
    finally:
        unix_socket.close()
        if ipv6_socket is not None:
            ipv6_socket.close()
        ipv4_socket.close()
        shutil.rmtree(probe_temp, ignore_errors=True)

    facts = _mapping(facts_value, "sandbox probe facts")
    if facts.get("system") != "Linux" or facts.get("machine") != "x86_64":
        raise GraderInfrastructureError("sandbox platform identity is invalid")
    os_release = _mapping(facts.get("os_release"), "sandbox operating system")
    if os_release.get("id") != "ubuntu" or os_release.get("version_id") != "24.04":
        raise GraderInfrastructureError("sandbox operating system identity is invalid")
    namespaces = _mapping(facts.get("namespaces"), "sandbox namespaces")
    for name, parent in parent_namespaces.items():
        child = namespaces.get(name)
        if type(child) is not int or child == parent:
            raise GraderInfrastructureError("sandbox namespace isolation is unavailable")
    caps = _mapping(facts.get("caps"), "sandbox capabilities")
    if caps.get("NoNewPrivs:") != "1" or any(
        caps.get(name) != "0000000000000000" for name in ("CapInh:", "CapPrm:", "CapEff:", "CapAmb:")
    ):
        raise GraderInfrastructureError("sandbox capability isolation is unavailable")
    if facts.get("nested_userns_disabled") is not True or facts.get("pid_is_one") is not True:
        raise GraderInfrastructureError("sandbox nested namespace policy is unavailable")
    if any(facts.get(name) is not False for name in ("root_write", "dev_write", "usr_write", "opt_write")):
        raise GraderInfrastructureError("sandbox read-only mount policy is invalid")
    if facts.get("tmp_write") is not True or facts.get("sentinel_visible") is not False or facts.get("sentinel_write") is not False:
        raise GraderInfrastructureError("sandbox writable-root policy is invalid")
    if facts.get("secret_absent") is not True or facts.get("extra_fds") is not False:
        raise GraderInfrastructureError("sandbox environment or descriptor policy is invalid")
    if facts.get("isolated") is not True or facts.get("prefix") != str(paths.venv):
        raise GraderInfrastructureError("sandbox interpreter isolation is invalid")
    if facts.get("listener_ipv4") is not False or facts.get("listener_ipv6") is not False or facts.get("listener_unix") is not False:
        raise GraderInfrastructureError("sandbox network isolation is unavailable")
    rlimits = _mapping(facts.get("rlimits"), "sandbox resource limits")
    for name, expected in expected_limits.items():
        observed = rlimits.get(name)
        if observed != expected:
            raise GraderInfrastructureError("sandbox resource limits are not active")
    mounts = _mapping(facts.get("mounts"), "sandbox mount facts")
    for path in ("/", "/dev", "/usr", VENDOR_GUEST_PATH, NLTK_DATA_GUEST_PATH):
        mount = _mapping(mounts.get(path), f"sandbox mount {path}")
        if mount.get("readonly") is not True:
            raise GraderInfrastructureError("sandbox read-only mounts are incomplete")
    for path in ("/tmp", "/dev/shm"):
        if not isinstance(mounts.get(path), dict):
            raise GraderInfrastructureError("sandbox scratch mounts are incomplete")
    nltk = _mapping(facts.get("nltk"), "sandbox NLTK facts")
    if (
        nltk.get("path") != [NLTK_DATA_GUEST_PATH]
        or nltk.get("url") != "file:///opt/bigcodebench/nltk_data/index.xml"
        or nltk.get("download_dir") != NLTK_DATA_GUEST_PATH
        or nltk.get("lookup") is not True
    ):
        raise GraderInfrastructureError("sandbox NLTK bootstrap is invalid")
    statuses = _mapping(nltk.get("statuses"), "sandbox NLTK package statuses")
    expected_ids = {
        "averaged_perceptron_tagger",
        "averaged_perceptron_tagger_eng",
        "punkt",
        "punkt_tab",
        "stopwords",
        "vader_lexicon",
        "words",
    }
    if set(statuses) != expected_ids or any(statuses.get(name) is not True for name in expected_ids):
        raise GraderInfrastructureError("sandbox NLTK package set is incomplete")
    return dict(facts)


def _bwrap_version(path: Path) -> str:
    try:
        completed = subprocess.run(
            (str(path), "--version"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GraderInfrastructureError("bubblewrap version is unavailable") from exc
    if completed.returncode != 0 or len(completed.stdout) > 4096:
        raise GraderInfrastructureError("bubblewrap version is unavailable")
    output = completed.stdout.decode("utf-8", errors="replace").strip()
    tokens = output.split()
    if len(tokens) < 2 or tokens[0] != "bubblewrap" or tokens[1] != BUBBLEWRAP_VERSION:
        raise GraderInfrastructureError("bubblewrap version is not pinned")
    return BUBBLEWRAP_VERSION


def _verify_bwrap_metadata(path: Path) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise GraderInfrastructureError("bubblewrap metadata is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(metadata.st_mode) != 0o755
        or metadata.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise GraderInfrastructureError("bubblewrap metadata is unsafe")
    try:
        completed = subprocess.run(
            ("getcap", str(path)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GraderInfrastructureError("bubblewrap capabilities are unavailable") from exc
    if completed.returncode not in {0, 1} or completed.stdout.strip():
        raise GraderInfrastructureError("bubblewrap capabilities are present")


def resolve_bigcodebench_sandbox_spec(
    resource_dir: Path,
    *,
    forbidden_roots: tuple[Path, ...] = (),
) -> GraderSandboxSpec:
    """Resolve an installed runtime manifest without creating or mutating it."""

    resource = _real_path(resource_dir, "resource directory")
    layout = _prepared_setup_layout()
    if resource != layout["resource"]:
        raise GraderInfrastructureError("resource directory is not the trusted prepared root")
    runtime = _runtime_manifest(resource)
    if runtime is None:
        raise GraderInfrastructureError("installed grader runtime manifest is unavailable")
    _, values = runtime
    resolved = _mapping(values.get("resolved_paths"), "runtime paths")
    runtime_resource = resolved.get("resource_dir")
    bwrap_value = resolved.get("bwrap")
    venv_value = resolved.get("grader_venv")
    if not isinstance(runtime_resource, str) or not isinstance(bwrap_value, str) or not isinstance(venv_value, str):
        raise GraderInfrastructureError("installed grader runtime paths are invalid")
    if _real_path(Path(runtime_resource), "runtime resource") != resource:
        raise GraderInfrastructureError("installed grader runtime resource is stale")
    venv = _real_path(Path(venv_value), "grader virtual environment")
    if not isinstance(forbidden_roots, tuple):
        raise GraderInfrastructureError("forbidden roots are invalid")
    return GraderSandboxSpec(
        resource_dir=resource,
        bwrap_path=_real_path(Path(bwrap_value), "bubblewrap executable"),
        grader_python=_real_path(venv / "bin" / "python", "grader interpreter"),
        forbidden_roots=forbidden_roots,
    )


def sandbox_provenance(preflight: GraderSandboxPreflight) -> dict[str, object]:
    """Return durable, independent provenance for a successful sandbox run."""

    if not isinstance(preflight, GraderSandboxPreflight) or not preflight.ok:
        raise GraderInfrastructureError("sandbox provenance requires successful preflight")
    if any(
        not isinstance(value, str) or not value
        for value in (preflight.sandbox_version, preflight.spec_sha256, preflight.manifest_sha256, preflight.attestation_sha256)
    ):
        raise GraderInfrastructureError("sandbox provenance is incomplete")
    return {
        "policy_revision": preflight.policy_revision,
        "sandbox_version": preflight.sandbox_version,
        "spec_sha256": preflight.spec_sha256,
        "manifest_sha256": preflight.manifest_sha256,
        "attestation_sha256": preflight.attestation_sha256,
        "lock_path": LOCK_PATH_TEMPLATE.format(uid=os.getuid()),
        "lock_scope": "exclusive-real-uid-grader-launch",
    }


def preflight_bigcodebench_sandbox(spec: GraderSandboxSpec) -> GraderSandboxPreflight:
    """Run the real policy probe and bind its facts to the exact spec."""

    sandbox_version: str | None = None
    try:
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            raise GraderInfrastructureError("Ubuntu Linux x86-64 is required")
        paths = _resolve_sandbox_paths(spec)
        bwrap_path = _real_path(spec.bwrap_path, "bubblewrap executable")
        manifest_path, manifest = _manifest_file(spec, paths)
        manifest_digest = _manifest_digest(manifest_path)
        resource_dir = _real_path(spec.resource_dir, "resource directory")
        runtime = _runtime_manifest(resource_dir)
        if runtime is None:
            raise GraderInfrastructureError("runtime manifest is unavailable")
        _verify_runtime_manifest(
            runtime,
            resource_dir=resource_dir,
            manifest_digest=manifest_digest,
            paths=paths,
            bwrap_path=bwrap_path,
        )
        identities = _verify_manifest_identities(
            manifest,
            manifest_digest=manifest_digest,
            paths=paths,
            bwrap_path=bwrap_path,
            runtime_values=runtime[1],
        )
        if manifest_path.name == _ACCEPTED_MANIFEST_NAME and spec.limits != PRODUCTION_GRADER_LIMITS:
            raise GraderInfrastructureError("accepted manifest requires production limits")
        # Version and metadata commands are executions of a trusted binary, so
        # all file identities are checked before either command is allowed.
        _verify_bwrap_metadata(bwrap_path)
        sandbox_version = _bwrap_version(bwrap_path)
        with _exclusive_grader_lock():
            facts = _run_policy_probe(spec, paths)
        facts["identities"] = identities
        facts["bubblewrap_version"] = sandbox_version
        payload = _spec_payload(spec, paths=paths, manifest_path=manifest_path)
        spec_digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        attestation_digest = _digest_attestation(spec_digest, manifest_digest, facts)
        _ATTESTATION_CACHE[(spec_digest, manifest_digest)] = (attestation_digest, facts)
        return GraderSandboxPreflight(
            ok=True,
            sandbox_version=sandbox_version,
            policy_revision=POLICY_REVISION,
            spec_sha256=spec_digest,
            manifest_sha256=manifest_digest,
            attestation_sha256=attestation_digest,
            details=("sandbox policy probe passed", "manifest and runtime identities are current"),
        )
    except GraderInfrastructureError as exc:
        return GraderSandboxPreflight(
            ok=False,
            sandbox_version=sandbox_version,
            policy_revision=POLICY_REVISION,
            spec_sha256=None,
            manifest_sha256=None,
            attestation_sha256=None,
            details=(str(exc),),
        )


def run_bigcodebench_sandbox(
    request: BigCodeBenchGradeRequest,
    *,
    spec: GraderSandboxSpec,
    preflight: GraderSandboxPreflight,
) -> GraderNativeResult:
    """Run one request, returning only an authenticated native outcome."""

    if not isinstance(preflight, GraderSandboxPreflight) or preflight.ok is not True:
        raise GraderInfrastructureError("successful sandbox preflight is required")
    if preflight.policy_revision != POLICY_REVISION:
        raise GraderInfrastructureError("sandbox policy revision is stale")
    with _exclusive_grader_lock():
        # The lock covers every run-time observation, request encoding, command
        # construction and child launch.  A preflight can never be reused
        # across a concurrent identity change.
        paths = _resolve_sandbox_paths(spec)
        manifest_path, manifest = _manifest_file(spec, paths)
        manifest_digest = _manifest_digest(manifest_path)
        spec_digest = hashlib.sha256(
            canonical_json_bytes(_spec_payload(spec, paths=paths, manifest_path=manifest_path))
        ).hexdigest()
        if preflight.spec_sha256 != spec_digest or preflight.manifest_sha256 != manifest_digest:
            raise GraderInfrastructureError("sandbox attestation is stale")
        cached = _ATTESTATION_CACHE.get((spec_digest, manifest_digest))
        if cached is None or cached[0] != preflight.attestation_sha256:
            raise GraderInfrastructureError("sandbox attestation is not trusted")
        resource_dir = _real_path(spec.resource_dir, "resource directory")
        runtime = _runtime_manifest(resource_dir)
        if runtime is None:
            raise GraderInfrastructureError("runtime manifest is unavailable")
        bwrap_path = _real_path(spec.bwrap_path, "bubblewrap executable")
        _verify_runtime_manifest(
            runtime,
            resource_dir=resource_dir,
            manifest_digest=manifest_digest,
            paths=paths,
            bwrap_path=bwrap_path,
        )
        identities = _verify_manifest_identities(
            manifest,
            manifest_digest=manifest_digest,
            paths=paths,
            bwrap_path=bwrap_path,
            runtime_values=runtime[1],
        )
        cached_identities = _mapping(cached[1].get("identities"), "cached identities")
        if dict(cached_identities) != identities:
            raise GraderInfrastructureError("sandbox identities changed since preflight")
        if manifest_path.name == _ACCEPTED_MANIFEST_NAME and spec.limits != PRODUCTION_GRADER_LIMITS:
            raise GraderInfrastructureError("accepted manifest requires production limits")
        key = secrets.token_bytes(KEY_SIZE)
        try:
            input_bytes = encode_bcbi(request, key)
        except ProtocolError as exc:
            raise GraderInfrastructureError("grader request is invalid") from exc
        command = _build_bwrap_command(spec)
        return _run_bounded_supervisor(command, input_bytes, key, spec.limits)


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
    "resolve_bigcodebench_resource_dir",
    "resolve_bigcodebench_sandbox_spec",
    "sandbox_provenance",
    "parse_grader_output",
    "run_bigcodebench_sandbox",
]
