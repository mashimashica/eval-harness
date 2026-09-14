# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Task-balanced statistics for saved anonymous pairwise judgments.

The public :func:`compute_pairwise_statistics` function consumes the saved
``judgments.jsonl`` row mappings emitted by the pairwise evaluator.  Rows are
matched by task, repetition, generation pair, condition pair, and judge.  A
judge contributes a usable paired result only when both presentation orders
are present and agree; duplicate re-evaluations and conflicting order votes
are retained in the pair report and excluded from the paired estimate.

The returned JSON-compatible mapping contains:

* ``pair_reports``: one report per distinct task/repeat/generation pair,
  including every judge's order reports and agreement or exclusion reason;
* ``judge_summaries``: separate status and outcome counts for each judge;
* ``pair_results``: one condition-pair estimate per judge protocol with
  task-balanced win credit (tie = 0.5) and a deterministic task-cluster
  percentile 95% interval.  Panel-level disagreement remains in
  ``pair_reports``; it is never hidden in a pooled quality estimate.

For a pair result, repetitions are averaged within each task first, then task
clusters are averaged.  Bootstrap resampling draws tasks with replacement and
keeps all usable repetitions in each selected task cluster.  Thus repeated
generations never become independent tasks, and rows from a judge panel never
become independent bootstrap observations.  A confidence interval is omitted
with an explicit reason when fewer than two usable tasks exist or all usable
task scores are identical.

Panel agreement compares only mutually usable judgments of the same saved
generation pair. Disagreements have no combined numeric score; the individual
judge estimates and their reasons remain separate.

The retained arena implementation is intentionally not called here:
``resources_servers.arena.arena._bootstrap_per_category`` samples individual
judge games, while ``fit_anchored_elo.py`` estimates one policy against fixed
external Elo ratings.  Neither represents matched order reversals, duplicate
saved judgments, task clusters, or a judge-separated panel.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from statistics import mean
from typing import Any, Literal

Outcome = Literal["win", "loss", "tie", "unjudgeable"]
_ReportStatus = Literal["usable", "missing_order", "unjudgeable", "order_conflict", "duplicate_conflict"]
Endpoint = tuple[str, str]
CanonicalEndpoints = tuple[Endpoint, Endpoint]
PairKey = tuple[str, int, CanonicalEndpoints]


@dataclass(frozen=True)
class _NormalizedJudgment:
    row_index: int
    task_id: str
    repeat: int
    judge_id: str
    judge_identity: str
    condition_ids: tuple[str, str]
    generation_ids: tuple[str, str]
    endpoints: tuple[Endpoint, Endpoint]
    canonical_endpoints: CanonicalEndpoints
    outcome: Outcome
    winner_condition_id: str | None
    raw_winner: str | None
    judgment_id: str | None
    pair_id: str | None
    reason: str | None


@dataclass(frozen=True)
class _ExcludedInput:
    row_index: int
    task_id: str | None
    judge_id: str
    reason: str


@dataclass(frozen=True)
class _OrderAggregate:
    status: _ReportStatus
    outcome: Outcome
    winner_condition_id: str | None
    record: dict[str, Any]
    duplicate_count: int


@dataclass(frozen=True)
class _JudgeAggregate:
    pair_key: PairKey
    judge_id: str
    judge_identity: str
    status: _ReportStatus
    winner_condition_id: str | None
    canonical_outcome: Outcome
    score_for_first: float | None
    record: dict[str, Any]


@dataclass(frozen=True)
class _PairAggregate:
    pair_key: PairKey
    record: dict[str, Any]
    score_for_first: float | None


