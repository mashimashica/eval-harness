# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Inspection provenance checks use synthetic controller-captured receipts."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml
from openpyxl import Workbook
from test_evaluation_panel import _ApplicationExecutor, _criteria, _parsed, _run_source

from eval_harness.artifacts import (
    file_manifest,
    manifest_hash,
    read_json,
    read_jsonl,
    sha256_file,
    write_json,
    write_jsonl,
)
from eval_harness.config import EvaluationConfig, RuntimeConfig, evaluation_snapshot, load_evaluation_config
from eval_harness.errors import ArtifactError, ConfigError
from eval_harness.evaluate_pipeline import (
    _evaluation_config_from_snapshot,
    _inspection_prompt,
    _judge_response_schema,
    evaluate_run,
    parse_scalar_score,
    resume_evaluation,
)
from eval_harness.executor import ExecutionRequest, ExecutionResult
from eval_harness.grading_criteria import criteria_for_task, criteria_hash
from eval_harness.inspection_protocol import (
    apply_inspection_protocol,
    human_handoff,
    load_inspection_protocol,
    protocol_for_task,
    protocol_hash,
    protocol_prompt,
    validate_human_receipt,
)


def _protocol(*, methods: list[str] | None = None, inference: bool = False, human: bool = False) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "version": "inspection-v1",
        "criteria_sha256": criteria_hash(_criteria()),
        "tasks": {
            "task-1": {
                "useful": {
                    "required_methods": ["human"] if human else methods or ["structure"],
                    "acceptable_inference": {
                        "required_methods": ["structure"],
                        "description": "Only infer when the structure suffices.",
                    }
                    if inference
                    else None,
                    "unconfirmed_conditions": ["Missing inspection or evidence leaves this item unconfirmed."],
                    "human_review": {
                        "reviewer": "Assigned reviewer",
                        "procedure": "Review the original artifact against the unchanged criterion.",
                    }
                    if human
                    else None,
                }
            }
        },
    }


def _task_criteria() -> dict[str, Any]:
    value = criteria_for_task(_criteria(), "task-1", "gdpval")
    assert value is not None
    return value


def _recapture(workspace: Path) -> str:
    root = workspace / ".harness_evidence"
    entries = [entry for entry in file_manifest(root) if entry["path"] != "manifest.json"]
    write_json(root / "manifest.json", {"files": entries, "runtime": {"type": "harness.runtime"}})
    return manifest_hash(entries)


def _evidence(
    workspace: Path, *, path: str = "submission/document.docx", tool: str = "inspect_document"
) -> tuple[str, dict[str, Any]]:
    artifact = workspace / path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if not artifact.exists():
        artifact.write_bytes(b"frozen synthetic artifact bytes")
    journal = workspace / ".harness_evidence/events.jsonl"
    events = read_jsonl(journal) if journal.is_file() else []
    call_id = f"{1 + sum(event.get('event') == 'started' for event in events):06d}-test"
    result: dict[str, Any] = {"path": path, "sha256": sha256_file(artifact), "call_id": call_id}
    reference_path = path
    if tool == "shell":
        # Service call IDs and sandbox output UUIDs are intentionally distinct.
        reference_path = ".harness_evidence/outputs/f66611a4b73c47f4a35dfd02f0bb5e84.stdout.log"
        output = workspace / reference_path
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            output,
            {
                "schema_version": 1,
                "source_artifacts": [{"path": path, "sha256": sha256_file(artifact)}],
                "checks": [
                    {"action": "Applied the declared input change", "observation": "Recorded output changed to 10"}
                ],
            },
        )
        result = {
            "status": "completed",
            "returncode": 0,
            "stdout_sha256": sha256_file(output),
            "call_id": call_id,
            "captured_stdout_path": reference_path,
        }
    elif tool == "render_pages":
        result = {"source": path, "source_sha256": sha256_file(artifact), "page": 1, "call_id": call_id}
    arguments = {"path": path} if tool != "shell" else {"command": "exec python scratch/check.py"}
    root = workspace / ".harness_evidence"
    receipt = root / "receipts" / f"{call_id}.json"
    write_json(receipt, {"call_id": call_id, "tool": tool, "arguments": arguments, "failure": None, "result": result})
    write_jsonl(
        root / "events.jsonl",
        [
            *events,
            {"event": "started", "call_id": call_id, "tool": tool, "arguments": arguments},
            {
                "event": "finished",
                "call_id": call_id,
                "tool": tool,
                "arguments": arguments,
                "status": "completed",
                "failure": None,
                "output_path": f"/private/state/receipts/{call_id}.json",
                "output_sha256": sha256_file(receipt),
            },
        ],
    )
    reference = {
        "path": reference_path,
        "sha256": sha256_file(workspace / reference_path),
        "location": "whole document",
        "call_id": call_id,
        "method": {"inspect_document": "structure", "render_pages": "visual", "shell": "functional"}[tool],
    }
    return _recapture(workspace), reference


def _item(reference: dict[str, Any] | None, *, kind: str = "direct") -> dict[str, Any]:
    return {
        "id": "useful",
        "status": "pass",
        "evidence": "Observed artifact.",
        "reason": "It satisfies the criterion.",
        "observation_kind": kind,
        "evidence_refs": [] if reference is None else [reference],
    }


