# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Evaluator context survives compaction without exposing it to participants."""

from __future__ import annotations

import json
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from test_evaluation_panel import _criteria, _parsed
from test_inline_skill_run import InlineExecutor
from test_pipeline import FakeExecutor, InterruptedJudgeExecutor, _config, _task_source, _two_condition_config

from eval_harness.artifacts import file_manifest, read_json
from eval_harness.benchmark import task_from_snapshot
from eval_harness.capability_service import CapabilityService
from eval_harness.config import EvaluationConfig, RuntimeConfig, load_experiment
from eval_harness.evaluate_pipeline import (
    _judge_response_schema,
    _stage_evaluation_inputs,
    evaluate_run,
    resume_evaluation,
)
from eval_harness.executor import ExecutionRequest, ExecutionResult
from eval_harness.grading_criteria import criteria_for_task, criteria_hash
from eval_harness.inspection_protocol import protocol_hash
from eval_harness.run_pipeline import run_experiment


def _protocol() -> dict[str, Any]:
    rule = {
        "required_methods": ["content"],
        "acceptable_inference": None,
        "unconfirmed_conditions": ["Observe the applicable branch; otherwise leave unconfirmed."],
        "human_review": None,
    }
    return {
        "schema_version": 1,
        "version": "recoverable-v1",
        "criteria_sha256": criteria_hash(_criteria()),
        "tasks": {"task-1": {"useful": rule}, "task-2": {"useful": rule}},
    }


def _snapshot(rubric: Any) -> dict[str, Any]:
    return {
        "raw": {
            "task_id": "task-1",
            "prompt": "Preserve the original task.\n日本語 ±0.5% and conditional branches.",
            "rubric_json": rubric,
            "rubric_pretty": "[-2] If supplied, the value must not exceed 5; otherwise this is optional.\n",
            "deliverable_file_urls": ["https://example.org/PRIVATE-GOLD-URL"],
            "unrelated_metadata": "PRIVATE-CONDITION-METADATA",
        },
        "source_path": "/PRIVATE-SOURCE-PATH",
        "source_line": 9,
    }


@pytest.mark.parametrize(
    "rubric",
    [
        [{"rubric_item_id": "original-id", "score": -2, "criterion": "If present: ≤5; optional otherwise."}],
        '[{"rubric_item_id":"original-id","score":-2,"criterion":"If present: ≤5; optional otherwise."}]',
        None,
    ],
)
def test_current_task_inputs_round_trip_exactly_without_raw_metadata(tmp_path: Path, rubric: Any) -> None:
    task = task_from_snapshot(_snapshot(rubric), "gdpval")
    criteria = criteria_for_task(_criteria(), task.task_id, "gdpval")
    assert criteria is not None
    criteria["mechanical"] = [{"id": "private-mechanical", "expected": "PRIVATE-MECHANICAL-ANSWER"}]
    protocol = _protocol()
    protocol["tasks"]["task-2"] = {"PRIVATE-OTHER-ITEM": {"description": "PRIVATE-OTHER-TASK"}}
    schema = _judge_response_schema("scalar", criteria, allow_unconfirmed=True, inspection_protocol=True)
    prompt = _stage_evaluation_inputs(tmp_path, task, criteria, protocol, "Current evaluator instructions.", schema)
    context = tmp_path / "evidence/evaluation-inputs"
    assert read_json(context / "task.json") == {
        "task_id": task.task_id,
        "prompt": task.prompt,
        "rubric_json": rubric,
        "rubric_pretty": task.rubric_pretty,
    }
    assert read_json(context / "criteria.json") == {key: criteria[key] for key in ("version", "policy", "ai")}
    assert read_json(context / "inspection_protocol.json") == {
        "version": protocol["version"],
        "protocol_sha256": protocol_hash(protocol),
        "criteria": protocol["tasks"][task.task_id],
    }
    assert read_json(context / "response_schema.json") == schema
    assert (context / "evaluator_prompt.txt").read_text() == prompt
    assert "reread these files before judging" in prompt
    assert (
        json.loads(prompt.split("Requested response JSON Schema (exact structured-output contract):\n")[1]) == schema
    )
    staged = "\n".join(path.read_text() for path in context.iterdir())
    assert "PRIVATE-" not in staged
    assert "task-2" not in staged