def compute_pairwise_statistics(
    judgments: Iterable[Mapping[str, Any]],
    *,
    bootstrap_resamples: int = 1_000,
    seed: int = 0,
    judge_id_field: str = "judge_id",
) -> dict[str, Any]:
    """Compute judge-separated, task-balanced statistics from saved judgments.

    Args:
        judgments: Saved pairwise judgment mappings.  Each usable row has two
            ``generation_ids``, two ``condition_ids``, ``presented_conditions``
            containing the position labels ``["A", "B"]``, and a ``winner``
            of ``"A"``, ``"B"``, or ``"tie"``.  ``winner_condition_id`` may
            be supplied and is checked against the position winner.  Rows with
            ``winner == "unjudgeable"`` or incomplete execution are retained
            as exclusions.  Missing ``judge_id`` values use ``"legacy"``.
        bootstrap_resamples: Positive number of task-cluster draws for each
            condition-pair confidence interval.
        seed: Fixed random seed used for every task-cluster bootstrap.
        judge_id_field: Field containing the judge identity; missing or null
            values still use the ``"legacy"`` judge bucket.

    Returns:
        A JSON-compatible dictionary with ``pair_reports``,
        ``judge_summaries``, ``pair_results``, and explicit collapse and
        exclusion counts.  ``pair_results`` contains a task-balanced point
        estimate for the first canonical condition and its mirrored second
        condition estimate.  A ``bootstrap`` mapping always includes
        ``seed``, ``resamples``, and ``reason``; its bounds are null when the
        usable task set is absent, has fewer than two tasks, or is degenerate.

    Raises:
        ValueError: If bootstrap arguments are invalid or ``judge_id_field``
            is empty.
    """

    _validate_bootstrap_arguments(bootstrap_resamples, seed, judge_id_field)
    rows = list(judgments)
    normalized: list[_NormalizedJudgment] = []
    excluded_inputs: list[_ExcludedInput] = []
    for row_index, row in enumerate(rows):
        item, excluded = _normalise_judgment(row_index, row, judge_id_field)
        if item is not None:
            normalized.append(item)
        else:
            assert excluded is not None
            excluded_inputs.append(excluded)

    grouped: defaultdict[tuple[str, int, CanonicalEndpoints, str], list[_NormalizedJudgment]] = defaultdict(list)
    for item in normalized:
        grouped[(item.task_id, item.repeat, item.canonical_endpoints, item.judge_identity)].append(item)

    judge_aggregates: list[_JudgeAggregate] = []
    pair_groups: defaultdict[PairKey, list[_JudgeAggregate]] = defaultdict(list)
    duplicate_row_count = 0
    collapsed_order_count = 0
    for group_key, group_rows in sorted(grouped.items(), key=lambda item: item[0]):
        pair_key = (group_key[0], group_key[1], group_key[2])
        aggregate = _aggregate_judge_group(pair_key, group_key[3], group_rows)
        judge_aggregates.append(aggregate)
        pair_groups[pair_key].append(aggregate)
        collapsed_order_count += len(aggregate.record["orders"])
        duplicate_row_count += sum(order["duplicate_count"] for order in aggregate.record["orders"])

    pair_aggregates: list[_PairAggregate] = []
    pair_reports: list[dict[str, Any]] = []
    for pair_key, reports in sorted(pair_groups.items(), key=lambda item: item[0]):
        pair_aggregate = _aggregate_pair(pair_key, reports)
        pair_aggregates.append(pair_aggregate)
        pair_reports.append(pair_aggregate.record)

    # Keep the reliable estimates judge-specific.  ``pair_aggregates`` is
    # still used for the panel-level agreement report, but averaging those
    # reports would turn a panel disagreement into an apparently precise
    # single score.
    pair_results = _pair_results(judge_aggregates, bootstrap_resamples, seed)
    judge_summaries = _judge_summaries(judge_aggregates)
    status_counts = Counter(aggregate.status for aggregate in judge_aggregates)
    return {
        "schema_version": 1,
        "input_row_count": len(rows),
        "normalized_row_count": len(normalized),
        "invalid_input_row_count": len(excluded_inputs),
        "collapsed_pair_count": len(pair_reports),
        "collapsed_order_count": collapsed_order_count,
        "collapsed_duplicate_row_count": duplicate_row_count,
        "condition_ids": _condition_ids(normalized),
        "pair_reports": pair_reports,
        "pair_results": pair_results,
        "judge_summaries": judge_summaries,
        "judge_agreement": _judge_agreement(pair_reports),
        "judge_report_status_counts": dict(sorted(status_counts.items())),
        "excluded_input_rows": [
            {
                "row_index": item.row_index,
                "task_id": item.task_id,
                "judge_id": item.judge_id,
                "reason": item.reason,
            }
            for item in excluded_inputs
        ],
        "bootstrap": {"method": "task_cluster_percentile_95", "seed": seed, "resamples": bootstrap_resamples},
    }


