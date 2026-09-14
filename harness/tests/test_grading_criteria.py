# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from eval_harness.artifacts import file_manifest
from eval_harness.errors import ConfigError
from eval_harness.grading_criteria import criteria_for_task, criteria_hash, load_criteria, mechanical_findings


def policy(*rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "rubric-v1",
        "benchmark": "gdpval",
        "policy": {
            "arithmetic": "decimal",
            "rounding": "half_up",
            "decimal_places": 2,
            "absolute_tolerance": 0,
            "relative_tolerance": 0,
            "missing": "unconfirmed",
            "units": "USD",
        },
        "tasks": {"task-1": {"mechanical": list(rules), "ai": [{"id": "quality", "description": "Readable report."}]}},
    }


def rule(identifier: str, kind: str, **kwargs: Any) -> dict[str, Any]:
    return {"id": identifier, "description": identifier, "kind": kind, "path": "book.xlsx", **kwargs}


def test_excel_inspection_checks_units_rounding_sums_and_uncached_formulas_without_writes(tmp_path: Path) -> None:
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Totals"
    sheet.append(["USD", 1.235, 2, "=SUM(B1:C1)"])
    book.save(tmp_path / "book.xlsx")
    criteria = load_criteria(
        policy(
            rule("rounded", "xlsx_cell", sheet="Totals", cell="B1", expected=1.24, unit="USD", unit_cell="A1"),
            rule("wrong-unit", "xlsx_cell", sheet="Totals", cell="B1", expected=1.24, unit="JPY", unit_cell="A1"),
            rule("sum", "xlsx_sum", sheet="Totals", range="B1:C1", expected=3.24),
            rule("formula", "xlsx_cell", sheet="Totals", cell="D1", expected=3.24),
            rule("sheet", "sheet_exists", sheet="Totals"),
        ),
        tmp_path,
    )
    before = file_manifest(tmp_path)
    findings = mechanical_findings(tmp_path, criteria_for_task(criteria, "task-1", "gdpval"))
    assert [f["status"] for f in findings] == ["pass", "fail", "pass", "unconfirmed", "pass"]
    assert findings[0]["observed"] == "1.24"
    assert "unit" in findings[1]["reason"]
    assert "cached" in findings[3]["reason"]
    assert file_manifest(tmp_path) == before


def test_tolerance_and_declared_missing_policy(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text(json.dumps({"total": 101}))
    criteria = policy(rule("total", "json_number", key="total", expected=100))
    criteria["tasks"]["task-1"]["mechanical"][0]["path"] = "result.json"
    criteria["policy"].update(rounding="none", relative_tolerance=0.01, missing="fail")
    resolved = load_criteria(criteria, tmp_path)
    assert mechanical_findings(tmp_path, criteria_for_task(resolved, "task-1", "gdpval"))[0]["status"] == "pass"
    (tmp_path / "result.json").write_text("{}")
    assert mechanical_findings(tmp_path, criteria_for_task(resolved, "task-1", "gdpval"))[0]["status"] == "fail"


@pytest.mark.parametrize("payload", [b"not a zip", b"PK\x03\x04broken"])
def test_corrupt_workbook_is_unconfirmed(tmp_path: Path, payload: bytes) -> None:
    (tmp_path / "book.xlsx").write_bytes(payload)
    criteria = load_criteria(policy(rule("value", "xlsx_cell", sheet="Totals", cell="A1", expected=1)), tmp_path)
    assert mechanical_findings(tmp_path, criteria_for_task(criteria, "task-1", "gdpval"))[0]["status"] == "unconfirmed"


def test_criteria_are_detached_hashed_and_task_scoped(tmp_path: Path) -> None:
    raw = policy()
    resolved = load_criteria(raw, tmp_path)
    old_hash = criteria_hash(resolved)
    raw["version"] = "changed"
    assert criteria_hash(resolved) == old_hash
    assert criteria_hash(load_criteria(raw, tmp_path)) != old_hash
    with pytest.raises(ConfigError, match="cover task"):
        criteria_for_task(resolved, "other-task", "gdpval")
    with pytest.raises(ConfigError, match="benchmark"):
        criteria_for_task(resolved, "task-1", "gsm8k")
    assert "tasks" not in criteria_for_task(resolved, "task-1", "gdpval")


@pytest.mark.parametrize(
    "change",
    [
        {"absolute_tolerance": -1},
        {"relative_tolerance": float("nan")},
        {"rounding": "guess"},
        {"units": ""},
        {"missing": "pass"},
        {"decimal_places": True},
    ],
)
def test_invalid_policy_rejected_before_grading(tmp_path: Path, change: dict[str, Any]) -> None:
    criteria = policy()
    criteria["policy"].update(change)
    with pytest.raises(ConfigError):
        load_criteria(criteria, tmp_path)


def test_external_paths_and_ambiguous_file_selection(tmp_path: Path) -> None:
    criteria = policy(rule("file", "file_exists"))
    criteria["tasks"]["task-1"]["mechanical"][0]["path"] = "../outside"
    with pytest.raises(ConfigError, match="within"):
        load_criteria(criteria, tmp_path)
    (tmp_path / "book.xlsx").symlink_to(Path(__file__).resolve())
    resolved = load_criteria(policy(rule("file", "file_exists")), tmp_path)
    finding = mechanical_findings(tmp_path, criteria_for_task(resolved, "task-1", "gdpval"))[0]
    assert finding["status"] == "unconfirmed"
    assert "escapes" in finding["reason"]


def test_common_and_task_rules_cannot_reuse_item_ids(tmp_path: Path) -> None:
    criteria = policy()
    criteria["tasks"]["*"] = deepcopy(criteria["tasks"]["task-1"])
    resolved = load_criteria(criteria, tmp_path)
    with pytest.raises(ConfigError, match="collide"):
        criteria_for_task(resolved, "task-1", "gdpval")
