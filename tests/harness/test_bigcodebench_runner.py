# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pure protocol coverage for the isolated BigCodeBench runner boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import selectors
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast
from unittest.mock import patch

import eval_harness.bigcodebench_runner as runner_module
import eval_harness.grader_sandbox as sandbox_module
from eval_harness.bigcodebench_runner import (
    INPUT_FIXED_BYTES,
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
    PRODUCTION_GRADER_LIMITS,
    GraderInfrastructureError,
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


class _FakePopen:
    """Small pipe-backed process double for host selector-loop tests."""

    def __init__(self, output: bytes, *, hold_open: bool = False, hold_pipes: bool = False) -> None:
        input_read, input_write = os.pipe()
        output_read, output_write = os.pipe()
        error_read, error_write = os.pipe()
        self.stdin: BinaryIO = os.fdopen(input_write, "wb", buffering=0)
        self.stdout: BinaryIO = os.fdopen(output_read, "rb", buffering=0)
        self.stderr: BinaryIO = os.fdopen(error_read, "rb", buffering=0)
        self.pid = 424242
        self.returncode: int | None = None
        self.killed = False
        self.poll_calls = 0
        self._input_read = input_read
        self._output_write = output_write
        self._error_write = error_write
        self._output = output
        self._hold_open = hold_open
        self._hold_pipes = hold_pipes
        self._fd_lock = threading.Lock()
        self._thread = threading.Thread(target=self._emit, daemon=True)
        self._thread.start()

    def _close_fd(self, name: str) -> None:
        with self._fd_lock:
            descriptor = cast(int, getattr(self, name))
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                setattr(self, name, -1)

    def _emit(self) -> None:
        try:
            offset = 0
            while offset < len(self._output):
                try:
                    offset += os.write(self._output_write, self._output[offset:])
                except BrokenPipeError:
                    break
        finally:
            if not self._hold_pipes:
                self._close_fd("_output_write")
                self._close_fd("_error_write")
            self._close_fd("_input_read")
            if not self._hold_open and not self.killed:
                self.returncode = 0

    def poll(self) -> int | None:
        self.poll_calls += 1
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        for name in ("_output_write", "_error_write", "_input_read"):
            self._close_fd(name)

    def close_writers(self) -> None:
        self._close_fd("_output_write")
        self._close_fd("_error_write")


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class _ScriptedSelector:
    def __init__(self, clock: _FakeClock, events: list[str | None]) -> None:
        self._clock = clock
        self._events = iter(events)
        self._registered: dict[str, tuple[BinaryIO, int]] = {}

    def register(self, fileobj: object, events: int, data: object = None) -> None:
        if not isinstance(data, str):
            raise AssertionError("scripted selector requires named streams")
        self._registered[data] = (cast(BinaryIO, fileobj), events)

    def unregister(self, fileobj: object) -> None:
        for name, (registered, _events) in tuple(self._registered.items()):
            if registered is fileobj:
                del self._registered[name]
                return
        raise KeyError(fileobj)

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        try:
            name = next(self._events)
        except StopIteration:
            name = None
        if name is None:
            self._clock.sleep(timeout or 0.0)
            return []
        fileobj, events = self._registered[name]
        key = selectors.SelectorKey(fileobj, fileobj.fileno(), events, name)
        return [(key, events)]

    def get_map(self) -> dict[int, selectors.SelectorKey]:
        return {
            fileobj.fileno(): selectors.SelectorKey(fileobj, fileobj.fileno(), events, name)
            for name, (fileobj, events) in self._registered.items()
        }

    def close(self) -> None:
        self._registered.clear()


class _PipePopen:
    def __init__(
        self,
        output: bytes,
        *,
        clock: _FakeClock | None = None,
        exit_at: float | None = None,
        exit_on_poll: int | None = None,
        hold_pipes: bool = False,
    ) -> None:
        input_read, input_write = os.pipe()
        output_read, output_write = os.pipe()
        error_read, error_write = os.pipe()
        self.stdin: BinaryIO = os.fdopen(input_write, "wb", buffering=0)
        self.stdout: BinaryIO = os.fdopen(output_read, "rb", buffering=0)
        self.stderr: BinaryIO = os.fdopen(error_read, "rb", buffering=0)
        self.pid = 424244
        self.returncode: int | None = None
        self.killed = False
        self.poll_calls = 0
        self._input_read = input_read
        self._output_write = output_write
        self._error_write = error_write
        self._clock = clock
        self._exit_at = exit_at
        self._exit_on_poll = exit_on_poll
        os.write(output_write, output)
        if not hold_pipes:
            self._close_fd("_output_write")
            self._close_fd("_error_write")

    def _close_fd(self, name: str) -> None:
        descriptor = cast(int, getattr(self, name))
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
            setattr(self, name, -1)

    def poll(self) -> int | None:
        self.poll_calls += 1
        if self.returncode is None and self._exit_on_poll is not None and self.poll_calls >= self._exit_on_poll:
            self.returncode = 0
        if self.returncode is None and self._exit_at is not None and self._clock is not None:
            if self._clock.value >= self._exit_at:
                self.returncode = 0
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        for name in ("_output_write", "_error_write", "_input_read"):
            self._close_fd(name)

    def exit_after_polls(self, additional_polls: int) -> None:
        self._exit_on_poll = self.poll_calls + additional_polls

    def close_all(self) -> None:
        for name in ("_output_write", "_error_write", "_input_read"):
            self._close_fd(name)
        self.stdin.close()
        self.stdout.close()
        self.stderr.close()


class TestBigCodeBenchRunner(unittest.TestCase):
    def _sandbox_fixture(self, root: Path) -> GraderSandboxSpec:
        resource = root / "resource"
        venv = root / "venv"
        base = root / "base"
        directories = (
            resource / "vendor",
            resource / "nltk_data",
            resource / "sandbox_etc",
            venv / "bin",
            base / "bin",
        )
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
            expected_bwrap = spec.bwrap_path.resolve()
            expected_venv = (Path(temporary) / "venv").resolve()
            expected_base = (Path(temporary) / "base").resolve()
            expected_resource = (Path(temporary) / "resource").resolve()
            expected_runner = (Path(sandbox_module.__file__).with_name("bigcodebench_runner.py")).resolve()
            expected = [
                str(expected_bwrap),
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
                "536870912",
                "--tmpfs",
                "/tmp",
                "--size",
                "67108864",
                "--tmpfs",
                "/dev/shm",
            ]
            for directory in (
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
            ):
                expected.extend(("--dir", directory))
            expected.extend(("--dir", "/etc"))
            expected.extend(("--ro-bind", str(expected_venv), str(expected_venv)))
            expected.extend(("--ro-bind", str(expected_base), str(expected_base)))
            expected.extend(("--ro-bind", str(expected_runner), "/opt/bigcodebench/bigcodebench_runner.py"))
            expected.extend(("--ro-bind", str(expected_resource / "vendor"), "/opt/bigcodebench/vendor"))
            expected.extend(("--ro-bind", str(expected_resource / "nltk_data"), "/opt/bigcodebench/nltk_data"))
            expected.extend(("--ro-bind", "/usr", "/usr"))
            for target, link in (
                ("usr/bin", "/bin"),
                ("usr/sbin", "/sbin"),
                ("usr/lib", "/lib"),
                ("usr/lib64", "/lib64"),
            ):
                expected.extend(("--symlink", target, link))
            frozen_system_mounts = (
                ("/etc/ld.so.cache", "/etc/ld.so.cache"),
                ("/etc/ssl/certs", "/etc/ssl/certs"),
                ("/etc/fonts", "/etc/fonts"),
                ("/etc/localtime", "/etc/localtime"),
            )
            self.assertEqual(sandbox_module._SYSTEM_OPTIONAL_MOUNTS, frozen_system_mounts)
            present_system_mounts = {Path("/etc/ld.so.cache"), Path("/etc/localtime")}
            for source, target in frozen_system_mounts:
                if Path(source) in present_system_mounts:
                    expected.extend(("--ro-bind", source, target))
            for name in ("hosts", "nsswitch.conf", "resolv.conf", "passwd", "group"):
                expected.extend(("--ro-bind", str(expected_resource / "sandbox_etc" / name), f"/etc/{name}"))
            expected.extend(("--remount-ro", "/dev", "--remount-ro", "/"))
            environment = (
                ("PATH", f"{expected_venv / 'bin'}:/usr/bin:/bin"),
                ("LANG", "C.UTF-8"),
                ("LC_ALL", "C.UTF-8"),
                ("TZ", "UTC"),
                ("HOME", "/tmp/home"),
                ("TMPDIR", "/tmp"),
                ("MPLBACKEND", "Agg"),
                ("NLTK_DATA", "/opt/bigcodebench/nltk_data"),
                ("BIGCODEBENCH_NLTK_OFFLINE", "bigcodebench-bwrap-v1"),
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
            for name, value in environment:
                expected.extend(("--setenv", name, value))
            expected.extend(("--chdir", "/tmp/work", str(expected_venv / "bin" / "python"), "-I", "-B"))
            expected.extend(("/opt/bigcodebench/bigcodebench_runner.py",))
            expected.extend(
                (
                    "--cpu-soft-seconds",
                    "245",
                    "--cpu-hard-seconds",
                    "250",
                    "--address-space-bytes",
                    "8589934592",
                    "--data-bytes",
                    "6442450944",
                    "--stack-bytes",
                    "10485760",
                    "--file-bytes",
                    "67108864",
                    "--open-files",
                    "256",
                    "--processes",
                    "123",
                )
            )
            original_exists = Path.exists

            def controlled_exists(path: Path) -> bool:
                for source, _target in frozen_system_mounts:
                    if path == Path(source):
                        return path in present_system_mounts
                return original_exists(path)

            with patch.object(Path, "exists", controlled_exists):
                command = sandbox_module._build_bwrap_command(spec, process_limit=123)
            self.assertEqual(command, tuple(expected))

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
        with patch.object(subprocess, "Popen") as popen:
            with self.assertRaisesRegex(GraderInfrastructureError, "input exceeds"):
                sandbox_module._run_bounded_supervisor(
                    ("bwrap",), b"x" * (8 * 1024**2 + INPUT_FIXED_BYTES + 1), KEY, GraderSandboxLimits()
                )
        popen.assert_not_called()

    def test_supervisor_input_limit_counts_payload_not_fixed_frame(self) -> None:
        limits = GraderSandboxLimits(stdin_bytes=64)
        sandbox_module._validate_input_size(b"x" * (64 + INPUT_FIXED_BYTES), limits)
        with self.assertRaisesRegex(GraderInfrastructureError, "input exceeds"):
            sandbox_module._validate_input_size(b"x" * (65 + INPUT_FIXED_BYTES), limits)

    def _run_fake_supervisor(
        self,
        output: bytes,
        *,
        samples: list[tuple[set[int], int]] | None = None,
        hold_open: bool = False,
        limits: GraderSandboxLimits | None = None,
    ) -> tuple[GraderNativeResult, _FakePopen]:
        fake = _FakePopen(output, hold_open=hold_open)
        values = iter(samples or [(set(), 0)])
        last_sample: tuple[set[int], int] = (set(), 0)

        def sample(_pid: int) -> tuple[set[int], int]:
            nonlocal last_sample
            try:
                last_sample = next(values)
            except StopIteration:
                pass
            return last_sample

        with (
            patch.object(subprocess, "Popen", return_value=fake),
            patch.object(sandbox_module, "_sample_process_tree", side_effect=sample),
            patch.object(sandbox_module, "_descendant_pids", return_value=set()),
        ):
            result = sandbox_module._run_bounded_supervisor(("bwrap",), b"", KEY, limits or GraderSandboxLimits())
        return result, fake

    def test_supervisor_returns_authenticated_result_and_waits_for_cleanup(self) -> None:
        output = encode_start(KEY) + encode_result(KEY, NativeStatus.PASS)
        with patch.object(sandbox_module, "_wait_for_cleanup", wraps=sandbox_module._wait_for_cleanup) as cleanup:
            result, fake = self._run_fake_supervisor(output)
        self.assertEqual(result, GraderNativeResult(NativeStatus.PASS))
        self.assertFalse(fake.killed)
        cleanup.assert_called_once()

    def test_supervisor_maps_authenticated_error_and_cleans_trusted_process(self) -> None:
        output = encode_error(KEY, "runner_internal", 0)
        fake = _FakePopen(output)
        with patch.object(sandbox_module, "_wait_for_cleanup", wraps=sandbox_module._wait_for_cleanup) as cleanup:
            with (
                patch.object(subprocess, "Popen", return_value=fake),
                patch.object(sandbox_module, "_sample_process_tree", return_value=(set(), 0)),
                patch.object(sandbox_module, "_descendant_pids", return_value=set()),
            ):
                with self.assertRaisesRegex(GraderInfrastructureError, "infrastructure error"):
                    sandbox_module._run_bounded_supervisor(("bwrap",), b"", KEY, GraderSandboxLimits())
        cleanup.assert_called_once()

    def test_supervisor_enforces_live_candidate_process_cap(self) -> None:
        output = encode_start(KEY)
        result, fake = self._run_fake_supervisor(
            output,
            samples=[(set(), 0), ({99}, 0)],
            hold_open=True,
            limits=GraderSandboxLimits(process_headroom=1),
        )
        self.assertEqual(result, GraderNativeResult(None, LimitKind.PROCESSES))
        self.assertTrue(fake.killed)

    def test_supervisor_treats_prestart_process_cap_as_infrastructure(self) -> None:
        fake = _FakePopen(b"", hold_open=True)
        with (
            patch.object(subprocess, "Popen", return_value=fake),
            patch.object(sandbox_module, "_sample_process_tree", return_value=({99}, 0)),
            patch.object(sandbox_module, "_descendant_pids", return_value=set()),
        ):
            with self.assertRaisesRegex(GraderInfrastructureError, "before grader start"):
                sandbox_module._run_bounded_supervisor(("bwrap",), b"", KEY, GraderSandboxLimits(process_headroom=1))
        self.assertTrue(fake.killed)

    def test_supervisor_does_not_report_limit_for_trusted_process_that_died(self) -> None:
        class DiesAfterSample(_FakePopen):
            def __init__(self) -> None:
                super().__init__(b"", hold_open=True)
                self._polls = 0

            def poll(self) -> int | None:
                self._polls += 1
                if self._polls >= 2 and self.returncode is None:
                    self.returncode = 0
                return self.returncode

        fake = DiesAfterSample()
        with (
            patch.object(subprocess, "Popen", return_value=fake),
            patch.object(sandbox_module, "_sample_process_tree", return_value=({99}, 0)),
            patch.object(sandbox_module, "_descendant_pids", return_value=set()),
        ):
            with self.assertRaisesRegex(GraderInfrastructureError, "invalid grader protocol"):
                sandbox_module._run_bounded_supervisor(("bwrap",), b"", KEY, GraderSandboxLimits())
        self.assertFalse(fake.killed)

    def test_supervisor_does_not_restart_teardown_after_terminal_before_outer_exit(self) -> None:
        clock = _FakeClock()
        fake = _PipePopen(
            encode_start(KEY) + encode_result(KEY, NativeStatus.PASS),
            clock=clock,
            exit_at=1.0,
            hold_pipes=True,
        )
        selector = _ScriptedSelector(clock, ["stdout"])
        limits = GraderSandboxLimits(teardown_seconds=5.0)
        try:
            with (
                patch.object(subprocess, "Popen", return_value=fake),
                patch.object(
                    selectors,
                    "DefaultSelector",
                    return_value=cast(selectors.BaseSelector, selector),
                ),
                patch.object(sandbox_module, "_sample_process_tree", return_value=(set(), 0)),
                patch.object(sandbox_module, "_descendant_pids", return_value=set()),
                patch.object(time, "monotonic", side_effect=clock.monotonic),
                patch.object(time, "sleep", side_effect=clock.sleep),
                patch.object(sandbox_module, "DESCENDANT_SAMPLE_SECONDS", 1.0),
            ):
                with self.assertRaises(GraderInfrastructureError):
                    sandbox_module._run_bounded_supervisor(("bwrap",), b"", KEY, limits)
            self.assertEqual(clock.value, limits.teardown_seconds)
        finally:
            fake.close_all()

    def test_supervisor_does_not_restart_cleanup_budget_after_successful_result(self) -> None:
        clock = _FakeClock()
        fake = _PipePopen(
            encode_start(KEY) + encode_result(KEY, NativeStatus.PASS),
        )
        fake.returncode = 0
        selector = _ScriptedSelector(clock, ["stdout", "stdout", "stderr"])
        limits = GraderSandboxLimits(teardown_seconds=1.0)
        try:
            with (
                patch.object(subprocess, "Popen", return_value=fake),
                patch.object(
                    selectors,
                    "DefaultSelector",
                    return_value=cast(selectors.BaseSelector, selector),
                ),
                patch.object(sandbox_module, "_descendant_pids", return_value={99}),
                patch.object(time, "monotonic", side_effect=clock.monotonic),
                patch.object(time, "sleep", side_effect=clock.sleep),
                patch.object(sandbox_module, "DESCENDANT_SAMPLE_SECONDS", 1.0),
            ):
                with self.assertRaises(GraderInfrastructureError):
                    sandbox_module._run_bounded_supervisor(("bwrap",), b"", KEY, limits)
            self.assertEqual(clock.value, limits.teardown_seconds)
        finally:
            fake.close_all()

    def test_supervisor_rejects_limit_when_trusted_process_exits_during_reap_poll(self) -> None:
        clock = _FakeClock()
        fake = _PipePopen(encode_start(KEY), clock=clock, hold_pipes=True)
        selector = _ScriptedSelector(clock, ["stdout"])
        samples = iter([(set(), 0), ({99}, 0)])

        def sample(_pid: int) -> tuple[set[int], int]:
            value = next(samples)
            if value[0]:
                fake.exit_after_polls(2)
            return value

        try:
            with (
                patch.object(subprocess, "Popen", return_value=fake),
                patch.object(
                    selectors,
                    "DefaultSelector",
                    return_value=cast(selectors.BaseSelector, selector),
                ),
                patch.object(
                    sandbox_module,
                    "_sample_process_tree",
                    side_effect=sample,
                ),
                patch.object(sandbox_module, "_descendant_pids", return_value=set()),
                patch.object(time, "monotonic", side_effect=clock.monotonic),
                patch.object(time, "sleep", side_effect=clock.sleep),
                patch.object(sandbox_module, "DESCENDANT_SAMPLE_SECONDS", 0.0),
            ):
                with self.assertRaises(GraderInfrastructureError):
                    sandbox_module._run_bounded_supervisor(
                        ("bwrap",), b"", KEY, GraderSandboxLimits(process_headroom=1)
                    )
            self.assertFalse(fake.killed)
        finally:
            fake.close_all()

    def test_supervisor_bounds_drain_after_dead_process_with_held_pipes(self) -> None:
        fake = _FakePopen(b"", hold_pipes=True)
        fake.returncode = 0
        limits = GraderSandboxLimits(teardown_seconds=0.01)
        try:
            with (
                patch.object(subprocess, "Popen", return_value=fake),
                patch.object(sandbox_module, "_descendant_pids", return_value=set()),
            ):
                with self.assertRaisesRegex(GraderInfrastructureError, "pipes did not close"):
                    sandbox_module._run_bounded_supervisor(("bwrap",), b"", KEY, limits)
        finally:
            fake.close_writers()

    def test_cleanup_polls_outer_process_before_unverifiable_descendants(self) -> None:
        fake = _FakePopen(b"", hold_open=True)
        typed_fake = cast(subprocess.Popen[bytes], fake)
        try:
            with patch.object(
                sandbox_module,
                "_descendant_pids",
                side_effect=GraderInfrastructureError("process tree is unavailable"),
            ):
                with self.assertRaisesRegex(GraderInfrastructureError, "process tree"):
                    sandbox_module._terminate_and_reap(typed_fake, set(), 0.01)
            self.assertTrue(fake.killed)
            self.assertGreaterEqual(fake.poll_calls, 2)
        finally:
            fake.close_writers()
            fake.stdin.close()
            fake.stdout.close()
            fake.stderr.close()

    def test_supervisor_reaps_when_popen_does_not_supply_all_pipes(self) -> None:
        class NoPipes:
            pid = 424243
            stdin = None
            stdout = None
            stderr = None
            returncode: int | None = None
            killed = False

            def poll(self) -> int | None:
                return self.returncode

            def kill(self) -> None:
                self.killed = True
                self.returncode = -9

        fake = NoPipes()
        with (
            patch.object(subprocess, "Popen", return_value=fake),
            patch.object(sandbox_module, "_descendant_pids", return_value=set()),
        ):
            with self.assertRaisesRegex(GraderInfrastructureError, "pipes unavailable"):
                sandbox_module._run_bounded_supervisor(("bwrap",), b"", KEY, GraderSandboxLimits())
        self.assertTrue(fake.killed)

    def test_supervisor_cleans_up_parser_and_selector_initialization_failures(self) -> None:
        for patcher, message in (
            (
                patch.object(sandbox_module, "AuthenticatedOutputParser", side_effect=ProtocolError("bad key")),
                "sandbox I/O",
            ),
            (
                patch.object(selectors, "DefaultSelector", side_effect=OSError("selector")),
                "sandbox I/O",
            ),
        ):
            with self.subTest(message=message):
                fake = _FakePopen(b"", hold_open=True)
                try:
                    with (
                        patch.object(subprocess, "Popen", return_value=fake),
                        patch.object(sandbox_module, "_descendant_pids", return_value=set()),
                        patcher,
                    ):
                        with self.assertRaisesRegex(GraderInfrastructureError, message):
                            sandbox_module._run_bounded_supervisor(("bwrap",), b"", KEY, GraderSandboxLimits())
                        self.assertTrue(fake.killed)
                        self.assertIsNotNone(fake.returncode)
                        self.assertGreaterEqual(fake.poll_calls, 2)
                        self.assertTrue(fake.stdin.closed)
                        self.assertTrue(fake.stdout.closed)
                        self.assertTrue(fake.stderr.closed)
                finally:
                    fake.close_writers()

    def test_process_baseline_uses_real_uid_and_all_threads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entry = Path(temporary) / "123"
            entry.mkdir()
            (entry / "status").write_text(
                f"Name:\tworker\nUid:\t{os.getuid()} 9999 9999 9999\nThreads:\t3\n",
                encoding="ascii",
            )
            self.assertEqual(sandbox_module._process_thread_count(entry, os.getuid()), 3)

            (entry / "status").write_text("Name:\tworker\nUid:\tbroken\nThreads:\t3\n", encoding="ascii")
            with self.assertRaisesRegex(GraderInfrastructureError, "baseline observation"):
                sandbox_module._process_thread_count(entry, os.getuid())

    def test_process_tree_observation_fails_closed_except_exit_races(self) -> None:
        with patch.object(Path, "iterdir", side_effect=PermissionError):
            with self.assertRaisesRegex(GraderInfrastructureError, "process tree is unavailable"):
                sandbox_module._proc_parent_map()

        with tempfile.TemporaryDirectory() as temporary:
            entry = Path(temporary) / "123"
            entry.mkdir()
            (entry / "stat").write_text("malformed", encoding="utf-8")
            with patch.object(Path, "iterdir", return_value=(entry,)):
                with self.assertRaisesRegex(GraderInfrastructureError, "observation failed"):
                    sandbox_module._proc_parent_map()

            disappeared = Path(temporary) / "456"
            with patch.object(Path, "iterdir", return_value=(disappeared,)):
                self.assertEqual(sandbox_module._proc_parent_map(), {})

            (entry / "stat").write_text("123 (worker-☃) S 1 2 3\n", encoding="utf-8")
            with patch.object(Path, "iterdir", return_value=(entry,)):
                self.assertEqual(sandbox_module._proc_parent_map(), {123: 1})

    def test_rss_observation_recognizes_zombies_and_rejects_live_gaps(self) -> None:
        with patch.object(Path, "read_text", return_value="Name:\tworker\nState:\tZ (zombie)\n"):
            self.assertEqual(sandbox_module._rss_bytes(123), 0)
        with patch.object(Path, "read_text", return_value="Name:\tworker\nState:\tX (dead)\n"):
            self.assertEqual(sandbox_module._rss_bytes(123), 0)
        with patch.object(Path, "read_text", return_value="Name:\tworker\nState:\tS (sleeping)\n"):
            with self.assertRaisesRegex(GraderInfrastructureError, "incomplete"):
                sandbox_module._rss_bytes(123)
        with patch.object(Path, "read_text", return_value="Name:\tworker\nState:\tS (sleeping)\nVmRSS:\tbad kB\n"):
            with self.assertRaisesRegex(GraderInfrastructureError, "observation failed"):
                sandbox_module._rss_bytes(123)
        with patch.object(Path, "read_text", side_effect=PermissionError):
            with self.assertRaisesRegex(GraderInfrastructureError, "memory observation"):
                sandbox_module._rss_bytes(123)

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
