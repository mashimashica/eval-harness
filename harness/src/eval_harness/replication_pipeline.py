# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Independent Skill creation cohorts composed from ordinary immutable runs.

Every cohort's inputs and execution journal are prepared before the first
creator is called. Within a cohort, each generated Skill is reused for all
execution repeats. Cohorts share task identities, never bootstrap sample IDs.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from .artifacts import ensure_new_output, file_manifest, manifest_hash, read_json, write_json
from .config import EvaluationConfig, ExperimentConfig, evaluation_snapshot, snapshot_mapping
from .errors import ArtifactError, ConfigError
from .executor import Executor
from .run_pipeline import RunSummary, _timestamp, _verify_frozen_input_manifest, resume_run, run_experiment
from .skill_pipeline import ExecutorFactory

if TYPE_CHECKING:
    from .evaluate_pipeline import EvaluationSummary


def cohort_paths(root: Path, manifest: Mapping[str, Any], field: str = "run_dir") -> list[Path]:
    """Resolve recorded children without allowing duplicate or escaping paths."""
    cohorts = manifest.get("cohorts")
    if not isinstance(cohorts, list) or not cohorts:
        raise ArtifactError("creation cohort manifest has no children")
    paths: list[Path] = []
    for cohort in cohorts:
        value = cohort.get(field) if isinstance(cohort, dict) else None
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ArtifactError("invalid relative creation cohort path")
        path = (root / value).resolve()
        if path == root or not path.is_relative_to(root) or path in paths:
            raise ArtifactError("creation cohort path escapes its parent or repeats a child")
        paths.append(path)
    return paths


def run_cohorts(
    config: ExperimentConfig,
    output_dir: str | Path,
    executor: Executor,
    *,
    check_auth: bool,
    executor_factory: ExecutorFactory | None,
) -> RunSummary:
    """Prepare all independent creations, then use the normal resume engine."""
    if config.creation_repeats < 2:
        raise ConfigError("creation cohorts require creation_repeats greater than one")
    skills = [c.intervention for c in config.conditions if c.intervention is not None]
    if not skills or any(skill.build is None for skill in skills):
        raise ConfigError("creation_repeats > 1 requires build configurations for all Skill conditions")
    root = ensure_new_output(output_dir)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "creation_cohorts",
        "run_id": uuid.uuid4().hex,
        "created_at": _timestamp(),
        "benchmark": config.benchmark,
        "config_snapshot": snapshot_mapping(config),
        "creation_repeats": config.creation_repeats,
        "execution_repeats": config.repeats,
        "source_freeze_status": "pending",
        "execution_status": "not_started",
        "cohorts": [],
    }
    write_json(root / "run_manifest.json", manifest)
    for index in range(config.creation_repeats):
        relative = f"cohorts/creation_{index}"
        manifest["cohorts"].append({"creation_repeat": index, "run_dir": relative})
        write_json(root / "run_manifest.json", manifest)
        child = root / relative
        run_experiment(
            replace(config, creation_repeats=1),
            child,
            executor,
            check_auth=check_auth,
            executor_factory=executor_factory,
            _prepare_only=True,
        )
        child_manifest = read_json(child / "run_manifest.json")
        child_manifest.update(creation_repeat=index, cohort_parent_id=manifest["run_id"])
        write_json(child / "run_manifest.json", child_manifest)
        state = read_json(child / "run_state.json")
        for record in state:
            record.update(creation_repeat=index, cohort_parent_id=manifest["run_id"])
            write_json(child / record["execution_dir"] / "execution.json", record)
        write_json(child / "run_state.json", state)
    manifest["source_freeze_status"] = "completed"
    write_json(root / "run_manifest.json", manifest)
    return resume_cohorts(root, executor, check_auth=check_auth, executor_factory=executor_factory)


