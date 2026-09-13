# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TypedDict, cast
from unittest.mock import patch

import eval_harness.runner as runner_module
from eval_harness.benchmarks.base import Benchmark, BenchmarkTask
from eval_harness.benchmarks.snapshot import Availability, SnapshotError, SnapshotTaskContent, open_verified_snapshot
from eval_harness.candidate_bundle import (
    CandidateBundleError,
    SnapshotReference,
    VerifiedSnapshotBinding,
    load_candidate_bundle,
)
from eval_harness.capabilities import ExecutorCapabilities, ExecutorInput, ExecutorOutput
from eval_harness.evaluators.base import (
    EvaluationPlan,
    EvaluationRequest,
    EvaluationResult,
    EvaluationStatus,
    Evaluator,
    EvaluatorPreflightResult,
    EvaluatorType,
)
from eval_harness.executors.base import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    Executor,
    PreflightResult,
    TaskSpec,
)
from eval_harness.failures import Failure, FailureImpact, FailureKind, RunAbort
from eval_harness.interventions.base import (
    ApplicationMapping,
    Intervention,
    InterventionApplication,
    InterventionBundle,
    InterventionManifest,
    InterventionPreflightResult,
    InterventionType,
    compute_bundle_sha256,
    file_evidence,
)
from eval_harness.layout import candidate_layout
from eval_harness.provenance import RepositoryProvenance
from eval_harness.reasoning import ReasoningEffortOption
from eval_harness.run_manifest import (
    RunManifest,
    RunManifestError,
    RunResultRow,
    RunResultWriter,
    load_run_manifest,
    load_run_results,
)
from eval_harness.runner import run_benchmark


JsonObject = dict[str, object]


class SemanticChanges(TypedDict, total=False):
    model: str
    network_access_enabled: bool
    timeout_seconds: float
    intervention_content: bytes
    judge_model: str
    prompt_suffix: str


def _json_object(value: object) -> JsonObject:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise AssertionError(f"expected a JSON object, got {type(value).__name__}")
    return cast(JsonObject, value)


def _load_json(path: Path) -> JsonObject:
    return _json_object(json.loads(path.read_text(encoding="utf-8")))


class FixtureBenchmark(Benchmark):
    """Unknown-name benchmark whose snapshot and execution views are observable."""

    name = "unknown-fixture-benchmark"
    source = "fixture-source"
    source_availability = Availability.AVAILABLE
    revision = "fixture-revision"
    revision_availability = Availability.AVAILABLE

    def __init__(
        self,
        *,
        task_count: int = 2,
        events: list[str] | None = None,
        prompt_suffix: str = "",
    ) -> None:
        self.task_count = task_count
        self.events = events if events is not None else []
        self.prompt_suffix = prompt_suffix
        self.prepare_calls = 0
        self.load_tasks_calls = 0
        self.snapshot_task_calls = 0
        self.materialize_calls = 0
        self.network_policies: list[str] = []

    def is_prepared(self) -> bool:
        return True

    def prepare(self) -> None:
        self.prepare_calls += 1
        self.events.append("prepare")

    def load_tasks(self, limit: int) -> list[BenchmarkTask]:
        self.load_tasks_calls += 1
        self.events.append("load_tasks")
        return [
            BenchmarkTask(
                execution=TaskSpec(
                    task_id=f"fixture-{index}",
                    prompt=f"canonical prompt {index}{self.prompt_suffix}",
                ),
                evaluation={"expected": f"expected-{index}"},
            )
            for index in range(min(limit, self.task_count))
        ]

    def materialize(self, task: BenchmarkTask, workspace: Path) -> list[str]:
        self.materialize_calls += 1
        self.events.append(f"materialize:{task.execution.task_id}")
        task_id = task.execution.task_id
        input_relative = f"task_inputs/{task_id}.txt"
        evaluation_relative = f"task_inputs/{task_id}-evaluation-only.txt"
        input_path = workspace / input_relative
        evaluation_path = workspace / evaluation_relative
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_bytes(task.execution.prompt.encode("utf-8"))
        evaluation_path.write_bytes(f"evaluation-only-{task_id}".encode("utf-8"))
        return [input_relative, evaluation_relative]

    def snapshot_task(self, task: BenchmarkTask, workspace: Path) -> SnapshotTaskContent:
        self.snapshot_task_calls += 1
        self.events.append(f"snapshot_task:{task.execution.task_id}")
        materialized = self.materialize(task, workspace)
        return SnapshotTaskContent(
            evaluation_data=dict(task.evaluation),
            files=((materialized[0], workspace / materialized[0]),),
            evaluation_files=((materialized[1], workspace / materialized[1]),),
        )

    def execution_task(self, task: BenchmarkTask, workspace: Path, *, network_policy: str) -> TaskSpec:
        del workspace
        self.network_policies.append(network_policy)
        self.events.append(f"execution_task:{task.execution.task_id}")
        return TaskSpec(
            task_id=task.execution.task_id,
            prompt=f"fixture execution wrapper; network_policy={network_policy}\n{task.execution.prompt}",
        )


