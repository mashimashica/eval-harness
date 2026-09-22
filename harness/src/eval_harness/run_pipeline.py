# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GDPval task execution and immutable run state."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .artifacts import (
    ensure_new_output,
    file_manifest,
    manifest_hash,
    read_json,
    sha256_bytes,
    sha256_file,
    write_json,
)
from .benchmark import (
    BenchmarkTask,
    copy_reference_files,
    load_tasks,
    reference_source_paths,
    render_application_prompt,
    select_tasks,
    task_directory_name,
    task_from_snapshot,
    task_snapshot,
)
from .config import (
    ConditionConfig,
    EvaluationConfig,
    ExperimentConfig,
    InterventionConfig,
    LimitsConfig,
    RuntimeConfig,
    TaskSelection,
    _evaluation,
    _runtime,
    snapshot_mapping,
    validate_config,
)
from .errors import ArtifactError, ConfigError, HarnessError
from .executor import AuthStatus, ExecutionRequest, ExecutionResult, Executor, ParsedCodexOutput, preflight_executor
from .skill_pipeline import (
    BuildConfig,
    ExecutorFactory,
    _source_manifest,
    build_skill,
    copy_skill_for_application,
    freeze_build_config,
    load_build_config,
    resume_skill_build,
    stage_skill,
)


@dataclass(frozen=True)
class RunSummary:
    """Result of a run operation."""

    run_dir: Path
    run_id: str
    execution_status: str
    task_count: int
    completed_count: int
    failed_count: int
    evaluation_dir: Path | None = None
    evaluation_status: str = "not_started"
    comparison_dir: Path | None = None
    pending_count: int = 0


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _execution_dict(result: ExecutionResult, run_dir: Path, execution_dir: Path) -> dict[str, Any]:
    artifact_root = execution_dir / "deliverables"
    entries = file_manifest(artifact_root)
    return {
        "execution_status": result.status,
        "returncode": result.returncode,
        "elapsed_seconds": result.elapsed_seconds,
        "usage": result.parsed.usage,
        "cost_usd": result.parsed.usage.get("cost_usd"),
        "error": result.error,
        "command": list(result.command),
        "events_path": str((execution_dir / "codex_events.jsonl").relative_to(run_dir)),
        "stderr_path": str((execution_dir / "stderr.log").relative_to(run_dir)),
        "response_path": str((execution_dir / "agent_response.txt").relative_to(run_dir)),
        "deliverables_path": str(artifact_root.relative_to(run_dir)),
        "artifact_files": entries,
        "artifact_sha256": manifest_hash(entries),
        "task_success": None,
        "evaluation_status": "pending",
    }


def _failed_result(error: Exception) -> ExecutionResult:
    parsed = ParsedCodexOutput(
        events=(),
        assistant_messages=(),
        final_text="",
        usage={
            "input_tokens": None,
            "output_tokens": None,
            "cached_input_tokens": None,
            "reasoning_tokens": None,
            "cost_usd": None,
        },
        errors=(str(error),),
        terminal_completed=False,
    )
    return ExecutionResult(
        command=(),
        returncode=None,
        status="failed",
        elapsed_seconds=0.0,
        stdout="",
        stderr="",
        parsed=parsed,
        error=str(error),
    )


def _copy_saved_references(task_dir: Path, workspace: Path, saved_references: list[Mapping[str, Any]]) -> None:
    target_root = workspace / "reference_files"
    target_root.mkdir(parents=True, exist_ok=True)
    for entry in saved_references:
        relative = entry.get("path")
        if not isinstance(relative, str) or Path(relative).name != relative:
            raise ArtifactError(f"invalid saved reference path for task workspace: {relative!r}")
        source = task_dir / relative
        if not source.is_file():
            raise ArtifactError(f"saved reference input is missing: {source}")
        expected_hash = entry.get("sha256")
        if expected_hash is not None and (not isinstance(expected_hash, str) or sha256_file(source) != expected_hash):
            raise ArtifactError(f"saved reference input hash mismatch: {source}")
        shutil.copy2(source, target_root / relative)


def _copy_saved_skill(skill_dir: Path | None, workspace: Path) -> list[dict[str, Any]]:
    if skill_dir is None:
        return []
    return copy_skill_for_application(skill_dir, workspace / "skill")


def _skill_prompt_fragment(skill_dir: Path) -> str:
    """Deliver the selected Skill body explicitly while retaining its staged files."""

    skill_path = skill_dir / "SKILL.md"
    try:
        instructions = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactError(f"cannot read selected Skill instructions: {skill_path}: {exc}") from exc
    return (
        "The selected experiment Skill is part of this task. Apply its instructions while working in the "
        "workspace. The same Skill is available at skill/SKILL.md for supporting references.\n\n"
        "--- BEGIN SELECTED SKILL INSTRUCTIONS ---\n"
        f"{instructions}\n"
        "--- END SELECTED SKILL INSTRUCTIONS ---\n\n"
    )


def _intervention_prompt_fragment(prompt: str) -> str:
    """Deliver a configured condition prompt only to the application agent."""

    return (
        "The experiment includes these additional application instructions. Apply them while working in the "
        "workspace; they are separate from the benchmark task and contain no grading materials.\n\n"
        "--- BEGIN ADDITIONAL APPLICATION INSTRUCTIONS ---\n"
        f"{prompt}\n"
        "--- END ADDITIONAL APPLICATION INSTRUCTIONS ---\n\n"
    )


