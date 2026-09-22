# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import pytest

from eval_harness.compare_pipeline import compare_evaluations
from eval_harness.config import EvaluationConfig, RuntimeConfig, load_experiment
from eval_harness.errors import ArtifactError, ConfigError, HarnessError, OutputExistsError
from eval_harness.evaluate_pipeline import evaluate_run, parse_pairwise_score, parse_scalar_score, resume_evaluation
from eval_harness.executor import AuthStatus, ExecutionRequest, ExecutionResult, ParsedCodexOutput
from eval_harness.gdpval import task_directory_name
from eval_harness.run_pipeline import resume_run, run_experiment


class FakeExecutor:
    def __init__(self) -> None:
        self.requests: list[ExecutionRequest] = []

    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
        return AuthStatus(True, True, "fake account login")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.requests.append(request)
        if request.purpose == "application":
            (request.cwd / "answer.txt").write_text("participant output", encoding="utf-8")
            message = "I saved answer.txt."
        else:
            message = json.dumps({"score": 0.75, "rationale": "The saved answer meets the test rubric."})
        event = {"type": "item.completed", "item": {"type": "agent_message", "text": message}}
        terminal = {"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 8}}
        stdout = json.dumps(event) + "\n" + json.dumps(terminal) + "\n"
        parsed = ParsedCodexOutput(
            events=(event, terminal),
            assistant_messages=(message,),
            final_text=message,
            usage={
                "input_tokens": 12,
                "output_tokens": 8,
                "cached_input_tokens": None,
                "reasoning_tokens": None,
                "cost_usd": None,
            },
            errors=(),
            terminal_completed=True,
        )
        return ExecutionResult(
            command=("fake-codex", "exec"),
            returncode=0,
            status="completed",
            elapsed_seconds=0.25,
            stdout=stdout,
            stderr="",
            parsed=parsed,
        )


class MissingAuthExecutor(FakeExecutor):
    def check_auth(self, settings: Mapping[str, Any] | None = None) -> AuthStatus:
        return AuthStatus(True, False, "synthetic missing account login")


class OutcomeExecutor(FakeExecutor):
    """Return bounded application outcomes so journal retry/resume paths are real tests."""

    def __init__(self, outcomes: list[str]) -> None:
        super().__init__()
        self.outcomes = list(outcomes)

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.purpose != "application" or not self.outcomes:
            return super().execute(request)
        outcome = self.outcomes.pop(0)
        if outcome == "completed":
            return super().execute(request)
        self.requests.append(request)
        parsed = ParsedCodexOutput(
            events=(),
            assistant_messages=(),
            final_text="",
            usage={
                "input_tokens": None,
                "output_tokens": None,
                "cached_input_tokens": None,
                "reasoning_tokens": None,
                "cost_usd": None,
            },
            errors=(f"synthetic {outcome}",),
            terminal_completed=False,
        )
        return ExecutionResult(
            command=("fake-codex", "exec"),
            returncode=None,
            status=outcome,
            elapsed_seconds=0.1,
            stdout="",
            stderr="",
            parsed=parsed,
            error=f"synthetic {outcome}",
        )


class InterruptedJudgeExecutor(FakeExecutor):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.purpose != "evaluation":
            return super().execute(request)
        self.requests.append(request)
        parsed = ParsedCodexOutput(
            events=(),
            assistant_messages=(),
            final_text="",
            usage={
                "input_tokens": None,
                "output_tokens": None,
                "cached_input_tokens": None,
                "reasoning_tokens": None,
                "cost_usd": None,
            },
            errors=(),
            terminal_completed=False,
        )
        return ExecutionResult(
            command=("fake-codex", "exec"),
            returncode=None,
            status="interrupted",
            elapsed_seconds=0.1,
            stdout="",
            stderr="",
            parsed=parsed,
            error="synthetic interruption",
        )


class PairwiseExecutor(FakeExecutor):
    def __init__(self, outcomes: list[str] | None = None) -> None:
        super().__init__()
        self.outcomes = list(outcomes or ["A", "B"])

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.purpose != "evaluation":
            return super().execute(request)
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else "tie"
        if outcome == "interrupted":
            return InterruptedJudgeExecutor().execute(request)
        message = json.dumps({"winner": outcome, "rationale": "A comparison of the observed submissions."})
        event = {"type": "item.completed", "item": {"type": "agent_message", "text": message}}
        terminal = {"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 3}}
        parsed = ParsedCodexOutput(
            events=(event, terminal),
            assistant_messages=(message,),
            final_text=message,
            usage={
                "input_tokens": 5,
                "output_tokens": 3,
                "cached_input_tokens": None,
                "reasoning_tokens": None,
                "cost_usd": None,
            },
            errors=(),
            terminal_completed=True,
        )
        return ExecutionResult(
            command=("fake-codex", "exec"),
            returncode=0,
            status="completed",
            elapsed_seconds=0.2,
            stdout=json.dumps(event) + "\n" + json.dumps(terminal) + "\n",
            stderr="",
            parsed=parsed,
        )


def _config(tmp_path: Path, source: Path, *, limit: int = 1, max_retries: int = 0) -> Path:
    config_path = tmp_path / "experiment.yaml"
    config_path.write_text(
        "\n".join(
            [
                "benchmark: gdpval",
                "tasks:",
                f"  path: {source.name}",
                f"  limit: {limit}",
                "  seed: 42",
                "repeats: 1",
                "limits:",
                f"  max_tasks: {limit}",
                f"  max_retries: {max_retries}",
                "  concurrency: 1",
                "application:",
                "  executor: codex",
                "  model: gpt-5.6-luna",
                "  settings:",
                "    timeout_seconds: 10",
                "conditions:",
                "  - id: baseline",
                "    intervention: null",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _two_condition_config(tmp_path: Path, source: Path) -> Path:
    config_path = _config(tmp_path, source)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  - id: baseline\n    intervention: null",
            "  - id: baseline\n    intervention: null\n  - id: variant\n    intervention: null",
        ),
        encoding="utf-8",
    )
    return config_path


def _three_condition_config(tmp_path: Path, source: Path) -> Path:
    config_path = _two_condition_config(tmp_path, source)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  - id: variant\n    intervention: null",
            "  - id: variant\n    intervention: null\n  - id: other\n    intervention: null",
        ),
        encoding="utf-8",
    )
    return config_path


def _task_source(tmp_path: Path, *, count: int = 1) -> Path:
    reference = tmp_path / "reference.txt"
    reference.write_text("reference input", encoding="utf-8")
    source = tmp_path / "tasks.jsonl"
    rows = []
    for index in range(1, count + 1):
        rows.append(
            {
                "task_id": f"task-{index}",
                "prompt": "Create answer.txt from the reference input.",
                "reference_files": [reference.name],
                "rubric_pretty": "[+1] The answer file exists. [+1] The answer is useful.",
                "rubric_json": [{"score": 1, "criterion": "The answer file exists."}],
            }
        )
    source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return source


def test_run_stages_only_selected_inputs_and_keeps_success_unknown(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_config(tmp_path, source))
    executor = FakeExecutor()
    run_dir = tmp_path / "run"
    summary = run_experiment(config, run_dir, executor)

    assert summary.execution_status == "completed"
    assert summary.completed_count == 1
    assert len(executor.requests) == 1
    prompt = executor.requests[0].prompt
    assert "The answer file exists" not in prompt
    assert (run_dir / "inputs/tasks/task-1/references/reference.txt").read_text() == "reference input"
    record = json.loads((run_dir / "run_state.json").read_text())[0]
    assert record["execution_status"] == "completed"
    assert record["task_success"] is None
    assert record["usage"]["input_tokens"] == 12
    assert record["cost_usd"] is None
    assert (run_dir / "conditions/baseline/tasks/task-1/repeat_0/deliverables/answer.txt").is_file()
    assert (run_dir / "conditions/baseline/tasks/task-1/repeat_0/codex_events.jsonl").is_file()


def test_run_freezes_input_manifest_and_resume_rejects_tampering(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_config(tmp_path, source))
    executor = FakeExecutor()
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, executor)

    run_manifest = json.loads((run_dir / "run_manifest.json").read_text())
    input_manifest_path = run_dir / "inputs/input_manifest.json"
    input_manifest = json.loads(input_manifest_path.read_text())
    reference_entry = next(item for item in input_manifest if item["path"].endswith("references/reference.txt"))
    saved_reference = json.loads((run_dir / "inputs/tasks/task-1/task.json").read_text())["saved_reference_files"][0]
    assert saved_reference["sha256"] == reference_entry["sha256"]
    assert run_manifest["input_manifest_sha256"]

    (run_dir / "inputs/tasks/task-1/references/reference.txt").write_text("tampered", encoding="utf-8")
    executor.requests.clear()
    with pytest.raises(ArtifactError, match="frozen task inputs"):
        resume_run(run_dir, executor, check_auth=False)
    assert executor.requests == []