class FixtureIntervention(Intervention):
    name = "fixture-intervention"
    intervention_type = InterventionType.PROMPT_OVERLAY

    def __init__(
        self,
        *,
        content: bytes = b"reviewed fixture overlay",
        events: list[str] | None = None,
        fail_validation_task_id: str | None = None,
    ) -> None:
        self.content = content
        self.events = events if events is not None else []
        self.fail_validation_task_id = fail_validation_task_id
        self.validated_tasks: list[TaskSpec] = []
        self.applied_tasks: list[TaskSpec] = []
        self._bundle: InterventionBundle | None = None

    def preflight(self) -> InterventionPreflightResult:
        entry = file_evidence("overlay.txt", self.content)
        manifest = InterventionManifest(
            intervention_id="fixture-intervention-id",
            intervention_type=self.intervention_type,
            source_revision="fixture-intervention-revision",
            revision_status="available",
            files=(entry,),
            bundle_sha256=compute_bundle_sha256(((entry.path, self.content),)),
            application=ApplicationMapping(method="prompt-overlay", target="task.prompt"),
        )
        self._bundle = InterventionBundle(root=None, manifest=manifest)
        self.events.append("intervention_preflight")
        return InterventionPreflightResult(
            name=self.name,
            intervention_type=self.intervention_type,
            ok=True,
            bundle=self._bundle,
            details=("fixture intervention ready",),
        )

    def validate_task(self, task: TaskSpec) -> None:
        self.validated_tasks.append(task)
        self.events.append(f"validate_intervention:{task.task_id}")
        if task.task_id == self.fail_validation_task_id:
            raise ValueError(f"invalid fixture intervention task {task.task_id}")

    def apply(self, task: TaskSpec, workspace: Path, *, application_run_id: str) -> InterventionApplication:
        del workspace
        self.events.append(f"apply_intervention:{task.task_id}")
        self.applied_tasks.append(task)
        if self._bundle is None:
            raise AssertionError("intervention preflight was not called")
        effective_task = TaskSpec(
            task_id=task.task_id,
            prompt=f"[fixture overlay]\n{self.content.decode('utf-8')}\n{task.prompt}",
        )
        manifest = self._bundle.manifest
        return InterventionApplication(
            application_run_id=application_run_id,
            task=effective_task,
            materialized_files=(),
            bundle_sha256=manifest.bundle_sha256,
            manifest_sha256=manifest.manifest_sha256 or "",
            application=manifest.application,
        )


