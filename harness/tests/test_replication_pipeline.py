# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import pytest
import yaml

from eval_harness.artifacts import read_json, write_json
from eval_harness.config import load_experiment
from eval_harness.errors import ConfigError
from eval_harness.executor import AuthStatus, ExecutionRequest, ExecutionResult, ParsedCodexOutput
from eval_harness.run_pipeline import resume_run, run_experiment


class CohortExecutor:
    def __init__(self, interrupt: bool = True) -> None:
        self.creations = 0
        self.applications = 0
        self.interrupt = interrupt
        self.source_texts: list[str] = []

    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
        return AuthStatus(True, True, "test account")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        status = "completed"
        if request.purpose == "skill_creation":
            self.creations += 1
            self.source_texts.extend(p.read_text() for p in (request.cwd / "creation_inputs").rglob("*.txt"))
            (request.cwd / "SKILL.md").write_text(
                f"---\nname: arithmetic\ndescription: Solve arithmetic.\n---\nCreation {self.creations}: Check totals."
            )
        else:
            assert request.purpose == "application"
            self.applications += 1
            if self.interrupt and self.applications == 2:
                status = "interrupted"
            (request.cwd / "answer.txt").write_text("18")
        text = "18"
        parsed = ParsedCodexOutput((), (text,), text, {"cost_usd": None}, (), status == "completed")
        return ExecutionResult(("fake",), 0, status, 1, "", "", parsed)


def config_file(tmp_path: Path) -> Path:
    (tmp_path / "source.txt").write_text("frozen creator input")
    for name in ("s", "a"):
        (tmp_path / f"{name}.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "arithmetic",
                    "executor": "codex",
                    "model": "gpt-5.6-sol",
                    "settings": {"reasoning_effort": "medium"},
                    "prompt": "Create an arithmetic Skill.",
                    "inputs": ["source.txt"],
                }
            )
        )
    config = {
        "benchmark": "gsm8k",
        "comparison_design": "matched_skills",
        "creation_repeats": 2,
        "repeats": 2,
        "tasks": {"rows": [{"task_id": "same-task", "question": "What is 9+9?", "expected_answer": "18"}]},
        "application": {"executor": "codex", "model": "gpt-5.6-luna", "settings": {"reasoning_effort": "max"}},
        "conditions": [
            {"id": "N"},
            {"id": "S", "intervention": {"build": "s.yaml"}},
            {"id": "A", "intervention": {"build": "a.yaml"}},
        ],
    }
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def test_cohorts_resume_preserves_finished_work_and_freezes_all_sources(tmp_path: Path) -> None:
    config = load_experiment(config_file(tmp_path))
    executor = CohortExecutor()
    root = tmp_path / "run"
    first = run_experiment(config, root, executor, check_auth=False)
    assert first.execution_status == "partial"
    assert executor.creations == 2
    assert executor.applications == 2
    child0 = root / "cohorts/creation_0"
    first_done = read_json(child0 / "run_state.json")[0]
    (tmp_path / "source.txt").write_text("CHANGED AFTER FIRST CREATION")
    (tmp_path / "s.yaml").unlink()
    (tmp_path / "a.yaml").unlink()
    second = resume_run(root, executor, check_auth=False)
    assert second.execution_status == "completed"
    assert second.completed_count == 12
    assert executor.creations == 4
    assert executor.applications == 13
    assert set(executor.source_texts) == {"frozen creator input"}
    assert read_json(child0 / "run_state.json")[0] == first_done
    creation_ids = set()
    for index in range(2):
        child = root / f"cohorts/creation_{index}"
        rows = read_json(child / "run_state.json")
        assert {r["creation_repeat"] for r in rows} == {index}
        assert {r["task_id"] for r in rows} == {"same-task"}
        for condition in ("S", "A"):
            ids = {r["skill"]["creation_id"] for r in rows if r["condition_id"] == condition}
            assert len(ids) == 1
            creation_ids.update(ids)
    assert len(creation_ids) == 4
    resume_run(root, executor, check_auth=False)
    assert executor.creations == 4 and executor.applications == 13


def test_matched_comparison_rejects_different_creator_settings_before_any_call(tmp_path: Path) -> None:
    path = config_file(tmp_path)
    creator = yaml.safe_load((tmp_path / "a.yaml").read_text())
    creator["settings"]["reasoning_effort"] = "high"
    (tmp_path / "a.yaml").write_text(yaml.safe_dump(creator))
    config = replace(load_experiment(path), creation_repeats=1)
    executor = CohortExecutor(False)
    with pytest.raises(ConfigError, match="identical creator"):
        run_experiment(config, tmp_path / "run", executor, check_auth=False)
    assert executor.creations == executor.applications == 0


