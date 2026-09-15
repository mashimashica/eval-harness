# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Freeze common PDF derivatives before independent incremental judge sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import copy_files, file_manifest, manifest_hash, read_json, sha256_file, write_json
from .capability_inspection import InspectionTools
from .errors import ArtifactError
from .office_rendering import OFFICE_SUFFIXES


def prepare_shared_previews(sources: Sequence[Path], cache: Path, settings: Mapping[str, Any]) -> None:
    if (cache / "manifest.json").exists():
        actual = [e for e in file_manifest(cache) if e["path"] != "manifest.json"]
        saved = read_json(cache / "manifest.json")
        if actual != saved["files"] or manifest_hash(actual) != saved.get("sha256"):
            raise ArtifactError("shared inspection previews changed; regeneration is forbidden")
        return
    cache.mkdir(parents=True, exist_ok=True)
    index: dict[str, Any] = {}
    for source in sources:
        if source.suffix.lower() not in {*OFFICE_SUFFIXES, ".pdf"}:
            continue
        key = sha256_file(source)
        if key in index:
            continue
        inspector = InspectionTools(source.parent, cache / "conversion" / key, settings)
        target = cache / "documents" / key
        try:
            pdf = inspector._pdf(source, target)
            index[key] = {
                "status": "completed",
                "path": str(pdf.relative_to(cache)),
                "sha256": sha256_file(pdf),
                "page_count": read_json(target / "conversion.json")["page_count"],
            }
        except Exception as exc:
            # A malformed submission is evidence to assess, not an invisible dropped sample.
            index[key] = {"status": "unavailable", "reason": str(exc), "source_sha256": key}
    write_json(cache / "index.json", index)
    entries = file_manifest(cache)
    write_json(cache / "manifest.json", {"files": entries, "sha256": manifest_hash(entries)})


def stage_shared_previews(workspace: Path, cache: Path, labels: Sequence[str]) -> None:
    if not cache.is_dir():
        return
    actual = [e for e in file_manifest(cache) if e["path"] != "manifest.json"]
    saved = read_json(cache / "manifest.json")
    if actual != saved["files"] or manifest_hash(actual) != saved.get("sha256"):
        raise ArtifactError("shared inspection cache changed")
    index = read_json(cache / "index.json")
    selected: dict[str, Any] = {}
    target = workspace / ".prepared_previews"
    target.mkdir(exist_ok=True)
    for label in labels:
        for source in (workspace / label).rglob("*"):
            if not source.is_file() or source.suffix.lower() not in {*OFFICE_SUFFIXES, ".pdf"}:
                continue
            key = sha256_file(source)
            entry = index.get(key)
            if entry is None:
                raise ArtifactError("shared inspection derivative is missing for a submitted document")
            if key not in selected and entry["status"] == "completed":
                copy_files(cache / "documents" / key, target / "documents" / key)
            selected[key] = entry
    write_json(target / "index.json", selected)
