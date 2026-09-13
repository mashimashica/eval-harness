# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic benchmark × evaluator × executor orchestration."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from numbers import Real
from pathlib import Path
from typing import Mapping, Sequence, TextIO

from eval_harness.benchmarks.base import Benchmark, BenchmarkTask
from eval_harness.candidate_bundle import (
    CandidateBundleError,
    ExecutorEvidence,
    InterventionEvidence,
    SnapshotReference,
    VerifiedSnapshotBinding,
    seal_candidate_bundle,
)
from eval_harness.capabilities import ExecutorCapabilities, ExecutorOutput
from eval_harness.evaluators.base import (
    EvaluationCandidate,
    EvaluationPlan,
    EvaluationRequest,
    EvaluationResult,
    EvaluationStatus,
    Evaluator,
    EvaluatorPreflightResult,
    EvaluatorType,
)
from eval_harness.executors.base import ExecutionRequest, ExecutionResult, ExecutionStatus, Executor
from eval_harness.failures import FailureImpact, FailureKind, RunAbort
from eval_harness.interventions.base import (
    Intervention,
    InterventionApplication,
    InterventionBundle,
    InterventionManifest,
    InterventionPreflightResult,
    ensure_source_output_separation,
)
from eval_harness.interventions.none import NoneIntervention
from eval_harness.layout import candidate_layout, safe_task_id, task_layout
from eval_harness.provenance import (
    RepositoryProvenance,
    execution_record,
    repository_provenance,
    task_sha256,
)
from eval_harness.reasoning import ReasoningEffortOption, validate_executor_reasoning_effort
from eval_harness.run_manifest import RunManifest, RunResultRow, RunResultWriter, write_run_manifest


