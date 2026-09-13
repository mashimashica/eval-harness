<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Eval Harness CLI specification

This document defines the target CLI, not the implementation status.
The [product requirements](requirements.md) remain the development baseline.
Use `eval-harness` as the command name and YAML for experiment configuration.
Single-condition runs and comparative experiments use the same commands.

## Commands

Angle brackets denote values to supply. Examples assume the repository root as the working directory.

| Operation | Syntax | Example |
| --- | --- | --- |
| Preflight | `eval-harness check <experiment.yaml>` | `eval-harness check experiments/nsa.yaml` |
| Create a Skill separately | `eval-harness build <build.yaml> --out <skill-dir>` | `eval-harness build configs/build-a.yaml --out skills/a` |
| Run an experiment | `eval-harness run <experiment.yaml> --out <run-dir>` | `eval-harness run experiments/nsa.yaml --out runs/pilot` |
| Re-evaluate saved artifacts | `eval-harness evaluate <run-dir> --config <evaluation.yaml> --out <evaluation-dir>` | `eval-harness evaluate runs/pilot --config configs/judge.yaml --out evaluations/rejudge` |
| Aggregate and compare results | `eval-harness compare <run-or-evaluation-dir>... --out <report-dir>` | `eval-harness compare runs/pilot evaluations/rejudge --out reports/comparison` |
| Resume interrupted work | `eval-harness resume <run-or-evaluation-dir>` | `eval-harness resume runs/pilot` |

- `check` validates configuration, supported combinations, authentication state, and required inputs.
  It makes no model generation or grading calls. Passing preflight is not evidence of task success.
- `build` creates a reusable Skill using its own CLI, model, settings, and creation inputs.
  Running it separately is optional; `run` can perform the configured creation stage.
- `run` performs optional Skill creation, task execution, artifact capture, evaluation, and aggregation.
  Conditions may use no intervention, an existing Skill, or a Skill created for the experiment.
- `evaluate` applies the selected evaluation to saved artifacts without regenerating them.
  AI scoring and anonymous pairwise judging belong here, not in `compare`.
- `compare` reads saved evaluations and produces a comparison report. It makes no generation or grading calls.
  Preserve evaluation methods, task identities, and sample counts; do not count re-evaluations as new generated samples.
- `resume` continues incomplete work using saved configuration and state. It preserves completed work.
  It does not accept replacement experiment conditions or a new output directory.

## Experiment configuration

Example: `experiments/nsa.yaml`.
Replace model placeholders and supply the referenced creation configurations before execution.

```yaml
benchmark: gdpval
tasks:
  limit: 1
  seed: 42
repeats: 2

application:
  executor: codex
  model: <application-model-id>
  settings: {}

conditions:
  - id: N
    intervention: null
  - id: S
    intervention:
      build: ../configs/build-s.yaml
  - id: A
    intervention:
      build: ../configs/build-a.yaml

evaluation:
  method: pairwise
  executor: claude-code
  model: <judge-model-id>
  settings: {}
```

| Field | Meaning |
| --- | --- |
| `benchmark` | Selects the existing benchmark adapter; `gdpval` is one example. |
| `tasks.limit`, `tasks.seed` | Select a reproducible task subset shared by the conditions. |
| `repeats` | Number of task executions per selected task and condition, not the number of judge votes. |
| `application` | Default executor, model, and settings for task execution. |
| `conditions[].id` | A recording label, not information to disclose to a blind judge. |
| `conditions[].application` | Optional overrides of the application fields. Omitted fields inherit the defaults. A supplied `settings` mapping replaces the default mapping. |
| `conditions[].intervention` | The intervention for this condition; `null` means none. |
| `conditions[].intervention.build` | References a separate Skill creation configuration. |
| `evaluation` | Evaluation method and, when using AI, independently selected executor, model, and settings. |

Executor identifiers are `codex` and `claude-code`, using account/subscription authentication.
The example executes the same task twice in each of N, S, and A: six task executions.
It then uses Claude Code for anonymous pairwise evaluation.
S creates its Skill with skill-creator; A uses skill-creator plus ALPS.
Their creation configurations specify creation inputs and their own CLI, model, and settings.
These labels are examples, not special cases in the implementation.

`configs/judge.yaml` contains the evaluation mapping directly, without an `evaluation` wrapper:

```yaml
method: pairwise
executor: claude-code
model: <judge-model-id>
settings: {}
```

## Shared behavior

Resolve CLI paths from the working directory and YAML file references from the containing YAML file.
Save the resolved configuration and required inputs for resumption; do not silently adopt later source YAML edits.
Require a new output directory for `build`, `run`, `evaluate`, and `compare`; never overwrite an existing result.
Use `resume` for interrupted runs or evaluations. Changed conditions require a new run or evaluation directory.
Report unsupported combinations, missing inputs, and failed prerequisites explicitly.
Do not silently substitute an executor, model, setting, or billing route.
Apply the information-separation, recording, and bounded-execution requirements R08-R10 to these operations.

This specification fixes the command surface and fields shown above, not every configuration schema.
Define creation/reuse settings, pair scheduling, non-pairwise evaluation settings, human-rating entry, and execution-limit
fields with their implementations. Keep them explicit and consistent with R05, R07, R08, and R10.
Those remaining details do not introduce mandatory new top-level commands or require completing unrelated features first.
