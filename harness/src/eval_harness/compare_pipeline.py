# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Pure comparison: preserve evaluation strata and count generated samples once."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping, Sequence

from .artifacts import (
    ensure_new_output,
    file_manifest,
    manifest_hash,
    read_json,
    read_jsonl,
    write_json,
)
from .errors import ArtifactError
from .pairwise_statistics import compute_pairwise_statistics


def _evaluation_inputs(path: Path, _visited: set[Path] | None = None) -> list[Path]:
    """Resolve one evaluation, run, or recursively recorded cohort root.

    Cohort manifests may point directly at child evaluation directories or at
    ordinary child run directories whose evaluations are nested below them.
    The resolver keeps the comparison layer read-only and rejects malformed
    relative paths before any child results are loaded.
    """

    visited = _visited if _visited is not None else set()
    path = path.resolve()
    if path in visited:
        raise ArtifactError(f"cohort comparison source repeats or cycles: {path}")
    visited.add(path)
    if (path / "evaluation_manifest.json").is_file():
        evaluation_manifest = read_json(path / "evaluation_manifest.json")
        if isinstance(evaluation_manifest, Mapping) and evaluation_manifest.get("kind") == "creation_cohorts":
            return _cohort_evaluation_inputs(path, evaluation_manifest, visited)
        return [path]
    if (path / "run_manifest.json").is_file():
        run_manifest = read_json(path / "run_manifest.json")
        if isinstance(run_manifest, Mapping) and run_manifest.get("kind") == "creation_cohorts":
            return _cohort_evaluation_inputs(path, run_manifest, visited)
        candidates = sorted(p for p in path.glob("evaluations/*") if (p / "evaluation_manifest.json").is_file())
        if candidates:
            return candidates
        raise ArtifactError(f"run has no saved evaluations: {path}")
    raise ArtifactError(f"not a run or evaluation directory: {path}")


def _cohort_evaluation_inputs(path: Path, manifest: Mapping[str, Any], visited: set[Path]) -> list[Path]:
    """Expand children recorded by either a cohort run or evaluation manifest."""

    cohorts = manifest.get("cohorts")
    if not isinstance(cohorts, list) or not cohorts:
        raise ArtifactError(f"creation cohort has no comparison children: {path}")
    children: list[Path] = []
    for cohort in cohorts:
        if not isinstance(cohort, Mapping):
            raise ArtifactError(f"creation cohort child is invalid: {path}")
        value = cohort.get("evaluation_dir", cohort.get("run_dir"))
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ArtifactError(f"creation cohort child path must be relative: {path}")
        child = (path / value).resolve()
        if child == path or not child.is_relative_to(path) or child in children:
            raise ArtifactError(f"creation cohort child path escapes or repeats its parent: {path}")
        children.append(child)
    resolved: list[Path] = []
    for child in children:
        resolved.extend(_evaluation_inputs(child, visited))
    if not resolved:
        raise ArtifactError(f"creation cohort has no saved evaluations: {path}")
    return resolved


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _distribution(values: Iterable[Any]) -> dict[str, Any]:
    observations = list(values)
    measured = [value for item in observations if (value := _number(item)) is not None]
    return {
        "observations": observations,
        "measured_count": len(measured),
        "missing_count": len(observations) - len(measured),
        "mean": mean(measured) if measured else None,
        "population_stddev": pstdev(measured) if measured else None,
        "min": min(measured) if measured else None,
        "max": max(measured) if measured else None,
        # A partial counter must not look like a complete total.
        "total": sum(measured) if measured and len(measured) == len(observations) else None,
    }