def test_optional_inputs_are_explicit_null_and_existing_inputs_are_not_replaced(tmp_path: Path) -> None:
    task = task_from_snapshot(_snapshot(None), "gdpval")
    schema = _judge_response_schema("scalar", None)
    _stage_evaluation_inputs(tmp_path, task, None, None, "No declared criteria.", schema)
    context = tmp_path / "evidence/evaluation-inputs"
    assert read_json(context / "criteria.json") is None
    assert read_json(context / "inspection_protocol.json") is None
    before = file_manifest(context)
    with pytest.raises(FileExistsError):
        _stage_evaluation_inputs(tmp_path, task, None, None, "Replacement must not overwrite.", schema)
    assert file_manifest(context) == before


class RecoveringJudge(FakeExecutor):
    """Model-free executor reads durable files rather than remembering criterion text."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.requests.append(request)
        assert request.purpose == "evaluation"
        context = request.cwd / "evidence/evaluation-inputs"
        task = read_json(context / "task.json")
        criteria = read_json(context / "criteria.json")
        protocol = read_json(context / "inspection_protocol.json")
        assert task["task_id"] in {"task-1", "task-2"}
        assert task["rubric_json"] == [{"score": 1, "criterion": "The answer file exists."}]
        frozen = criteria_for_task(_criteria(), task["task_id"], "gdpval")
        assert frozen is not None
        assert criteria == {key: frozen[key] for key in ("version", "policy", "ai")}
        assert protocol["criteria"] == _protocol()["tasks"][task["task_id"]]
        assert read_json(context / "response_schema.json") == request.response_schema
        assert (context / "evaluator_prompt.txt").read_text() == request.prompt
        assert "gpt-5.6-luna" not in request.prompt
        assert "baseline" not in request.prompt and "variant" not in request.prompt
        field, outcome = ("winner", "unjudgeable") if (request.cwd / "submission_A").exists() else ("score", None)
        response = {
            field: outcome,
            "rationale": "Fixture recovers criteria, but makes no artifact inspection claim.",
            "criteria_results": [
                {
                    "id": item["id"],
                    "status": "unconfirmed",
                    "evidence": "No inspection in this fixture.",
                    "reason": item["description"],
                    "observation_kind": "unconfirmed",
                    "evidence_refs": [],
                }
                for item in criteria["ai"]
            ],
        }
        parsed = _parsed(json.dumps(response))
        stdout = "\n".join(json.dumps(event) for event in parsed.events) + "\n"
        return ExecutionResult(("fixture",), 0, "completed", 0.01, stdout, "", parsed)


@pytest.mark.parametrize("method", ["scalar", "pairwise"])
def test_pipeline_stages_scoped_frozen_inputs_only_for_evaluation(tmp_path: Path, method: str) -> None:
    source = _task_source(tmp_path, count=2)
    path = _config(tmp_path, source, limit=2) if method == "scalar" else _two_condition_config(tmp_path, source)
    app = FakeExecutor()
    run = tmp_path / "run"
    run_experiment(load_experiment(path), run, app, check_auth=False)
    before = file_manifest(run)
    source.write_text("The mutable original task source has changed.\n")
    runtime = RuntimeConfig("codex", "gpt-5.6-luna", {"environment": {"profile": "gdpval-v1", "network_domains": []}})
    config = EvaluationConfig(method, runtime, criteria=_criteria(), inspection_protocol=_protocol())
    judge = RecoveringJudge()
    evaluation = tmp_path / "evaluation"
    summary = evaluate_run(run, config, evaluation, judge, check_auth=False)
    assert summary.status == "completed" and len(judge.requests) == 2
    assert file_manifest(run) == before
    assert all(not (r.cwd / "evidence/evaluation-inputs").exists() for r in app.requests)
    assert all("The answer file exists." not in r.prompt for r in app.requests)
    saved = file_manifest(evaluation)
    noop = RecoveringJudge()
    resume_evaluation(evaluation, noop, check_auth=False)
    assert not noop.requests
    # Completed judgments/context files remain byte-identical on resume.
    assert [x for x in file_manifest(evaluation) if x["path"].startswith("judgments/")] == [
        x for x in saved if x["path"].startswith("judgments/")
    ]


def test_legacy_completed_evaluation_without_durable_inputs_still_resumes(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    run = tmp_path / "run"
    run_experiment(load_experiment(_config(tmp_path, source)), run, FakeExecutor(), check_auth=False)
    config = EvaluationConfig("scalar", RuntimeConfig("codex", "gpt-5.6-luna", {}))
    old = tmp_path / "old"
    evaluate_run(run, config, old, FakeExecutor(), check_auth=False)
    context = next(old.glob("judgments/**/workspace/evidence/evaluation-inputs"))
    shutil.rmtree(context)  # Emulate a completed legacy fixture, never a real saved session.
    old_judgments = file_manifest(old / "judgments")
    no_calls = FakeExecutor()
    resume_evaluation(old, no_calls, check_auth=False)
    assert not no_calls.requests and file_manifest(old / "judgments") == old_judgments
    fresh = tmp_path / "new-evaluation"
    evaluate_run(run, config, fresh, FakeExecutor(), check_auth=False)
    assert list(fresh.glob("judgments/**/workspace/evidence/evaluation-inputs/task.json"))


def test_interrupted_retry_archives_prior_inputs_and_recovers_frozen_source(tmp_path: Path) -> None:
    source = _task_source(tmp_path)
    run = tmp_path / "run"
    run_experiment(load_experiment(_config(tmp_path, source)), run, FakeExecutor(), check_auth=False)
    config = EvaluationConfig("scalar", RuntimeConfig("codex", "gpt-5.6-luna", {}))
    evaluation = tmp_path / "evaluation"
    evaluate_run(run, config, evaluation, InterruptedJudgeExecutor(), check_auth=False)
    context = next(evaluation.glob("judgments/**/workspace/evidence/evaluation-inputs"))
    before = file_manifest(context)
    source.unlink()
    retry = FakeExecutor()
    resume_evaluation(evaluation, retry, check_auth=False)
    assert len(retry.requests) == 1
    archived = next(evaluation.glob("judgments/**/attempts/0/workspace/evidence/evaluation-inputs"))
    assert file_manifest(archived) == before
    assert file_manifest(retry.requests[0].cwd / "evidence/evaluation-inputs") == before


@pytest.mark.skipif(sys.platform != "darwin", reason="actual Seatbelt isolation is required")
def test_actual_evaluation_service_reads_inputs_but_denies_writes_and_other_tasks(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    task = task_from_snapshot(_snapshot([{"score": -2, "criterion": "Keep exact source text."}]), "gdpval")
    schema = _judge_response_schema("scalar", None)
    _stage_evaluation_inputs(workspace, task, None, None, "Evaluator instructions.", schema)
    other = tmp_path / "other-task.json"
    other.write_text("PRIVATE OTHER TASK")
    before = file_manifest(workspace / "evidence")
    python = Path(sys.executable).resolve()
    service = CapabilityService(
        workspace,
        tmp_path / "state",
        "evaluation",
        {"network_domains": [], "python": str(python), "python_roots": [str(python.parent.parent)]},
    )
    code = f"""from pathlib import Path