class FixtureExecutor(Executor):
    name = "fixture-executor"
    runtime = "fixture-runtime"
    invocation_mode = "fixture"
    reasoning_effort: ReasoningEffortOption = None
    capabilities = ExecutorCapabilities(
        inputs=frozenset({ExecutorInput.PROMPT_TEXT, ExecutorInput.WORKSPACE_FILES}),
        outputs=frozenset({ExecutorOutput.FINAL_TEXT, ExecutorOutput.ARTIFACT_FILES}),
    )

    def __init__(
        self,
        *,
        network_access_enabled: object = False,
        events: list[str] | None = None,
        result_model_id: str | None = "fixture-result-model-id",
        result_metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.network_access_enabled = cast(bool, network_access_enabled)
        self.events = events if events is not None else []
        self.result_model_id = result_model_id
        self.result_metadata = dict(result_metadata or {})
        self.preflight_calls = 0
        self.execute_calls = 0
        self.requests: list[ExecutionRequest] = []
        self.workspace_files: list[tuple[str, ...]] = []

    def preflight(self) -> PreflightResult:
        self.preflight_calls += 1
        self.events.append("executor_preflight")
        return PreflightResult(
            executor=self.name,
            ok=True,
            version="fixture-executor-1",
            auth_mode="fixture-auth",
        )

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.execute_calls += 1
        self.events.append(f"execute:{request.task.task_id}")
        self.requests.append(request)
        files = tuple(
            str(path.relative_to(request.workspace)) for path in sorted(request.workspace.rglob("*")) if path.is_file()
        )
        self.workspace_files.append(files)
        request.executor_dir.mkdir(parents=True, exist_ok=True)
        (request.executor_dir / "stdout.log").write_bytes(b"fixture stdout\n")
        request.deliverables_dir.mkdir(parents=True, exist_ok=True)
        (request.deliverables_dir / "answer.txt").write_bytes(f"artifact-{request.task.task_id}".encode("utf-8"))
        output = f"output-{request.task.task_id}"
        return ExecutionResult(
            task_id=request.task.task_id,
            executor=self.name,
            executor_version="fixture-executor-1",
            invocation_mode=self.invocation_mode,
            auth_mode="fixture-auth",
            workspace=request.workspace,
            deliverables_dir=request.deliverables_dir,
            status=ExecutionStatus.COMPLETED,
            started_at="2026-09-13T00:00:00+00:00",
            finished_at="2026-09-13T00:00:01+00:00",
            exit_code=0,
            available_outputs=frozenset({ExecutorOutput.FINAL_TEXT, ExecutorOutput.ARTIFACT_FILES}),
            failure=None,
            runtime=self.runtime,
            output_text=output,
            metadata=self.result_metadata,
            reasoning_effort_requested=None,
            model_id=self.result_model_id,
        )


class SystemicFailureExecutor(FixtureExecutor):
    def __init__(self, failure: Failure, *, events: list[str] | None = None) -> None:
        super().__init__(events=events)
        self.systemic_failure = failure

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        result = super().execute(request)
        return replace(
            result,
            status=ExecutionStatus.FAILED,
            output_text=None,
            available_outputs=frozenset(),
            failure=self.systemic_failure,
            exit_code=1,
        )


class OutputCapabilityMismatchExecutor(FixtureExecutor):
    capabilities = ExecutorCapabilities(
        inputs=frozenset({ExecutorInput.PROMPT_TEXT, ExecutorInput.WORKSPACE_FILES}),
        outputs=frozenset(),
    )


class SymlinkArtifactExecutor(FixtureExecutor):
    def __init__(self, artifact_target: Path) -> None:
        super().__init__()
        self.artifact_target = artifact_target

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        result = super().execute(request)
        artifact = request.deliverables_dir / "answer.txt"
        artifact.unlink()
        artifact.symlink_to(self.artifact_target)
        return result


class ResultPathMismatchExecutor(FixtureExecutor):
    def __init__(self, *, replacement: Path, workspace: bool) -> None:
        super().__init__()
        self.replacement = replacement
        self.workspace = workspace

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        result = super().execute(request)
        if self.workspace:
            return replace(result, workspace=self.replacement)
        return replace(result, deliverables_dir=self.replacement)


class DestinationCollisionExecutor(FixtureExecutor):
    def __init__(self, destination: Path) -> None:
        super().__init__()
        self.destination = destination

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        result = super().execute(request)
        self.destination.mkdir(parents=True)
        (self.destination / "collision-marker").write_text("occupied", encoding="utf-8")
        return result


class MissingNetworkExecutor(FixtureExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.__dict__.pop("network_access_enabled", None)


class FixtureEvaluator(Evaluator):
    name = "fixture-evaluator"
    evaluator_type = EvaluatorType.BENCHMARK_NATIVE

    def __init__(
        self,
        *,
        events: list[str] | None = None,
        fail_plan_task_id: str | None = None,
        evaluator_type: EvaluatorType = EvaluatorType.BENCHMARK_NATIVE,
        judge_model: str | None = None,
        preflight_details: Sequence[str] = (),
        handoff_root: Path | None = None,
    ) -> None:
        self.events = events if events is not None else []
        self.fail_plan_task_id = fail_plan_task_id
        self.evaluator_type = evaluator_type
        self.judge_model = judge_model
        self.preflight_details = tuple(preflight_details)
        self.handoff_root = handoff_root
        self.preflight_calls = 0
        self.validate_plans: list[EvaluationPlan] = []
        self.evaluation_requests: list[EvaluationRequest] = []
        self.durability_checks: list[str] = []

    def preflight(self, run_dir: Path | None = None) -> EvaluatorPreflightResult:
        del run_dir
        self.preflight_calls += 1
        self.events.append("evaluator_preflight")
        judge_applicable = self.evaluator_type in {EvaluatorType.LLM_RUBRIC, EvaluatorType.PAIRWISE}
        return EvaluatorPreflightResult(
            name=self.name,
            evaluator_type=self.evaluator_type,
            ok=True,
            version="fixture-evaluator-1",
            details=self.preflight_details,
            judge_executor="fixture-judge" if judge_applicable else None,
            judge_executor_version="fixture-judge-1" if judge_applicable else None,
            judge_auth_mode="fixture-judge-auth" if judge_applicable else None,
            judge_model=self.judge_model if judge_applicable else None,
        )

    def validate_plan(self, plan: EvaluationPlan) -> None:
        self.validate_plans.append(plan)
        self.events.append(f"validate_plan:{plan.task_id}")
        if plan.task_id == self.fail_plan_task_id:
            raise ValueError(f"invalid fixture evaluation plan {plan.task_id}")

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        self.evaluation_requests.append(request)
        self.events.append(f"evaluate:{request.task_id}")
        if self.handoff_root is not None:
            manifest = load_run_manifest(self.handoff_root)
            binding = VerifiedSnapshotBinding.load(self.handoff_root / manifest.snapshot_path)
            loaded = load_run_results(manifest, snapshot_binding=binding)
            if not loaded or loaded[-1][0].candidate_id != request.candidates[0].candidate_id:
                raise AssertionError("evaluator observed an unindexed candidate")
            self.durability_checks.append(loaded[-1][0].candidate_id)
        return EvaluationResult(
            task_id=request.task_id,
            status=EvaluationStatus.COMPLETED,
            metrics={"score": 1.0},
            details={"canonical_prompt": request.task_prompt},
        )


class GenerationHandoffTests(unittest.TestCase):
    def _fresh_fixture_handoff(
        self, root: Path
    ) -> tuple[Path, FixtureEvaluator, FixtureExecutor, RunManifest, VerifiedSnapshotBinding]:
        out = root / "run"
        runtime = root / "runtime"
        evaluator = FixtureEvaluator()
        executor = FixtureExecutor()
        run_benchmark(
            FixtureBenchmark(task_count=1),
            evaluator,
            executor,
            out_dir=out,
            runtime_root=runtime,
            limit=1,
            intervention=FixtureIntervention(),
        )
        manifest = load_run_manifest(out)
        binding = VerifiedSnapshotBinding.load(out / manifest.snapshot_path)
        self.assertEqual(len(load_run_results(manifest, snapshot_binding=binding)), 1)
        shutil.rmtree(runtime)
        return out, evaluator, executor, manifest, binding

    def test_successful_handoff_seals_and_indexes_before_each_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "run"
            runtime = root / "runtime"
            events: list[str] = []
            benchmark = FixtureBenchmark(events=events)
            evaluator = FixtureEvaluator(events=events, handoff_root=out)
            intervention = FixtureIntervention(events=events)
            executor = FixtureExecutor(events=events)
            index_path = out / "candidate-results.jsonl"

            real_fsync = os.fsync

            def record_index_fsync(descriptor: int) -> None:
                real_fsync(descriptor)
                try:
                    descriptor_info = os.fstat(descriptor)
                    index_info = index_path.stat()
                except OSError:
                    return
                if (
                    stat.S_ISREG(descriptor_info.st_mode)
                    and stat.S_ISREG(index_info.st_mode)
                    and descriptor_info.st_dev == index_info.st_dev
                    and descriptor_info.st_ino == index_info.st_ino
                    and descriptor_info.st_size > 0
                ):
                    events.append("candidate_index_fsync")

            with patch.object(os, "fsync", side_effect=record_index_fsync):
                run_benchmark(
                    benchmark,
                    evaluator,
                    executor,
                    out_dir=out,
                    runtime_root=runtime,
                    limit=2,
                    model="requested-model",
                    intervention=intervention,
                )

            manifest = load_run_manifest(out)
            self.assertEqual(manifest.snapshot_path, "snapshot")
            self.assertEqual(manifest.results_path, "candidate-results.jsonl")
            binding = VerifiedSnapshotBinding.load(out / manifest.snapshot_path)
            loaded = load_run_results(manifest, snapshot_binding=binding)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(
                evaluator.durability_checks,
                [f"{manifest.run_id}:candidate-00000000", f"{manifest.run_id}:candidate-00000001"],
            )
            index_fsync_positions = [index for index, event in enumerate(events) if event == "candidate_index_fsync"]
            self.assertEqual(len(index_fsync_positions), 2)
            for sequence in range(2):
                self.assertLess(index_fsync_positions[sequence], events.index(f"evaluate:fixture-{sequence}"))
            for sequence, ((row, bundle), reference) in enumerate(zip(loaded, manifest.ordered_tasks, strict=True)):
                self.assertEqual(row.sequence, sequence)
                self.assertEqual(row.candidate_id, f"{manifest.run_id}:candidate-{sequence:08d}")
                self.assertEqual(row.bundle_path, f"candidates/candidate-{sequence:08d}")
                self.assertEqual(bundle.snapshot_reference, reference)
                self.assertEqual(bundle.canonical_task_prompt, f"canonical prompt {sequence}")
                self.assertIn("fixture overlay", bundle.effective_executor_prompt)
                self.assertIn("requested-model", bundle.executor_evidence.requested_model or "")
                self.assertEqual(bundle.outcome.output_text, f"output-fixture-{sequence}")
                self.assertIn(ExecutorOutput.FINAL_TEXT, bundle.outcome.available_outputs)
                self.assertIn(ExecutorOutput.ARTIFACT_FILES, bundle.outcome.available_outputs)
                self.assertEqual(bundle.read_artifact("answer.txt"), f"artifact-fixture-{sequence}".encode())

    def test_handoff_survives_runtime_deletion_and_out_relocation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "run"
            runtime = root / "runtime"
            run_benchmark(
                FixtureBenchmark(),
                FixtureEvaluator(),
                FixtureExecutor(),
                out_dir=out,
                runtime_root=runtime,
                limit=2,
                intervention=FixtureIntervention(),
            )
            shutil.rmtree(runtime)
            relocated = root / "relocated-run"
            out.rename(relocated)

            manifest = load_run_manifest(relocated)
            binding = VerifiedSnapshotBinding.load(relocated / manifest.snapshot_path)
            loaded = load_run_results(manifest, snapshot_binding=binding)
            self.assertEqual(len(loaded), 2)
            self.assertFalse(runtime.exists())
            self.assertFalse(relocated.joinpath("tasks").exists())
            for row, bundle in loaded:
                self.assertEqual(bundle.snapshot_reference, row.snapshot_reference)
                self.assertIsInstance(bundle.outcome.output_text, str)
                self.assertEqual(
                    bundle.read_artifact("answer.txt"), f"artifact-{row.snapshot_reference.task_id}".encode()
                )

    def test_handoff_readers_reject_fresh_snapshot_and_candidate_tampering(self) -> None:
        snapshot_cases = (
            ("snapshot_execution_blob", "execution_view", "task_inputs/fixture-0.txt"),
            ("snapshot_evaluation_blob", "evaluation_view", "task_inputs/fixture-0-evaluation-only.txt"),
        )
        for case, view_name, expected_path in snapshot_cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                out, evaluator, executor, manifest, binding = self._fresh_fixture_handoff(root)
                snapshot_root = out / manifest.snapshot_path
                snapshot_manifest_path = snapshot_root / "benchmark-snapshot.json"
                snapshot_payload = _load_json(snapshot_manifest_path)
                raw_tasks = snapshot_payload.get("tasks")
                if type(raw_tasks) is not list or not raw_tasks or type(raw_tasks[0]) is not dict:
                    raise AssertionError("fixture snapshot did not contain one task manifest")
                task_payload = cast(JsonObject, raw_tasks[0])
                view_payload = _json_object(task_payload[view_name])
                raw_files = view_payload.get("files")
                if type(raw_files) is not list:
                    raise AssertionError("fixture snapshot view did not contain a file manifest")
                file_payload = next(
                    (
                        cast(JsonObject, item)
                        for item in raw_files
                        if type(item) is dict and item.get("path") == expected_path
                    ),
                    None,
                )
                if file_payload is None or type(file_payload.get("sha256")) is not str:
                    raise AssertionError(f"fixture snapshot did not contain {expected_path}")
                (snapshot_root / "blobs" / "sha256" / cast(str, file_payload["sha256"])).write_bytes(
                    b"tampered snapshot bytes"
                )
                with self.assertRaises(SnapshotError):
                    VerifiedSnapshotBinding.load(snapshot_root)
                self.assertEqual(len(evaluator.evaluation_requests), 1)
                self.assertEqual(executor.execute_calls, 1)

        candidate_cases = (
            "candidate_artifact_blob",
            "candidate_missing_blob",
            "candidate_manifest_text",
            "candidate_manifest_hash",
        )
        for case in candidate_cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                out, evaluator, executor, manifest, binding = self._fresh_fixture_handoff(root)
                loaded = load_run_results(manifest, snapshot_binding=binding)
                bundle_root = loaded[0][1].root
                if case in {"candidate_artifact_blob", "candidate_missing_blob"}:
                    artifact = loaded[0][1].outcome.artifacts[0]
                    artifact_blob = bundle_root / "blobs" / "sha256" / artifact.sha256
                    if case == "candidate_artifact_blob":
                        artifact_blob.write_bytes(b"tampered artifact bytes")
                    else:
                        artifact_blob.unlink()
                else:
                    candidate_manifest_path = bundle_root / "candidate-bundle.json"
                    candidate_payload = _load_json(candidate_manifest_path)
                    candidate_payload["effective_executor_prompt"] = (
                        "tampered candidate prompt"
                        if case == "candidate_manifest_text"
                        else candidate_payload["effective_executor_prompt"]
                    )
                    if case == "candidate_manifest_hash":
                        candidate_payload["bundle_sha256"] = "0" * 64
                    candidate_manifest_path.write_bytes(
                        json.dumps(
                            candidate_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    )
                with self.assertRaises(RunManifestError):
                    load_run_results(manifest, snapshot_binding=binding)
                self.assertEqual(len(evaluator.evaluation_requests), 1)
                self.assertEqual(executor.execute_calls, 1)

    def test_handoff_reader_rejects_fresh_malformed_and_changed_index_links(self) -> None:
        cases = ("malformed", "changed_path", "changed_digest")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                out, evaluator, executor, manifest, binding = self._fresh_fixture_handoff(root)
                index_path = out / manifest.results_path
                if case == "malformed":
                    index_path.write_bytes(b"not-json\n")
                else:
                    lines = index_path.read_text(encoding="utf-8").splitlines()
                    if len(lines) != 1:
                        raise AssertionError("fixture run did not contain one result row")
                    row_payload = _json_object(json.loads(lines[0]))
                    row_payload["bundle_path"] = "../outside" if case == "changed_path" else row_payload["bundle_path"]
                    if case == "changed_digest":
                        row_payload["bundle_sha256"] = "0" * 64
                    index_path.write_bytes(
                        (json.dumps(row_payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                    )
                with self.assertRaises(RunManifestError):
                    load_run_results(manifest, snapshot_binding=binding)
                self.assertEqual(len(evaluator.evaluation_requests), 1)
                self.assertEqual(executor.execute_calls, 1)

    def test_snapshot_and_bound_materialization_are_single_pass_and_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events: list[str] = []
            benchmark = FixtureBenchmark(events=events)
            evaluator = FixtureEvaluator(events=events)
            executor = FixtureExecutor(events=events)
            materialize_calls: list[str] = []
            original_materialize = VerifiedSnapshotBinding.materialize_execution

            def counted_materialize(
                binding: VerifiedSnapshotBinding,
                reference: SnapshotReference,
                workspace: Path,
            ) -> tuple[str, ...]:
                materialize_calls.append(reference.task_id)
                return original_materialize(binding, reference, workspace)

            with patch.object(
                VerifiedSnapshotBinding,
                "materialize_execution",
                new=counted_materialize,
            ):
                run_benchmark(
                    benchmark,
                    evaluator,
                    executor,
                    out_dir=root / "run",
                    limit=2,
                    intervention=FixtureIntervention(events=events),
                )

            self.assertEqual(benchmark.prepare_calls, 1)
            self.assertEqual(benchmark.load_tasks_calls, 1)
            self.assertEqual(benchmark.snapshot_task_calls, 2)
            self.assertEqual(benchmark.materialize_calls, 2)
            self.assertEqual(materialize_calls, ["fixture-0", "fixture-1"])
            self.assertEqual(executor.execute_calls, 2)
            self.assertEqual(len(evaluator.validate_plans), 2)
            first_execution = next(index for index, event in enumerate(events) if event == "execute:fixture-0")
            self.assertTrue(
                all(
                    index < first_execution for index, event in enumerate(events) if event.startswith("validate_plan:")
                )
            )
            self.assertEqual(
                executor.workspace_files,
                [("task_inputs/fixture-0.txt",), ("task_inputs/fixture-1.txt",)],
            )
            for plan in evaluator.validate_plans:
                self.assertEqual(plan.metadata["expected"], f"expected-{plan.task_id.removeprefix('fixture-')}")

    def test_network_provenance_is_typed_and_propagates_to_wrapper_and_handoff(self) -> None:
        for enabled in (True, False):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                out = root / "run"
                benchmark = FixtureBenchmark(task_count=1)
                executor = FixtureExecutor(network_access_enabled=enabled)
                run_benchmark(
                    benchmark,
                    FixtureEvaluator(),
                    executor,
                    out_dir=out,
                    limit=1,
                    intervention=FixtureIntervention(),
                )
                policy = "enabled" if enabled else "disabled"
                self.assertEqual(benchmark.network_policies, [policy])
                metadata = _load_json(out / "run-metadata.json")
                self.assertEqual(metadata["network_policy"], policy)
                configuration = _json_object(metadata["configuration"])
                self.assertEqual(configuration["network_policy"], policy)
                manifest = load_run_manifest(out)
                binding = VerifiedSnapshotBinding.load(out / manifest.snapshot_path)
                bundle = load_run_results(manifest, snapshot_binding=binding)[0][1]
                self.assertIn(f"network_policy={policy}", bundle.effective_executor_prompt)

        for invalid in (0, 1, None):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                benchmark = FixtureBenchmark(task_count=1)
                executor = FixtureExecutor(network_access_enabled=invalid)
                with self.assertRaises(TypeError):
                    run_benchmark(
                        benchmark,
                        FixtureEvaluator(),
                        executor,
                        out_dir=root / "run",
                        runtime_root=root / "runtime",
                        limit=1,
                    )
                self.assertEqual(benchmark.prepare_calls, 0)
                self.assertEqual(benchmark.load_tasks_calls, 0)
                self.assertEqual(executor.execute_calls, 0)
                self.assertFalse((root / "run").exists())
                self.assertFalse((root / "runtime").exists())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            benchmark = FixtureBenchmark(task_count=1)
            executor = MissingNetworkExecutor()
            with self.assertRaises(AttributeError):
                run_benchmark(
                    benchmark,
                    FixtureEvaluator(),
                    executor,
                    out_dir=root / "run",
                    runtime_root=root / "runtime",
                    limit=1,
                )
            self.assertEqual(benchmark.prepare_calls, 0)
            self.assertEqual(executor.execute_calls, 0)
            self.assertFalse((root / "run").exists())
            self.assertFalse((root / "runtime").exists())

    def test_semantic_fingerprints_ignore_roots_and_repository_evidence(self) -> None:
        def run_once(
            destination: Path,
            *,
            repository: RepositoryProvenance,
            model: str | None = None,
            network_access_enabled: bool = False,
            timeout_seconds: float = 123.0,
            intervention_content: bytes = b"reviewed fixture overlay",
            judge_model: str = "judge-a",
            prompt_suffix: str = "",
        ) -> JsonObject:
            destination.mkdir(parents=True)
            with (
                patch.object(runner_module, "repository_provenance", return_value=repository),
                patch.dict(os.environ, {"FIXTURE_SECRET": "environment-secret"}),
            ):
                run_benchmark(
                    FixtureBenchmark(prompt_suffix=prompt_suffix),
                    FixtureEvaluator(
                        evaluator_type=EvaluatorType.LLM_RUBRIC,
                        judge_model=judge_model,
                        preflight_details=("preflight-secret",),
                    ),
                    FixtureExecutor(
                        network_access_enabled=network_access_enabled,
                        result_model_id="result-model-id",
                        result_metadata={"executor-secret": "credential-secret"},
                    ),
                    out_dir=destination / "out",
                    runtime_root=destination / "runtime",
                    limit=1,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    intervention=FixtureIntervention(content=intervention_content),
                )
            return _load_json(destination / "out" / "run-metadata.json")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = run_once(
                root / "first",
                repository=RepositoryProvenance("a" * 40, "available", "dirty"),
            )
            second = run_once(
                root / "second",
                repository=RepositoryProvenance("b" * 40, "available", "clean"),
            )
            self.assertEqual(first["configuration_sha256"], second["configuration_sha256"])
            self.assertEqual(first["run_fingerprint_sha256"], second["run_fingerprint_sha256"])
            self.assertNotEqual(first["run_id"], second["run_id"])

            configuration = _json_object(first["configuration"])
            intervention_configuration = _json_object(configuration["intervention"])
            evaluator_configuration = _json_object(configuration["evaluator"])
            self.assertNotIn("runtime_layout", configuration)
            self.assertNotIn("status", configuration)
            self.assertNotIn("status", intervention_configuration)
            self.assertNotIn("source_reference", intervention_configuration)
            self.assertNotIn("preflight_details", evaluator_configuration)
            serialized_configuration = json.dumps(configuration, sort_keys=True)
            for forbidden in (
                str(root / "first" / "out"),
                str(root / "first" / "runtime"),
                "preflight-secret",
                "environment-secret",
                "credential-secret",
                "result-model-id",
                "condition-label",
                "arm-label",
            ):
                self.assertNotIn(forbidden, serialized_configuration)

            changed_semantics: tuple[SemanticChanges, ...] = (
                {"model": "different-model"},
                {"network_access_enabled": True},
                {"timeout_seconds": 456.0},
                {"intervention_content": b"different overlay"},
                {"judge_model": "judge-b"},
                {"prompt_suffix": " changed snapshot"},
            )
            for index, changes in enumerate(changed_semantics):
                changed = run_once(
                    root / f"changed-{index}",
                    repository=RepositoryProvenance("c" * 40, "available", "dirty"),
                    **changes,
                )
                self.assertNotEqual(first["run_fingerprint_sha256"], changed["run_fingerprint_sha256"])
                if "prompt_suffix" not in changes:
                    self.assertNotEqual(first["configuration_sha256"], changed["configuration_sha256"])

    def test_prepare_and_repository_provenance_precede_run_root_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "run"
            runtime = root / "runtime"
            benchmark = FixtureBenchmark(task_count=1)
            observations: list[tuple[int, bool, bool, bool]] = []

            def observe_provenance(_repository_root: Path) -> RepositoryProvenance:
                observations.append(
                    (
                        benchmark.prepare_calls,
                        out.exists(),
                        runtime.exists(),
                        any(path.name.startswith(".run.staging-") for path in root.iterdir()),
                    )
                )
                return RepositoryProvenance("a" * 40, "available", "clean")

            with patch.object(runner_module, "repository_provenance", side_effect=observe_provenance):
                run_benchmark(
                    benchmark,
                    FixtureEvaluator(),
                    FixtureExecutor(),
                    out_dir=out,
                    runtime_root=runtime,
                    limit=1,
                    intervention=FixtureIntervention(),
                )
            self.assertEqual(benchmark.prepare_calls, 1)
            self.assertEqual(observations, [(1, False, False, False)])

    def test_systemic_executor_failure_is_sealed_indexed_before_abort(self) -> None:
        failures = (
            Failure(FailureKind.AUTH, "fixture-auth", FailureImpact.RUN),
            Failure(FailureKind.QUOTA, "fixture-quota", FailureImpact.RUN),
            Failure(FailureKind.PROTOCOL, "fixture-protocol", FailureImpact.RUN),
            Failure(FailureKind.INTEGRITY, "fixture-integrity", FailureImpact.RUN),
        )
        for failure in failures:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                out = root / "run"
                events: list[str] = []
                benchmark = FixtureBenchmark(task_count=2, events=events)
                evaluator = FixtureEvaluator(events=events)
                executor = SystemicFailureExecutor(failure, events=events)

                with self.assertRaises(RunAbort) as raised:
                    run_benchmark(
                        benchmark,
                        evaluator,
                        executor,
                        out_dir=out,
                        limit=2,
                        intervention=FixtureIntervention(events=events),
                    )

                self.assertEqual(raised.exception.failure, failure)
                self.assertEqual(executor.execute_calls, 1)
                self.assertEqual(evaluator.evaluation_requests, [])
                self.assertNotIn("execute:fixture-1", events)

                manifest = load_run_manifest(out)
                binding = VerifiedSnapshotBinding.load(out / manifest.snapshot_path)
                loaded = load_run_results(manifest, snapshot_binding=binding)
                self.assertEqual(len(loaded), 1)
                row, bundle = loaded[0]
                self.assertEqual(row.sequence, 0)
                self.assertEqual(bundle.outcome.status, ExecutionStatus.FAILED)
                self.assertEqual(bundle.outcome.failure, failure)
                self.assertEqual(bundle.outcome.available_outputs, frozenset())
                self.assertIsNone(bundle.outcome.output_text)
                self.assertEqual(
                    bundle.outcome.failure,
                    Failure(failure.kind, failure.code, failure.impact),
                )

                legacy_rows = [
                    json.loads(line) for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(len(legacy_rows), 1)
                self.assertEqual(legacy_rows[0]["evaluation"]["status"], "skipped")
                self.assertEqual(
                    legacy_rows[0]["execution"]["failure"],
                    {"kind": failure.kind.value, "code": failure.code, "impact": failure.impact.value},
                )
                metadata = _load_json(out / "run-metadata.json")
                self.assertEqual(metadata["status"], "failed")

    def test_seal_index_path_and_capability_failures_fail_closed(self) -> None:
        cases: tuple[tuple[str, type[Exception], str], ...] = (
            ("capability", CandidateBundleError, "undeclared output channel"),
            ("workspace", ValueError, "outside the assigned task workspace"),
            ("deliverables", ValueError, "outside the assigned task directory"),
            ("symlink", CandidateBundleError, "artifact source cannot contain symlinks"),
            ("collision", CandidateBundleError, "candidate destination must be fresh"),
        )
        for case, expected_exception, message in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                out = root / "run"
                evaluator = FixtureEvaluator()
                if case == "capability":
                    executor: FixtureExecutor = OutputCapabilityMismatchExecutor()
                elif case == "workspace":
                    executor = ResultPathMismatchExecutor(replacement=root / "outside", workspace=True)
                elif case == "deliverables":
                    executor = ResultPathMismatchExecutor(replacement=root / "outside", workspace=False)
                elif case == "symlink":
                    target = root / "outside-artifact.txt"
                    target.write_bytes(b"outside artifact")
                    executor = SymlinkArtifactExecutor(target)
                else:
                    executor = DestinationCollisionExecutor(candidate_layout(out, 0).root)

                with self.assertRaisesRegex(expected_exception, message):
                    run_benchmark(
                        FixtureBenchmark(task_count=1),
                        evaluator,
                        executor,
                        out_dir=out,
                        limit=1,
                        intervention=FixtureIntervention(),
                    )

                self.assertEqual(evaluator.evaluation_requests, [])
                self.assertEqual(executor.execute_calls, 1)
                self.assertEqual((out / "candidate-results.jsonl").read_text(encoding="utf-8"), "")
                if case == "collision":
                    self.assertEqual(
                        (candidate_layout(out, 0).root / "collision-marker").read_text(encoding="utf-8"),
                        "occupied",
                    )
                else:
                    self.assertFalse(candidate_layout(out, 0).root.exists())
                    candidates_root = out / "candidates"
                    if candidates_root.exists():
                        self.assertEqual(tuple(candidates_root.iterdir()), ())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "run"
            evaluator = FixtureEvaluator()
            executor = FixtureExecutor()
            append_sequences: list[int] = []
            original_append = RunResultWriter.append

            def append_then_fail(writer: RunResultWriter, row: RunResultRow) -> None:
                append_sequences.append(row.sequence)
                if row.sequence == 1:
                    raise RunManifestError("forced index append failure")
                original_append(writer, row)

            with patch.object(RunResultWriter, "append", new=append_then_fail):
                with self.assertRaisesRegex(RunManifestError, "forced index append failure"):
                    run_benchmark(
                        FixtureBenchmark(task_count=2),
                        evaluator,
                        executor,
                        out_dir=out,
                        limit=2,
                        intervention=FixtureIntervention(),
                    )

            self.assertEqual(append_sequences, [0, 1])
            self.assertEqual(executor.execute_calls, 2)
            self.assertEqual(len(evaluator.evaluation_requests), 1)
            manifest = load_run_manifest(out)
            binding = VerifiedSnapshotBinding.load(out / manifest.snapshot_path)
            loaded = load_run_results(manifest, snapshot_binding=binding)
            self.assertEqual(len(loaded), 1)
            first_row, first_bundle = loaded[0]
            self.assertEqual(first_row.sequence, 0)
            self.assertEqual(first_bundle.read_artifact("answer.txt"), b"artifact-fixture-0")
            unindexed = candidate_layout(out, 1).root
            unindexed_bundle = load_candidate_bundle(unindexed, snapshot_binding=binding)
            self.assertEqual(unindexed_bundle.candidate_id, f"{manifest.run_id}:candidate-00000001")
            result_rows = (out / "candidate-results.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(result_rows), 1)
            legacy_rows = (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(legacy_rows), 2)
            self.assertEqual(json.loads(legacy_rows[1])["evaluation"]["status"], "failed")

    def test_unknown_fixture_benchmark_keeps_labels_out_of_handoff_identity_and_evaluator_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "run"
            benchmark = FixtureBenchmark(task_count=1)
            evaluator = FixtureEvaluator()
            run_benchmark(
                benchmark,
                evaluator,
                FixtureExecutor(),
                out_dir=out,
                limit=1,
                model="model-label",
                intervention=FixtureIntervention(content=b"intervention-label"),
            )
            self.assertEqual(load_run_manifest(out).run_id.__class__, str)
            forbidden = (
                "unknown-fixture-benchmark",
                "model-label",
                "intervention-label",
                "condition-label",
                "arm-label",
            )
            evaluator_input = json.dumps(
                [
                    {
                        "task_id": request.task_id,
                        "prompt": request.task_prompt,
                        "metadata": dict(request.metadata),
                        "candidate_ids": [candidate.candidate_id for candidate in request.candidates],
                    }
                    for request in evaluator.evaluation_requests
                ],
                sort_keys=True,
            )
            self.assertEqual(len(evaluator.evaluation_requests), 1)
            self.assertEqual(benchmark.name, "unknown-fixture-benchmark")
            self.assertNotIn("model-label", evaluator_input)
            self.assertNotIn("intervention-label", evaluator_input)
            manifest = load_run_manifest(out)
            binding = VerifiedSnapshotBinding.load(out / manifest.snapshot_path)
            for row, _bundle in load_run_results(manifest, snapshot_binding=binding):
                for label in forbidden:
                    self.assertNotIn(label, row.candidate_id)
                    self.assertNotIn(label, row.bundle_path)

    def test_late_plan_or_intervention_validation_fails_before_publication(self) -> None:
        cases = ("evaluator", "intervention")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                events: list[str] = []
                benchmark = FixtureBenchmark(events=events)
                evaluator = FixtureEvaluator(
                    events=events,
                    fail_plan_task_id="fixture-1" if case == "evaluator" else None,
                )
                intervention = FixtureIntervention(
                    events=events,
                    fail_validation_task_id="fixture-1" if case == "intervention" else None,
                )
                executor = FixtureExecutor(events=events)
                expected_message = (
                    "invalid fixture evaluation plan" if case == "evaluator" else "invalid fixture intervention task"
                )
                with self.assertRaisesRegex(ValueError, expected_message):
                    run_benchmark(
                        benchmark,
                        evaluator,
                        executor,
                        out_dir=root / "run",
                        runtime_root=root / "runtime",
                        limit=2,
                        intervention=intervention,
                    )
                self.assertEqual(benchmark.prepare_calls, 1)
                self.assertEqual(benchmark.load_tasks_calls, 1)
                self.assertEqual(benchmark.snapshot_task_calls, 2)
                self.assertEqual(executor.execute_calls, 0)
                self.assertEqual(len(evaluator.evaluation_requests), 0)
                self.assertEqual(evaluator.validate_plans[0].task_prompt, "canonical prompt 0")
                self.assertEqual(evaluator.validate_plans[0].metadata["expected"], "expected-0")
                self.assertEqual(intervention.validated_tasks[0], TaskSpec("fixture-0", "canonical prompt 0"))
                self.assertFalse((root / "run").exists())
                self.assertFalse((root / "runtime").exists())
                self.assertFalse(any(path.name.startswith(".run.staging-") for path in root.iterdir()))

    def test_success_reopens_binding_after_snapshot_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "run"
            runtime = root / "runtime"
            with patch(
                "eval_harness.candidate_bundle.open_verified_snapshot",
                wraps=open_verified_snapshot,
            ) as open_snapshot:
                run_benchmark(
                    FixtureBenchmark(task_count=1),
                    FixtureEvaluator(),
                    FixtureExecutor(),
                    out_dir=out,
                    runtime_root=runtime,
                    limit=1,
                    intervention=FixtureIntervention(),
                )
            loaded_paths = [cast(Path, call.args[0]) for call in open_snapshot.call_args_list]
            self.assertEqual(len(loaded_paths), 2)
            self.assertTrue(loaded_paths[0].parent.name.startswith(".run.staging-"))
            self.assertEqual(loaded_paths[1], out / "snapshot")
            self.assertFalse(loaded_paths[0].exists())
            manifest = load_run_manifest(out)
            binding = VerifiedSnapshotBinding.load(out / manifest.snapshot_path)
            self.assertEqual(
                tuple(binding.reference(reference.task_id) for reference in manifest.ordered_tasks),
                manifest.ordered_tasks,
            )
            self.assertFalse(any(path.name.startswith(".run.staging-") for path in root.iterdir()))


if __name__ == "__main__":
    unittest.main()
