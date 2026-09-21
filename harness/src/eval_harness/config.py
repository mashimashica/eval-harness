# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration loading and validation for the local harness.

The configuration objects deliberately keep the schema small.  A resolved
snapshot is written with every run/evaluation so later source YAML edits cannot
change a resumed operation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .capability_environment import enabled as capability_enabled
from .capability_environment import environment_fingerprint, parse_environment
from .errors import ConfigError
from .grading_criteria import load_criteria
from .inspection_protocol import load_inspection_protocol
from .models import CLAUDE_EFFORTS, CODEX_EFFORTS, MODEL_EFFORTS
from .office_rendering import OfficeRenderingConfig, parse_rendering

_SECRET_KEY_MARKERS = ("api_key", "access_token", "password", "secret", "token")
_SUPPORTED_CODEX_MODELS = set(CODEX_EFFORTS)
_SUPPORTED_CLAUDE_MODELS = set(CLAUDE_EFFORTS)
_SUPPORTED_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
_MODEL_REASONING_EFFORTS = MODEL_EFFORTS


@dataclass(frozen=True)
class TaskSelection:
    """The source and deterministic subset selection for benchmark tasks."""

    path: Path | None
    limit: int
    seed: int
    ids: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    reference_overrides: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class RuntimeConfig:
    """An independently selectable CLI runtime, model and settings mapping."""

    executor: str
    model: str | None
    settings: dict[str, Any]


@dataclass(frozen=True)
class InterventionConfig:
    """An optional reusable Skill or an inline Skill creation configuration."""

    path: Path | None = None
    build: Path | None = None
    prompt: str | None = None


@dataclass(frozen=True)
class ConditionConfig:
    """A recorded application condition."""

    id: str
    application: RuntimeConfig
    intervention: InterventionConfig | None


@dataclass(frozen=True)
class JudgeConfig:
    """A named independent panel member; the ID is not shown to other judges."""

    id: str
    runtime: RuntimeConfig


@dataclass(frozen=True)
class EvaluationConfig:
    """A grading configuration independent from task execution."""

    method: str
    runtime: RuntimeConfig
    judges: tuple[JudgeConfig, ...] = ()
    criteria: dict[str, Any] | None = None
    pairs: tuple[tuple[str, str], ...] | None = None
    office_rendering: OfficeRenderingConfig | None = None
    inspection_protocol: dict[str, Any] | None = None


@dataclass(frozen=True)
class LimitsConfig:
    """Explicit bounds for one local operation."""

    max_tasks: int
    max_retries: int
    concurrency: int


@dataclass(frozen=True)
class ExperimentConfig:
    """Resolved experiment configuration."""

    config_path: Path
    benchmark: str
    tasks: TaskSelection
    repeats: int
    application: RuntimeConfig
    conditions: tuple[ConditionConfig, ...]
    evaluation: EvaluationConfig | None
    limits: LimitsConfig
    raw: dict[str, Any]
    source_bytes: bytes
    comparison_design: str = "general"
    creation_repeats: int = 1


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"{field} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _string(value: Any, field: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        suffix = "" if required else " when supplied"
        raise ConfigError(f"{field} must be a non-empty string{suffix}")
    return value.strip()


