# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Apply current, source-grounded requirements without turning registration into proof."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from typing import Any, Mapping

REVIEW_PATH = ".agents/development/evidence/gdpval-220-requirements-review.json"
EVIDENCE_PATH = ".agents/development/evidence/gdpval-220-capabilities.json"


def row_hash(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def apply_route_evidence(record: dict[str, Any], review: dict[str, Any], evidence: dict[str, Any]) -> None:
    """Adopt source-bound common operation proofs without inventing artifact observations."""
    mapped = evidence.get("route_applicability", {}).get(review["task_id"])
    if mapped is None:
        return
    if mapped.get("row_sha256") != review["row_sha256"] or not mapped.get("evidence_ref"):
        raise ValueError("route applicability does not bind the original row and evidence")
    expected = {route[0] for route in review["rubric_routes"]}
    criteria = mapped.get("criteria", [])
    if len(criteria) != len(expected) or {item["criterion_id"] for item in criteria} != expected:
        raise ValueError("route applicability must cover all original criteria exactly once")
    statuses = {
        "shared_route_applicable",
        "partial_shared_route",
        "infrastructure_pending",
        "provisional_human_observation_pending",
        "unconfirmed",
    }
    for item in criteria:
        if item.get("status") not in statuses or not item.get("basis_ref") or not item.get("methods"):
            raise ValueError("criterion route needs an explicit status, methods and evidence basis")
        if item["status"] != "shared_route_applicable" and not item.get("remaining_obligation"):
            raise ValueError("pending criterion route needs its remaining obligation")
    generation = mapped.get("generation")
    if (
        not isinstance(generation, dict)
        or generation.get("status") not in {"shared_routes_applicable", "partial_shared_routes", "unconfirmed"}
        or not generation.get("capabilities")
    ):
        raise ValueError("generation route must declare its capabilities and bounded status")
    evaluation_status = (
        "shared_routes_applicable"
        if all(item["status"] == "shared_route_applicable" for item in criteria)
        else "partial_shared_routes"
    )
    environment = record["environment_support"]
    environment["criterion_routes"] = {
        "record_ref": mapped["evidence_ref"] + "/criteria",
        "criterion_count": len(criteria),
        "status_counts": dict(Counter(item["status"] for item in criteria)),
        "actual_artifact_observation_inferred": False,
    }
    environment["route_evidence_ref"] = mapped["evidence_ref"]
    for method in environment["required_evaluation_methods"]:
        relevant = [item for item in criteria if item["criterion_id"] in method["rubric_item_ids"]]
        method["task_criterion_applicability"] = (
            "shared_route_applicable"
            if all(item["status"] == "shared_route_applicable" for item in relevant)
            else "mixed_routes_see_original_criterion_ids"
        )
        method["applicability_basis_ref"] = mapped["evidence_ref"]
        method["legacy_category_is_not_final_method"] = True
    environment["generation_vs_evaluation"] = {
        "generation": {**deepcopy(generation), "evidence_scope": "shared", "task_success_inferred": False},
        "evaluation": {
            "status": evaluation_status,
            "evidence_scope": "shared",
            "actual_artifact_observation_required": True,
            "criterion_routes_ref": "environment_support.criterion_routes",
        },
        "proofs_are_separate": True,
    }
    environment["task_level_acceptance"] = (
        "common_routes_applicable_with_limits"
        if generation["status"] == evaluation_status == "shared_routes_applicable"
        else "route_gaps_remain"
    )
    environment["interpretation"] = (
        "Common route applicability is bounded infrastructure evidence, not a successful participant solution "
        "or completed artifact inspection. Source conflicts, input defects, conditional branches and actual "
        "observations remain separate. Pending operations are not inherently human-only."
    )
    record["assessment"]["inspection_protocol"]["coverage"] = (
        "All original IDs retained; current criterion routes override legacy broad categories. "
        "Actual checks and interpretation remain per-run obligations."
    )
    record["assessment"]["inspection_protocol"]["criterion_routes_ref"] = "environment_support.criterion_routes"


def apply_review(
    record: dict[str, Any], row: dict[str, Any], review: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    """Replace current inferences; retain prior observations under explicit historical pointers."""
    if row["task_id"] != review["task_id"] or row_hash(row) != review["row_sha256"]:
        raise ValueError("requirements review does not bind the original task row")
    task_id = row["task_id"]
    reference = f"{REVIEW_PATH}#/tasks/{review['row_index']}"
    feasibility = review["content_feasibility"]
    feasibility_reference = reference
    addendum = evidence.get("content_feasibility_updates", {}).get(task_id)
    if addendum is not None:
        if addendum.get("source_row_sha256") != review["row_sha256"]:
            raise ValueError("content feasibility addendum does not bind the original task row")
        feasibility = addendum["content_feasibility"]
        feasibility_reference = addendum["evidence_ref"]
    if feasibility["status"] not in {"candidate", "needs_clarification", "undetermined"}:
        raise ValueError("unknown current content feasibility")
    required = deepcopy(review["required_capabilities"])
    routes = review["rubric_routes"]
    identifiers = [route[0] for route in routes]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate criterion routing")
    record["identity"].update(summary=review["summary"], summary_basis=reference)
    record["primary_route"]["content_readiness"] = {
        **deepcopy(feasibility),
        "basis_ref": feasibility_reference,
        "initial_requirements_review_ref": reference,
        "empirical_acceptance": False,
        "historical_membership_ref": record["primary_route"]["content_readiness"]["historical_membership_ref"],
    }
    record["primary_route"]["output_formats"] = required["participant_output"]["modalities"]
    record["primary_route"]["reference_formats"] = [item["format"] for item in required["supplied_read"]]
    record["primary_route"]["artifact_modalities"] = required["participant_output"]["modalities"]
    record["required_capabilities"] = {
        **required,
        "basis_ref": reference,
        "status": "requirements_mapped_not_verified",
    }
    record["task_specific_checks"] = {
        "content_feasibility": deepcopy(feasibility),
        "source_conflicts_and_access_questions": deepcopy(review["conflicts_or_data_access_questions"]),
        "external_data": deepcopy(review["external_data"]),
        "provided_input_staging": deepcopy(
            evidence.get("startup", {}).get(
                task_id, {"status": "unconfirmed", "reason": "No applicable all-input staging receipt attached"}
            )
        ),
        "source_input_uncertainty": deepcopy(evidence.get("source_input_impact", {}).get(task_id)),
        "current_content_addendum": deepcopy(addendum),
    }
    if addendum is not None:
        record["task_specific_checks"]["initial_review_questions"] = deepcopy(
            review["conflicts_or_data_access_questions"]
        )
        record["task_specific_checks"]["source_conflicts_and_access_questions"] = [
            {
                "kind": "provided_content_clarification",
                "detail": feasibility["basis"],
                "criterion_ids": deepcopy(addendum.get("affected_criterion_ids", [])),
                "related_criterion_ids": deepcopy(addendum.get("related_criterion_ids", [])),
                "constraint_location": addendum.get("constraint_location", "identified original criteria"),
                "resolution_status": "needs_clarification",
                "basis_ref": feasibility_reference,
                "originals_preserved": True,
            }
        ]
    common = evidence.get("common_methods", {})
    inspection_plan = evidence.get("inspection_plans", {}).get(task_id)
    methods = sorted({method for route in routes for method in route[2]})
    capability_methods = [
        {
            "method": method,
            "common_evidence": deepcopy(
                common.get(method, {"status": "unconfirmed", "reason": "No current common proof"})
            ),
            "task_criterion_applicability": "unconfirmed",
            "rubric_item_ids": [route[0] for route in routes if method in route[2]],
        }
        for method in methods
    ]
    record["environment_support"] = {
        "common_profile_ref": "gdpval-v2",
        "client_role_support_ref": "common_environment.client_role_support",
        "applicable_roles": ["creation", "application", "evaluation"],
        "required_input_read": deepcopy(required["supplied_read"]),
        "required_output_authoring": deepcopy(required["participant_output"]),
        "required_evaluation_methods": capability_methods,
        "known_unsupported": [],
        "generation_vs_evaluation": {
            "generation": {"status": "unverified", "evidence_scope": "unconfirmed"},
            "evaluation": {
                "status": "unverified",
                "evidence_scope": "unconfirmed",
                "actual_artifact_observation_required": True,
            },
            "proofs_are_separate": True,
        },
        "task_level_acceptance": "unverified",
        "interpretation": "Missing task evidence is unverified. Input STEP/media or occupational vocabulary does not imply output authoring or permanent unsupported status.",
    }
    prior_trials = record["assessment"]["task_verification"]
    record["assessment"] = {
        "original_rubric": {
            "source_row_sha256": review["row_sha256"],
            "criterion_ids": identifiers,
            "signed_scores": [route[1] for route in routes],
            "meaning_changed": False,
        },
        "inspection_protocol": {
            "requirements_ref": reference + "/rubric_routes",
            "coverage": "all original criterion IDs; proposed routes require applicable verification",
            "required_methods": capability_methods,
            "equivalent_to_official_grading": "unconfirmed_custom_evaluation",
            "generated_plan": deepcopy(inspection_plan),
        },
        "optional_domain_escalation": deepcopy(review["human_domain_review"]),
        "scoring": {"criterion_source": reference, "criterion_count": len(routes), "result_status": "unconfirmed"},
        "task_verification": prior_trials,
        "current_trials": deepcopy(evidence.get("task_trials", {}).get(task_id, [])),
        "available_vs_viewed": {"available": "see common method evidence", "viewed_or_performed": "not inferred"},
        "unknown_is_not_zero_pass_or_failure": True,
    }
    record["evidence_version"]["current_requirements_review"] = reference
    record["evidence_version"]["current_capability_evidence"] = EVIDENCE_PATH
    record["evidence_version"]["environment"]["profile_ref"] = "gdpval-v2"
    record["acceptance_scope"] = {
        "status": "included",
        "reason": "Owner authorized all 220 original tasks; completion depends on applicable evidence.",
        "fixed_acceptance_order": 1
        if task_id == "9e39df84-ac57-4c9b-a2e3-12b8abf2c797"
        else 2
        if task_id == "5d0feb24-e8b6-4ace-b64f-d5cd1a8b563d"
        else None,
    }
    apply_route_evidence(record, review, evidence)
    return record
