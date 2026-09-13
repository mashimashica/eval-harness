# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The credential-free BigCodeBench runner protocol.

This module intentionally contains only the standard library.  The later
runner implementation is executed as a standalone file in an isolated
namespace, while the host uses the codec and parser below to authenticate its
output.  Keeping the protocol here prevents the isolated process from
importing host evaluator code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Any, Callable, Final, Mapping, Sequence, cast


PROTOCOL_VERSION: Final[int] = 1
INPUT_MAGIC: Final[bytes] = b"BCBI"
OUTPUT_MAGIC: Final[bytes] = b"BCBO"
KEY_SIZE: Final[int] = 32
INPUT_LENGTH_BYTES: Final[int] = 4
OUTPUT_LENGTH_BYTES: Final[int] = 4
HMAC_SIZE: Final[int] = hashlib.sha256().digest_size
OUTPUT_HEADER_SIZE: Final[int] = 4 + 1 + 1 + 1 + OUTPUT_LENGTH_BYTES
OUTPUT_FRAME_OVERHEAD: Final[int] = OUTPUT_HEADER_SIZE + HMAC_SIZE

# These are protocol bounds, rather than evaluator policy limits.  The input
# limit includes the request JSON but not the fixed BCBI header and key.  The
# output limit covers every byte emitted by the runner, including framing.
MAX_INPUT_PAYLOAD_BYTES: Final[int] = 8 * 1024 * 1024
MAX_CODE_BYTES: Final[int] = 2 * 1024 * 1024
MAX_TEST_CODE_BYTES: Final[int] = 6 * 1024 * 1024
MAX_IDENTIFIER_BYTES: Final[int] = 256
MAX_OUTPUT_BYTES: Final[int] = 16 * 1024
MAX_OUTPUT_BODY_BYTES: Final[int] = MAX_OUTPUT_BYTES - OUTPUT_FRAME_OVERHEAD
INPUT_FIXED_BYTES: Final[int] = len(INPUT_MAGIC) + 1 + INPUT_LENGTH_BYTES + KEY_SIZE
MAX_INPUT_FRAME_BYTES: Final[int] = INPUT_FIXED_BYTES + MAX_INPUT_PAYLOAD_BYTES
VENDOR_ROOT: Final[str] = "/opt/bigcodebench/vendor"
NATIVE_AS_LIMIT_MIB: Final[int] = 8192
NATIVE_DATA_LIMIT_MIB: Final[int] = 6144
NATIVE_STACK_LIMIT_MIB: Final[int] = 10

ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "input_invalid",
        "fd_setup_failed",
        "native_setup_failed",
        "native_start_failed",
        "native_contract_invalid",
        "runner_internal",
    }
)


class ProtocolError(ValueError):
    """A malformed, non-canonical, or unauthenticated protocol value."""


class NativeStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    TIMEOUT = "timeout"


class NativeSignal(StrEnum):
    SIGXCPU = "sigxcpu"
    SIGXFSZ = "sigxfsz"


class LimitKind(StrEnum):
    WALL = "wall"
    CPU = "cpu"
    MEMORY = "memory"
    PROCESSES = "processes"
    FILE_SIZE = "file_size"


class FrameType(IntEnum):
    START = 1
    RESULT = 2
    ERROR = 3


def _protocol_error(message: str) -> ProtocolError:
    """Build a deliberately secret-free protocol error."""

    return ProtocolError(message)


def _require_exact_int(value: object, field: str) -> int:
    if type(value) is not int:
        raise _protocol_error(f"{field} must be an integer")
    return value


def _require_string(
    value: object,
    field: str,
    maximum: int,
    *,
    nonempty: bool = False,
    forbid_nul: bool = False,
) -> str:
    if type(value) is not str:
        raise _protocol_error(f"{field} must be a string")
    string = value
    if nonempty and not string:
        raise _protocol_error(f"{field} must not be empty")
    if forbid_nul and "\x00" in string:
        raise _protocol_error(f"{field} contains a forbidden character")
    try:
        encoded = string.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _protocol_error(f"{field} is not valid UTF-8") from exc
    if len(encoded) > maximum:
        raise _protocol_error(f"{field} exceeds its size limit")
    return string