def _integer(value: Any, field: str, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{field} must be an integer")
    return value


def _resolve_path(base: Path, value: Any, field: str, *, required: bool = False) -> Path | None:
    text = _string(value, field, required=required)
    if text is None:
        return None
    path = Path(text).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            copied[str(key)] = _copy_mapping(item)
        elif isinstance(item, list):
            copied[str(key)] = [_copy_mapping(child) if isinstance(child, Mapping) else child for child in item]
        else:
            copied[str(key)] = item
    return copied


def _runtime(
    value: Any,
    field: str,
    *,
    default: RuntimeConfig | None = None,
    base_dir: Path | None = None,
) -> RuntimeConfig:
    mapping = _mapping(value, field)
    allowed_fields = {"executor", "model", "settings"}
    if field == "evaluation":
        allowed_fields.update({"method", "judges", "criteria", "pairs", "office_rendering", "inspection_protocol"})
    if field == "build":
        allowed_fields.update({"name", "prompt", "instructions", "inputs", "input_paths", "skills", "creator_skills"})
    unknown_fields = sorted(set(mapping) - allowed_fields)
    if unknown_fields:
        raise ConfigError(f"{field} has unsupported field(s): " + ", ".join(unknown_fields))
    if default is not None:
        executor = mapping.get("executor", default.executor)
        model = mapping.get("model", default.model)
        # SPEC says a supplied settings mapping replaces the default mapping.
        settings_value = mapping["settings"] if "settings" in mapping else default.settings
    else:
        executor = mapping.get("executor")
        model = mapping.get("model")
        settings_value = mapping.get("settings", {})

    executor_text = _string(executor, f"{field}.executor")
    model_text = _string(model, f"{field}.model", required=False)
    settings = _mapping(settings_value, f"{field}.settings")
    if base_dir is not None:
        read_paths = settings.get("toolchain_read_paths")
        if isinstance(read_paths, list):
            resolved_paths: list[Any] = []
            for item in read_paths:
                if isinstance(item, str) and item.strip():
                    resolved_paths.append(str(_resolve_path(base_dir, item, f"{field}.settings.toolchain_read_paths")))
                else:
                    resolved_paths.append(item)
            settings["toolchain_read_paths"] = resolved_paths
        auth_home = settings.get("auth_source_home")
        if isinstance(auth_home, str) and auth_home.strip():
            settings["auth_source_home"] = str(
                _resolve_path(base_dir, auth_home, f"{field}.settings.auth_source_home")
            )
        for path_key in ("ratings_path", "ratings_file"):
            rating_path = settings.get(path_key)
            if isinstance(rating_path, str) and rating_path.strip():
                settings[path_key] = str(_resolve_path(base_dir, rating_path, f"{field}.settings.{path_key}"))
    if "environment" in settings:
        settings["environment"] = parse_environment(settings["environment"], base_dir or Path.cwd())
        if "fingerprint" not in settings["environment"]:
            settings["environment"]["fingerprint"] = environment_fingerprint(settings["environment"])
    assert executor_text is not None
    return RuntimeConfig(executor=executor_text, model=model_text, settings=_copy_mapping(settings))


def _task_selection(raw: Any, base: Path) -> TaskSelection:
    if isinstance(raw, list):
        mapping: dict[str, Any] = {"rows": raw}
    else:
        mapping = _mapping(raw, "tasks")
    path_value = mapping.get("path", mapping.get("file", mapping.get("source")))
    path = _resolve_path(base, path_value, "tasks.path") if path_value is not None else None
    rows_value = mapping.get("rows", mapping.get("inline"))
    rows: list[dict[str, Any]] = []
    if rows_value is not None:
        if not isinstance(rows_value, Sequence) or isinstance(rows_value, (str, bytes)):
            raise ConfigError("tasks.rows must be a list of task mappings")
        for index, row in enumerate(rows_value):
            if not isinstance(row, Mapping):
                raise ConfigError(f"tasks.rows[{index}] must be a mapping")
            rows.append(_copy_mapping(row))
    if path is None and not rows:
        raise ConfigError("tasks.path (or tasks.rows) is required")
    if path is not None and rows:
        raise ConfigError("tasks.path and tasks.rows cannot be supplied together")
    limit = _integer(mapping.get("limit"), "tasks.limit", default=1)
    seed = _integer(mapping.get("seed"), "tasks.seed", default=0)
    ids_value = mapping.get("ids", [])
    if not isinstance(ids_value, Sequence) or isinstance(ids_value, (str, bytes)):
        raise ConfigError("tasks.ids must be a list of strings")
    ids: list[str] = []
    for index, item in enumerate(ids_value):
        item_text = _string(item, f"tasks.ids[{index}]")
        assert item_text is not None
        ids.append(item_text)
    overrides_value = mapping.get("reference_file_overrides", {})
    overrides_mapping = _mapping(overrides_value, "tasks.reference_file_overrides")
    reference_overrides: dict[str, tuple[str, ...]] = {}
    for task_id, paths_value in overrides_mapping.items():
        if not isinstance(paths_value, Sequence) or isinstance(paths_value, (str, bytes)):
            raise ConfigError(f"tasks.reference_file_overrides.{task_id} must be a list of paths")
        paths: list[str] = []
        for index, path_value in enumerate(paths_value):
            resolved = _resolve_path(
                base, path_value, f"tasks.reference_file_overrides.{task_id}[{index}]", required=True
            )
            assert resolved is not None
            paths.append(str(resolved))
        reference_overrides[task_id] = tuple(paths)
    return TaskSelection(
        path=path,
        limit=limit,
        seed=seed,
        ids=tuple(ids),
        rows=tuple(rows),
        reference_overrides=reference_overrides,
    )


def _limits(raw: Any) -> LimitsConfig:
    mapping = _mapping(raw, "limits")
    max_tasks = _integer(mapping.get("max_tasks"), "limits.max_tasks", default=1)
    max_retries = _integer(mapping.get("max_retries"), "limits.max_retries", default=0)
    concurrency = _integer(mapping.get("concurrency"), "limits.concurrency", default=1)
    return LimitsConfig(max_tasks=max_tasks, max_retries=max_retries, concurrency=concurrency)


def _condition(raw: Any, index: int, base: RuntimeConfig, config_dir: Path) -> ConditionConfig:
    mapping = _mapping(raw, f"conditions[{index}]")
    condition_id = _string(mapping.get("id"), f"conditions[{index}].id")
    assert condition_id is not None
    application = _runtime(
        mapping.get("application"), f"conditions[{index}].application", default=base, base_dir=config_dir
    )
    intervention_value = mapping.get("intervention")
    if intervention_value is None:
        intervention = None
    elif isinstance(intervention_value, str):
        path = _resolve_path(config_dir, intervention_value, f"conditions[{index}].intervention", required=True)
        assert path is not None
        intervention = InterventionConfig(path=path)
    elif isinstance(intervention_value, Mapping):
        intervention_mapping = _mapping(intervention_value, f"conditions[{index}].intervention")
        unknown = sorted(set(intervention_mapping) - {"path", "build", "prompt"})
        if unknown:
            raise ConfigError(f"conditions[{index}].intervention has unsupported field(s): " + ", ".join(unknown))
        path_value = intervention_mapping.get("path")
        build_value = intervention_mapping.get("build")
        prompt = _string(
            intervention_mapping.get("prompt"),
            f"conditions[{index}].intervention.prompt",
            required=False,
        )
        if path_value is not None and build_value is not None:
            raise ConfigError(f"conditions[{index}].intervention must select path or build, not both")
        if path_value is None and build_value is None and prompt is None:
            raise ConfigError(f"conditions[{index}].intervention requires path, build, or prompt")
        path = (
            _resolve_path(config_dir, path_value, f"conditions[{index}].intervention.path", required=True)
            if path_value is not None
            else None
        )
        build = (
            _resolve_path(config_dir, build_value, f"conditions[{index}].intervention.build", required=True)
            if build_value is not None
            else None
        )
        intervention = InterventionConfig(path=path, build=build, prompt=prompt)
    else:
        raise ConfigError(f"conditions[{index}].intervention must be null, a Skill path, or a mapping")
    return ConditionConfig(id=condition_id, application=application, intervention=intervention)


def _evaluation(raw: Any, config_dir: Path) -> EvaluationConfig | None:
    if raw is None:
        return None
    mapping = _mapping(raw, "evaluation")
    method = _string(mapping.get("method"), "evaluation.method")
    assert method is not None
    judges_value = mapping.get("judges", [])
    if not isinstance(judges_value, list):
        raise ConfigError("evaluation.judges must be a list")
    judges: list[JudgeConfig] = []
    for index, value in enumerate(judges_value):
        judge = _mapping(value, f"evaluation.judges[{index}]")
        identifier = _string(judge.pop("id", None), f"evaluation.judges[{index}].id")
        assert identifier is not None
        judges.append(JudgeConfig(identifier, _runtime(judge, f"evaluation.judges[{index}]", base_dir=config_dir)))
    runtime_mapping = {**mapping}
    if judges and "executor" not in mapping:
        if "model" in mapping or "settings" in mapping:
            raise ConfigError("with judges, put model/settings on each panel member and pairs at evaluation.pairs")
        runtime_mapping.update(runtime_snapshot(judges[0].runtime))
    runtime = _runtime(runtime_mapping, "evaluation", base_dir=config_dir)
    criteria = load_criteria(mapping.get("criteria"), config_dir)
    pairs = mapping.get("pairs")
    if pairs is not None:
        if not isinstance(pairs, list) or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or any(not isinstance(item, str) or not item.strip() for item in pair)
            or pair[0] == pair[1]
            for pair in pairs
        ):
            raise ConfigError("evaluation.pairs must be a list of two distinct condition IDs")
        if "pairs" in runtime.settings:
            raise ConfigError("specify evaluation.pairs or legacy settings.pairs, not both")
    return EvaluationConfig(
        method,
        runtime,
        tuple(judges),
        criteria,
        tuple(tuple(p) for p in pairs) if pairs is not None else None,
        parse_rendering(mapping.get("office_rendering"), config_dir),
        load_inspection_protocol(mapping.get("inspection_protocol"), config_dir, criteria),
    )


