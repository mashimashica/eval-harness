# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Panel evaluator, frozen criteria, and per-judge resume regressions."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import pytest

from eval_harness.artifacts import read_json, read_jsonl, write_json
from eval_harness.config import EvaluationConfig, JudgeConfig, RuntimeConfig, load_experiment
from eval_harness.errors import ArtifactError
from eval_harness.evaluate_pipeline import _criteria_prompt, evaluate_run, resume_evaluation
from eval_harness.executor import AuthStatus, ExecutionRequest, ExecutionResult, ParsedCodexOutput
from eval_harness.grading_criteria import criteria_for_task
from eval_harness.run_pipeline import run_experiment


def _task_source(root: Path, *, count: int = 1) -> Path:
    source = root / "tasks.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(
                {
                    "task_id": f"task-{index}",
                    "prompt": "Create answer.txt with a useful answer.",
                    "reference_files": [],
                    "rubric_pretty": "The answer is useful.",
                }
            )
            for index in range(1, count + 1)
        )
        + "\n",
        encoding="utf-8",
    )
    return source


def _experiment_config(root: Path, source: Path) -> Path:
    path = root / "experiment.yaml"
    path.write_text(
        "\n".join(
            [
                "benchmark: gdpval",
                "tasks:",
                f"  path: {source.name}",
                "  ids: [task-1]",
                "  limit: 1",
                "repeats: 1",
                "limits:",
                "  max_tasks: 1",
                "  max_retries: 0",
                "  concurrency: 1",
                "application:",
                "  executor: codex",
                "  model: gpt-5.6-luna",
                "  settings:",
                "    timeout_seconds: 10",
                "conditions:",
                "  - id: N",
                "    intervention: null",
                "  - id: A",
                "    intervention: null",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _parsed(text: str) -> ParsedCodexOutput:
    event = {"type": "item.completed", "item": {"type": "agent_message", "text": text}}
    terminal = {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}}
    return ParsedCodexOutput(
        events=(event, terminal),
        assistant_messages=(text,),
        final_text=text,
        usage={
            "input_tokens": 3,
            "output_tokens": 2,
            "cached_input_tokens": None,
            "reasoning_tokens": None,
            "cost_usd": None,
        },
        errors=(),
        terminal_completed=True,
    )


class _ApplicationExecutor:
    def __init__(self) -> None:
        self.requests: list[ExecutionRequest] = []

    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
        return AuthStatus(True, True, "fixture account")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.requests.append(request)
        if request.purpose == "application":
            (request.cwd / "answer.txt").write_text("fixture answer", encoding="utf-8")
            text = "Saved answer.txt"
        else:
            text = json.dumps({"score": 0.75, "rationale": "The saved artifact is useful."})
        parsed = _parsed(text)
        stdout = "\n".join(json.dumps(event) for event in parsed.events) + "\n"
        return ExecutionResult(("fixture",), 0, "completed", 0.01, stdout, "", parsed)


class _PanelExecutor(_ApplicationExecutor):
    def __init__(self, model: str, *, pairwise: bool = False, interrupt: bool = False) -> None:
        super().__init__()
        self.model = model
        self.pairwise = pairwise
        self.interrupt = interrupt

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.purpose != "evaluation":
            return super().execute(request)
        self.requests.append(request)
        if self.interrupt and len(self.requests) == 1:
            parsed = ParsedCodexOutput(
                (),
                (),
                "",
                {
                    "input_tokens": None,
                    "output_tokens": None,
                    "cached_input_tokens": None,
                    "reasoning_tokens": None,
                    "cost_usd": None,
                },
                (),
                False,
            )
            return ExecutionResult(("fixture",), None, "interrupted", 0.01, "", "", parsed, "fixture interruption")
        if self.pairwise:
            response: dict[str, Any] = {"winner": "tie", "rationale": f"{self.model} observed both files."}
        else:
            response = {"score": 0.75, "rationale": f"{self.model} observed the saved artifact."}
        parsed = _parsed(json.dumps(response))
        stdout = "\n".join(json.dumps(event) for event in parsed.events) + "\n"
        return ExecutionResult(("fixture",), 0, "completed", 0.01, stdout, "", parsed)


def _run_source(tmp_path: Path) -> tuple[Path, _ApplicationExecutor]:
    source = _task_source(tmp_path)
    config = load_experiment(_experiment_config(tmp_path, source))
    app = _ApplicationExecutor()
    run_experiment(config, tmp_path / "run", app, check_auth=False)
    return tmp_path / "run", app


def _runtime(model: str) -> RuntimeConfig:
    return RuntimeConfig("codex", model, {"timeout_seconds": 10})


def test_scalar_panel_calls_each_judge_with_independent_identity(tmp_path: Path) -> None:
    run_dir, _ = _run_source(tmp_path)
    first, second = _runtime("gpt-5.6-luna"), _runtime("gpt-5.6-sol")
    config = EvaluationConfig("scalar", first, (JudgeConfig("j-luna", first), JudgeConfig("j-sol", second)))
    created: dict[str, _PanelExecutor] = {}

    models = iter(("gpt-5.6-luna", "gpt-5.6-sol"))

    def factory(executor_name: str) -> _PanelExecutor:
        assert executor_name == "codex"
        model = next(models)
        executor = _PanelExecutor(model)
        created[model] = executor
        return executor

    summary = evaluate_run(
        run_dir,
        config,
        tmp_path / "evaluation",
        _ApplicationExecutor(),
        check_auth=False,
        executor_factory=factory,
    )
    rows = read_jsonl(summary.evaluation_dir / "judgments.jsonl")
    assert summary.status == "completed"
    assert len(rows) == 4
    assert {row["judge_id"] for row in rows} == {"j-luna", "j-sol"}
    assert len({row["judgment_id"] for row in rows}) == 4
    assert {row["judge_runtime"]["model"] for row in rows} == {"gpt-5.6-luna", "gpt-5.6-sol"}
    assert sum(len(executor.requests) for executor in created.values()) == 4
    assert all(request.response_schema is not None for executor in created.values() for request in executor.requests)
    assert all(
        request.response_schema["required"] == ["score", "rationale"]
        and request.response_schema["additionalProperties"] is False
        for executor in created.values()
        for request in executor.requests
        if request.response_schema is not None
    )
    assert all(
        "j-luna" not in request.prompt and "j-sol" not in request.prompt
        for executor in created.values()
        for request in executor.requests
    )


def test_pairwise_panel_honors_selected_pair_and_both_orders(tmp_path: Path) -> None:
    run_dir, _ = _run_source(tmp_path)
    # The source fixture has two conditions, so one selected pair still has
    # exactly two presentation orders for every judge.
    first, second = _runtime("gpt-5.6-luna"), _runtime("gpt-5.6-sol")
    config = EvaluationConfig(
        "pairwise",
        first,
        (JudgeConfig("j1", first), JudgeConfig("j2", second)),
        pairs=(("N", "A"),),
    )
    created: list[_PanelExecutor] = []

    models = iter(("gpt-5.6-luna", "gpt-5.6-sol"))

    def factory(executor_name: str) -> _PanelExecutor:
        assert executor_name == "codex"
        executor = _PanelExecutor(next(models), pairwise=True)
        created.append(executor)
        return executor

    summary = evaluate_run(
        run_dir,
        config,
        tmp_path / "pairs",
        _ApplicationExecutor(),
        check_auth=False,
        executor_factory=factory,
    )
    rows = read_jsonl(summary.evaluation_dir / "judgments.jsonl")
    assert summary.status == "completed"
    assert len(rows) == 4
    assert {row["judge_id"] for row in rows} == {"j1", "j2"}
    assert {tuple(row["condition_ids"]) for row in rows} == {("N", "A"), ("A", "N")}
    assert all(
        "submission_A/" in request.prompt or "submission_A" in request.prompt
        for executor in created
        for request in executor.requests
    )
    assert sum(len(executor.requests) for executor in created) == 4
    assert all(
        request.response_schema is not None
        and request.response_schema["properties"]["winner"]["enum"] == ["A", "B", "tie", "unjudgeable"]
        for executor in created
        for request in executor.requests
    )


def test_panel_resume_retries_only_pending_judgments_and_archives_attempt(tmp_path: Path) -> None:
    run_dir, _ = _run_source(tmp_path)
    runtime = _runtime("gpt-5.6-luna")
    config = EvaluationConfig("scalar", runtime, (JudgeConfig("j1", runtime), JudgeConfig("j2", runtime)))
    first_executor = _PanelExecutor(runtime.model or "unknown", interrupt=True)
    # A factory is used so resume can receive fresh per-runtime fake executors.
    first = evaluate_run(
        run_dir,
        config,
        tmp_path / "resume-evaluation",
        _ApplicationExecutor(),
        check_auth=False,
        executor_factory=lambda _: first_executor,
    )
    assert first.status == "interrupted"
    saved = read_jsonl(first.evaluation_dir / "judgments.jsonl")
    assert len(saved) == 1 and saved[0]["evaluation_status"] == "interrupted"

    resumed_executor = _PanelExecutor(runtime.model or "unknown")
    resumed = resume_evaluation(
        first.evaluation_dir,
        check_auth=False,
        executor_factory=lambda _: resumed_executor,
    )
    assert resumed.status == "completed"
    rows = read_jsonl(first.evaluation_dir / "judgments.jsonl")
    assert len(rows) == 4
    assert {row["evaluation_status"] for row in rows} == {"completed"}
    assert sum(row["evaluation_attempt_count"] for row in rows) == 5
    assert list((first.evaluation_dir / "judgments/judges/j1/N/task-1/repeat_0/attempts/0").iterdir())


def _criteria() -> dict[str, Any]:
    return {
        "version": "fixture-v1",
        "benchmark": "gdpval",
        "policy": {
            "arithmetic": "decimal",
            "rounding": "none",
            "decimal_places": 2,
            "absolute_tolerance": 0,
            "relative_tolerance": 0,
            "missing": "unconfirmed",
            "units": "fixture units",
        },
        "tasks": {
            "*": {
                "mechanical": [
                    {
                        "id": "answer-file",
                        "description": "The saved answer exists.",
                        "kind": "file_exists",
                        "path": "answer.txt",
                    }
                ],
                "ai": [{"id": "useful", "description": "The artifact is useful."}],
            }
        },
    }


def test_criteria_prompt_includes_frozen_policy_without_run_context_leakage() -> None:
    criteria = _criteria()
    task_criteria = criteria_for_task(criteria, "task-1", "gdpval")
    assert task_criteria is not None
    prompt = _criteria_prompt(task_criteria)
    assert "Frozen criteria version: fixture-v1" in prompt
    for key, value in criteria["policy"].items():
        assert f"- {key}: {value}" in prompt
    assert "- useful: The artifact is useful." in prompt
    assert "creator" not in prompt.lower()
    assert "application" not in prompt.lower()

    changed = {
        **task_criteria,
        "policy": {**task_criteria["policy"], "units": "changed fixture units"},
    }
    changed_prompt = _criteria_prompt(changed)
    assert changed_prompt != prompt
    assert "- units: changed fixture units" in changed_prompt


def test_criteria_results_are_strict_and_snapshot_is_immutable(tmp_path: Path) -> None:
    run_dir, _ = _run_source(tmp_path)
    runtime = _runtime("gpt-5.6-luna")
    config = EvaluationConfig("scalar", runtime, criteria=_criteria())

    class CriteriaExecutor(_PanelExecutor):
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            result = super().execute(request)
            response = json.loads(result.parsed.final_text)
            response["criteria_results"] = [
                {"id": "useful", "status": "pass", "evidence": "answer.txt exists", "reason": "observed"}
            ]
            parsed = _parsed(json.dumps(response))
            return replace(result, parsed=parsed)

    evaluator = CriteriaExecutor(runtime.model or "unknown")
    summary = evaluate_run(
        run_dir,
        config,
        tmp_path / "criteria-evaluation",
        _ApplicationExecutor(),
        check_auth=False,
        executor_factory=lambda _: evaluator,
    )
    row = read_jsonl(summary.evaluation_dir / "judgments.jsonl")[0]
    assert row["criteria_results"][0]["id"] == "useful"
    findings_path = summary.evaluation_dir / row["mechanical_findings_path"]
    assert read_json(findings_path)[0]["status"] == "pass"
    assert row["criteria_sha256"] == read_json(summary.evaluation_dir / "criteria_snapshot.json")["criteria_sha256"]
    request_schema = evaluator.requests[0].response_schema
    assert request_schema is not None
    assert request_schema["required"] == ["score", "rationale", "criteria_results"]
    assert request_schema["properties"]["criteria_results"]["items"]["properties"]["id"]["enum"] == ["useful"]
    assert request_schema["properties"]["criteria_results"]["items"]["properties"]["evidence"] == {
        "type": "string",
        "minLength": 1,
    }
    criteria_path = summary.evaluation_dir / "criteria_snapshot.json"
    saved = read_json(criteria_path)
    saved["criteria"]["version"] = "tampered"
    write_json(criteria_path, saved)
    with pytest.raises(ArtifactError, match="criteria"):
        resume_evaluation(summary.evaluation_dir, check_auth=False, executor_factory=lambda _: evaluator)


def test_unjudgeable_pairwise_output_is_completed_but_invalid(tmp_path: Path) -> None:
    run_dir, _ = _run_source(tmp_path)
    runtime = _runtime("gpt-5.6-luna")

    class Unjudgeable(_PanelExecutor):
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            result = super().execute(request)
            parsed = _parsed(json.dumps({"winner": "unjudgeable", "rationale": "Files are not comparable."}))
            return replace(result, parsed=parsed)

    summary = evaluate_run(
        run_dir,
        EvaluationConfig("pairwise", runtime),
        tmp_path / "unjudgeable",
        _ApplicationExecutor(),
        check_auth=False,
        executor_factory=lambda _: Unjudgeable(runtime.model or "unknown", pairwise=True),
    )
    rows = read_jsonl(summary.evaluation_dir / "judgments.jsonl")
    assert summary.status == "completed"
    assert all(row["evaluation_status"] == "completed" for row in rows)
    assert all(row["score_valid"] is False and row["winner"] == "unjudgeable" for row in rows)


def test_prepare_only_freezes_scalar_schedule_without_constructing_judge(tmp_path: Path) -> None:
    run_dir, _ = _run_source(tmp_path)
    runtime = _runtime("gpt-5.6-luna")
    config = EvaluationConfig("scalar", runtime)

    def forbidden_factory(_: str) -> _PanelExecutor:
        raise AssertionError("prepare-only evaluation must not construct a judge")

    summary = evaluate_run(
        run_dir,
        config,
        tmp_path / "prepared-scalar",
        check_auth=True,
        executor_factory=forbidden_factory,
        _prepare_only=True,
    )
    manifest = read_json(summary.evaluation_dir / "evaluation_manifest.json")
    state = read_json(summary.evaluation_dir / "evaluation_state.json")
    assert summary.status == "not_started"
    assert manifest["source_snapshot_dir"] == str(summary.evaluation_dir / "source_snapshot")
    assert manifest["pending_count"] == 2
    assert state["status"] == "not_started"
    assert len(state["planned_judgment_ids"]) == 2
    assert not (summary.evaluation_dir / "judgments.jsonl").exists()

    resumed = resume_evaluation(
        summary.evaluation_dir,
        check_auth=False,
        executor_factory=lambda _: _PanelExecutor(runtime.model or "unknown"),
    )
    assert resumed.status == "completed"
    assert len(read_jsonl(summary.evaluation_dir / "judgments.jsonl")) == 2


def test_prepare_only_freezes_pairwise_orders_before_panel_preflight(tmp_path: Path) -> None:
    run_dir, _ = _run_source(tmp_path)
    runtime = _runtime("gpt-5.6-luna")

    def forbidden_factory(_: str) -> _PanelExecutor:
        raise AssertionError("prepare-only evaluation must not construct a judge")

    summary = evaluate_run(
        run_dir,
        EvaluationConfig("pairwise", runtime, pairs=(("N", "A"),)),
        tmp_path / "prepared-pairwise",
        check_auth=True,
        executor_factory=forbidden_factory,
        _prepare_only=True,
    )
    state = read_json(summary.evaluation_dir / "evaluation_state.json")
    assert summary.status == "not_started"
    assert len(state["planned_judgment_ids"]) == 2
    assert state["pending_judgment_ids"] == state["planned_judgment_ids"]

    resumed = resume_evaluation(
        summary.evaluation_dir,
        check_auth=False,
        executor_factory=lambda _: _PanelExecutor(runtime.model or "unknown", pairwise=True),
    )
    assert resumed.status == "completed"
    rows = read_jsonl(summary.evaluation_dir / "judgments.jsonl")
    assert {tuple(row["condition_ids"]) for row in rows} == {("N", "A"), ("A", "N")}