def _capture_shell_record(workspace: Path, reference: dict[str, Any], record: Any) -> str:
    output = workspace / reference["path"]
    # Deliberately allow nonfinite tokens here so rejection tests exercise the
    # captured input boundary, rather than the fixture JSON writer.
    output.write_text(json.dumps(record, allow_nan=True) + "\n")
    reference["sha256"] = sha256_file(output)
    receipt_path = workspace / f".harness_evidence/receipts/{reference['call_id']}.json"
    receipt = read_json(receipt_path)
    receipt["result"]["stdout_sha256"] = reference["sha256"]
    write_json(receipt_path, receipt)
    journal = workspace / ".harness_evidence/events.jsonl"
    events = read_jsonl(journal)
    for event in events:
        if event["call_id"] == reference["call_id"] and event["event"] == "finished":
            event["output_sha256"] = sha256_file(receipt_path)
    write_jsonl(journal, events)
    return _recapture(workspace)


def _apply(
    workspace: Path,
    digest: str | None,
    reference: dict[str, Any] | None,
    *,
    protocol: dict[str, Any] | None = None,
    kind: str = "direct",
    receipts: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    return apply_inspection_protocol(
        [_item(reference, kind=kind)],
        protocol=protocol or _protocol(),
        task_id="task-1",
        task_criteria=_task_criteria(),
        workspace=workspace,
        evidence_sha256=digest,
        artifact_hashes=["a" * 64],
        human_receipts=receipts,
    )[0]


def test_exact_protocol_coverage_and_unchanged_descriptions(tmp_path: Path) -> None:
    protocol = _protocol()
    assert load_inspection_protocol(protocol, tmp_path, _criteria()) == protocol
    assert protocol_for_task(protocol, "task-1", _task_criteria()) == protocol["tasks"]["task-1"]
    bad = copy.deepcopy(protocol)
    bad["tasks"]["task-1"]["useful"]["description"] = "Easier replacement"
    with pytest.raises(ConfigError, match="descriptions cannot change"):
        load_inspection_protocol(bad, tmp_path, _criteria())
    criteria = _criteria()
    criteria["tasks"]["*"]["ai"][0]["description"] = "Changed original description"
    with pytest.raises(ConfigError, match="original criteria hash"):
        load_inspection_protocol(protocol, tmp_path, criteria)
    for rules in ({}, {"unknown": protocol["tasks"]["task-1"]["useful"]}):
        bad = {**protocol, "tasks": {"task-1": rules}}
        with pytest.raises(ConfigError, match="exactly"):
            protocol_for_task(bad, "task-1", _task_criteria())


@pytest.mark.parametrize("format", ["json", "yaml"])
def test_protocol_file_inline_snapshot_and_restoration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, format: str
) -> None:
    import eval_harness.config as config_module

    monkeypatch.setattr(config_module, "environment_fingerprint", lambda value: "f" * 64)
    protocol_path = tmp_path / f"protocol.{format}"
    protocol_path.write_text(json.dumps(_protocol()) if format == "json" else yaml.safe_dump(_protocol()))
    config_path = tmp_path / "evaluation.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "method": "scalar",
                "executor": "codex",
                "model": "gpt-5.6-luna",
                "criteria": _criteria(),
                "inspection_protocol": protocol_path.name,
                "settings": {"environment": {"profile": "gdpval-v1", "network_domains": []}},
            }
        )
    )
    config = load_evaluation_config(config_path)
    snapshot = evaluation_snapshot(config)
    protocol_path.write_text("not: the original protocol")
    restored = _evaluation_config_from_snapshot(snapshot)
    assert restored.inspection_protocol == _protocol()
    snapshot["inspection_protocol"]["version"] = "caller mutation"
    assert config.inspection_protocol == _protocol()
    assert "inspection_protocol" not in evaluation_snapshot(
        EvaluationConfig("scalar", RuntimeConfig("codex", "gpt-5.6-luna", {}))
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing_ref",
        "missing_capture",
        "forged_call",
        "stale_file",
        "stale_hash",
        "wrong_method",
        "changed_capture",
        "bad_receipt_hash",
        "failed_call",
    ],
)
def test_unsupported_claims_are_unconfirmed(tmp_path: Path, fault: str) -> None:
    digest, reference = _evidence(tmp_path)
    root = tmp_path / ".harness_evidence"
    if fault == "missing_ref":
        reference = None  # type: ignore[assignment]
    elif fault == "missing_capture":
        digest = None  # type: ignore[assignment]
    elif fault == "forged_call":
        reference["call_id"] = "invented"
    elif fault == "stale_file":
        (tmp_path / reference["path"]).write_bytes(b"changed artifact")
    elif fault == "stale_hash":
        reference["sha256"] = "0" * 64
    elif fault == "wrong_method":
        reference["method"] = "visual"
    elif fault == "changed_capture":
        (root / "unexpected.bin").write_bytes(b"tamper")
    elif fault == "bad_receipt_hash":
        receipt = root / "receipts/000001-test.json"
        data = read_json(receipt)
        data["result"]["sha256"] = "0" * 64
        write_json(receipt, data)
        digest = _recapture(tmp_path)
    elif fault == "failed_call":
        events = read_jsonl(root / "events.jsonl")
        events[-1]["status"] = "failed"
        write_jsonl(root / "events.jsonl", events)
        digest = _recapture(tmp_path)
    item = _apply(tmp_path, digest, reference)
    assert item["status"] == "unconfirmed" and item["reported_status"] == "pass"
    assert item["evidence_validation"]["issues"]
    assert "hallucination" not in json.dumps(item)