def load_experiment(path: str | Path) -> ExperimentConfig:
    """Load and resolve one experiment YAML file."""

    config_path = Path(path).expanduser().resolve()
    try:
        source_bytes = config_path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read configuration {config_path}: {exc}") from exc
    try:
        loaded = yaml.safe_load(source_bytes) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    raw = _mapping(loaded, "configuration")
    benchmark = _string(raw.get("benchmark"), "benchmark")
    assert benchmark is not None
    config_dir = config_path.parent
    tasks = _task_selection(raw.get("tasks"), config_dir)
    repeats = _integer(raw.get("repeats"), "repeats", default=1)
    application = _runtime(raw.get("application"), "application", base_dir=config_dir)
    condition_values = raw.get("conditions")
    if condition_values is None:
        condition_values = [{"id": "baseline", "intervention": None}]
    if not isinstance(condition_values, Sequence) or isinstance(condition_values, (str, bytes)):
        raise ConfigError("conditions must be a list of mappings")
    conditions = tuple(
        _condition(value, index, application, config_dir) for index, value in enumerate(condition_values)
    )
    evaluation = _evaluation(raw.get("evaluation"), config_dir)
    limits = _limits(raw.get("limits"))
    config = ExperimentConfig(
        config_path=config_path,
        benchmark=benchmark,
        tasks=tasks,
        repeats=repeats,
        application=application,
        conditions=conditions,
        evaluation=evaluation,
        limits=limits,
        raw=raw,
        source_bytes=source_bytes,
        comparison_design=str(raw.get("comparison_design", "general")),
        creation_repeats=_integer(raw.get("creation_repeats"), "creation_repeats", default=1),
    )
    errors = validate_config(config)
    if errors:
        raise ConfigError("configuration is invalid:\n" + "\n".join(f"- {error}" for error in errors))
    return config


