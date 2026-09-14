# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Independent Skill creation and immutable Skill staging."""

from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import yaml

from .artifacts import (
    copy_files,
    ensure_new_output,
    file_manifest,
    manifest_hash,
    read_json,
    sha256_bytes,
    sha256_file,
    write_json,
)
from .config import RuntimeConfig, _mapping, _runtime, _string, _validate_runtime
from .errors import ArtifactError, ConfigError, HarnessError
from .executor import ExecutionRequest, Executor, preflight_executor

ExecutorFactory = Callable[[str], Executor]


@dataclass(frozen=True)
class BuildConfig:
    """A model-backed Skill creation configuration."""

    config_path: Path
    name: str
    runtime: RuntimeConfig
    prompt: str
    input_paths: tuple[Path, ...]
    skill_paths: tuple[Path, ...]
    raw: dict[str, Any]
    source_bytes: bytes


def _path_list(value: Any, field: str, base: Path) -> tuple[Path, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ConfigError(f"{field} must be a list of paths")
    paths: list[Path] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"{field}[{index}] must be a non-empty path")
        path = Path(item).expanduser()
        paths.append((path if path.is_absolute() else base / path).resolve())
    return tuple(paths)


def load_build_config(path: str | Path) -> BuildConfig:
    """Parse a creation config and resolve all file references to its directory."""

    config_path = Path(path).expanduser().resolve()
    try:
        source_bytes = config_path.read_bytes()
        loaded = yaml.safe_load(source_bytes) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read Skill build configuration {config_path}: {exc}") from exc
    raw = _mapping(loaded, "build configuration")
    runtime_value = raw.get("runtime", raw)
    runtime = _runtime(runtime_value, "build", base_dir=config_path.parent)
    prompt = _string(raw.get("prompt", raw.get("instructions")), "build.prompt")
    assert prompt is not None
    name = _string(raw.get("name"), "build.name", required=False) or config_path.stem
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        raise ConfigError("build.name must be a lowercase hyphenated Skill name of at most 64 characters")
    input_paths = _path_list(raw.get("inputs", raw.get("input_paths")), "build.inputs", config_path.parent)
    skill_paths = _path_list(raw.get("skills", raw.get("creator_skills")), "build.skills", config_path.parent)
    result = BuildConfig(config_path, name, runtime, prompt, input_paths, skill_paths, raw, source_bytes)
    errors = _validate_runtime(runtime, "build")
    errors.extend(f"build.inputs path does not exist: {path}" for path in input_paths if not path.exists())
    errors.extend(f"build.skills path does not exist: {path}" for path in skill_paths if not path.exists())
    names = [path.name for path in skill_paths]
    if len(set(names)) != len(names):
        errors.append("creator Skill directory names collide")
    for skill in skill_paths:
        if not skill.is_dir() or not (skill / "SKILL.md").is_file():
            errors.append(f"build.skills must name Skill directories containing SKILL.md: {skill}")
    if errors:
        raise ConfigError("Skill build configuration is invalid:\n" + "\n".join(f"- {error}" for error in errors))
    return result


def _copy_source(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ArtifactError(f"symbolic link is not allowed in Skill creation input: {source}")
    if source.is_dir():
        copy_files(source, destination)
    elif source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    else:
        raise ArtifactError(f"Skill creation input is not a regular file or directory: {source}")


def _source_manifest(paths: Sequence[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path),
            "kind": "directory" if path.is_dir() else "file",
            "sha256": manifest_hash(file_manifest(path)) if path.is_dir() else sha256_file(path),
        }
        for path in paths
    ]