def _usage_metrics(rows: Iterable[Mapping[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    """Summarize every observed usage field while preserving missing values."""

    observations = list(rows)
    keys: set[str] = set()
    for row in observations:
        usage = row.get(field)
        if isinstance(usage, Mapping):
            keys.update(key for key in usage if isinstance(key, str))
    return {
        key: _distribution(
            (usage.get(key) if isinstance(usage := row.get(field), Mapping) else None) for row in observations
        )
        for key in keys
    }


def _reported_cost(row: Mapping[str, Any], *, direct_key: str = "reported_cost_usd", usage_key: str = "usage") -> Any:
    """Read a CLI estimate separately from the actual incremental cost field."""

    direct = row.get(direct_key)
    if direct is not None:
        return direct
    usage = row.get(usage_key)
    return usage.get("reported_cost_usd") if isinstance(usage, Mapping) else None


def _verified_source_root(evaluation_dir: Path, evaluation_manifest: Mapping[str, Any]) -> tuple[Path, str]:
    """Prefer the evaluation's immutable source snapshot over its old absolute path."""

    snapshot = evaluation_dir / "source_snapshot"
    snapshot_marker = evaluation_manifest.get("source_snapshot_dir")
    expected_hash = evaluation_manifest.get("source_snapshot_sha256")
    snapshot_manifest_path = evaluation_dir / "source_snapshot_manifest.json"
    has_snapshot_marker = snapshot_marker is not None or expected_hash is not None
    if has_snapshot_marker:
        if not isinstance(snapshot_marker, str) or not snapshot_marker:
            raise ArtifactError(f"saved source snapshot marker is invalid: {evaluation_dir}")
        if not isinstance(expected_hash, str) or not expected_hash:
            raise ArtifactError(f"saved source snapshot hash is missing: {evaluation_dir}")
        if not snapshot.is_dir() or not snapshot_manifest_path.is_file():
            raise ArtifactError(f"saved source snapshot is missing: {evaluation_dir}")
        saved_entries = read_json(snapshot_manifest_path)
        if not isinstance(saved_entries, list) or any(not isinstance(entry, Mapping) for entry in saved_entries):
            raise ArtifactError(f"saved source snapshot manifest is invalid: {evaluation_dir}")
        entries = file_manifest(snapshot)
        if entries != [dict(entry) for entry in saved_entries] or manifest_hash(entries) != expected_hash:
            raise ArtifactError(f"saved source snapshot changed: {evaluation_dir}")
        return snapshot, "evaluation_snapshot"
    # A complete snapshot is usable even if an older manifest omitted the
    # marker; an unverified directory must never replace the legacy source.
    if snapshot.is_dir() and snapshot_manifest_path.is_file():
        saved_entries = read_json(snapshot_manifest_path)
        if isinstance(saved_entries, list) and all(isinstance(entry, Mapping) for entry in saved_entries):
            entries = file_manifest(snapshot)
            if entries == [dict(entry) for entry in saved_entries]:
                return snapshot, "evaluation_snapshot"
    source_value = evaluation_manifest.get("source_run_dir")
    if not isinstance(source_value, str) or not source_value:
        raise ArtifactError(f"evaluation has no source run or verified source snapshot: {evaluation_dir}")
    return Path(source_value).expanduser().resolve(), "original_source"


def _generation_ids(row: Mapping[str, Any], run_id: str) -> list[str]:
    ids = row.get("generation_ids", [row.get("generation_id")])
    if not isinstance(ids, list) or not ids or any(not isinstance(v, str) or not v for v in ids):
        raise ArtifactError("judgment has no valid generation identity")
    return [value if value.startswith(run_id + ":") else run_id + ":" + value for value in ids]


def _condition_ids(row: Mapping[str, Any]) -> list[str]:
    values = row.get("condition_ids", [row.get("condition_id")])
    if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v for v in values):
        raise ArtifactError("judgment has no valid condition identity")
    return values


def _valid(row: Mapping[str, Any]) -> bool:
    return (
        row.get("evaluation_status") == "completed"
        and row.get("score_valid") is True
        and row.get("winner") != "unjudgeable"
    )


def _criteria_results(rows: Sequence[Mapping[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """Preserve criterion-level evidence alongside scalar score summaries."""

    results: list[dict[str, Any]] = []
    for row in rows:
        values = row.get("criteria_results")
        if not isinstance(values, list):
            continue
        results.append(
            {
                "generation_ids": _generation_ids(row, run_id),
                "task_id": row.get("task_id"),
                "repeat": row.get("repeat"),
                "criteria_results": [dict(item) if isinstance(item, Mapping) else item for item in values],
            }
        )
    return results


def _stats(
    rows: list[dict[str, Any]],
    run_id: str,
    *,
    include_judge_protocols: bool = False,
) -> dict[str, Any]:
    planned_ids = {gid for row in rows for gid in _generation_ids(row, run_id)}
    generation_ids = sorted(
        {
            gid
            for row in rows
            if row.get("execution_status") not in {"pending", "not_started", "not_run"}
            for gid in _generation_ids(row, run_id)
        }
    )
    valid_rows = [row for row in rows if _valid(row)]
    scores = [value for row in valid_rows if (value := _number(row.get("score"))) is not None]
    quality = _distribution(scores)
    criteria = sorted({key for row in rows for key in (row.get("ratings") or {})})
    result: dict[str, Any] = {
        "generation_ids": generation_ids,
        "scheduled_sample_count": len(planned_ids),
        "generated_sample_count": len(generation_ids),
        "unique_generated_sample_count": len(generation_ids),
        "judgment_count": len(rows),
        "valid_judgment_count": len(valid_rows),
        "evaluated_sample_count": len({gid for row in valid_rows for gid in _generation_ids(row, run_id)}),
        "evaluation_status_counts": dict(Counter(str(row.get("evaluation_status", "unknown")) for row in rows)),
        "failed_or_missing_count": len(rows) - len(valid_rows),
        "task_ids": sorted({str(row["task_id"]) for row in rows}),
        "scores": scores,
        "mean_score": quality["mean"],
        "population_stddev": quality["population_stddev"],
        "min_score": quality["min"],
        "max_score": quality["max"],
        "human_test_data_count": sum(row.get("is_test_data") is True for row in rows),
        "ratings": {key: _distribution((row.get("ratings") or {}).get(key) for row in valid_rows) for key in criteria},
        "comments": [
            {key: row.get(key) for key in ("generation_id", "rater_id", "comment", "is_test_data")}
            for row in rows
            if row.get("comment") is not None
        ],
        "judge_elapsed_seconds": _distribution(row.get("judge_elapsed_seconds") for row in rows),
        "judge_usage": _usage_metrics(rows, "judge_usage"),
        "judge_cost_usd": _distribution(row.get("judge_cost_usd") for row in rows),
        "judge_reported_cost_usd": _distribution(
            _reported_cost(row, direct_key="judge_reported_cost_usd", usage_key="judge_usage") for row in rows
        ),
        "criteria_results": _criteria_results(rows, run_id),
    }
    if include_judge_protocols:
        protocols = _judge_protocol_rows(rows)
        result["by_judge_protocol"] = [
            {
                **descriptor,
                "stats": _stats(protocol_rows, run_id),
            }
            for descriptor, protocol_rows in protocols
        ]
        result["judge_protocol_count"] = len(protocols)
        if len(protocols) > 1:
            result["aggregation"] = "diagnostic_pooled_across_judge_protocols"
    return result


def _condition_rows(rows: list[dict[str, Any]], condition: str, run_id: str) -> list[dict[str, Any]]:
    selected = []
    for row in rows:
        conditions = _condition_ids(row)
        if condition not in conditions:
            continue
        copy = dict(row)
        if len(conditions) > 1:
            ids = _generation_ids(row, run_id)
            if len(ids) != len(conditions):
                raise ArtifactError("pairwise condition and generation identities do not align")
            copy["generation_ids"] = [ids[conditions.index(condition)]]
            winner = row.get("winner_condition_id")
            if not _valid(row) or row.get("winner") == "unjudgeable":
                copy["score"] = None
            elif row.get("winner") == "tie":
                copy["score"] = 0.5
            elif isinstance(winner, str) and winner in conditions:
                copy["score"] = float(winner == condition)
            else:
                # Legacy pair rows may omit winner_condition_id. Derive it
                # from the saved presentation labels when possible.
                presented = row.get("presented_conditions")
                if (
                    isinstance(presented, list)
                    and len(presented) == 2
                    and row.get("winner") in {"A", "B"}
                    and all(isinstance(value, str) for value in presented)
                ):
                    winner_position = presented.index(row["winner"])
                    copy["score"] = float(conditions[winner_position] == condition)
                else:
                    copy["score"] = None
        selected.append(copy)
    return selected


def _execution_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = [attempt for row in rows for attempt in (row.get("attempt_history") or [row])]
    return {
        "execution_count": len(rows),
        "status_counts": dict(Counter(str(row.get("execution_status", "unknown")) for row in rows)),
        "elapsed_seconds": _distribution(row.get("elapsed_seconds") for row in rows),
        "usage": _usage_metrics(rows, "usage"),
        "cost_usd": _distribution(row.get("cost_usd") for row in rows),
        "reported_cost_usd": _distribution(_reported_cost(row) for row in rows),
        "attempt_count": len(attempts),
        "all_attempts_elapsed_seconds": _distribution(row.get("elapsed_seconds") for row in attempts),
        "all_attempts_cost_usd": _distribution(row.get("cost_usd") for row in attempts),
        "all_attempts_reported_cost_usd": _distribution(_reported_cost(row) for row in attempts),
        "all_attempts_usage": _usage_metrics(attempts, "usage"),
    }


def _creation_descriptor(row: Mapping[str, Any]) -> dict[str, Any]:
    """Identify the Skill creation behind an execution without pooling cohorts."""

    skill = row.get("skill")
    if not isinstance(skill, Mapping):
        parent_id = row.get("cohort_parent_id")
        creation_repeat = row.get("creation_repeat")
        creation_key = (
            f"cohort:{parent_id}:{creation_repeat}"
            if isinstance(parent_id, str) and isinstance(creation_repeat, int)
            else "none"
        )
        return {
            "creation_key": creation_key,
            "creation_id": None,
            "content_sha256": None,
            "creation_in_this_run": None,
            "creation_repeat": creation_repeat,
            "cohort_parent_id": parent_id,
        }
    creation_id = skill.get("creation_id")
    content_sha256 = skill.get("generated_sha256", skill.get("sha256"))
    parent_id = row.get("cohort_parent_id", skill.get("cohort_parent_id"))
    creation_repeat = row.get("creation_repeat", skill.get("creation_repeat"))
    if isinstance(creation_id, str) and creation_id:
        creation_key = f"creation:{creation_id}"
    elif isinstance(content_sha256, str) and content_sha256:
        creation_key = f"content:{content_sha256}"
    elif row.get("creation_in_this_run") is False or skill.get("creation_in_this_run") is False:
        creation_key = "fixed:unknown"
    elif isinstance(parent_id, str) and isinstance(creation_repeat, int):
        creation_key = f"cohort:{parent_id}:{creation_repeat}"
    else:
        creation_key = "unknown"
    return {
        "creation_key": creation_key,
        "creation_id": creation_id,
        "content_sha256": content_sha256,
        "creation_in_this_run": skill.get("creation_in_this_run", row.get("creation_in_this_run")),
        "creation_repeat": creation_repeat,
        "cohort_parent_id": parent_id,
    }


def _creation_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize execution repeats separately for each Skill creation cohort."""

    grouped: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    descriptors: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        condition = str(row.get("condition_id", "unknown"))
        descriptor = _creation_descriptor(row)
        key = (condition, str(descriptor["creation_key"]))
        grouped[key].append(row)
        descriptors.setdefault(key, descriptor)
    result: list[dict[str, Any]] = []
    for (condition, creation_key), members in sorted(grouped.items()):
        descriptor = descriptors[(condition, creation_key)]
        result.append(
            {
                "condition_id": condition,
                **descriptor,
                "execution_count": len(members),
                "execution_repeats": _distribution(row.get("repeat") for row in members),
                "execution_metrics": _execution_metrics(members),
                "aggregation": "one_creation_identity_within_condition",
            }
        )
    return result


def _skill_creations(run_path: Path, run_manifest: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Show one-time creation evidence separately from repeated application usage.

    Evaluation source snapshots copy the run manifest and execution journals,
    but intentionally omit the mutable ``skills/`` tree.  In that case the
    frozen run manifest's ``skills`` metadata is the authoritative source for
    creator duration, usage, and cost evidence.
    """

    if run_manifest is None and (run_path / "run_manifest.json").is_file():
        candidate = read_json(run_path / "run_manifest.json")
        run_manifest = candidate if isinstance(candidate, Mapping) else None
    paths = sorted(
        set(run_path.glob("skills/*/skill_manifest.json")) | set(run_path.glob("skills/*/*/skill_manifest.json"))
    )
    creations: list[dict[str, Any]] = []
    for path in paths:
        manifest = read_json(path)
        creations.append(
            {
                "skill_path": str(path.parent.relative_to(run_path)),
                **{
                    key: manifest.get(key)
                    for key in (
                        "creation_id",
                        "name",
                        "runtime",
                        "creator_status",
                        "creator_elapsed_seconds",
                        "creator_usage",
                        "creator_cost_usd",
                        "creator_reported_cost_usd",
                        "generated_sha256",
                        "creator_skills",
                        "creation_inputs",
                    )
                },
            }
        )
    if isinstance(run_manifest, Mapping):
        saved_skills = run_manifest.get("skills")
        if isinstance(saved_skills, Mapping):
            for condition_id, skill in sorted(saved_skills.items(), key=lambda item: str(item[0])):
                if not isinstance(skill, Mapping):
                    continue
                creations.append(
                    {
                        "condition_id": str(condition_id),
                        "skill_path": skill.get("skill_path", f"skills/{condition_id}"),
                        "creation_id": skill.get("creation_id"),
                        "name": skill.get("name"),
                        "runtime": skill.get("creator_runtime", skill.get("runtime")),
                        "creator_status": skill.get("creator_status"),
                        "creator_elapsed_seconds": skill.get("creator_elapsed_seconds"),
                        "creator_usage": skill.get("creator_usage"),
                        "creator_cost_usd": skill.get("creator_cost_usd"),
                        "creator_reported_cost_usd": skill.get("creator_reported_cost_usd"),
                        "generated_sha256": skill.get("generated_sha256", skill.get("sha256")),
                        "creator_skills": skill.get("creator_skills"),
                        "creation_inputs": skill.get("creation_inputs"),
                    }
                )

    # A run can expose the same creation once per condition or again through
    # a frozen metadata copy.  Keep the first complete record and retain all
    # condition/path provenance on that identity.
    unique: dict[str, dict[str, Any]] = {}
    for record in creations:
        creation_id = record.get("creation_id")
        content_hash = record.get("generated_sha256", record.get("sha256"))
        identity = (
            f"creation:{creation_id}"
            if isinstance(creation_id, str) and creation_id
            else f"content:{content_hash}"
            if isinstance(content_hash, str) and content_hash
            else f"path:{record.get('skill_path', len(unique))}"
        )
        existing = unique.get(identity)
        if existing is None:
            unique[identity] = dict(record, creation_key=identity, source_conditions=[])
            existing = unique[identity]
        condition_id = record.get("condition_id")
        if isinstance(condition_id, str) and condition_id not in existing["source_conditions"]:
            existing["source_conditions"].append(condition_id)
    return list(unique.values())


def _source_generation_id(run_id: str, execution: Mapping[str, Any]) -> str:
    supplied = execution.get("generation_id")
    if isinstance(supplied, str) and supplied:
        return supplied if supplied.startswith(run_id + ":") else f"{run_id}:{supplied}"
    condition = execution.get("condition_id")
    task_id = execution.get("task_id")
    repeat = execution.get("repeat")
    if not isinstance(condition, str) or not isinstance(task_id, str) or not isinstance(repeat, int):
        raise ArtifactError("source execution has no valid generation identity")
    return f"{run_id}:{condition}:{task_id}:{repeat}"


def _stage_observation_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    elapsed_key: str,
    usage_key: str,
    cost_key: str,
    reported_cost_key: str,
) -> dict[str, Any]:
    return {
        "observation_count": len(rows),
        "elapsed_seconds": _distribution(row.get(elapsed_key) for row in rows),
        "usage": _usage_metrics(rows, usage_key),
        "cost_usd": _distribution(row.get(cost_key) for row in rows),
        "reported_cost_usd": _distribution(
            _reported_cost(row, direct_key=reported_cost_key, usage_key=usage_key) for row in rows
        ),
    }


def _evaluation_attempts(root: Path, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Read archived failed calls as resource measurements, never as new grades."""
    attempts: list[dict[str, Any]] = []
    for row in rows:
        count = row.get("evaluation_attempt_count", 1)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ArtifactError("invalid evaluation attempt count")
        if count > 1:
            value = row.get("judge_events_path") or row.get("judgment_path")
            if not isinstance(value, str) or Path(value).is_absolute():
                raise ArtifactError("resumed judgment has no saved attempt path")
            directory = (root / value).resolve().parent
            if not directory.is_relative_to((root / "judgments").resolve()):
                raise ArtifactError("judgment attempt path escapes the evaluation")
            for index in range(count - 1):
                prior = read_json(directory / "attempts" / str(index) / "judgment.json")
                if not isinstance(prior, Mapping) or prior.get("judgment_id") != row.get("judgment_id"):
                    raise ArtifactError("archived judgment attempt identity changed")
                attempts.append(dict(prior))
        attempts.append(dict(row))
    return attempts


def _stage_metrics(
    source_executions: Mapping[str, Sequence[Mapping[str, Any]]],
    source_creations: Mapping[str, Sequence[Mapping[str, Any]]],
    evaluation_rows: Sequence[tuple[str, Sequence[Mapping[str, Any]]]],
) -> dict[str, Any]:
    """Aggregate lifecycle stages without treating repeats or rejudgments as new generations."""

    application_by_generation: dict[str, Mapping[str, Any]] = {}
    for run_id, executions in source_executions.items():
        for index, execution in enumerate(executions):
            try:
                generation_id = _source_generation_id(run_id, execution)
            except ArtifactError:
                # Older diagnostic-only run records may omit task/repeat
                # identity. Preserve their stage measurement without
                # pretending two such rows are the same generation.
                generation_id = f"{run_id}:unidentified:{index}"
            application_by_generation.setdefault(generation_id, execution)
    application_rows = list(application_by_generation.values())

    creation_by_identity: dict[str, dict[str, Any]] = {}
    for run_id, creations in source_creations.items():
        for index, creation in enumerate(creations):
            creation_key = creation.get("creation_key")
            if not isinstance(creation_key, str) or not creation_key:
                creation_id = creation.get("creation_id")
                content_hash = creation.get("generated_sha256", creation.get("sha256"))
                creation_key = (
                    f"creation:{creation_id}"
                    if isinstance(creation_id, str) and creation_id
                    else f"content:{content_hash}"
                    if isinstance(content_hash, str) and content_hash
                    else f"unidentified:{run_id}:{index}"
                )
            current = creation_by_identity.get(creation_key)
            if current is None:
                current = {
                    **dict(creation),
                    "creation_key": creation_key,
                    "source_run_ids": [],
                    "source_conditions": [],
                }
                creation_by_identity[creation_key] = current
            if run_id not in current["source_run_ids"]:
                current["source_run_ids"].append(run_id)
            for condition_id in creation.get("source_conditions", []):
                if isinstance(condition_id, str) and condition_id not in current["source_conditions"]:
                    current["source_conditions"].append(condition_id)
    creation_rows = list(creation_by_identity.values())

    judgment_by_identity: dict[tuple[str, str], Mapping[str, Any]] = {}
    for evaluation_id, rows in evaluation_rows:
        for index, row in enumerate(rows):
            judgment_id = row.get("judgment_id", row.get("rating_id"))
            if not isinstance(judgment_id, str) or not judgment_id:
                judgment_id = f"row-{index}"
            judgment_by_identity.setdefault((evaluation_id, judgment_id), row)
    evaluation_observations = list(judgment_by_identity.values())

    return {
        "creation": {
            "identity_field": "creation_id (content hash fallback)",
            "unique_count": len(creation_rows),
            "unique_creation_count": len(creation_rows),
            "creation_ids": sorted(
                {
                    str(row["creation_id"])
                    for row in creation_rows
                    if isinstance(row.get("creation_id"), str) and row["creation_id"]
                }
            ),
            "identities": creation_rows,
            **_stage_observation_metrics(
                creation_rows,
                elapsed_key="creator_elapsed_seconds",
                usage_key="creator_usage",
                cost_key="creator_cost_usd",
                reported_cost_key="creator_reported_cost_usd",
            ),
            "scope": "one observation per unique creation identity across supplied source runs",
        },
        "application": {
            "identity_field": "generation_id",
            "unique_count": len(application_rows),
            "unique_generation_count": len(application_rows),
            "generation_ids": sorted(application_by_generation),
            **_stage_observation_metrics(
                application_rows,
                elapsed_key="elapsed_seconds",
                usage_key="usage",
                cost_key="cost_usd",
                reported_cost_key="reported_cost_usd",
            ),
            "scope": "one observation per unique saved generation across supplied evaluations",
        },
        "evaluation": {
            "identity_field": "evaluation_id + judgment_id",
            "unique_count": len(evaluation_observations),
            "judgment_count": len(evaluation_observations),
            **_stage_observation_metrics(
                evaluation_observations,
                elapsed_key="judge_elapsed_seconds",
                usage_key="judge_usage",
                cost_key="judge_cost_usd",
                reported_cost_key="judge_reported_cost_usd",
            ),
            "scope": "latest attempt per logical judgment; order presentations remain separate; all_attempts includes retries",
        },
    }


def _judge_protocol_descriptor(row: Mapping[str, Any]) -> dict[str, Any] | None:
    judge_id = row.get("judge_id", "legacy")
    if not isinstance(judge_id, str) or not judge_id:
        return None
    runtime = row.get("judge_runtime_identity", row.get("judge_runtime"))
    runtime_hash = row.get("judge_runtime_sha256")
    criteria_digest = row.get("criteria_sha256")
    if not isinstance(runtime_hash, str) or not runtime_hash:
        runtime_hash = None
    if not isinstance(criteria_digest, str) or not criteria_digest:
        criteria_digest = None
    if runtime_hash is None and isinstance(runtime, Mapping):
        encoded = json.dumps(runtime, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        runtime_hash = hashlib.sha256(encoded).hexdigest()
    identity = (
        f"{judge_id}|runtime={runtime_hash or 'none'}|criteria={criteria_digest or 'none'}"
        if runtime_hash is not None or criteria_digest is not None or runtime is not None
        else judge_id
    )
    return {
        "judge_id": judge_id,
        "judge_identity": identity,
        "judge_runtime": runtime,
        "judge_runtime_sha256": runtime_hash,
        "criteria_sha256": criteria_digest,
    }


def _judge_protocol_rows(rows: Sequence[Mapping[str, Any]]) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Group saved rows by the complete judge runtime and criteria identity."""

    protocols: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    for row in rows:
        descriptor = _judge_protocol_descriptor(row)
        if descriptor is None:
            continue
        identity = descriptor["judge_identity"]
        if identity not in protocols:
            protocols[identity] = (descriptor, [])
        protocols[identity][1].append(dict(row))
    return [protocols[key] for key in sorted(protocols)]


def _judge_protocols(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return distinct saved judge identities without collapsing their protocols."""

    return [descriptor for descriptor, _ in _judge_protocol_rows(rows)]


def compare_evaluations(
    inputs: Iterable[str | Path],
    output_dir: str | Path,
    *,
    bootstrap_resamples: int = 1_000,
    seed: int = 0,
) -> Path:
    """Read saved results only; duplicate inputs and rejudging add no generations.

    Pairwise confidence intervals are task-cluster estimates calculated
    independently for each saved judge protocol.  The older condition score
    distributions remain useful diagnostics, while ``pairwise_statistics``
    is the reliable paired comparison and never pools incompatible judges.
    """
    evaluation_dirs = sorted({p for value in inputs for p in _evaluation_inputs(Path(value).expanduser().resolve())})
    if not evaluation_dirs:
        raise ArtifactError("no evaluations were supplied")
    evaluations: list[dict[str, Any]] = []
    conditions: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    all_ids: set[str] = set()
    seen_evaluations: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    source_runs: dict[str, dict[str, Any]] = {}
    source_executions: dict[str, list[dict[str, Any]]] = {}
    source_creations: dict[str, list[dict[str, Any]]] = {}
    evaluation_metric_rows: list[tuple[str, list[dict[str, Any]]]] = []
    all_judge_attempts: list[dict[str, Any]] = []
    condition_generations: dict[tuple[str, str], set[str]] = defaultdict(set)
    condition_evaluated: dict[tuple[str, str], set[str]] = defaultdict(set)
    pairwise_reports: list[dict[str, Any]] = []
    for path in evaluation_dirs:
        manifest = read_json(path / "evaluation_manifest.json")
        if not isinstance(manifest, dict):
            raise ArtifactError(f"invalid evaluation manifest: {path}")
        evaluation_id, run_id = manifest.get("evaluation_id"), manifest.get("source_run_id")
        if not isinstance(evaluation_id, str) or not isinstance(run_id, str):
            raise ArtifactError("evaluation and source run identities are required")
        rows = read_jsonl(path / "judgments.jsonl")
        if evaluation_id in seen_evaluations:
            if seen_evaluations[evaluation_id] != (manifest, rows):
                raise ArtifactError(f"conflicting saved copies of evaluation {evaluation_id}")
            continue
        seen_evaluations[evaluation_id] = (manifest, rows)
        run_path, source_kind = _verified_source_root(path, manifest)
        benchmark = str(manifest.get("benchmark", "unknown"))
        evaluation_metric_rows.append((evaluation_id, rows))
        all_judge_attempts.extend(_evaluation_attempts(path, rows))
        needs_source = run_id not in source_runs or (
            source_kind == "evaluation_snapshot" and source_runs[run_id].get("source_kind") != source_kind
        )
        if needs_source and (run_path / "run_manifest.json").is_file():
            run = read_json(run_path / "run_manifest.json")
            if run.get("run_id") != run_id:
                raise ArtifactError(f"source run identity mismatch: {run_path}")
            benchmark = str(run.get("benchmark", benchmark))
            executions = read_json(run_path / "run_state.json")
            if not isinstance(executions, list):
                raise ArtifactError(f"invalid run state: {run_path}")
            if any(not isinstance(execution, Mapping) for execution in executions):
                raise ArtifactError(f"invalid run state records: {run_path}")
            normalized_executions = [dict(execution) for execution in executions]
            normalized_creations = _skill_creations(run_path, run)
            source_executions[run_id] = normalized_executions
            source_creations[run_id] = normalized_creations
            source_runs[run_id] = {
                "run_id": run_id,
                "benchmark": benchmark,
                "path": str(run_path),
                "source_kind": source_kind,
                "config_sha256": run.get("config_sha256"),
                "config": run.get("config_snapshot"),
                "metrics": _execution_metrics(normalized_executions),
                "metrics_scope": "all executions in this source run; pooled diagnostic",
                "skill_creations": normalized_creations,
                "skill_sources": run.get("skills"),
                "creation_groups": _creation_groups(normalized_executions),
                "conditions": {
                    str(condition): _execution_metrics(
                        [row for row in normalized_executions if row.get("condition_id") == condition]
                    )
                    for condition in sorted({str(row.get("condition_id")) for row in normalized_executions})
                },
            }
        elif run_id in source_runs:
            benchmark = source_runs[run_id]["benchmark"]
        method = manifest.get("method")
        include_judge_protocols = method in {"scalar", "pairwise"}
        stats = _stats(rows, run_id, include_judge_protocols=include_judge_protocols)
        pairwise_statistics = None
        judge_protocols: list[dict[str, Any]] = []
        if method == "pairwise":
            pairwise_statistics = compute_pairwise_statistics(
                rows,
                bootstrap_resamples=bootstrap_resamples,
                seed=seed,
            )
            judge_protocols = _judge_protocols(rows)
            pairwise_reports.append(
                {
                    "evaluation_id": evaluation_id,
                    "source_run_id": run_id,
                    "statistics": pairwise_statistics,
                    "judge_protocols": judge_protocols,
                }
            )
        all_ids.update(stats["generation_ids"])
        evaluation_record = {
            "evaluation_id": evaluation_id,
            "source_run_id": run_id,
            "benchmark": benchmark,
            "method": method,
            "config": manifest.get("config_snapshot"),
            "evaluation_status": manifest.get("evaluation_status"),
            "stats": stats,
            "path": str(path),
        }
        if pairwise_statistics is not None:
            evaluation_record["pairwise_statistics"] = pairwise_statistics
            evaluation_record["judge_protocols"] = judge_protocols
        evaluations.append(evaluation_record)
        for condition in sorted({c for row in rows for c in _condition_ids(row)}):
            selected = _condition_rows(rows, condition, run_id)
            condition_stats = _stats(selected, run_id, include_judge_protocols=include_judge_protocols)
            key = (benchmark, condition)
            condition_generations[key].update(condition_stats["generation_ids"])
            condition_evaluated[key].update(
                gid for row in selected if _valid(row) for gid in _generation_ids(row, run_id)
            )
            conditions[key].append(
                {
                    "evaluation_id": evaluation_id,
                    "source_run_id": run_id,
                    "method": method,
                    "stats": condition_stats,
                    "aggregation": "condition across creation identities; diagnostic",
                    "by_task": {
                        task_id: _stats(
                            [row for row in selected if row["task_id"] == task_id],
                            run_id,
                            include_judge_protocols=include_judge_protocols,
                        )
                        for task_id in sorted({str(row["task_id"]) for row in selected})
                    },
                }
            )
    results = [
        {
            "benchmark": benchmark,
            "condition_id": condition,
            "evaluations": entries,
            "evaluation_count": len(entries),
            "generated_sample_count": len(condition_generations[(benchmark, condition)]),
            "unique_generated_sample_count": len(condition_generations[(benchmark, condition)]),
            "evaluated_sample_count": len(condition_evaluated[(benchmark, condition)]),
            "scores": entries[0]["stats"]["scores"] if len(entries) == 1 else None,
        }
        for (benchmark, condition), entries in sorted(conditions.items())
    ]
    report: dict[str, Any] = {
        "schema_version": 1,
        "report_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_count": len(evaluations),
        "generated_sample_count": len(all_ids),
        "evaluations": evaluations,
        "condition_results": results,
        "source_runs": list(source_runs.values()),
        "stage_metrics": _stage_metrics(source_executions, source_creations, evaluation_metric_rows),
        "creation_groups": [
            {
                "source_run_id": source_run_id,
                "groups": source_run.get("creation_groups", []),
                "aggregation": "separate creation identities; execution repeats remain nested",
            }
            for source_run_id, source_run in sorted(source_runs.items())
        ],
        "pairwise_statistics": pairwise_reports,
        "bootstrap": {
            "method": "task_cluster_percentile_95",
            "cluster_unit": "task_id",
            "seed": seed,
            "resamples": bootstrap_resamples,
        },
        "interpretation": (
            "Quality distributions stay separate per evaluation, method, condition and task. "
            "Pairwise condition distributions are presentation diagnostics. "
            "Reliable paired statistics are task-cluster estimates reported separately for each judge protocol; "
            "win credit is 1, tie 0.5, and loss 0 after agreeing order presentations. "
            "Repeated judgments and human raters add no generated samples. Unknown measurements are null."
        ),
    }
    report["stage_metrics"]["evaluation"]["all_attempts"] = {
        "attempt_count": len(all_judge_attempts),
        **_stage_observation_metrics(
            all_judge_attempts,
            elapsed_key="judge_elapsed_seconds",
            usage_key="judge_usage",
            cost_key="judge_cost_usd",
            reported_cost_key="judge_reported_cost_usd",
        ),
        "scope": "all archived and latest grading attempts; failed calls consume resources but add no generations",
    }
    report_dir = ensure_new_output(output_dir)
    write_json(report_dir / "comparison.json", report)
    write_json(report_dir / "report.json", report)
    return report_dir
