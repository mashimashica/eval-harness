# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pure protocol coverage for the isolated BigCodeBench runner boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from eval_harness.bigcodebench_runner import (
    OUTPUT_FRAME_OVERHEAD,
    OUTPUT_HEADER_SIZE,
    AuthenticatedOutputParser,
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
from eval_harness.grader_sandbox import (
    PRODUCTION_GRADER_LIMITS,
    GraderSandboxLimits,
    GraderSandboxPreflight,
    GraderSandboxSpec,
)


KEY = bytes(range(32))


def request() -> BigCodeBenchGradeRequest:
    return BigCodeBenchGradeRequest(
        schema_version=1,
        code="def answer(x):\n    return x + 1\n",
        test_code="assert answer(1) == 2\n",
        entry_point="answer",
        task_id="task-001",
    )


def input_with_payload(key: bytes, payload: bytes) -> bytes:
    return b"BCBI" + b"\x01" + len(payload).to_bytes(4, "big") + key + payload


def frame_with_body(key: bytes, sequence: int, frame_type: FrameType, body: bytes) -> bytes:
    header = b"BCBO" + bytes((1, sequence, int(frame_type))) + len(body).to_bytes(4, "big")
    tag = hmac.new(key, header + body, hashlib.sha256).digest()
    return header + tag + body


def test_public_types_are_frozen_and_have_contract_defaults() -> None:
    limits = GraderSandboxLimits()
    assert limits == PRODUCTION_GRADER_LIMITS
    assert limits.protocol_bytes == 16 * 1024
    assert limits.diagnostic_bytes == 32 * 1024
    spec = GraderSandboxSpec(Path("resources"), Path("bwrap"), Path("python"))
    assert spec.manifest_path is None
    with pytest.raises((AttributeError, TypeError)):
        limits.protocol_bytes = 1  # type: ignore[misc]

    preflight = GraderSandboxPreflight(False, None, "policy-v1", None, None, None, ("missing",))
    assert preflight.details == ("missing",)


def test_bcbi_round_trip_is_canonical_and_bounded() -> None:
    encoded = encode_bcbi(request(), KEY)
    decoded_key, decoded_request = decode_bcbi(encoded)
    assert decoded_key == KEY
    assert decoded_request == request()
    assert encoded.endswith(
        json.dumps(request().as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    )

    with pytest.raises(ProtocolError):
        encode_bcbi(request(), b"short")
    with pytest.raises(ProtocolError):
        BigCodeBenchGradeRequest(1, "x" * (2 * 1024 * 1024 + 1), "", "entry", "task")
    with pytest.raises(ProtocolError):
        BigCodeBenchGradeRequest(1, "", "", "", "task")


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema_version":1,"code":"","test_code":"","entry_point":"answer","task_id":"t","task_id":"t"}',
        b'{"code":"","entry_point":"answer","schema_version":1,"task_id":"t","test_code":"","extra":0}',
        b'{"schema_version":1,"code":"","test_code":"","entry_point":"answer","task_id":"t"} trailing',
        b'{"schema_version":1,"code":"\xff","test_code":"","entry_point":"answer","task_id":"t"}',
    ],
)
def test_bcbi_rejects_duplicate_unknown_noncanonical_and_invalid_utf8(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_bcbi(input_with_payload(KEY, payload))


def test_bcbi_rejects_truncation_and_trailing_bytes() -> None:
    encoded = encode_bcbi(request(), KEY)
    with pytest.raises(ProtocolError):
        decode_bcbi(encoded[:-1])
    with pytest.raises(ProtocolError):
        decode_bcbi(encoded + b"x")


def test_bcbo_hmac_and_partial_feed() -> None:
    stream = encode_start(KEY) + encode_result(KEY, NativeStatus.PASS)
    parser = AuthenticatedOutputParser(KEY)
    frames = []
    for byte in stream:
        frames.extend(parser.feed(bytes((byte,))))
    result = parser.finish()
    assert [frame.frame_type for frame in frames] == [FrameType.START, FrameType.RESULT]
    assert result.native_status is NativeStatus.PASS
    assert result.native_signal is None
    assert parse_authenticated_output(stream, KEY) == result

    tampered = bytearray(stream)
    tampered[-1] ^= 1
    with pytest.raises(ProtocolError, match="authentication"):
        parse_authenticated_output(bytes(tampered), KEY)


def test_bcbo_signal_union_and_authenticated_error() -> None:
    signal_frame = encode_start(KEY) + encode_signal(KEY, NativeSignal.SIGXCPU)
    parsed = parse_authenticated_output(signal_frame, KEY)
    assert parsed.native_status is None
    assert parsed.native_signal is NativeSignal.SIGXCPU

    error = parse_authenticated_output(encode_error(KEY, "input_invalid", 0), KEY)
    assert error.frame_type is FrameType.ERROR
    assert error.error_code == "input_invalid"

    with pytest.raises(ProtocolError):
        encode_bcbo(
            KEY,
            1,
            FrameType.RESULT,
            {"schema_version": 1, "native_status": "pass", "native_signal": "sigxcpu"},
        )
    with pytest.raises(ProtocolError):
        encode_bcbo(KEY, 1, FrameType.RESULT, {"schema_version": 1, "native_signal": "SIGXCPU"})
    with pytest.raises(ProtocolError):
        GraderNativeResult(NativeStatus.PASS, LimitKind.CPU)
    assert GraderNativeResult(None, LimitKind.CPU).limit_kind is LimitKind.CPU


def test_bcbo_rejects_invalid_sequences_duplicates_and_trailing_data() -> None:
    with pytest.raises(ProtocolError):
        parse_authenticated_output(encode_result(KEY, "pass", sequence=0), KEY)
    with pytest.raises(ProtocolError):
        parse_authenticated_output(encode_start(KEY) + encode_start(KEY), KEY)
    with pytest.raises(ProtocolError):
        parse_authenticated_output(encode_start(KEY) + encode_result(KEY, "pass") + b"x", KEY)
    with pytest.raises(ProtocolError):
        parse_authenticated_output(encode_start(KEY)[:-1], KEY)


def test_bcbo_rejects_duplicate_unknown_and_noncanonical_body_keys() -> None:
    duplicate = b'{"schema_version":1,"error_code":"input_invalid","error_code":"runner_internal"}'
    unknown = b'{"schema_version":1,"error_code":"input_invalid","detail":"x"}'
    noncanonical = b'{ "schema_version": 1, "error_code": "input_invalid" }'
    for body in (duplicate, unknown, noncanonical):
        with pytest.raises(ProtocolError):
            parse_authenticated_output(frame_with_body(KEY, 0, FrameType.ERROR, body), KEY)


def test_bcbo_enforces_protocol_byte_bound() -> None:
    # A body can be valid JSON yet exceed the fixed frame budget.
    frame = encode_error(KEY, "runner_internal", 0)
    assert len(frame) <= OUTPUT_FRAME_OVERHEAD + 64
    assert OUTPUT_HEADER_SIZE < OUTPUT_FRAME_OVERHEAD
    oversized = b"{" + b"a" * 20_000 + b"}"
    with pytest.raises(ProtocolError):
        parse_authenticated_output(frame_with_body(KEY, 0, FrameType.ERROR, oversized), KEY)
