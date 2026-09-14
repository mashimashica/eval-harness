# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import eval_harness.cli as cli
from eval_harness.errors import ArtifactError
from eval_harness.executor import AuthStatus


class _AuthenticatedExecutor:
    def check_auth(self, settings: Any = None) -> AuthStatus:
        return AuthStatus(True, True, "synthetic account")


def test_resume_run_uses_frozen_executor_without_loading_source_yaml(tmp_path: Path, monkeypatch: Any) -> None:
    result_dir = tmp_path / "run"
    result_dir.mkdir()
    (result_dir / "run_manifest.json").write_text(
        '{"config_path": "/deleted/original.yaml", "config_snapshot": '
        '{"_resolved": {"application": {"executor": "codex"}}}}',
        encoding="utf-8",
    )
    sentinel = object()
    calls: dict[str, object] = {}

    def factory(name: str) -> object:
        calls["executor_name"] = name
        return sentinel

    def fail_load(*args: object, **kwargs: object) -> Any:
        raise AssertionError("resume must not reopen the original YAML")

    def resume(root: Path, executor: object, **kwargs: object) -> Any:
        calls["root"] = root
        calls["executor"] = executor
        return SimpleNamespace(
            execution_status="completed", evaluation_status="not_started", completed_count=1, failed_count=0
        )

    monkeypatch.setattr(cli, "_executor_factory", factory)
    monkeypatch.setattr(cli, "load_experiment", fail_load)
    monkeypatch.setattr(cli, "resume_run", resume)

    assert cli._resume(result_dir) == 0
    assert calls == {"executor_name": "codex", "root": result_dir.resolve(), "executor": sentinel}


def test_resume_evaluation_uses_frozen_claude_executor(tmp_path: Path, monkeypatch: Any) -> None:
    result_dir = tmp_path / "evaluation"
    result_dir.mkdir()
    (result_dir / "evaluation_manifest.json").write_text(
        '{"config_path": "/deleted/evaluation.yaml", "config_snapshot": '
        '{"method": "scalar", "executor": "claude-code"}}',
        encoding="utf-8",
    )
    sentinel = object()
    calls: dict[str, object] = {}

    def factory(name: str) -> object:
        calls["executor_name"] = name
        return sentinel

    def resume(root: Path, executor: object, **kwargs: object) -> Any:
        calls["root"] = root
        calls["executor"] = executor
        return SimpleNamespace(status="completed", valid_count=1)

    monkeypatch.setattr(cli, "_executor_factory", factory)
    monkeypatch.setattr(cli, "resume_evaluation", resume)

    assert cli._resume(result_dir) == 0
    assert calls == {"executor_name": "claude-code", "root": result_dir.resolve(), "executor": sentinel}


def test_check_preflights_existing_skill_document(tmp_path: Path, monkeypatch: Any) -> None:
    skill = tmp_path / "bad-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("This has no Agent Skills frontmatter.", encoding="utf-8")
    experiment = tmp_path / "experiment.yaml"
    experiment.write_text(
        f"""benchmark: gsm8k
tasks:
  rows:
    - question: What is one plus one?
      expected_answer: 2
application:
  executor: codex
  model: gpt-5.6-luna
  settings:
    timeout_seconds: 10
conditions:
  - id: baseline
    intervention:
      path: {skill.name}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_executor_factory", lambda name: _AuthenticatedExecutor())

    with pytest.raises(ArtifactError, match="frontmatter"):
        cli._check(experiment)