def resume_cohorts(
    root: Path,
    executor: Executor,
    *,
    check_auth: bool,
    executor_factory: ExecutorFactory | None,
) -> RunSummary:
    """Continue existing child journals; never recreate completed Skills/tasks."""
    root = root.resolve()
    manifest = read_json(root / "run_manifest.json")
    if manifest.get("source_freeze_status") != "completed":
        raise ArtifactError("cohort input preparation did not finish; preserve it and start a new output")
    paths = cohort_paths(root, manifest)
    # Validate every frozen cohort before any resumed model call.
    for index, child in enumerate(paths):
        child_manifest = read_json(child / "run_manifest.json")
        if (
            child_manifest.get("cohort_parent_id") != manifest["run_id"]
            or child_manifest.get("creation_repeat") != index
        ):
            raise ArtifactError("creation cohort identity does not match its parent")
        _verify_frozen_input_manifest(child, child_manifest)
    for child in paths:
        try:
            summary = resume_run(child, executor, check_auth=check_auth, executor_factory=executor_factory)
        except (Exception, KeyboardInterrupt):
            _summarize(root, manifest, paths)
            raise
        _summarize(root, manifest, paths)
        if summary.execution_status != "completed":
            break
    return _summarize(root, manifest, paths)


def _summarize(root: Path, manifest: dict[str, Any], paths: list[Path]) -> RunSummary:
    children = [read_json(path / "run_manifest.json") for path in paths]
    states = [row for path in paths for row in read_json(path / "run_state.json")]
    completed = sum(row.get("execution_status") == "completed" for row in states)
    pending = sum(row.get("execution_status") == "pending" for row in states)
    failed = len(states) - completed - pending
    status = "completed" if completed == len(states) else "partial"
    evaluations = {str(child.get("evaluation_status", "not_started")) for child in children}
    evaluation_status = next(iter(evaluations)) if len(evaluations) == 1 else "partial"
    manifest.update(
        execution_status=status,
        evaluation_status=evaluation_status,
        task_count=len(states),
        completed_count=completed,
        failed_count=failed,
        pending_count=pending,
        selected_task_ids=children[0].get("selected_task_ids", []),
        conditions=children[0].get("conditions", []),
        aggregation_unit="task_id",
        independent_creation_count=len(paths),
    )
    comparison_dir: Path | None = None
    if status == "completed" and evaluations == {"completed"}:
        from .compare_pipeline import compare_evaluations

        if isinstance(manifest.get("comparison_dir"), str):
            comparison_dir = root / manifest["comparison_dir"]
        else:
            comparison_dir = root / "comparison"
            compare_evaluations(paths, comparison_dir)
            manifest["comparison_dir"] = "comparison"
    write_json(root / "run_manifest.json", manifest)
    return RunSummary(
        root,
        manifest["run_id"],
        status,
        len(states),
        completed,
        failed,
        evaluation_status=evaluation_status,
        comparison_dir=comparison_dir,
        pending_count=pending,
    )


