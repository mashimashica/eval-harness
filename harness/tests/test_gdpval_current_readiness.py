# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import importlib.util
import json
from copy import deepcopy
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
                    "capabilities": [
                        {
                            "capability": "pdf_author",
                            "status": "shared_route_applicable",
                            "basis_ref": "known-pdf-authoring-proof",
                        }
                    ],
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


def requirement_correction(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_sha256": review["row_sha256"],
        "evidence_ref": current.CORRECTIONS_PATH + "#/tasks/example",
        "original_output_capabilities": list(review["required_capabilities"]["participant_output"]["capabilities"]),
        "required_output_capabilities": ["pdf_author"],
        "optional_output_capabilities": ["endpoint_execution"],
        "removed_output_capabilities": [],
        "affected_criterion_ids": ["original-id"],
    }


def test_optional_endpoint_absence_does_not_block_required_source_instructions() -> None:
    record, row, review = inputs("Write a query and concrete instructions to execute it.")
    review["required_capabilities"]["participant_output"]["capabilities"].append("endpoint_execution")
    initial_review = deepcopy(review)
    correction = requirement_correction(review)
    correction["external_data"] = {"constraint": "Endpoint execution is optional."}
    evidence = route_evidence(review)
    evidence["route_corrections"] = {"example": correction}
    evidence["route_applicability"]["example"]["generation"]["capabilities"].append(
        {
            "capability": "endpoint_execution",
            "status": "infrastructure_pending",
            "required": False,
            "basis_ref": correction["evidence_ref"],
            "remaining_obligation": "Optional endpoint execution has not been performed.",
        }
    )
    result = current.apply_review(record, row, review, evidence)
    assert result["environment_support"]["task_level_acceptance"] == "common_routes_applicable_with_limits"
    assert result["environment_support"]["required_output_authoring"]["capabilities"] == ["pdf_author"]
    assert result["required_capabilities"]["optional_output_capabilities"] == ["endpoint_execution"]
    assert result["task_specific_checks"]["external_data"] == correction["external_data"]
    assert result["assessment"]["scoring"]["result_status"] == "unconfirmed"
    assert review == initial_review


def test_available_optional_operation_cannot_hide_required_operation_gap() -> None:
    assert (
        current.generation_status(
            [
                {"capability": "native_required", "status": "infrastructure_pending"},
                {"capability": "optional_read", "status": "shared_route_applicable", "required": False},
            ]
        )
        == "unconfirmed"
    )


@pytest.mark.parametrize("mutation", ["unbound_optional", "missing_required", "wrong_summary", "not_boolean"])
def test_generation_summary_cannot_silently_reclassify_required_operations(mutation: str) -> None:
    record, row, review = inputs("An actual required operation.")
    evidence = route_evidence(review)
    generation = evidence["route_applicability"]["example"]["generation"]
    if mutation == "unbound_optional":
        generation["capabilities"].append(
            {"capability": "unreviewed", "status": "infrastructure_pending", "required": False}
        )
    elif mutation == "missing_required":
        generation["capabilities"][0]["required"] = False
    elif mutation == "wrong_summary":
        generation["capabilities"][0]["status"] = "infrastructure_pending"
    else:
        generation["capabilities"][0]["required"] = "false"
    with pytest.raises(ValueError):
        current.apply_review(record, row, review, evidence)


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "review",
        "row",
        "original_capabilities",
        "invented_capability",
        "duplicate",
        "overlap",
        "criterion",
        "ref",
    ],
)
def test_correction_loader_rejects_stale_or_unbound_source(mutation: str) -> None:
    _, _, review = inputs("Original task.")
    review["required_capabilities"]["participant_output"]["capabilities"].append("endpoint_execution")
    correction = requirement_correction(review)
    value = {
        "schema_version": 1,
        "kind": "bounded_requirement_route_corrections",
        "source_dataset_sha256": "source-hash",
        "source_review_sha256": "review-hash",
        "tasks": {"example": correction},
    }
    if mutation == "source":
        value["source_dataset_sha256"] = "stale"
    elif mutation == "review":
        value["source_review_sha256"] = "stale"
    elif mutation == "row":
        correction["row_sha256"] = "stale"
    elif mutation == "original_capabilities":
        correction["original_output_capabilities"] = ["pdf_author"]
    elif mutation == "invented_capability":
        correction["required_output_capabilities"] = ["invented"]
    elif mutation == "duplicate":
        correction["optional_output_capabilities"] *= 2
    elif mutation == "overlap":
        correction["required_output_capabilities"].append("endpoint_execution")
    elif mutation == "criterion":
        correction["affected_criterion_ids"] = ["invented"]
    else:
        correction["evidence_ref"] = "unbound"
    with pytest.raises(ValueError):
        current.validate_route_corrections(value, {"example": review}, "source-hash", "review-hash")


