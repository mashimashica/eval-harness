# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pure protocol coverage for the isolated BigCodeBench runner boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import eval_harness.bigcodebench_runner as runner_module
from eval_harness.bigcodebench_runner import (
    MAX_OUTPUT_BYTES,
    OUTPUT_FRAME_OVERHEAD,
    OUTPUT_HEADER_SIZE,
    AuthenticatedFrame,
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


class TestBigCodeBenchRunner(unittest.TestCase):
    def test_public_types_are_frozen_and_have_contract_defaults(self) -> None:
        limits = GraderSandboxLimits()
        self.assertEqual(limits, PRODUCTION_GRADER_LIMITS)
        self.assertEqual(limits.protocol_bytes, 16 * 1024)
        self.assertEqual(limits.diagnostic_bytes, 32 * 1024)
        spec = GraderSandboxSpec(Path("resources"), Path("bwrap"), Path("python"))
        self.assertIsNone(spec.manifest_path)
        with self.assertRaises((AttributeError, TypeError)):
            setattr(limits, "protocol_bytes", 1)

        preflight = GraderSandboxPreflight(False, None, "policy-v1", None, None, None, ("missing",))
        self.assertEqual(preflight.details, ("missing",))

    def test_bcbi_round_trip_is_canonical_and_bounded(self) -> None:
        encoded = encode_bcbi(request(), KEY)
        decoded_key, decoded_request = decode_bcbi(encoded)
        self.assertEqual(decoded_key, KEY)
        self.assertEqual(decoded_request, request())
        self.assertTrue(
            encoded.endswith(
                json.dumps(request().as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
            )
        )

        with self.assertRaises(ProtocolError):
            encode_bcbi(request(), b"short")
        with self.assertRaises(ProtocolError):
            BigCodeBenchGradeRequest(1, "x" * (2 * 1024 * 1024 + 1), "", "entry", "task")
        with self.assertRaises(ProtocolError):
            BigCodeBenchGradeRequest(1, "", "", "", "task")

        nul_request = BigCodeBenchGradeRequest(1, "before\x00after", "test\x00code", "answer", "task")
        nul_key, decoded_nul_request = decode_bcbi(encode_bcbi(nul_request, KEY))
        self.assertEqual(nul_key, KEY)
        self.assertEqual(decoded_nul_request, nul_request)
        with self.assertRaises(ProtocolError):
            BigCodeBenchGradeRequest(1, "", "", "answer\x00", "task")
        with self.assertRaises(ProtocolError):
            BigCodeBenchGradeRequest(1, "", "", "answer", "task\x00")

    def test_bcbi_rejects_duplicate_unknown_noncanonical_and_invalid_utf8(self) -> None:
        payloads = (
            b'{"schema_version":1,"code":"","test_code":"","entry_point":"answer","task_id":"t","task_id":"t"}',
            b'{"code":"","entry_point":"answer","schema_version":1,"task_id":"t","test_code":"","extra":0}',
            b'{"schema_version":1,"code":"","test_code":"","entry_point":"answer","task_id":"t"} trailing',
            b'{"schema_version":1,"code":"\xff","test_code":"","entry_point":"answer","task_id":"t"}',
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ProtocolError):
                    decode_bcbi(input_with_payload(KEY, payload))

    def test_bcbi_rejects_truncation_and_trailing_bytes(self) -> None:
        encoded = encode_bcbi(request(), KEY)
        with self.assertRaises(ProtocolError):
            decode_bcbi(encoded[:-1])
        with self.assertRaises(ProtocolError):
            decode_bcbi(encoded + b"x")

    def test_bcbo_hmac_and_partial_feed(self) -> None:
        stream = encode_start(KEY) + encode_result(KEY, NativeStatus.PASS)
        parser = AuthenticatedOutputParser(KEY)
        frames: list[AuthenticatedFrame] = []
        for byte in stream:
            frames.extend(parser.feed(bytes((byte,))))
        result = parser.finish()
        self.assertEqual([frame.frame_type for frame in frames], [FrameType.START, FrameType.RESULT])
        self.assertIs(result.native_status, NativeStatus.PASS)
        self.assertIsNone(result.native_signal)
        self.assertEqual(parse_authenticated_output(stream, KEY), result)

        tampered = bytearray(stream)
        tampered[-1] ^= 1
        with self.assertRaisesRegex(ProtocolError, "authentication"):
            parse_authenticated_output(bytes(tampered), KEY)

    def test_bcbo_signal_union_and_authenticated_error(self) -> None:
        signal_frame = encode_start(KEY) + encode_signal(KEY, NativeSignal.SIGXCPU)
        parsed = parse_authenticated_output(signal_frame, KEY)
        self.assertIsNone(parsed.native_status)
        self.assertIs(parsed.native_signal, NativeSignal.SIGXCPU)

        error = parse_authenticated_output(encode_error(KEY, "input_invalid", 0), KEY)
        self.assertIs(error.frame_type, FrameType.ERROR)
        self.assertEqual(error.error_code, "input_invalid")

        with self.assertRaises(ProtocolError):
            encode_bcbo(
                KEY,
                1,
                FrameType.RESULT,
                {"schema_version": 1, "native_status": "pass", "native_signal": "sigxcpu"},
            )
        with self.assertRaises(ProtocolError):
            encode_bcbo(KEY, 1, FrameType.RESULT, {"schema_version": 1, "native_signal": "SIGXCPU"})
        with self.assertRaises(ProtocolError):
            GraderNativeResult(NativeStatus.PASS, LimitKind.CPU)
        self.assertIs(GraderNativeResult(None, LimitKind.CPU).limit_kind, LimitKind.CPU)

    def test_bcbo_rejects_invalid_sequences_duplicates_and_trailing_data(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_authenticated_output(encode_result(KEY, "pass", sequence=0), KEY)
        with self.assertRaises(ProtocolError):
            parse_authenticated_output(encode_start(KEY) + encode_start(KEY), KEY)
        with self.assertRaises(ProtocolError):
            parse_authenticated_output(encode_start(KEY) + encode_result(KEY, "pass") + b"x", KEY)
        with self.assertRaises(ProtocolError):
            parse_authenticated_output(encode_start(KEY)[:-1], KEY)

    def test_bcbo_rejects_duplicate_unknown_and_noncanonical_body_keys(self) -> None:
        bodies = (
            b'{"schema_version":1,"error_code":"input_invalid","error_code":"runner_internal"}',
            b'{"schema_version":1,"error_code":"input_invalid","detail":"x"}',
            b'{ "schema_version": 1, "error_code": "input_invalid" }',
        )
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaises(ProtocolError):
                    parse_authenticated_output(frame_with_body(KEY, 0, FrameType.ERROR, body), KEY)

    def test_bcbo_enforces_protocol_byte_bound(self) -> None:
        # A body can be valid JSON yet exceed the fixed frame budget.
        frame = encode_error(KEY, "runner_internal", 0)
        self.assertLessEqual(len(frame), OUTPUT_FRAME_OVERHEAD + 64)
        self.assertLess(OUTPUT_HEADER_SIZE, OUTPUT_FRAME_OVERHEAD)
        oversized = b"{" + b"a" * 20_000 + b"}"
        with self.assertRaises(ProtocolError):
            parse_authenticated_output(frame_with_body(KEY, 0, FrameType.ERROR, oversized), KEY)

        parser = AuthenticatedOutputParser(KEY)
        parser.feed(encode_start(KEY))
        remaining = MAX_OUTPUT_BYTES - len(encode_start(KEY))
        pending = frame_with_body(KEY, 1, FrameType.RESULT, b" " * (MAX_OUTPUT_BYTES - OUTPUT_FRAME_OVERHEAD))
        with self.assertRaisesRegex(ProtocolError, "^output exceeds its size limit$"):
            parser.feed(pending[: remaining + 1])

    def test_bcbi_normalizes_recursion_errors(self) -> None:
        nested = b"[" * 2_000 + b"]" * 2_000
        payload = b'{"schema_version":1,"code":' + nested + b',"test_code":"","entry_point":"answer","task_id":"t"}'
        with self.assertRaises(ProtocolError):
            decode_bcbi(input_with_payload(KEY, payload))

    def test_main_orders_dumpability_limits_input_and_fd_setup(self) -> None:
        arguments = [item for flag, _field in runner_module._CLI_LIMIT_FIELDS for item in (flag, "1")]
        events: list[str] = []
        input_bytes = encode_bcbi(request(), KEY)
        with (
            patch.object(runner_module, "_set_dumpability", side_effect=lambda: events.append("dumpability")),
            patch.object(runner_module, "_apply_runner_limits", side_effect=lambda _limits: events.append("limits")),
            patch.object(
                runner_module, "_read_bounded_input", side_effect=lambda: events.append("input") or input_bytes
            ),
            patch.object(runner_module, "_prepare_output_fd", side_effect=lambda: events.append("dup") or 9),
            patch.object(runner_module, "_replace_standard_fds", side_effect=lambda: events.append("null")),
            patch.object(runner_module, "_run_native", side_effect=lambda *_args: events.append("native") or True),
            patch.object(runner_module.os, "close"),
        ):
            result = runner_module.main(arguments)
        self.assertEqual(result, 0)
        self.assertEqual(events, ["dumpability", "limits", "input", "dup", "null", "native"])

    def test_native_hook_emits_authenticated_start_and_result_without_key_args(self) -> None:
        events: list[object] = []
        original_start_holder: list[object] = []

        class FakeProcess:
            instances: list[object] = []

            def __init__(self, target: object, args: tuple[object, ...] = ()) -> None:
                self._target = target
                self._args = args
                self.exitcode: int | None = 0
                self.instances.append(self)

            def start(self) -> None:
                self.exitcode = 0

        original_start_holder.append(FakeProcess.start)

        def unsafe_execute(*_args: object) -> None:
            return None

        def untrusted_check(
            code: str,
            test_code: str,
            entry_point: str,
            max_as_limit: int,
            max_data_limit: int,
            max_stack_limit: int,
        ) -> tuple[str, dict[str, object]]:
            self.assertEqual(
                (code, test_code, entry_point), (request().code, request().test_code, request().entry_point)
            )
            self.assertEqual((max_as_limit, max_data_limit, max_stack_limit), (8192, 6144, 10))
            process = FakeProcess(unsafe_execute, (request().code,))
            process.start()
            return "pass", {}

        fake_multiprocessing = types.ModuleType("multiprocessing")
        setattr(fake_multiprocessing, "set_start_method", lambda method, force: events.append((method, force)))
        setattr(fake_multiprocessing, "get_start_method", lambda: "spawn")
        setattr(fake_multiprocessing, "get_context", lambda: types.SimpleNamespace(Process=FakeProcess))
        fake_package = types.ModuleType("bigcodebench")
        fake_eval = types.ModuleType("bigcodebench.eval")
        setattr(fake_eval, "unsafe_execute", unsafe_execute)
        setattr(fake_eval, "untrusted_check", untrusted_check)
        output: list[bytes] = []
        with (
            patch.dict(
                sys.modules,
                {
                    "multiprocessing": fake_multiprocessing,
                    "bigcodebench": fake_package,
                    "bigcodebench.eval": fake_eval,
                },
            ),
            patch.object(runner_module.sys, "path", list(runner_module.sys.path)),
            patch.object(runner_module, "_write_frame", side_effect=output.append),
        ):
            self.assertTrue(runner_module._run_native(request(), KEY, 9))
        self.assertEqual(events, [("spawn", True)])
        self.assertEqual(FakeProcess.start, original_start_holder[0])
        self.assertEqual(parse_authenticated_output(b"".join(output), KEY).native_status, NativeStatus.PASS)
        self.assertNotIn(KEY, FakeProcess.instances[0]._args)


if __name__ == "__main__":
    unittest.main()
