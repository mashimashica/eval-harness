# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from eval_harness.grading_criteria import criteria_for_task, criteria_hash, load_criteria
from eval_harness.inspection_protocol import apply_inspection_protocol, load_inspection_protocol, protocol_for_task

SCRIPT = Path(__file__).resolve().parents[2] / ".agents/development/scripts/gdpval_inspection_plan.py"
SPEC = importlib.util.spec_from_file_location("gdpval_inspection_plan_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plan)


def inputs(
    categories: list[str],
    *,
    description: str = "The original criterion.",
    identifier: str = "original-id",
    task_id: str = "example",
    inference: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    item = {"rubric_item_id": identifier, "criterion": description, "score": -2, "author_type": "human"}
    row = {"task_id": task_id, "prompt": "Original frozen task.", "rubric_json": json.dumps([item])}
    task = {
        "task_id": task_id,
        "row_index": 0,
        "row_sha256": plan.canonical_hash(row),
        "raw_line_sha256": plan.digest(json.dumps(row).encode()),
        "inclusion": "in_scope",
        "rubric_routes": [[identifier, -2, categories, inference]],
        "required_capabilities": {
            "supplied_read": [],
            "participant_output": {"modalities": ["document"], "capabilities": ["document_author"]},
        },
        "conflicts_or_data_access_questions": [],
        "human_domain_review": {
            "route_status": "optional_candidate_escalation",
            "rubric_item_ids": [],
            "mandatory_human_criterion_ids": [],
        },
    }
    return row, task


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("inspection-plan")
    rows: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    for index in range(220):
        row, task = inputs(["text/content"], task_id=f"task-{index}")
        count = 48 if index < 113 else 47
        items = [
            {
                "rubric_item_id": f"criterion-{index}-{number}",
                "criterion": f"If branch A applies, keep ‘unchanged’ line {number}.\nOtherwise B is optional.",
                "score": -3 if index < 2 else 2,
            }
            for number in range(count)
        ]
        row["rubric_json"] = json.dumps(items, ensure_ascii=False)
        task.update(
            row_index=index,
            row_sha256=plan.canonical_hash(row),
            raw_line_sha256=plan.digest(json.dumps(row).encode()),
            rubric_routes=[
                [item["rubric_item_id"], item["score"], ["audio_listen"] if index == 0 else ["text/content"], False]
                for item in items
            ],
        )
        rows.append(row)
        tasks.append(task)
    source_bytes = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    source_hash = plan.digest(source_bytes)
    review = {"schema_version": 1, "source": {"sha256": source_hash}, "tasks": tasks}
    source, review_path, out = root / "source.jsonl", root / "review.json", root / "generated"
    source.write_bytes(source_bytes)
    review_path.write_text(json.dumps(review))
    manifest = plan.generate(source, source_hash, review_path, out)
    return {
        "source": source,
        "review_path": review_path,
        "source_hash": source_hash,
        "source_bytes": source_bytes,
        "review": review,
        "rows": rows,
        "out": out,
        "manifest": manifest,
    }


def test_exact_all_task_criterion_wording_order_and_negative_scores(bundle: dict[str, Any]) -> None:
    manifest = bundle["manifest"]
    assert manifest["summary"] == {
        "task_count": 220,
        "criterion_count": 10453,
        "original_negative_score_count": 96,
        "usable_draft_tasks": 219,
        "assignment_pending_tasks": 1,
        "runnable_draft_tasks": 219,
        "unassigned_human_criteria": 48,
    }
    for row, entry in zip(bundle["rows"], manifest["tasks"], strict=True):
        directory = bundle["out"] / "tasks" / row["task_id"]
        criteria = json.loads((directory / "criteria.json").read_bytes())
        original = json.loads(row["rubric_json"])
        assert criteria["tasks"][row["task_id"]]["ai"] == [
            {"id": item["rubric_item_id"], "description": item["criterion"]} for item in original
        ]
        scores = json.loads((directory / "source_scores.json").read_bytes())
        assert [score["original_signed_score"] for score in scores["items"]] == [item["score"] for item in original]
        assert [score["original_index"] for score in scores["items"]] == list(range(len(original)))
        for inventory in entry["files"].values():
            assert plan.digest((bundle["out"] / inventory["path"]).read_bytes()) == inventory["sha256"]
        assert entry["criteria_sha256"] == criteria_hash(criteria)
    assert manifest["inputs"]["source"]["sha256"] == bundle["source_hash"]
    assert manifest["inputs"]["review"]["sha256"] == plan.digest(bundle["review_path"].read_bytes())
    assert manifest["inputs"]["generator"]["sha256"] == plan.digest(SCRIPT.read_bytes())


def test_unassigned_human_blocks_only_affected_task_protocol_and_other_drafts_load(bundle: dict[str, Any]) -> None:
    blocked = bundle["out"] / "tasks/task-0"
    assert not (blocked / "inspection_protocol.json").exists()
    candidate = json.loads((blocked / "candidate_plan.json").read_bytes())
    assert candidate["status"] == "assignment_pending"
    assert candidate["items"][0]["runtime_rule_candidate"]["human_review"]["reviewer"] is None
    assert candidate["protocol_sha256"] is None
    usable = bundle["out"] / "tasks/task-1"
    criteria = load_criteria(str(usable / "criteria.json"), usable)
    protocol = load_inspection_protocol(str(usable / "inspection_protocol.json"), usable, criteria)
    selected = criteria_for_task(criteria, "task-1", "gdpval")
    rules = protocol_for_task(protocol, "task-1", selected)
    assert rules is not None and set(rules) == {f"criterion-1-{i}" for i in range(48)}
    assert candidate["capability_acceptance"] == "unconfirmed"
    assert "every route" in candidate["limits"][0]


def test_named_reviewer_enables_schema_but_never_supplies_completed_receipt() -> None:
    row, task = inputs(["text/content", "audio_listen"])
    criteria, _, candidate, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, "Assigned reviewer")
    assert load_inspection_protocol(protocol, Path.cwd(), criteria) == protocol
    rule = protocol["tasks"]["example"]["original-id"]
    assert rule["required_methods"] == ["human"] and rule["acceptable_inference"] is None
    assert rule["human_review"]["reviewer"] == "Assigned reviewer"
    assert "artifact hashes" in rule["human_review"]["procedure"]
    assert "not a completed observation" in rule["human_review"]["procedure"]
    assert candidate["status"] == "usable_draft" and candidate["capability_acceptance"] == "unconfirmed"
    assert "receipt" not in protocol and candidate["unassigned_human_criterion_ids"] == []


def test_coordination_owner_allows_pending_protocol_without_inventing_reviewer() -> None:
    row, task = inputs(["text/content", "audio_listen"])
    criteria, _, candidate, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None, "user")
    assert protocol is not None
    human = protocol["tasks"]["example"]["original-id"]["human_review"]
    assert human["reviewer"] is None and human["coordination_owner"] == "user"
    assert candidate["status"] == "assignment_pending" and candidate["runnable_draft"] is True
    assert candidate["unassigned_human_criterion_ids"] == ["original-id"]
    assert candidate["capability_acceptance"] == "unconfirmed"
    assert protocol["criteria_sha256"] == criteria_hash(criteria)


