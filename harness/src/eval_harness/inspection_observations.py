# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Item-bound observation completeness, never semantic verification.

These records are evaluator observations. Their shape cannot establish that a
comparison is correct, an input change is meaningful, or an application worked.
"""

from __future__ import annotations

import math
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping
from xml.etree import ElementTree

OBSERVATION_METHODS = {"source_comparison": "research", "input_change": "functional"}


def xlsx_pivot_absence(receipt: Mapping[str, Any], path: Path, relative: str, digest: str) -> bool:
    """Check a complete, captured XLSX inventory after the caller verifies its journal/hash.

    The inspector's prefix-filtered Pivot lists alone are insufficient: OPC parts
    can live elsewhere. Recheck every member's content type and XML declarations.
    Unsupported/oversized packages simply cannot use this optional failure route.
    This establishes object absence, never the truth of a behavioral pass.
    """
    result = receipt.get("result")
    if (
        receipt.get("tool") != "inspect_document"
        or receipt.get("failure") is not None
        or receipt.get("arguments") != {"path": relative}
        or not isinstance(result, Mapping)
        or result.get("path") != relative
        or result.get("sha256") != digest
        or result.get("format") != ".xlsx"
        or result.get("pivot_tables") != []
        or result.get("pivot_caches") != []
        or type(result.get("bytes")) is not int
        or result["bytes"] != path.stat().st_size
        or path.suffix.lower() != ".xlsx"
        or path.stat().st_size > 50 * 1024 * 1024
        or Path(relative).parts[0] not in {"submission", "submission_A", "submission_B"}
    ):
        return False
    try:
        with zipfile.ZipFile(path) as package:
            entries = package.infolist()
            names = package.namelist()
            if (
                result.get("members") != names
                or not {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"}.issubset(names)
                or len(entries) > 10000
                or sum(entry.file_size for entry in entries) > 32 * 1024 * 1024
                or len({name.casefold() for name in names}) != len(names)
                or any(
                    entry.flag_bits & 1
                    or "pivot" in entry.filename.lower()
                    or "\\" in entry.filename
                    or any(part in {"", ".", ".."} for part in entry.filename.rstrip("/").split("/"))
                    for entry in entries
                )
            ):
                return False

            def xml(data: bytes) -> ElementTree.Element:
                if b"\x00" in data or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                    raise ValueError("XML entities and non-UTF8-compatible encodings are unsupported")
                return ElementTree.fromstring(data)

            types = xml(package.read("[Content_Types].xml"))
            namespace = "{http://schemas.openxmlformats.org/package/2006/content-types}"
            if types.tag != namespace + "Types":
                return False
            defaults: dict[str, str] = {}
            overrides: dict[str, str] = {}
            for element in types:
                content_type = element.get("ContentType", "")
                if not content_type or "pivot" in content_type.lower():
                    return False
                if element.tag == namespace + "Default":
                    key, target = element.get("Extension", "").lower(), defaults
                elif element.tag == namespace + "Override":
                    name = element.get("PartName", "")
                    if not name.startswith("/") or name[1:] not in names:
                        return False
                    key, target = name[1:], overrides
                else:
                    return False
                if not key or key in target:
                    return False
                target[key] = content_type
            for entry in entries:
                if entry.is_dir():
                    if entry.file_size:
                        return False
                    continue
                # Reading all members also checks their CRC; no extraction occurs.
                data = package.read(entry)
                if entry.filename == "[Content_Types].xml":
                    continue
                extension = entry.filename.rsplit(".", 1)[-1].lower()
                content_type = overrides.get(entry.filename, defaults.get(extension, ""))
                if not content_type:
                    return False
                if content_type.startswith("image/"):
                    continue
                if not (content_type.endswith("+xml") or content_type in {"application/xml", "text/xml"}):
                    return False
                tree = xml(data)
                if entry.filename == "xl/workbook.xml" and tree.tag != (
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook"
                ):
                    return False
                for element in tree.iter():
                    if "pivot" in element.tag.lower() or any(
                        # Default cell/table style preferences are not objects.
                        marker in key.lower()
                        for key in element.attrib
                        for marker in ("pivottable", "pivotcache", "pivotsource")
                    ):
                        return False
                    if element.tag.endswith("}Relationship") and "pivot" in element.get("Type", "").lower():
                        return False
            return True
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
    ):
        return False


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
        and _observed_value(value.get("observed"))
    )


def _observed_value(value: Any) -> bool:
    """Require an actual value in the caller's already finite JSON record.

    Lists of passages and maps of located values need not be stringified. Empty,
    null or blank leaves alone cannot establish an observed source passage.
    """
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return any(_observed_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(_text(key) for key in value) and any(_observed_value(item) for item in value.values())
    return False


def _state(value: Any) -> bool:
    return (
        isinstance(value, Mapping) and _located_values(value.get("inputs")) and _located_values(value.get("outputs"))
    )


def _located_values(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(_text(location) for location in value)
