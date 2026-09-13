# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Generation identity, evaluation strata and missing-measurement regressions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from eval_harness.artifacts import read_json, write_json, write_jsonl
from eval_harness.compare_pipeline import compare_evaluations
from eval_harness.errors import ArtifactError


def evaluation(root: Path, name: str, run_id: str, method: str, rows: list[dict[str, Any]]) -> Path:
    path = root / name
    write_json(
        path / "evaluation_manifest.json",
        {
            "evaluation_id": name,
            "source_run_id": run_id,
            "benchmark": "gsm8k",
            "method": method,
            "source_run_dir": str(root / run_id),
            "evaluation_status": "completed",
        },
    )
    write_jsonl(path / "judgments.jsonl", rows)
    return path


def scalar(score: float | None, repeat: int = 0) -> dict[str, Any]:
    return {
        "generation_id": f"N:task:{repeat}",
        "condition_id": "N",
        "task_id": "task",
        "repeat": repeat,
        "score": score,
        "score_valid": score is not None,
        "evaluation_status": "completed" if score is not None else "failed",
        "execution_status": "completed",
    }


def test_rejudging_does_not_inflate_samples_or_pool_methods(tmp_path: Path) -> None:
    first = evaluation(tmp_path, "e1", "r1", "scalar", [scalar(0.2), scalar(0.8, 1)])
    second = evaluation(tmp_path, "e2", "r1", "mechanical", [scalar(0), scalar(1, 1)])
    report = read_json(compare_evaluations([first, second, first], tmp_path / "report") / "comparison.json")
    assert report["input_count"] == 2
    assert report["generated_sample_count"] == 2
    condition = report["condition_results"][0]
    assert condition["generated_sample_count"] == 2
    assert condition["evaluated_sample_count"] == 2
    assert condition["scores"] is None
    assert [row["method"] for row in condition["evaluations"]] == ["scalar", "mechanical"]
    assert condition["evaluations"][0]["stats"]["mean_score"] == 0.5
    assert condition["evaluations"][0]["by_task"]["task"]["population_stddev"] == pytest.approx(0.3)


def test_different_runs_and_unknown_usage_remain_distinct(tmp_path: Path) -> None:
    first = evaluation(tmp_path, "e1", "r1", "scalar", [scalar(0.2), scalar(None, 1)])
    second = evaluation(tmp_path, "e2", "r2", "scalar", [scalar(1)])
    write_json(tmp_path / "r1/run_manifest.json", {"run_id": "r1", "benchmark": "gsm8k"})
    write_json(
        tmp_path / "r1/run_state.json",
        [
            {
                "condition_id": "N",
                "execution_status": "completed",
                "elapsed_seconds": 2,
                "usage": {"input_tokens": 10},
                "cost_usd": None,
            },
            {
                "condition_id": "N",
                "execution_status": "failed",
                "elapsed_seconds": 4,
                "usage": {"input_tokens": None},
                "cost_usd": None,
            },
        ],
    )
    report = read_json(compare_evaluations([first, second], tmp_path / "report") / "comparison.json")
    assert report["generated_sample_count"] == 3
    metrics = report["source_runs"][0]["metrics"]
    assert metrics["elapsed_seconds"]["mean"] == 3
    assert metrics["elapsed_seconds"]["population_stddev"] == 1
    assert metrics["usage"]["input_tokens"]["measured_count"] == 1
    assert metrics["usage"]["input_tokens"]["total"] is None
    assert metrics["cost_usd"]["mean"] is None
    assert report["evaluations"][0]["stats"]["scores"] == [0.2]


def test_pair_order_votes_and_human_raters_add_no_generations(tmp_path: Path) -> None:
    pair = {
        "generation_ids": ["N:task:0", "A:task:0"],
        "condition_ids": ["N", "A"],
        "task_id": "task",
        "repeat": 0,
        "score_valid": True,
        "evaluation_status": "completed",
        "winner": "B",
        "winner_condition_id": "A",
    }
    pairs = evaluation(tmp_path, "pairs", "r1", "pairwise", [pair, {**pair, "winner": "A"}])
    humans = evaluation(
        tmp_path,
        "humans",
        "r1",
        "human",
        [
            {
                **scalar(0.8),
                "rater_id": "fixture-1",
                "ratings": {"clarity": 4},
                "comment": "Fixture only",
                "is_test_data": True,
            },
            {**scalar(0.6), "rater_id": "fixture-2", "ratings": {"clarity": 3}, "is_test_data": True},
        ],
    )
    report = read_json(compare_evaluations([pairs, humans], tmp_path / "report") / "comparison.json")
    assert report["generated_sample_count"] == 2
    a = next(row for row in report["condition_results"] if row["condition_id"] == "A")
    assert a["generated_sample_count"] == 1
    assert a["scores"] == [1, 1]
    h = next(row for row in report["evaluations"] if row["method"] == "human")["stats"]
    assert h["generated_sample_count"] == 1
    assert h["judgment_count"] == 2
    assert h["ratings"]["clarity"]["mean"] == 3.5
    assert h["human_test_data_count"] == 2
    assert h["comments"][0]["comment"] == "Fixture only"


def test_pending_is_not_generated_and_conflicting_identity_is_rejected(tmp_path: Path) -> None:
    row = {**scalar(None), "execution_status": "pending", "evaluation_status": "not_evaluated"}
    source = evaluation(tmp_path, "e1", "r1", "scalar", [row])
    report = read_json(compare_evaluations([source], tmp_path / "report") / "comparison.json")
    assert report["generated_sample_count"] == 0
    assert report["evaluations"][0]["stats"]["scheduled_sample_count"] == 1
    duplicate = evaluation(tmp_path, "copy", "r1", "scalar", [scalar(1)])
    manifest = read_json(duplicate / "evaluation_manifest.json")
    manifest["evaluation_id"] = "e1"
    write_json(duplicate / "evaluation_manifest.json", manifest)
    with pytest.raises(ArtifactError, match="conflicting"):
        compare_evaluations([source, duplicate], tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
