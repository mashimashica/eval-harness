# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Immutable run/evaluation artifact helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .errors import ArtifactError, OutputExistsError


def ensure_new_output(path: str | Path) -> Path:
    """Create a fresh output directory, refusing all existing paths."""

    output = Path(path).expanduser().resolve()
    if output.exists():
        raise OutputExistsError(f"output directory already exists; choose a new path: {output}")
    output.mkdir(parents=True)
    return output


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ArtifactError(f"cannot hash file {path}: {exc}") from exc
    return digest.hexdigest()


def write_json(path: str | Path, value: Any) -> None:
    """Write stable UTF-8 JSON suitable for later resumption or comparison."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
    temporary.replace(target)


def read_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"cannot read JSON artifact {path}: {exc}") from exc


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
    temporary.replace(target)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ArtifactError(f"cannot read JSONL artifact {target}: {exc}") from exc
    result: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ArtifactError(f"invalid JSONL at {target}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ArtifactError(f"JSONL row at {target}:{line_number} is not an object")
        result.append(value)
    return result


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ArtifactError(f"symbolic links are not allowed in captured artifacts: {path}")
        if path.is_file():
            yield path


def file_manifest(root: str | Path) -> list[dict[str, Any]]:
    """Return relative file metadata, sorted for deterministic hashes."""

    base = Path(root).resolve()
    entries: list[dict[str, Any]] = []
    for path in _iter_files(base):
        relative = path.relative_to(base).as_posix()
        entries.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return entries


def manifest_hash(entries: Sequence[Mapping[str, Any]]) -> str:
    encoded = json.dumps(entries, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return sha256_bytes(encoded)


def copy_files(source: str | Path, destination: str | Path) -> list[dict[str, Any]]:
    """Copy all files below *source* while refusing symlink escapes."""

    source_root = Path(source).resolve()
    destination_root = Path(destination).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    for path in _iter_files(source_root):
        relative = path.relative_to(source_root)
        target = destination_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return file_manifest(destination_root)


def copy_workspace_deliverables(
    workspace: str | Path,
    destination: str | Path,
    *,
    exclude_top_level: Sequence[str] = ("reference_files",),
) -> list[dict[str, Any]]:
    """Capture participant-created files, excluding staged context directories."""

    workspace_root = Path(workspace).resolve()
    destination_root = Path(destination).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    for path in _iter_files(workspace_root):
        relative = path.relative_to(workspace_root)
        if relative.parts and relative.parts[0] in exclude_top_level:
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        target = destination_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return file_manifest(destination_root)


def check_tree_unchanged(root: str | Path, before: list[Mapping[str, Any]]) -> bool:
    """Compare a tree against a prior manifest without mutating it."""

    return list(file_manifest(root)) == [dict(entry) for entry in before]