def test_run_preflights_evaluator_auth_before_application_call(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config_path = _config(tmp_path, source)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\nevaluation:\n  method: scalar\n  executor: codex\n  model: gpt-5.6-luna\n  settings:\n    timeout_seconds: 10\n",
        encoding="utf-8",
    )
    application_executor = FakeExecutor()

    def factory(name: str) -> MissingAuthExecutor:
        assert name == "codex"
        return MissingAuthExecutor()

    with pytest.raises(HarnessError, match="authentication"):
        run_experiment(
            load_experiment(config_path),
            tmp_path / "run",
            application_executor,
            executor_factory=factory,
        )
    assert application_executor.requests == []
    assert not (tmp_path / "run").exists()


def test_run_preflights_human_ratings_source_before_application_call(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config_path = _config(tmp_path, source)
    missing = tmp_path / "ratings.jsonl"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + f"\nevaluation:\n  method: human\n  executor: none\n  model: null\n  settings:\n    ratings_path: {missing.name}\n",
        encoding="utf-8",
    )
    application_executor = FakeExecutor()

    with pytest.raises(ArtifactError, match="human ratings source is missing"):
        run_experiment(load_experiment(config_path), tmp_path / "run", application_executor)
    assert application_executor.requests == []
    assert not (tmp_path / "run").exists()


