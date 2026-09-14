# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from test_replication_pipeline import CohortExecutor, config_file

from eval_harness.artifacts import read_json
from eval_harness.compare_pipeline import compare_evaluations
from eval_harness.config import EvaluationConfig, RuntimeConfig, load_experiment
from eval_harness.errors import ArtifactError
from eval_harness.evaluate_pipeline import evaluate_run, resume_evaluation
from eval_harness.run_pipeline import run_experiment


def test_cohort_evaluation_freezes_all_sources_and_resumes_without_originals(tmp_path: Path) -> None:
    executor = CohortExecutor(False)
    run = tmp_path / "runs"
    run_experiment(load_experiment(config_file(tmp_path)), run, executor, check_auth=False)
    evaluation = tmp_path / "evaluation"
    config = EvaluationConfig("mechanical", RuntimeConfig("none", None, {}))
    prepared = evaluate_run(run, config, evaluation, _prepare_only=True)
    assert prepared.status == "not_started"
    assert prepared.attempted_count == 0
    shutil.rmtree(run)
    completed = resume_evaluation(evaluation)
    assert completed.status == "completed" and completed.valid_count == 12
    before = read_json(evaluation / "cohorts/creation_0/evaluation_manifest.json")
    again = resume_evaluation(evaluation)
    assert again.valid_count == 12
    assert read_json(evaluation / "cohorts/creation_0/evaluation_manifest.json") == before
    summary = compare_evaluations([evaluation], tmp_path / "comparison")
    assert len(read_json(summary / "comparison.json")["evaluations"]) == 2
    assert executor.applications == 12 and executor.creations == 4


def test_changed_later_cohort_is_rejected_before_any_earlier_grading(tmp_path: Path) -> None:
    executor = CohortExecutor(False)
    run = tmp_path / "runs"
    run_experiment(load_experiment(config_file(tmp_path)), run, executor, check_auth=False)
    evaluation = tmp_path / "evaluation"
    evaluate_run(run, EvaluationConfig("mechanical", RuntimeConfig("none", None, {})), evaluation, _prepare_only=True)
    later = evaluation / "cohorts/creation_1/source_snapshot/run_state.json"
    later.write_text("[]")
    with pytest.raises(ArtifactError, match="prepared cohort evaluation"):
        resume_evaluation(evaluation)
    first = read_json(evaluation / "cohorts/creation_0/evaluation_manifest.json")
    assert first["attempted_count"] == 0
