# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Complete mandatory-object absence requires a captured actual package inspection."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from openpyxl import Workbook
from test_evaluation_panel import _criteria
from test_inspection_protocol import _evidence, _item, _protocol, _recapture, _task_criteria

from eval_harness.artifacts import read_json, read_jsonl, sha256_file, write_json, write_jsonl
from eval_harness.capability_inspection import InspectionTools
from eval_harness.errors import ConfigError
from eval_harness.inspection_observations import xlsx_pivot_absence
from eval_harness.inspection_protocol import apply_inspection_protocol, load_inspection_protocol

CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"


def _package(tmp_path: Path, *, scope: str = "submission") -> Path:
    path = tmp_path / scope / "book.xlsx"
    path.parent.mkdir(parents=True)
    workbook = Workbook()
    workbook.create_sheet("Known")["A1"] = 2
    workbook.save(path)
    return path


def _capture(tmp_path: Path, path: Path) -> tuple[str, dict[str, Any], dict[str, Any]]:
    _, reference = _evidence(tmp_path, path=path.relative_to(tmp_path).as_posix())
    result = InspectionTools(tmp_path, tmp_path / "private-state", {}).inspect_document(reference["path"])
    result["call_id"] = reference["call_id"]
    receipt_path = tmp_path / f".harness_evidence/receipts/{reference['call_id']}.json"
    receipt = read_json(receipt_path)
    receipt["result"] = result
    return _save_receipt(tmp_path, reference, receipt), reference, receipt


def _save_receipt(tmp_path: Path, reference: dict[str, Any], receipt: dict[str, Any]) -> str:
    receipt_path = tmp_path / f".harness_evidence/receipts/{reference['call_id']}.json"
    write_json(receipt_path, receipt)
    events_path = tmp_path / ".harness_evidence/events.jsonl"
    events = read_jsonl(events_path)
    for event in events:
        if event["call_id"] == reference["call_id"] and event["event"] == "finished":
            event["output_sha256"] = sha256_file(receipt_path)
    write_jsonl(events_path, events)
    return _recapture(tmp_path)


def _absence_protocol() -> dict[str, Any]:
    protocol = _protocol(methods=["structure", "content", "functional"])
    protocol["tasks"]["task-1"]["useful"]["decisive_absence"] = {
        "kind": "xlsx_pivot_tables",
        "procedure": "This criterion requires a PivotTable; complete absence establishes failure only.",
    }
    return protocol


