# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate recorded derivative provenance, without judging transformation truth.

The controller must verify the capability manifest, journal, and receipts before
passing ``verified_calls`` here. A successful recorded command and matching file
hashes bind an inspection claim to bytes; they do not prove that the command
actually produced those bytes from the declared originals.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import sha256_file
from .errors import ArtifactError

_MAX_RECORD_BYTES = 2 * 1024 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SCOPES = frozenset({"submission", "submission_A", "submission_B"})
_DERIVATION_KEYS = frozenset({"path", "sha256", "source_paths", "location"})


@dataclass(frozen=True)
class DerivedArtifact:
    """A validated declaration; ``scopes`` uses only this entry's sources."""

    path: str
    sha256: str
    source_paths: tuple[str, ...]
    location: str
    scopes: frozenset[str]


def _digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _workspace_file(workspace: Path, raw: Any) -> Path:
    if (
        not isinstance(raw, str)
        or not raw
        or "\\" in raw
        or "\x00" in raw
        or Path(raw).is_absolute()
        or any(part in {"", ".", ".."} for part in raw.split("/"))
    ):
        raise ArtifactError("lineage paths must be canonical workspace-relative paths")
    current = workspace
    for part in raw.split("/"):
        current /= part
        if current.is_symlink():
            raise ArtifactError("lineage path contains a symbolic link")
    if not current.is_file() or not current.resolve().is_relative_to(workspace.resolve()):
        raise ArtifactError("lineage file is missing or outside the workspace")
    return current


def _check_record_size(record: Mapping[str, Any]) -> None:
    size = 0
    try:
        for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(record):
            size += len(chunk.encode("utf-8"))
            if size > _MAX_RECORD_BYTES:
                raise ArtifactError("shell lineage record exceeds 2 MiB")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ArtifactError("shell lineage record must contain finite JSON values") from exc


def validate_derivations(record: Mapping[str, Any], workspace: Path) -> tuple[DerivedArtifact, ...]:
    """Validate an optional ``derived_artifacts`` field and its original files.

    Legacy records without that field return an empty tuple. The caller must
    separately validate the enclosing source/check/observation record. Every
    derivative has exactly path, sha256, source_paths, and location. Sources are
    canonical paths declared and hashed in this same record, and derivatives
    live under ``.harness_evidence/scratch/``. No basename or absolute aliases
    confer submission scope. Referenced supplied files may contribute no scope.
    """
    if "derived_artifacts" not in record:
        return ()
    _check_record_size(record)
    if (
        set(record) != {"schema_version", "source_artifacts", "checks", "derived_artifacts"}
        or type(record.get("schema_version")) is not int
        or record["schema_version"] != 1
    ):
        raise ArtifactError("shell lineage requires a versioned source/check/observation record")
    sources = record["source_artifacts"]
    entries = record["derived_artifacts"]
    if not isinstance(sources, list) or not sources or not isinstance(entries, list):
        raise ArtifactError("shell lineage sources and derived_artifacts must be lists")
    source_scopes: dict[str, str | None] = {}
    for source in sources:
        if (
            not isinstance(source, Mapping)
            or not {"path", "sha256"}.issubset(source)
            or set(source) - {"path", "sha256", "size", "bytes"}
        ):
            raise ArtifactError("shell lineage source has invalid fields")
        source_path = source["path"]
        original = _workspace_file(workspace, source_path)
        if source_path in source_scopes:
            raise ArtifactError("shell lineage repeats a source path")
        if not _digest(source["sha256"]) or sha256_file(original) != source["sha256"]:
            raise ArtifactError("shell lineage original hash is invalid or stale")
        for key in ("size", "bytes"):
            if key in source and (type(source[key]) is not int or source[key] != original.stat().st_size):
                raise ArtifactError("shell lineage original size is invalid or stale")
        parts = source_path.split("/")
        source_scopes[source_path] = parts[0] if len(parts) > 1 and parts[0] in _SCOPES else None
    result: list[DerivedArtifact] = []
    paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != _DERIVATION_KEYS:
            raise ArtifactError("derived artifact has invalid fields")
        path = entry["path"]
        derivative = _workspace_file(workspace, path)
        if Path(path).parts[:2] != (".harness_evidence", "scratch") or len(Path(path).parts) < 3:
            raise ArtifactError("derived artifact must use its canonical captured scratch path")
        if path in paths:
            raise ArtifactError("shell lineage repeats a derived artifact path")
        paths.add(path)
        if not _digest(entry["sha256"]) or sha256_file(derivative) != entry["sha256"]:
            raise ArtifactError("derived artifact hash is invalid or stale")
        source_paths = entry["source_paths"]
        if (
            not isinstance(source_paths, list)
            or not source_paths
            or any(not isinstance(value, str) or value not in source_scopes for value in source_paths)
            or len(set(source_paths)) != len(source_paths)
        ):
            raise ArtifactError("derived artifact sources must name distinct originals in this record")
        if not isinstance(entry["location"], str) or not entry["location"].strip():
            raise ArtifactError("derived artifact location is missing")
        result.append(
            DerivedArtifact(
                path=path,
                sha256=entry["sha256"],
                source_paths=tuple(source_paths),
                location=entry["location"],
                scopes=frozenset(scope for source in source_paths if (scope := source_scopes[source]) is not None),
            )
        )
    return tuple(result)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactError("shell lineage JSON repeats an object key")
        result[key] = value
    return result


