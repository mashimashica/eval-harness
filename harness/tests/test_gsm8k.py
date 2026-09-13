# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eval_harness.config import load_experiment
from eval_harness.executor import AuthStatus, ExecutionRequest, ExecutionResult, ParsedCodexOutput
from eval_harness.gsm8k import GSM8KTask, grade
from eval_harness.run_pipeline import run_experiment


class GSMExecutor:
    def __init__(self, answer: int = 3) -> None:
        self.requests: list[ExecutionRequest] = []
        self.answer = answer

    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
        return AuthStatus(True, True, "test account")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.requests.append(request)
        message = f"The calculation is straightforward.\nFinal answer: {self.answer}"
        if request.purpose == "skill_creation":
            (request.cwd / "SKILL.md").write_text("Use a concise arithmetic workflow.", encoding="utf-8")
            message = "Wrote SKILL.md"
        elif request.purpose == "evaluation":
            raise AssertionError("mechanical GSM8K evaluation must not invoke a judge")
        event = {"type": "item.completed", "item": {"type": "agent_message", "text": message}}
        terminal = {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}
        parsed = ParsedCodexOutput(
            events=(event, terminal),
            assistant_messages=(message,),
            final_text=message,
            usage={
                "input_tokens": 1,
                "output_tokens": 1,
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
            stdout=json.dumps(event) + "\n" + json.dumps(terminal) + "\n",
            stderr="",
            parsed=parsed,
        )


def _task() -> GSM8KTask:
    return GSM8KTask(
        task_id="gsm-test",
        prompt="What is one plus two?",
        expected_answer=3,
        reference_solution="One plus two is three.",
        raw={"question": "What is one plus two?", "expected_answer": 3, "reference_solution": "secret"},
        source_path=Path("tasks.jsonl"),
        source_line=1,
    )


def test_gsm8k_grader_requires_a_complete_numeric_answer() -> None:
    task = _task()
    assert grade(task, "Final answer: $3 dollars").score == 1
    assert grade(task, "Final answer: $3 per day").score == 1
    assert grade(task, "**Final answer:** **3**").score == 1
    assert grade(task, "Final answer: 3/1").score == 0
    assert grade(task, "There are 3 items.\nFinal answer: 3").score == 1


def test_gsm8k_run_auto_mechanical_evaluation(tmp_path: Path) -> None:
    config_path = tmp_path / "gsm8k.yaml"
    config_path.write_text(
        """benchmark: gsm8k
tasks:
  rows:
    - question: What is one plus two?
      expected_answer: 3
      reference_solution: secret solution
  limit: 1
repeats: 1
limits:
  max_tasks: 1
  max_retries: 0
  concurrency: 1
application:
  executor: codex
  model: gpt-5.6-luna
  settings:
    timeout_seconds: 10
evaluation:
  method: mechanical
  executor: none
  model: null
  settings: {}
""",
        encoding="utf-8",
    )
    executor = GSMExecutor()
    config = load_experiment(config_path)
    summary = run_experiment(config, tmp_path / "run", executor, check_auth=True)

    assert summary.execution_status == "completed"
    assert summary.evaluation_status == "completed"
    assert len(executor.requests) == 1
    assert "secret solution" not in executor.requests[0].prompt
    assert summary.evaluation_dir is not None
    assert summary.comparison_dir is not None
    assert (summary.comparison_dir / "comparison.json").is_file()
    judgment = json.loads((summary.evaluation_dir / "judgments.jsonl").read_text().splitlines()[0])
    assert judgment["grading_method"] == "mechanical"
    assert judgment["score"] == 1.0
    assert judgment["expected_answer"] == 3
    assert judgment["judge_execution_status"] == "not_run"
    assert judgment["task_success"] is True


def test_gsm8k_mechanical_failure_keeps_execution_and_evaluation_completed(tmp_path: Path) -> None:
    config_path = tmp_path / "gsm8k.yaml"
    config_path.write_text(
        """benchmark: gsm8k
tasks:
  rows:
    - question: What is one plus two?
      expected_answer: 3
      reference_solution: secret solution
  limit: 1
repeats: 1
limits:
  max_tasks: 1
  max_retries: 0
  concurrency: 1
application:
  executor: codex
  model: gpt-5.6-luna
  settings:
    timeout_seconds: 10
evaluation:
  method: mechanical
  executor: none
  model: null
  settings: {}
""",
        encoding="utf-8",
    )
    summary = run_experiment(
        load_experiment(config_path),
        tmp_path / "run",
        GSMExecutor(answer=4),
        check_auth=True,
    )

    assert summary.execution_status == "completed"
    assert summary.evaluation_status == "completed"
    assert summary.evaluation_dir is not None
    judgment = json.loads((summary.evaluation_dir / "judgments.jsonl").read_text().splitlines()[0])
    assert judgment["execution_status"] == "completed"
    assert judgment["evaluation_status"] == "completed"
    assert judgment["score"] == 0.0
    assert judgment["score_valid"] is True
    assert judgment["task_success"] is False