def _apply(
    tmp_path: Path,
    digest: str,
    references: list[dict[str, Any]],
    *,
    status: str = "fail",
    kind: str = "direct",
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = {**_item(None, kind=kind), "status": status, "evidence_refs": references}
    return apply_inspection_protocol(
        [item],
        protocol=protocol or _absence_protocol(),
        task_id="task-1",
        task_criteria=_task_criteria(),
        workspace=tmp_path,
        evidence_sha256=digest,
        artifact_hashes=["a" * 64],
    )[0]


def test_actual_inspector_complete_absence_allows_only_declared_direct_failure(tmp_path: Path) -> None:
    digest, reference, _ = _capture(tmp_path, _package(tmp_path))
    protocol = _absence_protocol()
    assert load_inspection_protocol(protocol, tmp_path, _criteria()) == protocol
    failure = _apply(tmp_path, digest, [reference])
    assert failure["status"] == "fail" and failure["inspection_branch"] == "decisive_absence"
    assert failure["evidence_validation"]["issues"] == []
    for status, kind in (("pass", "direct"), ("fail", "inference"), ("unconfirmed", "direct")):
        assert _apply(tmp_path, digest, [reference], status=status, kind=kind)["status"] == "unconfirmed"
    protocol["tasks"]["task-1"]["useful"].pop("decisive_absence")
    assert _apply(tmp_path, digest, [reference], protocol=protocol)["status"] == "unconfirmed"


@pytest.mark.parametrize(
    "mutation", ["members", "inventories", "bytes", "path", "format", "failed", "stale", "journal", "missing_call"]
)
def test_incomplete_failed_or_unbound_inspection_cannot_establish_absence(tmp_path: Path, mutation: str) -> None:
    path = _package(tmp_path)
    digest, reference, receipt = _capture(tmp_path, path)
    if mutation == "members":
        receipt["result"]["members"].pop()
    elif mutation == "inventories":
        receipt["result"].pop("pivot_caches")
    elif mutation == "bytes":
        receipt["result"]["bytes"] += 1
    elif mutation == "path":
        receipt["result"]["path"] = "scratch/book.xlsx"
    elif mutation == "format":
        receipt["result"]["format"] = ".docx"
    elif mutation == "failed":
        receipt["failure"] = "inspection failed"
    elif mutation == "stale":
        path.write_bytes(path.read_bytes() + b"changed")
    elif mutation == "journal":
        receipt_path = tmp_path / f".harness_evidence/receipts/{reference['call_id']}.json"
        write_json(receipt_path, {**receipt, "result": {**receipt["result"], "pivot_tables": ["tampered"]}})
    else:
        reference["call_id"] = "absent"
    if mutation not in {"stale", "journal", "missing_call"}:
        digest = _save_receipt(tmp_path, reference, receipt)
    assert _apply(tmp_path, digest, [reference])["status"] == "unconfirmed"


def _alter_package(path: Path, mutation: str) -> None:
    with zipfile.ZipFile(path) as package:
        parts = {name: package.read(name) for name in package.namelist()}
    types = ElementTree.fromstring(parts["[Content_Types].xml"])
    if mutation in {"relocated_type", "relocated_xml", "unsupported_binary", "untyped", "entity"}:
        name = "xl/elsewhere/object.xml" if mutation != "unsupported_binary" else "xl/elsewhere/object.bin"
        parts[name] = (
            b'<pivotTableDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
            if mutation == "relocated_xml"
            else b"<object/>"
        )
        if mutation == "entity":
            parts[name] = b'<!DOCTYPE object [<!ENTITY x "x">]><object>&x;</object>'
        if mutation != "untyped":
            content_type = {
                "relocated_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.pivotTable+xml",
                "unsupported_binary": "application/octet-stream",
            }.get(mutation, "application/xml")
            ElementTree.SubElement(types, CT + "Override", PartName="/" + name, ContentType=content_type)
        else:
            parts["xl/elsewhere/object.unknown"] = parts.pop(name)
    elif mutation == "relationship":
        parts["xl/_rels/workbook.xml.rels"] = (
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/pivotTable" '
            b'Target="elsewhere/object.xml"/></Relationships>'
        )
    elif mutation == "worksheet_declaration":
        parts["xl/worksheets/sheet1.xml"] = (
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><pivotTableParts/></worksheet>'
        )
    elif mutation == "malformed_xml":
        parts["xl/styles.xml"] = b"<broken"
    elif mutation == "malformed_types":
        parts["[Content_Types].xml"] = b"<wrong/>"
    elif mutation == "wrong_workbook":
        parts["xl/workbook.xml"] = b"<wrong/>"
    elif mutation == "standard_pivot":
        parts["xl/pivotTables/pivotTable1.xml"] = b"<pivotTableDefinition/>"
    if mutation != "malformed_types":
        parts["[Content_Types].xml"] = ElementTree.tostring(types)
    with zipfile.ZipFile(path, "w") as package:
        for name, data in parts.items():
            package.writestr(name, data)
        if mutation == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate"):
                package.writestr("xl/styles.xml", parts["xl/styles.xml"])


@pytest.mark.parametrize(
    "mutation",
    [
        "relocated_type",
        "relocated_xml",
        "relationship",
        "worksheet_declaration",
        "standard_pivot",
        "unsupported_binary",
        "untyped",
        "entity",
        "malformed_xml",
        "malformed_types",
        "wrong_workbook",
        "duplicate",
    ],
)
def test_empty_prefix_list_is_insufficient_for_whole_package_absence(tmp_path: Path, mutation: str) -> None:
    path = _package(tmp_path)
    _alter_package(path, mutation)
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
    # Even a fully hash-bound but incomplete old inspector result cannot hide a
    # relocated part/declaration. Some malformed fixtures would fail inspection
    # earlier; the checker must still reject this stronger forged-empty claim.
    result = {
        "path": "submission/book.xlsx",
        "format": ".xlsx",
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "members": names,
        "pivot_tables": [],
        "pivot_caches": [],
    }
    receipt = {
        "tool": "inspect_document",
        "arguments": {"path": "submission/book.xlsx"},
        "failure": None,
        "result": result,
    }
    assert not xlsx_pivot_absence(receipt, path, "submission/book.xlsx", sha256_file(path))


def test_pairwise_absence_does_not_transfer_and_shell_empty_query_is_insufficient(tmp_path: Path) -> None:
    _, reference_a, _ = _capture(tmp_path, _package(tmp_path, scope="submission_A"))
    digest, reference_b, _ = _capture(tmp_path, _package(tmp_path, scope="submission_B"))
    assert _apply(tmp_path, digest, [reference_a])["status"] == "unconfirmed"
    assert _apply(tmp_path, digest, [reference_a, reference_b])["status"] == "fail"
    digest, shell = _evidence(tmp_path, path="submission_A/book.xlsx", tool="shell")
    shell["method"] = "structure"
    assert _apply(tmp_path, digest, [shell, reference_b])["status"] == "unconfirmed"


def test_empty_workbook_cannot_hide_another_submission_artifact(tmp_path: Path) -> None:
    digest, reference, _ = _capture(tmp_path, _package(tmp_path))
    response = tmp_path / "submission/agent_response.txt"
    response.write_text("Controller-captured final response text.")
    assert _apply(tmp_path, digest, [reference])["status"] == "fail"
    response.write_bytes(b"\xffnot UTF-8")
    assert _apply(tmp_path, digest, [reference])["status"] == "unconfirmed"
    response.write_text("Controller-captured final response text.")
    other = tmp_path / "submission/other.xlsx"
    other.write_bytes((tmp_path / reference["path"]).read_bytes())
    assert _apply(tmp_path, digest, [reference])["status"] == "unconfirmed"
    digest, other_reference, _ = _capture(tmp_path, other)
    assert _apply(tmp_path, digest, [reference, other_reference])["status"] == "fail"
    (tmp_path / "submission/uninspected.xlsb").write_bytes(b"unsupported binary workbook")
    assert _apply(tmp_path, digest, [reference, other_reference])["status"] == "unconfirmed"


@pytest.mark.parametrize("mutation", ["crc", "truncated", "expanded_limit"])
def test_damaged_or_oversized_package_never_counts_as_absent(tmp_path: Path, mutation: str) -> None:
    path = _package(tmp_path)
    _, _, receipt = _capture(tmp_path, path)
    if mutation == "crc":
        with zipfile.ZipFile(path) as package:
            parts = {name: package.read(name) for name in package.namelist()}
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as package:
            for name, content in parts.items():
                package.writestr(name, content)
        data = path.read_bytes()
        index = data.index(b"<styleSheet")
        path.write_bytes(data[:index] + b"X" + data[index + 1 :])
    elif mutation == "truncated":
        path.write_bytes(path.read_bytes()[:-30])
    else:
        with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_DEFLATED) as package:
            package.writestr("huge.xml", b" " * (33 * 1024 * 1024))
        with zipfile.ZipFile(path) as package:
            receipt["result"]["members"] = package.namelist()
    receipt["result"].update(bytes=path.stat().st_size, sha256=sha256_file(path))
    assert not xlsx_pivot_absence(receipt, path, "submission/book.xlsx", sha256_file(path))


@pytest.mark.parametrize(
    "mutation", ["human", "pending", "or", "missing_procedure", "unknown_kind", "wrong_type", "no_structure"]
)
def test_absence_rule_cannot_bypass_human_pending_or_alternative_gates(tmp_path: Path, mutation: str) -> None:
    protocol = _absence_protocol()
    rule = protocol["tasks"]["task-1"]["useful"]
    if mutation == "human":
        rule["required_methods"] = ["human"]
    elif mutation == "pending":
        rule["pending_reason"] = "Native operation missing"
    elif mutation == "or":
        rule["machine_alternative"] = {"condition": "Another branch suffices", "required_methods": ["structure"]}
    elif mutation == "missing_procedure":
        rule["decisive_absence"]["procedure"] = " "
    elif mutation == "unknown_kind":
        rule["decisive_absence"]["kind"] = "arbitrary_empty_query"
    elif mutation == "no_structure":
        rule["required_methods"] = ["functional"]
    else:
        rule["decisive_absence"] = []
    with pytest.raises(ConfigError, match="decisive_absence"):
        load_inspection_protocol(protocol, tmp_path, _criteria())