def load_evaluation_config(path: str | Path) -> EvaluationConfig:
    """Load a direct evaluation YAML mapping (or an ``evaluation`` wrapper)."""

    config_path = Path(path).expanduser().resolve()
    try:
        loaded = yaml.safe_load(config_path.read_bytes()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read evaluation configuration {config_path}: {exc}") from exc
    raw = _mapping(loaded, "evaluation configuration")
    if "evaluation" in raw:
        raw = _mapping(raw["evaluation"], "evaluation")
    result = _evaluation(raw, config_path.parent)
    assert result is not None
    errors = validate_evaluation_config(result)
    if errors:
        raise ConfigError("evaluation configuration is invalid:\n" + "\n".join(f"- {error}" for error in errors))
    return result


def _contains_placeholder(value: str) -> bool:
    return "<" in value or ">" in value


def _validate_runtime(
    runtime: RuntimeConfig, field: str, *, extra_settings: frozenset[str] = frozenset()
) -> list[str]:
    errors: list[str] = []
    if runtime.executor not in {"codex", "claude-code"}:
        errors.append(f"{field}.executor={runtime.executor!r} is unsupported; choose codex or claude-code")
    if runtime.model is None:
        errors.append(f"{field}.model is required; the selected model must be recorded explicitly")
    elif _contains_placeholder(runtime.model):
        errors.append(f"{field}.model must be replaced; placeholder values are not executable")
    elif runtime.executor == "codex" and runtime.model not in _SUPPORTED_CODEX_MODELS:
        errors.append(
            f"{field}.model={runtime.model!r} is unsupported for Codex; choose one of "
            + ", ".join(sorted(_SUPPORTED_CODEX_MODELS))
        )
    elif runtime.executor == "claude-code" and runtime.model not in _SUPPORTED_CLAUDE_MODELS:
        errors.append(
            f"{field}.model={runtime.model!r} is unsupported for Claude Code; choose an exact model ID: "
            + ", ".join(sorted(_SUPPORTED_CLAUDE_MODELS))
        )
    allowed_settings = {
        "timeout_seconds",
        "reasoning_effort",
        "auth_source_home",
        "toolchain_read_paths",
        "environment",
    } | extra_settings
    if runtime.executor == "claude-code":
        allowed_settings.add("max_turns")
        allowed_settings.add("tool_mode")
    for key in runtime.settings:
        if key not in allowed_settings:
            errors.append(f"{field}.settings.{key} is unsupported for this runtime and operation")
        normalized = key.lower().replace("-", "_")
        if any(marker in normalized for marker in _SECRET_KEY_MARKERS):
            errors.append(f"{field}.settings.{key} must not contain credentials")
        if normalized in {"openai_base_url", "anthropic_base_url", "base_url"}:
            errors.append(f"{field}.settings.{key} is unsupported; API endpoint routing is not allowed")
    if "environment" in runtime.settings:
        try:
            parse_environment(runtime.settings["environment"], Path.cwd())
        except ConfigError as exc:
            errors.append(str(exc))
        if "tool_mode" in runtime.settings:
            errors.append("environment and legacy tool_mode cannot be combined")
    timeout = runtime.settings.get("timeout_seconds", 600)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or timeout <= 0
    ):
        errors.append(f"{field}.settings.timeout_seconds must be finite and positive")
    if "max_turns" in runtime.settings:
        turns = runtime.settings["max_turns"]
        if isinstance(turns, bool) or not isinstance(turns, int) or turns < 1:
            errors.append(f"{field}.settings.max_turns must be a positive integer")
    if "tool_mode" in runtime.settings and runtime.settings["tool_mode"] not in {"files", "sandboxed_shell"}:
        errors.append(f"{field}.settings.tool_mode must be files or sandboxed_shell")
    if "auth_source_home" in runtime.settings:
        source_home = runtime.settings["auth_source_home"]
        if not isinstance(source_home, str) or not source_home.strip():
            errors.append(f"{field}.settings.auth_source_home must be a non-empty directory path")
    if "sandbox" in runtime.settings:
        errors.append(
            f"{field}.settings.sandbox is unsupported; the harness creates its own minimal native permission profile"
        )
    if "sandbox_profile" in runtime.settings:
        errors.append(
            f"{field}.settings.sandbox_profile is unsupported; the harness creates its own per-invocation profile"
        )
    effort = runtime.settings.get("reasoning_effort")
    if effort is not None and (not isinstance(effort, str) or effort not in _SUPPORTED_REASONING_EFFORTS):
        errors.append(
            f"{field}.settings.reasoning_effort must be one of " + ", ".join(sorted(_SUPPORTED_REASONING_EFFORTS))
        )
    elif isinstance(effort, str) and runtime.model is not None:
        supported_efforts = _MODEL_REASONING_EFFORTS.get(runtime.model)
        if supported_efforts is not None and effort not in supported_efforts:
            errors.append(
                f"{field}.settings.reasoning_effort={effort!r} is unsupported for {runtime.model}; "
                + (
                    "choose one of " + ", ".join(sorted(supported_efforts))
                    if supported_efforts
                    else "omit reasoning_effort"
                )
            )
    read_paths = runtime.settings.get("toolchain_read_paths")
    if read_paths is not None:
        if not isinstance(read_paths, list) or any(
            not isinstance(item, str) or not item.strip() for item in read_paths
        ):
            errors.append(f"{field}.settings.toolchain_read_paths must be a list of non-empty strings")
        elif read_paths:
            errors.append(
                f"{field}.settings.toolchain_read_paths must be empty; the harness supplies its own toolchain paths"
            )
    return errors