def _validate_bootstrap_arguments(bootstrap_resamples: int, seed: int, judge_id_field: str) -> None:
    if isinstance(bootstrap_resamples, bool) or not isinstance(bootstrap_resamples, int) or bootstrap_resamples <= 0:
        raise ValueError("bootstrap_resamples must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not isinstance(judge_id_field, str) or not judge_id_field.strip():
        raise ValueError("judge_id_field must be a non-empty string")


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _judge_identity(row: Mapping[str, Any], judge_id: str) -> str:
    """Separate equal labels when saved runtime or criteria identities differ."""

    runtime_hash = _text(row.get("judge_runtime_sha256"))
    if runtime_hash is None:
        runtime = row.get("judge_runtime_identity", row.get("judge_runtime"))
        if isinstance(runtime, Mapping):
            encoded = json.dumps(runtime, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            runtime_hash = hashlib.sha256(encoded).hexdigest()
    criteria_hash = _text(row.get("criteria_sha256"))
    if runtime_hash is None and criteria_hash is None:
        return judge_id
    return f"{judge_id}|runtime={runtime_hash or 'none'}|criteria={criteria_hash or 'none'}"


def _pair_text(value: Any) -> tuple[str, str] | None:
    if isinstance(value, str) or not isinstance(value, Sequence) or len(value) != 2:
        return None
    first, second = value
    if not isinstance(first, str) or not first or not isinstance(second, str) or not second:
        return None
    return first, second


def _normalise_judgment(
    row_index: int, row: Mapping[str, Any], judge_id_field: str
) -> tuple[_NormalizedJudgment | None, _ExcludedInput | None]:
    task_id = _text(row.get("task_id"))
    raw_judge = row.get(judge_id_field, "legacy")
    judge_id = "legacy" if raw_judge is None else _text(raw_judge)
    if judge_id is None:
        return None, _ExcludedInput(row_index, task_id, "legacy", "judge_id must be a non-empty string")

    def invalid(reason: str) -> tuple[None, _ExcludedInput]:
        return None, _ExcludedInput(row_index, task_id, judge_id, reason)

    if task_id is None:
        return invalid("task_id must be a non-empty string")
    conditions = _pair_text(row.get("condition_ids"))
    if conditions is None or conditions[0] == conditions[1]:
        return invalid("condition_ids must contain two distinct non-empty strings")
    generations = _pair_text(row.get("generation_ids"))
    if generations is None or generations[0] == generations[1]:
        return invalid("generation_ids must contain two distinct non-empty strings")
    presented = _pair_text(row.get("presented_conditions"))
    if presented is None or set(presented) != {"A", "B"}:
        return invalid('presented_conditions must contain the two position labels "A" and "B"')
    raw_repeat = row.get("repeat", 0)
    if isinstance(raw_repeat, bool) or not isinstance(raw_repeat, int) or raw_repeat < 0:
        return invalid("repeat must be a non-negative integer")

    endpoints = ((conditions[0], generations[0]), (conditions[1], generations[1]))
    canonical = tuple(sorted(endpoints))
    assert len(canonical) == 2
    canonical_endpoints: CanonicalEndpoints = (canonical[0], canonical[1])
    raw_winner_value = row.get("winner")
    raw_winner = raw_winner_value if isinstance(raw_winner_value, str) else None
    raw_winner_condition = row.get("winner_condition_id")
    winner_condition: str | None = _text(raw_winner_condition) if raw_winner_condition is not None else None
    if raw_winner_condition is not None and winner_condition is None:
        return invalid("winner_condition_id must be a non-empty string")

    status = row.get("evaluation_status")
    reason: str | None
    if status is not None and status != "completed":
        outcome: Outcome = "unjudgeable"
        reason = f"evaluation_status={status!r}"
        winner_condition = None
    elif "score_valid" in row and row.get("score_valid") is not True:
        outcome = "unjudgeable"
        reason = "score_valid is not true"
        winner_condition = None
    else:
        outcome, winner_condition, reason = _resolve_outcome(raw_winner_value, winner_condition, conditions, presented)

    judgment_id = _text(row.get("judgment_id"))
    pair_id = _text(row.get("pair_id"))
    item = _NormalizedJudgment(
        row_index=row_index,
        task_id=task_id,
        repeat=raw_repeat,
        judge_id=judge_id,
        judge_identity=_judge_identity(row, judge_id),
        condition_ids=conditions,
        generation_ids=generations,
        endpoints=endpoints,
        canonical_endpoints=canonical_endpoints,
        outcome=outcome,
        winner_condition_id=winner_condition,
        raw_winner=raw_winner,
        judgment_id=judgment_id,
        pair_id=pair_id,
        reason=reason,
    )
    return item, None


def _resolve_outcome(
    raw_winner: Any,
    winner_condition_id: str | None,
    conditions: tuple[str, str],
    presented: tuple[str, str],
) -> tuple[Outcome, str | None, str | None]:
    if winner_condition_id is not None and winner_condition_id not in conditions:
        return "unjudgeable", None, "winner_condition_id is not one of condition_ids"
    if raw_winner is not None and not isinstance(raw_winner, str):
        return "unjudgeable", None, "winner must be a string"
    if raw_winner not in {None, "A", "B", "tie", "unjudgeable"}:
        return "unjudgeable", None, 'winner must be exactly "A", "B", "tie", or "unjudgeable"'
    if raw_winner == "unjudgeable":
        return "unjudgeable", None, "winner is unjudgeable"
    if raw_winner == "tie":
        if winner_condition_id is not None:
            return "unjudgeable", None, "tie cannot include winner_condition_id"
        return "tie", None, None
    if raw_winner in {"A", "B"}:
        position = presented.index(raw_winner)
        derived_winner = conditions[position]
        if winner_condition_id is not None and winner_condition_id != derived_winner:
            return "unjudgeable", None, "winner disagrees with winner_condition_id"
        return "win", derived_winner, None
    if winner_condition_id is not None:
        return "win", winner_condition_id, None
    return "unjudgeable", None, "winner is missing"


def _canonical_outcome(winner_condition_id: str | None, pair_key: PairKey) -> Outcome:
    if winner_condition_id is None:
        return "tie"
    first_condition, second_condition = pair_key[2][0][0], pair_key[2][1][0]
    if winner_condition_id == first_condition:
        return "win"
    if winner_condition_id == second_condition:
        return "loss"
    return "unjudgeable"


def _position_label(outcome: Outcome) -> str:
    if outcome == "win":
        return "A"
    if outcome == "loss":
        return "B"
    if outcome == "tie":
        return "tie"
    return "unjudgeable"


def _order_aggregate(rows: list[_NormalizedJudgment], pair_key: PairKey) -> _OrderAggregate:
    first = rows[0]
    semantic_outcomes = {(item.outcome, item.winner_condition_id) for item in rows}
    duplicate_count = max(0, len(rows) - 1)
    if len(semantic_outcomes) != 1:
        record = _order_record(rows, "duplicate_conflict", "unjudgeable", None, pair_key)
        record["reason"] = "duplicate reevaluations for one presentation disagree"
        record["outcomes"] = [
            {"outcome": item.outcome, "winner_condition_id": item.winner_condition_id} for item in rows
        ]
        return _OrderAggregate("duplicate_conflict", "unjudgeable", None, record, duplicate_count)

    outcome, winner_condition = next(iter(semantic_outcomes))
    canonical = _canonical_outcome(winner_condition, pair_key) if outcome != "unjudgeable" else "unjudgeable"
    status: _ReportStatus = "usable" if canonical != "unjudgeable" else "unjudgeable"
    record = _order_record(rows, status, canonical, winner_condition, pair_key)
    if status == "unjudgeable":
        record["reason"] = first.reason or "order presentation is unjudgeable"
    return _OrderAggregate(status, canonical, winner_condition, record, duplicate_count)


def _order_record(
    rows: list[_NormalizedJudgment],
    status: _ReportStatus,
    canonical_outcome: Outcome,
    winner_condition_id: str | None,
    pair_key: PairKey,
) -> dict[str, Any]:
    first = rows[0]
    return {
        "status": status,
        "order_condition_ids": list(first.condition_ids),
        "order_generation_ids": list(first.generation_ids),
        "presented_conditions": ["A", "B"],
        "winner": _position_label(canonical_outcome),
        "winner_condition_id": winner_condition_id,
        "outcome_for_canonical_first": canonical_outcome,
        "row_indices": [item.row_index for item in rows],
        "judgment_ids": [item.judgment_id for item in rows if item.judgment_id is not None],
        "pair_ids": [item.pair_id for item in rows if item.pair_id is not None],
        "raw_winners": [item.raw_winner for item in rows],
        "duplicate_count": max(0, len(rows) - 1),
        "canonical_condition_ids": [endpoint[0] for endpoint in pair_key[2]],
        "canonical_generation_ids": [endpoint[1] for endpoint in pair_key[2]],
    }


def _aggregate_judge_group(pair_key: PairKey, judge_identity: str, rows: list[_NormalizedJudgment]) -> _JudgeAggregate:
    buckets: defaultdict[tuple[Endpoint, Endpoint], list[_NormalizedJudgment]] = defaultdict(list)
    for row in rows:
        buckets[row.endpoints].append(row)
    order_aggregates = [
        _order_aggregate(bucket, pair_key) for _, bucket in sorted(buckets.items(), key=lambda item: item[0])
    ]
    duplicate_conflict = any(order.status == "duplicate_conflict" for order in order_aggregates)
    if duplicate_conflict:
        status: _ReportStatus = "duplicate_conflict"
        reason = "duplicate reevaluations disagree for at least one order presentation"
        winner_condition_id = None
        canonical_outcome: Outcome = "unjudgeable"
        score_for_first = None
    elif len(order_aggregates) != 2:
        status = "missing_order"
        reason = "both order presentations are required; one or more are missing"
        winner_condition_id = None
        canonical_outcome = "unjudgeable"
        score_for_first = None
    elif any(order.status != "usable" for order in order_aggregates):
        status = "unjudgeable"
        reason = "one or both order presentations are unjudgeable"
        winner_condition_id = None
        canonical_outcome = "unjudgeable"
        score_for_first = None
    else:
        first, second = order_aggregates
        if first.winner_condition_id != second.winner_condition_id:
            status = "order_conflict"
            reason = "reversed order presentations disagree on the winning condition"
            winner_condition_id = None
            canonical_outcome = "unjudgeable"
            score_for_first = None
        else:
            status = "usable"
            reason = "both order presentations agree"
            winner_condition_id = first.winner_condition_id
            canonical_outcome = first.outcome
            score_for_first = _score_for_first(canonical_outcome)
    judge_id = rows[0].judge_id
    record: dict[str, Any] = {
        "judge_id": judge_id,
        "judge_identity": judge_identity,
        "status": status,
        "reason": reason,
        "winner": _position_label(canonical_outcome),
        "winner_condition_id": winner_condition_id,
        "outcome_for_canonical_first": canonical_outcome,
        "score_for_canonical_first": score_for_first,
        "orders": [order.record for order in order_aggregates],
        "row_count": len(rows),
        "duplicate_count": sum(order.duplicate_count for order in order_aggregates),
    }
    return _JudgeAggregate(
        pair_key, judge_id, judge_identity, status, winner_condition_id, canonical_outcome, score_for_first, record
    )


def _score_for_first(outcome: Outcome) -> float | None:
    if outcome == "win":
        return 1.0
    if outcome == "loss":
        return 0.0
    if outcome == "tie":
        return 0.5
    return None


def _aggregate_pair(pair_key: PairKey, reports: list[_JudgeAggregate]) -> _PairAggregate:
    usable = [report for report in reports if report.status == "usable" and report.score_for_first is not None]
    scores: list[float] = []
    for report in usable:
        assert report.score_for_first is not None
        scores.append(report.score_for_first)
    winner_ids = {report.winner_condition_id for report in usable}
    if not usable:
        agreement_status = "no_usable_judges"
        agreement_reason = "no judge has two agreeing usable order presentations"
        winner_condition_id = None
        winner = "unjudgeable"
        score_for_first = None
        status = "unjudgeable"
    else:
        score_for_first = scores[0] if len(winner_ids) == 1 else None
        if len(winner_ids) == 1:
            winner_condition_id = next(iter(winner_ids))
            winner = _position_label(_canonical_outcome(winner_condition_id, pair_key))
            agreement_status = "agreement"
            agreement_reason = "usable judges agree on the winning condition"
        else:
            winner_condition_id = None
            winner = "disagreement"
            agreement_status = "disagreement"
            agreement_reason = "usable judges disagree on the winning condition"
        status = "usable" if len(winner_ids) == 1 else "disagreement"

    outcome_by_judge = {report.judge_identity: report.record["winner"] for report in reports}
    excluded_reasons = [
        f"{report.judge_identity}: {report.record['reason']}" for report in reports if report.status != "usable"
    ]
    if usable and excluded_reasons:
        agreement_reason += "; excluded judge reports are retained"
    condition_ids = [endpoint[0] for endpoint in pair_key[2]]
    generation_ids = [endpoint[1] for endpoint in pair_key[2]]
    pair_ids = sorted(
        {pair_id for report in reports for order in report.record["orders"] for pair_id in order["pair_ids"]}
    )
    record: dict[str, Any] = {
        "task_id": pair_key[0],
        "repeat": pair_key[1],
        "pair_ids": pair_ids,
        "condition_ids": condition_ids,
        "generation_ids": generation_ids,
        "status": status,
        "winner": winner,
        "winner_condition_id": winner_condition_id,
        "score_for_canonical_first": score_for_first,
        "score_by_condition": (
            {condition_ids[0]: score_for_first, condition_ids[1]: 1.0 - score_for_first}
            if score_for_first is not None
            else None
        ),
        "judge_agreement": {
            "status": agreement_status,
            "reason": agreement_reason,
            "outcome_by_judge": outcome_by_judge,
            "usable_judge_ids": [report.judge_identity for report in usable],
            "excluded_reasons": excluded_reasons,
        },
        "usable_judge_count": len(usable),
        "excluded_judge_count": len(reports) - len(usable),
        "judge_reports": [report.record for report in sorted(reports, key=lambda item: item.judge_identity)],
    }
    return _PairAggregate(pair_key, record, score_for_first)


def _condition_ids(rows: Sequence[_NormalizedJudgment]) -> list[str]:
    return sorted({condition for row in rows for condition in row.condition_ids})


def _single_judge_pair(judge_report: _JudgeAggregate) -> _PairAggregate:
    """Adapt one judge report to the task-balanced result representation."""

    pair_key = judge_report.pair_key
    condition_ids = [endpoint[0] for endpoint in pair_key[2]]
    generation_ids = [endpoint[1] for endpoint in pair_key[2]]
    report = dict(judge_report.record)
    report.update(
        {
            "pair_ids": sorted({pair_id for order in judge_report.record["orders"] for pair_id in order["pair_ids"]}),
            "condition_ids": condition_ids,
            "generation_ids": generation_ids,
            "judge_reports": [judge_report.record],
            "usable_judge_count": int(judge_report.status == "usable"),
            "excluded_judge_count": int(judge_report.status != "usable"),
            "judge_agreement": {
                "status": "single_judge",
                "reason": "one independent judge protocol",
                "outcome_by_judge": {judge_report.judge_identity: judge_report.record["winner"]},
                "usable_judge_ids": ([judge_report.judge_identity] if judge_report.status == "usable" else []),
                "excluded_reasons": (
                    [f"{judge_report.judge_identity}: {judge_report.record['reason']}"]
                    if judge_report.status != "usable"
                    else []
                ),
            },
        }
    )
    return _PairAggregate(pair_key, report, judge_report.score_for_first)


def _pair_results(
    judge_reports: Sequence[_JudgeAggregate], bootstrap_resamples: int, seed: int
) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, str, str], list[_PairAggregate]] = defaultdict(list)
    for judge_report in judge_reports:
        first, second = judge_report.pair_key[2]
        grouped[(first[0], second[0], judge_report.judge_identity)].append(_single_judge_pair(judge_report))

    results: list[dict[str, Any]] = []
    for (condition_first, condition_second, judge_identity), pair_reports in sorted(grouped.items()):
        result = _pair_result((condition_first, condition_second), pair_reports, bootstrap_resamples, seed)
        first_report = pair_reports[0].record["judge_reports"][0]
        result["judge_id"] = first_report["judge_id"]
        result["judge_identity"] = judge_identity
        results.append(result)
    return results


