# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

from eval_harness.benchmarks.bigcodebench import BigCodeBenchBenchmark
from eval_harness.capabilities import ExecutorOutput
from eval_harness.evaluators.base import EvaluationCandidate, EvaluationRequest, EvaluatorType
from eval_harness.evaluators.bigcodebench import BigCodeBenchEvaluator, _native_bigcodebench_evaluate
from eval_harness.grader_sandbox import GraderSandboxPreflight, GraderSandboxSpec
from eval_harness.executors.base import ExecutionResult, ExecutionStatus
from eval_harness.failures import Failure, FailureImpact, FailureKind


class BigCodeBenchBenchmarkTests(unittest.TestCase):
    def ready(self, evaluator: BigCodeBenchEvaluator) -> None:
        evaluator._sandbox_spec = cast(GraderSandboxSpec, MagicMock())
        evaluator._sandbox_preflight = GraderSandboxPreflight(
            True, "0.12.0", "bigcodebench-bwrap-v1", "spec", "manifest", "attestation", ()
        )

    def benchmark(self, root: Path) -> BigCodeBenchBenchmark:
        return BigCodeBenchBenchmark(
            root=root,
            dataset_path=root / "bigcodebench.jsonl",
            prepare_script=root / "prepare.py",
        )

    def write_task(self, benchmark: BigCodeBenchBenchmark) -> None:
        benchmark.dataset_path.write_text(
            json.dumps(
                {
                    "question": "Complete this function.",
                    "verifier_metadata": {
                        "task_id": "BigCodeBench/1",
                        "test": "def test_solution(): pass",
                        "entry_point": "solve",
                        "code_prompt": "def solve():",
                        "split": "hard",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def result(
        self,
        root: Path,
        *,
        output_text: str | None,
        status: ExecutionStatus = ExecutionStatus.NO_DELIVERABLE,
    ) -> ExecutionResult:
        effective_output = (
            output_text if status in {ExecutionStatus.COMPLETED, ExecutionStatus.NO_DELIVERABLE} else None
        )
        return ExecutionResult(
            runtime="test",
            task_id="BigCodeBench/1",
            executor="codex",
            executor_version="test",
            invocation_mode="codex exec",
            auth_mode="chatgpt-subscription",
            workspace=root / "executor-workspace",
            deliverables_dir=root / "executor-workspace" / "deliverables",
            status=status,
            started_at="2026-09-11T00:00:00+00:00",
            finished_at="2026-09-11T00:00:01+00:00",
            exit_code=0 if status in {ExecutionStatus.COMPLETED, ExecutionStatus.NO_DELIVERABLE} else 1,
            available_outputs=frozenset({ExecutorOutput.FINAL_TEXT}) if effective_output is not None else frozenset(),
            failure=None
            if effective_output is not None
            else Failure(FailureKind.PROCESS, "test_failure", FailureImpact.RUN),
            output_text=effective_output,
        )

    def request(self, root: Path, result: ExecutionResult) -> EvaluationRequest:
        return EvaluationRequest(
            task_id="BigCodeBench/1",
            task_prompt="Complete this function.",
            metadata={
                "task_id": "BigCodeBench/1",
                "test": "test-code",
                "entry_point": "solve",
                "code_prompt": "def solve():",
            },
            candidates=(EvaluationCandidate("policy", result),),
        )

    def test_load_tasks_preserves_codegen_prompt_and_verifier_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = self.benchmark(root)
            self.write_task(benchmark)

            task = benchmark.load_tasks(1)[0]

            self.assertEqual(task.execution.task_id, "BigCodeBench/1")
            self.assertEqual(
                task.execution.prompt,
                "Generate an executable Python function generated from the given prompt.\n\nComplete this function.",
            )
            self.assertEqual(task.evaluation["entry_point"], "solve")
            self.assertEqual(benchmark.revision, "v0.1.4")
            self.assertNotIn("evaluate", type(benchmark).__dict__)
            self.assertEqual(BigCodeBenchEvaluator.evaluator_type, EvaluatorType.EXECUTABLE_TESTS)

    def test_evaluate_uses_native_grader_outside_executor_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grader = root / "grader"
            grader.mkdir()
            evaluator = BigCodeBenchEvaluator(resource_dir=grader)
            self.ready(evaluator)
            result = self.result(root, output_text="```python\nreturn 42\n```")

            with patch(
                "eval_harness.evaluators.bigcodebench._native_bigcodebench_evaluate",
                return_value={
                    "reward": 1.0,
                    "status": "passed",
                    "extracted_model_code": "return 42",
                    "details": {},
                },
            ) as native:
                evaluation = evaluator.evaluate(self.request(root, result))

            native.assert_called_once()
            self.assertEqual(native.call_args.kwargs["resource_dir"], grader.resolve())
            self.assertEqual(evaluation.metrics, {"pass_rate": 1.0})
            self.assertEqual(evaluation.details["native_status"], "passed")
            self.assertNotEqual(evaluation.details["grader_root"], evaluation.details["executor_workspace"])

    def test_preflight_checks_runner_and_dedicated_venv_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grader = root / "grader"
            grader.mkdir()
            evaluator = BigCodeBenchEvaluator(resource_dir=grader)
            fake_spec = cast(GraderSandboxSpec, MagicMock())
            fake_preflight = GraderSandboxPreflight(
                True, "0.12.0", "bigcodebench-bwrap-v1", "spec", "manifest", "attestation", ()
            )
            with patch(
                "eval_harness.evaluators.bigcodebench.resolve_bigcodebench_sandbox_spec",
                return_value=fake_spec,
            ) as resolve, patch(
                "eval_harness.evaluators.bigcodebench.preflight_bigcodebench_sandbox",
                return_value=fake_preflight,
            ) as preflight:
                result = evaluator.preflight(root / "run")
            resolve.assert_called_once_with(grader.resolve(), forbidden_roots=(root / "run",))
            preflight.assert_called_once_with(fake_spec)
            self.assertTrue(result.ok)
            self.assertEqual(result.details, ())

    def test_failed_execution_scores_zero_without_invoking_grader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grader = root / "grader"
            grader.mkdir()
            evaluator = BigCodeBenchEvaluator(resource_dir=grader)
            self.ready(evaluator)
            result = self.result(root, output_text="```python\nreturn 42\n```", status=ExecutionStatus.FAILED)

            with patch("eval_harness.evaluators.bigcodebench._native_bigcodebench_evaluate") as native:
                evaluation = evaluator.evaluate(self.request(root, result))

            native.assert_not_called()
            self.assertEqual(evaluation.metrics, {"pass_rate": 0.0})
            self.assertFalse(evaluation.details["grader_invoked"])

    def test_successful_evaluation_requires_preflight_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grader = root / "grader"
            grader.mkdir()
            evaluator = BigCodeBenchEvaluator(resource_dir=grader)
            result = self.result(root, output_text="```python\nreturn 42\n```")

            with self.assertRaisesRegex(RuntimeError, "preflight"):
                evaluator.evaluate(self.request(root, result))

    def test_grader_directory_must_not_be_inside_executor_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "executor-workspace"
            grader = workspace / "grader"
            grader.mkdir(parents=True)
            evaluator = BigCodeBenchEvaluator(resource_dir=grader)
            self.ready(evaluator)
            result = self.result(root, output_text="```python\nreturn 42\n```")

            with self.assertRaisesRegex(RuntimeError, "grader directory must be separate"):
                evaluator.evaluate(self.request(root, result))

    def test_native_helper_uses_the_shared_attested_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resource_dir = Path(tmp)
            metadata = {
                "task_id": "BigCodeBench/1",
                "test": "test-code",
                "entry_point": "solve",
                "code_prompt": "def solve():",
            }

            fake_spec = cast(GraderSandboxSpec, MagicMock())
            fake_preflight = GraderSandboxPreflight(
                True, "0.12.0", "bigcodebench-bwrap-v1", "spec", "manifest", "attestation", ()
            )

            def fake_run(request: object, *, spec: object, preflight: object) -> object:
                self.assertEqual(spec, fake_spec)
                self.assertEqual(preflight, fake_preflight)
                self.assertEqual(getattr(request, "code"), "def solve():\n    pass\nreturn 42")
                self.assertEqual(getattr(request, "test_code"), "test-code")
                self.assertEqual(getattr(request, "entry_point"), "solve")
                from eval_harness.bigcodebench_runner import GraderNativeResult, NativeStatus

                return GraderNativeResult(NativeStatus.PASS)

            with (
                patch(
                    "resources_servers.bigcodebench.code_extraction.preprocess_code_completion",
                    return_value="return 42",
                ),
                patch(
                    "eval_harness.evaluators.bigcodebench.resolve_bigcodebench_sandbox_spec",
                    return_value=fake_spec,
                ),
                patch(
                    "eval_harness.evaluators.bigcodebench.preflight_bigcodebench_sandbox",
                    return_value=fake_preflight,
                ),
                patch("eval_harness.evaluators.bigcodebench.run_bigcodebench_sandbox", side_effect=fake_run),
            ):
                evaluation = _native_bigcodebench_evaluate(
                    "```python\nreturn 42\n```",
                    metadata,
                    resource_dir=resource_dir,
                )

            self.assertEqual(evaluation["reward"], 1.0)
            self.assertEqual(evaluation["status"], "passed")
            self.assertEqual(evaluation["extracted_model_code"], "return 42")


if __name__ == "__main__":
    unittest.main()
