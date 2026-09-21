# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Item-bound observation completeness, never semantic verification.

These records are evaluator observations. Their shape cannot establish that a
comparison is correct, an input change is meaningful, or an application worked.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

OBSERVATION_METHODS = {"source_comparison": "research", "input_change": "functional"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_requirements(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and set(value) <= {"pass", "fail"}
        and all(
            isinstance(kinds, list)
            and bool(kinds)
            and all(isinstance(kind, str) and kind in OBSERVATION_METHODS for kind in kinds)
            and len(kinds) == len(set(kinds))
            for kinds in value.values()
        )
    )


def recorded_observations(
    record: Mapping[str, Any],
    *,
    identifier: str,
    method: str,
    source_scope: Callable[[str, str], str | None],
) -> dict[str, set[str]]:
    """Return complete observation kinds per submission in a verified shell record.

    The caller has already verified each original source hash and the captured call.
    Only references on this criterion count. Pairwise records cannot transfer an
    observation from one submission to the other.
    """
    sources = {source["path"]: source["sha256"] for source in record["source_artifacts"]}
    covered: dict[str, set[str]] = {}
    for check in record["checks"]:
        item = check["observation"]
        if not isinstance(item, Mapping):
            continue
        ids, kind = item.get("criterion_ids"), item.get("kind")
        if (
            not isinstance(ids, list)
            or not ids
            or identifier not in ids
            or not all(_text(value) for value in ids)
            or len(ids) != len(set(ids))
            or not isinstance(kind, str)
            or OBSERVATION_METHODS.get(kind) != method
        ):
            continue
        artifact_path: Any = item.get("artifact_path")
        if kind == "source_comparison":
            submission, reference = item.get("submission"), item.get("reference")
            if not _passage(submission, sources) or not _passage(reference, sources):
                continue
            assert isinstance(submission, Mapping) and isinstance(reference, Mapping)
            artifact_path = submission["path"]
            reference_path = reference["path"]
            if not reference_path.startswith(("reference_files/", "research/", ".harness_evidence/research/")):
                continue
            if not _text(item.get("comparison")):
                continue
        elif kind == "input_change":
            before, after = item.get("before"), item.get("after")
            if not _state(before) or not _state(after):
                continue
            assert isinstance(before, Mapping) and isinstance(after, Mapping)
            if (
                before["inputs"] == after["inputs"]
                or not _located_values(item.get("expected"))
                or not _text(item.get("engine"))
                or not _text(item.get("operation"))
                or not _text(item.get("comparison"))
                or item.get("operation_mode") not in ("direct_cell_write", "existing_control", "existing_filter")
                or item.get("update_mode")
                not in ("automatic", "manual_recalculation", "manual_refresh", "not_observed")
            ):
                continue
        if not isinstance(artifact_path, str) or artifact_path not in sources:
            continue
        scope = source_scope(artifact_path, sources[artifact_path])
        if scope:
            covered.setdefault(scope, set()).add(kind)
    return covered


def _passage(value: Any, sources: Mapping[str, str]) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("path"), str)
        and value["path"] in sources
        and _text(value.get("location"))
        and _text(value.get("observed"))
    )


def _state(value: Any) -> bool:
    return (
        isinstance(value, Mapping) and _located_values(value.get("inputs")) and _located_values(value.get("outputs"))
    )


def _located_values(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(_text(location) for location in value)