def test_complete_direct_evidence_keeps_reported_assessment_without_claiming_truth(tmp_path: Path) -> None:
    digest, reference = _evidence(tmp_path)
    result = _apply(tmp_path, digest, reference)
    assert result["status"] == "pass" and result["observation_kind"] == "direct"
    assert result["evidence_validation"]["status"] == "referenced"
    assert "not semantic verification" in result["evidence_validation"]["scope"]


def test_inference_permission_and_alternative_methods(tmp_path: Path) -> None:
    digest, reference = _evidence(tmp_path)
    assert _apply(tmp_path, digest, reference, kind="inference")["status"] == "unconfirmed"
    protocol = _protocol(methods=["visual"], inference=True)
    assert _apply(tmp_path, digest, reference, protocol=protocol, kind="direct")["status"] == "unconfirmed"
    result = _apply(tmp_path, digest, reference, protocol=protocol, kind="inference")
    assert result["status"] == "pass" and result["observation_kind"] == "inference"


def test_functional_evidence_requires_actual_captured_successful_shell_output(tmp_path: Path) -> None:
    digest, reference = _evidence(tmp_path, tool="shell")
    result = _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))
    assert result["status"] == "pass"
    unrelated = tmp_path / "scratch/copied.txt"
    unrelated.parent.mkdir()
    unrelated.write_bytes((tmp_path / reference["path"]).read_bytes())
    reference["path"] = "scratch/copied.txt"
    assert _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))["status"] == "unconfirmed"


def test_bound_workbook_structured_observations_preserve_reported_assessment(tmp_path: Path) -> None:
    artifact = tmp_path / "submission/Dashboard Output.xlsx"
    artifact.parent.mkdir()
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Operator Output Data"
    sheet["E5"] = 950
    sheet["J5"] = "=AVERAGE(E5:I5)"
    dashboard = workbook.create_sheet("Dashboard")
    dashboard["D4"], dashboard["I4"] = 1, 1
    workbook.save(artifact)
    before = sha256_file(artifact)
    _, reference = _evidence(tmp_path, path="submission/Dashboard Output.xlsx", tool="shell")
    source = {"path": "submission/Dashboard Output.xlsx", "sha256": before, "size": artifact.stat().st_size}
    record = {
        "schema_version": 1,
        "source_artifacts": [source],
        "checks": [
            {"action": "enumerate submission files", "observation": [source]},
            {
                "action": "recalculate controlled scratch copies with LibreOffice Calc and compare outputs",
                "observation": {
                    "engine": "LibreOffice Calc via soffice --headless --convert-to xlsx",
                    "results": {
                        "daily": {
                            "inputs": {"D4": 1, "I4": 1, "E5": 1950, "E14": None},
                            "calculated": {"J5": 1144, "K5": 5720, "J14": None, "H20_H21": [948.6, 808.25]},
                        }
                    },
                    "empty_cell_details": {"text": "", "validations": [], "metadata": {}},
                    "matches_expected": True,
                },
            },
        ],
    }
    digest = _capture_shell_record(tmp_path, reference, record)
    result = _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))
    assert result["status"] == result["reported_status"] == "pass"
    assert result["evidence_validation"]["status"] == "referenced"
    assert "not semantic verification" in result["evidence_validation"]["scope"]
    assert sha256_file(artifact) == before


@pytest.mark.parametrize(
    "observation", ["observed", [None, "", [], {}], {"blank": None}, 0, -2, 0.0, 1.25, True, False]
)
def test_shell_accepts_nonempty_or_scalar_finite_json_observation(tmp_path: Path, observation: Any) -> None:
    _, reference = _evidence(tmp_path, tool="shell")
    record = read_json(tmp_path / reference["path"])
    record["checks"][0]["observation"] = observation
    digest = _capture_shell_record(tmp_path, reference, record)
    assert _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))["status"] == "pass"


@pytest.mark.parametrize(
    "observation",
    [None, "", " \n", [], {}, float("nan"), float("inf"), float("-inf"), [float("nan")], {"cells": [float("inf")]}],
)
def test_shell_rejects_empty_or_nonfinite_observation(tmp_path: Path, observation: Any) -> None:
    _, reference = _evidence(tmp_path, tool="shell")
    record = read_json(tmp_path / reference["path"])
    record["checks"][0]["observation"] = observation
    digest = _capture_shell_record(tmp_path, reference, record)
    item = _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))
    assert item["status"] == "unconfirmed"
    assert any("observation" in issue for issue in item["evidence_validation"]["issues"])


