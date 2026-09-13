# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Regression for the real nested inline Skill path failure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eval_harness.config import load_experiment
from eval_harness.executor import AuthStatus, ExecutionRequest, ExecutionResult, parse_codex_jsonl
from eval_harness.run_pipeline import resume_run, run_experiment


class InlineExecutor:
    def __init__(self) -> None:
        self.purposes: list[str] = []

    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
        return AuthStatus(True, True, "fixture account")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.purposes.append(request.purpose)
        body = "---\nname: word-problems\ndescription: Solve word problems.\n---\nCheck units carefully.\n"
        if request.purpose == "skill_creation":
            assert "Two plus two" not in request.prompt
            (request.cwd / "SKILL.md").write_text(body)
            response = "Created Skill."
        else:
            assert request.purpose == "application"
            assert (request.cwd / "skill/SKILL.md").read_text() == body
            assert "Check units carefully." in request.prompt
            assert not (request.cwd / "skill/.creation").exists()
            response = "Final answer: 4"
        stdout = "\n".join(
            json.dumps(event)
            for event in [
                {"type": "item.completed", "item": {"type": "agent_message", "text": response}},
                {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}},
            ]
        )
        return ExecutionResult(("fixture",), 0, "completed", 0.01, stdout, "", parse_codex_jsonl(stdout))


def test_inline_build_applies_nested_skill_and_completed_resume_is_noop(tmp_path: Path) -> None:
    task = tmp_path / "tasks.jsonl"
    task.write_text(json.dumps({"question": "Two plus two?", "expected_answer": 4}) + "\n")
    build = tmp_path / "build.yaml"
    build.write_text("name: word-problems\nexecutor: codex\nmodel: gpt-5.6-luna\nprompt: General arithmetic.\n")
    config = tmp_path / "experiment.yaml"
    config.write_text("""benchmark: gsm8k
tasks: {path: tasks.jsonl, limit: 1}
application: {executor: codex, model: gpt-5.6-luna}
conditions:
  - id: A
    intervention: {build: build.yaml}
evaluation: {method: mechanical, executor: none}
""")
    executor = InlineExecutor()
    summary = run_experiment(load_experiment(config), tmp_path / "run", executor, check_auth=False)
    assert summary.execution_status == "completed"
    assert summary.completed_count == 1
    assert summary.evaluation_status == "completed"
    assert executor.purposes == ["skill_creation", "application"]
    for source in (task, build, config):
        source.unlink()
    resumed = resume_run(summary.run_dir, executor, check_auth=False)
    assert resumed.execution_status == "completed"
    assert executor.purposes == ["skill_creation", "application"]