def validate_evaluation_config(config: EvaluationConfig) -> list[str]:
    """Return all actionable errors for an evaluation configuration."""

    panel_errors: list[str] = []
    if config.inspection_protocol is not None:
        try:
            load_inspection_protocol(config.inspection_protocol, Path.cwd(), config.criteria)
        except ConfigError as exc:
            panel_errors.append(str(exc))
        if config.method not in {"scalar", "pairwise"}:
            panel_errors.append("inspection_protocol is supported only for scalar or pairwise AI grading")
        if any(
            not capability_enabled(runtime.settings)
            for runtime in ([judge.runtime for judge in config.judges] or [config.runtime])
        ):
            panel_errors.append("inspection_protocol requires a capability environment for every judge")
    capability_runtimes = [j.runtime for j in config.judges if capability_enabled(j.runtime.settings)]
    if not config.judges and capability_enabled(config.runtime.settings):
        capability_runtimes = [config.runtime]
    if capability_runtimes:
        if config.criteria is None:
            panel_errors.append("gdpval-v1 evaluation requires explicit frozen criteria and unconfirmed-item handling")
        if config.office_rendering is not None:
            panel_errors.append(
                "gdpval-v1 uses environment.office_rendering; do not combine legacy initial-image rendering"
            )
        native = [r.settings["environment"].get("office_rendering") for r in capability_runtimes]
        if any(value != native[0] for value in native):
            panel_errors.append(
                "incremental judge panels require the same declared Office renderer for shared derivatives"
            )
    if config.office_rendering is not None and config.method not in {"scalar", "pairwise"}:
        panel_errors.append("evaluation.office_rendering is supported only for scalar or pairwise AI grading")
    if config.pairs is not None and config.method != "pairwise":
        panel_errors.append("evaluation.pairs is supported only for pairwise grading")
    if config.judges:
        if config.method not in {"scalar", "pairwise"}:
            panel_errors.append("evaluation.judges is supported only for scalar or pairwise AI grading")
        if len({judge.id for judge in config.judges}) != len(config.judges):
            panel_errors.append("evaluation.judges IDs must be unique")
        if config.runtime != config.judges[0].runtime:
            panel_errors.append("top-level evaluation runtime must match the first panel member or be omitted")
        for judge in config.judges:
            panel_errors.extend(_validate_runtime(judge.runtime, f"evaluation.judges.{judge.id}"))
    if config.method == "mechanical":
        errors: list[str] = []
        if config.runtime.executor != "none":
            errors.append("evaluation.executor must be 'none' for mechanical grading")
        if config.runtime.model is not None:
            errors.append("evaluation.model must be omitted for mechanical grading")
        errors.extend(_validate_settings_without_runtime(config.runtime.settings, "evaluation"))
        return errors + panel_errors
    if config.method == "human":
        errors = _validate_settings_without_runtime(
            config.runtime.settings,
            "evaluation",
            allowed_settings=frozenset({"ratings", "ratings_path", "ratings_file", "score_scale"}),
        )
        if config.runtime.executor != "none":
            errors.append("evaluation.executor must be 'none' for human ratings")
        if config.runtime.model is not None:
            errors.append("evaluation.model must be omitted for human ratings")
        ratings_path = config.runtime.settings.get("ratings_path", config.runtime.settings.get("ratings_file"))
        ratings = config.runtime.settings.get("ratings")
        if ratings_path is None and ratings is None:
            errors.append(
                "evaluation.settings.ratings_path or evaluation.settings.ratings is required for human ratings"
            )
        if ratings_path is not None and ratings is not None:
            errors.append("evaluation.settings.ratings_path and evaluation.settings.ratings cannot both be supplied")
        if ratings_path is not None and (not isinstance(ratings_path, str) or not ratings_path.strip()):
            errors.append("evaluation.settings.ratings_path must be a non-empty string")
        if ratings is not None and (
            not isinstance(ratings, list) or any(not isinstance(item, Mapping) for item in ratings)
        ):
            errors.append("evaluation.settings.ratings must be a list of mappings")
        scale = config.runtime.settings.get("score_scale")
        if scale is not None:
            if isinstance(scale, Mapping):
                low, high = scale.get("min"), scale.get("max")
            elif isinstance(scale, list) and len(scale) == 2:
                low, high = scale
            else:
                low, high = None, None
            if (
                isinstance(low, bool)
                or not isinstance(low, (int, float))
                or not math.isfinite(float(low))
                or not isinstance(high, (int, float))
                or isinstance(high, bool)
                or not math.isfinite(float(high))
                or float(high) <= float(low)
            ):
                errors.append("evaluation.settings.score_scale must have finite min and max with max greater than min")
        return errors + panel_errors
    errors = _validate_runtime(
        config.runtime,
        "evaluation",
        extra_settings=frozenset({"pairs"}) if config.method == "pairwise" else frozenset(),
    )
    if config.method == "pairwise":
        pairs = config.runtime.settings.get("pairs")
        if pairs is not None:
            if not isinstance(pairs, list):
                errors.append("evaluation.settings.pairs must be a list of condition-id pairs")
            else:
                for index, pair in enumerate(pairs):
                    if (
                        not isinstance(pair, list)
                        or len(pair) != 2
                        or any(not isinstance(value, str) or not value.strip() for value in pair)
                        or pair[0] == pair[1]
                    ):
                        errors.append(
                            f"evaluation.settings.pairs[{index}] must contain two distinct non-empty condition ids"
                        )
    if config.method not in {"scalar", "pairwise"}:
        errors.append(
            f"evaluation.method={config.method!r} is unsupported; choose scalar, pairwise, mechanical, or human"
        )
    return errors + panel_errors