def test_resume_reconciles_completed_execution_journal_before_retrying(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_config(tmp_path, source))
    executor = FakeExecutor()
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, executor)
    state_path = run_dir / "run_state.json"
    state = json.loads(state_path.read_text())
    state[0]["execution_status"] = "pending"
    state[0]["attempt_count"] = 0
    state[0]["attempt_history"] = []
    state_path.write_text(json.dumps(state), encoding="utf-8")
    executor.requests.clear()

    resumed = resume_run(run_dir, executor, check_auth=False)

    assert resumed.execution_status == "completed"
    assert resumed.completed_count == 1
    assert executor.requests == []


def test_application_receives_selected_skill_body_and_staged_file(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    skill = tmp_path / "selected-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: selected-skill\ndescription: A selected test Skill.\n---\n\nUse the supplied reference.",
        encoding="utf-8",
    )
    config_path = _config(tmp_path, source)
    config_path.write_text(
        config_path.read_text().replace(
            "    intervention: null",
            f"    intervention:\n      path: {skill.name}",
        ),
        encoding="utf-8",
    )

    executor = FakeExecutor()
    run_experiment(load_experiment(config_path), tmp_path / "run", executor)

    assert "Use the supplied reference." in executor.requests[0].prompt
    assert (executor.requests[0].cwd / "skill/SKILL.md").is_file()


def test_path_components_preserve_distinct_task_identities(tmp_path: Path) -> None:
    source = _task_source(tmp_path, count=2)
    rows = [
        {
            "task_id": "a/b",
            "prompt": "First task",
            "reference_files": [],
            "rubric_pretty": "r",
        },
        {
            "task_id": "a_b",
            "prompt": "Second task",
            "reference_files": [],
            "rubric_pretty": "r",
        },
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    config = load_experiment(_config(tmp_path, source, limit=2))
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, FakeExecutor())

    first = task_directory_name("a/b")
    second = task_directory_name("a_b")
    assert first != second
    assert (run_dir / "conditions/baseline/tasks" / first / "repeat_0/execution.json").is_file()
    assert (run_dir / "conditions/baseline/tasks" / second / "repeat_0/execution.json").is_file()


def test_application_receives_condition_prompt_without_creator_or_skill(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config_path = _config(tmp_path, source)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "    intervention: null",
            "    intervention:\n      prompt: Apply the concise format requested by the user.",
        ),
        encoding="utf-8",
    )
    executor = FakeExecutor()

    run_experiment(load_experiment(config_path), tmp_path / "run", executor)

    assert "Apply the concise format requested by the user." in executor.requests[0].prompt
    assert not (executor.requests[0].cwd / "skill").exists()


def test_intervention_rejects_unknown_fields(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config_path = _config(tmp_path, source)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "    intervention: null",
            "    intervention:\n      prompt: A valid prompt\n      unsupported: ignored",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unsupported field"):
        load_experiment(config_path)


def test_evaluate_reads_saved_artifacts_and_compare_aggregates(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_config(tmp_path, source))
    executor = FakeExecutor()
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, executor)
    artifact = run_dir / "conditions/baseline/tasks/task-1/repeat_0/deliverables/answer.txt"
    before = artifact.read_bytes()
    eval_config = EvaluationConfig(
        method="scalar",
        runtime=RuntimeConfig("codex", "gpt-5.6-luna", {"timeout_seconds": 10}),
    )
    evaluation_dir = tmp_path / "evaluation"
    summary = evaluate_run(run_dir, eval_config, evaluation_dir, executor)

    assert summary.status == "completed"
    assert summary.valid_count == 1
    assert artifact.read_bytes() == before
    assert len(executor.requests) == 2
    judge_prompt = executor.requests[1].prompt
    assert "The answer file exists" in judge_prompt
    assert "baseline" not in judge_prompt
    judgment = json.loads((evaluation_dir / "judgments.jsonl").read_text().splitlines()[0])
    assert judgment["score"] == 0.75
    run_id = json.loads((run_dir / "run_manifest.json").read_text())["run_id"]
    assert judgment["generation_id"] == f"{run_id}:baseline:task-1:0"

    report_dir = tmp_path / "report"
    compare_evaluations([evaluation_dir], report_dir)
    report = json.loads((report_dir / "comparison.json").read_text())
    assert report["condition_results"][0]["condition_id"] == "baseline"
    assert report["condition_results"][0]["evaluated_sample_count"] == 1
    assert report["condition_results"][0]["scores"] == [0.75]


