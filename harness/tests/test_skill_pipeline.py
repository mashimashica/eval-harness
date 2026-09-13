# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import pytest

from eval_harness.config import load_experiment
from eval_harness.errors import ArtifactError, ConfigError, HarnessError
from eval_harness.executor import AuthStatus, ExecutionRequest, ExecutionResult, ParsedCodexOutput
from eval_harness.skill_pipeline import (
    build_skill,
    copy_skill_for_application,
    load_build_config,
    resume_skill_build,
)


class SkillExecutor:
    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
        return AuthStatus(True, True, "test account")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        (request.cwd / "creation_inputs").mkdir(exist_ok=True)
        (request.cwd / "creator_skills").mkdir(exist_ok=True)
        (request.cwd / "SKILL.md").write_text(
            "---\nname: arithmetic\ndescription: Arithmetic workflow.\n---\n\nUse the supplied input carefully.",
            encoding="utf-8",
        )
        event = {"type": "item.completed", "item": {"type": "agent_message", "text": "created"}}
        terminal = {"type": "turn.completed", "usage": {}}
        parsed = ParsedCodexOutput(
            events=(event, terminal),
            assistant_messages=("created",),
            final_text="created",
            usage={
                "input_tokens": None,
                "output_tokens": None,
                "cached_input_tokens": None,
                "reasoning_tokens": None,
                "cost_usd": None,
            },
            errors=(),
            terminal_completed=True,
        )
        return ExecutionResult(
            command=("test-cli",),
            returncode=0,
            status="completed",
            elapsed_seconds=0.01,
            stdout=json.dumps(event) + "\n" + json.dumps(terminal),
            stderr="",
            parsed=parsed,
        )