@pytest.mark.parametrize("keys", [("size",), ("bytes",), ("size", "bytes")])
@pytest.mark.parametrize("payload", [b"", b"source bytes"])
def test_shell_source_optional_sizes_bind_actual_file_bytes(
    tmp_path: Path, keys: tuple[str, ...], payload: bytes
) -> None:
    artifact = tmp_path / "submission/data.txt"
    artifact.parent.mkdir()
    artifact.write_bytes(payload)
    _, reference = _evidence(tmp_path, path="submission/data.txt", tool="shell")
    record = read_json(tmp_path / reference["path"])
    record["source_artifacts"][0].update({key: len(payload) for key in keys})
    digest = _capture_shell_record(tmp_path, reference, record)
    assert _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))["status"] == "pass"


@pytest.mark.parametrize("key", ["size", "bytes"])
@pytest.mark.parametrize("size", [-1, 0, 1.0, True, False, None, "31", float("inf")])
def test_shell_source_rejects_invalid_or_stale_optional_size(tmp_path: Path, key: str, size: Any) -> None:
    _, reference = _evidence(tmp_path, tool="shell")
    record = read_json(tmp_path / reference["path"])
    record["source_artifacts"][0][key] = size
    digest = _capture_shell_record(tmp_path, reference, record)
    item = _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))
    assert item["status"] == "unconfirmed"
    assert any("source" in issue for issue in item["evidence_validation"]["issues"])


@pytest.mark.parametrize("fault", ["unknown_key", "missing_path", "missing_sha256", "stale_sha256", "mixed_sizes"])
def test_shell_source_metadata_does_not_weaken_identity_contract(tmp_path: Path, fault: str) -> None:
    _, reference = _evidence(tmp_path, tool="shell")
    record = read_json(tmp_path / reference["path"])
    source = record["source_artifacts"][0]
    size = (tmp_path / source["path"]).stat().st_size
    source["size"] = size
    if fault == "unknown_key":
        source["format"] = "docx"
    elif fault.startswith("missing_"):
        source.pop(fault.removeprefix("missing_"))
    elif fault == "stale_sha256":
        source["sha256"] = "0" * 64
    else:
        source["bytes"] = size + 1
    digest = _capture_shell_record(tmp_path, reference, record)
    assert _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))["status"] == "unconfirmed"


@pytest.mark.parametrize(
    "check",
    [
        {"action": "", "observation": True},
        {"action": ["check"], "observation": True},
        {"action": "check", "observation": True, "extra": "unrecognized"},
        {"action": "check"},
        {"observation": True},
        None,
    ],
)
def test_structured_observations_keep_exact_check_and_action_contract(tmp_path: Path, check: Any) -> None:
    _, reference = _evidence(tmp_path, tool="shell")
    record = read_json(tmp_path / reference["path"])
    record["checks"] = [check]
    digest = _capture_shell_record(tmp_path, reference, record)
    assert _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))["status"] == "unconfirmed"


@pytest.mark.parametrize("fault", ["boolean_version", "unknown_version", "extra_key", "missing_sources", "no_checks"])
def test_structured_observations_keep_versioned_source_check_envelope(tmp_path: Path, fault: str) -> None:
    _, reference = _evidence(tmp_path, tool="shell")
    record = read_json(tmp_path / reference["path"])
    record["checks"][0]["observation"] = {"value": 0}
    if fault == "boolean_version":
        record["schema_version"] = True
    elif fault == "unknown_version":
        record["schema_version"] = 2
    elif fault == "extra_key":
        record["summary"] = "unrecognized"
    elif fault == "missing_sources":
        record.pop("source_artifacts")
    else:
        record["checks"] = []
    digest = _capture_shell_record(tmp_path, reference, record)
    assert _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))["status"] == "unconfirmed"


def test_human_only_remains_pending_without_matching_completed_external_receipt(tmp_path: Path) -> None:
    protocol = _protocol(human=True)
    digest, reference = _evidence(tmp_path)
    handoff = human_handoff(protocol, "task-1", _task_criteria()["ai"][0], "a" * 64)
    assert handoff["status"] == "pending" and handoff["reviewer"] == "Assigned reviewer"
    assert _apply(tmp_path, digest, reference, protocol=protocol)["status"] == "unconfirmed"
    assert validate_human_receipt(handoff, handoff)
    complete = {
        **handoff,
        "status": "completed",
        "decision": "fail",
        "completed_at": "2026-09-21T12:00:00+00:00",
        "evidence": "Named reviewer inspected the artifact and identified the missing requirement.",
        "handoff_sha256": criteria_hash(handoff),
    }
    assert validate_human_receipt(complete, handoff) == []
    assert _apply(tmp_path, digest, reference, protocol=protocol, receipts=(complete,))["status"] == "fail"
    for key in ("reviewer", "artifact_sha256", "criterion_sha256", "protocol_sha256", "procedure"):
        stale = {**complete, key: "stale"}
        assert validate_human_receipt(stale, handoff)
        assert _apply(tmp_path, digest, reference, protocol=protocol, receipts=(stale,))["status"] == "unconfirmed"