def find_derived_scopes(
    view_source_sha256: str,
    workspace: Path,
    verified_calls: Mapping[str, Mapping[str, Any]],
    *,
    validate_record: Callable[[Path, Path], object],
) -> set[str]:
    """Find scopes for viewed bytes using controller-verified shell receipts.

    ``validate_record(path, workspace)`` must enforce the existing versioned
    source/check/observation guard. Its returned scopes are deliberately ignored:
    each matching derivative supplies its own explicit source membership. Failed
    calls, non-JSON streams, absent lineage, and unrelated hashes confer no scope.
    Malformed declared lineage raises ``ArtifactError`` and must not be promoted
    to a confirmed inspection. The caller must bind ``view_source_sha256`` to an
    actual successful view_image receipt before invoking this function.
    """
    if not _digest(view_source_sha256):
        raise ArtifactError("viewed source hash is invalid")
    scopes: set[str] = set()
    for call_id, receipt in verified_calls.items():
        if receipt.get("tool") != "shell" or receipt.get("failure") is not None:
            continue
        if receipt.get("call_id") != call_id:
            raise ArtifactError("shell lineage receipt has a mismatched call ID")
        result = receipt.get("result")
        if (
            not isinstance(result, Mapping)
            or result.get("status") != "completed"
            or type(result.get("returncode")) is not int
            or result["returncode"] != 0
        ):
            continue
        for stream in ("stdout", "stderr"):
            raw_path = result.get(f"captured_{stream}_path")
            if raw_path is None:
                continue
            captured = _workspace_file(workspace, raw_path)
            if (
                Path(raw_path).parts[:2] != (".harness_evidence", "outputs")
                or len(Path(raw_path).parts) != 3
                or not raw_path.endswith(f".{stream}.log")
            ):
                raise ArtifactError("shell lineage requires its canonical captured stream path")
            # A larger stream cannot be a bounded lineage record; do not parse it.
            if captured.stat().st_size > _MAX_RECORD_BYTES:
                continue
            with captured.open("rb") as handle:
                raw = handle.read(_MAX_RECORD_BYTES + 1)
            if len(raw) > _MAX_RECORD_BYTES:
                raise ArtifactError("shell lineage record exceeds 2 MiB")
            digest = result.get(f"{stream}_sha256")
            if not _digest(digest) or hashlib.sha256(raw).hexdigest() != digest:
                raise ArtifactError("shell lineage stream hash does not match its recorded result")
            try:
                record = json.loads(raw, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, UnicodeError, RecursionError):
                continue
            if not isinstance(record, Mapping) or "derived_artifacts" not in record:
                continue
            validate_record(captured, workspace)
            for derivative in validate_derivations(record, workspace):
                if derivative.sha256 == view_source_sha256:
                    scopes.update(derivative.scopes)
    return scopes
