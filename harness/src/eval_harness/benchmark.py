# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Common benchmark adapter dispatch for the local harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence, TypeAlias, cast

from .config import ExperimentConfig
from .errors import ArtifactError, ConfigError
from .gdpval import (
    GDPValTask,
)
from .gdpval import (
    copy_reference_files as copy_gdpval_reference_files,
)
from .gdpval import (
    load_tasks as load_gdpval_tasks,
)
from .gdpval import (
    reference_source_paths as gdpval_reference_source_paths,
)
from .gdpval import (
    render_application_prompt as render_gdpval_application_prompt,
)
from .gdpval import (
    render_scalar_prompt as render_gdpval_scalar_prompt,
)
from .gdpval import (
    select_tasks as select_gdpval_tasks,
)
from .gdpval import task_directory_name as _gdpval_task_directory_name
from .gdpval import (
    task_snapshot as gdpval_task_snapshot,
)
from .gsm8k import (
    GSM8KTask,
    MechanicalGrade,
)
from .gsm8k import (
    copy_reference_files as copy_gsm8k_reference_files,
)
from .gsm8k import (
    grade as grade_gsm8k,
)
from .gsm8k import (
    load_tasks as load_gsm8k_tasks,
)
from .gsm8k import (
    reference_source_paths as gsm8k_reference_source_paths,
)
from .gsm8k import (
    render_application_prompt as render_gsm8k_application_prompt,
)
from .gsm8k import (
    render_scalar_prompt as render_gsm8k_scalar_prompt,
)
from .gsm8k import (
    select_tasks as select_gsm8k_tasks,
)
from .gsm8k import (
    task_from_snapshot as gsm8k_task_from_snapshot,
)
from .gsm8k import (
    task_snapshot as gsm8k_task_snapshot,
)

BenchmarkTask: TypeAlias = GDPValTask | GSM8KTask
task_directory_name = _gdpval_task_directory_name


def load_tasks(config: ExperimentConfig) -> list[BenchmarkTask]:
    """Load rows through the selected benchmark's pure adapter."""

    if config.benchmark == "gdpval":
        return cast(list[BenchmarkTask], load_gdpval_tasks(config))
    if config.benchmark == "gsm8k":
        return cast(list[BenchmarkTask], load_gsm8k_tasks(config))
    raise ConfigError(f"unsupported benchmark adapter: {config.benchmark}")


def select_tasks(tasks: Sequence[BenchmarkTask], config: ExperimentConfig) -> list[BenchmarkTask]:
    """Apply the shared deterministic selection policy."""

    if config.benchmark == "gdpval":
        return cast(
            list[BenchmarkTask],
            select_gdpval_tasks([task for task in tasks if isinstance(task, GDPValTask)], config),
        )
    if config.benchmark == "gsm8k":
        return cast(
            list[BenchmarkTask],
            select_gsm8k_tasks([task for task in tasks if isinstance(task, GSM8KTask)], config),
        )
    raise ConfigError(f"unsupported benchmark adapter: {config.benchmark}")


def reference_source_paths(task: BenchmarkTask) -> list[Path]:
    """Return only local files that must be staged for a participant."""

    if isinstance(task, GDPValTask):
        return gdpval_reference_source_paths(task)
    return gsm8k_reference_source_paths(task)


def copy_reference_files(task: BenchmarkTask, destination: Path) -> list[dict[str, str | int]]:
    """Stage benchmark inputs and return immutable metadata."""

    if isinstance(task, GDPValTask):
        return copy_gdpval_reference_files(task, destination)
    return copy_gsm8k_reference_files(task, destination)


def task_snapshot(task: BenchmarkTask, saved_references: list[dict[str, str | int]]) -> dict[str, Any]:
    """Create a benchmark-tagged snapshot outside agent workspaces."""

    if isinstance(task, GDPValTask):
        return {**gdpval_task_snapshot(task, saved_references), "benchmark": "gdpval"}
    return gsm8k_task_snapshot(task)


def task_from_snapshot(snapshot: Mapping[str, Any], benchmark: str) -> BenchmarkTask:
    """Reconstruct a task without rereading mutable source data."""

    if benchmark == "gdpval":
        raw = snapshot.get("raw")
        if not isinstance(raw, Mapping):
            raise ArtifactError("GDPval task snapshot has no raw row")
        task_id = raw.get("task_id")
        prompt = raw.get("prompt")
        if not isinstance(task_id, str) or not isinstance(prompt, str):
            raise ArtifactError("GDPval task snapshot has invalid task_id or prompt")
        references = raw.get("reference_files")
        urls = raw.get("reference_file_urls")
        source_line = snapshot.get("source_line", 0)
        if not isinstance(source_line, int):
            raise ArtifactError("GDPval task snapshot has an invalid source line")
        rubric_pretty = raw.get("rubric_pretty")
        if not isinstance(rubric_pretty, str):
            rubric_pretty = ""
        return GDPValTask(
            task_id=task_id,
            prompt=prompt,
            rubric_json=raw.get("rubric_json"),
            rubric_pretty=rubric_pretty,
            reference_files=tuple(item for item in references if isinstance(item, str))
            if isinstance(references, list)
            else (),
            reference_file_urls=tuple(item for item in urls if isinstance(item, str))
            if isinstance(urls, list)
            else (),
            raw={str(key): value for key, value in raw.items()},
            source_path=Path(str(snapshot.get("source_path", ""))),
            source_line=source_line,
        )
    if benchmark == "gsm8k":
        return gsm8k_task_from_snapshot(snapshot)
    raise ArtifactError(f"unsupported benchmark in saved run: {benchmark}")


def render_application_prompt(task: BenchmarkTask) -> str:
    """Render a participant prompt through its benchmark adapter."""

    if isinstance(task, GDPValTask):
        return render_gdpval_application_prompt(task)
    return render_gsm8k_application_prompt(task)


def render_scalar_prompt(task: BenchmarkTask) -> str:
    """Render an optional independent scalar judge prompt."""

    if isinstance(task, GDPValTask):
        return render_gdpval_scalar_prompt(task)
    return render_gsm8k_scalar_prompt(task)


def mechanical_grade(task: BenchmarkTask, response: str) -> MechanicalGrade:
    """Run a benchmark-owned mechanical grader where one is available."""

    if isinstance(task, GSM8KTask):
        return grade_gsm8k(task, response)
    raise ConfigError(f"benchmark {type(task).__name__} does not provide mechanical grading")


def supports_mechanical_grading(benchmark: str) -> bool:
    """Whether the selected benchmark supplies a local deterministic grader."""

    return benchmark == "gsm8k"