def test_cli_source_hash_mismatch_writes_nothing(
    bundle: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "must-not-exist"
    assert (
        plan.main(
            [
                "--source",
                str(bundle["source"]),
                "--source-sha256",
                "0" * 64,
                "--review",
                str(bundle["review_path"]),
                "--out",
                str(out),
            ]
        )
        == 2
    )
    assert not out.exists() and "SHA256 mismatch" in capsys.readouterr().err


@pytest.mark.parametrize("mutation", ["row", "raw_line", "id", "score", "method", "mandatory_expert", "task_count"])
def test_stale_or_incomplete_review_rejected(bundle: dict[str, Any], mutation: str) -> None:
    review = copy.deepcopy(bundle["review"])
    task = review["tasks"][0]
    if mutation == "row":
        task["row_sha256"] = "0" * 64
    elif mutation == "raw_line":
        task["raw_line_sha256"] = "0" * 64
    elif mutation == "id":
        task["rubric_routes"][0][0] = "different-original"
    elif mutation == "score":
        task["rubric_routes"][0][1] = abs(task["rubric_routes"][0][1])
    elif mutation == "method":
        task["rubric_routes"][0][2] = ["human_domain"]
    elif mutation == "mandatory_expert":
        task["human_domain_review"]["mandatory_human_criterion_ids"] = [task["rubric_routes"][0][0]]
    else:
        review["tasks"].pop()
    with pytest.raises(ValueError):
        plan.validate_inputs(bundle["source_bytes"], bundle["source_hash"], review)


def test_exact_criterion_total_is_required_even_when_routes_match(bundle: dict[str, Any]) -> None:
    rows, review = copy.deepcopy(bundle["rows"]), copy.deepcopy(bundle["review"])
    items = json.loads(rows[0]["rubric_json"])
    items.pop()
    rows[0]["rubric_json"] = json.dumps(items)
    review["tasks"][0]["rubric_routes"].pop()
    review["tasks"][0]["row_sha256"] = plan.canonical_hash(rows[0])
    review["tasks"][0]["raw_line_sha256"] = plan.digest(json.dumps(rows[0]).encode())
    source_bytes = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    review["source"]["sha256"] = plan.digest(source_bytes)
    with pytest.raises(ValueError, match="exactly 10453 criteria"):
        plan.validate_inputs(source_bytes, plan.digest(source_bytes), review)


def test_existing_output_and_blank_reviewer_are_rejected_without_changes(
    bundle: dict[str, Any], tmp_path: Path
) -> None:
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("preserved")
    with pytest.raises(ValueError, match="new directory"):
        plan.generate(bundle["source"], bundle["source_hash"], bundle["review_path"], tmp_path)
    with pytest.raises(ValueError, match="nonempty"):
        plan.generate(bundle["source"], bundle["source_hash"], bundle["review_path"], tmp_path / "new", " ")
    assert sentinel.read_text() == "preserved" and not (tmp_path / "new").exists()


@pytest.mark.parametrize("identifier", sorted(plan.SCIENCE_IDS))
def test_fixed_science_accuracy_requires_actual_authoritative_comparison(identifier: str) -> None:
    description = "Complex scientific terms or processes are simplified into plain, accurate language."
    row, task = inputs(["text/content"], identifier=identifier, description=description, inference=True)
    criteria, _, candidate, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    rule = protocol["tasks"]["example"][identifier]
    assert rule["required_methods"] == ["content", "research"]
    assert rule["acceptable_inference"]["required_methods"] == ["content", "research"]
    text = json.dumps(rule)
    assert "actually compare" in text and "authoritative primary source content" in text
    assert "Wording preservation" in text and "is insufficient" in text
    assert criteria["tasks"]["example"]["ai"] == [{"id": identifier, "description": description}]
    assert candidate["items"][0]["controller_overrides"]


def test_reports_about_media_and_optional_domain_expertise_do_not_require_human() -> None:
    row, task = inputs(
        ["text/content"], description="The report describes audio, video and native app procedures.", inference=True
    )
    task["human_domain_review"].update(rubric_item_ids=["original-id"], candidate_role="Subject expert")
    _, _, candidate, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    assert protocol is not None
    assert candidate["items"][0]["runtime_rule_candidate"]["required_methods"] == ["content"]
    assert candidate["items"][0]["human_handoff_categories"] == []
    assert candidate["items"][0]["optional_expert_escalation"]["status"] == "optional_candidate_escalation"
    assert candidate["items"][0]["runtime_rule_candidate"]["acceptable_inference"] is not None


def test_pure_supplied_source_comparison_accepts_shell_without_external_fetch() -> None:
    row, task = inputs(
        ["text/content", "source_comparison"], description="Values match the provided workbook.", inference=True
    )
    task["required_capabilities"]["supplied_read"] = [{"format": ".xlsx", "files": ["reference_files/source.xlsx"]}]
    _, _, candidate, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    rule = protocol["tasks"]["example"]["original-id"]
    assert rule["required_methods"] == ["content", "research"]
    assert "needs no external fetch" in json.dumps(rule)
    assert "shell may bind both submission and supplied-source paths and hashes" in json.dumps(rule)
    assert "wording preservation, not factual or scientific accuracy" in json.dumps(rule)
    assert "captured_stdout_path" in " ".join(candidate["items"][0]["procedure"])


def test_input_step_is_not_new_step_output_or_blanket_geometry_requirement() -> None:
    row, task = inputs(["text/content", "source_comparison"], description="PDF report cites the supplied STEP model.")
    task["required_capabilities"]["supplied_read"] = [{"format": ".step", "files": ["reference_files/input.step"]}]
    task["required_capabilities"]["participant_output"] = {"modalities": ["pdf"], "capabilities": ["pdf_author"]}
    task["cad_boundary"] = {"supplied_step_read_required": True, "new_step_authoring_required": False}
    _, _, candidate, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    assert candidate["participant_output"]["modalities"] == ["pdf"]
    assert candidate["cad_boundary"]["new_step_authoring_required"] is False
    assert protocol["tasks"]["example"]["original-id"]["required_methods"] == ["content", "research"]
    task["rubric_routes"][0][2] = ["CAD_geometry"]
    _, _, _, geometry_protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    assert geometry_protocol["tasks"]["example"]["original-id"]["required_methods"] == ["functional"]
    assert "measured quantities" in json.dumps(geometry_protocol)


def test_pivot_presence_is_structure_only_and_word_native_click_requires_human() -> None:
    row, task = inputs(
        ["structure", "text/content", "spreadsheet_recalc", "source_comparison", "native_app"],
        identifier=plan.PIVOT_PRESENCE_ID,
        description='"Sales by Store" contains an Excel PivotTable object whose source data range is on the "Data" sheet.',
    )
    _, _, _, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    assert protocol["tasks"]["example"][plan.PIVOT_PRESENCE_ID]["required_methods"] == ["structure"]
    for identifier in plan.SCIENCE_NATIVE_UI_IDS:
        row, task = inputs(["structure", "native_app"], task_id=plan.SCIENCE_TASK_ID, identifier=identifier)
        _, _, candidate, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
        assert protocol is None and candidate["unassigned_human_criterion_ids"] == [identifier]


def test_word_xml_and_comment_counts_do_not_require_native_human_or_external_research() -> None:
    identifier = "1f122410-2ced-4c2e-bf53-e8cc64a9f6c8"
    row, task = inputs(
        ["structure", "text/content", "source_comparison", "native_app"],
        task_id=plan.SCIENCE_TASK_ID,
        identifier=identifier,
        description="At least three reviewer comments occur in three distinct paragraphs.",
    )
    _, _, _, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    assert protocol["tasks"][plan.SCIENCE_TASK_ID][identifier]["required_methods"] == ["structure"]
    row, task = inputs(
        ["structure", "text/content", "source_comparison", "native_app"],
        task_id=plan.SCIENCE_TASK_ID,
        identifier="9729dc33-d728-4b96-9e2b-22b7c1abd606",
        description="Substantive edits appear as Track Changes insertions.",
    )
    _, _, _, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    assert protocol["tasks"][plan.SCIENCE_TASK_ID]["9729dc33-d728-4b96-9e2b-22b7c1abd606"]["required_methods"] == [
        "structure",
        "content",
        "research",
    ]


def test_dashboard_functional_evidence_requires_changed_inputs_observed_outputs_not_call_existence() -> None:
    row, task = inputs(
        ["structure", "spreadsheet_recalc", "interactive_execution"],
        task_id=plan.DASHBOARD_TASK_ID,
        description="The dashboard updates outputs for selected weeks.",
        inference=True,
    )
    _, _, _, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    rule = protocol["tasks"][plan.DASHBOARD_TASK_ID]["original-id"]
    assert rule["required_methods"] == ["structure", "functional"]
    assert rule["acceptable_inference"] is None
    text = json.dumps(rule)
    assert "selected values and changed source cells" in text and "before/after PivotTable" in text
    assert "independent expected values" in text and "Merely executing a shell" in text
    assert "provenance only" in text


def test_reviewed_dashboard_output_routes_are_functional_and_user_controls_stay_human() -> None:
    for identifier in plan.DASHBOARD_FUNCTIONAL_IDS:
        row, task = inputs(
            ["structure", "text/content", "spreadsheet_recalc", "native_app"],
            task_id=plan.DASHBOARD_TASK_ID,
            identifier=identifier,
        )
        _, _, _, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
        rule = protocol["tasks"][plan.DASHBOARD_TASK_ID][identifier]
        assert "functional" in rule["required_methods"] and "human" not in rule["required_methods"]
        if identifier == "a7c98919-f78d-497b-a82e-0b619385ba87":
            assert "visual" in rule["required_methods"]
    for identifier in ["95e4be82-2487-474e-b51a-a5ed3bbdebf7", "2a682572-ceef-4b12-bd20-603cbeb1aec1"]:
        row, task = inputs(
            ["structure", "interactive_execution", "native_app"],
            task_id=plan.DASHBOARD_TASK_ID,
            identifier=identifier,
        )
        _, _, candidate, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None, "user")
        rule = protocol["tasks"][plan.DASHBOARD_TASK_ID][identifier]
        assert rule["required_methods"] == ["human"]
        assert candidate["unassigned_human_criterion_ids"] == [identifier]


