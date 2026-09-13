# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Re-evaluation resumes from frozen bytes and never substitutes the source run."""

import shutil
from pathlib import Path

import pytest
from test_pipeline import FakeExecutor, _config, _task_source

from eval_harness.config import EvaluationConfig, RuntimeConfig, load_experiment
from eval_harness.errors import ArtifactError
from eval_harness.evaluate_pipeline import evaluate_run, resume_evaluation
from eval_harness.run_pipeline import run_experiment


@pytest.mark.parametrize("damage", ["change", "remove"])
def test_completed_evaluation_refuses_changed_or_missing_snapshot(tmp_path: Path, damage: str) -> None:
    run_dir = tmp_path / "run"
    run_experiment(load_experiment(_config(tmp_path, _task_source(tmp_path))), run_dir, FakeExecutor())
    evaluation_dir = tmp_path / "evaluation"
    config = EvaluationConfig("scalar", RuntimeConfig("codex", "gpt-5.6-luna", {}))
    evaluate_run(run_dir, config, evaluation_dir, FakeExecutor())
    frozen = evaluation_dir / "source_snapshot"
    if damage == "remove":
        shutil.rmtree(frozen)
    else:
        (frozen / "inputs/tasks/task-1/references/tamper.txt").write_text("changed input")
    judge = FakeExecutor()
    with pytest.raises(ArtifactError, match="snapshot"):
        resume_evaluation(evaluation_dir, judge)
    assert not judge.requests


def test_new_evaluation_rejects_altered_run_inputs_before_judging(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_experiment(load_experiment(_config(tmp_path, _task_source(tmp_path))), run_dir, FakeExecutor())
    (run_dir / "inputs/tasks/task-1/references/changed.txt").write_text("unrecorded input")
    judge = FakeExecutor()
    config = EvaluationConfig("scalar", RuntimeConfig("codex", "gpt-5.6-luna", {}))
    with pytest.raises(ArtifactError, match="frozen task inputs"):
        evaluate_run(run_dir, config, tmp_path / "evaluation", judge)
    assert not judge.requests
    assert not (tmp_path / "evaluation").exists()