def test_unassigned_human_cannot_complete_review_despite_named_coordination_owner(tmp_path: Path) -> None:
    protocol = _protocol(human=True)
    human = protocol["tasks"]["task-1"]["useful"]["human_review"]
    human.update(reviewer=None, coordination_owner="Experiment owner")
    assert load_inspection_protocol(protocol, tmp_path, _criteria()) == protocol
    digest, reference = _evidence(tmp_path)
    handoff = human_handoff(protocol, "task-1", _task_criteria()["ai"][0], "a" * 64)
    attempted = {
        **handoff,
        "status": "completed",
        "decision": "pass",
        "completed_at": "2026-09-21T12:00:00+00:00",
        "evidence": "An unassigned review cannot establish a rating.",
        "handoff_sha256": criteria_hash(handoff),
    }
    assert any("unassigned" in error for error in validate_human_receipt(attempted, handoff))
    assert _apply(tmp_path, digest, reference, protocol=protocol, receipts=(attempted,))["status"] == "unconfirmed"
    human.pop("coordination_owner")
    with pytest.raises(ConfigError, match="coordination owner"):
        load_inspection_protocol(protocol, tmp_path, _criteria())


def test_native_schema_and_prompt_have_unambiguous_inspection_contract() -> None:
    schema = _judge_response_schema("scalar", _task_criteria(), allow_unconfirmed=True, inspection_protocol=True)
    item = schema["properties"]["criteria_results"]["items"]
    assert set(item["required"]) == {"id", "status", "evidence", "reason", "observation_kind", "evidence_refs"}
    assert schema["properties"]["score"]["type"] == ["number", "null"]
    prompt = _inspection_prompt(
        "Return exactly one JSON object with a numeric score between 0 and 1 and a short rationale."
    )
    assert "numeric score" not in prompt and "or null" in prompt
    inspection = protocol_prompt(_protocol(), _protocol()["tasks"]["task-1"])
    assert "nonempty string/list/object, finite number, or boolean" in inspection
    assert "nested null/empty JSON values" in inspection
    assert "nonnegative integers matching the original file size" in inspection
    assert "For all shell references, including structure checks" in inspection
    assert "For a derived scratch image or PDF" in inspection
    assert "location as a nonempty string" in inspection
    assert "not an object or list" in inspection
    assert "not a visual-method evidence reference" in inspection
    assert "cite the actual render_pages or view_image call" in inspection
    assert "with the visible scratch/... path during the session" in inspection
    assert "not a persistent evidence reference" in inspection
    assert "evidence_refs covering every required method" in inspection
    assert "match each original criterion ID to its own description" in inspection
    assert "modified state, not the original's unchanged layout or values" in inspection
    legacy = parse_scalar_score(
        json.dumps(
            {
                "score": 0.8,
                "rationale": "ok",
                "criteria_results": [{"id": "useful", "status": "pass", "evidence": "text", "reason": "ok"}],
            }
        ),
        _task_criteria(),
    )
    assert legacy.valid and legacy.score == 0.8


def test_shell_visual_self_report_is_not_promoted_by_an_additional_valid_render(tmp_path: Path) -> None:
    _, rendered = _evidence(tmp_path, tool="render_pages")
    digest, shell = _evidence(tmp_path, tool="shell")
    shell["method"] = "visual"
    item = _item(rendered)
    item["evidence_refs"].append(shell)
    result = apply_inspection_protocol(
        [item],
        protocol=_protocol(methods=["visual"]),
        task_id="task-1",
        task_criteria=_task_criteria(),
        workspace=tmp_path,
        evidence_sha256=digest,
        artifact_hashes=["a" * 64],
    )[0]
    assert result["status"] == "unconfirmed"
    assert result["evidence_validation"]["issues"] == [
        "evidence reference has no completed call of the required method"
    ]
    assert _apply(tmp_path, digest, rendered, protocol=_protocol(methods=["visual"]))["status"] == "pass"


@pytest.mark.parametrize("include_structure_reference", [False, True])
def test_one_performed_shell_record_needs_explicit_references_for_each_required_method(
    tmp_path: Path, include_structure_reference: bool
) -> None:
    _, reference = _evidence(tmp_path, path="submission/workbook.xlsx", tool="shell")
    record = read_json(tmp_path / reference["path"])
    record["checks"] = [
        {
            "action": "Enumerate worksheet names and read the data header cells",
            "observation": {"worksheets": ["Data"], "headers": {"A1": "Value", "B1": "Total"}},
        }
    ]
    digest = _capture_shell_record(tmp_path, reference, record)
    reference["method"] = "content"
    item = _item(reference)
    if include_structure_reference:
        item["evidence_refs"].append(
            {**reference, "method": "structure", "location": "checks[0].observation.worksheets"}
        )
    result = apply_inspection_protocol(
        [item],
        protocol=_protocol(methods=["structure", "content"]),
        task_id="task-1",
        task_criteria=_task_criteria(),
        workspace=tmp_path,
        evidence_sha256=digest,
        artifact_hashes=["a" * 64],
    )[0]
    assert result["status"] == ("pass" if include_structure_reference else "unconfirmed")
    assert result["reported_status"] == "pass"


