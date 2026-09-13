# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pure protocol coverage for the isolated BigCodeBench runner boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import sys
import tempfile
import types
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import eval_harness.bigcodebench_runner as runner_module
import eval_harness.grader_sandbox as sandbox_module
from eval_harness.bigcodebench_runner import (
    MAX_INPUT_FRAME_BYTES,
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
    GraderInfrastructureError,
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
    def _sandbox_fixture(self, root: Path) -> GraderSandboxSpec:
        resource = root / "resource"
        venv = root / "venv"
        base = root / "base"
        directories = (resource / "vendor", resource / "nltk_data", resource / "sandbox_etc", venv / "bin", base / "bin")
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        for name in ("hosts", "nsswitch.conf", "resolv.conf", "passwd", "group"):
            (resource / "sandbox_etc" / name).write_text("fixed\n", encoding="utf-8")
        (venv / "pyvenv.cfg").write_text(f"home = {base / 'bin'}\n", encoding="utf-8")
        python = venv / "bin" / "python"
        bwrap = root / "bwrap"
        python.write_text("python\n", encoding="utf-8")
        bwrap.write_text("bwrap\n", encoding="utf-8")
        python.chmod(0o755)
        bwrap.chmod(0o755)
        return GraderSandboxSpec(resource, bwrap, python)

    def test_bwrap_policy_is_explicit_read_only_and_credential_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            spec = self._sandbox_fixture(Path(temporary))
            command = sandbox_module._build_bwrap_command(spec, process_limit=123)
        self.assertEqual(command[0], str(spec.bwrap_path))
        self.assertIn("--unshare-user", command)
        self.assertIn("--unshare-ipc", command)
        self.assertIn("--unshare-pid", command)
        self.assertIn("--unshare-net", command)
        self.assertIn("--unshare-uts", command)
        self.assertIn("--disable-userns", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("--clearenv", command)
        self.assertIn("--new-session", command)
        self.assertIn("--die-with-parent", command)
        ro_binds = tuple(
            tuple(command[index : index + 3]) for index, value in enumerate(command) if value == "--ro-bind"
        )
        self.assertIn(("--ro-bind", "/usr", "/usr"), ro_binds)
        self.assertNotIn("--unshare-all", command)
        self.assertNotIn("--share-net", command)
        self.assertNotIn("--not-a-security-boundary", command)
        self.assertIn("--setenv", command)
        self.assertNotIn("PYTHONPATH", command)
        self.assertEqual(command[command.index("--processes") + 1], "123")
        self.assertEqual(command[-6:], ("--file-bytes", "67108864", "--open-files", "256", "--processes", "123"))

    def test_policy_rejects_mounts_under_forbidden_untrusted_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._sandbox_fixture(root)
            forbidden = root / "venv"
            unsafe = GraderSandboxSpec(
                spec.resource_dir,
                spec.bwrap_path,
                spec.grader_python,
                forbidden_roots=(forbidden,),
            )
            with self.assertRaisesRegex(GraderInfrastructureError, "untrusted root"):
                sandbox_module._build_bwrap_command(unsafe, process_limit=1)

    def test_secure_uid_lock_requires_private_single_link_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock_template = str(Path(temporary) / "lock-{uid}")
            with patch.object(sandbox_module, "LOCK_PATH_TEMPLATE", lock_template):
                with sandbox_module._exclusive_grader_lock():
                    lock_path = Path(lock_template.format(uid=os.getuid()))
                    mode = stat.S_IMODE(lock_path.stat().st_mode)
                    self.assertEqual(mode, 0o600)
                lock_path.chmod(0o644)
                with self.assertRaisesRegex(GraderInfrastructureError, "unsafe metadata"):
                    with sandbox_module._exclusive_grader_lock():
                        pass

    def test_supervisor_rejects_oversized_input_before_launch(self) -> None:
        with patch.object(sandbox_module.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(GraderInfrastructureError, "input exceeds"):
                sandbox_module._run_bounded_supervisor(
                    ("bwrap",), b"x" * (8 * 1024**2 + 1), KEY, GraderSandboxLimits()
                )
        popen.assert_not_called()

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

        def mark(name: str) -> Callable[..., None]:
            def callback(*_args: object) -> None:
                events.append(name)

            return callback

        def mark_value(name: str, value: object) -> Callable[..., object]:
            def callback(*_args: object) -> object:
                events.append(name)
                return value

            return callback

        with (
            patch.object(runner_module, "_set_dumpability", side_effect=mark("dumpability")),
            patch.object(runner_module, "_apply_runner_limits", side_effect=mark("limits")),
            patch.object(runner_module, "_read_bounded_input", side_effect=mark_value("input", input_bytes)),
            patch.object(runner_module, "_prepare_output_fd", side_effect=mark_value("dup", 9)),
            patch.object(runner_module, "_replace_standard_fds", side_effect=mark("null")),
            patch.object(runner_module, "_run_native", side_effect=mark_value("native", True)),
            patch.object(runner_module, "_close_result_fd"),
        ):
            result = runner_module.main(arguments)
        self.assertEqual(result, 0)
        self.assertEqual(events, ["dumpability", "limits", "input", "dup", "null", "native"])

    def test_native_hook_emits_authenticated_start_and_result_without_key_args(self) -> None:
        cases = (
            (8 * 1024**3, 6 * 1024**3, 10 * 1024**2, (8192, 6144, 10)),
            (2 * 1024**2, 3 * 1024**2, 4 * 1024**2, (2, 3, 4)),
        )
        for address_space, data, stack, expected_native_limits in cases:
            with self.subTest(native_limits=expected_native_limits):
                events: list[object] = []
                captured_args: list[tuple[object, ...]] = []

                class FakeProcess:
                    def __init__(self, target: object, args: tuple[object, ...] = ()) -> None:
                        self._target = target
                        self._args = args
                        self.exitcode: int | None = 0
                        captured_args.append(args)

                    def start(self) -> None:
                        self.exitcode = 0

                original_start = FakeProcess.start

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
                    self.assertEqual((max_as_limit, max_data_limit, max_stack_limit), expected_native_limits)
                    process = FakeProcess(unsafe_execute, (request().code,))
                    process.start()
                    return "pass", {}

                fake_multiprocessing = types.ModuleType("multiprocessing")
                context_process = type("ContextProcess", (), {})

                def set_start_method(method: str, force: bool) -> None:
                    events.append((method, force))

                setattr(fake_multiprocessing, "set_start_method", set_start_method)
                setattr(fake_multiprocessing, "get_start_method", lambda: "spawn")
                setattr(fake_multiprocessing, "Process", FakeProcess)
                setattr(
                    fake_multiprocessing,
                    "get_context",
                    lambda: types.SimpleNamespace(Process=context_process),
                )
                fake_package = types.ModuleType("bigcodebench")
                fake_eval = types.ModuleType("bigcodebench.eval")
                setattr(fake_eval, "unsafe_execute", unsafe_execute)
                setattr(fake_eval, "untrusted_check", untrusted_check)
                output: list[bytes] = []

                def record_frame(_fd: int, frame: bytes) -> None:
                    output.append(frame)

                with (
                    patch.dict(
                        sys.modules,
                        {
                            "multiprocessing": fake_multiprocessing,
                            "bigcodebench": fake_package,
                            "bigcodebench.eval": fake_eval,
                        },
                    ),
                    patch.object(sys, "path", list(sys.path)),
                    patch.object(runner_module, "_write_frame", side_effect=record_frame),
                ):
                    limits = runner_module._RunnerLimits(245, 250, address_space, data, stack, 64 * 1024**2, 256, 32)
                    self.assertTrue(runner_module._run_native(request(), KEY, 9, limits))
                self.assertEqual(events, [("spawn", True)])
                self.assertIs(FakeProcess.start, original_start)
                self.assertEqual(parse_authenticated_output(b"".join(output), KEY).native_status, NativeStatus.PASS)
                self.assertEqual(len(captured_args), 1)
                self.assertNotIn(KEY, captured_args[0])

    def test_non_whole_native_limit_rejects_before_native_import(self) -> None:
        imported: list[str] = []
        fake_importlib = types.ModuleType("importlib")

        def import_module(name: str) -> object:
            imported.append(name)
            raise AssertionError("native import should not run")

        setattr(fake_importlib, "import_module", import_module)
        output: list[bytes] = []

        def record_frame(_fd: int, frame: bytes) -> None:
            output.append(frame)

        limits = runner_module._RunnerLimits(245, 250, 1, 3 * 1024**2, 4 * 1024**2, 64 * 1024**2, 256, 32)
        with (
            patch.dict(sys.modules, {"importlib": fake_importlib}),
            patch.object(runner_module, "_write_frame", side_effect=record_frame),
        ):
            self.assertFalse(runner_module._run_native(request(), KEY, 9, limits))
        self.assertEqual(imported, [])
        error = parse_authenticated_output(b"".join(output), KEY)
        self.assertEqual(error.error_code, "native_setup_failed")

    def test_bounded_reader_overflow_with_key_emits_input_error_without_native(self) -> None:
        arguments = [item for flag, _field in runner_module._CLI_LIMIT_FIELDS for item in (flag, "1")]
        input_bytes = encode_bcbi(request(), KEY)
        oversized = input_bytes + b"x" * (MAX_INPUT_FRAME_BYTES + 1 - len(input_bytes))
        chunks = [oversized[index : index + 64 * 1024] for index in range(0, len(oversized), 64 * 1024)]

        def read(_fd: int, _size: int) -> bytes:
            return chunks.pop(0) if chunks else b""

        output: list[bytes] = []

        def record_frame(_fd: int, frame: bytes) -> None:
            output.append(frame)

        def forbidden_native(*_args: object) -> bool:
            self.fail("native execution must not follow oversized input")
            return False

        with (
            patch.object(runner_module, "_set_dumpability"),
            patch.object(runner_module, "_apply_runner_limits"),
            patch.object(os, "read", side_effect=read),
            patch.object(runner_module, "_prepare_output_fd", return_value=9),
            patch.object(runner_module, "_replace_standard_fds"),
            patch.object(runner_module, "_close_result_fd"),
            patch.object(runner_module, "_run_native", side_effect=forbidden_native),
            patch.object(runner_module, "_write_frame", side_effect=record_frame),
        ):
            self.assertEqual(runner_module.main(arguments), 1)
        error = parse_authenticated_output(b"".join(output), KEY)
        self.assertEqual(error.sequence, 0)
        self.assertIs(error.frame_type, FrameType.ERROR)
        self.assertEqual(error.error_code, "input_invalid")


if __name__ == "__main__":
    unittest.main()
