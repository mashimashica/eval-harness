# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Pure comparison: preserve evaluation strata and count generated samples once."""

from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping

from .artifacts import ensure_new_output, read_json, read_jsonl, write_json
from .errors import ArtifactError


def _evaluation_inputs(path: Path) -> list[Path]:
    if (path / "evaluation_manifest.json").is_file():
        return [path]
    if (path / "run_manifest.json").is_file():
        candidates = sorted(p for p in path.glob("evaluations/*") if (p / "evaluation_manifest.json").is_file())
        if candidates:
            return candidates
        raise ArtifactError(f"run has no saved evaluations: {path}")
    raise ArtifactError(f"not a run or evaluation directory: {path}")


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
    return row.get("evaluation_status") == "completed" and row.get("score_valid") is True


def _stats(rows: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
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
    return {
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
        "judge_cost_usd": _distribution(row.get("judge_cost_usd") for row in rows),
    }


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
            copy["score"] = (
                (0.5 if row.get("winner") == "tie" else float(winner == condition)) if _valid(row) else None
            )
        selected.append(copy)
    return selected


def _execution_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = sorted({key for row in rows for key in (row.get("usage") or {})})
    attempts = [attempt for row in rows for attempt in (row.get("attempt_history") or [row])]
    return {
        "execution_count": len(rows),
        "status_counts": dict(Counter(str(row.get("execution_status", "unknown")) for row in rows)),
        "elapsed_seconds": _distribution(row.get("elapsed_seconds") for row in rows),
        "usage": {key: _distribution((row.get("usage") or {}).get(key) for row in rows) for key in keys},
        "cost_usd": _distribution(row.get("cost_usd") for row in rows),
        "attempt_count": len(attempts),
        "all_attempts_elapsed_seconds": _distribution(row.get("elapsed_seconds") for row in attempts),
        "all_attempts_cost_usd": _distribution(row.get("cost_usd") for row in attempts),
        "all_attempts_usage": {
            key: _distribution((row.get("usage") or {}).get(key) for row in attempts) for key in keys
        },
    }


def _skill_creations(run_path: Path) -> list[dict[str, Any]]:
    """Show one-time creation evidence separately from repeated application usage."""
    paths = sorted(
        set(run_path.glob("skills/*/skill_manifest.json")) | set(run_path.glob("skills/*/*/skill_manifest.json"))
    )
    creations = []
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
                        "generated_sha256",
                        "creator_skills",
                        "creation_inputs",
                    )
                },
            }
        )
    return creations


def compare_evaluations(inputs: Iterable[str | Path], output_dir: str | Path) -> Path:
    """Read saved results only; duplicate inputs and rejudging add no generations."""
    evaluation_dirs = sorted({p for value in inputs for p in _evaluation_inputs(Path(value).expanduser().resolve())})
    if not evaluation_dirs:
        raise ArtifactError("no evaluations were supplied")
    evaluations: list[dict[str, Any]] = []
    conditions: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    all_ids: set[str] = set()
    seen_evaluations: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    source_runs: dict[str, dict[str, Any]] = {}
    condition_generations: dict[tuple[str, str], set[str]] = defaultdict(set)
    condition_evaluated: dict[tuple[str, str], set[str]] = defaultdict(set)
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
        run_path = Path(str(manifest.get("source_run_dir", "")))
        benchmark = str(manifest.get("benchmark", "unknown"))
        if run_id not in source_runs and (run_path / "run_manifest.json").is_file():
            run = read_json(run_path / "run_manifest.json")
            if run.get("run_id") != run_id:
                raise ArtifactError(f"source run identity mismatch: {run_path}")
            benchmark = str(run.get("benchmark", benchmark))
            executions = read_json(run_path / "run_state.json")
            if not isinstance(executions, list):
                raise ArtifactError(f"invalid run state: {run_path}")
            source_runs[run_id] = {
                "run_id": run_id,
                "benchmark": benchmark,
                "path": str(run_path),
                "config_sha256": run.get("config_sha256"),
                "config": run.get("config_snapshot"),
                "metrics": _execution_metrics(executions),
                "skill_creations": _skill_creations(run_path),
                "skill_sources": run.get("skills"),
                "conditions": {
                    str(condition): _execution_metrics(
                        [row for row in executions if row.get("condition_id") == condition]
                    )
                    for condition in sorted({row.get("condition_id") for row in executions})
                },
            }
        elif run_id in source_runs:
            benchmark = source_runs[run_id]["benchmark"]
        stats = _stats(rows, run_id)
        all_ids.update(stats["generation_ids"])
        evaluations.append(
            {
                "evaluation_id": evaluation_id,
                "source_run_id": run_id,
                "benchmark": benchmark,
                "method": manifest.get("method"),
                "config": manifest.get("config_snapshot"),
                "evaluation_status": manifest.get("evaluation_status"),
                "stats": stats,
                "path": str(path),
            }
        )
        for condition in sorted({c for row in rows for c in _condition_ids(row)}):
            selected = _condition_rows(rows, condition, run_id)
            condition_stats = _stats(selected, run_id)
            key = (benchmark, condition)
            condition_generations[key].update(condition_stats["generation_ids"])
            condition_evaluated[key].update(
                gid for row in selected if _valid(row) for gid in _generation_ids(row, run_id)
            )
            conditions[key].append(
                {
                    "evaluation_id": evaluation_id,
                    "source_run_id": run_id,
                    "method": manifest.get("method"),
                    "stats": condition_stats,
                    "by_task": {
                        task_id: _stats([row for row in selected if row["task_id"] == task_id], run_id)
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
    report = {
        "schema_version": 1,
        "report_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_count": len(evaluations),
        "generated_sample_count": len(all_ids),
        "evaluations": evaluations,
        "condition_results": results,
        "source_runs": list(source_runs.values()),
        "interpretation": (
            "Quality distributions stay separate per evaluation, method, condition and task. "
            "Pairwise condition scores are win credit (win 1, tie 0.5, loss 0) per presentation. "
            "Repeated judgments and human raters add no generated samples. Unknown measurements are null."
        ),
    }
    report_dir = ensure_new_output(output_dir)
    write_json(report_dir / "comparison.json", report)
    write_json(report_dir / "report.json", report)
    return report_dir