class _InspectionExecutor(_ApplicationExecutor):
    def __init__(self, *, valid: bool, pairwise: bool = False) -> None:
        super().__init__()
        self.valid, self.pairwise = valid, pairwise

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.requests.append(request)
        path = "submission_A/answer.txt" if self.pairwise else "submission/answer.txt"
        digest, reference = _evidence(request.cwd, path=path)
        response = (
            {"winner": "A", "rationale": "Observed the artifact."}
            if self.pairwise
            else {"score": 0.8, "rationale": "Observed the artifact."}
        )
        criterion = _item(reference if self.valid else None)
        if self.valid and self.pairwise:
            digest, second = _evidence(request.cwd, path="submission_B/answer.txt")
            criterion["evidence_refs"].append(second)
        response["criteria_results"] = [criterion]  # type: ignore[assignment]
        text = json.dumps(response)
        parsed = _parsed(text)
        parsed = replace(
            parsed,
            events=(
                {"type": "harness.runtime", "environment_profile": "gdpval-v1", "evidence_sha256": digest},
                *parsed.events,
            ),
        )
        return ExecutionResult(
            ("fixture",), 0, "completed", 0.01, "\n".join(json.dumps(event) for event in parsed.events), "", parsed
        )


def _config(*, pairwise: bool = False) -> EvaluationConfig:
    runtime = RuntimeConfig(
        "codex",
        "gpt-5.6-luna",
        {"timeout_seconds": 10, "environment": {"profile": "gdpval-v1", "network_domains": []}},
    )
    return EvaluationConfig(
        "pairwise" if pairwise else "scalar", runtime, criteria=_criteria(), inspection_protocol=_protocol()
    )


@pytest.mark.parametrize("pairwise", [False, True])
def test_pipeline_preserves_raw_response_but_withholds_unsupported_effective_scores(
    tmp_path: Path, pairwise: bool
) -> None:
    run, application = _run_source(tmp_path)
    count = len(application.requests)
    evaluator = _InspectionExecutor(valid=False, pairwise=pairwise)
    summary = evaluate_run(run, _config(pairwise=pairwise), tmp_path / "evaluation", evaluator, check_auth=False)
    rows = read_jsonl(summary.evaluation_dir / "judgments.jsonl")
    assert len(application.requests) == count
    assert rows and all(row["criteria_results"][0]["status"] == "unconfirmed" for row in rows)
    assert all(row["score"] is None and not row["score_valid"] for row in rows)
    if pairwise:
        assert all(row["winner"] == "unjudgeable" and row["reported_winner"] == "A" for row in rows)
    else:
        assert all(row["reported_score"] == 0.8 for row in rows)
    original = json.loads((summary.evaluation_dir / rows[0]["judge_response_path"]).read_text())
    assert original["criteria_results"][0]["status"] == "pass"
    assert all(row["inspection_protocol_sha256"] == protocol_hash(_protocol()) for row in rows)


def test_protocol_resume_uses_frozen_saved_artifacts_and_refuses_protocol_mutation(tmp_path: Path) -> None:
    run, application = _run_source(tmp_path)
    config = _config()
    count = len(application.requests)
    prepared = evaluate_run(run, config, tmp_path / "evaluation", check_auth=False, _prepare_only=True)
    evaluator = _InspectionExecutor(valid=True)
    assert config.inspection_protocol is not None
    config.inspection_protocol["version"] = "changed caller config"
    result = resume_evaluation(prepared.evaluation_dir, evaluator, check_auth=False)
    assert result.status == "completed" and len(evaluator.requests) == 2
    assert len(application.requests) == count
    rows = read_jsonl(result.evaluation_dir / "judgments.jsonl")
    assert all(row["score"] == 0.8 and row["score_valid"] for row in rows)
    assert all("captured_stdout_path" in request.prompt for request in evaluator.requests)
    assert all("original criterion descriptions remain unchanged" in request.prompt for request in evaluator.requests)
    calls = len(evaluator.requests)
    resume_evaluation(prepared.evaluation_dir, evaluator, check_auth=False)
    assert len(evaluator.requests) == calls
    path = prepared.evaluation_dir / "inspection_protocol_snapshot.json"
    frozen = read_json(path)
    frozen["inspection_protocol"]["version"] = "tampered"
    write_json(path, frozen)
    with pytest.raises(ArtifactError, match="inspection protocol snapshot changed"):
        resume_evaluation(prepared.evaluation_dir, evaluator, check_auth=False)


def test_missing_new_response_fields_are_unconfirmed_instead_of_accepted(tmp_path: Path) -> None:
    digest, _ = _evidence(tmp_path)
    response = {
        "score": 1,
        "rationale": "Claims success",
        "criteria_results": [
            {"id": "useful", "status": "pass", "evidence": "Unsupported claim", "reason": "Claims completion"}
        ],
    }
    parsed = parse_scalar_score(json.dumps(response), _task_criteria(), inspection_protocol=True)
    assert parsed.valid
    result = apply_inspection_protocol(
        parsed.criteria_results or (),
        protocol=_protocol(),
        task_id="task-1",
        task_criteria=_task_criteria(),
        workspace=tmp_path,
        evidence_sha256=digest,
        artifact_hashes=["a" * 64],
    )
    assert result[0]["status"] == "unconfirmed"