def _validate_skill_document(path: Path, *, expected_name: str | None = None) -> dict[str, str]:
    """Validate the small Agent Skills frontmatter contract used by the harness."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactError(f"cannot read Skill instructions: {path}: {exc}") from exc
    if not text.startswith("---\n"):
        raise ArtifactError(f"Skill instructions need YAML frontmatter: {path}")
    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise ArtifactError(f"Skill instructions have an unterminated YAML frontmatter block: {path}")
    try:
        metadata = yaml.safe_load(text[4:closing]) or {}
    except yaml.YAMLError as exc:
        raise ArtifactError(f"Skill instructions have invalid YAML frontmatter: {path}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ArtifactError(f"Skill frontmatter must be a mapping: {path}")
    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        raise ArtifactError(f"Skill frontmatter name must be a non-empty string: {path}")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ArtifactError(f"Skill frontmatter description must be a non-empty string: {path}")
    if expected_name is not None and name.strip() != expected_name:
        raise ArtifactError(f"generated Skill frontmatter name {name!r} does not match build.name {expected_name!r}")
    return {"name": name.strip(), "description": description.strip()}


def _copy_created_skill(workspace: Path, output_dir: Path, *, expected_name: str) -> list[dict[str, Any]]:
    """Copy generated Skill files while excluding staged creation context."""

    named = workspace / expected_name
    if (workspace / "SKILL.md").is_file() and (named / "SKILL.md").is_file():
        raise ArtifactError("creator produced ambiguous root and named-folder Skills")
    if not (workspace / "SKILL.md").is_file() and (named / "SKILL.md").is_file():
        if named.is_symlink():
            raise ArtifactError("symbolic link in generated Skill")
        workspace = named
    generated = workspace / "SKILL.md"
    if not generated.is_file():
        raise ArtifactError("Skill creator completed without writing SKILL.md in its workspace")
    _validate_skill_document(generated, expected_name=expected_name)
    for source in sorted(workspace.rglob("*")):
        if source.is_symlink() or not source.is_file():
            if source.is_symlink():
                raise ArtifactError(f"symbolic link in generated Skill: {source}")
            continue
        relative = source.relative_to(workspace)
        if relative.parts and relative.parts[0] in {"creation_inputs", "creator_skills"}:
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    entries = [
        entry
        for entry in file_manifest(output_dir)
        if entry["path"] != "skill_manifest.json" and not str(entry["path"]).startswith(".creation/")
    ]
    if not any(entry.get("path") == "SKILL.md" for entry in entries):
        raise ArtifactError("generated Skill output does not contain SKILL.md")
    return entries


def freeze_build_config(config: BuildConfig, destination: Path) -> BuildConfig:
    """Freeze creation inputs and relative Skill links before any model invocation."""
    root = ensure_new_output(destination)
    for index, path in enumerate(config.input_paths):
        _copy_source(path, root / "inputs" / f"{index:03d}_{path.name}")
    for path in config.skill_paths:
        _copy_source(path, root / "skills" / path.name)
    snapshot = {
        "name": config.name,
        "runtime": {
            "executor": config.runtime.executor,
            "model": config.runtime.model,
            "settings": config.runtime.settings,
        },
        "prompt": config.prompt,
        "inputs": [f"inputs/{index:03d}_{path.name}" for index, path in enumerate(config.input_paths)],
        "skills": [f"skills/{path.name}" for path in config.skill_paths],
    }
    (root / "build.yaml").write_text(yaml.safe_dump(snapshot, sort_keys=False), encoding="utf-8")
    write_json(
        root / "source.json",
        {
            "config_path": str(config.config_path),
            "config_sha256": sha256_bytes(config.source_bytes),
            "creation_inputs": _source_manifest(config.input_paths),
            "creator_skills": _source_manifest(config.skill_paths),
        },
    )
    write_json(root / "input_manifest.json", file_manifest(root))
    return load_build_config(root / "build.yaml")


def _load_frozen_build(root: Path) -> BuildConfig:
    expected = read_json(root / "input_manifest.json")
    current = [item for item in file_manifest(root) if item["path"] != "input_manifest.json"]
    if current != expected:
        raise ArtifactError("saved Skill creation inputs changed")
    return load_build_config(root / "build.yaml")


def _run_creation(config: BuildConfig, output: Path, executor: Executor, *, check_auth: bool) -> Path:
    if check_auth:
        auth = preflight_executor(executor, config.runtime.model, config.runtime.settings, "skill_creation")
        if not auth.available or not auth.authenticated:
            raise HarnessError(f"Skill creator authentication is unavailable: {auth.detail}")
    manifest = read_json(output / "skill_manifest.json")
    attempt = int(manifest.get("attempt_count", 0))
    audit = output / ".creation" / "attempts" / str(attempt)
    audit.mkdir(parents=True, exist_ok=False)
    workspace = audit / "workspace"
    workspace.mkdir(mode=0o700)
    for index, source in enumerate(config.input_paths):
        _copy_source(source, workspace / "creation_inputs" / f"{index:03d}_{source.name}")
    for source in config.skill_paths:
        _copy_source(source, workspace / "creator_skills" / source.name)
    prompt = (
        "Create a reusable Codex/Claude Skill in the current workspace. Write SKILL.md with YAML frontmatter "
        f"name: {config.name} and a nonempty description, followed by complete instructions. "
        "Write supporting files only when needed. Apply all selected Skill instructions supplied below, "
        "loading their relevant supporting references from creator_skills/. Use the supplied creation_inputs/ "
        "for the brief and format requirements. Do not read outside the workspace. Do not include benchmark answers, "
        "grading materials, credentials, creation logs, or development instructions in the generated Skill.\n\n"
        f"Creation brief:\n{config.prompt}\n"
    )
    for source in config.skill_paths:
        relative = f"creator_skills/{source.name}/SKILL.md"
        prompt += f"\n\nSelected Skill instructions ({relative}):\n" + (workspace / relative).read_text(
            encoding="utf-8"
        )
    (audit / "prompt.txt").write_text(prompt, encoding="utf-8")
    manifest.update({"creator_status": "running", "attempt_count": attempt + 1})
    write_json(output / "skill_manifest.json", manifest)
    try:
        result = executor.execute(
            ExecutionRequest(prompt, workspace, config.runtime.model, config.runtime.settings, "skill_creation")
        )
        (audit / "events.jsonl").write_text(result.stdout, encoding="utf-8")
        (audit / "stderr.log").write_text(result.stderr, encoding="utf-8")
        (audit / "response.txt").write_text(result.parsed.final_text, encoding="utf-8")
        manifest.update(
            {
                "creator_status": result.status,
                "creator_returncode": result.returncode,
                "creator_elapsed_seconds": result.elapsed_seconds,
                "creator_error": result.error,
                "creator_usage": result.parsed.usage,
                "creator_cost_usd": result.parsed.usage.get("cost_usd"),
            }
        )
        manifest["workspace_files"] = file_manifest(workspace)
        write_json(audit / "execution.json", manifest)
        if result.status != "completed":
            raise HarnessError(result.error or "Skill creator did not complete")
        entries = _copy_created_skill(workspace, output, expected_name=config.name)
        manifest.update({"generated_files": entries, "generated_sha256": manifest_hash(entries)})
        write_json(output / "skill_manifest.json", manifest)
    except (Exception, KeyboardInterrupt) as exc:
        if manifest.get("creator_status") in {"running", "completed"}:
            manifest["creator_status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        manifest["creator_error"] = str(exc) or "creation interrupted"
        write_json(output / "skill_manifest.json", manifest)
        raise
    return output


def build_skill(
    config: BuildConfig,
    output_dir: str | Path,
    executor: Executor,
    *,
    check_auth: bool = True,
) -> Path:
    """Create a versioned Skill with hidden, isolated creation evidence."""
    output_path = Path(output_dir).expanduser().resolve()
    if output_path.name != config.name:
        raise ConfigError(f"Skill output directory must be named exactly build.name={config.name!r}")
    input_versions = _source_manifest(config.input_paths)
    creator_versions = _source_manifest(config.skill_paths)
    output = ensure_new_output(output_path)
    write_json(
        output / "skill_manifest.json",
        {
            "schema_version": 1,
            "creation_id": uuid.uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "name": config.name,
            "source_config": str(config.config_path),
            "config_sha256": sha256_bytes(config.source_bytes),
            "config_snapshot": config.raw,
            "runtime": {
                "executor": config.runtime.executor,
                "model": config.runtime.model,
                "settings": config.runtime.settings,
            },
            "creation_inputs": input_versions,
            "creator_skills": creator_versions,
            "creator_status": "preparing",
            "skill_delivery": "explicit SKILL.md bodies in prompt; supporting files staged",
            "attempt_count": 0,
        },
    )
    try:
        frozen = freeze_build_config(config, output / ".creation" / "config")
    except (Exception, KeyboardInterrupt) as exc:
        manifest = read_json(output / "skill_manifest.json")
        manifest.update(
            {
                "creator_status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                "creator_error": f"creation input setup failed before any model call: {exc}",
                "creation_snapshot_complete": False,
            }
        )
        write_json(output / "skill_manifest.json", manifest)
        raise
    manifest = read_json(output / "skill_manifest.json")
    manifest.update({"creator_status": "pending", "creation_snapshot_complete": True})
    write_json(output / "skill_manifest.json", manifest)
    return _run_creation(frozen, output, executor, check_auth=check_auth)


def resume_skill_build(output_dir: str | Path, executor: Executor, *, check_auth: bool = True) -> Path:
    """Resume an inline creation; successful Skills and all earlier attempts are preserved."""
    output = Path(output_dir).expanduser().resolve()
    manifest = read_json(output / "skill_manifest.json")
    if manifest.get("creator_status") == "completed":
        entries = [
            entry
            for entry in file_manifest(output)
            if entry["path"] != "skill_manifest.json" and not str(entry["path"]).startswith(".creation/")
        ]
        if manifest_hash(entries) != manifest.get("generated_sha256"):
            raise ArtifactError("saved generated Skill changed")
        return output
    if manifest.get("creation_snapshot_complete") is False:
        raise ArtifactError(
            "creation input snapshot is incomplete; no model was called; preserve this setup evidence and use a new build"
        )
    config = _load_frozen_build(output / ".creation" / "config")
    count = int(manifest.get("attempt_count", 0))
    if count:
        audit = output / ".creation" / "attempts" / str(count - 1)
        execution_path = audit / "execution.json"
        if execution_path.is_file():
            execution = read_json(execution_path)
            if execution.get("creator_status") == "completed":
                workspace = audit / "workspace"
                expected = execution.get("workspace_files")
                if expected is None or file_manifest(workspace) != expected:
                    raise ArtifactError("completed creator workspace is unverified or changed; will not regenerate it")
                entries = _copy_created_skill(workspace, output, expected_name=config.name)
                manifest.update(execution)
                manifest.update(
                    creator_status="completed",
                    creator_error=None,
                    collection_resumed=True,
                    generated_files=entries,
                    generated_sha256=manifest_hash(entries),
                )
                write_json(output / "skill_manifest.json", manifest)
                return output
    return _run_creation(config, output, executor, check_auth=check_auth)


def stage_skill(source: Path, destination: Path) -> list[dict[str, Any]]:
    """Copy an existing Skill to an isolated run input and return its manifest."""

    source = source.expanduser().resolve()
    if not source.exists():
        raise ArtifactError(f"Skill path does not exist: {source}")
    if source.is_file() and source.name != "SKILL.md":
        raise ArtifactError(f"an application Skill file must be named SKILL.md: {source}")
    entries = (
        file_manifest(source)
        if source.is_dir()
        else [{"path": source.name, "bytes": source.stat().st_size, "sha256": sha256_file(source)}]
    )
    if source.is_file():
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination / source.name)
    else:
        copy_files(source, destination)
    _validate_skill_document(destination / "SKILL.md")
    return entries


def copy_skill_for_application(source: Path, destination: Path) -> list[dict[str, Any]]:
    """Copy only generated Skill content, excluding creation audit material."""

    source = source.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        if source.name != "SKILL.md":
            raise ArtifactError("an application Skill file must be named SKILL.md")
        shutil.copy2(source, destination / "SKILL.md")
    elif source.is_dir():
        excluded = {
            "skill_manifest.json",
            "application_skill.json",
            "creation_prompt.txt",
            "creation_events.jsonl",
            "creation_stderr.log",
            "creator_response.txt",
        }
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ArtifactError(f"symbolic link in Skill input: {path}")
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            if relative.parts and relative.parts[0].startswith("."):
                continue
            if relative.name in excluded:
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    else:
        raise ArtifactError(f"Skill path is not a regular file or directory: {source}")
    entries = file_manifest(destination)
    if not any(entry.get("path") == "SKILL.md" for entry in entries):
        raise ArtifactError(f"Skill does not contain SKILL.md: {source}")
    _validate_skill_document(destination / "SKILL.md")
    return entries