def _pair_result(
    condition_pair: tuple[str, str], pairs: Sequence[_PairAggregate], bootstrap_resamples: int, seed: int
) -> dict[str, Any]:
    task_groups: defaultdict[str, list[_PairAggregate]] = defaultdict(list)
    outcome_counts: Counter[str] = Counter()
    canonical_outcome_counts: Counter[str] = Counter()
    exclusion_counts: Counter[str] = Counter()
    for pair in pairs:
        task_groups[pair.pair_key[0]].append(pair)
        report = pair.record
        if report["status"] != "usable":
            outcome_counts["unjudgeable"] += 1
            canonical_outcome_counts["unjudgeable"] += 1
        elif report["winner"] == "A":
            outcome_counts["first_wins"] += 1
            canonical_outcome_counts["win"] += 1
        elif report["winner"] == "B":
            outcome_counts["second_wins"] += 1
            canonical_outcome_counts["loss"] += 1
        elif report["winner"] == "tie":
            outcome_counts["ties"] += 1
            canonical_outcome_counts["tie"] += 1
        else:
            outcome_counts["judge_disagreements"] += 1
            canonical_outcome_counts["disagreement"] += 1
        for judge_report in report["judge_reports"]:
            if judge_report["status"] != "usable":
                exclusion_counts[str(judge_report["status"])] += 1

    task_records: list[dict[str, Any]] = []
    task_score_clusters: list[list[float]] = []
    for task_id, task_pairs in sorted(task_groups.items()):
        repetitions = []
        scores = []
        for pair in sorted(task_pairs, key=lambda item: item.pair_key[1:]):
            report = pair.record
            score = pair.score_for_first
            repetitions.append(
                {
                    "repeat": pair.pair_key[1],
                    "generation_ids": report["generation_ids"],
                    "status": report["status"],
                    "winner": report["winner"],
                    "score_for_canonical_first": score,
                }
            )
            if score is not None:
                scores.append(score)
        task_score = mean(scores) if scores else None
        if task_score is not None:
            task_score_clusters.append(scores)
        task_records.append(
            {
                "task_id": task_id,
                "repetitions": repetitions,
                "distinct_repeat_count": len(repetitions),
                "usable_repetition_count": len(scores),
                "task_balanced_win_credit": task_score,
            }
        )

    task_scores = [mean(cluster) for cluster in task_score_clusters]
    point_estimate = mean(task_scores) if task_scores else None
    bootstrap = _bootstrap_result(task_score_clusters, bootstrap_resamples, seed)
    first, second = condition_pair
    if point_estimate is None:
        point_by_condition: dict[str, float | None] = {first: None, second: None}
    else:
        point_by_condition = {first: point_estimate, second: 1.0 - point_estimate}
    lower = bootstrap["ci95_lower"]
    upper = bootstrap["ci95_upper"]
    if lower is None or upper is None:
        ci_by_condition = {first: {"lower": None, "upper": None}, second: {"lower": None, "upper": None}}
    else:
        ci_by_condition = {
            first: {"lower": lower, "upper": upper},
            second: {"lower": 1.0 - upper, "upper": 1.0 - lower},
        }
    return {
        "condition_ids": [first, second],
        "pair_report_count": len(pairs),
        "distinct_task_count": len(task_records),
        "usable_task_count": len(task_scores),
        "usable_repetition_count": sum(record["usable_repetition_count"] for record in task_records),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "canonical_outcome_counts": dict(sorted(canonical_outcome_counts.items())),
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "task_clusters": task_records,
        "point_estimate_by_condition": point_by_condition,
        "bootstrap": bootstrap,
        "ci95_by_condition": ci_by_condition,
    }