def test_original_conflict_and_alternative_remain_unconfirmed_conditions() -> None:
    description = "If no source is provided, use either A or B; do not require both."
    row, task = inputs(["text/content"], description=description)
    task["conflicts_or_data_access_questions"] = [
        {"criterion_ids": ["original-id"], "detail": "A conflicts with the prompt."}
    ]
    criteria, _, candidate, protocol = plan.task_plan(row, task, "a" * 64, "b" * 64, None)
    assert criteria["tasks"]["example"]["ai"][0]["description"] == description
    assert candidate["items"][0]["original_description"] == description
    assert "do not require all alternatives" in json.dumps(protocol)
    assert "A conflicts with the prompt." in json.dumps(protocol)


def routing_review_for_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    row, task = bundle["rows"][0], bundle["review"]["tasks"][0]
    entries = []
    for index, original in enumerate(json.loads(row["rubric_json"])):
        classification = {0: "application_operation", 1: "perception", 2: "ambiguous"}.get(index, "machine_observable")
        methods = {0: ["structure", "functional"], 1: ["human"]}.get(index, ["content"])
        checks = [
            {
                "id": "original-predicate",
                "observation": "Inspect the applicable original clause without changing its alternatives.",
                "methods": methods,
                "route_ids": ["fixture-route"],
                "verification_status": "unconfirmed" if index < 3 else "verified_common_route",
                "evidence_refs": [],
                "conditional_branch": original["criterion"],
            }
        ]
        if index == 1:
            checks.insert(
                0,
                {
                    **checks[0],
                    "id": "numeric-component",
                    "methods": ["structure"],
                    "observation": "Read the actual stream sample rate; this does not establish listening quality.",
                },
            )
        entries.append(
            {
                "task_id": row["task_id"],
                "rubric_item_id": original["rubric_item_id"],
                "source_row_sha256": task["row_sha256"],
                "original_item_sha256": plan.canonical_hash(original),
                "original_signed_score": original["score"],
                "original_description": original["criterion"],
                "classification": classification,
                "runtime_methods": methods,
                "pending_reason": {
                    0: "Native update automation awaits verification.",
                    2: "Original branch is ambiguous.",
                }.get(index),
                "provisional_human": index == 1,
                "component_checks": checks,
                "basis": "Synthetic source-bound routing fixture; no real capability acceptance claim.",
            }
        )
    return {
        "schema_version": 1,
        "source_dataset_sha256": bundle["source_hash"],
        "source_review_sha256": plan.digest(bundle["review_path"].read_bytes()),
        "source_plan_manifest_sha256": plan.digest((bundle["out"] / "manifest.json").read_bytes()),
        "route_catalog": {"fixture-route": {"scope": "Synthetic route metadata."}},
        "items": entries,
    }


