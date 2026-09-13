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
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Final, Mapping, cast


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
    "parse_authenticated_output",
]