import json
root = Path('evidence/evaluation-inputs')
values = {{p.name: p.read_text() for p in root.iterdir()}}
denied = []
for p in root.iterdir():
    try:
        p.write_text('tampered')
    except PermissionError:
        denied.append(p.name)
try:
    Path({str(other)!r}).read_text()
    outside_denied = False
except PermissionError:
    outside_denied = True
print(json.dumps({{'values': values, 'write_denied': sorted(denied), 'other_task_denied': outside_denied}}))
"""
    result = service.invoke("shell", {"command": f"exec {shlex.quote(str(python))} -c {shlex.quote(code)}"})
    assert result["status"] == "completed", result
    observed = json.loads(result["stdout"])
    assert json.loads(observed["values"]["task.json"])["prompt"] == task.prompt
    assert json.loads(observed["values"]["response_schema.json"]) == schema
    assert observed["write_denied"] == sorted(observed["values"])
    assert len(observed["values"]) == 5 and observed["other_task_denied"] is True
    assert file_manifest(workspace / "evidence") == before


def test_inline_creation_and_application_never_receive_evaluator_inputs(tmp_path: Path) -> None:
    class NoEvaluationContext(InlineExecutor):
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            assert not (request.cwd / "evidence/evaluation-inputs").exists()
            assert "Durable evaluator-only inputs" not in request.prompt
            return super().execute(request)

    (tmp_path / "tasks.jsonl").write_text(json.dumps({"question": "Two plus two?", "expected_answer": 4}) + "\n")
    (tmp_path / "build.yaml").write_text(
        "name: word-problems\nexecutor: codex\nmodel: gpt-5.6-luna\nprompt: General arithmetic.\n"
    )
    config_path = tmp_path / "experiment.yaml"
    config_path.write_text("""benchmark: gsm8k
tasks: {path: tasks.jsonl, limit: 1}
application: {executor: codex, model: gpt-5.6-luna}
conditions:
  - id: A
    intervention: {build: build.yaml}
""")
    executor = NoEvaluationContext()
    run_experiment(load_experiment(config_path), tmp_path / "run", executor, check_auth=False)
    assert executor.purposes == ["skill_creation", "application"]