def test_build_invokes_configured_creator_and_saves_only_generated_skill(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("creation source", encoding="utf-8")
    creator_skill = tmp_path / "creator"
    creator_skill.mkdir()
    (creator_skill / "SKILL.md").write_text("creator guidance", encoding="utf-8")
    config_path = tmp_path / "build.yaml"
    config_path.write_text(
        f"""name: arithmetic
executor: codex
model: gpt-5.6-luna
settings:
  timeout_seconds: 10
prompt: Create a concise arithmetic Skill.
inputs:
  - {source.name}
skills:
  - {creator_skill.name}
""",
        encoding="utf-8",
    )
    config = load_build_config(config_path)
    output = build_skill(config, tmp_path / "arithmetic", SkillExecutor())

    assert "name: arithmetic" in (output / "SKILL.md").read_text()
    assert not (output / "creation_inputs").exists()
    assert not (output / "creator_skills").exists()
    manifest = json.loads((output / "skill_manifest.json").read_text())
    assert manifest["name"] == "arithmetic"
    assert manifest["generated_sha256"]
    assert manifest["creator_status"] == "completed"
    assert manifest["creator_elapsed_seconds"] == 0.01


def test_build_requires_skill_frontmatter_and_matching_name(tmp_path: Path) -> None:
    class InvalidSkillExecutor(SkillExecutor):
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            result = super().execute(request)
            (request.cwd / "SKILL.md").write_text("plain instructions", encoding="utf-8")
            return result

    config_path = tmp_path / "build.yaml"
    config_path.write_text(
        "name: arithmetic\nexecutor: codex\nmodel: gpt-5.6-luna\nprompt: Create it.\n",
        encoding="utf-8",
    )
    config = load_build_config(config_path)
    with pytest.raises(ArtifactError, match="frontmatter"):
        build_skill(config, tmp_path / "arithmetic", InvalidSkillExecutor())


def test_build_output_directory_must_match_skill_name(tmp_path: Path) -> None:
    config_path = tmp_path / "build.yaml"
    config_path.write_text(
        "name: arithmetic\nexecutor: codex\nmodel: gpt-5.6-luna\nprompt: Create it.\n",
        encoding="utf-8",
    )
    config = load_build_config(config_path)
    with pytest.raises(ConfigError, match="named exactly"):
        build_skill(config, tmp_path / "wrong-name", SkillExecutor())


def test_intervention_build_is_parsed_as_a_creation_config(tmp_path: Path) -> None:
    build = tmp_path / "build.yaml"
    build.write_text(
        "executor: codex\nmodel: gpt-5.6-luna\nprompt: Write a Skill.\n",
        encoding="utf-8",
    )
    task = tmp_path / "tasks.jsonl"
    task.write_text(
        json.dumps({"task_id": "t", "prompt": "q", "reference_files": [], "rubric_pretty": "r"}) + "\n",
        encoding="utf-8",
    )
    experiment = tmp_path / "experiment.yaml"
    experiment.write_text(
        f"""benchmark: gdpval
tasks:
  path: {task.name}
  limit: 1
application:
  executor: codex
  model: gpt-5.6-luna
conditions:
  - id: skilled
    intervention:
      build: {build.name}
""",
        encoding="utf-8",
    )
    config = load_experiment(experiment)
    assert config.conditions[0].intervention is not None
    assert config.conditions[0].intervention.build == build.resolve()


def test_creation_resume_uses_frozen_inputs_and_keeps_completed_skill(tmp_path: Path) -> None:
    class InterruptedCreator(SkillExecutor):
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            self.calls += 1
            assert "original brief" in request.prompt
            assert "name: arithmetic" in request.prompt
            assert "first guidance" in request.prompt and "second guidance" in request.prompt
            assert [path.read_text() for path in (request.cwd / "creation_inputs").iterdir()] == ["source v1"]
            # Relative links between selected sibling Skill directories remain usable.
            sibling = request.cwd / "creator_skills/first/../second/SKILL.md"
            assert sibling.read_text() == "second guidance"
            result = super().execute(request)
            return replace(result, status="interrupted", error="test interruption") if self.calls == 1 else result

    source = tmp_path / "source.txt"
    source.write_text("source v1")
    for name in ("first", "second"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "SKILL.md").write_text(name + " guidance")
    config_path = tmp_path / "build.yaml"
    config_path.write_text(
        "name: arithmetic\nexecutor: codex\nmodel: gpt-5.6-luna\nprompt: original brief\n"
        "inputs: [source.txt]\nskills: [first, second]\n"
    )
    creator = InterruptedCreator()
    output = tmp_path / "arithmetic"
    with pytest.raises(HarnessError, match="interruption"):
        build_skill(load_build_config(config_path), output, creator)
    source.unlink()
    config_path.unlink()
    (tmp_path / "second/SKILL.md").write_text("changed source")
    resume_skill_build(output, creator)
    assert creator.calls == 2
    assert (output / ".creation/attempts/0/events.jsonl").is_file()
    assert (output / ".creation/attempts/1/events.jsonl").is_file()
    before = (output / "skill_manifest.json").read_bytes()
    resume_skill_build(output, creator)
    assert creator.calls == 2
    assert before == (output / "skill_manifest.json").read_bytes()
    copied = tmp_path / "applied"
    copy_skill_for_application(output, copied)
    assert {p.name for p in copied.iterdir()} == {"SKILL.md"}


def test_input_freeze_failure_records_no_model_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "build.yaml"
    config_path.write_text("name: arithmetic\nexecutor: codex\nmodel: gpt-5.6-luna\nprompt: create\n")

    def fail_freeze(config: Any, destination: Path) -> None:
        destination.mkdir(parents=True)
        (destination / "partial.txt").write_text("setup evidence")
        raise OSError("simulated setup failure")

    monkeypatch.setattr("eval_harness.skill_pipeline.freeze_build_config", fail_freeze)
    output = tmp_path / "arithmetic"
    with pytest.raises(OSError, match="setup failure"):
        build_skill(load_build_config(config_path), output, SkillExecutor())
    manifest = json.loads((output / "skill_manifest.json").read_text())
    assert manifest["creator_status"] == "failed"
    assert manifest["attempt_count"] == 0
    assert manifest["creation_snapshot_complete"] is False
    assert (output / ".creation/config/partial.txt").read_text() == "setup evidence"
    with pytest.raises(ArtifactError, match="snapshot is incomplete"):
        resume_skill_build(output, SkillExecutor())