@dataclass(frozen=True, slots=True)
class BigCodeBenchGradeRequest:
    """The exact typed request carried by a BCBI input frame."""

    schema_version: int
    code: str
    test_code: str
    entry_point: str
    task_id: str

    def __post_init__(self) -> None:
        if _require_exact_int(self.schema_version, "schema_version") != PROTOCOL_VERSION:
            raise _protocol_error("unsupported schema version")
        _require_string(self.code, "code", MAX_CODE_BYTES)
        _require_string(self.test_code, "test_code", MAX_TEST_CODE_BYTES)
        _require_string(self.entry_point, "entry_point", MAX_IDENTIFIER_BYTES, nonempty=True, forbid_nul=True)
        _require_string(self.task_id, "task_id", MAX_IDENTIFIER_BYTES, nonempty=True, forbid_nul=True)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "test_code": self.test_code,
            "entry_point": self.entry_point,
            "task_id": self.task_id,
        }


@dataclass(frozen=True, slots=True)
class GraderNativeResult:
    """The authenticated native outcome or a host-observed limit outcome."""

    native_status: NativeStatus | None
    limit_kind: LimitKind | None = None

    def __post_init__(self) -> None:
        status = self.native_status
        limit = self.limit_kind
        if status is not None and not isinstance(status, NativeStatus):
            try:
                status = NativeStatus(status)
            except (TypeError, ValueError) as exc:
                raise _protocol_error("invalid native status") from exc
            object.__setattr__(self, "native_status", status)
        if limit is not None and not isinstance(limit, LimitKind):
            try:
                limit = LimitKind(limit)
            except (TypeError, ValueError) as exc:
                raise _protocol_error("invalid limit kind") from exc
            object.__setattr__(self, "limit_kind", limit)
        if (status is None) == (limit is None):
            raise _protocol_error("result must contain exactly one outcome")


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError, UnicodeEncodeError) as exc:
        raise _protocol_error("JSON value is not canonical") from exc
    return encoded