_LEGACY_CONDITION_ENVIRONMENT_KEYS = frozenset(
    {"GDPVAL_CONDITION", "GDPVAL_CONDITION_FILE", "GDPVAL_CONDITION_APPLIED"}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically write a JSON file and fsync both file and containing dir."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(6)}")
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append_jsonl(handle: TextIO, payload: Mapping[str, object]) -> None:
    handle.write(json.dumps(payload, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def _executor_environment() -> dict[str, str]:
    """Pass the generic executor a clean environment without legacy labels."""

    return {key: value for key, value in os.environ.items() if key not in _LEGACY_CONDITION_ENVIRONMENT_KEYS}


def _executor_reasoning_effort(executor: Executor) -> ReasoningEffortOption:
    return validate_executor_reasoning_effort(executor, executor.reasoning_effort)


def _value(value: object) -> object:
    return value.value if hasattr(value, "value") else value


def _capabilities_payload(capabilities: ExecutorCapabilities) -> dict[str, list[str]]:
    if type(capabilities) is not ExecutorCapabilities:
        raise TypeError("executor capabilities must be an ExecutorCapabilities")
    return {
        "inputs": sorted(item.value for item in capabilities.inputs),
        "outputs": sorted(item.value for item in capabilities.outputs),
    }


def _evaluation_payload(evaluation: EvaluationResult) -> dict[str, object]:
    return {
        "status": str(_value(evaluation.status)),
        "metrics": dict(evaluation.metrics),
        "outcomes": dict(evaluation.outcomes),
        "details": dict(evaluation.details),
    }


def _evaluation_error_payload(exc: BaseException, *, phase: str = "evaluation") -> dict[str, object]:
    # Keep the durable failure record useful without serializing tracebacks,
    # request objects, candidate metadata, or arbitrary exception attributes.
    return {
        "status": "failed",
        "metrics": {},
        "outcomes": {},
        "details": {
            "error_type": type(exc).__name__,
            "error_message": "evaluation failure persisted before re-raise",
            "error_details": {
                "phase": phase,
                "exception_type": type(exc).__name__,
            },
        },
    }


def _evaluation_interrupt_payload(exc: BaseException) -> dict[str, object]:
    return {
        "status": "interrupted",
        "metrics": {},
        "outcomes": {},
        "details": {
            "error_type": type(exc).__name__,
            "error_message": "evaluation interrupted after executor returned",
            "error_details": {"phase": "evaluation_interrupt", "exception_type": type(exc).__name__},
        },
    }


def _execution_payload(result: ExecutionResult) -> dict[str, object]:
    return execution_record(result)


def _execution_failure_evaluation_payload() -> dict[str, object]:
    """Record the stable evaluation outcome for a systemic executor failure."""

    return {
        "status": EvaluationStatus.SKIPPED.value,
        "metrics": {},
        "outcomes": {},
        "details": {"reason": "executor failure prevented evaluation"},
    }


def _aggregate_metrics(rows: list[dict[str, object]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for row in rows:
        evaluation = row.get("evaluation")
        if not isinstance(evaluation, dict) or evaluation.get("status") != EvaluationStatus.COMPLETED.value:
            continue
        metrics = evaluation.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for name, value in metrics.items():
            if isinstance(value, Real) and not isinstance(value, bool):
                values.setdefault(str(name), []).append(float(value))
    return {name: sum(samples) / len(samples) for name, samples in sorted(values.items()) if samples}


def _evaluation_status_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        evaluation = row.get("evaluation")
        if not isinstance(evaluation, dict):
            continue
        status = str(evaluation.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _path_matches(actual: Path, expected: Path) -> bool:
    """Require an executor result path to be the runner-assigned path."""

    try:
        actual_absolute = actual.absolute()
        expected_absolute = expected.absolute()
    except (AttributeError, OSError, TypeError):
        return False
    current = Path(actual_absolute.anchor)
    parts = actual_absolute.parts[1:] if actual_absolute.anchor else actual_absolute.parts
    for part in parts:
        current /= part
        if current.is_symlink():
            return False
        if not current.exists():
            break
    try:
        return actual_absolute.resolve(strict=False) == expected_absolute.resolve(strict=False)
    except OSError:
        return False


def _preflight_failure(prefix: str, details: object) -> RuntimeError:
    if isinstance(details, (list, tuple)):
        message = "; ".join(str(detail) for detail in details) or "preflight failed"
    else:
        message = str(details) or "preflight failed"
    return RuntimeError(f"{prefix} preflight failed: {message}")


def _canonical_planned_root(path: Path, *, existing_message: str) -> Path:
    """Return a canonical root that is still fresh and has no root symlink."""

    if path.exists() or path.is_symlink():
        raise FileExistsError(existing_message)
    try:
        canonical = path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"could not resolve planned output root: {path}") from exc
    # A parent symlink can make a non-existent spelling resolve to an existing
    # path.  Check the canonical spelling too so neither root can be reused.
    if canonical.exists() or canonical.is_symlink():
        raise FileExistsError(existing_message)
    return canonical


def _ensure_roots_are_separate(out_root: Path, runtime_root: Path) -> None:
    if out_root == runtime_root or out_root in runtime_root.parents or runtime_root in out_root.parents:
        raise ValueError("out_dir and runtime_root must be separate, non-overlapping roots")


def _evaluator_metadata(evaluator: Evaluator, preflight: EvaluatorPreflightResult) -> dict[str, object]:
    evaluator_id = getattr(preflight, "name", None) or getattr(evaluator, "name", type(evaluator).__name__)
    evaluator_type = getattr(preflight, "evaluator_type", None) or getattr(evaluator, "evaluator_type", None)
    evaluator_type_value = _value(evaluator_type)
    evaluator_version = getattr(preflight, "version", None)
    if evaluator_version is None:
        evaluator_version = getattr(evaluator, "version", None)
    evaluator_revision = getattr(preflight, "revision", None)
    if evaluator_revision is None:
        evaluator_revision = getattr(evaluator, "revision", None)
    details = tuple(getattr(preflight, "details", ()) or ())
    judge_fields = {
        "executor": getattr(preflight, "judge_executor", None),
        "version": getattr(preflight, "judge_executor_version", None),
        "auth_mode": getattr(preflight, "judge_auth_mode", None),
        "model": getattr(preflight, "judge_model", None),
    }
    judge_applicable = evaluator_type_value in {
        EvaluatorType.LLM_RUBRIC.value,
        EvaluatorType.PAIRWISE.value,
    }
    judge = {
        "applicable": judge_applicable,
        **(judge_fields if judge_applicable else {key: None for key in judge_fields}),
    }
    payload: dict[str, object] = {
        "id": evaluator_id,
        "type": evaluator_type_value,
        "version": evaluator_version,
        "revision": evaluator_revision,
        "preflight_details": [],
        "preflight_detail_count": len(details),
        "judge": judge,
    }
    return payload


def _revision_status(revision: object) -> str:
    return "available" if revision is not None else "unavailable"


def _repository_record(provenance: RepositoryProvenance) -> dict[str, object]:
    return {
        "commit": provenance.commit,
        "revision_status": provenance.revision_status,
        "worktree_status": provenance.worktree_status,
    }


def _configuration_intervention(descriptor: Mapping[str, object]) -> dict[str, object]:
    """Select intervention evidence that is stable and independent of source paths/status."""

    return {
        key: descriptor.get(key)
        for key in (
            "id",
            "type",
            "revision",
            "source_revision",
            "revision_status",
            "bundle_sha256",
            "manifest_sha256",
            "files",
            "application",
        )
    }


def _configuration_evaluator(descriptor: Mapping[str, object]) -> dict[str, object]:
    """Select evaluator evidence without arbitrary preflight detail payloads."""

    return {key: descriptor.get(key) for key in ("id", "type", "version", "revision", "judge")}


def _intervention_metadata(
    intervention: Intervention,
    preflight: InterventionPreflightResult,
) -> dict[str, object]:
    """Persist only the reviewed intervention descriptor and hashes."""

    bundle = preflight.bundle
    manifest = bundle.manifest if bundle is not None else None
    application = manifest.application if manifest is not None else None
    intervention_id = (
        manifest.intervention_id
        if manifest is not None
        else getattr(intervention, "intervention_id", None) or preflight.name
    )
    intervention_type = _value(getattr(preflight, "intervention_type", None))
    source_revision = manifest.source_revision if manifest is not None else None
    revision_status = manifest.revision_status if manifest is not None else "unavailable"
    files = (
        [{"path": item.path, "size": item.size, "sha256": item.sha256} for item in manifest.files]
        if manifest is not None
        else []
    )
    descriptor: dict[str, object] = {
        "id": intervention_id,
        "type": intervention_type,
        "revision": source_revision,
        "source_revision": source_revision,
        "revision_status": revision_status,
        "status": "ready" if preflight.ok else "failed",
        "bundle_sha256": manifest.bundle_sha256 if manifest is not None else None,
        "manifest_sha256": manifest.manifest_sha256 if manifest is not None else None,
        "files": files,
        "application": (
            {"method": application.method, "target": application.target}
            if application is not None
            else {"method": None, "target": None}
        ),
    }
    source_reference = getattr(intervention, "source_reference", None)
    if isinstance(source_reference, str) and source_reference and "\x00" not in source_reference:
        descriptor["source_reference"] = source_reference
    return descriptor


def _intervention_application_payload(
    application: InterventionApplication,
    descriptor: Mapping[str, object],
) -> dict[str, object]:
    """Convert application evidence into a safe durable JSON payload."""

    mapping = application.application
    files = [{"path": item.path, "size": item.size, "sha256": item.sha256} for item in application.materialized_files]
    payload = {
        "id": descriptor.get("id"),
        "type": descriptor.get("type"),
        "revision": descriptor.get("revision"),
        "source_revision": descriptor.get("source_revision"),
        "revision_status": descriptor.get("revision_status"),
        "status": "applied",
        "application_run_id": application.application_run_id,
        "bundle_sha256": application.bundle_sha256,
        "manifest_sha256": application.manifest_sha256,
        "application": {"method": mapping.method, "target": mapping.target},
        "materialized_files": files,
    }
    return payload


def _intervention_error_payload(
    exc: BaseException,
    *,
    descriptor: Mapping[str, object],
    application_run_id: str,
    phase: str,
    interrupted: bool = False,
) -> dict[str, object]:
    """Return safe intervention failure evidence without arbitrary exception text."""

    return {
        "id": descriptor.get("id"),
        "type": descriptor.get("type"),
        "revision": descriptor.get("revision"),
        "source_revision": descriptor.get("source_revision"),
        "revision_status": descriptor.get("revision_status"),
        "status": "interrupted" if interrupted else "failed",
        "application_run_id": application_run_id,
        "bundle_sha256": descriptor.get("bundle_sha256"),
        "manifest_sha256": descriptor.get("manifest_sha256"),
        "application": descriptor.get("application"),
        "materialized_files": [],
        "error_type": type(exc).__name__,
        "error_message": (
            "intervention application interrupted before executor"
            if interrupted
            else "intervention application failed before executor"
        ),
        "error_details": {"phase": phase, "exception_type": type(exc).__name__},
    }


@dataclass(frozen=True)
class RunSummary:
    benchmark: str
    executor: str
    out_dir: Path
    runtime_root: Path
    status: str
    task_count: int
    metrics: Mapping[str, float]
    evaluation_status_counts: Mapping[str, int]
    application_run_ids: Mapping[str, str] = field(default_factory=dict)


def run_benchmark(
    benchmark: Benchmark,
    evaluator: Evaluator,
    executor: Executor,
    *,
    out_dir: Path,
    limit: int,
    model: str | None = None,
    timeout_seconds: float = 12600.0,
    intervention: Intervention | None = None,
    runtime_root: Path | None = None,
) -> RunSummary:
    """Run benchmark tasks and publish the durable generation handoff first."""

    if intervention is None:
        intervention = NoneIntervention()
    if type(limit) is not int or limit <= 0:
        raise ValueError("--limit must be a positive integer")
    if timeout_seconds <= 0:
        raise ValueError("--executor-timeout must be positive")

    run_id = secrets.token_hex(16)
    reasoning_effort = _executor_reasoning_effort(executor)
    out_root = _canonical_planned_root(
        out_dir,
        existing_message=f"refusing to overwrite existing run directory: {out_dir}",
    )
    if runtime_root is None:
        effective_runtime_root = out_root
        runtime_layout = "run-output"
        runtime_layout_root: Path | None = None
    else:
        effective_runtime_root = _canonical_planned_root(
            runtime_root,
            existing_message=f"refusing to overwrite existing runtime directory: {runtime_root}",
        )
        _ensure_roots_are_separate(out_root, effective_runtime_root)
        runtime_layout = "external-persistent"
        runtime_layout_root = effective_runtime_root

    # Evaluator readiness is checked first.  This prevents an executor from
    # consuming a model call when the requested evaluation path is unavailable.
    evaluator_preflight = evaluator.preflight(run_dir=out_dir)
    if not evaluator_preflight.ok:
        raise _preflight_failure(getattr(evaluator, "name", "evaluator"), evaluator_preflight.details)

    intervention_preflight = intervention.preflight()
    if not intervention_preflight.ok:
        raise _preflight_failure(getattr(intervention, "name", "intervention"), intervention_preflight.details)
    intervention_bundle = intervention_preflight.bundle
    if type(intervention_bundle) is not InterventionBundle:
        raise TypeError("successful intervention preflight must include an InterventionBundle")
    intervention_manifest = intervention_bundle.manifest
    if type(intervention_manifest) is not InterventionManifest:
        raise TypeError("successful intervention preflight must include an InterventionManifest")
    if isinstance(intervention_bundle.root, Path):
        ensure_source_output_separation(intervention_bundle, out_root)
        if runtime_root is not None:
            ensure_source_output_separation(intervention_bundle, effective_runtime_root)

    executor_preflight = executor.preflight()
    if not executor_preflight.ok:
        raise _preflight_failure(executor.name, executor_preflight.details)
    if executor_preflight.executor != executor.name:
        raise ValueError("executor preflight returned a mismatched executor")

    # These are fixed executor contracts.  Validate them before benchmark
    # preparation so malformed implementations cannot create a partial run.
    network_access_enabled = executor.network_access_enabled
    if type(network_access_enabled) is not bool:
        raise TypeError("executor network_access_enabled must be a bool")
    capabilities = executor.capabilities
    if type(capabilities) is not ExecutorCapabilities:
        raise TypeError("executor capabilities must be an ExecutorCapabilities")
    network_policy = "enabled" if network_access_enabled else "disabled"

    # Snapshot acquisition is the only benchmark task load.  The temporary
    # sibling lets all plan/intervention validation complete while both planned
    # roots remain absent; the sealed snapshot is then moved into the run root.
    out_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{out_root.name}.staging-", dir=str(out_root.parent)) as controller_name:
        controller_root = Path(controller_name)
        snapshot_destination = controller_root / "snapshot"
        benchmark.prepare()
        snapshot = benchmark.acquire_snapshot(limit, snapshot_destination)
        temporary_binding = VerifiedSnapshotBinding.load(snapshot_destination)
        snapshot_tasks = tuple(snapshot.tasks)
        if not snapshot_tasks:
            raise ValueError("benchmark snapshot returned no tasks")

        seen_task_ids: set[str] = set()
        safe_task_ids: dict[str, str] = {}
        ordered_references: list[SnapshotReference] = []
        plans: list[tuple[SnapshotReference, EvaluationPlan]] = []
        legacy_task_hashes: dict[str, str] = {}
        for snapshot_task in snapshot_tasks:
            reference = temporary_binding.reference(snapshot_task.task_id)
            resolved_task = temporary_binding.resolve(reference)
            if resolved_task != snapshot_task:
                raise ValueError("benchmark snapshot task does not match its verified binding")
            task = resolved_task.task_spec()
            task_id = task.task_id
            if task_id in seen_task_ids:
                raise ValueError(f"duplicate task_id loaded: {task_id!r}")
            seen_task_ids.add(task_id)
            safe_id = safe_task_id(task_id)
            previous_task_id = safe_task_ids.get(safe_id)
            if previous_task_id is not None:
                raise ValueError(f"task ids {previous_task_id!r} and {task_id!r} collide after safe normalization")
            safe_task_ids[safe_id] = task_id

            bound_view = temporary_binding.bind_evaluation_view(reference)
            plan_layout = task_layout(out_root, task_id, runtime_root=runtime_layout_root)
            plan = EvaluationPlan(
                task_id=task_id,
                task_prompt=bound_view.canonical_task_prompt,
                metadata=bound_view.evaluation_data,
                candidate_count=1,
                artifact_dir=plan_layout.judge_deliverables,
            )
            evaluator.validate_plan(plan)
            intervention.validate_task(task)
            ordered_references.append(reference)
            plans.append((reference, plan))
            legacy_task_hashes[task_id] = task_sha256(task)

        # ``acquire_snapshot`` has published a fully verified directory at the
        # temporary destination.  Move that directory exactly once and reopen
        # its binding so no pre-rename path capability survives publication.
        out_root.mkdir(parents=True, exist_ok=False)
        published_snapshot = out_root / "snapshot"
        os.rename(snapshot_destination, published_snapshot)
        _fsync_directory(out_root)

    binding = VerifiedSnapshotBinding.load(out_root / "snapshot")
    reopened_references = tuple(binding.reference(reference.task_id) for reference in ordered_references)
    if reopened_references != tuple(ordered_references):
        raise ValueError("published snapshot references do not match the acquired snapshot")

    # The external runtime is created only after the durable snapshot has been
    # published and all plans have passed validation.
    if runtime_root is not None:
        effective_runtime_root.mkdir(parents=True, exist_ok=False)

    started_at = _now()
    metadata_path = out_root / "run-metadata.json"
    legacy_results_path = out_root / "results.jsonl"
    candidate_results_path = out_root / "candidate-results.jsonl"
    evaluator_info = _evaluator_metadata(evaluator, evaluator_preflight)
    intervention_info = _intervention_metadata(intervention, intervention_preflight)
    snapshot_source = snapshot.source
    snapshot_source_availability = _value(snapshot.source_availability)
    snapshot_revision = snapshot.revision
    snapshot_revision_availability = _value(snapshot.revision_availability)
    executor_descriptor: dict[str, object] = {
        "id": executor.name,
        "version": executor_preflight.version,
        "invocation_mode": executor.invocation_mode,
        "auth_mode": executor_preflight.auth_mode,
        "model": model,
        "network_policy": network_policy,
        "reasoning_effort_requested": reasoning_effort,
        "capabilities": _capabilities_payload(capabilities),
    }
    ordered_task_records = [
        {
            "task_id": reference.task_id,
            "task_sha256": legacy_task_hashes[reference.task_id],
            "snapshot_sha256": reference.snapshot_sha256,
        }
        for reference in ordered_references
    ]
    configuration: dict[str, object] = {
        "benchmark": {
            "id": snapshot.benchmark_id,
            "source": snapshot_source,
            "source_availability": snapshot_source_availability,
            "revision": snapshot_revision,
            "revision_availability": snapshot_revision_availability,
        },
        "executor": executor_descriptor,
        "evaluator": _configuration_evaluator(evaluator_info),
        "intervention": _configuration_intervention(intervention_info),
        "model": model,
        "network_policy": network_policy,
        "limit": limit,
        "timeout_seconds": timeout_seconds,
    }
    snapshot_sha256 = ordered_references[0].snapshot_sha256
    manifest = RunManifest(
        run_id=run_id,
        snapshot_path="snapshot",
        snapshot_sha256=snapshot_sha256,
        results_path="candidate-results.jsonl",
        configuration=configuration,
        configuration_sha256=None,
        ordered_tasks=tuple(ordered_references),
        run_fingerprint_sha256=None,
        root=out_root,
    )
    candidate_writer = RunResultWriter.create(candidate_results_path)
    manifest = write_run_manifest(out_root, manifest)

    repository_info = _repository_record(repository_provenance(Path(__file__).resolve().parents[1]))
    base_metadata: dict[str, object] = {
        "schema_version": 4,
        "run_id": run_id,
        "benchmark": snapshot.benchmark_id,
        "benchmark_source": snapshot_source,
        "benchmark_source_availability": snapshot_source_availability,
        "benchmark_revision": snapshot_revision,
        "benchmark_revision_status": snapshot_revision_availability,
        "snapshot_path": "snapshot",
        "snapshot_sha256": snapshot_sha256,
        "evaluator_id": evaluator_info["id"],
        "evaluator_type": evaluator_info["type"],
        "evaluator_version": evaluator_info["version"],
        "evaluator_revision": evaluator_info["revision"],
        "evaluator": evaluator_info,
        "intervention_id": intervention_info["id"],
        "intervention_type": intervention_info["type"],
        "intervention_revision": intervention_info["revision"],
        "intervention": intervention_info,
        "executor": executor.name,
        "executor_version": executor_preflight.version,
        "auth_mode": executor_preflight.auth_mode,
        "executor_descriptor": executor_descriptor,
        "model": model,
        "network_policy": network_policy,
        "limit": limit,
        "timeout_seconds": timeout_seconds,
        "runtime_root": str(effective_runtime_root),
        "runtime_layout": runtime_layout,
        "started_at": started_at,
        "finished_at": None,
        "status": "running",
        "judge": evaluator_info["judge"],
        "repository": repository_info,
        "tasks": ordered_task_records,
        "configuration": configuration,
        "configuration_sha256": manifest.configuration_sha256,
        "run_fingerprint_sha256": manifest.run_fingerprint_sha256,
    }
    if reasoning_effort is not None:
        base_metadata["reasoning_effort_requested"] = reasoning_effort
    _write_json(metadata_path, base_metadata)

    rows: list[dict[str, object]] = []
    application_run_ids: dict[str, str] = {}

    def record_application_run_id(row: Mapping[str, object]) -> None:
        task_id = row.get("task_id")
        intervention_payload = row.get("intervention")
        if not isinstance(task_id, str) or not isinstance(intervention_payload, Mapping):
            return
        application_run_id = intervention_payload.get("application_run_id")
        if isinstance(application_run_id, str) and application_run_id:
            application_run_ids[task_id] = application_run_id

    run_status = "completed"
    try:
        with legacy_results_path.open("x", encoding="utf-8", newline="\n") as results_handle:

            def persist_legacy_row(
                task_id: str,
                task_layout_value: object,
                materialized: Sequence[str],
                intervention_payload: Mapping[str, object],
                result: object,
                evaluation_payload: dict[str, object],
            ) -> dict[str, object]:
                execution_payload = _execution_payload(result) if type(result) is ExecutionResult else None
                row: dict[str, object] = {
                    "task_id": task_id,
                    "task_sha256": legacy_task_hashes[task_id],
                    "materialized": list(materialized),
                    "intervention": dict(intervention_payload),
                    "execution": execution_payload,
                    "evaluation": evaluation_payload,
                }
                if not hasattr(task_layout_value, "executor_dir"):
                    raise TypeError("task layout is invalid")
                executor_dir = task_layout_value.executor_dir
                _write_json(executor_dir.parent / "result.json", row)
                _append_jsonl(results_handle, row)
                rows.append(row)
                record_application_run_id(row)
                return row

            for sequence, (reference, plan) in enumerate(plans):
                snapshot_task = binding.resolve(reference)
                canonical_task = snapshot_task.task_spec()
                layout = task_layout(
                    out_root,
                    reference.task_id,
                    runtime_root=runtime_layout_root,
                )
                task_root = layout.workspace.parent
                task_root.mkdir(parents=True, exist_ok=False)
                layout.executor_dir.mkdir(exist_ok=False)
                materialized = binding.materialize_execution(reference, layout.workspace)
                layout.workspace_deliverables.mkdir(parents=False, exist_ok=False)
                execution_task = benchmark.execution_task(
                    BenchmarkTask(execution=canonical_task),
                    layout.workspace,
                    network_policy=network_policy,
                )
                # Keep the legacy prompt file for staged consumers.  It is
                # written from the bound canonical view and is not a handoff
                # input for the new candidate ledger.
                canonical_path = layout.executor_dir / "task-prompt.txt"
                canonical_path.write_text(plan.task_prompt, encoding="utf-8")
                with canonical_path.open("rb") as canonical_handle:
                    canonical_handle.flush()
                    os.fsync(canonical_handle.fileno())

                application_run_id = secrets.token_urlsafe(24)
                try:
                    application = intervention.apply(
                        execution_task,
                        layout.workspace,
                        application_run_id=application_run_id,
                    )
                    if application.application_run_id != application_run_id:
                        raise ValueError("intervention returned a mismatched application_run_id")
                    if application.task.task_id != reference.task_id:
                        raise ValueError("intervention returned a mismatched task_id")
                    if application.bundle_sha256 != intervention_info["bundle_sha256"]:
                        raise ValueError("intervention returned a mismatched bundle_sha256")
                    if application.manifest_sha256 != intervention_info["manifest_sha256"]:
                        raise ValueError("intervention returned a mismatched manifest_sha256")
                    application_mapping = {
                        "method": application.application.method,
                        "target": application.application.target,
                    }
                    if application_mapping != intervention_info["application"]:
                        raise ValueError("intervention returned a mismatched application mapping")
                    intervention_payload = _intervention_application_payload(application, intervention_info)
                except KeyboardInterrupt as exc:
                    intervention_payload = _intervention_error_payload(
                        exc,
                        descriptor=intervention_info,
                        application_run_id=application_run_id,
                        phase="intervention_apply",
                        interrupted=True,
                    )
                    persist_legacy_row(
                        reference.task_id,
                        layout,
                        materialized,
                        intervention_payload,
                        None,
                        _evaluation_interrupt_payload(exc),
                    )
                    base_metadata["failure"] = {
                        "phase": "intervention_apply",
                        "exception_type": type(exc).__name__,
                    }
                    run_status = "interrupted"
                    _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
                    raise
                except Exception as exc:
                    intervention_payload = _intervention_error_payload(
                        exc,
                        descriptor=intervention_info,
                        application_run_id=application_run_id,
                        phase="intervention_apply",
                    )
                    persist_legacy_row(
                        reference.task_id,
                        layout,
                        materialized,
                        intervention_payload,
                        None,
                        _evaluation_error_payload(exc, phase="intervention_apply"),
                    )
                    base_metadata["failure"] = {
                        "phase": "intervention_apply",
                        "exception_type": type(exc).__name__,
                    }
                    run_status = "failed"
                    _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
                    raise

                request = ExecutionRequest(
                    task=application.task,
                    workspace=layout.workspace,
                    deliverables_dir=layout.workspace_deliverables,
                    executor_dir=layout.executor_dir,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    environment=_executor_environment(),
                )
                result = executor.execute(request)

                try:
                    if type(result) is not ExecutionResult:
                        raise TypeError("executor must return an ExecutionResult")
                    if result.task_id != reference.task_id:
                        raise ValueError("executor returned a mismatched task_id")
                    if result.executor != executor.name:
                        raise ValueError("executor returned a mismatched executor")
                    if result.invocation_mode != executor.invocation_mode:
                        raise ValueError("executor returned a mismatched invocation_mode")
                    if (
                        executor_preflight.version is not None
                        and result.executor_version is not None
                        and result.executor_version != executor_preflight.version
                    ):
                        raise ValueError("executor returned a mismatched executor_version")
                    if (
                        executor_preflight.auth_mode is not None
                        and result.auth_mode is not None
                        and result.auth_mode != executor_preflight.auth_mode
                    ):
                        raise ValueError("executor returned a mismatched auth_mode")
                    if result.runtime != executor.runtime:
                        raise ValueError("executor returned a mismatched runtime")
                    if not _path_matches(result.workspace, layout.workspace):
                        raise ValueError("executor returned a workspace outside the assigned task workspace")
                    if not _path_matches(result.deliverables_dir, layout.workspace_deliverables):
                        raise ValueError("executor returned deliverables outside the assigned task directory")
                    if not result.available_outputs <= capabilities.outputs:
                        raise CandidateBundleError("executor returned an undeclared output channel")
                except Exception as exc:
                    legacy_result = result if type(result) is ExecutionResult else None
                    persist_legacy_row(
                        reference.task_id,
                        layout,
                        materialized,
                        intervention_payload,
                        legacy_result,
                        _evaluation_error_payload(exc, phase="executor_result_validation"),
                    )
                    run_status = "failed"
                    _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
                    raise

                executor_evidence = ExecutorEvidence(
                    executor_id=result.executor,
                    executor_version=result.executor_version,
                    runtime=result.runtime,
                    invocation_mode=result.invocation_mode,
                    auth_mode=result.auth_mode,
                    requested_model=model,
                    model_id=result.model_id,
                    reasoning_effort_requested=result.reasoning_effort_requested,
                    effective_reasoning_effort=result.effective_reasoning_effort,
                    effective_reasoning_effort_available=result.effective_reasoning_effort_available,
                    declared_capabilities=capabilities,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    exit_code=result.exit_code,
                )
                intervention_evidence = InterventionEvidence(
                    manifest=intervention_manifest,
                    application=application,
                )
                candidate_name = f"candidate-{sequence:08d}"
                candidate_id = f"{run_id}:{candidate_name}"
                candidate_path = candidate_layout(out_root, sequence)
                try:
                    bundle = seal_candidate_bundle(
                        destination=candidate_path.root,
                        candidate_id=candidate_id,
                        snapshot_binding=binding,
                        snapshot_reference=reference,
                        effective_executor_prompt=application.task.prompt,
                        executor_evidence=executor_evidence,
                        intervention_evidence=intervention_evidence,
                        status=result.status,
                        output_text=result.output_text,
                        available_outputs=result.available_outputs,
                        failure=result.failure,
                        artifacts_root=(
                            result.deliverables_dir
                            if ExecutorOutput.ARTIFACT_FILES in result.available_outputs
                            else None
                        ),
                    )
                    candidate_writer.append(
                        RunResultRow(
                            sequence=sequence,
                            candidate_id=candidate_id,
                            snapshot_reference=reference,
                            bundle_path=candidate_path.relative_path,
                            bundle_sha256=bundle.bundle_sha256,
                        )
                    )
                except Exception as exc:
                    persist_legacy_row(
                        reference.task_id,
                        layout,
                        materialized,
                        intervention_payload,
                        result,
                        _evaluation_error_payload(exc, phase="candidate_handoff"),
                    )
                    run_status = "failed"
                    _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
                    raise

                if result.failure is not None and result.failure.impact is FailureImpact.RUN:
                    persist_legacy_row(
                        reference.task_id,
                        layout,
                        materialized,
                        intervention_payload,
                        result,
                        _execution_failure_evaluation_payload(),
                    )
                    run_status = "interrupted" if result.status is ExecutionStatus.INTERRUPTED else "failed"
                    _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
                    raise RunAbort(result.failure)

                candidate = EvaluationCandidate(
                    candidate_id=candidate_id,
                    execution=result,
                    artifacts_dir=result.deliverables_dir,
                )
                evaluation_request = EvaluationRequest(
                    task_id=plan.task_id,
                    task_prompt=plan.task_prompt,
                    metadata=plan.metadata,
                    candidates=(candidate,),
                    artifact_dir=plan.artifact_dir,
                )
                try:
                    evaluation = evaluator.evaluate(evaluation_request)
                    if evaluation.task_id != reference.task_id:
                        raise ValueError(
                            f"evaluator returned task id {evaluation.task_id!r}; expected {reference.task_id!r}"
                        )
                    evaluation_payload = _evaluation_payload(evaluation)
                except KeyboardInterrupt as exc:
                    persist_legacy_row(
                        reference.task_id,
                        layout,
                        materialized,
                        intervention_payload,
                        result,
                        _evaluation_interrupt_payload(exc),
                    )
                    run_status = "interrupted"
                    _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
                    raise
                except Exception as exc:
                    evaluation_payload = _evaluation_error_payload(exc)
                    persist_legacy_row(
                        reference.task_id,
                        layout,
                        materialized,
                        intervention_payload,
                        result,
                        evaluation_payload,
                    )
                    run_status = "failed"
                    _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
                    raise

                persist_legacy_row(
                    reference.task_id,
                    layout,
                    materialized,
                    intervention_payload,
                    result,
                    evaluation_payload,
                )

    except RunAbort as exc:
        if exc.failure.kind is FailureKind.INTERRUPTED:
            run_status = "interrupted"
        else:
            run_status = "failed"
        _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
        raise
    except KeyboardInterrupt:
        run_status = "interrupted"
        _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
        raise
    except Exception:
        run_status = "failed"
        _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows)
        raise

    metrics = _aggregate_metrics(rows)
    _write_run_metadata(metadata_path, base_metadata, status=run_status, rows=rows, metrics=metrics)
    return RunSummary(
        benchmark=snapshot.benchmark_id,
        executor=executor.name,
        out_dir=out_dir,
        runtime_root=effective_runtime_root,
        status=run_status,
        task_count=len(rows),
        metrics=metrics,
        evaluation_status_counts=_evaluation_status_counts(rows),
        application_run_ids=dict(application_run_ids),
    )


def _write_run_metadata(
    metadata_path: Path,
    base_metadata: Mapping[str, object],
    *,
    status: str,
    rows: list[dict[str, object]],
    metrics: Mapping[str, float] | None = None,
) -> None:
    final_metadata = dict(base_metadata)
    final_metadata.update(
        {
            "status": status,
            "finished_at": _now(),
            "completed_tasks": len(rows),
            "metrics": dict(metrics if metrics is not None else _aggregate_metrics(rows)),
            "evaluation_status_counts": _evaluation_status_counts(rows),
        }
    )
    _write_json(metadata_path, final_metadata)


__all__ = ["RunSummary", "run_benchmark"]