def test_pairwise_requires_inspection_of_both_anonymous_submissions(tmp_path: Path) -> None:
    (tmp_path / "submission_B").mkdir()
    (tmp_path / "submission_B" / "other.docx").write_bytes(b"other artifact")
    digest, reference = _evidence(tmp_path, path="submission_A/document.docx")
    result = _apply(tmp_path, digest, reference)
    assert result["status"] == "unconfirmed"
    assert any("submission_B" in message for message in result["evidence_validation"]["issues"])
    digest, other = _evidence(tmp_path, path="submission_B/other.docx")
    item = _item(reference)
    item["evidence_refs"].append(other)
    result = apply_inspection_protocol(
        [item],
        protocol=_protocol(),
        task_id="task-1",
        task_criteria=_task_criteria(),
        workspace=tmp_path,
        evidence_sha256=digest,
        artifact_hashes=["a" * 64, "b" * 64],
    )[0]
    assert result["status"] == "pass"


def test_pairwise_valid_evidence_preserves_winner_and_resume_rejects_changed_capture(tmp_path: Path) -> None:
    run, _ = _run_source(tmp_path)
    evaluator = _InspectionExecutor(valid=True, pairwise=True)
    result = evaluate_run(run, _config(pairwise=True), tmp_path / "evaluation", evaluator, check_auth=False)
    rows = read_jsonl(result.evaluation_dir / "judgments.jsonl")
    assert all(row["winner"] == "A" and row["score_valid"] for row in rows)
    workspace = result.evaluation_dir / Path(rows[0]["judge_response_path"]).parent / "workspace"
    (workspace / ".harness_evidence" / "tampered.txt").write_text("changed")
    with pytest.raises(ArtifactError, match="evidence changed"):
        resume_evaluation(result.evaluation_dir, evaluator, check_auth=False)


def test_shell_existence_without_performed_check_record_is_unconfirmed(tmp_path: Path) -> None:
    digest, reference = _evidence(tmp_path, tool="shell")
    output = tmp_path / reference["path"]
    output.write_text("shell merely started")
    reference["sha256"] = sha256_file(output)
    receipt_path = tmp_path / ".harness_evidence/receipts/000001-test.json"
    receipt = read_json(receipt_path)
    receipt["result"]["stdout_sha256"] = reference["sha256"]
    write_json(receipt_path, receipt)
    journal = tmp_path / ".harness_evidence/events.jsonl"
    events = read_jsonl(journal)
    events[-1]["output_sha256"] = sha256_file(receipt_path)
    write_jsonl(journal, events)
    digest = _recapture(tmp_path)
    item = _apply(tmp_path, digest, reference, protocol=_protocol(methods=["functional"]))
    assert item["status"] == "unconfirmed"


def test_failed_http_response_cannot_supply_required_research_evidence(tmp_path: Path) -> None:
    digest, reference = _evidence(tmp_path)
    receipt_path = tmp_path / ".harness_evidence/receipts/000001-test.json"
    receipt = read_json(receipt_path)
    receipt["tool"] = "fetch"
    receipt["result"]["status"] = 403
    receipt["result"]["http_error"] = True
    write_json(receipt_path, receipt)
    journal = tmp_path / ".harness_evidence/events.jsonl"
    events = read_jsonl(journal)
    for event in events:
        event["tool"] = "fetch"
    events[-1]["output_sha256"] = sha256_file(receipt_path)
    write_jsonl(journal, events)
    digest = _recapture(tmp_path)
    reference["method"] = "research"
    assert _apply(tmp_path, digest, reference, protocol=_protocol(methods=["research"]))["status"] == "unconfirmed"


@pytest.mark.parametrize(
    "method,filename",
    [("content", "notes.txt"), ("content", "script.py"), ("structure", "image.psd"), ("structure", "assembly.step")],
)
def test_shell_content_and_structure_use_returned_capture_path_not_service_call_id(
    tmp_path: Path,
    method: str,
    filename: str,
) -> None:
    digest, reference = _evidence(tmp_path, path=f"submission/{filename}", tool="shell")
    assert reference["call_id"] not in reference["path"]
    reference["method"] = method
    protocol = _protocol(methods=[method])
    assert load_inspection_protocol(protocol, tmp_path, _criteria()) == protocol
    assert _apply(tmp_path, digest, reference, protocol=protocol)["status"] == "pass"


@pytest.mark.parametrize("source_root", ["reference_files", "research/submission", ".harness_evidence/research"])
def test_shell_source_comparison_binds_recorded_source(tmp_path: Path, source_root: str) -> None:
    digest, reference = _evidence(tmp_path, path="submission/report.txt", tool="shell")
    reference["method"] = "research"
    protocol = _protocol(methods=["research"])
    assert _apply(tmp_path, digest, reference, protocol=protocol)["status"] == "unconfirmed"
    source = tmp_path / source_root / "source.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("supplied original source")
    output = tmp_path / reference["path"]
    record = read_json(output)
    record["source_artifacts"].append({"path": source.relative_to(tmp_path).as_posix(), "sha256": sha256_file(source)})
    record["checks"] = [
        {"action": "Compared supplied source with the report", "observation": "Recorded the matching quotation"}
    ]
    write_json(output, record)
    reference["sha256"] = sha256_file(output)
    receipt_path = tmp_path / ".harness_evidence/receipts/000001-test.json"
    receipt = read_json(receipt_path)
    receipt["result"]["stdout_sha256"] = reference["sha256"]
    write_json(receipt_path, receipt)
    journal = tmp_path / ".harness_evidence/events.jsonl"
    events = read_jsonl(journal)
    events[-1]["output_sha256"] = sha256_file(receipt_path)
    write_jsonl(journal, events)
    digest = _recapture(tmp_path)
    assert _apply(tmp_path, digest, reference, protocol=protocol)["status"] == "pass"
    assert {event["tool"] for event in events} == {"shell"}
    source.write_text("changed source")
    assert _apply(tmp_path, digest, reference, protocol=protocol)["status"] == "unconfirmed"