@pytest.fixture(scope="module")
def corrected_routes() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    evidence = SCRIPT.parents[1] / "evidence"
    corrections = json.loads((evidence / "gdpval-route-corrections-2026-09-21.json").read_text())
    routes = json.loads((evidence / "gdpval-220-route-applicability.json").read_text())
    reviews = {
        task["task_id"]: task
        for task in json.loads((evidence / "gdpval-220-requirements-review.json").read_text())["tasks"]
    }
    return corrections, routes, reviews


def test_tracked_correction_binds_unchanged_source_units_and_review(
    corrected_routes: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    corrections, routes, reviews = corrected_routes
    evidence = SCRIPT.parents[1] / "evidence"
    review_bytes = (evidence / "gdpval-220-requirements-review.json").read_bytes()
    source_hash = json.loads(review_bytes)["source"]["sha256"]
    adopted = current.validate_route_corrections(
        corrections, reviews, source_hash, hashlib.sha256(review_bytes).hexdigest()
    )
    assert len(adopted) == 13
    assert routes["requirement_corrections"] == {
        "path": current.CORRECTIONS_PATH,
        "sha256": hashlib.sha256((evidence / "gdpval-route-corrections-2026-09-21.json").read_bytes()).hexdigest(),
    }
    for task_id, correction in adopted.items():
        scores = {item[0]: item[1] for item in reviews[task_id]["rubric_routes"]}
        for item in correction["criterion_evidence"]:
            assert scores[item["criterion_id"]] == item["original_signed_score"]
        assert routes["tasks"][task_id]["row_sha256"] == correction["row_sha256"]


def test_static_forms_preserve_required_layout_and_source_operations(
    corrected_routes: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    corrections, routes, reviews = corrected_routes
    forms = {task_id for task_id, task in corrections["tasks"].items() if task["finding_id"] == "R1"}
    assert len(forms) == 9
    for task_id in forms:
        caps = routes["tasks"][task_id]["generation"]["capabilities"]
        form = next(cap for cap in caps if cap["capability"] == "pdf_form_layout")
        assert form["status"] == "shared_route_applicable"
        assert form["remaining_obligation"]
        assert form.get("required", True) is True
        assert "browser_widget_ui" not in form["route_ids"]
        assert (
            corrections["tasks"][task_id]["required_output_capabilities"]
            == reviews[task_id]["required_capabilities"]["participant_output"]["capabilities"]
        )


def test_office_form_layout_preserves_active_input_and_native_gates(
    corrected_routes: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    _, routes, reviews = corrected_routes
    correction = routes["form_layout_source_correction"]
    assert correction["classification_only"] is True
    assert correction["new_operation_proofs"] == 0
    assert len(correction["tasks"]) == 7
    pending_tasks = {
        "4d61a19a-8438-4d4c-9fc2-cf167e36dcd6",
        "41f6ef59-88c9-4b2c-bcc7-9ceb88422f48",
        "a0552909-bc66-4a3a-8970-ee0d17b49718",
    }
    pending_items = 0
    for task_id, source in correction["tasks"].items():
        task = routes["tasks"][task_id]
        form = next(c for c in task["generation"]["capabilities"] if c["capability"] == "form_layout")
        assert form["status"] == "shared_route_applicable"
        assert form["route_ids"] == ["office_authoring", "page_render_and_transport"]
        assert source["row_sha256"] == task["row_sha256"] == reviews[task_id]["row_sha256"]
        criteria = {item["criterion_id"]: item for item in task["criteria"]}
        for gate in source["existing_native_gates_unchanged"]:
            assert criteria[gate["criterion_id"]] == gate
            assert gate["status"] == "infrastructure_pending"
            assert "functional" in gate["methods"]
            pending_items += 1
        record = {
            "required_capabilities": deepcopy(reviews[task_id]["required_capabilities"]),
            "environment_support": {"required_evaluation_methods": []},
            "assessment": {"inspection_protocol": {}},
        }
        current.apply_route_evidence(record, reviews[task_id], {"route_applicability": routes["tasks"]})
        expected = "route_gaps_remain" if task_id in pending_tasks else "common_routes_applicable_with_limits"
        assert record["environment_support"]["task_level_acceptance"] == expected
        assert record["environment_support"]["criterion_routes"]["actual_artifact_observation_inferred"] is False
    assert pending_items == 8
    pathology = routes["tasks"]["a0552909-bc66-4a3a-8970-ee0d17b49718"]
    controls = next(
        c
        for c in pathology["generation"]["capabilities"]
        if c["capability"] == "spreadsheet_input_controls_and_behavior"
    )
    assert controls["status"] == "partial_shared_route"
    outreach = routes["tasks"]["41f6ef59-88c9-4b2c-bcc7-9ceb88422f48"]
    table_or_filter = next(
        c for c in outreach["criteria"] if c["criterion_id"] == "53b88dce-5f98-426f-aa59-86e53a232351"
    )
    assert table_or_filter["alternative_ref"].endswith("/machine_alternative")


@pytest.mark.parametrize(
    "task_id",
    ["43dc9778-450b-4b46-b77e-b6d82b202035", "e6429658-4de1-42dd-a9e0-2d2b9b02fb10"],
)
def test_shared_form_retrieval_preserves_unconfirmed_source_requirements(
    corrected_routes: tuple[dict[str, Any], dict[str, Any], dict[str, Any]], task_id: str
) -> None:
    _, routes, reviews = corrected_routes
    mapped = routes["tasks"][task_id]
    review = reviews[task_id]
    original_external = deepcopy(review["external_data"])
    record = {
        "required_capabilities": deepcopy(review["required_capabilities"]),
        "environment_support": {"required_evaluation_methods": []},
        "assessment": {"inspection_protocol": {}},
        "task_specific_checks": {
            "content_feasibility": deepcopy(review["content_feasibility"]),
            "external_data": deepcopy(original_external),
            "source_input_uncertainty": {"existing_fixture_issue": "unconfirmed"},
        },
    }
    current.apply_route_evidence(record, review, {"route_applicability": routes["tasks"]})
    acquisition = next(
        c for c in mapped["generation"]["capabilities"] if c["capability"] == "official_form_acquisition"
    )
    assert acquisition["status"] == "shared_route_applicable"
    assert acquisition["route_ids"] == ["public_source_access"]
    checks = record["task_specific_checks"]
    obligations = checks["external_data"].pop("source_input_obligations")
    assert checks["external_data"] == original_external
    assert obligations == mapped["source_input_obligations"]
    assert obligations["status"] == "unconfirmed"
    assert obligations["participant_retrieval_required"] is True
    assert obligations["exact_source_fetched_in_this_review"] is False
    assert obligations["task_success_inferred"] is False
    assert set(obligations["criterion_ids"]) <= {item[0] for item in review["rubric_routes"]}
    if task_id.startswith("43dc"):
        assert obligations["required_source"]["tax_year"] == 2024
    else:
        assert obligations["required_source"]["url"] in original_external["source_urls_in_prompt"]
        assert obligations["required_source"]["archived_edition_explicitly_named"] is False
    assert checks["content_feasibility"] == review["content_feasibility"]
    assert checks["source_input_uncertainty"] == {"existing_fixture_issue": "unconfirmed"}
    assert review["external_data"] == original_external
    obligations["status"] = "changed_in_generated_copy"
    assert mapped["source_input_obligations"]["status"] == "unconfirmed"


def test_notebook_only_actual_interface_item_retains_browser_requirement(
    corrected_routes: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    corrections, routes, _ = corrected_routes
    task_id = "c7d83f01-2874-4876-b7fd-52582ec99e1a"
    task = routes["tasks"][task_id]
    criteria = {item["criterion_id"]: item for item in task["criteria"]}
    assert {item["criterion_id"] for item in criteria.values() if "browser_widget_ui" in item["route_ids"]} == {
        "ec4b8d47-73fe-46e9-b01e-0e0a4b569f0c"
    }
    assert task["generation"]["status"] == "partial_shared_routes"
    changed = corrections["tasks"][task_id]["criterion_route_corrections"]
    assert len(changed) == 29
    for source in changed:
        item = criteria[source["criterion_id"]]
        assert item["status"] == "shared_route_applicable"
        assert item["methods"] == source["current_methods"]
        assert item["original_signed_score"] == source["original_signed_score"]
        assert item["original_item_sha256"] == source["original_item_sha256"]
        assert "fresh_inprocess_kernel" in item["route_ids"]
    assert "functional" in criteria["aad3a219-1411-4ebe-978b-913e48f83ef6"]["methods"]  # fixed RNG seed
    assert "functional" in criteria["ca9d31a9-9aed-4291-adec-9907ca4c48d0"]["methods"]  # early exercise


def test_supplied_gmp_form_and_optional_overpass_are_source_bound(
    corrected_routes: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    corrections, routes, reviews = corrected_routes
    for task_id, removed, optional in [
        ("58ac1cc5-5754-4580-8c9c-8c67e1a9d619", ["official_form_acquisition"], []),
        ("854f3814-681c-4950-91ac-55b0db0e3781", [], ["bounded_query_validation"]),
    ]:
        review = reviews[task_id]
        corrected = current.apply_requirement_correction(
            review["required_capabilities"], review, corrections["tasks"][task_id]
        )
        assert corrected["removed_output_capabilities"] == removed
        assert corrected["optional_output_capabilities"] == optional
        assert corrected["supplied_read"] == review["required_capabilities"]["supplied_read"]
        assert routes["tasks"][task_id]["generation"]["status"] == "shared_routes_applicable"
        assert current.generation_status(routes["tasks"][task_id]["generation"]["capabilities"]) == (
            "shared_routes_applicable"
        )
    task = routes["tasks"]["854f3814-681c-4950-91ac-55b0db0e3781"]
    instructions = next(c for c in task["criteria"] if c["criterion_id"] == "5e9003e6-697d-4017-b404-ec497a165fce")
    assert instructions["methods"] == ["content"]
    optional_cap = next(c for c in task["generation"]["capabilities"] if c["capability"] == "bounded_query_validation")
    assert optional_cap["required"] is False
    assert optional_cap["status"] == "partial_shared_route"


def test_pdf_and_word_embedding_require_separate_operation_proofs(
    corrected_routes: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    corrections, routes, _ = corrected_routes
    iem = routes["tasks"]["99ac6944-4ec6-4848-959c-a460ac705c6f"]
    pdf_cap = next(c for c in iem["generation"]["capabilities"] if c["capability"] == "document_image_embedding")
    assert pdf_cap["status"] == "shared_route_applicable"
    assert "pdf_png_embedding" in pdf_cap["route_ids"]
    assert routes["route_catalog"]["pdf_png_embedding"]["proof_refs"] == [corrections["operation_proof_addendum"]]
    word_id = "bb499d9c-0263-4684-9238-75e8e86077b1"
    assert word_id not in corrections["tasks"]
    word = routes["tasks"][word_id]
    word_cap = next(c for c in word["generation"]["capabilities"] if c["capability"] == "word_diagram_embedding")
    assert word_cap["status"] == "shared_route_applicable"
    assert word_cap["route_ids"] == ["word_image_text_roundtrip"]
    assert "pdf_png_embedding" not in word_cap["route_ids"]
    accepted = json.loads((SCRIPT.parents[1] / "evidence/gdpval-document-operations-2026-09-22.json").read_text())
    adoption = routes["common_document_operation_adoption"]
    word_route = routes["route_catalog"]["word_image_text_roundtrip"]
    assert adoption["proof_ref"] == accepted["proof"]
    assert accepted["proof"] in word_route["proof_refs"]
    assert accepted["controller_visual_review"] in word_route["proof_refs"]
    assert corrections["operation_proof_addendum"] not in word_route["proof_refs"]
    assert adoption["tasks"][word_id]["row_sha256"] == word["row_sha256"]
    assert set(adoption["tasks"][word_id]["criteria"]) == set(accepted["affected_task_item_components"][word_id])
