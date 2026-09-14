# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Generation identity, evaluation strata and missing-measurement regressions."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from eval_harness.artifacts import file_manifest, manifest_hash, read_json, write_json, write_jsonl
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


def test_stage_metrics_use_frozen_sources_and_separate_reused_creation_and_judgment_calls(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    evaluation_root = tmp_path / "evaluations"
    evaluation_root.mkdir()
    source_paths: list[Path] = []

    def make_evaluation(evaluation_id: str, run_id: str, elapsed: float, tokens: int, estimate: float) -> Path:
        source = source_root / run_id
        source.mkdir(parents=True, exist_ok=True)
        source_manifest = {
            "run_id": run_id,
            "benchmark": "gsm8k",
            "skills": {
                "A": {
                    "creation_id": "shared-creation",
                    "name": "arithmetic",
                    "creator_runtime": {"executor": "codex", "model": "gpt-5.6-sol"},
                    "creator_status": "completed",
                    "creator_elapsed_seconds": 7,
                    "creator_usage": {"input_tokens": 11, "output_tokens": 5, "reported_cost_usd": 0.07},
                    "creator_cost_usd": None,
                    "sha256": "shared-skill-content",
                    "skill_path": "skills/A/arithmetic",
                }
            },
        }
        execution = {
            "condition_id": "A",
            "task_id": "task",
            "repeat": 0,
            "execution_status": "completed",
            "elapsed_seconds": 3 if run_id == "run-1" else 4,
            "usage": {"input_tokens": 20, "output_tokens": 4},
            "cost_usd": None,
        }
        write_json(source / "run_manifest.json", source_manifest)
        write_json(source / "run_state.json", [execution])
        source_paths.append(source)

        path = evaluation_root / evaluation_id
        snapshot = path / "source_snapshot"
        write_json(snapshot / "run_manifest.json", source_manifest)
        write_json(snapshot / "run_state.json", [execution])
        entries = file_manifest(snapshot)
        write_json(path / "source_snapshot_manifest.json", entries)
        write_json(
            path / "evaluation_manifest.json",
            {
                "evaluation_id": evaluation_id,
                "source_run_id": run_id,
                "source_run_dir": str(source),
                "source_snapshot_dir": str(snapshot),
                "source_snapshot_sha256": manifest_hash(entries),
                "benchmark": "gsm8k",
                "method": "scalar",
                "evaluation_status": "completed",
            },
        )
        write_jsonl(
            path / "judgments.jsonl",
            [
                {
                    "judgment_id": f"{evaluation_id}:judgment",
                    "generation_id": f"{run_id}:A:task:0",
                    "condition_id": "A",
                    "task_id": "task",
                    "repeat": 0,
                    "score": 1,
                    "score_valid": True,
                    "evaluation_status": "completed",
                    "execution_status": "completed",
                    "judge_elapsed_seconds": elapsed,
                    "judge_usage": {
                        "input_tokens": tokens,
                        "output_tokens": 2,
                        "reported_cost_usd": estimate,
                    },
                    "judge_cost_usd": None,
                    "judge_reported_cost_usd": None,
                }
            ],
        )
        return path

    first = make_evaluation("e1", "run-1", 1, 10, 0.1)
    second = make_evaluation("e2", "run-1", 2, 20, 0.2)
    reused = make_evaluation("e3", "run-2", 3, 30, 0.3)
    for source in set(source_paths):
        shutil.rmtree(source)

    report = read_json(
        compare_evaluations([first, second, reused, first], tmp_path / "stage-report") / "comparison.json"
    )
    stages = report["stage_metrics"]
    assert stages["creation"]["unique_creation_count"] == 1
    assert stages["creation"]["creation_ids"] == ["shared-creation"]
    assert stages["creation"]["elapsed_seconds"]["observations"] == [7]
    assert stages["application"]["unique_generation_count"] == 2
    assert stages["application"]["generation_ids"] == ["run-1:A:task:0", "run-2:A:task:0"]
    assert stages["evaluation"]["judgment_count"] == 3
    assert stages["evaluation"]["elapsed_seconds"]["observations"] == [1, 2, 3]
    assert stages["evaluation"]["usage"]["input_tokens"]["observations"] == [10, 20, 30]
    assert stages["evaluation"]["cost_usd"]["missing_count"] == 3
    assert stages["evaluation"]["cost_usd"]["total"] is None
    assert stages["evaluation"]["reported_cost_usd"]["total"] == pytest.approx(0.6)
    assert all(source["source_kind"] == "evaluation_snapshot" for source in report["source_runs"])


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


def test_pairwise_statistics_are_saved_separately_from_diagnostic_scores(tmp_path: Path) -> None:
    first = {
        "generation_ids": ["N:task:0", "A:task:0"],
        "condition_ids": ["N", "A"],
        "task_id": "task",
        "repeat": 0,
        "presented_conditions": ["A", "B"],
        "winner": "A",
        "winner_condition_id": "N",
        "score_valid": True,
        "evaluation_status": "completed",
        "judge_id": "j1",
        "judge_runtime_sha256": "runtime-1",
        "criteria_sha256": "criteria-1",
    }
    second = {
        **first,
        "condition_ids": ["A", "N"],
        "generation_ids": ["A:task:0", "N:task:0"],
        "winner": "B",
    }
    path = evaluation(tmp_path, "pairwise", "r1", "pairwise", [first, second])
    report = read_json(compare_evaluations([path], tmp_path / "report") / "comparison.json")

    assert report["bootstrap"] == {
        "method": "task_cluster_percentile_95",
        "cluster_unit": "task_id",
        "seed": 0,
        "resamples": 1000,
    }
    statistics = report["evaluations"][0]["pairwise_statistics"]
    assert statistics["pair_results"][0]["judge_id"] == "j1"
    assert statistics["pair_results"][0]["distinct_task_count"] == 1
    assert report["pairwise_statistics"][0]["judge_protocols"][0]["criteria_sha256"] == "criteria-1"


def test_scalar_panel_stats_preserve_each_judge_score_and_criteria_items(tmp_path: Path) -> None:
    rows = []
    for judge_id, runtime_hash, criteria_hash, score, status in (
        ("j1", "runtime-1", "criteria-1", 0.25, "pass"),
        ("j2", "runtime-2", "criteria-2", 0.75, "unconfirmed"),
    ):
        rows.append(
            {
                "judgment_id": f"{judge_id}:r1:N:task:0",
                "generation_id": "N:task:0",
                "condition_id": "N",
                "task_id": "task",
                "repeat": 0,
                "score": score,
                "score_valid": True,
                "evaluation_status": "completed",
                "execution_status": "completed",
                "judge_id": judge_id,
                "judge_runtime_sha256": runtime_hash,
                "criteria_sha256": criteria_hash,
                "criteria_results": [
                    {"id": "quality", "status": status, "evidence": f"{judge_id} evidence", "reason": "saved"}
                ],
            }
        )
    path = evaluation(tmp_path, "scalar-panel", "r1", "scalar", rows)
    report = read_json(compare_evaluations([path], tmp_path / "report") / "comparison.json")
    stats = report["evaluations"][0]["stats"]
    assert stats["aggregation"] == "diagnostic_pooled_across_judge_protocols"
    protocols = stats["by_judge_protocol"]
    assert [item["judge_id"] for item in protocols] == ["j1", "j2"]
    assert [item["stats"]["scores"] for item in protocols] == [[0.25], [0.75]]
    assert protocols[0]["stats"]["criteria_results"][0]["criteria_results"][0]["status"] == "pass"
    assert protocols[1]["stats"]["criteria_results"][0]["criteria_results"][0]["status"] == "unconfirmed"


def test_unjudgeable_pair_is_not_a_condition_loss(tmp_path: Path) -> None:
    pair = {
        "generation_ids": ["N:task:0", "A:task:0"],
        "condition_ids": ["N", "A"],
        "task_id": "task",
        "repeat": 0,
        "score_valid": True,
        "evaluation_status": "completed",
        "execution_status": "completed",
        "winner": "unjudgeable",
        "winner_condition_id": None,
    }
    source = evaluation(tmp_path, "unjudgeable", "r1", "pairwise", [pair])
    report = read_json(compare_evaluations([source], tmp_path / "report") / "comparison.json")
    for condition in report["condition_results"]:
        stats = condition["evaluations"][0]["stats"]
        assert stats["scores"] == []
        assert stats["evaluated_sample_count"] == 0


def test_creation_groups_keep_cohort_identity_and_execution_repeats_nested(tmp_path: Path) -> None:
    run_dir = tmp_path / "r1"
    write_json(run_dir / "run_manifest.json", {"run_id": "r1", "benchmark": "gdpval"})
    write_json(
        run_dir / "run_state.json",
        [
            {
                "condition_id": "A",
                "task_id": "task",
                "repeat": 0,
                "execution_status": "completed",
                "elapsed_seconds": 1,
                "skill": {
                    "creation_id": "creation-1",
                    "generated_sha256": "content-1",
                    "creation_in_this_run": True,
                },
            },
            {
                "condition_id": "A",
                "task_id": "task",
                "repeat": 1,
                "execution_status": "completed",
                "elapsed_seconds": 2,
                "skill": {
                    "creation_id": "creation-1",
                    "generated_sha256": "content-1",
                    "creation_in_this_run": True,
                },
            },
            {
                "condition_id": "A",
                "task_id": "task",
                "repeat": 0,
                "execution_status": "completed",
                "elapsed_seconds": 3,
                "skill": {
                    "creation_id": "creation-2",
                    "generated_sha256": "content-2",
                    "creation_in_this_run": True,
                },
            },
            {
                "condition_id": "N",
                "task_id": "task",
                "repeat": 0,
                "creation_repeat": 0,
                "cohort_parent_id": "cohort-parent",
                "execution_status": "completed",
                "elapsed_seconds": 4,
            },
        ],
    )
    source = evaluation(tmp_path, "e1", "r1", "scalar", [scalar(1)])
    report = read_json(compare_evaluations([source], tmp_path / "report") / "comparison.json")
    groups = report["creation_groups"][0]["groups"]
    assert {group["creation_id"] for group in groups} == {None, "creation-1", "creation-2"}
    first = next(group for group in groups if group["creation_id"] == "creation-1")
    assert first["execution_count"] == 2
    assert first["execution_repeats"]["observations"] == [0, 1]
    no_skill = next(group for group in groups if group["condition_id"] == "N")
    assert no_skill["creation_key"] == "cohort:cohort-parent:0"


def test_compare_recursively_expands_creation_cohort_children(tmp_path: Path) -> None:
    cohort_root = tmp_path / "cohort"
    write_json(
        cohort_root / "run_manifest.json",
        {
            "kind": "creation_cohorts",
            "run_id": "cohort-root",
            "cohorts": [
                {"creation_repeat": 0, "run_dir": "cohorts/creation_0"},
                {"creation_repeat": 1, "run_dir": "cohorts/creation_1"},
            ],
        },
    )
    evaluation_dirs: list[Path] = []
    for index in range(2):
        child = cohort_root / f"cohorts/creation_{index}"
        run_id = f"child-{index}"
        write_json(child / "run_manifest.json", {"run_id": run_id, "benchmark": "gsm8k"})
        write_json(
            child / "run_state.json",
            [
                {
                    "condition_id": "N",
                    "task_id": "task",
                    "repeat": 0,
                    "execution_status": "completed",
                    "elapsed_seconds": 1,
                }
            ],
        )
        evaluation_dirs.append(
            evaluation(
                child / "evaluations",
                f"e{index}",
                run_id,
                "mechanical",
                [scalar(float(index))],
            )
        )
        # ``evaluation`` writes source_run_dir relative to its supplied base;
        # point it at the real child run for source metrics.
        manifest = read_json(evaluation_dirs[-1] / "evaluation_manifest.json")
        manifest["source_run_dir"] = str(child)
        write_json(evaluation_dirs[-1] / "evaluation_manifest.json", manifest)

    report = read_json(compare_evaluations([cohort_root], tmp_path / "report") / "comparison.json")
    assert report["input_count"] == 2
    assert {row["source_run_id"] for row in report["evaluations"]} == {"child-0", "child-1"}

    write_json(
        cohort_root / "evaluation_manifest.json",
        {
            "kind": "creation_cohorts",
            "cohorts": [
                {"creation_repeat": index, "evaluation_dir": str(path.relative_to(cohort_root))}
                for index, path in enumerate(evaluation_dirs)
            ],
        },
    )
    evaluation_report = read_json(
        compare_evaluations([cohort_root], tmp_path / "evaluation-report") / "comparison.json"
    )
    assert evaluation_report["input_count"] == 2


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