def _json_object(raw: bytes, *, context: str, maximum: int) -> dict[str, object]:
    if len(raw) > maximum:
        raise _protocol_error(f"{context} exceeds its size limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _protocol_error(f"{context} is not valid UTF-8") from exc

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _protocol_error(f"{context} contains duplicate keys")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise _protocol_error(f"{context} contains a non-finite number")

    try:
        parsed = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except ProtocolError:
        raise
    except (RecursionError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _protocol_error(f"{context} is not valid JSON") from exc
    if type(parsed) is not dict:
        raise _protocol_error(f"{context} must be a JSON object")
    result = cast(dict[str, object], parsed)
    if _canonical_json_bytes(result) != raw:
        raise _protocol_error(f"{context} is not canonical JSON")
    return result


def _validate_key(key: bytes) -> bytes:
    if type(key) is not bytes or len(key) != KEY_SIZE:
        raise _protocol_error("protocol key has an invalid size")
    return key


def encode_bcbi(request: BigCodeBenchGradeRequest, key: bytes) -> bytes:
    """Encode one complete BCBI request, including its secret key."""

    _validate_key(key)
    if not isinstance(request, BigCodeBenchGradeRequest):
        raise _protocol_error("request has an invalid type")
    body = _canonical_json_bytes(request.as_dict())
    if len(body) > MAX_INPUT_PAYLOAD_BYTES or len(body) > 0xFFFFFFFF:
        raise _protocol_error("input payload exceeds its size limit")
    return INPUT_MAGIC + bytes((PROTOCOL_VERSION,)) + len(body).to_bytes(4, "big") + key + body


def decode_bcbi(data: bytes) -> tuple[bytes, BigCodeBenchGradeRequest]:
    """Decode and strictly validate a complete BCBI request.

    The returned tuple is ``(key, request)``.  The key is retained by the
    runner only for authenticating BCBO output and is never exposed in errors.
    """

    if type(data) is not bytes:
        raise _protocol_error("input frame must be bytes")
    fixed = len(INPUT_MAGIC) + 1 + INPUT_LENGTH_BYTES + KEY_SIZE
    if len(data) < fixed:
        raise _protocol_error("input frame is incomplete")
    if data[:4] != INPUT_MAGIC:
        raise _protocol_error("input frame has an invalid magic")
    if data[4] != PROTOCOL_VERSION:
        raise _protocol_error("input frame has an unsupported version")
    payload_length = int.from_bytes(data[5:9], "big")
    if payload_length > MAX_INPUT_PAYLOAD_BYTES:
        raise _protocol_error("input payload exceeds its size limit")
    expected = fixed + payload_length
    if len(data) != expected:
        raise _protocol_error("input frame has trailing or missing bytes")
    key = data[9 : 9 + KEY_SIZE]
    raw = data[fixed:]
    object_value = _json_object(raw, context="input payload", maximum=MAX_INPUT_PAYLOAD_BYTES)
    expected_keys = {"schema_version", "code", "test_code", "entry_point", "task_id"}
    if set(object_value) != expected_keys:
        raise _protocol_error("input payload has an invalid schema")
    request = BigCodeBenchGradeRequest(
        _require_exact_int(object_value["schema_version"], "schema_version"),
        _require_string(object_value["code"], "code", MAX_CODE_BYTES),
        _require_string(object_value["test_code"], "test_code", MAX_TEST_CODE_BYTES),
        _require_string(
            object_value["entry_point"], "entry_point", MAX_IDENTIFIER_BYTES, nonempty=True, forbid_nul=True
        ),
        _require_string(object_value["task_id"], "task_id", MAX_IDENTIFIER_BYTES, nonempty=True, forbid_nul=True),
    )
    return key, request


def _body_for_frame(frame_type: FrameType, body: Mapping[str, object]) -> bytes:
    if not isinstance(frame_type, FrameType):
        try:
            frame_type = FrameType(frame_type)
        except (TypeError, ValueError) as exc:
            raise _protocol_error("output frame has an unknown type") from exc
    if type(body) is not dict:
        raise _protocol_error("output body must be an object")
    expected_schema = {"schema_version"}
    schema = body.get("schema_version")
    if type(schema) is not int or schema != PROTOCOL_VERSION:
        raise _protocol_error("output body has an invalid schema version")
    if frame_type is FrameType.START:
        expected_schema = {"schema_version"}
    elif frame_type is FrameType.RESULT:
        expected_schema = (
            {"schema_version", "native_status"}
            if "native_status" in body
            else {
                "schema_version",
                "native_signal",
            }
        )
        if "native_status" in body and "native_signal" in body:
            raise _protocol_error("output result contains multiple outcomes")
        if "native_status" in body:
            value = body["native_status"]
            if type(value) is not str or value not in {item.value for item in NativeStatus}:
                raise _protocol_error("output result has an invalid native status")
        elif "native_signal" in body:
            value = body["native_signal"]
            if type(value) is not str or value not in {item.value for item in NativeSignal}:
                raise _protocol_error("output result has an invalid native signal")
        else:
            raise _protocol_error("output result has no outcome")
    elif frame_type is FrameType.ERROR:
        expected_schema = {"schema_version", "error_code"}
        value = body.get("error_code")
        if type(value) is not str or value not in ERROR_CODES:
            raise _protocol_error("output error has an invalid code")
    if set(body) != expected_schema:
        raise _protocol_error("output body has an invalid schema")
    encoded = _canonical_json_bytes(body)
    if len(encoded) > MAX_OUTPUT_BODY_BYTES:
        raise _protocol_error("output body exceeds its size limit")
    return encoded


def encode_bcbo(key: bytes, sequence: int, frame_type: FrameType, body: Mapping[str, object]) -> bytes:
    """Encode and authenticate one canonical BCBO frame."""

    _validate_key(key)
    if type(sequence) is not int or sequence < 0 or sequence > 255:
        raise _protocol_error("output frame has an invalid sequence")
    try:
        frame_type = FrameType(frame_type)
    except (TypeError, ValueError) as exc:
        raise _protocol_error("output frame has an unknown type") from exc
    raw_body = _body_for_frame(frame_type, body)
    if len(raw_body) > 0xFFFFFFFF:
        raise _protocol_error("output body exceeds its size limit")
    header = OUTPUT_MAGIC + bytes((PROTOCOL_VERSION, sequence, int(frame_type))) + len(raw_body).to_bytes(4, "big")
    tag = hmac.new(key, header + raw_body, hashlib.sha256).digest()
    return header + tag + raw_body


def encode_start(key: bytes) -> bytes:
    return encode_bcbo(key, 0, FrameType.START, {"schema_version": PROTOCOL_VERSION})


def encode_result(key: bytes, status: NativeStatus | str, sequence: int = 1) -> bytes:
    try:
        status = NativeStatus(status)
    except (TypeError, ValueError) as exc:
        raise _protocol_error("output result has an invalid native status") from exc
    return encode_bcbo(
        key,
        sequence,
        FrameType.RESULT,
        {"schema_version": PROTOCOL_VERSION, "native_status": status.value},
    )


def encode_signal(key: bytes, signal: NativeSignal | str, sequence: int = 1) -> bytes:
    try:
        signal = NativeSignal(signal)
    except (TypeError, ValueError) as exc:
        raise _protocol_error("output result has an invalid native signal") from exc
    return encode_bcbo(
        key,
        sequence,
        FrameType.RESULT,
        {"schema_version": PROTOCOL_VERSION, "native_signal": signal.value},
    )


def encode_error(key: bytes, error_code: str, sequence: int) -> bytes:
    return encode_bcbo(key, sequence, FrameType.ERROR, {"schema_version": PROTOCOL_VERSION, "error_code": error_code})


@dataclass(frozen=True, slots=True)
class AuthenticatedFrame:
    """A frame whose HMAC, canonical body, and sequence were all verified."""

    sequence: int
    frame_type: FrameType
    body: Mapping[str, object]
    native_status: NativeStatus | None = None
    native_signal: NativeSignal | None = None
    error_code: str | None = None

    @property
    def is_error(self) -> bool:
        return self.frame_type is FrameType.ERROR


def _decode_bcbo_frame(raw: bytes, key: bytes) -> AuthenticatedFrame:
    if len(raw) < OUTPUT_FRAME_OVERHEAD:
        raise _protocol_error("output frame is incomplete")
    if raw[:4] != OUTPUT_MAGIC:
        raise _protocol_error("output frame has an invalid magic")
    if raw[4] != PROTOCOL_VERSION:
        raise _protocol_error("output frame has an unsupported version")
    sequence = raw[5]
    if sequence > 1:
        raise _protocol_error("output frame has an invalid sequence")
    try:
        frame_type = FrameType(raw[6])
    except ValueError as exc:
        raise _protocol_error("output frame has an unknown type") from exc
    body_length = int.from_bytes(raw[7:11], "big")
    if body_length > MAX_OUTPUT_BODY_BYTES:
        raise _protocol_error("output body exceeds its size limit")
    expected = OUTPUT_FRAME_OVERHEAD + body_length
    if len(raw) != expected:
        raise _protocol_error("output frame has an invalid length")
    supplied_tag = raw[OUTPUT_HEADER_SIZE:OUTPUT_FRAME_OVERHEAD]
    body_raw = raw[OUTPUT_FRAME_OVERHEAD:]
    expected_tag = hmac.new(key, raw[:OUTPUT_HEADER_SIZE] + body_raw, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied_tag, expected_tag):
        raise _protocol_error("output frame authentication failed")
    body = _json_object(body_raw, context="output body", maximum=MAX_OUTPUT_BODY_BYTES)
    _body_for_frame(frame_type, body)
    status: NativeStatus | None = None
    signal: NativeSignal | None = None
    error_code: str | None = None
    if frame_type is FrameType.RESULT:
        if "native_status" in body:
            status = NativeStatus(cast(str, body["native_status"]))
        else:
            signal = NativeSignal(cast(str, body["native_signal"]))
    elif frame_type is FrameType.ERROR:
        error_code = cast(str, body["error_code"])
    return AuthenticatedFrame(sequence, frame_type, body, status, signal, error_code)


class AuthenticatedOutputParser:
    """Incrementally authenticate and validate a bounded BCBO stream."""

    def __init__(self, key: bytes) -> None:
        self._key = _validate_key(key)
        self._buffer = bytearray()
        self._received_bytes = 0
        self._complete: AuthenticatedFrame | None = None
        self._expect_start = True

    def _accept(self, frame: AuthenticatedFrame) -> None:
        if self._complete is not None:
            raise _protocol_error("output contains data after its terminal frame")
        if self._expect_start:
            if frame.sequence != 0 or frame.frame_type not in (FrameType.START, FrameType.ERROR):
                raise _protocol_error("output has an invalid initial frame")
            self._expect_start = False
            if frame.frame_type is FrameType.ERROR:
                self._complete = frame
            return
        if frame.sequence != 1 or frame.frame_type not in (FrameType.RESULT, FrameType.ERROR):
            raise _protocol_error("output has an invalid terminal frame")
        self._complete = frame

    def feed(self, chunk: bytes) -> tuple[AuthenticatedFrame, ...]:
        if type(chunk) is not bytes:
            raise _protocol_error("output chunk must be bytes")
        if self._received_bytes + len(chunk) > MAX_OUTPUT_BYTES:
            raise _protocol_error("output exceeds its size limit")
        self._received_bytes += len(chunk)
        if self._complete is not None and chunk:
            raise _protocol_error("output contains trailing data")
        self._buffer.extend(chunk)
        frames: list[AuthenticatedFrame] = []
        while True:
            if len(self._buffer) < OUTPUT_HEADER_SIZE:
                break
            if self._buffer[:4] != OUTPUT_MAGIC:
                raise _protocol_error("output frame has an invalid magic")
            if self._buffer[4] != PROTOCOL_VERSION:
                raise _protocol_error("output frame has an unsupported version")
            body_length = int.from_bytes(self._buffer[7:11], "big")
            if body_length > MAX_OUTPUT_BODY_BYTES:
                raise _protocol_error("output body exceeds its size limit")
            frame_length = OUTPUT_FRAME_OVERHEAD + body_length
            if frame_length > MAX_OUTPUT_BYTES:
                raise _protocol_error("output frame exceeds its size limit")
            if len(self._buffer) < frame_length:
                break
            raw = bytes(self._buffer[:frame_length])
            del self._buffer[:frame_length]
            frame = _decode_bcbo_frame(raw, self._key)
            self._accept(frame)
            frames.append(frame)
        return tuple(frames)

    def finish(self) -> AuthenticatedFrame:
        if self._buffer:
            raise _protocol_error("output ends with an incomplete frame")
        if self._complete is None:
            raise _protocol_error("output has no complete result")
        return self._complete


def parse_authenticated_output(data: bytes, key: bytes) -> AuthenticatedFrame:
    parser = AuthenticatedOutputParser(key)
    parser.feed(data)
    return parser.finish()


class _RunnerFailure(RuntimeError):
    """An internal runner failure whose details never cross the protocol."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "runner_internal",
        input_key: bytes | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.input_key = input_key


@dataclass(frozen=True, slots=True)
class _RunnerLimits:
    cpu_soft_seconds: int
    cpu_hard_seconds: int
    address_space_bytes: int
    data_bytes: int
    stack_bytes: int
    file_bytes: int
    open_files: int
    processes: int


_CLI_LIMIT_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("--cpu-soft-seconds", "cpu_soft_seconds"),
    ("--cpu-hard-seconds", "cpu_hard_seconds"),
    ("--address-space-bytes", "address_space_bytes"),
    ("--data-bytes", "data_bytes"),
    ("--stack-bytes", "stack_bytes"),
    ("--file-bytes", "file_bytes"),
    ("--open-files", "open_files"),
    ("--processes", "processes"),
)


def _parse_runner_limits(argv: Sequence[str]) -> _RunnerLimits:
    expected_count = len(_CLI_LIMIT_FIELDS) * 2
    if len(argv) != expected_count:
        raise _RunnerFailure("invalid runner limits")
    values: dict[str, int] = {}
    for index, (flag, field) in enumerate(_CLI_LIMIT_FIELDS):
        actual_flag = argv[index * 2]
        raw_value = argv[index * 2 + 1]
        if actual_flag != flag or field in values or type(raw_value) is not str:
            raise _RunnerFailure("invalid runner limits")
        if not raw_value.isascii() or not raw_value.isdecimal() or raw_value != str(int(raw_value)):
            raise _RunnerFailure("invalid runner limits")
        value = int(raw_value)
        if value <= 0 or value > (2**63 - 1):
            raise _RunnerFailure("invalid runner limits")
        values[field] = value
    limits = _RunnerLimits(**values)
    if limits.cpu_soft_seconds > limits.cpu_hard_seconds:
        raise _RunnerFailure("invalid runner limits")
    return limits


def _set_dumpability() -> None:
    """Disable ptrace dumpability before consuming any untrusted input."""

    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    if prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE
        raise _RunnerFailure("dumpability setup failed")
    if prctl(3, 0, 0, 0, 0) != 0:  # PR_GET_DUMPABLE
        raise _RunnerFailure("dumpability verification failed")


def _apply_runner_limits(limits: _RunnerLimits) -> None:
    """Install and read back the finite rlimits supplied by trusted argv."""

    import resource

    requested = (
        ("RLIMIT_CPU", (limits.cpu_soft_seconds, limits.cpu_hard_seconds)),
        ("RLIMIT_AS", (limits.address_space_bytes, limits.address_space_bytes)),
        ("RLIMIT_DATA", (limits.data_bytes, limits.data_bytes)),
        ("RLIMIT_STACK", (limits.stack_bytes, limits.stack_bytes)),
        ("RLIMIT_FSIZE", (limits.file_bytes, limits.file_bytes)),
        ("RLIMIT_NOFILE", (limits.open_files, limits.open_files)),
        ("RLIMIT_CORE", (0, 0)),
        ("RLIMIT_NPROC", (limits.processes, limits.processes)),
    )
    for name, bound in requested:
        resource_id = getattr(resource, name, None)
        if resource_id is None:
            raise _RunnerFailure("required resource limit is unavailable")
        try:
            resource.setrlimit(resource_id, bound)
            observed = resource.getrlimit(resource_id)
        except (OSError, ValueError) as exc:
            raise _RunnerFailure("resource limit setup failed") from exc
        if observed != bound:
            raise _RunnerFailure("resource limit verification failed")


def _read_bounded_input() -> bytes:
    """Read exactly one bounded BCBI frame and its terminating EOF."""

    data = bytearray()
    total = 0
    while True:
        remaining = MAX_INPUT_FRAME_BYTES - total
        if remaining < 0:
            raise _RunnerFailure("input exceeds its size limit")
        chunk = os.read(0, min(64 * 1024, remaining + 1))
        if not chunk:
            break
        if total + len(chunk) > MAX_INPUT_FRAME_BYTES:
            data.extend(chunk[: MAX_INPUT_FRAME_BYTES - total])
            raise _RunnerFailure(
                "input exceeds its size limit",
                code="input_invalid",
                input_key=_input_key_if_available(bytes(data)),
            )
        data.extend(chunk)
        total += len(chunk)
    return bytes(data)


def _input_key_if_available(data: bytes) -> bytes | None:
    if len(data) < INPUT_FIXED_BYTES or data[:4] != INPUT_MAGIC or data[4] != PROTOCOL_VERSION:
        return None
    key = data[9 : 9 + KEY_SIZE]
    return key if len(key) == KEY_SIZE else None


def _prepare_output_fd() -> int:
    """Duplicate stdout as a CLOEXEC pipe before native imports."""

    import fcntl
    import stat

    try:
        result_fd = fcntl.fcntl(1, fcntl.F_DUPFD_CLOEXEC, 3)
        if result_fd < 3:
            raise _RunnerFailure("result descriptor setup failed", code="fd_setup_failed")
        descriptor_flags = fcntl.fcntl(result_fd, fcntl.F_GETFD)
        if descriptor_flags & fcntl.FD_CLOEXEC == 0 or not stat.S_ISFIFO(os.fstat(result_fd).st_mode):
            raise _RunnerFailure("result descriptor is not a CLOEXEC pipe", code="fd_setup_failed")
        return result_fd
    except (OSError, ValueError) as exc:
        raise _RunnerFailure("result descriptor setup failed", code="fd_setup_failed") from exc


def _replace_standard_fds() -> None:
    """Replace stdin/stdout/stderr with /dev/null after the input is parsed."""

    null_fd = -1
    try:
        null_fd = os.open(os.devnull, os.O_RDWR | os.O_CLOEXEC)
        if null_fd < 3:
            replacement = os.dup(null_fd)
            os.set_inheritable(replacement, False)
            os.close(null_fd)
            null_fd = replacement
        for descriptor in (0, 1, 2):
            os.dup2(null_fd, descriptor, inheritable=False)
    except OSError as exc:
        raise _RunnerFailure("standard descriptor setup failed", code="fd_setup_failed") from exc
    finally:
        if null_fd >= 0:
            try:
                os.close(null_fd)
            except OSError:
                pass


def _write_frame(result_fd: int, frame: bytes) -> None:
    if len(frame) > MAX_OUTPUT_BYTES:
        raise _RunnerFailure("output exceeds its size limit")
    offset = 0
    while offset < len(frame):
        try:
            written = os.write(result_fd, frame[offset:])
        except OSError as exc:
            raise _RunnerFailure("result descriptor write failed") from exc
        if written <= 0:
            raise _RunnerFailure("result descriptor write failed")
        offset += written


def _close_result_fd(result_fd: int) -> None:
    try:
        os.close(result_fd)
    except OSError:
        pass


def _safe_error(result_fd: int, key: bytes, sequence: int, code: str = "runner_internal") -> None:
    try:
        _write_frame(result_fd, encode_error(key, code, sequence))
    except BaseException:
        pass


def _validate_native_return(value: object) -> NativeStatus:
    if type(value) is not tuple or len(value) != 2:
        raise _RunnerFailure("native result tuple is invalid", code="native_contract_invalid")
    status = value[0]
    if type(status) is not str:
        raise _RunnerFailure("native status is invalid", code="native_contract_invalid")
    try:
        return NativeStatus(status)
    except ValueError as exc:
        raise _RunnerFailure("native status is invalid", code="native_contract_invalid") from exc


def _captured_signal(exitcode: int) -> NativeSignal | None:
    import signal

    if hasattr(signal, "SIGXCPU") and exitcode == -int(signal.SIGXCPU):
        return NativeSignal.SIGXCPU
    if hasattr(signal, "SIGXFSZ") and exitcode == -int(signal.SIGXFSZ):
        return NativeSignal.SIGXFSZ
    return None


def _native_limit_mib(value: int, field: str) -> int:
    mib = 1024 * 1024
    if type(value) is not int or value <= 0 or value % mib != 0:
        raise _RunnerFailure(f"{field} is not a whole MiB", code="native_setup_failed")
    return value // mib


def _run_native(request: BigCodeBenchGradeRequest, key: bytes, result_fd: int, limits: _RunnerLimits) -> bool:
    """Run exactly one vendored native check and emit its authenticated result."""

    started = False
    process_type: Any = None
    original_start: Callable[..., object] | None = None
    try:
        max_as_limit = _native_limit_mib(limits.address_space_bytes, "address-space limit")
        max_data_limit = _native_limit_mib(limits.data_bytes, "data limit")
        max_stack_limit = _native_limit_mib(limits.stack_bytes, "stack limit")
        import multiprocessing

        multiprocessing.set_start_method("spawn", force=True)
        if multiprocessing.get_start_method() != "spawn":
            raise _RunnerFailure("spawn start method verification failed", code="native_setup_failed")
        if VENDOR_ROOT not in sys.path:
            sys.path.insert(0, VENDOR_ROOT)
        import importlib

        native_module = importlib.import_module("bigcodebench.eval")
        unsafe_execute = getattr(native_module, "unsafe_execute", None)
        untrusted_check_object = getattr(native_module, "untrusted_check", None)
        if not callable(unsafe_execute) or not callable(untrusted_check_object):
            raise _RunnerFailure("native entrypoints are unavailable", code="native_setup_failed")
        untrusted_check = cast(Callable[[str, str, str, int, int, int], object], untrusted_check_object)

        process_type = multiprocessing.Process
        original_start = cast(Callable[..., object], process_type.start)
        start_impl = original_start
        captured: list[Any] = []

        def wrapped_start(process: Any, *args: Any, **kwargs: Any) -> object:
            nonlocal started
            if getattr(process, "_target", None) is unsafe_execute:
                if captured:
                    raise _RunnerFailure("multiple native processes were captured", code="native_contract_invalid")
                _write_frame(result_fd, encode_start(key))
                captured.append(process)
                started = True
            try:
                return start_impl(process, *args, **kwargs)
            except _RunnerFailure:
                raise
            except BaseException as exc:
                raise _RunnerFailure("native process start failed", code="native_start_failed") from exc

        setattr(process_type, "start", wrapped_start)
        try:
            native_value = untrusted_check(
                request.code,
                request.test_code,
                request.entry_point,
                max_as_limit,
                max_data_limit,
                max_stack_limit,
            )
        finally:
            if original_start is not None:
                setattr(process_type, "start", original_start)
                original_start = None

        if len(captured) != 1:
            raise _RunnerFailure("native process capture count is invalid", code="native_contract_invalid")
        status = _validate_native_return(native_value)
        process = captured[0]
        exitcode = getattr(process, "exitcode", None)
        if type(exitcode) is not int:
            raise _RunnerFailure("native process exit code is invalid", code="native_contract_invalid")
        signal_name = _captured_signal(exitcode)
        if signal_name is not None:
            _write_frame(result_fd, encode_signal(key, signal_name))
        elif exitcode < 0:
            if status is not NativeStatus.TIMEOUT:
                raise _RunnerFailure("unattributed native signal", code="native_contract_invalid")
            _write_frame(result_fd, encode_result(key, status))
        else:
            _write_frame(result_fd, encode_result(key, status))
        return True
    except _RunnerFailure as exc:
        _safe_error(result_fd, key, 1 if started else 0, exc.code)
        return False
    except BaseException:
        code = "native_contract_invalid" if started else "native_setup_failed"
        _safe_error(result_fd, key, 1 if started else 0, code)
        return False
    finally:
        if process_type is not None and original_start is not None:
            setattr(process_type, "start", original_start)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the trusted in-sandbox native-checker adapter."""

    # Keep this as the first operation: no argument, key, or candidate byte is
    # consumed until Linux has disabled and verified dumpability.
    try:
        _set_dumpability()
    except BaseException:
        return 1

    result_fd: int | None = None
    key: bytes | None = None
    try:
        arguments = tuple(sys.argv[1:] if argv is None else argv)
        limits = _parse_runner_limits(arguments)
        _apply_runner_limits(limits)
        input_bytes = _read_bounded_input()
        key = _input_key_if_available(input_bytes)
        if key is None:
            return 1
        try:
            decoded_key, request = decode_bcbi(input_bytes)
            if decoded_key != key or encode_bcbi(request, decoded_key) != input_bytes:
                raise _RunnerFailure("input canonicality verification failed")
        except (ProtocolError, _RunnerFailure):
            result_fd = _prepare_output_fd()
            _replace_standard_fds()
            _write_frame(result_fd, encode_error(key, "input_invalid", 0))
            return 1
        key = decoded_key
        result_fd = _prepare_output_fd()
        _replace_standard_fds()
        return 0 if _run_native(request, key, result_fd, limits) else 1
    except _RunnerFailure as exc:
        if key is None:
            key = exc.input_key
        if result_fd is None and key is not None and exc.code == "input_invalid":
            try:
                result_fd = _prepare_output_fd()
                _replace_standard_fds()
            except BaseException:
                result_fd = None
        if result_fd is not None and key is not None:
            _safe_error(result_fd, key, 0, exc.code)
        return 1
    except BaseException:
        if result_fd is not None and key is not None:
            _safe_error(result_fd, key, 0)
        return 1
    finally:
        if result_fd is not None:
            _close_result_fd(result_fd)


__all__ = [
    "AuthenticatedFrame",
    "AuthenticatedOutputParser",
    "BigCodeBenchGradeRequest",
    "ERROR_CODES",
    "FrameType",
    "GraderNativeResult",
    "INPUT_MAGIC",
    "KEY_SIZE",
    "LimitKind",
    "MAX_CODE_BYTES",
    "MAX_IDENTIFIER_BYTES",
    "MAX_INPUT_PAYLOAD_BYTES",
    "MAX_OUTPUT_BODY_BYTES",
    "MAX_OUTPUT_BYTES",
    "MAX_TEST_CODE_BYTES",
    "NativeSignal",
    "NativeStatus",
    "PROTOCOL_VERSION",
    "ProtocolError",
    "decode_bcbi",
    "encode_bcbi",
    "encode_error",
    "encode_result",
    "encode_signal",
    "encode_start",
    "main",
    "parse_authenticated_output",
]


if __name__ == "__main__":
    raise SystemExit(main())