def _record_workspace(
    task: BenchmarkTask,
    task_input_dir: Path,
    execution_dir: Path,
    run_dir: Path,
    executor: Executor,
    runtime_model: str | None,
    runtime_settings: Mapping[str, Any],
    skill_dir: Path | None = None,
    intervention_prompt: str | None = None,
) -> dict[str, Any]:
    workspace = execution_dir / "workspace"
    deliverables = execution_dir / "deliverables"
    workspace.mkdir(parents=True, exist_ok=True)
    saved_references = read_json(task_input_dir / "task.json").get("saved_reference_files", [])
    if not isinstance(saved_references, list):
        raise ArtifactError(f"saved reference metadata is invalid for {task.task_id}")
    _copy_saved_references(task_input_dir / "references", workspace, saved_references)
    skill_entries = _copy_saved_skill(skill_dir, workspace)
    prompt = render_application_prompt(task)
    if intervention_prompt is not None:
        prompt = _intervention_prompt_fragment(intervention_prompt) + prompt
    if skill_entries:
        prompt = (
            _skill_prompt_fragment(workspace / "skill")
            + "The Skill is part of the selected application condition; do not disclose condition labels.\n\n"
            + prompt
        )
    (execution_dir / "participant_prompt.txt").write_text(prompt, encoding="utf-8")
    try:
        result = executor.execute(
            ExecutionRequest(
                prompt=prompt,
                cwd=workspace,
                model=runtime_model,
                settings=runtime_settings,
                purpose="application",
            )
        )
    except Exception as exc:  # Preserve a failed task record so resume can continue it.
        result = _failed_result(exc)
    (execution_dir / "codex_events.jsonl").write_text(result.stdout, encoding="utf-8")
    (execution_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    (execution_dir / "agent_response.txt").write_text(result.parsed.final_text, encoding="utf-8")
    entries = file_manifest(deliverables) if deliverables.exists() else []
    if result.status == "completed":
        from .artifacts import copy_workspace_deliverables

        entries = copy_workspace_deliverables(workspace, deliverables, exclude_top_level=("reference_files", "skill"))
    # The final response is an artifact as well, so a text-only GDPval task can
    # be evaluated without special-casing a missing deliverable file.
    response_artifact = deliverables / "agent_response.txt"
    if not response_artifact.exists():
        response_artifact.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(execution_dir / "agent_response.txt", response_artifact)
    entries = file_manifest(deliverables)
    write_json(execution_dir / "artifact_manifest.json", entries)
    record = _execution_dict(result, run_dir, execution_dir)
    record["artifact_files"] = entries
    record["artifact_sha256"] = manifest_hash(entries)
    record["participant_prompt_sha256"] = sha256_bytes(prompt.encode())
    record["skill_files"] = skill_entries
    record["skill_delivery"] = "file_and_prompt" if skill_entries else "none"
    capability = next((event for event in result.parsed.events if event.get("environment_profile")), None)
    if capability is not None:
        record["capability_evidence"] = capability
    return record


def _auth_or_raise(
    executor: Executor, settings: Mapping[str, Any], model: str | None = None, purpose: str = "application"
) -> AuthStatus:
    auth = preflight_executor(executor, model, settings, purpose)
    if not auth.available:
        raise HarnessError(auth.detail)
    if not auth.authenticated:
        raise HarnessError(f"Codex account authentication is unavailable: {auth.detail}")
    return auth


def _validate_creation_sources(build_config: BuildConfig) -> None:
    """Validate every frozen creation source before any creator can run."""

    for source in (*build_config.input_paths, *build_config.skill_paths):
        if source.is_symlink():
            raise ArtifactError(f"symbolic link is not allowed in Skill creation input: {source}")
        if source.is_dir():
            # file_manifest walks the complete tree and rejects nested links.
            file_manifest(source)
        elif not source.is_file():
            raise ArtifactError(f"Skill creation input is not a regular file or directory: {source}")


def _preflight_interventions(
    config: ExperimentConfig,
    primary_executor: Executor,
    executor_factory: ExecutorFactory | None,
    *,
    check_auth: bool,
) -> None:
    """Check all condition Skills and creator runtimes before the first model call."""

    creator_runtimes: list[RuntimeConfig] = []
    creator_bases: list[tuple[Any, Any]] = []
    for condition in config.conditions:
        intervention = condition.intervention
        if intervention is None:
            continue
        if intervention.path is not None:
            # Stage to a disposable directory so the existing Skill's frontmatter
            # and complete tree are checked without changing the run output.
            with tempfile.TemporaryDirectory(prefix="eval-harness-skill-check-") as temporary:
                stage_skill(intervention.path, Path(temporary) / "skill")
            if config.comparison_design == "matched_skills":
                source = intervention.path if intervention.path.is_dir() else intervention.path.parent
                manifest_path = source / "skill_manifest.json"
                if not manifest_path.is_file():
                    raise ConfigError("matched_skills requires creator provenance for every existing Skill")
                manifest = read_json(manifest_path)
                creator_runtimes.append(_saved_runtime(manifest.get("runtime"), "Skill creator"))
                if manifest.get("creator_status") != "completed":
                    raise ConfigError("matched_skills requires completed creator provenance")
                with tempfile.TemporaryDirectory(prefix="eval-harness-skill-content-") as directory:
                    content = copy_skill_for_application(source, Path(directory) / "skill")
                if manifest_hash(content) != manifest.get("generated_sha256"):
                    raise ConfigError("matched_skills existing Skill differs from its recorded creation version")
                snapshot = manifest.get("config_snapshot", {})
                inputs = manifest.get("creation_inputs", [])
                if not isinstance(snapshot, dict) or not isinstance(inputs, list):
                    raise ConfigError("matched_skills requires recorded creation brief and inputs")
                creator_bases.append(
                    (
                        snapshot.get("prompt", snapshot.get("instructions")),
                        [(entry.get("kind"), entry.get("sha256")) for entry in inputs],
                    )
                )
        if intervention.build is not None:
            build_config = load_build_config(intervention.build)
            creator_runtimes.append(build_config.runtime)
            creator_bases.append(
                (
                    build_config.prompt,
                    [(entry["kind"], entry["sha256"]) for entry in _source_manifest(build_config.input_paths)],
                )
            )
            _validate_creation_sources(build_config)
            if check_auth:
                creator_executor = _executor_for(build_config.runtime, primary_executor, executor_factory)
                _auth_or_raise(
                    creator_executor, build_config.runtime.settings, build_config.runtime.model, "skill_creation"
                )
    if config.comparison_design == "matched_skills":
        if not creator_runtimes or any(runtime != creator_runtimes[0] for runtime in creator_runtimes):
            raise ConfigError("matched_skills requires identical creator model and settings for S/A Skills")
        if any(not isinstance(brief, str) or not brief for brief, _ in creator_bases) or any(
            basis != creator_bases[0] for basis in creator_bases
        ):
            raise ConfigError("matched_skills requires identical creation briefs and input versions for S/A Skills")
        if any(c.intervention is not None and c.intervention.prompt is not None for c in config.conditions):
            raise ConfigError(
                "matched_skills conditions must differ by selected Skill only; inline prompts are unsupported"
            )


def _preflight_evaluation(
    config: ExperimentConfig,
    primary_executor: Executor,
    executor_factory: ExecutorFactory | None,
    *,
    check_auth: bool,
) -> AuthStatus | None:
    """Validate evaluation prerequisites before any participant generation."""

    evaluation = config.evaluation
    if evaluation is None:
        return None
    if evaluation.method == "human":
        # Validate only the source representation here.  Mapping rows are
        # matched to saved generations during evaluation, after artifacts have
        # been frozen; no score or judgment is produced by this preflight.
        from .evaluate_pipeline import _human_rating_rows

        _human_rating_rows(evaluation.runtime.settings)
        return None
    if evaluation.method == "mechanical" or not check_auth:
        return None
    status: AuthStatus | None = None
    for runtime in [j.runtime for j in evaluation.judges] or [evaluation.runtime]:
        evaluator = _executor_for(runtime, primary_executor, executor_factory)
        status = _auth_or_raise(evaluator, runtime.settings, runtime.model, "evaluation")
    return status


def _freeze_condition_sources(config: ExperimentConfig, run_dir: Path) -> ExperimentConfig:
    """Copy every condition source into the run before invoking any creator."""

    frozen_root = run_dir / "inputs" / "conditions"
    frozen_conditions: list[ConditionConfig] = []
    for condition in config.conditions:
        intervention = condition.intervention
        if intervention is None:
            frozen_conditions.append(condition)
            continue
        condition_root = frozen_root / task_directory_name(condition.id)
        if intervention.path is not None:
            frozen_path = condition_root / "skill"
            stage_skill(intervention.path, frozen_path)
            frozen_intervention = InterventionConfig(path=frozen_path, prompt=intervention.prompt)
        elif intervention.build is not None:
            build_config = load_build_config(intervention.build)
            frozen = freeze_build_config(build_config, condition_root / "creation")
            frozen_intervention = InterventionConfig(build=frozen.config_path, prompt=intervention.prompt)
        else:
            frozen_intervention = intervention
        frozen_conditions.append(replace(condition, intervention=frozen_intervention))
    return replace(config, conditions=tuple(frozen_conditions))


def _validate_and_load(config: ExperimentConfig) -> tuple[list[BenchmarkTask], list[BenchmarkTask]]:
    errors = validate_config(config)
    if errors:
        raise ConfigError("configuration is invalid:\n" + "\n".join(f"- {error}" for error in errors))
    tasks = load_tasks(config)
    selected = select_tasks(tasks, config)
    for task in selected:
        reference_source_paths(task)
        if config.evaluation is not None:
            from .grading_criteria import criteria_for_task

            criteria_for_task(config.evaluation.criteria, task.task_id, config.benchmark)
    return tasks, selected


def _executor_for(runtime: RuntimeConfig, primary: Executor, executor_factory: ExecutorFactory | None) -> Executor:
    return executor_factory(runtime.executor) if executor_factory is not None else primary


def _prepare_condition_skill(
    condition: ConditionConfig,
    run_dir: Path,
    primary_executor: Executor,
    executor_factory: ExecutorFactory | None,
    *,
    check_auth: bool,
) -> tuple[Path | None, dict[str, Any] | None]:
    intervention = condition.intervention
    if intervention is None:
        return None, None
    target = run_dir / "skills" / task_directory_name(condition.id)
    if intervention.path is not None:
        entries = stage_skill(intervention.path, target)
        metadata: dict[str, Any] = {
            "kind": "existing",
            "source": str(intervention.path),
            "prompt": intervention.prompt,
            "files": entries,
            "sha256": manifest_hash(entries),
            "skill_path": str(target.relative_to(run_dir)),
        }
        if (target / "skill_manifest.json").is_file():
            provenance = read_json(target / "skill_manifest.json")
            for key in (
                "creation_id",
                "runtime",
                "generated_sha256",
                "creator_status",
                "creator_elapsed_seconds",
                "creator_usage",
                "creator_cost_usd",
            ):
                metadata[key if key != "runtime" else "creator_runtime"] = provenance.get(key)
            metadata["creation_in_this_run"] = False
        write_json(target / "application_skill.json", metadata)
        return target, metadata
    if intervention.build is None:
        if intervention.prompt is None:
            raise ConfigError(f"condition {condition.id} has an empty Skill intervention")
        return None, {"kind": "prompt", "prompt": intervention.prompt}
    build_config = load_build_config(intervention.build)
    build_executor = _executor_for(build_config.runtime, primary_executor, executor_factory)
    # Keep an inline condition container separate from the generated Skill so
    # the reusable Skill's directory basename can remain exactly build.name.
    build_target = target / build_config.name
    if (build_target / "skill_manifest.json").is_file():
        build_output = resume_skill_build(build_target, build_executor, check_auth=check_auth)
    else:
        build_output = build_skill(build_config, build_target, build_executor, check_auth=check_auth)
    manifest = read_json(build_output / "skill_manifest.json")
    if not isinstance(manifest, dict):
        raise ArtifactError(f"inline Skill build did not write a valid manifest: {build_output}")
    metadata = {
        "kind": "built",
        "source_config": str(build_config.config_path),
        "prompt": intervention.prompt,
        "creation_id": manifest.get("creation_id"),
        "creator_runtime": manifest.get("runtime"),
        "creation_in_this_run": True,
        "files": manifest.get("generated_files", []),
        "sha256": manifest.get("generated_sha256"),
        "name": manifest.get("name"),
        "skill_path": str(build_output.relative_to(run_dir)),
        "creator_status": manifest.get("creator_status"),
        "creator_elapsed_seconds": manifest.get("creator_elapsed_seconds"),
        "creator_usage": manifest.get("creator_usage"),
        "creator_cost_usd": manifest.get("creator_cost_usd"),
    }
    write_json(target / "application_skill.json", metadata)
    return build_output, metadata


def _built_skill_metadata(
    build_output: Path,
    run_dir: Path,
    source_config: Path,
    prompt: str | None,
) -> dict[str, Any]:
    """Read a completed or resumed creator manifest into the run snapshot."""

    manifest = read_json(build_output / "skill_manifest.json")
    if not isinstance(manifest, dict):
        raise ArtifactError(f"inline Skill build did not write a valid manifest: {build_output}")
    return {
        "kind": "built",
        "source_config": str(source_config),
        "prompt": prompt,
        "creation_id": manifest.get("creation_id"),
        "creator_runtime": manifest.get("runtime"),
        "creation_in_this_run": True,
        "files": manifest.get("generated_files", []),
        "sha256": manifest.get("generated_sha256"),
        "name": manifest.get("name"),
        "skill_path": str(build_output.relative_to(run_dir)),
        "creator_status": manifest.get("creator_status"),
        "creator_elapsed_seconds": manifest.get("creator_elapsed_seconds"),
        "creator_usage": manifest.get("creator_usage"),
        "creator_cost_usd": manifest.get("creator_cost_usd"),
    }


def _planned_state(
    config: ExperimentConfig,
    selected: list[BenchmarkTask],
    run_dir: Path,
    skill_metadata: Mapping[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Create the complete append-only execution journal before any CLI call."""

    state: list[dict[str, Any]] = []
    for condition in config.conditions:
        for task in selected:
            for repeat in range(config.repeats):
                execution_dir = (
                    run_dir
                    / "conditions"
                    / task_directory_name(condition.id)
                    / "tasks"
                    / task_directory_name(task.task_id)
                    / f"repeat_{repeat}"
                )
                execution_dir.mkdir(parents=True, exist_ok=True)
                record: dict[str, Any] = {
                    "condition_id": condition.id,
                    "task_id": task.task_id,
                    "repeat": repeat,
                    "execution_dir": str(execution_dir.relative_to(run_dir)),
                    "execution_status": "pending",
                    "attempt_count": 0,
                    "attempt_history": [],
                    "evaluation_status": "pending",
                    "task_success": None,
                    "skill": skill_metadata[condition.id],
                }
                write_json(execution_dir / "execution.json", record)
                state.append(record)
    return state


def _execution_path(run_dir: Path, record: Mapping[str, Any]) -> Path:
    """Resolve a journal path while refusing paths outside the run root."""

    value = record.get("execution_dir")
    if not isinstance(value, str) or not value:
        raise ArtifactError("run state has an invalid execution_dir")
    root = run_dir.resolve()
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ArtifactError(f"run state execution_dir escapes the run directory: {value!r}") from exc
    return candidate


def _archive_current_attempt(execution_dir: Path, attempt_number: int) -> None:
    """Move the previous mutable attempt aside before retrying it."""

    archive_root = execution_dir / "attempts" / f"attempt_{attempt_number}"
    if archive_root.exists():
        raise ArtifactError(f"retry archive already exists: {archive_root}")
    archive_root.mkdir(parents=True, exist_ok=False)
    for child in sorted(execution_dir.iterdir()):
        if child.name == "attempts":
            continue
        shutil.move(str(child), str(archive_root / child.name))


def _write_execution_record(run_dir: Path, state: list[dict[str, Any]], record: Mapping[str, Any]) -> None:
    """Persist both the per-task record and the complete state journal atomically."""

    execution_dir = _execution_path(run_dir, record)
    write_json(execution_dir / "execution.json", dict(record))
    write_json(run_dir / "run_state.json", state)


def _execute_record(
    record: dict[str, Any],
    task: BenchmarkTask,
    condition: ConditionConfig,
    input_task_dir: Path,
    run_dir: Path,
    executor: Executor,
    skill_dir: Path | None,
    max_retries: int,
    state: list[dict[str, Any]],
) -> bool:
    """Run one planned record, returning whether it interrupted the scheduler."""

    execution_dir = _execution_path(run_dir, record)
    previous_attempts = record.get("attempt_count", 0)
    if isinstance(previous_attempts, bool) or not isinstance(previous_attempts, int) or previous_attempts < 0:
        raise ArtifactError(f"run state has invalid attempt_count for {record.get('task_id')!r}")
    history_value = record.get("attempt_history", [])
    if not isinstance(history_value, list):
        raise ArtifactError(f"run state has invalid attempt_history for {record.get('task_id')!r}")
    history = [dict(item) for item in history_value if isinstance(item, Mapping)]

    for retry_index in range(max_retries + 1):
        attempt_number = previous_attempts + retry_index
        if attempt_number > 0:
            _archive_current_attempt(execution_dir, attempt_number - 1)
        refreshed = _record_workspace(
            task,
            input_task_dir,
            execution_dir,
            run_dir,
            executor,
            condition.application.model,
            condition.application.settings,
            skill_dir,
            condition.intervention.prompt if condition.intervention is not None else None,
        )
        history.append(
            {
                "attempt": attempt_number,
                "execution_status": refreshed.get("execution_status"),
                "returncode": refreshed.get("returncode"),
                "elapsed_seconds": refreshed.get("elapsed_seconds"),
                "usage": refreshed.get("usage"),
                "cost_usd": refreshed.get("cost_usd"),
                "error": refreshed.get("error"),
            }
        )
        refreshed.update(
            {
                "condition_id": condition.id,
                "task_id": task.task_id,
                "repeat": record.get("repeat"),
                "creation_repeat": record.get("creation_repeat", 0),
                "cohort_parent_id": record.get("cohort_parent_id"),
                "execution_dir": record["execution_dir"],
                "skill": record.get("skill"),
                "attempt_count": attempt_number + 1,
                "attempt_history": history,
            }
        )
        record.clear()
        record.update(refreshed)
        _write_execution_record(run_dir, state, record)
        status = record.get("execution_status")
        if status in {"completed", "interrupted"}:
            return bool(status == "interrupted")
    return False


def _execute_state(
    config: ExperimentConfig,
    selected: list[BenchmarkTask],
    state: list[dict[str, Any]],
    run_dir: Path,
    primary_executor: Executor,
    executor_factory: ExecutorFactory | None,
    skill_paths: Mapping[str, Path | None],
) -> tuple[bool, bool]:
    """Execute pending/failed records in journal order until completion or interruption."""

    tasks = {task.task_id: task for task in selected}
    conditions = {condition.id: condition for condition in config.conditions}
    changed = False
    for record in state:
        if record.get("execution_status") == "completed":
            continue
        condition_id = record.get("condition_id")
        task_id = record.get("task_id")
        repeat = record.get("repeat")
        if not isinstance(condition_id, str) or not isinstance(task_id, str) or not isinstance(repeat, int):
            raise ArtifactError("run state record has invalid identity")
        condition = conditions.get(condition_id)
        task = tasks.get(task_id)
        if condition is None:
            raise ArtifactError(f"run state references unknown condition: {condition_id}")
        if task is None:
            raise ArtifactError(f"run state references task no longer selected: {task_id}")
        input_task_dir = run_dir / "inputs" / "tasks" / task_directory_name(task_id)
        interrupted = _execute_record(
            record,
            task,
            condition,
            input_task_dir,
            run_dir,
            _executor_for(condition.application, primary_executor, executor_factory),
            skill_paths.get(condition_id),
            config.limits.max_retries,
            state,
        )
        changed = True
        if interrupted:
            return True, changed
    return False, changed


def _state_counts(state: Sequence[Mapping[str, Any]]) -> tuple[int, int, int, str]:
    completed = sum(record.get("execution_status") == "completed" for record in state)
    pending = sum(record.get("execution_status") == "pending" for record in state)
    failed = len(state) - completed - pending
    interrupted = any(record.get("execution_status") == "interrupted" for record in state)
    if interrupted:
        status = "interrupted"
    elif pending:
        status = "partial"
    elif failed == 0:
        status = "completed"
    elif completed == 0:
        status = "failed"
    else:
        status = "partial"
    return completed, failed, pending, status


def _auto_evaluate(
    config: ExperimentConfig,
    run_dir: Path,
    executor: Executor,
    executor_factory: ExecutorFactory | None,
    *,
    check_auth: bool,
) -> tuple[Path | None, str, Path | None]:
    """Run configured evaluation and comparison after all planned executions finish."""

    if config.evaluation is None:
        return None, "not_started", None
    from .evaluate_pipeline import evaluate_run

    evaluation_executor = (
        executor
        if config.evaluation.method in {"mechanical", "human"}
        else _executor_for(config.evaluation.runtime, executor, executor_factory)
    )
    evaluation_dir = run_dir / "evaluations" / f"{config.evaluation.method}-{uuid.uuid4().hex[:12]}"
    comparison_dir: Path | None = None
    try:
        evaluation_summary = evaluate_run(
            run_dir,
            config.evaluation,
            evaluation_dir,
            evaluation_executor,
            check_auth=check_auth,
            executor_factory=executor_factory,
        )
        evaluation_status = evaluation_summary.status
        from .compare_pipeline import compare_evaluations

        comparison_dir = run_dir / "comparison"
        if comparison_dir.exists():
            comparison_dir = run_dir / "comparisons" / f"comparison-{uuid.uuid4().hex[:12]}"
        compare_evaluations([evaluation_dir], comparison_dir)
    except (HarnessError, ArtifactError, ConfigError) as exc:
        evaluation_status = "failed"
        write_json(
            run_dir / "evaluation_error.json",
            {"error": str(exc), "evaluation_config": config.evaluation.method},
        )
    return evaluation_dir, evaluation_status, comparison_dir


def _resume_auto_evaluation(
    config: ExperimentConfig,
    run_dir: Path,
    evaluation_dir: Path,
    executor: Executor,
    executor_factory: ExecutorFactory | None,
    *,
    check_auth: bool,
) -> tuple[str, Path | None]:
    """Continue an incomplete auto-evaluation without regenerating artifacts."""

    if config.evaluation is None:
        return "not_started", None
    from .evaluate_pipeline import resume_evaluation

    evaluation_executor = (
        executor
        if config.evaluation.method in {"mechanical", "human"}
        else _executor_for(config.evaluation.runtime, executor, executor_factory)
    )
    comparison_dir: Path | None = None
    try:
        summary = resume_evaluation(
            evaluation_dir, evaluation_executor, check_auth=check_auth, executor_factory=executor_factory
        )
        evaluation_status = summary.status
        from .compare_pipeline import compare_evaluations

        comparison_dir = run_dir / "comparison"
        if comparison_dir.exists():
            comparison_dir = run_dir / "comparisons" / f"comparison-{uuid.uuid4().hex[:12]}"
        compare_evaluations([evaluation_dir], comparison_dir)
    except (HarnessError, ArtifactError, ConfigError) as exc:
        evaluation_status = "failed"
        write_json(
            run_dir / "evaluation_error.json",
            {
                "error": str(exc),
                "evaluation_config": config.evaluation.method,
                "evaluation_dir": str(evaluation_dir.relative_to(run_dir)),
            },
        )
    return evaluation_status, comparison_dir


def _write_frozen_input_manifest(run_dir: Path) -> tuple[list[dict[str, Any]], str]:
    """Record the exact task snapshots and copied references used by a run."""

    input_root = run_dir / "inputs"
    entries = file_manifest(input_root)
    write_json(input_root / "input_manifest.json", entries)
    return entries, manifest_hash(entries)


def _verify_frozen_input_manifest(run_dir: Path, run_manifest: Mapping[str, Any]) -> None:
    """Reject a resume after any frozen task snapshot or reference changed."""

    manifest_path = run_dir / "inputs" / "input_manifest.json"
    if not manifest_path.is_file():
        # Runs written before the manifest was introduced remain resumable from
        # their copied task snapshots; new runs always write this file.
        if run_manifest.get("input_manifest_sha256") is not None:
            raise ArtifactError(f"frozen input manifest is missing: {manifest_path}")
        return
    expected = read_json(manifest_path)
    if not isinstance(expected, list) or any(not isinstance(item, Mapping) for item in expected):
        raise ArtifactError(f"frozen input manifest is invalid: {manifest_path}")
    current = [entry for entry in file_manifest(run_dir / "inputs") if entry["path"] != "input_manifest.json"]
    if current != [dict(item) for item in expected]:
        raise ArtifactError("frozen task inputs or references changed")
    expected_hash = run_manifest.get("input_manifest_sha256")
    if expected_hash is not None and (not isinstance(expected_hash, str) or manifest_hash(current) != expected_hash):
        raise ArtifactError("frozen input manifest hash does not match the run manifest")


def run_experiment(
    config: ExperimentConfig,
    output_dir: str | Path,
    executor: Executor,
    *,
    check_auth: bool = True,
    executor_factory: ExecutorFactory | None = None,
    _prepare_only: bool = False,
) -> RunSummary:
    """Execute selected benchmark tasks and persist all inputs and outputs."""

    if config.creation_repeats > 1:
        from .replication_pipeline import run_cohorts

        return run_cohorts(config, output_dir, executor, check_auth=check_auth, executor_factory=executor_factory)
    _, selected = _validate_and_load(config)
    if check_auth:
        _auth_or_raise(executor, config.application.settings, config.application.model)
        for condition in config.conditions:
            condition_executor = _executor_for(condition.application, executor, executor_factory)
            if condition_executor is not executor or condition.application.settings != config.application.settings:
                _auth_or_raise(condition_executor, condition.application.settings, condition.application.model)
    _preflight_interventions(config, executor, executor_factory, check_auth=check_auth)
    _preflight_evaluation(config, executor, executor_factory, check_auth=check_auth)
    run_dir = ensure_new_output(output_dir)
    run_id = uuid.uuid4().hex
    initial_snapshot = snapshot_mapping(config)
    write_json(run_dir / "config.resolved.json", initial_snapshot)
    (run_dir / "config.source.yaml").write_bytes(config.source_bytes)
    write_json(
        run_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "created_at": _timestamp(),
            "benchmark": config.benchmark,
            "config_sha256": sha256_bytes(config.source_bytes),
            "config_path": str(config.config_path),
            "config_snapshot": initial_snapshot,
            "source_freeze_status": "pending",
            "execution_status": "not_started",
            "evaluation_status": "not_started",
            "task_success": None,
            "selected_task_ids": [task.task_id for task in selected],
            "conditions": [condition.id for condition in config.conditions],
        },
    )
    try:
        # Freeze all condition build inputs and reusable Skills before the
        # first creator can run. Later creators therefore cannot observe
        # source edits made after an earlier creator call.
        run_config = _freeze_condition_sources(config, run_dir)
    except (Exception, KeyboardInterrupt) as exc:
        manifest = read_json(run_dir / "run_manifest.json")
        manifest.update(
            {
                "source_freeze_status": "failed",
                "failure_stage": "input_freeze",
                "failure_error": str(exc) or "condition input freeze interrupted",
            }
        )
        write_json(run_dir / "run_manifest.json", manifest)
        raise
    config_snapshot = snapshot_mapping(run_config)
    write_json(run_dir / "config.resolved.json", config_snapshot)
    manifest = read_json(run_dir / "run_manifest.json")
    manifest.update(
        {
            "config_snapshot": config_snapshot,
            "source_freeze_status": "completed",
            "conditions": [condition.id for condition in run_config.conditions],
        }
    )
    write_json(run_dir / "run_manifest.json", manifest)
    input_root = run_dir / "inputs"
    for task in selected:
        input_task_dir = input_root / "tasks" / task_directory_name(task.task_id)
        input_ref_dir = input_task_dir / "references"
        saved_refs = copy_reference_files(task, input_ref_dir)
        write_json(input_task_dir / "task.json", task_snapshot(task, saved_refs))
    _, input_manifest_sha256 = _write_frozen_input_manifest(run_dir)
    manifest = read_json(run_dir / "run_manifest.json")
    manifest.update(
        {
            "input_manifest_path": "inputs/input_manifest.json",
            "input_manifest_sha256": input_manifest_sha256,
        }
    )
    write_json(run_dir / "run_manifest.json", manifest)

    # Freeze task/condition identities before any optional Skill creator call.
    # A failed creator therefore leaves a resumable pending journal.
    skill_metadata: dict[str, dict[str, Any] | None] = {condition.id: None for condition in run_config.conditions}
    state = _planned_state(run_config, selected, run_dir, skill_metadata)
    write_json(run_dir / "run_state.json", state)
    if _prepare_only:
        return RunSummary(run_dir, run_id, "not_started", len(state), 0, 0, pending_count=len(state))
    skill_paths: dict[str, Path | None] = {}
    for condition in run_config.conditions:
        try:
            skill_path, metadata = _prepare_condition_skill(
                condition,
                run_dir,
                executor,
                executor_factory,
                check_auth=check_auth,
            )
        except (Exception, KeyboardInterrupt) as exc:
            # Keep a resumable run journal when creator setup or execution
            # fails before the first application call.
            manifest = read_json(run_dir / "run_manifest.json")
            manifest.update(
                {
                    "skills": skill_metadata,
                    "execution_status": "failed",
                    "failure_stage": "skill_creation",
                    "failure_condition_id": condition.id,
                    "failure_error": str(exc) or "Skill creation interrupted",
                }
            )
            write_json(run_dir / "run_manifest.json", manifest)
            write_json(run_dir / "run_state.json", state)
            raise
        skill_paths[condition.id] = skill_path
        skill_metadata[condition.id] = metadata
        for record in state:
            if record.get("condition_id") == condition.id:
                record["skill"] = metadata
        write_json(run_dir / "run_state.json", state)
        manifest = read_json(run_dir / "run_manifest.json")
        manifest["skills"] = skill_metadata
        write_json(run_dir / "run_manifest.json", manifest)
    interrupted, _ = _execute_state(
        run_config,
        selected,
        state,
        run_dir,
        executor,
        executor_factory,
        skill_paths,
    )
    completed, failed, pending, execution_status = _state_counts(state)
    manifest = read_json(run_dir / "run_manifest.json")
    manifest.update(
        {
            "execution_status": execution_status,
            "evaluation_status": "not_started",
            "task_success": None,
            "task_count": len(state),
            "completed_count": completed,
            "failed_count": failed,
            "pending_count": pending,
            "interrupted": interrupted,
        }
    )
    evaluation_dir: Path | None = None
    evaluation_status = "not_started"
    comparison_dir: Path | None = None
    if not pending and not interrupted:
        evaluation_dir, evaluation_status, comparison_dir = _auto_evaluate(
            run_config, run_dir, executor, executor_factory, check_auth=check_auth
        )
    manifest = read_json(run_dir / "run_manifest.json")
    manifest.update(
        {
            "evaluation_status": evaluation_status,
            "evaluation_dir": str(evaluation_dir.relative_to(run_dir)) if evaluation_dir else None,
            "comparison_dir": str(comparison_dir.relative_to(run_dir)) if comparison_dir else None,
        }
    )
    write_json(run_dir / "run_manifest.json", manifest)
    return RunSummary(
        run_dir,
        run_id,
        execution_status,
        len(state),
        completed,
        failed,
        evaluation_dir,
        evaluation_status,
        comparison_dir,
        pending,
    )


def _reconcile_completed_execution_journals(run_dir: Path, state: list[dict[str, Any]]) -> bool:
    """Recover a completed task journal if the aggregate state write was interrupted."""

    changed = False
    for record in state:
        execution_dir = _execution_path(run_dir, record)
        journal_path = execution_dir / "execution.json"
        if not journal_path.is_file():
            continue
        journal = read_json(journal_path)
        if not isinstance(journal, Mapping) or journal.get("execution_status") != "completed":
            continue
        for field in ("condition_id", "task_id", "repeat", "execution_dir"):
            if journal.get(field) != record.get(field):
                raise ArtifactError(f"completed execution journal identity mismatch: {journal_path}")
        deliverables = execution_dir / "deliverables"
        expected_hash = journal.get("artifact_sha256")
        artifact_manifest = execution_dir / "artifact_manifest.json"
        if not isinstance(expected_hash, str) or not deliverables.is_dir() or not artifact_manifest.is_file():
            raise ArtifactError(f"completed execution journal has incomplete artifacts: {journal_path}")
        entries = file_manifest(deliverables)
        saved_entries = read_json(artifact_manifest)
        if not isinstance(saved_entries, list) or saved_entries != entries or manifest_hash(entries) != expected_hash:
            raise ArtifactError(f"completed execution journal artifact hash mismatch: {journal_path}")
        if record.get("execution_status") != "completed":
            record.clear()
            record.update(journal)
            changed = True
    if changed:
        write_json(run_dir / "run_state.json", state)
    return changed


def _load_state(run_dir: Path) -> list[dict[str, Any]]:
    state = read_json(run_dir / "run_state.json")
    if not isinstance(state, list) or any(not isinstance(item, dict) for item in state):
        raise ArtifactError(f"invalid run state: {run_dir / 'run_state.json'}")
    _reconcile_completed_execution_journals(run_dir, state)
    return state


def _saved_runtime(value: Any, field: str) -> RuntimeConfig:
    if not isinstance(value, Mapping):
        raise ArtifactError(f"saved run is missing resolved {field} runtime")
    executor = value.get("executor")
    model = value.get("model")
    settings = value.get("settings", {})
    if not isinstance(executor, str) or not executor:
        raise ArtifactError(f"saved run has invalid {field}.executor")
    if model is not None and not isinstance(model, str):
        raise ArtifactError(f"saved run has invalid {field}.model")
    if not isinstance(settings, Mapping):
        raise ArtifactError(f"saved run has invalid {field}.settings")
    return RuntimeConfig(executor, model, dict(settings))


def _find_saved_skill(root: Path, condition_id: str, saved: Mapping[str, Any] | None) -> Path | None:
    """Find the staged/generated Skill even for runs written before skill_path metadata."""

    candidates: list[Path] = []
    if saved is not None and isinstance(saved.get("skill_path"), str):
        candidates.append((root / str(saved["skill_path"])).resolve())
    container = root / "skills" / task_directory_name(condition_id)
    candidates.append(container)
    if container.is_dir():
        candidates.extend(path for path in sorted(container.iterdir()) if path.is_dir())
    for candidate in candidates:
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ArtifactError(f"saved Skill path escapes the run: {candidate}") from exc
        if (candidate / "SKILL.md").is_file() or (candidate / ".creation" / "config" / "build.yaml").is_file():
            return candidate
    return None


def _saved_source_path(root: Path, value: Any, field: str) -> Path | None:
    """Resolve a frozen intervention source while refusing external paths."""

    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value).expanduser().resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        # Pre-freeze runs may record an original source path.  Never reopen it;
        # the caller will require a staged source or report an incomplete run.
        return None
    return candidate


def _saved_experiment(root: Path, manifest: Mapping[str, Any], state: Sequence[Mapping[str, Any]]) -> ExperimentConfig:
    """Reconstruct a run solely from its frozen manifest, snapshots and staged files."""

    snapshot = manifest.get("config_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ArtifactError("run manifest has no frozen config snapshot")
    resolved = snapshot.get("_resolved")
    if not isinstance(resolved, Mapping) or not isinstance(resolved.get("application"), Mapping):
        # Early runs already contain a copied source YAML and task snapshots,
        # so recover runtime values from that copy while never reopening the
        # original source configuration or task file.
        source_copy = root / "config.source.yaml"
        try:
            loaded = yaml.safe_load(source_copy.read_bytes()) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ArtifactError(
                "run predates resolved configuration snapshots and its copied config is unreadable"
            ) from exc
        if not isinstance(loaded, Mapping):
            raise ArtifactError("copied run configuration is not a mapping")
        loaded_mapping = dict(loaded)
        fallback_application = _runtime(loaded_mapping.get("application"), "application", base_dir=root)
        fallback_conditions: list[dict[str, Any]] = []
        condition_values = loaded_mapping.get("conditions", [])
        if not isinstance(condition_values, list):
            raise ArtifactError("copied run configuration has invalid conditions")
        saved_values = manifest.get("skills", {})
        if not isinstance(saved_values, Mapping):
            saved_values = {}
        for condition_value in condition_values:
            if not isinstance(condition_value, Mapping) or not isinstance(condition_value.get("id"), str):
                raise ArtifactError("copied run configuration has an invalid condition")
            condition_id = str(condition_value["id"])
            saved_value = saved_values.get(condition_id)
            saved_mapping = saved_value if isinstance(saved_value, Mapping) else None
            candidate = _find_saved_skill(root, condition_id, saved_mapping)
            condition_runtime = _runtime(
                condition_value.get("application"),
                f"conditions[{condition_id}].application",
                default=fallback_application,
                base_dir=root,
            )
            intervention_value = condition_value.get("intervention")
            intervention_prompt = (
                intervention_value.get("prompt")
                if isinstance(intervention_value, Mapping) and isinstance(intervention_value.get("prompt"), str)
                else None
            )
            fallback_intervention = None
            if candidate is not None:
                fallback_intervention = {"path": str(candidate), "build": None, "prompt": intervention_prompt}
            elif intervention_prompt is not None:
                fallback_intervention = {"path": None, "build": None, "prompt": intervention_prompt}
            fallback_conditions.append(
                {
                    "id": condition_id,
                    "application": {
                        "executor": condition_runtime.executor,
                        "model": condition_runtime.model,
                        "settings": condition_runtime.settings,
                    },
                    "intervention": fallback_intervention,
                }
            )
        evaluation_value = loaded_mapping.get("evaluation")
        fallback_evaluation = None
        if isinstance(evaluation_value, Mapping):
            fallback_eval_runtime = _runtime(evaluation_value, "evaluation", base_dir=root)
            fallback_evaluation = {
                "method": evaluation_value.get("method"),
                "executor": fallback_eval_runtime.executor,
                "model": fallback_eval_runtime.model,
                "settings": fallback_eval_runtime.settings,
            }
        resolved = {
            "application": {
                "executor": fallback_application.executor,
                "model": fallback_application.model,
                "settings": fallback_application.settings,
            },
            "conditions": fallback_conditions,
            "limits": loaded_mapping.get("limits", {}),
            "repeats": loaded_mapping.get("repeats", 1),
            "evaluation": fallback_evaluation,
        }
    benchmark = manifest.get("benchmark")
    if not isinstance(benchmark, str):
        raise ArtifactError("run manifest has no benchmark")
    ids_value = manifest.get("selected_task_ids")
    ids: list[str] = []
    if isinstance(ids_value, list):
        ids.extend(value for value in ids_value if isinstance(value, str))
    if not ids:
        ids.extend(
            value
            for value in (record.get("task_id") for record in state)
            if isinstance(value, str) and value not in ids
        )
    tasks: list[BenchmarkTask] = []
    rows: list[dict[str, Any]] = []
    for task_id in ids:
        snapshot_path = root / "inputs" / "tasks" / task_directory_name(task_id) / "task.json"
        task_snapshot_value = read_json(snapshot_path)
        if not isinstance(task_snapshot_value, Mapping):
            raise ArtifactError(f"invalid frozen task snapshot: {snapshot_path}")
        task = task_from_snapshot(task_snapshot_value, benchmark)
        if task.task_id != task_id:
            raise ArtifactError(f"frozen task identity mismatch: {snapshot_path}")
        tasks.append(task)
        raw = task_snapshot_value.get("raw")
        if not isinstance(raw, Mapping):
            raise ArtifactError(f"frozen task has no raw row: {snapshot_path}")
        rows.append(dict(raw))
    if not tasks:
        raise ArtifactError("run has no frozen selected task snapshots")
    application = _saved_runtime(resolved.get("application"), "application")
    saved_skills = manifest.get("skills", {})
    if not isinstance(saved_skills, Mapping):
        saved_skills = {}
    conditions_value = resolved.get("conditions")
    if not isinstance(conditions_value, list) or not conditions_value:
        raise ArtifactError("run has no frozen condition runtimes")
    conditions: list[ConditionConfig] = []
    for condition_value in conditions_value:
        if not isinstance(condition_value, Mapping) or not isinstance(condition_value.get("id"), str):
            raise ArtifactError("run has an invalid frozen condition")
        condition_id = condition_value["id"]
        intervention: InterventionConfig | None = None
        intervention_value = condition_value.get("intervention")
        intervention_prompt = (
            intervention_value.get("prompt")
            if isinstance(intervention_value, Mapping) and isinstance(intervention_value.get("prompt"), str)
            else None
        )
        saved_skill = saved_skills.get(condition_id)
        candidate = _find_saved_skill(
            root,
            condition_id,
            saved_skill if isinstance(saved_skill, Mapping) else None,
        )
        if candidate is not None:
            if (candidate / "SKILL.md").is_file():
                intervention = InterventionConfig(path=candidate, prompt=intervention_prompt)
            elif (candidate / ".creation" / "config" / "build.yaml").is_file():
                intervention = InterventionConfig(
                    build=candidate / ".creation" / "config" / "build.yaml", prompt=intervention_prompt
                )
        elif isinstance(intervention_value, Mapping):
            frozen_path = _saved_source_path(
                root, intervention_value.get("path"), f"condition {condition_id} Skill path"
            )
            frozen_build = _saved_source_path(
                root, intervention_value.get("build"), f"condition {condition_id} Skill build"
            )
            if frozen_path is not None and frozen_path.exists():
                intervention = InterventionConfig(path=frozen_path, prompt=intervention_prompt)
            elif frozen_build is not None and frozen_build.is_file():
                intervention = InterventionConfig(build=frozen_build, prompt=intervention_prompt)
            elif intervention_prompt is not None:
                intervention = InterventionConfig(prompt=intervention_prompt)
        elif intervention_prompt is not None:
            intervention = InterventionConfig(prompt=intervention_prompt)
        if intervention_value is not None and intervention is None:
            raise ArtifactError(f"saved Skill for condition {condition_id} is incomplete")
        conditions.append(
            ConditionConfig(
                condition_id,
                _saved_runtime(condition_value.get("application"), f"conditions[{condition_id}].application"),
                intervention,
            )
        )
    limits_value = resolved.get("limits", {})
    if not isinstance(limits_value, Mapping):
        raise ArtifactError("run has invalid frozen limits")
    try:
        limits = LimitsConfig(
            int(limits_value.get("max_tasks", len(tasks))),
            int(limits_value.get("max_retries", 0)),
            int(limits_value.get("concurrency", 1)),
        )
        repeats = int(resolved.get("repeats", 1))
    except (TypeError, ValueError) as exc:
        raise ArtifactError("run has invalid frozen limits or repeats") from exc
    evaluation_value = resolved.get("evaluation")
    evaluation: EvaluationConfig | None = None
    if evaluation_value is not None:
        if not isinstance(evaluation_value, Mapping) or not isinstance(evaluation_value.get("method"), str):
            raise ArtifactError("run has invalid frozen evaluation")
        evaluation = _evaluation(evaluation_value, root)
    raw = dict(snapshot)
    raw["benchmark"] = benchmark
    raw["tasks"] = {"rows": rows, "limit": len(rows), "ids": ids, "seed": 0}
    return ExperimentConfig(
        config_path=root / "config.source.yaml",
        benchmark=benchmark,
        tasks=TaskSelection(None, len(rows), 0, tuple(ids), tuple(rows), {}),
        repeats=repeats,
        application=application,
        conditions=tuple(conditions),
        evaluation=evaluation,
        limits=limits,
        raw=raw,
        source_bytes=(root / "config.source.yaml").read_bytes() if (root / "config.source.yaml").is_file() else b"",
        comparison_design=str(resolved.get("comparison_design", "general")),
        creation_repeats=int(resolved.get("creation_repeats", 1)),
    )


def _tasks_from_state(
    root: Path,
    manifest: Mapping[str, Any],
    state: Sequence[Mapping[str, Any]],
    benchmark: str,
) -> list[BenchmarkTask]:
    ids_value = manifest.get("selected_task_ids")
    ids: list[str] = []
    if isinstance(ids_value, list):
        ids.extend(value for value in ids_value if isinstance(value, str))
    if not ids:
        ids.extend(
            value
            for value in (record.get("task_id") for record in state)
            if isinstance(value, str) and value not in ids
        )
    tasks: list[BenchmarkTask] = []
    for task_id in ids:
        path = root / "inputs" / "tasks" / task_directory_name(task_id) / "task.json"
        snapshot = read_json(path)
        if not isinstance(snapshot, Mapping):
            raise ArtifactError(f"invalid frozen task snapshot: {path}")
        task = task_from_snapshot(snapshot, benchmark)
        if task.task_id != task_id:
            raise ArtifactError(f"frozen task identity mismatch: {path}")
        tasks.append(task)
    if not tasks:
        raise ArtifactError("run has no frozen selected task snapshots")
    return tasks


def resume_run(
    run_dir: str | Path,
    executor: Executor,
    *,
    check_auth: bool = True,
    executor_factory: ExecutorFactory | None = None,
) -> RunSummary:
    """Resume incomplete executions using the frozen source configuration."""

    root = Path(run_dir).expanduser().resolve()
    manifest = read_json(root / "run_manifest.json")
    if manifest.get("kind") == "creation_cohorts":
        from .replication_pipeline import resume_cohorts

        return resume_cohorts(root, executor, check_auth=check_auth, executor_factory=executor_factory)
    _verify_frozen_input_manifest(root, manifest)
    state = _load_state(root)
    config = _saved_experiment(root, manifest, state)
    errors = validate_config(config)
    if errors:
        raise ConfigError("frozen run configuration is invalid:\n" + "\n".join(f"- {error}" for error in errors))
    if check_auth:
        _auth_or_raise(executor, config.application.settings, config.application.model)
        for condition in config.conditions:
            condition_executor = _executor_for(condition.application, executor, executor_factory)
            if condition_executor is not executor or condition.application.settings != config.application.settings:
                _auth_or_raise(condition_executor, condition.application.settings, condition.application.model)
    _preflight_interventions(config, executor, executor_factory, check_auth=check_auth)
    _preflight_evaluation(config, executor, executor_factory, check_auth=check_auth)
    selected = {task.task_id: task for task in _tasks_from_state(root, manifest, state, config.benchmark)}
    saved_skills = manifest.get("skills", {})
    if not isinstance(saved_skills, Mapping):
        saved_skills = {}
    skill_paths: dict[str, Path | None] = {}
    for condition in config.conditions:
        if condition.intervention is None:
            skill_paths[condition.id] = None
        elif condition.intervention.path is not None:
            target = condition.intervention.path
            if not target.is_dir():
                raise ArtifactError(f"saved Skill path is missing: {target}")
            skill_paths[condition.id] = target
            if not saved_skills.get(condition.id):
                skill_path, metadata = _prepare_condition_skill(
                    condition, root, executor, executor_factory, check_auth=check_auth
                )
                skill_paths[condition.id] = skill_path
                saved_skills[condition.id] = metadata
        elif condition.intervention.build is None:
            if condition.intervention.prompt is None:
                raise ArtifactError(f"condition {condition.id} has no saved Skill intervention")
            skill_paths[condition.id] = None
            continue
        else:
            target = root / "skills" / task_directory_name(condition.id)
            saved = saved_skills.get(condition.id)
            skill_name = saved.get("name") if isinstance(saved, Mapping) else None
            if not isinstance(skill_name, str) or not skill_name:
                build_path = condition.intervention.build
                if build_path is None:
                    raise ArtifactError(f"condition {condition.id} has no saved Skill build configuration")
                skill_name = load_build_config(build_path).name
            target = target / skill_name
            if target.is_dir():
                skill_manifest_path = target / "skill_manifest.json"
                if not skill_manifest_path.is_file():
                    raise ArtifactError(
                        f"saved inline Skill condition {condition.id} has no creator manifest; "
                        "preserve the incomplete output and use a new run"
                    )
                skill_manifest = read_json(skill_manifest_path)
                if not isinstance(skill_manifest, Mapping):
                    raise ArtifactError(f"saved inline Skill creator manifest is invalid: {skill_manifest_path}")
                build_path = condition.intervention.build
                if build_path is None:
                    raise ArtifactError(f"condition {condition.id} has no saved Skill build configuration")
                frozen_build = load_build_config(build_path)
                # A creator may have completed its CLI call while the run
                # journal was not updated.  The helper verifies completed
                # output without a model call and resumes only incomplete
                # frozen creator attempts.
                resume_skill_build(
                    target,
                    _executor_for(frozen_build.runtime, executor, executor_factory),
                    check_auth=check_auth,
                )
                build_manifest = read_json(skill_manifest_path)
                if not isinstance(build_manifest, Mapping) or build_manifest.get("creator_status") != "completed":
                    raise ArtifactError(f"saved inline Skill creator did not complete: {skill_manifest_path}")
                skill_paths[condition.id] = target
                saved_skills[condition.id] = _built_skill_metadata(
                    target, root, frozen_build.config_path, condition.intervention.prompt
                )
                continue
            skill_path, metadata = _prepare_condition_skill(
                condition,
                root,
                executor,
                executor_factory,
                check_auth=check_auth,
            )
            skill_paths[condition.id] = skill_path
            saved_skills[condition.id] = metadata
    if saved_skills:
        manifest["skills"] = saved_skills
        write_json(root / "run_manifest.json", manifest)
        for record in state:
            if record.get("execution_status") != "completed":
                record["skill"] = saved_skills.get(record["condition_id"])
    was_evaluated = manifest.get("evaluation_status") not in {None, "not_started"}
    interrupted, changed = _execute_state(
        config,
        list(selected.values()),
        state,
        root,
        executor,
        executor_factory,
        skill_paths,
    )
    completed, failed, pending, status = _state_counts(state)
    manifest.update(
        {
            "execution_status": status,
            "completed_count": completed,
            "failed_count": failed,
            "pending_count": pending,
            "interrupted": interrupted,
        }
    )
    evaluation_dir: Path | None = None
    evaluation_status = str(manifest.get("evaluation_status", "not_started"))
    comparison_dir: Path | None = None
    existing_evaluation = manifest.get("evaluation_dir")
    existing_comparison = manifest.get("comparison_dir")
    if isinstance(existing_evaluation, str):
        evaluation_dir = root / existing_evaluation
    if isinstance(existing_comparison, str):
        comparison_dir = root / existing_comparison
    if changed and pending:
        # Existing scores describe the previous immutable execution snapshot.
        # Clear their manifest pointers until the resumed state is complete.
        evaluation_dir = None
        comparison_dir = None
        evaluation_status = "not_started"
    elif not pending and not interrupted and config.evaluation is not None:
        resumable_evaluation = (
            not changed
            and evaluation_dir is not None
            and (evaluation_dir / "evaluation_manifest.json").is_file()
            and evaluation_status not in {"completed", "not_started"}
        )
        if resumable_evaluation:
            assert evaluation_dir is not None
            evaluation_status, comparison_dir = _resume_auto_evaluation(
                config,
                root,
                evaluation_dir,
                executor,
                executor_factory,
                check_auth=check_auth,
            )
        elif changed or not was_evaluated:
            evaluation_dir, evaluation_status, comparison_dir = _auto_evaluate(
                config, root, executor, executor_factory, check_auth=check_auth
            )
    write_json(root / "run_manifest.json", manifest)
    manifest = read_json(root / "run_manifest.json")
    manifest.update(
        {
            "evaluation_status": evaluation_status,
            "evaluation_dir": str(evaluation_dir.relative_to(root)) if evaluation_dir else None,
            "comparison_dir": str(comparison_dir.relative_to(root)) if comparison_dir else None,
        }
    )
    write_json(root / "run_manifest.json", manifest)
    return RunSummary(
        root,
        str(manifest.get("run_id", "")),
        status,
        len(state),
        completed,
        failed,
        evaluation_dir,
        evaluation_status,
        comparison_dir,
        pending,
    )