@pytest.mark.parametrize("mismatch", ["brief", "input"])
def test_matched_comparison_rejects_creator_brief_or_input_mismatch_before_any_call(
    tmp_path: Path, mismatch: str
) -> None:
    path = config_file(tmp_path)
    if mismatch == "brief":
        creator = yaml.safe_load((tmp_path / "a.yaml").read_text())
        creator["prompt"] = "A different creator brief."
        (tmp_path / "a.yaml").write_text(yaml.safe_dump(creator))
    else:
        alternate = tmp_path / "alternate.txt"
        alternate.write_text("a different source", encoding="utf-8")
        creator = yaml.safe_load((tmp_path / "a.yaml").read_text())
        creator["inputs"] = [alternate.name]
        (tmp_path / "a.yaml").write_text(yaml.safe_dump(creator))

    config = replace(load_experiment(path), creation_repeats=1)
    executor = CohortExecutor(False)
    with pytest.raises(ConfigError, match="identical creation briefs and input versions"):
        run_experiment(config, tmp_path / f"rejected-{mismatch}", executor, check_auth=False)
    assert executor.creations == executor.applications == 0


def test_matched_comparison_rejects_missing_existing_creator_brief_before_any_call(tmp_path: Path) -> None:
    config = replace(load_experiment(config_file(tmp_path)), creation_repeats=1)
    executor = CohortExecutor(False)
    source = tmp_path / "built"
    run_experiment(config, source, executor, check_auth=False)
    source_manifest_path = source / "skills" / "S" / "arithmetic" / "skill_manifest.json"
    source_manifest = read_json(source_manifest_path)
    assert isinstance(source_manifest.get("config_snapshot"), dict)
    source_manifest["config_snapshot"].pop("prompt", None)
    write_json(source_manifest_path, source_manifest)

    raw = yaml.safe_load(config.config_path.read_text())
    raw["creation_repeats"] = 1
    for condition in raw["conditions"][1:]:
        condition["intervention"] = {"path": str(source / "skills" / condition["id"] / "arithmetic")}
    reuse_config = tmp_path / "missing-brief.yaml"
    reuse_config.write_text(yaml.safe_dump(raw))
    before = (executor.creations, executor.applications)
    with pytest.raises(ConfigError, match="identical creation briefs and input versions"):
        run_experiment(load_experiment(reuse_config), tmp_path / "missing-brief-run", executor, check_auth=False)
    assert (executor.creations, executor.applications) == before


def test_matched_comparison_rejects_altered_existing_skill_provenance_before_any_call(tmp_path: Path) -> None:
    config = replace(load_experiment(config_file(tmp_path)), creation_repeats=1)
    executor = CohortExecutor(False)
    source = tmp_path / "built"
    run_experiment(config, source, executor, check_auth=False)
    skill_path = source / "skills" / "S" / "arithmetic" / "SKILL.md"
    skill_path.write_text(skill_path.read_text(encoding="utf-8") + "\nAltered after creation.\n", encoding="utf-8")

    raw = yaml.safe_load(config.config_path.read_text())
    raw["creation_repeats"] = 1
    for condition in raw["conditions"][1:]:
        condition["intervention"] = {"path": str(source / "skills" / condition["id"] / "arithmetic")}
    reuse_config = tmp_path / "altered-skill.yaml"
    reuse_config.write_text(yaml.safe_dump(raw))
    before = (executor.creations, executor.applications)
    with pytest.raises(ConfigError, match="differs from its recorded creation version"):
        run_experiment(load_experiment(reuse_config), tmp_path / "altered-skill-run", executor, check_auth=False)
    assert (executor.creations, executor.applications) == before


def test_fixed_skill_reuse_preserves_creation_identity_and_stage_runtime(tmp_path: Path) -> None:
    config = replace(load_experiment(config_file(tmp_path)), creation_repeats=1)
    executor = CohortExecutor(False)
    source = tmp_path / "built"
    run_experiment(config, source, executor, check_auth=False)
    raw = yaml.safe_load(config.config_path.read_text())
    raw["creation_repeats"] = 1
    for condition in raw["conditions"][1:]:
        condition["intervention"] = {"path": str(source / "skills" / condition["id"] / "arithmetic")}
    reuse_config = tmp_path / "reuse.yaml"
    reuse_config.write_text(yaml.safe_dump(raw))
    run_experiment(load_experiment(reuse_config), tmp_path / "reuse", executor, check_auth=False)
    assert executor.creations == 2
    source_skills = read_json(source / "run_manifest.json")["skills"]
    saved = read_json(tmp_path / "reuse/run_manifest.json")["skills"]
    for condition in ("S", "A"):
        assert saved[condition]["creation_id"] == source_skills[condition]["creation_id"]
        assert saved[condition]["creator_runtime"]["model"] == "gpt-5.6-sol"
        assert saved[condition]["creation_in_this_run"] is False
