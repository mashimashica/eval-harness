# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Generate evaluator-only GDPval rubric copies and conservative inspection drafts.

Usage: python gdpval_inspection_plan.py --source public-tasks.jsonl
    --source-sha256 SHA256 --review gdpval-220-requirements-review.json
    --out NEW_DIRECTORY [--human-reviewer 'Assigned reviewer name']
    [--human-coordination-owner 'Assignment coordinator']
    [--routing-review gdpval-239-observation-routes.json]
    [--code-routing-review gdpval-143-code-routes.json]

No candidate artifacts are inspected or executed. A generated protocol is a
configuration draft, not proof of criterion applicability, capability or success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

TASK_COUNT = 220
CRITERION_COUNT = 10453
VERSION = "gdpval-inspection-draft-v1"
REVIEWED_VERSION = "gdpval-inspection-reviewed-routes-v2"
CODE_REVIEWED_VERSION = "gdpval-inspection-reviewed-code-routes-v2"
CODE_TASK_CRITERION_COUNTS = {
    "0e386e32-df20-4d1f-b536-7159bc409ad5": 55,
    "4122f866-01fa-400b-904d-fa171cdab7c7": 65,
    "854f3814-681c-4950-91ac-55b0db0e3781": 23,
}
CODE_BEHAVIOR_FORMS = {"runtime_behavior", "explicit_executed_test", "optional_component_behavior"}
CODE_STATIC_FORMS = {
    "source_or_artifact",
    "documentation_or_configuration",
    "source_or_archive",
    "documentation",
    "query_source",
}
RUNTIME_METHODS = {"content", "structure", "visual", "functional", "research", "human"}
LEGACY_ROUTES = {
    "structure": "structure",
    "text/content": "content",
    "visual": "visual",
    "spreadsheet_recalc": "functional",
    "interactive_execution": "functional",
    "source_comparison": "research",
    "CAD_geometry": "functional",
    "audio_listen": "human",
    "video_temporal": "human",
    "native_app": "human",
}
SCIENCE_IDS = {
    "42a88af8-d5f8-4de9-af05-5911589c1a5c",
    "1b0e95d5-8151-4324-a079-5c3f91e16cb6",
}
PIVOT_PRESENCE_ID = "9890a9ff-5bb3-4998-9e3d-b561d630a95f"
DASHBOARD_TASK_ID = "9e39df84-ac57-4c9b-a2e3-12b8abf2c797"
DASHBOARD_FUNCTIONAL_IDS = {
    "3293cf5b-3041-455c-98ca-300a6c5e2e68",
    "67856dee-3cf4-4e2e-a023-683ec7a0edc4",
    "feed5a55-59e7-43dc-9cfc-d5be53a04780",
    "7a04bbe7-cc07-49ee-bc67-c972635649c0",
    "a7c98919-f78d-497b-a82e-0b619385ba87",
}
SCIENCE_TASK_ID = "5d0feb24-e8b6-4ace-b64f-d5cd1a8b563d"
SCIENCE_NATIVE_UI_IDS = {"cb64c7ad-0d67-4bbc-9686-1816fc3fa9ca", "10005343-81dc-4912-93a7-09389f9768d1"}
SCIENCE_STRUCTURAL_IDS = {
    "7b7c25cb-ae79-4734-8b22-f63f4a4d3702": ["structure"],
    "1f122410-2ced-4c2e-bf53-e8cc64a9f6c8": ["structure"],
    "7a42d49d-482e-4ab5-bdf3-74cd6da5cd95": ["structure", "text/content"],
    "ca14779c-1523-43da-addf-427783844b60": ["structure", "text/content"],
}
DRAFT_LIMIT = (
    "Conservative draft procedures: confirm criterion applicability and the chosen original branch before use. "
    "Complete ID coverage does not establish that every route is correct or any inspection path is verified."
)
BRANCH_PROCEDURE = (
    "Read the complete unchanged original criterion below in the frozen task context. Preserve every If clause, "
    "alternative, example, exception, optional suggestion, tolerance and negative predicate. Identify the applicable "
    "branch from observed evidence; do not require all alternatives or turn an optional suggestion into a requirement. "
    "If applicability cannot be established, leave the item unconfirmed."
)
PROVENANCE_LIMIT = (
    "A recorded tool call, file hash or citation proves provenance only. It does not prove source authority, "
    "scientific truth, meaningful input perturbation, observation accuracy or satisfaction of this criterion."
)
SHELL_PROCEDURE = (
    "For shell inspection, emit schema_version:1, source_artifacts:[{path,sha256}], "
    "checks:[{action,observation}] as one captured JSON object. Bind the unchanged inspected files and record "
    "actual checks and observations with precise locations. Cite the returned captured_stdout_path or "
    "captured_stderr_path, its SHA256 and call_id; never derive the captured path from call_id."
)
METHOD_PROCEDURES = {
    "text/content": (
        "Read the complete relevant artifact text, code or table values using shell, including the surrounding "
        "context and the applicable original clause. Record actual passages, lines or cells; a filename, summary "
        "or claim of having read the file is insufficient."
    ),
    "structure": (
        "Inspect actual artifact bytes and structure with inspect_document or shell. Record relevant package "
        "members, native object definitions, relationships, sheet names, counts or headers and their locations. "
        "Structural presence alone does not establish native application behavior or rendered appearance."
    ),
    "visual": (
        "Render and view the complete relevant pages, slides, images or charts, at readable scale with context. "
        "Record source hashes, render/view call IDs and page or region locations. Text extraction, XML and a "
        "description of an image cannot establish appearance."
    ),
    "spreadsheet_recalc": (
        "Inspect live formulas and input cells, recalculate or independently recompute the relevant results, "
        "and compare observed values with independently expected values. Where the original branch claims "
        "updates or formula effects, change relevant inputs on an inspection copy, record original and changed "
        "inputs, actual observed outputs before and after, expected outputs and the calculation engine. "
        "Cached values, formula presence or a shell success flag alone do not establish dynamic behavior."
    ),
    "interactive_execution": (
        "Under the already verified isolation, exercise the actual artifact behavior required by the chosen "
        "branch. Record the engine, action, concrete changed inputs, observed outputs before and after, and "
        "independently expected effects. Merely executing a shell or describing an interaction is insufficient. "
        "Do not demand executable software when the original accepts a static specification or report."
    ),
    "CAD_geometry": (
        "Load the actual required STEP files with a compatible geometry reader and inspect geometry, components "
        "and assembly relationships relevant to the original clause. Record file hashes, successful import, "
        "measured quantities and comparisons with supplied references. A filename or drawing screenshot alone "
        "does not establish geometry. A supplied STEP input does not imply a new STEP deliverable."
    ),
    "source_comparison": (
        "Compare the relevant submission passages, values or structure against the original prompt and the "
        "applicable frozen supplied sources or original baseline. A pure supplied-source comparison needs no "
        "external fetch: shell may bind both submission and supplied-source paths and hashes in its inspection "
        "record, with exact comparison locations. Use actual authoritative external source content only when "
        "the original predicate requires external facts; retain source URL, version/date and fetched bytes. "
        "If a needed prompt/source has no captured provenance or is inaccessible, leave the item unconfirmed. "
        "Matching unchanged wording establishes wording preservation, not factual or scientific accuracy."
    ),
    "audio_listen": (
        "The named human reviewer must decode and listen to the actual relevant audio over the necessary "
        "intervals, compare reference audio when required and record time locations and observations. Headers, "
        "transcripts, waveforms and CLI completion cannot stand in for required listening."
    ),
    "video_temporal": (
        "The named human reviewer must play the actual video over the required duration, inspect motion, "
        "temporal continuity and synchronization as applicable, and record time locations and observations. "
        "Still frames or a report describing a video do not establish temporal playback."
    ),
    "native_app": (
        "The named human reviewer must open the actual artifact in the compatible application and perform "
        "the native operation required by the applicable original clause, recording application/version, "
        "actions and observed results. Exercise native controls or Word hyperlinks when their behavior is "
        "claimed; package XML cannot establish clicking, repair-free opening or native UI behavior."
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    return digest(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def rubric(row: dict[str, Any]) -> list[dict[str, Any]]:
    value = row.get("rubric_json")
    if not isinstance(value, str):
        raise ValueError("source rubric_json must contain the original JSON string")
    items = json.loads(value)
    if not isinstance(items, list) or not items:
        raise ValueError("source rubric must be a nonempty list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items:
        item = _object(raw, "source criterion")
        identifier, description, score = item.get("rubric_item_id"), item.get("criterion"), item.get("score")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen or not _text(description):
            raise ValueError("source criterion IDs must be unique with unchanged nonempty descriptions")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError("original signed scores must be finite numbers")
        seen.add(identifier)
        result.append(item)
    return result


def validate_inputs(source_bytes: bytes, source_sha256: str, review: dict[str, Any]) -> list[dict[str, Any]]:
    """Reject source drift, incomplete coverage and stale requirement routes."""
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256) or digest(source_bytes) != source_sha256:
        raise ValueError("source SHA256 mismatch")
    if review.get("schema_version") != 1 or review.get("source", {}).get("sha256") != source_sha256:
        raise ValueError("review does not bind the supplied source SHA256")
    lines = source_bytes.splitlines()
    rows = [_object(json.loads(line), "source row") for line in lines]
    tasks = review.get("tasks")
    if not isinstance(tasks, list) or len(rows) != TASK_COUNT or len(tasks) != TASK_COUNT:
        raise ValueError(f"source and review must cover exactly {TASK_COUNT} tasks")
    seen_tasks: set[str] = set()
    count = 0
    for index, (row, line, raw_task) in enumerate(zip(rows, lines, tasks, strict=True)):
        task = _object(raw_task, "review task")
        task_id = row.get("task_id")
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", task_id) or task_id in seen_tasks:
            raise ValueError("source task IDs must be unique and safe directory names")
        seen_tasks.add(task_id)
        if (
            task.get("task_id") != task_id
            or task.get("row_index") != index
            or task.get("row_sha256") != canonical_hash(row)
            or task.get("raw_line_sha256") != digest(line)
            or task.get("inclusion") != "in_scope"
        ):
            raise ValueError(f"review row identity mismatch: {task_id}")
        original = rubric(row)
        routes = task.get("rubric_routes")
        if not isinstance(routes, list) or len(routes) != len(original):
            raise ValueError(f"review criterion coverage mismatch: {task_id}")
        for item, route in zip(original, routes, strict=True):
            if (
                not isinstance(route, list)
                or len(route) != 4
                or route[0] != item["rubric_item_id"]
                or type(route[1]) is not type(item["score"])
                or route[1] != item["score"]
                or not isinstance(route[2], list)
                or not route[2]
                or not all(isinstance(method, str) and method in LEGACY_ROUTES for method in route[2])
                or len(route[2]) != len(set(route[2]))
                or not isinstance(route[3], bool)
            ):
                raise ValueError(f"review criterion ID, signed score or route mismatch: {task_id}")
        optional = task.get("human_domain_review", {})
        ids = {item["rubric_item_id"] for item in original}
        if (
            not isinstance(optional, dict)
            or optional.get("route_status") != "optional_candidate_escalation"
            or optional.get("mandatory_human_criterion_ids") != []
            or not set(optional.get("rubric_item_ids", [])) <= ids
        ):
            raise ValueError("human_domain_review must remain optional candidate escalation")
        for conflict in task.get("conflicts_or_data_access_questions", []):
            if not isinstance(conflict, dict) or not set(conflict.get("criterion_ids", [])) <= ids:
                raise ValueError("review conflict references unknown original criteria")
        count += len(original)
    if count != CRITERION_COUNT:
        raise ValueError(f"source and review must cover exactly {CRITERION_COUNT} criteria")
    return rows


def _procedures(
    item: dict[str, Any], task: dict[str, Any], route: list[Any]
) -> tuple[list[str], list[str], list[str]]:
    categories: list[str] = list(route[2])
    overrides: list[str] = []
    identifier = item["rubric_item_id"]
    if identifier in SCIENCE_IDS:
        if "source_comparison" not in categories:
            categories.append("source_comparison")
        overrides.append("controller_scientific_accuracy_requires_authoritative_comparison")
    if identifier == PIVOT_PRESENCE_ID:
        categories = ["structure"]
        overrides.append("controller_native_pivot_presence_is_structural_not_ui_behavior")
    if task["task_id"] == SCIENCE_TASK_ID and "native_app" in categories and identifier not in SCIENCE_NATIVE_UI_IDS:
        categories = SCIENCE_STRUCTURAL_IDS.get(
            identifier, [category for category in categories if category != "native_app"]
        )
        overrides.append("controller_word_xml_presence_is_inspectable_without_native_ui")
    if task["task_id"] == DASHBOARD_TASK_ID and identifier in DASHBOARD_FUNCTIONAL_IDS:
        categories = [category for category in categories if category != "native_app"]
        if "spreadsheet_recalc" not in categories:
            categories.append("spreadsheet_recalc")
        if identifier == "a7c98919-f78d-497b-a82e-0b619385ba87" and "visual" not in categories:
            categories.append("visual")
        overrides.append("controller_dashboard_outputs_require_functional_observation")
    procedures = [BRANCH_PROCEDURE, *[METHOD_PROCEDURES[category] for category in categories]]
    if identifier in SCIENCE_IDS:
        procedures.append(
            "For this scientific-accuracy criterion, actually compare the relevant scientific claims and simplified "
            "explanations against authoritative primary source content, including the supplied study if it covers "
            "the claim. Record exact source and submission locations, source identity/version and the comparison. "
            "Wording preservation, readability, structural inspection or an authoritative-looking link alone "
            "is insufficient; unavailable or conflicting scientific evidence leaves the accuracy branch unconfirmed."
        )
    if task["task_id"] == DASHBOARD_TASK_ID and any(
        LEGACY_ROUTES[category] == "functional" for category in categories
    ):
        procedures.append(
            "For Dashboard selected-week, selected-range, update or formula-effect claims, use an inspection copy "
            "and exercise different relevant weeks/inputs. Record selected values and changed source cells, actual "
            "before/after PivotTable, chart or KPI outputs, and independent expected values. Native PivotTable "
            "presence alone is insufficient. If native controls cannot be exercised, keep that branch unconfirmed "
            "until the named human reviewer supplies the required observations."
        )
    return categories, procedures, overrides


def criterion_plan(
    item: dict[str, Any],
    task: dict[str, Any],
    route: list[Any],
    reviewer: str | None,
    coordination_owner: str | None = None,
) -> dict[str, Any]:
    categories, procedures, overrides = _procedures(item, task, route)
    methods = list(dict.fromkeys(LEGACY_ROUTES[category] for category in categories))
    human_categories = [category for category in categories if LEGACY_ROUTES[category] == "human"]
    conditions = [
        "Unconfirmed until criterion applicability and the chosen original branch have been established. "
        + DRAFT_LIMIT,
        "Unconfirmed if any required observation, source, method, location, hash or recorded receipt is missing, "
        "stale, inaccessible or insufficient for the complete applicable original predicate.",
        *["Unconfirmed until this necessary procedure is completed: " + procedure for procedure in procedures[1:]],
        PROVENANCE_LIMIT,
    ]
    conflicts = [
        conflict["detail"]
        for conflict in task.get("conflicts_or_data_access_questions", [])
        if item["rubric_item_id"] in conflict["criterion_ids"]
    ]
    conditions.extend(
        "Unconfirmed while this original instruction/access question remains unresolved: " + c for c in conflicts
    )
    inference: dict[str, Any] | None = None
    # Review permission cannot replace observation for an inherently direct route.
    if route[3] and set(categories) <= {"structure", "text/content", "source_comparison"}:
        inference = {
            "required_methods": methods,
            "description": (
                "Source-grounded interpretation of the complete observed static predicate is permitted after all "
                "listed methods and comparisons. Preserve every original conditional branch and tolerance. "
                "Do not infer appearance, execution, native behavior, media perception or scientific accuracy "
                "from names, descriptions, unchanged wording or citation existence. "
                + (procedures[-1] if item["rubric_item_id"] in SCIENCE_IDS else "")
            ).strip(),
        }
    human: dict[str, Any] | None = None
    if human_categories:
        human = {
            "reviewer": reviewer,
            "procedure": (
                DRAFT_LIMIT
                + " "
                + " ".join(procedures)
                + " "
                + SHELL_PROCEDURE
                + " "
                + PROVENANCE_LIMIT
                + " Complete a separate human receipt bound to the original criterion, protocol and artifact hashes, "
                "named reviewer, this procedure, observations, decision and completion time. Assignment alone is "
                "not a completed observation or automatic pass."
            ),
        }
        if reviewer is None and coordination_owner is not None:
            human["coordination_owner"] = coordination_owner
        conditions.append("Unconfirmed without a separately supplied, completed and identity-matching human receipt.")
    optional = task.get("human_domain_review", {})
    optional_escalation = (
        {
            "status": "optional_candidate_escalation",
            "candidate_role": optional.get("candidate_role"),
            "judgment_scope": optional.get("judgment_scope"),
            "assignment": None,
        }
        if item["rubric_item_id"] in optional.get("rubric_item_ids", [])
        else None
    )
    rule = {
        "required_methods": ["human"] if human_categories else methods,
        "acceptable_inference": None if human_categories else inference,
        "unconfirmed_conditions": [BRANCH_PROCEDURE, *conditions],
        "human_review": human,
    }
    return {
        "criterion_id": item["rubric_item_id"],
        "original_description": item["criterion"],
        "original_item_sha256": canonical_hash(item),
        "review_categories": route[2],
        "effective_categories": categories,
        "review_stable_inference_allowed": route[3],
        "controller_overrides": overrides,
        "necessary_evidence_methods": methods,
        "procedure": [BRANCH_PROCEDURE, *procedures[1:], SHELL_PROCEDURE, PROVENANCE_LIMIT],
        "human_handoff_categories": human_categories,
        "optional_expert_escalation": optional_escalation,
        "runtime_rule_candidate": rule,
    }


def validate_routing_review(
    value: dict[str, Any], rows: list[dict[str, Any]], review: dict[str, Any], source_hash: str, review_hash: str
) -> dict[str, dict[str, dict[str, Any]]]:
    """Bind each replacement to exactly the original provisional-human population."""
    if (
        value.get("schema_version") != 1
        or value.get("source_dataset_sha256") != source_hash
        or value.get("source_review_sha256") != review_hash
    ):
        raise ValueError("routing review source/review hash mismatch")
    catalog = _object(value.get("route_catalog"), "routing review route_catalog")
    entries = value.get("items")
    if not isinstance(entries, list):
        raise ValueError("routing review items must be a list")
    expected = {}
    for row, task in zip(rows, review["tasks"], strict=True):
        for original, route in zip(rubric(row), task["rubric_routes"], strict=True):
            legacy = criterion_plan(original, task, route, None, "user")
            if legacy["human_handoff_categories"]:
                expected[(row["task_id"], original["rubric_item_id"])] = (original, task)
    seen: set[tuple[str, str]] = set()
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for raw in entries:
        entry = _object(raw, "routing review item")
        key = (entry.get("task_id"), entry.get("rubric_item_id"))
        if key not in expected or key in seen:
            raise ValueError("routing review repeats an item or expands beyond the provisional-human population")
        seen.add(key)
        original, task = expected[key]
        if (
            entry.get("source_row_sha256") != task["row_sha256"]
            or entry.get("original_item_sha256") != canonical_hash(original)
            or entry.get("original_description") != original["criterion"]
            or type(entry.get("original_signed_score")) is not type(original["score"])
            or entry.get("original_signed_score") != original["score"]
        ):
            raise ValueError("routing review changes or fails to bind an original criterion")
        methods = entry.get("runtime_methods")
        if (
            not isinstance(methods, list)
            or not methods
            or not all(isinstance(method, str) and method in RUNTIME_METHODS for method in methods)
            or len(set(methods)) != len(methods)
        ):
            raise ValueError("routing review has invalid runtime methods")
        classification = entry.get("classification")
        if classification not in {"machine_observable", "application_operation", "perception", "ambiguous"}:
            raise ValueError("routing review has unknown classification")
        human = entry.get("provisional_human")
        if type(human) is not bool or human != (classification == "perception") or ("human" in methods) != human:
            raise ValueError("provisional human must name unobservable perception, not an application or uncertainty")
        if human and methods != ["human"]:
            raise ValueError("mixed observations retain one human final decision with separate component checks")
        pending = entry.get("pending_reason")
        if pending is not None and not _text(pending):
            raise ValueError("routing review pending reason must be nonempty")
        if classification == "ambiguous" and pending is None:
            raise ValueError("ambiguous predicates must remain pending")
        alternative = entry.get("machine_alternative")
        if alternative is not None and (
            not isinstance(alternative, dict)
            or set(alternative) != {"condition", "required_methods"}
            or not _text(alternative.get("condition"))
            or not isinstance(alternative.get("required_methods"), list)
            or not alternative["required_methods"]
            or not all(method in RUNTIME_METHODS - {"human"} for method in alternative["required_methods"])
            or len(set(alternative["required_methods"])) != len(alternative["required_methods"])
        ):
            raise ValueError("routing machine alternative must be a sufficient original branch with nonhuman methods")
        checks = entry.get("component_checks")
        if not isinstance(checks, list) or not checks or not _text(entry.get("basis")):
            raise ValueError("routing review needs concrete component observations and a basis")
        check_ids: set[str] = set()
        for check in checks:
            if not isinstance(check, dict) or not all(
                _text(check.get(k)) for k in ("id", "observation", "verification_status", "conditional_branch")
            ):
                raise ValueError("routing component needs observation, verification and original branch")
            if check["id"] in check_ids:
                raise ValueError("routing component IDs are repeated")
            check_ids.add(check["id"])
            if (
                not isinstance(check.get("methods"), list)
                or not check["methods"]
                or not all(m in RUNTIME_METHODS for m in check["methods"])
            ):
                raise ValueError("routing component has invalid methods")
            if (
                not isinstance(check.get("route_ids"), list)
                or not check["route_ids"]
                or not all(r in catalog for r in check["route_ids"])
            ):
                raise ValueError("routing component has no declared route")
            if not isinstance(check.get("evidence_refs"), list):
                raise ValueError("routing component must distinguish proof references from unverified routes")
        result.setdefault(key[0], {})[key[1]] = entry
    if seen != set(expected):
        raise ValueError("routing review must cover every original provisional-human item exactly once")
    return result


def apply_routing_review(
    candidate: dict[str, Any], entry: dict[str, Any], reviewer: str | None, coordination_owner: str | None
) -> dict[str, Any]:
    """Replace only the inspection route; preserve the complete original scoring unit."""
    if candidate["original_item_sha256"] != entry["original_item_sha256"]:
        raise ValueError("routing override does not bind the original criterion")
    components = entry["component_checks"]
    observations = [
        f"{check['id']}: {check['observation']} Original branch: {check['conditional_branch']} "
        f"Route(s): {', '.join(check['route_ids'])}; verification: {check['verification_status']}."
        for check in components
    ]
    procedures = [BRANCH_PROCEDURE, *observations, SHELL_PROCEDURE, PROVENANCE_LIMIT]
    conflicts = [
        condition
        for condition in candidate["runtime_rule_candidate"]["unconfirmed_conditions"]
        if condition.startswith("Unconfirmed while this original instruction/access question")
    ]
    human = None
    if entry["provisional_human"]:
        human = {
            "reviewer": reviewer,
            "procedure": " ".join(procedures)
            + " Machine-observable components may use recorded mechanical/AI checks; "
            "the provisional human observes only the unavailable perceptual components and integrates all evidence "
            "into the unchanged original criterion decision. Record actual time intervals and observations in a "
            "separate receipt bound to the criterion, protocol, artifact and assigned reviewer. Assignment is not observation.",
        }
        if reviewer is None and coordination_owner is not None:
            human["coordination_owner"] = coordination_owner
    rule = {
        "required_methods": entry["runtime_methods"],
        "acceptable_inference": None,
        "unconfirmed_conditions": [
            BRANCH_PROCEDURE,
            "Unconfirmed while any necessary applicable component lacks its stated evidence or verified route.",
            *observations,
            *conflicts,
            PROVENANCE_LIMIT,
        ],
        "human_review": human,
    }
    if entry["pending_reason"] is not None:
        rule["pending_reason"] = entry["pending_reason"]
    if entry.get("machine_alternative") is not None:
        rule["machine_alternative"] = entry["machine_alternative"]
        rule["unconfirmed_conditions"].append(
            "A positive observed machine alternative may satisfy the unchanged original OR predicate: "
            + entry["machine_alternative"]["condition"]
            + " If that branch is absent or fails, the other branch remains unconfirmed until actually inspected."
        )
    return {
        **candidate,
        "effective_categories": [entry["classification"]],
        "controller_overrides": [*candidate["controller_overrides"], "source_bound_provisional_human_route_review"],
        "necessary_evidence_methods": list(dict.fromkeys(m for check in components for m in check["methods"])),
        "procedure": procedures,
        "human_handoff_categories": ["currently_unobservable_perception"] if human else [],
        "runtime_rule_candidate": rule,
        "routing_review": entry,
    }


def validate_code_routing_review(
    value: dict[str, Any],
    rows: list[dict[str, Any]],
    source_bytes: bytes,
    source_hash: str,
    routing: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Bind the bounded three-task code review to every unchanged original item."""
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
        or value.get("kind") != "bounded_code_route_applicability_review"
        or _object(value.get("source"), "code routing source").get("sha256") != source_hash
        or digest(source_bytes) != source_hash
    ):
        raise ValueError("code routing review source hash or schema mismatch")
    tasks = value.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != len(CODE_TASK_CRITERION_COUNTS):
        raise ValueError("code routing review must cover exactly the three declared code tasks")
    originals = {row["task_id"]: (index, row) for index, row in enumerate(rows)}
    lines = source_bytes.splitlines()
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for raw_task in tasks:
        task = _object(raw_task, "code routing task")
        task_id = task.get("task_id")
        if (
            not isinstance(task_id, str)
            or task_id not in CODE_TASK_CRITERION_COUNTS
            or task_id not in originals
            or task_id in result
        ):
            raise ValueError("code routing review has duplicate or out-of-scope task IDs")
        index, row = originals[task_id]
        original_items = rubric(row)
        count = CODE_TASK_CRITERION_COUNTS[task_id]
        if (
            type(task.get("source_line_one_based")) is not int
            or task["source_line_one_based"] != index + 1
            or task.get("raw_line_sha256") != digest(lines[index])
            or task.get("original_row_sha256") != canonical_hash(row)
            or task.get("original_prompt_sha256") != digest(row["prompt"].encode())
            or type(task.get("criterion_count")) is not int
            or task["criterion_count"] != count
            or len(original_items) != count
        ):
            raise ValueError("code routing review does not bind the original task row or criterion count")
        entries = task.get("criteria")
        if not isinstance(entries, list) or len(entries) != count:
            raise ValueError("code routing review must cover all 143 original criteria exactly once")
        expected = {item["rubric_item_id"]: (number, item) for number, item in enumerate(original_items)}
        mapped: dict[str, dict[str, Any]] = {}
        for raw_entry in entries:
            entry = _object(raw_entry, "code routing criterion")
            identifier = entry.get("criterion_id")
            if not isinstance(identifier, str) or identifier not in expected or identifier in mapped:
                raise ValueError("code routing review has duplicate or unknown original criterion IDs")
            if identifier in (routing or {}).get(task_id, {}):
                raise ValueError("code routing review overlaps the separate provisional-human routing review")
            number, original = expected[identifier]
            if (
                type(entry.get("criterion_index_zero_based")) is not int
                or entry["criterion_index_zero_based"] != number
                or entry.get("original_item_sha256") != canonical_hash(original)
                or entry.get("original_description") != original["criterion"]
                or entry.get("description_sha256") != digest(original["criterion"].encode())
                or entry.get("normalized_ai_criterion_sha256")
                != canonical_hash({"id": identifier, "description": original["criterion"]})
                or type(entry.get("original_score")) is not type(original["score"])
                or entry.get("original_score") != original["score"]
            ):
                raise ValueError("code routing review changes or fails to bind an original criterion")
            methods = entry.get("proposed_required_methods")
            form = entry.get("requirement_form")
            if (
                not isinstance(methods, list)
                or not methods
                or not all(isinstance(method, str) and method in RUNTIME_METHODS - {"human"} for method in methods)
                or len(set(methods)) != len(methods)
                or not isinstance(form, str)
                or form not in CODE_BEHAVIOR_FORMS | CODE_STATIC_FORMS
            ):
                raise ValueError("code routing review has invalid nonhuman methods or requirement form")
            if (form in CODE_BEHAVIOR_FORMS and "functional" not in methods) or (
                form in CODE_STATIC_FORMS and not set(methods) <= {"content", "structure"}
            ):
                raise ValueError(
                    "code behavior requires functional evidence; static requirements use content/structure"
                )
            if (
                type(entry.get("execution_demonstration_explicitly_required")) is not bool
                or entry["execution_demonstration_explicitly_required"] != (form == "explicit_executed_test")
                or not all(_text(entry.get(key)) for key in ("basis", "inference_limit", "source_location"))
                or (entry.get("branch_condition") is not None and not _text(entry["branch_condition"]))
            ):
                raise ValueError("code routing review needs a consistent execution flag, basis and inference limit")
            if form == "optional_component_behavior" and not _text(entry.get("branch_condition")):
                raise ValueError("optional code behavior must retain its original branch condition")
            mapped[identifier] = entry
        result[task_id] = mapped
    return result


def apply_code_routing_review(candidate: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """Change an inspection procedure without establishing artifact success."""
    if candidate["original_item_sha256"] != entry["original_item_sha256"]:
        raise ValueError("code routing override does not bind the original criterion")
    methods = entry["proposed_required_methods"]
    category_for_method = {
        "content": "text/content",
        "functional": "interactive_execution",
        "research": "source_comparison",
    }
    procedures = [
        BRANCH_PROCEDURE,
        "Source-bound code requirement form: " + entry["requirement_form"] + ". " + entry["basis"],
        *[METHOD_PROCEDURES[category_for_method.get(method, method)] for method in methods],
        "Inference limit: " + entry["inference_limit"],
        SHELL_PROCEDURE,
        PROVENANCE_LIMIT,
    ]
    if entry.get("branch_condition") is not None:
        procedures.insert(2, "Original applicability condition: " + entry["branch_condition"])
    rule = candidate["runtime_rule_candidate"]
    conflicts = [
        condition
        for condition in rule["unconfirmed_conditions"]
        if condition.startswith("Unconfirmed while this original instruction/access question")
    ]
    return {
        **candidate,
        "effective_categories": [entry["requirement_form"]],
        "controller_overrides": [*candidate["controller_overrides"], "source_bound_code_route_review"],
        "necessary_evidence_methods": methods,
        "procedure": procedures,
        "human_handoff_categories": [],
        "runtime_rule_candidate": {
            **rule,
            "required_methods": methods,
            "acceptable_inference": None,
            "human_review": None,
            "unconfirmed_conditions": [
                DRAFT_LIMIT,
                "Unconfirmed unless the applicable original branch has actual submission evidence for every "
                "required method. Source, documentation or test presence alone does not establish execution, "
                "integration, security, deployment or a successful criterion result.",
                *procedures,
                *conflicts,
            ],
        },
        "code_routing_review": entry,
    }


def task_plan(
    row: dict[str, Any],
    task: dict[str, Any],
    source_sha256: str,
    review_sha256: str,
    reviewer: str | None,
    coordination_owner: str | None = None,
    routing_items: dict[str, dict[str, Any]] | None = None,
    routing_sha256: str | None = None,
    code_routing_items: dict[str, dict[str, Any]] | None = None,
    code_routing_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    original = rubric(row)
    task_id = row["task_id"]
    criteria = {
        "version": "gdpval-original-rubric-v1-" + source_sha256,
        "benchmark": "gdpval",
        "policy": {
            "arithmetic": "decimal",
            "rounding": "none",
            "decimal_places": 0,
            "absolute_tolerance": 0,
            "relative_tolerance": 0,
            "missing": "unconfirmed",
            "units": "Preserve units, tolerances, optionality and conditions exactly as stated in each original AI criterion.",
        },
        "tasks": {
            task_id: {
                "mechanical": [],
                "ai": [{"id": item["rubric_item_id"], "description": item["criterion"]} for item in original],
            }
        },
    }
    provenance = {
        "source_sha256": source_sha256,
        "review_sha256": review_sha256,
        "row_index": task["row_index"],
        "row_sha256": task["row_sha256"],
        "raw_line_sha256": task["raw_line_sha256"],
    }
    scores = {
        "schema_version": 1,
        "task_id": task_id,
        "provenance": provenance,
        "score_semantics": "Original signed rubric weights, preserved separately; no automatic aggregation or official score.",
        "items": [
            {
                "criterion_id": item["rubric_item_id"],
                "original_index": index,
                "original_signed_score": item["score"],
                "original_item_sha256": canonical_hash(item),
            }
            for index, item in enumerate(original)
        ],
    }
    items = [
        criterion_plan(item, task, route, reviewer, coordination_owner)
        for item, route in zip(original, task["rubric_routes"], strict=True)
    ]
    if routing_items is not None:
        items = [
            apply_routing_review(item, routing_items[item["criterion_id"]], reviewer, coordination_owner)
            if item["criterion_id"] in routing_items
            else item
            for item in items
        ]
        provenance["routing_review_sha256"] = routing_sha256
    if code_routing_items is not None:
        if set(code_routing_items) & set(routing_items or {}):
            raise ValueError("code and provisional-human routing overrides must not overlap")
        items = [
            apply_code_routing_review(item, code_routing_items[item["criterion_id"]])
            if item["criterion_id"] in code_routing_items
            else item
            for item in items
        ]
        provenance["code_routing_review_sha256"] = code_routing_sha256
    pending = [item["criterion_id"] for item in items if item["human_handoff_categories"] and reviewer is None]
    pending_routes = [item["criterion_id"] for item in items if item["runtime_rule_candidate"].get("pending_reason")]
    version = REVIEWED_VERSION + "/routing-" + routing_sha256 if routing_sha256 else VERSION
    if code_routing_sha256 is not None:
        version = (version if routing_sha256 else CODE_REVIEWED_VERSION) + "/code-routing-" + code_routing_sha256
    protocol = (
        None
        if pending and coordination_owner is None
        else {
            "schema_version": 1,
            "version": version + "/source-" + source_sha256 + "/review-" + review_sha256,
            "criteria_sha256": canonical_hash(criteria),
            "tasks": {task_id: {item["criterion_id"]: item["runtime_rule_candidate"] for item in items}},
        }
    )
    candidate = {
        "schema_version": 1,
        "version": version,
        "task_id": task_id,
        "status": "assignment_pending" if pending else "usable_draft",
        "applicability_status": "requires_criterion_applicability_confirmation",
        "capability_acceptance": "unconfirmed",
        "limits": [DRAFT_LIMIT, PROVENANCE_LIMIT],
        "provenance": provenance,
        "criteria_sha256": canonical_hash(criteria),
        "protocol_sha256": canonical_hash(protocol) if protocol is not None else None,
        "human_reviewer": reviewer,
        "human_coordination_owner": coordination_owner,
        "runnable_draft": protocol is not None,
        "unassigned_human_criterion_ids": pending,
        "pending_route_criterion_ids": pending_routes,
        "supplied_inputs": task["required_capabilities"]["supplied_read"],
        "participant_output": task["required_capabilities"]["participant_output"],
        "cad_boundary": task.get("cad_boundary"),
        "content_feasibility": task.get("content_feasibility"),
        "items": items,
    }
    return criteria, scores, candidate, protocol


def generate(
    source: Path,
    source_sha256: str,
    review_path: Path,
    out: Path,
    reviewer: str | None = None,
    coordination_owner: str | None = None,
    routing_review_path: Path | None = None,
    code_routing_review_path: Path | None = None,
) -> dict[str, Any]:
    if reviewer is not None and not reviewer.strip():
        raise ValueError("human reviewer must be a nonempty explicitly assigned name")
    if coordination_owner is not None and not coordination_owner.strip():
        raise ValueError("human coordination owner must be a nonempty explicitly assigned name")
    if out.exists() or out.is_symlink():
        raise ValueError("--out must name a new directory")
    source_bytes, review_bytes = source.read_bytes(), review_path.read_bytes()
    review = _object(json.loads(review_bytes), "review")
    rows = validate_inputs(source_bytes, source_sha256, review)
    review_sha256 = digest(review_bytes)
    routing_bytes = routing_review_path.read_bytes() if routing_review_path is not None else None
    routing_sha256 = digest(routing_bytes) if routing_bytes is not None else None
    routing = (
        validate_routing_review(
            _object(json.loads(routing_bytes), "routing review"), rows, review, source_sha256, review_sha256
        )
        if routing_bytes is not None
        else None
    )
    code_routing_bytes = code_routing_review_path.read_bytes() if code_routing_review_path is not None else None
    code_routing_sha256 = digest(code_routing_bytes) if code_routing_bytes is not None else None
    code_routing = (
        validate_code_routing_review(
            _object(json.loads(code_routing_bytes), "code routing review"), rows, source_bytes, source_sha256, routing
        )
        if code_routing_bytes is not None
        else None
    )
    plans = [
        task_plan(
            row,
            task,
            source_sha256,
            review_sha256,
            reviewer,
            coordination_owner,
            routing.get(row["task_id"], {}) if routing is not None else None,
            routing_sha256,
            code_routing.get(row["task_id"], {}) if code_routing is not None else None,
            code_routing_sha256,
        )
        for row, task in zip(rows, review["tasks"], strict=True)
    ]
    out.mkdir(parents=True, exist_ok=False)
    entries: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    for criteria, scores, candidate, protocol in plans:
        task_id = candidate["task_id"]
        directory = out / "tasks" / task_id
        directory.mkdir(parents=True)
        files = {"criteria.json": criteria, "source_scores.json": scores, "candidate_plan.json": candidate}
        if protocol is not None:
            files["inspection_protocol.json"] = protocol
        inventory: dict[str, dict[str, str]] = {}
        for name, value in files.items():
            data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
            target = directory / name
            with target.open("xb") as stream:
                stream.write(data)
            inventory[name] = {"path": target.relative_to(out).as_posix(), "sha256": digest(data)}
        totals[candidate["status"]] += 1
        totals["runnable_drafts"] += protocol is not None
        totals["criteria"] += len(candidate["items"])
        totals["negative_scores"] += sum(item["original_signed_score"] < 0 for item in scores["items"])
        totals["unassigned_human_criteria"] += len(candidate["unassigned_human_criterion_ids"])
        totals["pending_route_criteria"] += len(candidate["pending_route_criterion_ids"])
        totals["pending_route_tasks"] += bool(candidate["pending_route_criterion_ids"])
        entries.append(
            {
                "task_id": task_id,
                "status": candidate["status"],
                "runnable_draft": protocol is not None,
                "criterion_count": len(candidate["items"]),
                "unassigned_human_criterion_ids": candidate["unassigned_human_criterion_ids"],
                "pending_route_criterion_ids": candidate["pending_route_criterion_ids"],
                "criteria_sha256": candidate["criteria_sha256"],
                "protocol_sha256": candidate["protocol_sha256"],
                "files": inventory,
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "version": REVIEWED_VERSION
        if routing is not None
        else CODE_REVIEWED_VERSION
        if code_routing is not None
        else VERSION,
        "status": "reviewed_routes_not_artifact_assessment"
        if routing is not None or code_routing is not None
        else "conservative_draft_not_acceptance",
        "limits": [DRAFT_LIMIT, PROVENANCE_LIMIT, "No participant or model execution; no completed human receipts."],
        "inputs": {
            "source": {"path": str(source.resolve()), "sha256": source_sha256},
            "review": {"path": str(review_path.resolve()), "sha256": review_sha256},
            "generator": {"path": Path(__file__).name, "sha256": digest(Path(__file__).read_bytes())},
            "human_reviewer": reviewer,
            "human_coordination_owner": coordination_owner,
        },
        "summary": {
            "task_count": len(plans),
            "criterion_count": totals["criteria"],
            "original_negative_score_count": totals["negative_scores"],
            "usable_draft_tasks": totals["usable_draft"],
            "assignment_pending_tasks": totals["assignment_pending"],
            "runnable_draft_tasks": totals["runnable_drafts"],
            "unassigned_human_criteria": totals["unassigned_human_criteria"],
        },
        "tasks": entries,
    }
    if routing_review_path is not None:
        manifest["inputs"]["routing_review"] = {"path": str(routing_review_path.resolve()), "sha256": routing_sha256}
        manifest["summary"].update(
            pending_route_criteria=totals["pending_route_criteria"], pending_route_tasks=totals["pending_route_tasks"]
        )
    if code_routing_review_path is not None:
        manifest["inputs"]["code_routing_review"] = {
            "path": str(code_routing_review_path.resolve()),
            "sha256": code_routing_sha256,
        }
        manifest["summary"]["code_routing_task_count"] = len(code_routing or {})
        manifest["summary"]["code_routing_criterion_count"] = sum(
            len(items) for items in (code_routing or {}).values()
        )
    with (out / "manifest.json").open("x") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--routing-review",
        type=Path,
        help="Source-bound review of provisional human items; without it, reproduce the legacy conservative draft",
    )
    parser.add_argument("--human-reviewer", help="Explicitly assigned human name; never implies a completed receipt")
    parser.add_argument(
        "--code-routing-review",
        type=Path,
        help="Source-bound 143-item code review; distinct from the provisional-human routing review",
    )
    parser.add_argument(
        "--human-coordination-owner",
        help="Explicit assignment owner; permits AI evaluation with pending human criteria remaining unconfirmed",
    )
    args = parser.parse_args(argv)
    try:
        result = generate(
            args.source,
            args.source_sha256,
            args.review,
            args.out,
            args.human_reviewer,
            args.human_coordination_owner,
            args.routing_review,
            args.code_routing_review,
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"inspection plan generation failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                **result["summary"],
                "manifest": str((args.out / "manifest.json").resolve()),
                "manifest_sha256": digest((args.out / "manifest.json").read_bytes()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