def test_reviewed_routes_keep_original_units_and_do_not_block_unrelated_items(
    bundle: dict[str, Any], tmp_path: Path
) -> None:
    review = routing_review_for_bundle(bundle)
    review_path = tmp_path / "routing.json"
    review_path.write_text(json.dumps(review))
    out = tmp_path / "new-version"
    old_manifest = (bundle["out"] / "manifest.json").read_bytes()
    manifest = plan.generate(
        bundle["source"],
        bundle["source_hash"],
        bundle["review_path"],
        out,
        coordination_owner="user",
        routing_review_path=review_path,
    )
    assert manifest["summary"]["unassigned_human_criteria"] == 1
    assert manifest["summary"]["pending_route_criteria"] == 2
    assert manifest["summary"]["runnable_draft_tasks"] == 220
    assert manifest["summary"]["criterion_count"] == 10453
    assert manifest["summary"]["original_negative_score_count"] == 96
    assert (bundle["out"] / "manifest.json").read_bytes() == old_manifest
    directory = out / "tasks/task-0"
    candidate = json.loads((directory / "candidate_plan.json").read_bytes())
    criteria = load_criteria(str(directory / "criteria.json"), directory)
    protocol = load_inspection_protocol(str(directory / "inspection_protocol.json"), directory, criteria)
    assert protocol is not None
    rules = protocol["tasks"]["task-0"]
    assert rules["criterion-0-0"]["human_review"] is None
    assert rules["criterion-0-0"]["pending_reason"] == "Native update automation awaits verification."
    assert rules["criterion-0-2"]["pending_reason"] == "Original branch is ambiguous."
    assert rules["criterion-0-3"]["required_methods"] == ["content"]
    assert "pending_reason" not in rules["criterion-0-3"]
    assert candidate["items"][1]["necessary_evidence_methods"] == ["structure", "human"]
    assert "sample rate" in rules["criterion-0-1"]["human_review"]["procedure"]
    assert rules["criterion-0-1"]["human_review"]["coordination_owner"] == "user"
    assert all(
        item["original_description"] == original["criterion"]
        for item, original in zip(candidate["items"], json.loads(bundle["rows"][0]["rubric_json"]), strict=True)
    )
    assert protocol["version"].startswith(plan.REVIEWED_VERSION)
    assert manifest["inputs"]["routing_review"]["sha256"] == plan.digest(review_path.read_bytes())


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "source", "description", "weight", "row", "methods", "human_application"]
)
def test_routing_review_rejects_drift_incomplete_coverage_and_blanket_human(
    bundle: dict[str, Any], tmp_path: Path, mutation: str
) -> None:
    review = routing_review_for_bundle(bundle)
    if mutation == "missing":
        review["items"].pop()
    elif mutation == "duplicate":
        review["items"].append(copy.deepcopy(review["items"][0]))
    elif mutation == "source":
        review["source_dataset_sha256"] = "0" * 64
    elif mutation == "description":
        review["items"][0]["original_description"] = "Easier predicate."
    elif mutation == "weight":
        review["items"][0]["original_signed_score"] = 0
    elif mutation == "row":
        review["items"][0]["source_row_sha256"] = "0" * 64
    elif mutation == "methods":
        review["items"][0]["runtime_methods"] = ["human", "functional"]
    else:
        review["items"][0].update(provisional_human=True, runtime_methods=["human"])
    path = tmp_path / "invalid-routing.json"
    path.write_text(json.dumps(review))
    out = tmp_path / "no-partial-output"
    with pytest.raises(ValueError):
        plan.generate(
            bundle["source"],
            bundle["source_hash"],
            bundle["review_path"],
            out,
            coordination_owner="user",
            routing_review_path=path,
        )
    assert not out.exists()