def _bootstrap_result(task_score_clusters: Sequence[Sequence[float]], resamples: int, seed: int) -> dict[str, Any]:
    task_scores = [mean(cluster) for cluster in task_score_clusters if cluster]
    result: dict[str, Any] = {
        "seed": seed,
        "resamples": resamples,
        "cluster_unit": "task_id",
        "task_count": len(task_scores),
        "ci95_lower": None,
        "ci95_upper": None,
        "reason": None,
    }
    if not task_scores:
        result["reason"] = "no_usable_tasks"
        return result
    if len(task_scores) < 2:
        result["reason"] = "fewer_than_two_usable_tasks"
        return result
    if len(set(task_scores)) < 2:
        result["reason"] = "degenerate_outcomes"
        return result

    rng = random.Random(seed)
    n_tasks = len(task_scores)
    estimates = [mean(task_scores[rng.randrange(n_tasks)] for _ in range(n_tasks)) for _ in range(resamples)]
    result["ci95_lower"] = _percentile(estimates, 2.5)
    result["ci95_upper"] = _percentile(estimates, 97.5)
    return result


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    position = (len(ordered) - 1) * percentile / 100.0
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return float(ordered[lower_index])
    fraction = position - lower_index
    return float(ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction)


def _judge_summaries(reports: Sequence[_JudgeAggregate]) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[_JudgeAggregate]] = defaultdict(list)
    for report in reports:
        grouped[report.judge_identity].append(report)
    summaries: list[dict[str, Any]] = []
    for judge_identity, judge_reports in sorted(grouped.items()):
        judge_id = judge_reports[0].judge_id
        status_counts = Counter(report.status for report in judge_reports)
        outcome_counts = Counter(report.canonical_outcome for report in judge_reports)
        summaries.append(
            {
                "judge_id": judge_id,
                "judge_identity": judge_identity,
                "pair_report_count": len(judge_reports),
                "usable_pair_count": sum(report.status == "usable" for report in judge_reports),
                "status_counts": dict(sorted(status_counts.items())),
                "outcome_counts": dict(sorted(outcome_counts.items())),
            }
        )
    return summaries


