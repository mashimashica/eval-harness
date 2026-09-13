# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unsupported or unbounded runtime settings fail during configuration loading."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from eval_harness.config import load_experiment
from eval_harness.errors import ConfigError


@pytest.mark.parametrize(
    ("executor", "settings"),
    [
        ("codex", {"temperature": 0.2}),
        ("codex", {"max_turns": 12}),
        ("codex", {"timeout_seconds": float("inf")}),
        ("codex", {"timeout_seconds": float("nan")}),
        ("codex", {"auth_source_home": 42}),
        ("claude-code", {"max_turns": True}),
        ("claude-code", {"max_turns": 1.5}),
        ("claude-code", {"max_turns": 0}),
    ],
)
def test_invalid_settings_fail_before_any_runtime_is_selected(
    tmp_path: Path, executor: str, settings: dict[str, Any]
) -> None:
    config = {
        "benchmark": "gsm8k",
        "tasks": {"rows": [{"question": "What is one plus one?", "expected_answer": 2}]},
        "application": {
            "executor": executor,
            "model": "gpt-5.6-luna" if executor == "codex" else "claude-sonnet-4-6",
            "settings": settings,
        },
    }
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ConfigError, match="settings"):
        load_experiment(path)


def test_gdpval_cannot_select_mechanical_evaluation(tmp_path: Path) -> None:
    config = {
        "benchmark": "gdpval",
        "tasks": {"rows": [{"task_id": "task-1", "prompt": "Create a file."}]},
        "application": {
            "executor": "codex",
            "model": "gpt-5.6-luna",
            "settings": {"timeout_seconds": 10},
        },
        "evaluation": {"method": "mechanical", "executor": "none", "model": None, "settings": {}},
    }
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config))

    with pytest.raises(ConfigError, match="GDPval.*mechanical"):
        load_experiment(path)


def test_pairwise_requires_two_conditions(tmp_path: Path) -> None:
    config = {
        "benchmark": "gsm8k",
        "tasks": {"rows": [{"question": "What is one plus one?", "expected_answer": 2}]},
        "application": {
            "executor": "codex",
            "model": "gpt-5.6-luna",
            "settings": {"timeout_seconds": 10},
        },
        "conditions": [{"id": "only", "intervention": None}],
        "evaluation": {
            "method": "pairwise",
            "executor": "codex",
            "model": "gpt-5.6-luna",
            "settings": {"timeout_seconds": 10},
        },
    }
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config))

    with pytest.raises(ConfigError, match="at least two conditions"):
        load_experiment(path)