def test_pending_inspection_route_cannot_be_accepted_by_valid_model_evidence(tmp_path: Path) -> None:
    digest, reference = _evidence(tmp_path)
    protocol = _protocol()
    protocol["tasks"]["task-1"]["useful"]["pending_reason"] = "Native update route needs verification."
    assert load_inspection_protocol(protocol, tmp_path, _criteria()) == protocol
    result = _apply(tmp_path, digest, reference, protocol=protocol)
    assert result["reported_status"] == "pass"
    assert result["status"] == "unconfirmed"
    assert result["evidence_validation"]["issues"] == [
        "inspection prerequisite remains pending: Native update route needs verification."
    ]
    resolved = copy.deepcopy(protocol)
    resolved["version"] = "inspection-v2-route-verified"
    del resolved["tasks"]["task-1"]["useful"]["pending_reason"]
    assert protocol_hash(resolved) != protocol_hash(protocol)
    assert _apply(tmp_path, digest, reference, protocol=resolved)["status"] == "pass"


@pytest.mark.parametrize("reason", [None, "", "  ", False, [], {"claim": "ready"}])
def test_pending_route_requires_a_concrete_reason(tmp_path: Path, reason: Any) -> None:
    protocol = _protocol()
    protocol["tasks"]["task-1"]["useful"]["pending_reason"] = reason
    with pytest.raises(ConfigError, match="pending_reason"):
        load_inspection_protocol(protocol, tmp_path, _criteria())


@pytest.mark.parametrize(
    "status,expected", [("pass", "pass"), ("fail", "unconfirmed"), ("unconfirmed", "unconfirmed")]
)
@pytest.mark.parametrize("primary", ["human", "pending_functional"])
def test_original_or_allows_only_positive_verified_machine_alternative(
    tmp_path: Path, status: str, expected: str, primary: str
) -> None:
    protocol = _protocol(human=primary == "human", methods=["functional"])
    rule = protocol["tasks"]["task-1"]["useful"]
    rule["machine_alternative"] = {
        "condition": "The original explicitly accepts this observed static alternative.",
        "required_methods": ["structure"],
    }
    if primary == "pending_functional":
        rule["pending_reason"] = "The alternative native control route is not verified."
    else:
        rule["human_review"].update(reviewer=None, coordination_owner="user")
    assert load_inspection_protocol(protocol, tmp_path, _criteria()) == protocol
    digest, reference = _evidence(tmp_path)
    reported = _item(reference)
    reported["status"] = status
    result = apply_inspection_protocol(
        [reported],
        protocol=protocol,
        task_id="task-1",
        task_criteria=_task_criteria(),
        workspace=tmp_path,
        evidence_sha256=digest,
        artifact_hashes=["a" * 64],
    )[0]
    assert result["status"] == expected
    assert result["reported_status"] == status
    assert result["inspection_branch"] == "machine_alternative"
    stale = {**reference, "sha256": "0" * 64}
    assert _apply(tmp_path, digest, stale, protocol=protocol)["status"] == "unconfirmed"
    assert _apply(tmp_path, digest, None, protocol=protocol)["status"] == "unconfirmed"
    assert _apply(tmp_path, digest, reference, protocol=protocol, kind="inference")["status"] == "unconfirmed"


def test_completed_human_decision_covers_original_or_and_has_priority(tmp_path: Path) -> None:
    protocol = _protocol(human=True)
    protocol["tasks"]["task-1"]["useful"]["machine_alternative"] = {
        "condition": "The original permits a documented static alternative.",
        "required_methods": ["structure"],
    }
    digest, reference = _evidence(tmp_path)
    assert _apply(tmp_path, digest, reference, protocol=protocol)["status"] == "pass"
    handoff = human_handoff(protocol, "task-1", _task_criteria()["ai"][0], "a" * 64)
    complete = {
        **handoff,
        "status": "completed",
        "decision": "fail",
        "completed_at": "2026-09-21T12:00:00+00:00",
        "evidence": "Both original alternatives were inspected and failed.",
        "handoff_sha256": criteria_hash(handoff),
    }
    result = _apply(tmp_path, digest, reference, protocol=protocol, receipts=(complete,))
    assert result["status"] == "fail"
    assert "inspection_branch" not in result


@pytest.mark.parametrize(
    "alternative",
    [
        None,
        {},
        {"condition": "", "required_methods": ["structure"]},
        {"condition": "Any", "required_methods": ["human"]},
        {"condition": "Any", "required_methods": []},
    ],
)
def test_machine_alternative_requires_sufficient_original_condition_and_nonhuman_methods(
    tmp_path: Path, alternative: Any
) -> None:
    protocol = _protocol(human=True)
    protocol["tasks"]["task-1"]["useful"]["machine_alternative"] = alternative
    with pytest.raises(ConfigError, match="machine_alternative"):
        load_inspection_protocol(protocol, tmp_path, _criteria())
