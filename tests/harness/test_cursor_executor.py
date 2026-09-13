# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_harness.executors.base import ExecutionRequest, TaskSpec
from eval_harness.executors.cursor import CursorExecutor, subscription_environment
from eval_harness.failures import FailureKind


class CursorExecutorTests(unittest.TestCase):
    def request(self, root: str) -> ExecutionRequest:
        base = Path(root)
        workspace = base / "workspace"
        deliverables = workspace / "deliverables"
        executor_dir = base / "executor"
        workspace.mkdir(parents=True, exist_ok=True)
        deliverables.mkdir(parents=True, exist_ok=True)
        executor_dir.mkdir(parents=True, exist_ok=True)
        return ExecutionRequest(
            task=TaskSpec(task_id="t", prompt="real task text"),
            workspace=workspace,
            deliverables_dir=deliverables,
            executor_dir=executor_dir,
            model="example-model",
        )

    def test_command_is_headless_local_workspace_and_sandboxed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            request = self.request(root)
            command = CursorExecutor(network_enabled=False).build_command(request)
            self.assertEqual(command[:2], ["agent", "-p"])
            self.assertIn("--trust", command)
            self.assertNotIn("--force", command)
            self.assertIn("--workspace", command)
            self.assertEqual(command[command.index("--workspace") + 1], str(request.workspace))
            self.assertIn("--output-format", command)
            self.assertEqual(command[command.index("--output-format") + 1], "json")
            self.assertIn("--sandbox", command)
            self.assertEqual(command[command.index("--sandbox") + 1], "enabled")
            self.assertIn("--model", command)
            self.assertNotIn("real task text", command)
            self.assertNotIn("--api-key", command)
            self.assertNotIn("--auth-token", command)
            self.assertNotIn("--worktree", command)

    def test_workspace_policy_denies_network_mcp_and_adds_readonly_task_input_path(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            readonly = Path(root) / "readonly-inputs"
            workspace.mkdir()
            readonly.mkdir()
            CursorExecutor(network_enabled=False)._write_workspace_policy(workspace, readonly)
            sandbox = json.loads((workspace / ".cursor" / "sandbox.json").read_text())
            config = json.loads((workspace / ".cursor" / "cli.json").read_text())
            self.assertEqual(sandbox["type"], "workspace_readwrite")
            self.assertEqual(sandbox["networkPolicy"]["default"], "deny")
            self.assertTrue(sandbox["disableTmpWrite"])
            self.assertIn(str(readonly.resolve()), sandbox["additionalReadonlyPaths"])
            self.assertIn("Mcp(*:*)", config["permissions"]["deny"])
            self.assertIn("WebFetch(*)", config["permissions"]["deny"])
            self.assertIn("Write(task_inputs/**)", config["permissions"]["deny"])
            self.assertNotIn("Write(reference_files/**)", config["permissions"]["deny"])
            self.assertIn("Shell(*)", config["permissions"]["allow"])

    def test_task_input_tree_is_moved_outside_workspace_then_restored(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "task" / "workspace"
            inputs = workspace / "task_inputs"
            inputs.mkdir(parents=True)
            (inputs / "input.txt").write_text("original\n", encoding="utf-8")
            executor = CursorExecutor()
            protected, digest = executor._isolate_task_inputs(workspace)
            self.assertIsNotNone(protected)
            self.assertIsNotNone(digest)
            self.assertTrue(inputs.is_symlink())
            self.assertFalse(str(protected).startswith(str(workspace) + os.sep))
            executor._restore_task_inputs(workspace, protected)
            self.assertFalse(inputs.is_symlink())
            self.assertEqual((inputs / "input.txt").read_text(encoding="utf-8"), "original\n")

    def test_legacy_reference_namespace_is_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            (workspace / "reference_files").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "does not accept the legacy reference_files input namespace"):
                CursorExecutor()._isolate_task_inputs(workspace)

    def test_task_input_symlink_and_non_directory_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            workspace.mkdir()
            target = Path(root) / "target"
            target.mkdir()
            (workspace / "task_inputs").symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "task_inputs input must be a real directory"):
                CursorExecutor()._isolate_task_inputs(workspace)

            (workspace / "task_inputs").unlink()
            (workspace / "task_inputs").write_text("input", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "task_inputs input must be a real directory"):
                CursorExecutor()._isolate_task_inputs(workspace)

    def test_policy_write_failure_restores_task_inputs_without_invoking_agent(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            request = self.request(root)
            inputs = request.workspace / "task_inputs"
            inputs.mkdir()
            original = inputs / "input.txt"
            original.write_text("original", encoding="utf-8")
            executor = CursorExecutor(command="agent")
            with (
                patch.object(executor, "_write_workspace_policy", side_effect=OSError("policy denied")),
                patch("eval_harness.executors.cursor.subprocess.run") as run,
            ):
                with self.assertRaisesRegex(OSError, "policy denied"):
                    executor.execute(request)
            run.assert_not_called()
            self.assertTrue(inputs.is_dir())
            self.assertFalse(inputs.is_symlink())
            self.assertEqual(original.read_text(encoding="utf-8"), "original")

    def test_prompt_write_failure_or_interrupt_restores_task_inputs_without_invoking_agent(self) -> None:
        prompt_path_error = "prompt write denied"
        for name, prompt_error in (("error", OSError(prompt_path_error)), ("interrupt", KeyboardInterrupt())):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                request = self.request(root)
                inputs = request.workspace / "task_inputs"
                inputs.mkdir()
                original = inputs / "input.txt"
                original.write_text("original", encoding="utf-8")
                prompt_path = request.executor_dir / "prompt.txt"
                executor = CursorExecutor(command="agent")
                original_write_text = Path.write_text

                def write_text(path: Path, data: str, *args: object, **kwargs: object) -> int:
                    if path == prompt_path:
                        raise prompt_error
                    return original_write_text(path, data, *args, **kwargs)

                with (
                    patch.object(Path, "write_text", autospec=True, side_effect=write_text),
                    patch("eval_harness.executors.cursor.subprocess.run") as run,
                ):
                    if isinstance(prompt_error, KeyboardInterrupt):
                        with self.assertRaises(KeyboardInterrupt):
                            executor.execute(request)
                    else:
                        with self.assertRaisesRegex(OSError, prompt_path_error):
                            executor.execute(request)
                run.assert_not_called()
                self.assertTrue(inputs.is_dir())
                self.assertFalse(inputs.is_symlink())
                self.assertEqual(original.read_text(encoding="utf-8"), "original")

    def test_isolation_digest_failure_restores_task_inputs_without_invoking_agent(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            request = self.request(root)
            inputs = request.workspace / "task_inputs"
            inputs.mkdir()
            original = inputs / "input.txt"
            original.write_text("original", encoding="utf-8")
            executor = CursorExecutor(command="agent")
            with (
                patch("eval_harness.executors.cursor._tree_digest", side_effect=OSError("digest unavailable")),
                patch("eval_harness.executors.cursor.subprocess.run") as run,
            ):
                with self.assertRaisesRegex(OSError, "digest unavailable"):
                    executor.execute(request)
            run.assert_not_called()
            self.assertTrue(inputs.is_dir())
            self.assertFalse(inputs.is_symlink())
            self.assertEqual(original.read_text(encoding="utf-8"), "original")

    def test_late_task_input_mutation_discards_parsed_output(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            request = self.request(root)
            (request.workspace / "task_inputs").mkdir()
            (request.workspace / "task_inputs" / "input.txt").write_text("original", encoding="utf-8")
            executor = CursorExecutor(command="agent")
            executor._version = "fake-cursor"
            success = json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "duration_ms": 1,
                    "duration_api_ms": 1,
                    "result": "answer",
                    "session_id": "session",
                }
            )
            with (
                patch(
                    "eval_harness.executors.cursor.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 0, stdout=success, stderr=""),
                ),
                patch(
                    "eval_harness.executors.cursor._tree_digest",
                    side_effect=["baseline", "baseline", "mutated"],
                ),
            ):
                result = executor.execute(request)
            self.assertEqual(result.status.value, "failed")
            self.assertIsNotNone(result.failure)
            assert result.failure is not None
            self.assertEqual(result.failure.kind, FailureKind.INTEGRITY)
            self.assertEqual(result.failure.code, "task_input_mutation")
            self.assertIsNone(result.output_text)
            self.assertEqual(result.available_outputs, frozenset())

    def test_restore_failure_discards_successful_output(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            request = self.request(root)
            (request.workspace / "task_inputs").mkdir()
            (request.workspace / "task_inputs" / "input.txt").write_text("original", encoding="utf-8")
            executor = CursorExecutor(command="agent")
            executor._version = "fake-cursor"
            success = json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "duration_ms": 1,
                    "duration_api_ms": 1,
                    "result": "answer",
                    "session_id": "session",
                }
            )
            with (
                patch(
                    "eval_harness.executors.cursor.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 0, stdout=success, stderr=""),
                ),
                patch("eval_harness.executors.cursor._tree_digest", return_value="baseline"),
                patch.object(CursorExecutor, "_restore_task_inputs", side_effect=OSError("restore denied")),
            ):
                result = executor.execute(request)
            self.assertEqual(result.status.value, "failed")
            self.assertIsNotNone(result.failure)
            assert result.failure is not None
            self.assertEqual(result.failure.kind, FailureKind.INTEGRITY)
            self.assertEqual(result.failure.code, "task_input_restore")
            self.assertIsNone(result.output_text)
            self.assertEqual(result.available_outputs, frozenset())

    def test_existing_failures_remain_primary_when_cleanup_fails(self) -> None:
        cases = (
            (
                "timeout",
                subprocess.TimeoutExpired([], 1, output=b"partial", stderr=b"error"),
                FailureKind.TIMEOUT,
                "timed_out",
            ),
            ("process", subprocess.CompletedProcess([], 7, stdout="", stderr="error"), FailureKind.PROCESS, "failed"),
            ("interrupted", KeyboardInterrupt(), FailureKind.INTERRUPTED, "interrupted"),
        )
        for name, process_result, expected_kind, expected_status in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                request = self.request(root)
                (request.workspace / "task_inputs").mkdir()
                (request.workspace / "task_inputs" / "input.txt").write_text("original", encoding="utf-8")
                executor = CursorExecutor(command="agent")
                executor._version = "fake-cursor"
                with (
                    patch(
                        "eval_harness.executors.cursor.subprocess.run",
                        side_effect=process_result if isinstance(process_result, BaseException) else None,
                        return_value=process_result if not isinstance(process_result, BaseException) else None,
                    ),
                    patch("eval_harness.executors.cursor._tree_digest", return_value="baseline"),
                    patch.object(CursorExecutor, "_restore_task_inputs", side_effect=OSError("restore denied")),
                ):
                    result = executor.execute(request)
                self.assertEqual(result.status.value, expected_status)
                self.assertIsNotNone(result.failure)
                assert result.failure is not None
                self.assertEqual(result.failure.kind, expected_kind)
                self.assertIsNone(result.output_text)
                self.assertEqual(result.available_outputs, frozenset())

    def test_cleanup_interrupt_is_typed_as_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            request = self.request(root)
            (request.workspace / "task_inputs").mkdir()
            (request.workspace / "task_inputs" / "input.txt").write_text("original", encoding="utf-8")
            executor = CursorExecutor(command="agent")
            executor._version = "fake-cursor"
            success = json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "duration_ms": 1,
                    "duration_api_ms": 1,
                    "result": "answer",
                    "session_id": "session",
                }
            )
            with (
                patch(
                    "eval_harness.executors.cursor.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 0, stdout=success, stderr=""),
                ),
                patch("eval_harness.executors.cursor._tree_digest", return_value="baseline"),
                patch.object(CursorExecutor, "_restore_task_inputs", side_effect=KeyboardInterrupt),
            ):
                result = executor.execute(request)
            self.assertEqual(result.status.value, "interrupted")
            self.assertIsNotNone(result.failure)
            assert result.failure is not None
            self.assertEqual(result.failure.kind, FailureKind.INTERRUPTED)
            self.assertEqual(result.failure.code, "interrupted")
            self.assertIsNone(result.output_text)
            self.assertEqual(result.available_outputs, frozenset())

    def test_subscription_environment_removes_api_auth(self) -> None:
        env = subscription_environment(
            {
                "PATH": "/bin",
                "CURSOR_API_KEY": "secret",
                "CURSOR_AUTH_TOKEN": "token",
                "CURSOR_LOCAL_PROVIDER_URL": "http://127.0.0.1:9999",
                "CURSOR_BEDROCK_ENDPOINT_URL": "https://bedrock.example.invalid",
                "KEEP_ME": "yes",
            }
        )
        self.assertNotIn("CURSOR_API_KEY", env)
        self.assertNotIn("CURSOR_AUTH_TOKEN", env)
        self.assertNotIn("CURSOR_LOCAL_PROVIDER_URL", env)
        self.assertNotIn("CURSOR_BEDROCK_ENDPOINT_URL", env)
        self.assertEqual(env["KEEP_ME"], "yes")


if __name__ == "__main__":
    unittest.main()
