# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".agents/development/scripts/gdpval_current.py"
SPEC = importlib.util.spec_from_file_location("gdpval_current_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
current = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(current)


def inputs(prompt: str, *, supplied_step: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    row = {"task_id": "example", "prompt": prompt}
    record = {
        "identity": {},
        "primary_route": {"content_readiness": {"historical_membership_ref": "unchanged-history"}},
        "assessment": {"task_verification": {"historical_result": "unconfirmed"}},
        "evidence_version": {"environment": {}},
    }
    review = {
        "task_id": "example",
        "row_index": 0,
        "row_sha256": current.row_hash(row),
        "summary": "PDF report",
        "content_feasibility": {"status": "candidate", "basis": "Explicit report deliverable", "assumptions": []},
        "required_capabilities": {
            "supplied_read": [
                {"format": ".step", "files": ["model.step"], "required_read_capabilities": ["step_geometry_read"]}
            ]
            if supplied_step
            else [],
            "participant_output": {"modalities": ["pdf"], "capabilities": ["pdf_author"]},
            "evaluation": {"method_categories": ["text/content"]},
        },
        "rubric_routes": [["original-id", 2, ["text/content"], True]],
        "conflicts_or_data_access_questions": [],
        "external_data": {},
        "human_domain_review": {},
    }
    return record, row, review


def test_media_cad_words_do_not_invent_authoring_or_known_unsupported() -> None:
    record, row, review = inputs("Write a PDF policy discussing video, music, CAD and an interactive user interface.")
    result = current.apply_review(record, row, review, {})
    assert result["environment_support"]["known_unsupported"] == []
    assert result["required_capabilities"]["participant_output"]["capabilities"] == ["pdf_author"]
    assert result["acceptance_scope"]["status"] == "included"
    assert result["environment_support"]["task_level_acceptance"] == "unverified"


def test_reading_provided_step_does_not_require_authoring_step() -> None:
    record, row, review = inputs("Read the supplied STEP and write a PDF report.", supplied_step=True)
    result = current.apply_review(record, row, review, {})
    assert result["primary_route"]["reference_formats"] == [".step"]
    assert result["primary_route"]["output_formats"] == ["pdf"]
    assert result["environment_support"]["required_input_read"][0]["required_read_capabilities"] == [
        "step_geometry_read"
    ]
    assert result["environment_support"]["required_output_authoring"]["capabilities"] == ["pdf_author"]


def test_feasibility_is_current_and_independent_of_common_proof() -> None:
    record, row, review = inputs("Conflicting original requirements.")
    review["content_feasibility"] = {
        "status": "needs_clarification",
        "basis": "Two different required names",
        "assumptions": ["Owner adjudication pending"],
    }
    evidence = {"common_methods": {"text/content": {"status": "verified", "receipt": "bounded-check"}}}
    result = current.apply_review(record, row, review, evidence)
    assert result["primary_route"]["content_readiness"]["status"] == "needs_clarification"
    assert result["assessment"]["scoring"]["result_status"] == "unconfirmed"
    assert result["environment_support"]["task_level_acceptance"] == "unverified"
    assert (
        result["assessment"]["inspection_protocol"]["required_methods"][0]["common_evidence"]["status"] == "verified"
    )
    assert result["acceptance_scope"]["status"] == "included"


def test_changed_source_rejects_stale_requirement_mapping() -> None:
    record, row, review = inputs("Original prompt")
    row["prompt"] = "Changed task"
    with pytest.raises(ValueError, match="bind the original"):
        current.apply_review(record, row, review, {})


def test_source_bound_addendum_updates_current_feasibility_without_changing_review() -> None:
    record, row, review = inputs("Use the supplied original guide.")
    addendum = {
        "source_row_sha256": review["row_sha256"],
        "evidence_ref": "provided-content-check#/tasks/0",
        "content_feasibility": {
            "status": "needs_clarification",
            "basis": "Two supplied documents disagree on the required identifier.",
            "assumptions": ["Resolve the identified discrepancy without rewriting the rubric."],
        },
    }
    result = current.apply_review(record, row, review, {"content_feasibility_updates": {"example": addendum}})
    assert result["primary_route"]["content_readiness"]["status"] == "needs_clarification"
    assert result["primary_route"]["content_readiness"]["basis_ref"] == addendum["evidence_ref"]
    assert result["task_specific_checks"]["current_content_addendum"] == addendum
    assert review["content_feasibility"]["status"] == "candidate"
    assert result["acceptance_scope"]["status"] == "included"


def test_stale_content_addendum_is_rejected() -> None:
    record, row, review = inputs("Original prompt")
    with pytest.raises(ValueError, match="addendum does not bind"):
        current.apply_review(
            record, row, review, {"content_feasibility_updates": {"example": {"source_row_sha256": "stale"}}}
        )


def route_evidence(review: dict[str, Any], *, pending: bool = False) -> dict[str, Any]:
    return {
        "route_applicability": {
            "example": {
                "row_sha256": review["row_sha256"],
                "evidence_ref": "source-bound-common-operation-proof",
                "generation": {
                    "status": "shared_routes_applicable",
                    "capabilities": [{"capability": "pdf_author", "basis_ref": "known-pdf-authoring-proof"}],
                },
                "criteria": [
                    {
                        "criterion_id": "original-id",
                        "status": "infrastructure_pending" if pending else "shared_route_applicable",
                        "methods": ["functional"] if pending else ["content"],
                        "basis_ref": "matching-source-item-and-component-proof",
                        "remaining_obligation": "Verify actual native control activation" if pending else None,
                    }
                ],
            }
        }
    }


def test_shared_operation_proof_can_be_adopted_without_participant_success() -> None:
    record, row, review = inputs("Write a PDF.")
    result = current.apply_review(record, row, review, route_evidence(review))
    env = result["environment_support"]
    assert env["task_level_acceptance"] == "common_routes_applicable_with_limits"
    assert env["required_evaluation_methods"][0]["task_criterion_applicability"] == "shared_route_applicable"
    assert env["generation_vs_evaluation"]["evaluation"]["actual_artifact_observation_required"] is True
    assert result["assessment"]["scoring"]["result_status"] == "unconfirmed"
    assert result["assessment"]["task_verification"] == {"historical_result": "unconfirmed"}


def test_pending_operation_remains_infrastructure_gap_without_human_reclassification() -> None:
    record, row, review = inputs("Activate the input control.")
    result = current.apply_review(record, row, review, route_evidence(review, pending=True))
    env = result["environment_support"]
    assert env["task_level_acceptance"] == "route_gaps_remain"
    assert env["criterion_routes"]["status_counts"] == {"infrastructure_pending": 1}
    assert env["criterion_routes"]["record_ref"] == "source-bound-common-operation-proof/criteria"
    assert env["generation_vs_evaluation"]["generation"]["status"] == "shared_routes_applicable"
    assert env["generation_vs_evaluation"]["evaluation"]["status"] == "partial_shared_routes"
    assert result["assessment"]["scoring"]["result_status"] == "unconfirmed"


@pytest.mark.parametrize("mutation", ["row", "missing", "duplicate", "unknown", "status", "reason", "generation"])
def test_route_adoption_rejects_unbound_or_incomplete_mapping(mutation: str) -> None:
    record, row, review = inputs("Original task.")
    evidence = route_evidence(review, pending=True)
    mapped = evidence["route_applicability"]["example"]
    if mutation == "row":
        mapped["row_sha256"] = "stale"
    elif mutation == "missing":
        mapped["criteria"] = []
    elif mutation == "duplicate":
        mapped["criteria"] *= 2
    elif mutation == "unknown":
        mapped["criteria"][0]["criterion_id"] = "invented"
    elif mutation == "status":
        mapped["criteria"][0]["status"] = "pass"
    elif mutation == "reason":
        mapped["criteria"][0]["remaining_obligation"] = None
    else:
        mapped["generation"]["status"] = "pass"
    with pytest.raises(ValueError):
        current.apply_review(record, row, review, evidence)
