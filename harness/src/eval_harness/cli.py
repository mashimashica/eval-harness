# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Command line entry point for the local eval harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import read_json
from .benchmark import load_tasks, reference_source_paths, select_tasks
from .claude_executor import ClaudeExecutor
from .compare_pipeline import compare_evaluations
from .config import load_evaluation_config, load_experiment, validate_config
from .errors import ConfigError, HarnessError
from .evaluate_pipeline import evaluate_run, resume_evaluation
from .executor import CodexExecutor
from .run_pipeline import _preflight_evaluation, _preflight_interventions, resume_run, run_experiment
from .skill_pipeline import build_skill, load_build_config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval-harness", description="Run bounded account-authenticated agent evaluations"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="validate configuration, inputs and account authentication")
    check.add_argument("experiment", type=Path)

    build = subparsers.add_parser("build", help="materialize a reusable Skill from a build configuration")
    build.add_argument("build_config", type=Path)
    build.add_argument("--out", required=True, type=Path)

    run = subparsers.add_parser("run", help="execute selected benchmark tasks")
    run.add_argument("experiment", type=Path)
    run.add_argument("--out", required=True, type=Path)

    evaluate = subparsers.add_parser("evaluate", help="score saved artifacts without regenerating them")
    evaluate.add_argument("run_dir", type=Path)
    evaluate.add_argument("--config", required=True, type=Path)
    evaluate.add_argument("--out", required=True, type=Path)

    compare = subparsers.add_parser("compare", help="aggregate saved evaluations without model calls")
    compare.add_argument("inputs", nargs="+", type=Path)
    compare.add_argument("--out", required=True, type=Path)

    resume = subparsers.add_parser("resume", help="continue an incomplete run or evaluation")
    resume.add_argument("result_dir", type=Path)
    return parser


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _executor_factory(name: str) -> CodexExecutor | ClaudeExecutor:
    if name == "codex":
        return CodexExecutor()
    if name == "claude-code":
        return ClaudeExecutor()
    raise ConfigError(f"no CLI executor is registered for {name!r}")


def _executor_factory_fn(name: str) -> CodexExecutor | ClaudeExecutor:
    """Factory target kept separate so pipeline calls never accept arbitrary names."""

    return _executor_factory(name)


def _check(experiment_path: Path) -> int:
    config = load_experiment(experiment_path)
    errors = validate_config(config)
    if errors:
        raise ConfigError("configuration is invalid:\n" + "\n".join(f"- {error}" for error in errors))
    tasks = load_tasks(config)
    selected = select_tasks(tasks, config)
    for task in selected:
        reference_source_paths(task)
    executor = _executor_factory(config.application.executor)
    auth = executor.check_auth(config.application.settings)
    if not auth.authenticated:
        raise HarnessError(f"{config.application.executor} account authentication is unavailable: {auth.detail}")
    condition_auth: dict[str, str] = {}
    for condition in config.conditions:
        condition_executor = _executor_factory(condition.application.executor)
        condition_status = condition_executor.check_auth(condition.application.settings)
        if not condition_status.authenticated:
            raise HarnessError(
                f"condition {condition.id} account authentication is unavailable: {condition_status.detail}"
            )
        condition_auth[condition.id] = condition_status.detail
    _preflight_interventions(config, executor, _executor_factory_fn, check_auth=True)
    evaluation_status = _preflight_evaluation(config, executor, _executor_factory_fn, check_auth=True)
    evaluation_auth = evaluation_status.detail if evaluation_status is not None else None
    _print(
        {
            "status": "ready",
            "benchmark": config.benchmark,
            "task_source": str(config.tasks.path) if config.tasks.path else "inline",
            "available_task_count": len(tasks),
            "selected_task_ids": [task.task_id for task in selected],
            "condition_ids": [condition.id for condition in config.conditions],
            "application_executor": config.application.executor,
            "application_model": config.application.model,
            "evaluation": config.evaluation.method if config.evaluation else None,
            "application_auth": auth.detail,
            "condition_auth": condition_auth,
            "evaluation_auth": evaluation_auth,
        }
    )
    return 0


