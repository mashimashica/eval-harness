# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from eval_harness.artifacts import read_json, write_json, write_jsonl
from eval_harness.compare_pipeline import compare_evaluations
from eval_harness.errors import ArtifactError


def test_retry_resources_include_failed_call_without_adding_a_generation(tmp_path: Path) -> None:
    evaluation = tmp_path / "evaluation"
    write_json(
        evaluation / "evaluation_manifest.json",
        {
            "evaluation_id": "eval",
            "source_run_id": "run",
            "source_run_dir": str(tmp_path / "missing-source"),
            "benchmark": "gsm8k",
            "method": "scalar",
        },
    )
    row = {
        "judgment_id": "j",
        "generation_id": "run:N:t:0",
        "condition_id": "N",
        "task_id": "t",
        "repeat": 0,
        "execution_status": "completed",
        "evaluation_status": "completed",
        "score_valid": True,
        "score": 1,
        "evaluation_attempt_count": 2,
        "judge_events_path": "judgments/j/codex_events.jsonl",
        "judge_elapsed_seconds": 3,
        "judge_usage": {"output_tokens": 7, "reported_cost_usd": 0.2},
        "judge_cost_usd": None,
    }
    write_jsonl(evaluation / "judgments.jsonl", [row])
    archive = evaluation / "judgments/j/attempts/0/judgment.json"
    write_json(
        archive,
        {
            **row,
            "evaluation_status": "failed",
            "score_valid": False,
            "score": None,
            "judge_elapsed_seconds": 5,
            "judge_usage": {"output_tokens": 11, "reported_cost_usd": 0.3},
        },
    )
    result = read_json(compare_evaluations([evaluation, evaluation], tmp_path / "report") / "comparison.json")
    assert result["generated_sample_count"] == 1
    metric = result["stage_metrics"]["evaluation"]
    assert metric["judgment_count"] == 1
    assert metric["elapsed_seconds"]["total"] == 3
    all_attempts = metric["all_attempts"]
    assert all_attempts["attempt_count"] == 2
    assert all_attempts["elapsed_seconds"]["total"] == 8
    assert all_attempts["usage"]["output_tokens"]["total"] == 18
    assert all_attempts["reported_cost_usd"]["total"] == 0.5
    assert all_attempts["cost_usd"]["total"] is None
    write_json(archive, {"judgment_id": "another"})
    with pytest.raises(ArtifactError, match="identity changed"):
        compare_evaluations([evaluation], tmp_path / "bad")
