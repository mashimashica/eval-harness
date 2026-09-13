# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Frozen host-side types for the BigCodeBench grader boundary.

Process construction and sandbox enforcement are intentionally added in later
PR04 batches.  The protocol types live in the stdlib-only runner module so the
isolated runner can use them without importing this host module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from eval_harness.bigcodebench_runner import (
    AuthenticatedFrame,
    AuthenticatedOutputParser,
    BCBIError,
    BCBOError,
    BigCodeBenchGradeRequest,
    FrameType,
    GraderNativeResult,
    LimitKind,
    NativeSignal,
    NativeStatus,
    ProtocolError,
    decode_bcbi,
    encode_bcbi,
    encode_bcbo,
    encode_error,
    encode_result,
    encode_signal,
    encode_start,
    parse_authenticated_output,
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


__all__ = [
    "BigCodeBenchGradeRequest",
    "AuthenticatedFrame",
    "AuthenticatedOutputParser",
    "BCBIError",
    "BCBOError",
    "FrameType",
    "GraderInfrastructureError",
    "GraderNativeResult",
    "GraderSandboxLimits",
    "GraderSandboxPreflight",
    "GraderSandboxSpec",
    "LimitKind",
    "NativeSignal",
    "NativeStatus",
    "PRODUCTION_GRADER_LIMITS",
    "ProtocolError",
    "decode_bcbi",
    "encode_bcbi",
    "encode_bcbo",
    "encode_error",
    "encode_result",
    "encode_signal",
    "encode_start",
    "parse_authenticated_output",
    "parse_grader_output",
]