@pytest.fixture(scope="module")
def code_bundle(bundle: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("code-routing")
    rows, review = copy.deepcopy(bundle["rows"]), copy.deepcopy(bundle["review"])
    for index, (task_id, count) in enumerate(plan.CODE_TASK_CRITERION_COUNTS.items(), 1):
        row, task = rows[index], review["tasks"][index]
        originals = json.loads(row["rubric_json"])
        originals = [{**originals[0], "rubric_item_id": f"code-{index}-{number}"} for number in range(count)]
        originals[0]["criterion"] = "The README includes validation instructions; it does not require an executed run."
        originals[1]["criterion"] = "The submitted handler rejects an invalid request with the specified status."
        originals[2]["criterion"] = "If a relayer is included, it reports failed requests."
        originals[3]["criterion"] = "Include the generated artifact OR a script and instructions to produce it."
        row.update(task_id=task_id, rubric_json=json.dumps(originals, ensure_ascii=False))
        task.update(
            task_id=task_id,
            rubric_routes=[
                [item["rubric_item_id"], item["score"], ["interactive_execution"], False] for item in originals
            ],
        )
    # The three bounded tasks have 143 criteria, one fewer than the replaced fixture tasks.
    extra = json.loads(rows[4]["rubric_json"])
    extra.append({**extra[0], "rubric_item_id": "unchanged-extra-item"})
    rows[4]["rubric_json"] = json.dumps(extra, ensure_ascii=False)
    review["tasks"][4]["rubric_routes"].append(["unchanged-extra-item", extra[-1]["score"], ["text/content"], False])
    for row, task in zip(rows, review["tasks"], strict=True):
        task["row_sha256"] = plan.canonical_hash(row)
        task["raw_line_sha256"] = plan.digest(json.dumps(row).encode())
    source_bytes = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    source_hash = plan.digest(source_bytes)
    review["source"]["sha256"] = source_hash
    source, review_path = root / "source.jsonl", root / "review.json"
    source.write_bytes(source_bytes)
    review_path.write_text(json.dumps(review))
    code_tasks = []
    for index in range(1, 4):
        row, task = rows[index], review["tasks"][index]
        entries = []
        for number, item in enumerate(json.loads(row["rubric_json"])):
            form = {
                0: "documentation",
                1: "runtime_behavior",
                2: "optional_component_behavior",
                4: "explicit_executed_test",
            }.get(number, "source_or_artifact")
            entries.append(
                {
                    "criterion_index_zero_based": number,
                    "criterion_id": item["rubric_item_id"],
                    "original_description": item["criterion"],
                    "original_score": item["score"],
                    "original_item_sha256": plan.canonical_hash(item),
                    "normalized_ai_criterion_sha256": plan.canonical_hash(
                        {"id": item["rubric_item_id"], "description": item["criterion"]}
                    ),
                    "description_sha256": plan.digest(item["criterion"].encode()),
                    "source_location": f"JSONL line {index + 1}; decoded rubric_json[{number}]",
                    "requirement_form": form,
                    "proposed_required_methods": ["content", "functional"]
                    if form in plan.CODE_BEHAVIOR_FORMS
                    else ["content", "structure"],
                    "execution_demonstration_explicitly_required": form == "explicit_executed_test",
                    "basis": "Inspect the unchanged original branch using the specified observation method.",
                    "inference_limit": "Source and test presence do not prove execution, integration, security or deployment.",
                    "branch_condition": "Only if a relayer is included."
                    if form == "optional_component_behavior"
                    else None,
                }
            )
        code_tasks.append(
            {
                "task_id": row["task_id"],
                "source_line_one_based": index + 1,
                "raw_line_sha256": task["raw_line_sha256"],
                "original_row_sha256": task["row_sha256"],
                "original_prompt_sha256": plan.digest(row["prompt"].encode()),
                "criterion_count": len(entries),
                "criteria": entries,
            }
        )
    code_review = {
        "schema_version": 1,
        "kind": "bounded_code_route_applicability_review",
        "source": {"sha256": source_hash},
        "tasks": code_tasks,
    }
    return {
        **bundle,
        "source": source,
        "source_bytes": source_bytes,
        "source_hash": source_hash,
        "review_path": review_path,
        "review": review,
        "rows": rows,
        "code_review": code_review,
    }


def test_code_review_cli_changes_only_143_methods_and_preserves_originals(
    code_bundle: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code_path, routing_path, out = tmp_path / "code.json", tmp_path / "human.json", tmp_path / "new-protocol"
    code_path.write_text(json.dumps(code_bundle["code_review"]))
    routing_path.write_text(json.dumps(routing_review_for_bundle(code_bundle)))
    old_manifest = (code_bundle["out"] / "manifest.json").read_bytes()
    assert (
        plan.main(
            [
                "--source",
                str(code_bundle["source"]),
                "--source-sha256",
                code_bundle["source_hash"],
                "--review",
                str(code_bundle["review_path"]),
                "--out",
                str(out),
                "--routing-review",
                str(routing_path),
                "--code-routing-review",
                str(code_path),
                "--human-coordination-owner",
                "user",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["code_routing_criterion_count"] == 143 and output["code_routing_task_count"] == 3
    manifest = json.loads((out / "manifest.json").read_bytes())
    code_hash = plan.digest(code_path.read_bytes())
    assert manifest["inputs"]["code_routing_review"]["sha256"] == code_hash
    assert manifest["summary"]["criterion_count"] == 10453
    assert manifest["summary"]["unassigned_human_criteria"] == 1
    assert (code_bundle["out"] / "manifest.json").read_bytes() == old_manifest
    changed = 0
    for index, row in enumerate(code_bundle["rows"]):
        directory = out / "tasks" / row["task_id"]
        candidate = json.loads((directory / "candidate_plan.json").read_bytes())
        criteria = load_criteria(str(directory / "criteria.json"), directory)
        protocol = load_inspection_protocol(str(directory / "inspection_protocol.json"), directory, criteria)
        assert criteria is not None and protocol is not None
        scores = json.loads((directory / "source_scores.json").read_bytes())
        original = json.loads(row["rubric_json"])
        assert criteria["tasks"][row["task_id"]]["ai"] == [
            {"id": item["rubric_item_id"], "description": item["criterion"]} for item in original
        ]
        assert [item["original_signed_score"] for item in scores["items"]] == [item["score"] for item in original]
        assert candidate["provenance"]["code_routing_review_sha256"] == code_hash
        assert "/code-routing-" + code_hash in protocol["version"]
        changed += sum("source_bound_code_route_review" in item["controller_overrides"] for item in candidate["items"])
        assert candidate["capability_acceptance"] == "unconfirmed"
        if index in (1, 2, 3):
            rules = protocol["tasks"][row["task_id"]]
            assert rules[f"code-{index}-0"]["required_methods"] == ["content", "structure"]
            assert rules[f"code-{index}-1"]["required_methods"] == ["content", "functional"]
            assert rules[f"code-{index}-1"]["acceptable_inference"] is None
            assert "Only if a relayer is included." in " ".join(candidate["items"][2]["procedure"])
            assert " OR " in candidate["items"][3]["original_description"]
            assert "do not require all alternatives" in " ".join(candidate["items"][3]["procedure"])
            assert "machine_alternative" not in rules[f"code-{index}-3"]
        elif index > 3:
            _, _, legacy, _ = plan.task_plan(
                row, code_bundle["review"]["tasks"][index], code_bundle["source_hash"], "b" * 64, None, "user"
            )
            assert candidate["items"] == legacy["items"]
    assert changed == 143


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "row",
        "raw_line",
        "prompt",
        "description",
        "weight",
        "weight_type",
        "item_hash",
        "normalized_hash",
        "unknown_id",
        "duplicate_id",
        "missing_item",
        "unknown_task",
        "duplicate_task",
        "human",
        "unknown_method",
        "duplicate_method",
        "behavior_weakened",
        "static_execution",
        "missing_branch",
    ],
)
def test_invalid_code_review_fails_before_any_output(
    code_bundle: dict[str, Any], tmp_path: Path, mutation: str
) -> None:
    review = copy.deepcopy(code_bundle["code_review"])
    task, item = review["tasks"][0], review["tasks"][0]["criteria"][0]
    if mutation == "source":
        review["source"]["sha256"] = "0" * 64
    elif mutation in {"row", "raw_line", "prompt"}:
        task[
            {"row": "original_row_sha256", "raw_line": "raw_line_sha256", "prompt": "original_prompt_sha256"}[mutation]
        ] = "0" * 64
    elif mutation == "description":
        item["original_description"] = "A weaker predicate."
    elif mutation == "weight":
        item["original_score"] = 0
    elif mutation == "weight_type":
        item["original_score"] = float(item["original_score"])
    elif mutation in {"item_hash", "normalized_hash"}:
        item[{"item_hash": "original_item_sha256", "normalized_hash": "normalized_ai_criterion_sha256"}[mutation]] = (
            "0" * 64
        )
    elif mutation == "unknown_id":
        item["criterion_id"] = "unknown-original-id"
    elif mutation == "duplicate_id":
        task["criteria"][1] = copy.deepcopy(item)
    elif mutation == "missing_item":
        task["criteria"].pop()
    elif mutation == "unknown_task":
        task["task_id"] = "task-9"
    elif mutation == "duplicate_task":
        review["tasks"][1] = copy.deepcopy(task)
    elif mutation in {"human", "unknown_method", "duplicate_method", "static_execution"}:
        item["proposed_required_methods"] = {
            "human": ["human"],
            "unknown_method": ["deployment"],
            "duplicate_method": ["content", "content"],
            "static_execution": ["functional"],
        }[mutation]
    elif mutation == "behavior_weakened":
        task["criteria"][1]["proposed_required_methods"] = ["content"]
    else:
        task["criteria"][2]["branch_condition"] = None
    path, out = tmp_path / "bad-code.json", tmp_path / "not-created"
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError):
        plan.generate(
            code_bundle["source"],
            code_bundle["source_hash"],
            code_bundle["review_path"],
            out,
            code_routing_review_path=path,
        )
    assert not out.exists()


def test_code_routing_cannot_overlap_human_routing(code_bundle: dict[str, Any]) -> None:
    task = code_bundle["code_review"]["tasks"][0]
    overlap: dict[str, dict[str, dict[str, Any]]] = {task["task_id"]: {task["criteria"][0]["criterion_id"]: {}}}
    with pytest.raises(ValueError, match="overlaps"):
        plan.validate_code_routing_review(
            code_bundle["code_review"],
            code_bundle["rows"],
            code_bundle["source_bytes"],
            code_bundle["source_hash"],
            overlap,
        )


def test_code_route_declaration_cannot_turn_unsupported_pass_into_success(
    code_bundle: dict[str, Any], tmp_path: Path
) -> None:
    code = plan.validate_code_routing_review(
        code_bundle["code_review"], code_bundle["rows"], code_bundle["source_bytes"], code_bundle["source_hash"]
    )
    row, task = code_bundle["rows"][1], code_bundle["review"]["tasks"][1]
    criteria, _, candidate, protocol = plan.task_plan(
        row,
        task,
        code_bundle["source_hash"],
        "b" * 64,
        None,
        code_routing_items=code[row["task_id"]],
        code_routing_sha256="c" * 64,
    )
    effective = apply_inspection_protocol(
        [
            {
                "id": "code-1-0",
                "status": "pass",
                "reason": "The route permits source inspection.",
                "evidence": "Source files exist.",
                "observation_kind": "direct",
                "evidence_refs": [],
            }
        ],
        protocol=protocol,
        task_id=row["task_id"],
        task_criteria=criteria["tasks"][row["task_id"]],
        workspace=tmp_path,
        evidence_sha256=None,
        artifact_hashes=["d" * 64],
    )
    assert effective[0]["reported_status"] == "pass" and effective[0]["status"] == "unconfirmed"
    assert candidate["capability_acceptance"] == "unconfirmed"
    assert "does not establish execution" in " ".join(
        protocol["tasks"][row["task_id"]]["code-1-0"]["unconfirmed_conditions"]
    )


@pytest.mark.parametrize("identifier", sorted(plan.SCIENCE_IDS | plan.SCIENCE_BASELINE_COMPARISON_IDS))
def test_only_targeted_science_items_require_recorded_comparisons(identifier: str) -> None:
    row, task = inputs(["text/content"], identifier=identifier, task_id=plan.SCIENCE_TASK_ID)
    item = json.loads(row["rubric_json"])[0]
    result = plan.criterion_plan(item, task, task["rubric_routes"][0], None, "user")
    assert result["original_description"] == item["criterion"]
    assert result["runtime_rule_candidate"]["required_observations"] == {"pass": ["source_comparison"]}
    assert "research" in result["runtime_rule_candidate"]["required_methods"]
    task["task_id"] = "unrelated-task"
    unrelated = plan.criterion_plan(item, task, task["rubric_routes"][0], None, "user")
    assert "required_observations" not in unrelated["runtime_rule_candidate"]