def _judge_agreement(pair_reports: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Descriptive agreement on identical generations after order checks."""
    identities = sorted({report["judge_identity"] for pair in pair_reports for report in pair["judge_reports"]})
    result: list[dict[str, Any]] = []
    for first, second in combinations(identities, 2):
        compared, agreed = 0, 0
        exclusions: list[dict[str, Any]] = []
        disagreements: list[dict[str, Any]] = []
        for pair in pair_reports:
            judges = {row["judge_identity"]: row for row in pair["judge_reports"]}
            if first not in judges or second not in judges:
                continue
            a, b = judges[first], judges[second]
            evidence = {key: pair[key] for key in ("task_id", "repeat", "generation_ids", "condition_ids")}
            if a["status"] != "usable" or b["status"] != "usable":
                exclusions.append({**evidence, "reasons": {first: a["reason"], second: b["reason"]}})
                continue
            compared += 1
            if a["winner_condition_id"] == b["winner_condition_id"]:
                agreed += 1
            else:
                disagreements.append(
                    {**evidence, "outcomes": {first: a["winner"], second: b["winner"]}, "judge_reports": [a, b]}
                )
        result.append(
            {
                "judge_identities": [first, second],
                "aggregation_unit": "saved_generation_pair",
                "definition": "identical canonical outcomes among generation pairs with two agreeing usable orders for both judges",
                "compared_pair_count": compared,
                "agreement_count": agreed,
                "disagreement_count": compared - agreed,
                "agreement_rate": agreed / compared if compared else None,
                "excluded_pair_count": len(exclusions),
                "exclusions": exclusions,
                "disagreements": disagreements,
                "reason": None if compared else "no_mutually_usable_pairs",
            }
        )
    return result