def _validate_settings_without_runtime(
    settings: Mapping[str, Any], field: str, *, allowed_settings: frozenset[str] = frozenset()
) -> list[str]:
    """Validate persisted settings for a grader that makes no CLI call."""

    errors: list[str] = []
    for key in settings:
        if key not in allowed_settings:
            errors.append(f"{field}.settings.{key} is unsupported for this evaluation method")
        normalized = key.lower().replace("-", "_")
        if any(marker in normalized for marker in _SECRET_KEY_MARKERS):
            errors.append(f"{field}.settings.{key} must not contain credentials")
        if normalized in {"openai_base_url", "anthropic_base_url", "base_url"}:
            errors.append(f"{field}.settings.{key} is unsupported; API endpoint routing is not allowed")
        if normalized in {"sandbox", "sandbox_profile"}:
            errors.append(f"{field}.settings.{key} is unsupported; the harness owns isolation")
    return errors


def validate_config(config: ExperimentConfig) -> list[str]:
    """Return validation errors without probing external CLIs or making model calls."""

    errors: list[str] = []
    if config.benchmark not in {"gdpval", "gsm8k"}:
        errors.append(f"benchmark={config.benchmark!r} is unsupported; choose gdpval or gsm8k")
    if config.tasks.limit < 1:
        errors.append("tasks.limit must be at least 1")
    if config.tasks.ids and len(config.tasks.ids) > config.tasks.limit:
        errors.append("tasks.ids cannot contain more entries than tasks.limit")
    if config.repeats < 1:
        errors.append("repeats must be at least 1")
    if config.creation_repeats < 1:
        errors.append("creation_repeats must be at least 1")
    if config.creation_repeats > 1:
        interventions = [
            condition.intervention for condition in config.conditions if condition.intervention is not None
        ]
        if not interventions or any(intervention.build is None for intervention in interventions):
            errors.append("creation_repeats > 1 requires build configurations for every Skill condition")
    if config.comparison_design not in {"general", "matched_skills"}:
        errors.append("comparison_design must be general or matched_skills")
    if config.comparison_design == "matched_skills":
        if any(condition.application != config.application for condition in config.conditions):
            errors.append("matched_skills requires identical application model and settings for every condition")
        if config.evaluation is not None and config.evaluation.criteria is None:
            errors.append("matched_skills requires explicit versioned grading criteria before automatic evaluation")
    if config.limits.max_tasks < 1:
        errors.append("limits.max_tasks must be at least 1")
    if config.tasks.limit > config.limits.max_tasks:
        errors.append("tasks.limit exceeds limits.max_tasks")
    if config.limits.max_retries < 0:
        errors.append("limits.max_retries cannot be negative")
    if config.limits.concurrency != 1:
        errors.append("limits.concurrency must be 1 in this bounded slice")
    if config.tasks.path is not None and not config.tasks.path.is_file():
        errors.append(f"task source does not exist: {config.tasks.path}")
    errors.extend(_validate_runtime(config.application, "application"))
    if not config.conditions:
        errors.append("at least one condition is required")
    condition_ids = [condition.id for condition in config.conditions]
    if len(set(condition_ids)) != len(condition_ids):
        errors.append("condition ids must be unique")
    for index, condition in enumerate(config.conditions):
        errors.extend(_validate_runtime(condition.application, f"conditions[{index}].application"))
        intervention = condition.intervention
        if intervention is not None and intervention.path is not None and not intervention.path.exists():
            errors.append(f"conditions[{index}].intervention.path does not exist: {intervention.path}")
        if intervention is not None and intervention.build is not None and not intervention.build.is_file():
            errors.append(f"conditions[{index}].intervention.build does not exist: {intervention.build}")
    if config.evaluation is not None and config.evaluation.method == "pairwise":
        if len(config.conditions) < 2:
            errors.append("pairwise evaluation requires at least two conditions")
        pairs = config.evaluation.pairs or config.evaluation.runtime.settings.get("pairs")
        if isinstance(pairs, (list, tuple)):
            known_conditions = {condition.id for condition in config.conditions}
            for index, pair in enumerate(pairs):
                if (
                    isinstance(pair, (list, tuple))
                    and len(pair) == 2
                    and all(isinstance(value, str) for value in pair)
                ):
                    unknown = [value for value in pair if value not in known_conditions]
                    if unknown:
                        errors.append(
                            f"evaluation.settings.pairs[{index}] references unknown condition id(s): "
                            + ", ".join(unknown)
                        )
    if (
        config.benchmark == "gdpval"
        and config.evaluation is not None
        and config.evaluation.method == "mechanical"
        and config.evaluation.criteria is None
    ):
        errors.append("GDPval does not provide a mechanical grader in this slice; use scalar or pairwise evaluation")
    if (
        config.benchmark == "gdpval"
        and config.evaluation is not None
        and config.evaluation.method in {"scalar", "pairwise"}
    ):
        for runtime in [judge.runtime for judge in config.evaluation.judges] or [config.evaluation.runtime]:
            if (
                runtime.executor == "claude-code"
                and not capability_enabled(runtime.settings)
                and runtime.settings.get("tool_mode", "files") != "sandboxed_shell"
            ):
                errors.append("Claude Code GDPval evaluation requires tool_mode: sandboxed_shell to inspect XLSX")
    if config.benchmark == "gdpval":
        runtimes = [config.application, *(condition.application for condition in config.conditions)]
        if any(
            runtime.executor == "claude-code"
            and not capability_enabled(runtime.settings)
            and runtime.settings.get("tool_mode", "files") != "sandboxed_shell"
            for runtime in runtimes
        ):
            errors.append(
                "Claude Code GDPval requires tool_mode: sandboxed_shell; the file-only route cannot inspect XLSX"
            )
    if config.evaluation is not None:
        errors.extend(validate_evaluation_config(config.evaluation))
    return errors


