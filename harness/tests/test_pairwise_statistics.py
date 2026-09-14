# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Behavioral tests for task-balanced saved pairwise statistics."""

from __future__ import annotations

from typing import Any

import pytest

from eval_harness.pairwise_statistics import compute_pairwise_statistics


def judgment(
    task: str,
    repeat: int,
    order: tuple[str, str],
    winner: str,
    *,
    judge: str | None = None,
    generation_suffix: str | None = None,
    winner_condition_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    suffix = generation_suffix or f"{task}-{repeat}"
    generation_by_condition = {"N": f"gen-N-{suffix}", "A": f"gen-A-{suffix}"}
    row: dict[str, Any] = {
        "task_id": task,
        "repeat": repeat,
        "condition_ids": list(order),
        "generation_ids": [generation_by_condition[order[0]], generation_by_condition[order[1]]],
        "presented_conditions": ["A", "B"],
        "winner": winner,
        "evaluation_status": "completed",
        "score_valid": True,
    }
    if judge is not None:
        row["judge_id"] = judge
    if winner_condition_id is not None:
        row["winner_condition_id"] = winner_condition_id
    row.update(extra)
    return row


def paired_task(task: str, winner: str, *, judge: str | None = None, repeat: int = 0) -> list[dict[str, Any]]:
    reverse_winner = {"A": "B", "B": "A", "tie": "tie", "unjudgeable": "unjudgeable"}[winner]
    return [
        judgment(task, repeat, ("N", "A"), winner, judge=judge),
        judgment(task, repeat, ("A", "N"), reverse_winner, judge=judge),
    ]


def test_duplicate_reevaluations_collapse_and_missing_or_conflicting_orders_are_visible() -> None:
    rows = paired_task("t1", "A")
    rows += [rows[0].copy(), rows[1].copy()]
    rows += [judgment("t2", 0, ("N", "A"), "A", judge="panel")]
    rows += [
        judgment("t3", 0, ("N", "A"), "A"),
        judgment("t3", 0, ("A", "N"), "A"),
    ]
    rows += [
        judgment("t4", 0, ("N", "A"), "A"),
        judgment("t4", 0, ("N", "A"), "B"),
        judgment("t4", 0, ("A", "N"), "B"),
    ]
    result = compute_pairwise_statistics(rows, bootstrap_resamples=20, seed=4)

    assert result["collapsed_pair_count"] == 4
    assert result["collapsed_duplicate_row_count"] == 3
    reports = {(row["task_id"], row["judge_reports"][0]["judge_id"]): row for row in result["pair_reports"]}
    assert reports[("t1", "legacy")]["status"] == "usable"
    assert reports[("t1", "legacy")]["judge_reports"][0]["orders"][0]["duplicate_count"] == 1
    assert reports[("t2", "panel")]["status"] == "unjudgeable"
    assert reports[("t2", "panel")]["judge_reports"][0]["status"] == "missing_order"
    assert reports[("t3", "legacy")]["judge_reports"][0]["status"] == "order_conflict"
    assert "reversed order presentations disagree" in reports[("t3", "legacy")]["judge_reports"][0]["reason"]
    assert reports[("t4", "legacy")]["judge_reports"][0]["status"] == "duplicate_conflict"


def test_same_generations_and_opposite_orders_are_matched_by_condition_winner() -> None:
    rows = [
        judgment("t1", 0, ("N", "A"), "A"),
        judgment("t1", 0, ("A", "N"), "B"),
    ]
    result = compute_pairwise_statistics(rows, bootstrap_resamples=20, seed=5)
    report = result["pair_reports"][0]
    assert report["status"] == "usable"
    assert report["winner_condition_id"] == "N"
    assert report["score_by_condition"] == {"A": 0.0, "N": 1.0}


def test_three_condition_input_produces_each_canonical_condition_pair() -> None:
    rows: list[dict[str, Any]] = []
    for left, right, winner in (("N", "A", "A"), ("N", "S", "B"), ("S", "A", "tie")):
        for order, position_winner in (
            ((left, right), winner),
            ((right, left), {"A": "B", "B": "A", "tie": "tie"}[winner]),
        ):
            # The fixture helper's two fixed condition IDs are enough for N/A;
            # construct the S rows explicitly for the generic three-condition case.
            if {left, right} == {"N", "A"}:
                rows.extend([judgment("task", 0, order, position_winner)])
            else:
                rows.append(
                    {
                        "task_id": "task",
                        "repeat": 0,
                        "condition_ids": list(order),
                        "generation_ids": [f"gen-{condition}-task-0" for condition in order],
                        "presented_conditions": ["A", "B"],
                        "winner": position_winner,
                        "evaluation_status": "completed",
                        "score_valid": True,
                    }
                )
    result = compute_pairwise_statistics(rows, bootstrap_resamples=10, seed=8)
    assert result["condition_ids"] == ["A", "N", "S"]
    assert {tuple(row["condition_ids"]) for row in result["pair_results"]} == {("A", "N"), ("N", "S"), ("A", "S")}


def test_judges_remain_separate_and_disagreement_is_not_hidden() -> None:
    rows = paired_task("t1", "A", judge="j1") + paired_task("t1", "B", judge="j2")
    result = compute_pairwise_statistics(rows, bootstrap_resamples=20, seed=6)
    report = result["pair_reports"][0]
    assert [row["judge_id"] for row in report["judge_reports"]] == ["j1", "j2"]
    assert report["judge_agreement"]["status"] == "disagreement"
    assert report["winner"] == "disagreement"
    assert report["score_for_canonical_first"] is None
    assert report["score_by_condition"] is None
    assert result["judge_summaries"][0]["usable_pair_count"] == 1
    assert result["judge_summaries"][1]["usable_pair_count"] == 1


def test_same_judge_label_with_different_runtime_or_criteria_is_separate_protocol() -> None:
    first = paired_task("t1", "A", judge="panel")
    second = paired_task("t1", "A", judge="panel")
    for row in first:
        row.update(judge_runtime_sha256="runtime-a", criteria_sha256="criteria-a")
    for row in second:
        row.update(judge_runtime_sha256="runtime-b", criteria_sha256="criteria-b")

    result = compute_pairwise_statistics(first + second, bootstrap_resamples=20, seed=61)

    assert len(result["judge_summaries"]) == 2
    assert len(result["pair_results"]) == 2
    assert {row["judge_id"] for row in result["pair_results"]} == {"panel"}
    assert {row["judge_identity"] for row in result["pair_results"]} == {
        "panel|runtime=runtime-a|criteria=criteria-a",
        "panel|runtime=runtime-b|criteria=criteria-b",
    }


def test_task_balancing_averages_repeats_within_task_before_bootstrap() -> None:
    rows = paired_task("large", "A", repeat=0)
    rows += paired_task("large", "A", repeat=1)
    rows += paired_task("small", "B", repeat=0)
    result = compute_pairwise_statistics(rows, bootstrap_resamples=100, seed=7)
    pair_result = result["pair_results"][0]
    assert pair_result["distinct_task_count"] == 2
    assert pair_result["usable_task_count"] == 2
    assert pair_result["point_estimate_by_condition"]["A"] == pytest.approx(0.5)
    assert pair_result["point_estimate_by_condition"]["N"] == pytest.approx(0.5)
    assert pair_result["task_clusters"][0]["usable_repetition_count"] == 2
    assert pair_result["bootstrap"]["cluster_unit"] == "task_id"
    assert pair_result["bootstrap"]["reason"] is None


def test_bootstrap_is_seed_deterministic_and_mixed_outcomes_have_interval() -> None:
    rows = paired_task("t1", "A") + paired_task("t2", "B") + paired_task("t3", "tie")
    first = compute_pairwise_statistics(rows, bootstrap_resamples=200, seed=11)
    second = compute_pairwise_statistics(rows, bootstrap_resamples=200, seed=11)
    third = compute_pairwise_statistics(rows, bootstrap_resamples=200, seed=12)
    one = first["pair_results"][0]["bootstrap"]
    assert one == second["pair_results"][0]["bootstrap"]
    assert one["reason"] is None
    assert one["ci95_lower"] is not None and one["ci95_upper"] is not None
    assert one != third["pair_results"][0]["bootstrap"]


def test_unjudgeable_and_missing_rows_are_excluded_and_recorded() -> None:
    rows = paired_task("usable", "A")
    rows += [
        judgment("bad", 0, ("N", "A"), "unjudgeable"),
        judgment("bad", 0, ("A", "N"), "unjudgeable"),
        judgment("missing", 0, ("N", "A"), "A"),
    ]
    result = compute_pairwise_statistics(rows, bootstrap_resamples=20, seed=13)
    pair_result = result["pair_results"][0]
    assert pair_result["outcome_counts"]["unjudgeable"] == 2
    assert pair_result["exclusion_counts"]["unjudgeable"] == 1
    assert pair_result["exclusion_counts"]["missing_order"] == 1
    assert pair_result["usable_task_count"] == 1
    assert pair_result["bootstrap"]["ci95_lower"] is None
    assert pair_result["bootstrap"]["reason"] == "fewer_than_two_usable_tasks"


def test_no_usable_tasks_and_degenerate_outcomes_have_reasons() -> None:
    no_usable = compute_pairwise_statistics(
        [judgment("bad", 0, ("N", "A"), "unjudgeable"), judgment("bad", 0, ("A", "N"), "unjudgeable")],
        bootstrap_resamples=10,
        seed=14,
    )
    assert no_usable["pair_results"][0]["bootstrap"]["reason"] == "no_usable_tasks"

    degenerate = compute_pairwise_statistics(paired_task("t1", "tie") + paired_task("t2", "tie"), seed=15)
    assert degenerate["pair_results"][0]["bootstrap"]["reason"] == "degenerate_outcomes"


def test_invalid_identity_is_explicit_and_does_not_become_a_task() -> None:
    rows = [
        judgment("valid", 0, ("N", "A"), "A"),
        judgment("valid", 0, ("A", "N"), "B"),
        {"task_id": "invalid", "condition_ids": ["N", "A"], "winner": "A"},
    ]
    result = compute_pairwise_statistics(rows, bootstrap_resamples=10, seed=16)
    assert result["invalid_input_row_count"] == 1
    assert result["excluded_input_rows"][0]["task_id"] == "invalid"
    assert result["pair_results"][0]["distinct_task_count"] == 1


def test_explicit_winner_condition_id_is_checked_against_position_label() -> None:
    good = paired_task("good", "A")
    good[0]["winner_condition_id"] = "N"
    good[1]["winner_condition_id"] = "N"
    bad = paired_task("bad", "A")
    bad[0]["winner_condition_id"] = "A"
    bad[1]["winner_condition_id"] = "A"
    result = compute_pairwise_statistics(good + bad, bootstrap_resamples=10, seed=17)
    bad_report = next(row for row in result["pair_reports"] if row["task_id"] == "bad")
    assert bad_report["status"] == "unjudgeable"
    assert bad_report["judge_reports"][0]["orders"][0]["status"] == "unjudgeable"


def test_agreement_rate_counts_mutually_usable_generation_pairs_once() -> None:
    rows = paired_task("same", "tie", judge="sol") + paired_task("same", "tie", judge="opus")
    rows += paired_task("different", "A", judge="sol") + paired_task("different", "B", judge="opus")
    rows += paired_task("unknown", "unjudgeable", judge="sol") + paired_task("unknown", "A", judge="opus")
    result = compute_pairwise_statistics(rows + rows, seed=7, bootstrap_resamples=20)
    agreement = result["judge_agreement"][0]
    assert agreement["compared_pair_count"] == 2
    assert agreement["agreement_count"] == agreement["disagreement_count"] == 1
    assert agreement["agreement_rate"] == 0.5
    assert agreement["excluded_pair_count"] == 1
    assert agreement["disagreements"][0]["task_id"] == "different"
    assert agreement["exclusions"][0]["task_id"] == "unknown"