def _build(build_path: Path, output: Path) -> int:
    config = load_build_config(build_path)
    executor = _executor_factory(config.runtime.executor)
    skill_dir = build_skill(config, output, executor)
    _print(
        {
            "status": "completed",
            "skill_dir": str(skill_dir),
            "creation_id": read_json(skill_dir / "skill_manifest.json").get("creation_id"),
        }
    )
    return 0


def _run(experiment_path: Path, output: Path) -> int:
    config = load_experiment(experiment_path)
    executor = _executor_factory(config.application.executor)
    summary = run_experiment(config, output, executor, executor_factory=_executor_factory_fn)
    _print(
        {
            "status": summary.execution_status,
            "run_dir": str(summary.run_dir),
            "run_id": summary.run_id,
            "task_count": summary.task_count,
            "completed_count": summary.completed_count,
            "failed_count": summary.failed_count,
            "evaluation_status": summary.evaluation_status,
            "evaluation_dir": str(summary.evaluation_dir) if summary.evaluation_dir else None,
            "comparison_dir": str(summary.comparison_dir) if summary.comparison_dir else None,
        }
    )
    return (
        0
        if summary.execution_status == "completed" and summary.evaluation_status in {"completed", "not_started"}
        else 1
    )


def _evaluate(run_dir: Path, evaluation_path: Path, output: Path) -> int:
    config = load_evaluation_config(evaluation_path)
    executor = (
        _executor_factory(config.runtime.executor) if config.method not in {"mechanical", "human"} else CodexExecutor()
    )
    summary = evaluate_run(run_dir, config, output, executor)
    _print(
        {
            "status": summary.status,
            "evaluation_dir": str(summary.evaluation_dir),
            "evaluation_id": summary.evaluation_id,
            "attempted_count": summary.attempted_count,
            "valid_count": summary.valid_count,
        }
    )
    return 0 if summary.status == "completed" else 1


def _resume(result_dir: Path) -> int:
    root = result_dir.expanduser().resolve()
    if (root / "run_manifest.json").is_file():
        manifest = read_json(root / "run_manifest.json")
        snapshot = manifest.get("config_snapshot")
        resolved = snapshot.get("_resolved") if isinstance(snapshot, Mapping) else None
        application = resolved.get("application") if isinstance(resolved, Mapping) else None
        executor_name = application.get("executor") if isinstance(application, Mapping) else None
        if not isinstance(executor_name, str) or not executor_name:
            raise HarnessError("run manifest does not contain a frozen application executor")
        executor = _executor_factory(executor_name)
        run_summary = resume_run(root, executor, executor_factory=_executor_factory_fn)
        _print(
            {
                "status": run_summary.execution_status,
                "run_dir": str(root),
                "completed_count": run_summary.completed_count,
                "failed_count": run_summary.failed_count,
            }
        )
        return 0 if run_summary.execution_status == "completed" else 1
    if (root / "evaluation_manifest.json").is_file():
        manifest = read_json(root / "evaluation_manifest.json")
        snapshot = manifest.get("config_snapshot")
        method = snapshot.get("method") if isinstance(snapshot, Mapping) else None
        executor_name = snapshot.get("executor") if isinstance(snapshot, Mapping) else None
        if method in {"mechanical", "human"}:
            executor = CodexExecutor()
        elif isinstance(executor_name, str) and executor_name:
            executor = _executor_factory(executor_name)
        else:
            raise HarnessError("evaluation manifest does not contain a frozen evaluator executor")
        evaluation_summary = resume_evaluation(root, executor)
        _print(
            {
                "status": evaluation_summary.status,
                "evaluation_dir": str(root),
                "valid_count": evaluation_summary.valid_count,
            }
        )
        return 0 if evaluation_summary.status == "completed" else 1
    raise HarnessError(f"result directory is not a run or evaluation: {root}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "check":
            return _check(args.experiment)
        if args.command == "build":
            return _build(args.build_config, args.out)
        if args.command == "run":
            return _run(args.experiment, args.out)
        if args.command == "evaluate":
            return _evaluate(args.run_dir, args.config, args.out)
        if args.command == "compare":
            report_dir = compare_evaluations(args.inputs, args.out)
            _print({"status": "completed", "report_dir": str(report_dir)})
            return 0
        if args.command == "resume":
            return _resume(args.result_dir)
    except (HarnessError, ConfigError, OSError) as exc:
        print(f"eval-harness: error: {exc}", flush=True)
        return 2
    return 2