def evaluate_cohorts(
    source: Path,
    config: EvaluationConfig,
    output_dir: str | Path,
    executor: Executor | None,
    *,
    check_auth: bool,
    executor_factory: ExecutorFactory | None,
    prepare_only: bool = False,
) -> EvaluationSummary:
    """Freeze every cohort's grading source before invoking any judge."""
    from .evaluate_pipeline import evaluate_run

    source_manifest = read_json(source / "run_manifest.json")
    if source_manifest.get("source_freeze_status") != "completed":
        raise ArtifactError("cannot evaluate an incompletely prepared creation cohort")
    if config.method == "human":
        raise ConfigError(
            "evaluate human ratings on each child run: condition/task/repeat alone cannot identify a creation cohort"
        )
    paths = cohort_paths(source, source_manifest)
    root = ensure_new_output(output_dir)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "creation_cohorts",
        "evaluation_id": uuid.uuid4().hex,
        "created_at": _timestamp(),
        "source_run_dir": str(source),
        "source_run_id": source_manifest["run_id"],
        "config_snapshot": evaluation_snapshot(config),
        "method": config.method,
        "evaluation_status": "not_started",
        "source_freeze_status": "pending",
        "cohorts": [],
    }
    write_json(root / "evaluation_manifest.json", manifest)
    for index, child in enumerate(paths):
        relative = f"cohorts/creation_{index}"
        evaluate_run(
            child,
            config,
            root / relative,
            executor,
            check_auth=False,
            executor_factory=executor_factory,
            _prepare_only=True,
        )
        child_manifest = read_json(root / relative / "evaluation_manifest.json")
        manifest["cohorts"].append(
            {
                "creation_repeat": index,
                "evaluation_dir": relative,
                "source_run_id": child_manifest["source_run_id"],
                "source_snapshot_sha256": child_manifest["source_snapshot_sha256"],
            }
        )
        write_json(root / "evaluation_manifest.json", manifest)
    manifest["source_freeze_status"] = "completed"
    write_json(root / "evaluation_manifest.json", manifest)
    if prepare_only:
        return _summarize_evaluations(root, manifest)
    return resume_cohort_evaluation(root, executor, check_auth=check_auth, executor_factory=executor_factory)


def resume_cohort_evaluation(
    root: Path,
    executor: Executor | None,
    *,
    check_auth: bool,
    executor_factory: ExecutorFactory | None,
) -> EvaluationSummary:
    """Resume frozen child evaluations without reopening original runs/configs."""
    from .evaluate_pipeline import _load_criteria_snapshot, resume_evaluation
    from .grading_criteria import criteria_hash

    manifest = read_json(root / "evaluation_manifest.json")
    if manifest.get("source_freeze_status") != "completed":
        raise ArtifactError("cohort evaluation preparation did not finish; preserve it and use a new output")
    paths = cohort_paths(root, manifest, "evaluation_dir")
    for child, identity in zip(paths, manifest["cohorts"], strict=True):
        saved = read_json(child / "evaluation_manifest.json")
        entries = file_manifest(child / "source_snapshot")
        if (
            saved["config_snapshot"] != manifest["config_snapshot"]
            or saved["source_run_id"] != identity["source_run_id"]
            or manifest_hash(entries) != identity["source_snapshot_sha256"]
            or entries != read_json(child / "source_snapshot_manifest.json")
            or criteria_hash(_load_criteria_snapshot(child, saved))
            != criteria_hash(manifest["config_snapshot"].get("criteria"))
        ):
            raise ArtifactError("prepared cohort evaluation source, criteria or identity changed")
    for child in paths:
        try:
            result = resume_evaluation(child, executor, check_auth=check_auth, executor_factory=executor_factory)
        except (Exception, KeyboardInterrupt):
            _summarize_evaluations(root, manifest)
            raise
        _summarize_evaluations(root, manifest)
        if result.status != "completed":
            break
    return _summarize_evaluations(root, manifest)


def _summarize_evaluations(root: Path, manifest: dict[str, Any]) -> EvaluationSummary:
    from .evaluate_pipeline import EvaluationSummary

    paths = cohort_paths(root, manifest, "evaluation_dir")
    children = [read_json(child / "evaluation_manifest.json") for child in paths]
    states = {child["evaluation_status"] for child in children}
    status = next(iter(states)) if len(states) == 1 else "partial"
    attempted = sum(child.get("attempted_count", 0) for child in children)
    valid = sum(child.get("valid_count", 0) for child in children)
    manifest.update(
        evaluation_status=status,
        attempted_count=attempted,
        valid_count=valid,
        judgment_count=sum(child.get("judgment_count", child.get("task_count", 0)) for child in children),
        pending_count=sum(child.get("pending_count", 0) for child in children),
        aggregation_unit="task_id",
    )
    write_json(root / "evaluation_manifest.json", manifest)
    return EvaluationSummary(root, manifest["evaluation_id"], status, attempted, valid)
