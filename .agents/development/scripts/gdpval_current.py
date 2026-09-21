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
CORRECTIONS_PATH = ".agents/development/evidence/gdpval-route-corrections-2026-09-21.json"


def generation_status(capabilities: list[dict[str, Any]]) -> str:
    """Only original required operations can contribute a generation route gap."""
    statuses = {
        "shared_route_applicable",
        "partial_shared_route",
        "infrastructure_pending",
        "provisional_human_observation_pending",
        "unconfirmed",
    }
    names: set[str] = set()
    required: list[str] = []
    for capability in capabilities:
        name = capability.get("capability")
        status = capability.get("status")
        if not isinstance(name, str) or not name.strip() or name in names or status not in statuses:
            raise ValueError("generation capability needs a unique name and explicit route status")
        if type(capability.get("required", True)) is not bool:
            raise ValueError("generation requirement level must be an explicit boolean")
        names.add(name)
        if capability.get("required", True):
            required.append(status)
    if not required:
        raise ValueError("generation route must retain its required output operations")
    if all(status == "shared_route_applicable" for status in required):
        return "shared_routes_applicable"
    if any(status in {"shared_route_applicable", "partial_shared_route"} for status in required):
        return "partial_shared_routes"
    return "unconfirmed"


def apply_requirement_correction(
    required: dict[str, Any], review: dict[str, Any], correction: dict[str, Any] | None
) -> dict[str, Any]:
    """Apply an explicit source-bound correction without changing the initial review."""
    corrected = deepcopy(required)
    if correction is None:
        return corrected
    original = required["participant_output"]["capabilities"]
    if (
        correction.get("row_sha256") != review["row_sha256"]
        or correction.get("original_output_capabilities") != original
        or not correction.get("evidence_ref")
    ):
        raise ValueError("requirement correction does not bind the original row and capability list")
    current = correction.get("required_output_capabilities")
    optional = correction.get("optional_output_capabilities", [])
    removed = correction.get("removed_output_capabilities", [])
    for values in (current, optional, removed):
        if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
            raise ValueError("requirement correction needs explicit capability lists")
        if len(values) != len(set(values)):
            raise ValueError("requirement correction repeats a capability")
    if not current or set(current) & set(optional) or set(current) & set(removed) or set(optional) & set(removed):
        raise ValueError("corrected required, optional and removed capabilities must be disjoint")
    if set(current) | set(optional) | set(removed) != set(original):
        raise ValueError(
            "requirement correction must account for the original capabilities without inventing new ones"
        )
    corrected["participant_output"]["capabilities"] = list(current)
    corrected["optional_output_capabilities"] = list(optional)
    corrected["removed_output_capabilities"] = list(removed)
    corrected["correction_basis_ref"] = correction["evidence_ref"]
    return corrected


def validate_route_corrections(
    value: dict[str, Any], reviews: dict[str, dict[str, Any]], source_sha256: str, review_sha256: str
) -> dict[str, dict[str, Any]]:
    """Validate the versioned correction record before using its current requirements."""
    if (
        value.get("schema_version") != 1
        or value.get("kind") != "bounded_requirement_route_corrections"
        or value.get("source_dataset_sha256") != source_sha256
        or value.get("source_review_sha256") != review_sha256
        or not isinstance(value.get("tasks"), dict)
        or not value["tasks"]
    ):
        raise ValueError("route corrections must bind the frozen source and requirements review")
    result: dict[str, dict[str, Any]] = {}
    for task_id, correction in value["tasks"].items():
        if task_id not in reviews or not isinstance(correction, dict):
            raise ValueError("route correction names an unknown task")
        if correction.get("evidence_ref") != f"{CORRECTIONS_PATH}#/tasks/{task_id}":
            raise ValueError("route correction needs its exact evidence reference")
        review = reviews[task_id]
        apply_requirement_correction(review["required_capabilities"], review, correction)
        identifiers = {route[0] for route in review["rubric_routes"]}
        affected = correction.get("affected_criterion_ids")
        if (
            not isinstance(affected, list)
            or not affected
            or not all(isinstance(identifier, str) and identifier in identifiers for identifier in affected)
            or len(set(affected)) != len(affected)
        ):
            raise ValueError("route correction must identify original affected criteria without duplicates")
        result[task_id] = correction
    return result


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
    if "source_input_obligations" in mapped:
        record["task_specific_checks"]["external_data"]["source_input_obligations"] = deepcopy(
            mapped["source_input_obligations"]
        )
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
    capabilities = generation["capabilities"]
    if not isinstance(capabilities, list) or not all(isinstance(capability, dict) for capability in capabilities):
        raise ValueError("generation capabilities must be records")
    if generation["status"] != generation_status(capabilities):
        raise ValueError("generation status must follow required operations; optional checks cannot create gaps")
    required_capabilities = [
        capability["capability"] for capability in capabilities if capability.get("required", True)
    ]
    optional_capabilities = [
        capability["capability"] for capability in capabilities if not capability.get("required", True)
    ]
    if required_capabilities != record["required_capabilities"]["participant_output"][
        "capabilities"
    ] or optional_capabilities != record["required_capabilities"].get("optional_output_capabilities", []):
        raise ValueError("generation operations must match source-bound required and optional capabilities")
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
    correction = evidence.get("route_corrections", {}).get(task_id)
    required = apply_requirement_correction(review["required_capabilities"], review, correction)
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
        "current_route_correction": deepcopy(correction),
    }
    if correction is not None and correction.get("external_data") is not None:
        record["task_specific_checks"]["external_data"] = deepcopy(correction["external_data"])
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