def _redact(value: Any, key: str | None = None) -> Any:
    if key is not None:
        normalized = key.lower().replace("-", "_")
        if any(marker in normalized for marker in _SECRET_KEY_MARKERS):
            return "<redacted>"
    if isinstance(value, Mapping):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def runtime_snapshot(runtime: RuntimeConfig) -> dict[str, Any]:
    return {"executor": runtime.executor, "model": runtime.model, "settings": _redact(runtime.settings)}


def snapshot_mapping(config: ExperimentConfig) -> dict[str, Any]:
    """Return a JSON-safe, redacted resolved configuration snapshot."""

    snapshot = _redact(config.raw)
    assert isinstance(snapshot, dict)

    snapshot["_resolved"] = {
        "config_path": str(config.config_path),
        "task_path": str(config.tasks.path) if config.tasks.path is not None else None,
        "repeats": config.repeats,
        "creation_repeats": config.creation_repeats,
        "comparison_design": config.comparison_design,
        "limits": {
            "max_tasks": config.limits.max_tasks,
            "max_retries": config.limits.max_retries,
            "concurrency": config.limits.concurrency,
        },
        "application": runtime_snapshot(config.application),
        "conditions": [
            {
                "id": condition.id,
                "application": runtime_snapshot(condition.application),
                "intervention": (
                    {
                        "path": str(condition.intervention.path) if condition.intervention.path else None,
                        "build": str(condition.intervention.build) if condition.intervention.build else None,
                        "prompt": condition.intervention.prompt,
                    }
                    if condition.intervention is not None
                    else None
                ),
            }
            for condition in config.conditions
        ],
        "evaluation": (evaluation_snapshot(config.evaluation) if config.evaluation is not None else None),
    }
    return snapshot


def evaluation_snapshot(config: EvaluationConfig) -> dict[str, Any]:
    """Return a JSON-safe, redacted evaluation configuration snapshot."""

    return {
        "method": config.method,
        "executor": config.runtime.executor,
        "model": config.runtime.model,
        "settings": _redact(config.runtime.settings),
        "judges": [{"id": judge.id, **runtime_snapshot(judge.runtime)} for judge in config.judges],
        "criteria": config.criteria,
        "pairs": [list(pair) for pair in config.pairs] if config.pairs is not None else None,
        "office_rendering": config.office_rendering.snapshot() if config.office_rendering is not None else None,
        **(
            {"inspection_protocol": _copy_mapping(config.inspection_protocol)}
            if config.inspection_protocol is not None
            else {}
        ),
    }