def test_config_rejects_ambient_sandbox_and_non_codex_executor(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config_path = _config(tmp_path, source)
    original = config_path.read_text()
    config_path.write_text(
        original.replace("executor: codex", "executor: claude-code").replace(
            "timeout_seconds: 10", "sandbox: danger-full-access"
        )
    )
    with pytest.raises(ConfigError):
        load_experiment(config_path)


def test_config_rejects_reasoning_effort_not_supported_by_selected_model(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config_path = _config(tmp_path, source)
    config_path.write_text(
        config_path.read_text().replace("timeout_seconds: 10", "timeout_seconds: 10\n    reasoning_effort: ultra"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unsupported for gpt-5.6-luna"):
        load_experiment(config_path)


def test_config_rejects_claude_gdpval_evaluation_without_office_tools(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config_path = _config(tmp_path, source)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\nevaluation:\n  method: pairwise\n  executor: claude-code\n  model: claude-sonnet-4-6\n  settings: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Claude Code GDPval evaluation requires tool_mode: sandboxed_shell"):
        load_experiment(config_path)


@pytest.mark.parametrize(
    ("text", "score"),
    [
        ('{"score": 0.5, "rationale": "ok"}', 0.5),
    ],
)
def test_parse_scalar_score(text: str, score: float) -> None:
    parsed = parse_scalar_score(text)
    assert parsed.valid
    assert parsed.score == score


@pytest.mark.parametrize(
    "text",
    [
        '```json\n{"score": 1, "rationale": "all"}\n```',
        "SCORE: 0.25",
        '{"score": 0.5, "rationale": "ok", "extra": true}',
        '{"score": 0.5}',
    ],
)
def test_parse_scalar_score_rejects_non_schema_output(text: str) -> None:
    assert not parse_scalar_score(text).valid


@pytest.mark.parametrize(
    ("text", "winner"),
    [
        ('{"winner": "A", "rationale": "A is clearer."}', "A"),
        ('{"winner": "B", "rationale": "B is more complete."}', "B"),
        ('{"winner": "tie", "rationale": "Both are equivalent."}', "tie"),
    ],
)
def test_parse_pairwise_score(text: str, winner: str) -> None:
    parsed = parse_pairwise_score(text)
    assert parsed.valid
    assert parsed.winner == winner


@pytest.mark.parametrize(
    "text",
    [
        '{"winner": "a", "rationale": "lowercase is not the schema"}',
        '{"winner": "A", "rationale": "ok", "extra": true}',
        '{"winner": "A"}',
    ],
)
def test_parse_pairwise_score_rejects_non_schema_output(text: str) -> None:
    assert not parse_pairwise_score(text).valid


def test_pairwise_evaluation_schedules_both_orders_anonymously(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_two_condition_config(tmp_path, source))
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, FakeExecutor())
    evaluator = PairwiseExecutor()
    evaluation_config = EvaluationConfig(
        method="pairwise",
        runtime=RuntimeConfig("codex", "gpt-5.6-luna", {"timeout_seconds": 10}),
    )

    summary = evaluate_run(run_dir, evaluation_config, tmp_path / "pairs", evaluator)

    assert summary.status == "completed"
    assert summary.valid_count == 2
    assert len(evaluator.requests) == 2
    assert all("baseline" not in request.prompt and "variant" not in request.prompt for request in evaluator.requests)
    rows = [json.loads(line) for line in (summary.evaluation_dir / "judgments.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert all(row["generation_ids"][0] != row["generation_ids"][1] for row in rows)
    assert [row["presented_conditions"] for row in rows] == [["A", "B"], ["A", "B"]]
    assert {tuple(row["condition_ids"]) for row in rows} == {("baseline", "variant"), ("variant", "baseline")}


def test_pairwise_evaluation_can_select_one_condition_pair(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_three_condition_config(tmp_path, source))
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, FakeExecutor())
    evaluator = PairwiseExecutor()
    evaluation_config = EvaluationConfig(
        method="pairwise",
        runtime=RuntimeConfig(
            "codex",
            "gpt-5.6-luna",
            {"timeout_seconds": 10, "pairs": [["baseline", "variant"]]},
        ),
    )

    summary = evaluate_run(run_dir, evaluation_config, tmp_path / "pairs", evaluator)

    assert summary.status == "completed"
    assert summary.valid_count == 2
    assert len(evaluator.requests) == 2
    rows = [json.loads(line) for line in (summary.evaluation_dir / "judgments.jsonl").read_text().splitlines()]
    assert {tuple(row["condition_ids"]) for row in rows} == {("baseline", "variant"), ("variant", "baseline")}


def test_pairwise_evaluation_resume_preserves_judgment_and_archives_failure(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_two_condition_config(tmp_path, source))
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, FakeExecutor())
    evaluation_config = EvaluationConfig(
        method="pairwise",
        runtime=RuntimeConfig("codex", "gpt-5.6-luna", {"timeout_seconds": 10}),
    )
    evaluation_dir = tmp_path / "pairs"
    first = evaluate_run(run_dir, evaluation_config, evaluation_dir, PairwiseExecutor(["interrupted"]))
    assert first.status == "interrupted"
    saved = json.loads((evaluation_dir / "judgments.jsonl").read_text().splitlines()[0])

    resumed = resume_evaluation(evaluation_dir, PairwiseExecutor(["A", "B"]))

    assert resumed.status == "completed"
    replacement = json.loads((evaluation_dir / "judgments.jsonl").read_text().splitlines()[0])
    assert replacement["judgment_id"] == saved["judgment_id"]
    assert replacement["evaluation_attempt_count"] == 2
    assert list((evaluation_dir / "judgments/pairwise/task-1/repeat_0").glob("*/attempts/0"))


def test_human_evaluation_imports_ratings_and_normalizes_declared_scale(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_config(tmp_path, source))
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, FakeExecutor())
    run_id = json.loads((run_dir / "run_manifest.json").read_text())["run_id"]
    evaluation_config = EvaluationConfig(
        method="human",
        runtime=RuntimeConfig(
            "none",
            None,
            {
                "ratings": [
                    {
                        "generation_id": "baseline:task-1:0",
                        "rater_id": "rater-1",
                        "ratings": {"quality": 4},
                        "comment": "Clear and complete.",
                        "is_test_data": True,
                    }
                ],
                "score_scale": [1, 5],
            },
        ),
    )

    summary = evaluate_run(run_dir, evaluation_config, tmp_path / "human", FakeExecutor())

    assert summary.status == "completed"
    row = json.loads((summary.evaluation_dir / "judgments.jsonl").read_text().splitlines()[0])
    assert row["generation_id"] == f"{run_id}:baseline:task-1:0"
    assert row["score"] == 0.75
    assert row["score_valid"] is True
    assert row["ratings"] == {"quality": 4}
    assert row["comment"] == "Clear and complete."
    assert row["is_test_data"] is True
    assert row["judge_elapsed_seconds"] is None
    assert (summary.evaluation_dir / "inputs/human_ratings.jsonl").is_file()


def test_run_auto_human_evaluation_uses_imported_ratings_without_judge_call(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    base = load_experiment(_config(tmp_path, source))
    config = replace(
        base,
        evaluation=EvaluationConfig(
            method="human",
            runtime=RuntimeConfig(
                "none",
                None,
                {
                    "ratings": [
                        {
                            "condition_id": "baseline",
                            "task_id": "task-1",
                            "repeat": 0,
                            "rater_id": "reviewer",
                            "ratings": {"quality": 1},
                        }
                    ]
                },
            ),
        ),
    )
    executor = FakeExecutor()

    summary = run_experiment(config, tmp_path / "run", executor)

    assert summary.evaluation_status == "completed"
    assert summary.evaluation_dir is not None
    assert len(executor.requests) == 1
    row = json.loads((summary.evaluation_dir / "judgments.jsonl").read_text().splitlines()[0])
    assert row["rater_id"] == "reviewer"
    assert row["score"] is None
    assert row["score_valid"] is True


def test_resume_run_continues_failed_auto_evaluation_without_new_run(tmp_path: Path) -> None:
    class InvalidThenValidJudge(FakeExecutor):
        def __init__(self) -> None:
            super().__init__()
            self.judge_calls = 0

        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            result = super().execute(request)
            if request.purpose == "evaluation":
                self.judge_calls += 1
                if self.judge_calls == 1:
                    invalid = replace(
                        result.parsed,
                        final_text='{"score": 2, "rationale": "out of range"}',
                        assistant_messages=('{"score": 2, "rationale": "out of range"}',),
                    )
                    return replace(result, parsed=invalid)
            return result

    source = _task_source(tmp_path)
    base = load_experiment(_config(tmp_path, source))
    config = replace(
        base,
        evaluation=EvaluationConfig(
            method="scalar",
            runtime=RuntimeConfig("codex", "gpt-5.6-luna", {"timeout_seconds": 10}),
        ),
    )
    executor = InvalidThenValidJudge()
    first = run_experiment(config, tmp_path / "run", executor, check_auth=False)

    assert first.execution_status == "completed"
    assert first.evaluation_status == "partial"
    assert first.evaluation_dir is not None
    saved_evaluation_dir = first.evaluation_dir
    resumed = resume_run(first.run_dir, executor, check_auth=False)

    assert resumed.evaluation_status == "completed"
    assert resumed.evaluation_dir == saved_evaluation_dir
    assert executor.judge_calls == 2


def test_human_resume_consumes_append_only_inbox_and_preserves_completed_rating(tmp_path: Path) -> None:
    source = _task_source(tmp_path, count=2)
    config = load_experiment(_config(tmp_path, source, limit=2))
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, FakeExecutor())
    evaluation_config = EvaluationConfig(
        method="human",
        runtime=RuntimeConfig("none", None, {"ratings": []}),
    )
    evaluation_dir = tmp_path / "human"
    first = evaluate_run(run_dir, evaluation_config, evaluation_dir, FakeExecutor())
    assert first.status == "partial"
    inbox = evaluation_dir / "inputs/human_ratings.inbox.jsonl"
    inbox.write_text(
        json.dumps(
            {
                "condition_id": "baseline",
                "task_id": "task-1",
                "repeat": 0,
                "rater_id": "rater",
                "ratings": {"quality": 4},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    partial = resume_evaluation(evaluation_dir, FakeExecutor())
    assert partial.status == "partial"
    inbox.write_text(
        inbox.read_text(encoding="utf-8")
        + json.dumps(
            {
                "condition_id": "baseline",
                "task_id": "task-2",
                "repeat": 0,
                "rater_id": "rater",
                "ratings": {"quality": 3},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    completed = resume_evaluation(evaluation_dir, FakeExecutor())
    assert completed.status == "completed"

    inbox.write_text(
        inbox.read_text(encoding="utf-8")
        + json.dumps(
            {
                "rating_id": "1",
                "generation_id": "baseline:task-1:0",
                "rater_id": "rater",
                "ratings": {"quality": 1},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    changed = resume_evaluation(evaluation_dir, FakeExecutor())
    assert changed.status == "partial"
    rows = [json.loads(line) for line in (evaluation_dir / "judgments.jsonl").read_text().splitlines()]
    task_one = next(row for row in rows if row["task_id"] == "task-1")
    assert task_one["ratings"] == {"quality": 4}
    rejected = (evaluation_dir / "rejected_ratings.jsonl").read_text()
    assert "completed rating cannot be changed" in rejected


def test_output_directory_is_immutable_by_default(tmp_path: Path) -> None:
    with pytest.raises(OutputExistsError):
        from eval_harness.artifacts import ensure_new_output

        ensure_new_output(tmp_path)


def test_evaluate_rejects_modified_saved_deliverable(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_config(tmp_path, source))
    executor = FakeExecutor()
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, executor)
    artifact = run_dir / "conditions/baseline/tasks/task-1/repeat_0/deliverables/answer.txt"
    artifact.write_text("tampered", encoding="utf-8")
    eval_config = EvaluationConfig(
        method="scalar",
        runtime=RuntimeConfig("codex", "gpt-5.6-luna", {"timeout_seconds": 10}),
    )
    with pytest.raises(ArtifactError):
        evaluate_run(run_dir, eval_config, tmp_path / "evaluation", executor)


def test_run_retries_failed_attempt_and_preserves_prior_artifacts(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_config(tmp_path, source, max_retries=1))
    executor = OutcomeExecutor(["failed", "completed"])

    summary = run_experiment(config, tmp_path / "run", executor)

    assert summary.execution_status == "completed"
    assert summary.pending_count == 0
    assert len(executor.requests) == 2
    execution_dir = summary.run_dir / "conditions/baseline/tasks/task-1/repeat_0"
    record = json.loads((execution_dir / "execution.json").read_text())
    assert record["attempt_count"] == 2
    assert [item["execution_status"] for item in record["attempt_history"]] == ["failed", "completed"]
    assert (execution_dir / "attempts/attempt_0/agent_response.txt").is_file()
    assert record["execution_status"] == "completed"


def test_interrupted_run_freezes_later_records_for_resume(tmp_path: Path) -> None:
    source = _task_source(tmp_path, count=2)
    config = load_experiment(_config(tmp_path, source, limit=2))
    first = OutcomeExecutor(["interrupted"])

    summary = run_experiment(config, tmp_path / "run", first)

    assert summary.execution_status == "interrupted"
    assert summary.completed_count == 0
    assert summary.failed_count == 1
    assert summary.pending_count == 1
    assert len(first.requests) == 1
    state = json.loads((summary.run_dir / "run_state.json").read_text())
    assert [item["execution_status"] for item in state] == ["interrupted", "pending"]

    second = OutcomeExecutor(["completed", "completed"])
    resumed = resume_run(summary.run_dir, second)

    assert resumed.execution_status == "completed"
    assert resumed.pending_count == 0
    assert resumed.completed_count == 2
    assert len(second.requests) == 2


def test_failed_inline_creator_resumes_from_frozen_creation_inputs(tmp_path: Path) -> None:
    class CreatorThenApplication(FakeExecutor):
        def __init__(self) -> None:
            super().__init__()
            self.creator_calls = 0

        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            if request.purpose != "skill_creation":
                return super().execute(request)
            self.creator_calls += 1
            (request.cwd / "SKILL.md").write_text(
                "---\nname: arithmetic\ndescription: Arithmetic workflow.\n---\n\nUse arithmetic.",
                encoding="utf-8",
            )
            result = super().execute(request)
            if self.creator_calls == 1:
                return replace(result, status="interrupted", error="creator interrupted")
            return result

    source = _task_source(tmp_path)
    build = tmp_path / "build.yaml"
    build.write_text(
        "name: arithmetic\nexecutor: codex\nmodel: gpt-5.6-luna\nprompt: Create arithmetic guidance.\n",
        encoding="utf-8",
    )
    config_path = _config(tmp_path, source)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "    intervention: null", "    intervention:\n      build: build.yaml"
        ),
        encoding="utf-8",
    )
    executor = CreatorThenApplication()
    run_dir = tmp_path / "run"
    with pytest.raises(HarnessError, match="creator interrupted"):
        run_experiment(load_experiment(config_path), run_dir, executor, check_auth=False)
    run_manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert run_manifest["failure_stage"] == "skill_creation"
    assert run_manifest["execution_status"] == "failed"

    source.unlink()
    build.unlink()
    config_path.unlink()
    resumed = resume_run(run_dir, executor, check_auth=False)

    assert resumed.execution_status == "completed"
    assert executor.creator_calls == 2
    assert len([request for request in executor.requests if request.purpose == "application"]) == 1


def test_run_freezes_all_creator_sources_before_first_creator_call(tmp_path: Path) -> None:
    class TwoCreatorExecutor(FakeExecutor):
        def __init__(self, second_input: Path, second_build: Path) -> None:
            super().__init__()
            self.second_input = second_input
            self.second_build = second_build
            self.creator_inputs: list[str] = []

        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            if request.purpose != "skill_creation":
                return super().execute(request)
            if "name: skill-one" in request.prompt:
                skill_name = "skill-one"
                expected_input = "first source v1"
                self.second_input.write_text("second source changed", encoding="utf-8")
                self.second_build.unlink()
            else:
                skill_name = "skill-two"
                expected_input = "second source v1"
            staged = next((request.cwd / "creation_inputs").iterdir()).read_text(encoding="utf-8")
            self.creator_inputs.append(staged)
            assert expected_input in staged
            (request.cwd / "SKILL.md").write_text(
                f"---\nname: {skill_name}\ndescription: Test Skill.\n---\n\nUse it.",
                encoding="utf-8",
            )
            return super().execute(request)

    task_source = _task_source(tmp_path)
    first_input = tmp_path / "first.txt"
    second_input = tmp_path / "second.txt"
    first_input.write_text("first source v1", encoding="utf-8")
    second_input.write_text("second source v1", encoding="utf-8")
    first_build = tmp_path / "first-build.yaml"
    second_build = tmp_path / "second-build.yaml"
    for build, name, input_path in (
        (first_build, "skill-one", first_input),
        (second_build, "skill-two", second_input),
    ):
        build.write_text(
            f"name: {name}\nexecutor: codex\nmodel: gpt-5.6-luna\nprompt: Create {name}.\n"
            f"inputs: [{input_path.name}]\n",
            encoding="utf-8",
        )
    config_path = _config(tmp_path, task_source)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  - id: baseline\n    intervention: null",
            "  - id: first\n    intervention:\n      build: first-build.yaml\n"
            "  - id: second\n    intervention:\n      build: second-build.yaml",
        ),
        encoding="utf-8",
    )
    executor = TwoCreatorExecutor(second_input, second_build)

    summary = run_experiment(load_experiment(config_path), tmp_path / "run", executor, check_auth=False)

    assert summary.execution_status == "completed"
    assert executor.creator_inputs == ["first source v1", "second source v1"]


def test_interrupted_evaluation_resumes_and_reuses_generation_identity(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    config = load_experiment(_config(tmp_path, source))
    run_dir = tmp_path / "run"
    run_experiment(config, run_dir, FakeExecutor())
    eval_config = EvaluationConfig(
        method="scalar",
        runtime=RuntimeConfig("codex", "gpt-5.6-luna", {"timeout_seconds": 10}),
    )
    evaluation_dir = tmp_path / "evaluation"
    interrupted = InterruptedJudgeExecutor()
    first = evaluate_run(run_dir, eval_config, evaluation_dir, interrupted)
    assert first.status == "interrupted"
    saved = json.loads((evaluation_dir / "judgments.jsonl").read_text().splitlines()[0])
    assert saved["evaluation_status"] == "interrupted"

    resumed = resume_evaluation(evaluation_dir, FakeExecutor())

    assert resumed.status == "completed"
    replacement = json.loads((evaluation_dir / "judgments.jsonl").read_text().splitlines()[0])
    assert replacement["evaluation_status"] == "completed"
    assert replacement["generation_id"] == saved["generation_id"]
    state = json.loads((evaluation_dir / "evaluation_state.json").read_text())
    assert state["pending_generation_ids"] == []


@pytest.mark.parametrize("include_partial", [False, True])
def test_partial_evaluation_keeps_failed_execution_and_frozen_artifacts(tmp_path: Path, include_partial: bool) -> None:
    from eval_harness.artifacts import file_manifest

    source = _task_source(tmp_path)
    run_dir = tmp_path / "run"
    run_experiment(load_experiment(_config(tmp_path, source)), run_dir, OutcomeExecutor(["timeout"]))
    before = file_manifest(run_dir)
    evaluator = FakeExecutor()
    config = EvaluationConfig(
        "scalar",
        RuntimeConfig("codex", "gpt-5.6-luna", {"timeout_seconds": 10}),
        include_partial_artifacts=include_partial,
    )
    output = tmp_path / "evaluation"
    evaluate_run(run_dir, config, output, evaluator)
    record = json.loads((output / "judgments.jsonl").read_text().splitlines()[0])
    assert record["execution_status"] == "timeout"
    assert file_manifest(run_dir) == before
    if include_partial:
        assert record["evaluation_status"] == "completed"
        assert record["partial_artifact_evaluation"] is True
        assert record["submission_completeness"] == "partial"
        assert len(evaluator.requests) == 1
        prompt = evaluator.requests[0].prompt
        assert "sealed partial submission" in prompt
        assert "The answer file exists" in prompt and "baseline" not in prompt
        assert (evaluator.requests[0].cwd / "submission" / "agent_response.txt").exists()
        manifest = json.loads((output / "evaluation_manifest.json").read_text())
        assert manifest["config_snapshot"]["include_partial_artifacts"] is True
    else:
        assert record["evaluation_status"] == "not_evaluated"
        assert evaluator.requests == []


def test_partial_evaluation_rejects_changed_artifact_before_model(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    run_dir = tmp_path / "run"
    run_experiment(load_experiment(_config(tmp_path, source)), run_dir, OutcomeExecutor(["timeout"]))
    (run_dir / "conditions/baseline/tasks/task-1/repeat_0/deliverables/agent_response.txt").write_text("changed")
    evaluator = FakeExecutor()
    config = EvaluationConfig(
        "scalar",
        RuntimeConfig("codex", "gpt-5.6-luna", {}),
        include_partial_artifacts=True,
    )
    with pytest.raises(ArtifactError, match="artifact|manifest|deliverable"):
        evaluate_run(run_dir, config, tmp_path / "evaluation", evaluator)
    assert evaluator.requests == []


def test_partial_evaluation_resume_preserves_opt_in_and_source_status(tmp_path: Path) -> None:
    from eval_harness.artifacts import file_manifest

    source = _task_source(tmp_path)
    run_dir = tmp_path / "run"
    run_experiment(load_experiment(_config(tmp_path, source)), run_dir, OutcomeExecutor(["failed"]))
    before = file_manifest(run_dir)
    output = tmp_path / "evaluation"
    config = EvaluationConfig(
        "scalar",
        RuntimeConfig("codex", "gpt-5.6-luna", {}),
        include_partial_artifacts=True,
    )
    evaluate_run(run_dir, config, output, InterruptedJudgeExecutor())
    resumed = resume_evaluation(output, FakeExecutor())
    record = json.loads((output / "judgments.jsonl").read_text().splitlines()[0])
    assert resumed.status == "completed"
    assert record["execution_status"] == "failed"
    assert record["partial_artifact_evaluation"] is True
    assert file_manifest(run_dir) == before


def test_partial_evaluation_config_is_explicit_and_scalar_only(tmp_path: Path) -> None:
    from eval_harness.config import evaluation_snapshot, load_evaluation_config, validate_evaluation_config
    from eval_harness.evaluate_pipeline import _evaluation_config_from_snapshot, _saved_execution_is_evaluable

    path = tmp_path / "evaluation.yaml"
    path.write_text("method: scalar\nexecutor: codex\nmodel: gpt-5.6-luna\ninclude_partial_artifacts: true\n")
    config = load_evaluation_config(path)
    assert config.include_partial_artifacts is True
    assert _evaluation_config_from_snapshot(evaluation_snapshot(config)).include_partial_artifacts is True
    assert not _saved_execution_is_evaluable({"execution_status": "pending"}, config)
    assert validate_evaluation_config(replace(config, method="pairwise"))
    path.write_text(path.read_text().replace("true", "'true'"))
    with pytest.raises(ConfigError, match="must be boolean"):
        load_evaluation_config(path)
