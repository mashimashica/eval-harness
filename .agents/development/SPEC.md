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
| Aggregate and compare results | `eval-harness compare <run-or-evaluation-dir>... --out <report-dir> [--seed N] [--resamples N]` | `eval-harness compare runs/pilot evaluations/rejudge --out reports/comparison` |
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

## Current lightweight implementation

The project-local implementation lives under the harness/ directory and uses
the repository's locked uv environment. The first runnable adapters are
gdpval and the retained prepared gsm8k JSONL format. GSM8K uses its
benchmark-owned exact answer grader with method: mechanical; that grader runs
without a judge CLI and keeps the prepared answer outside the participant
workspace. GDPval spreadsheet work uses Codex or the Claude `sandboxed_shell`
route with an isolated Python/openpyxl toolchain. The legacy Claude `files` route
remains available for text tasks and Skills. `sandboxed_shell` is supported on
macOS with the verified native sandbox; unsupported platforms fail preflight.

The build command requires an independently configured executor, model,
creation prompt, optional input paths, and optional creator Skill paths. It
invokes the selected CLI and saves the generated SKILL.md plus creation
evidence. A condition may reuse a Skill with intervention: path or create one
inline with intervention: {build: path}. The run command stages the resulting
Skill into the application workspace, then runs the configured evaluation and
comparison under evaluations/ and comparison/ when an evaluation is present.

The supported model values in this slice are gpt-5.6-luna, gpt-5.6-sol,
gpt-5.6-terra, gpt-6-astra for Codex. Claude supports the exact IDs below; aliases
are rejected and the native account/model/effort preflight must also succeed.
Preflight applies the native effort catalog below and rejects an unsupported
model/effort pair before making a generation call:

| Model | Supported reasoning efforts |
| --- | --- |
| `gpt-5.6-luna` | `low`, `medium`, `high`, `xhigh`, `max` |
| `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-6-astra` | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` |
| `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5` | `low`, `medium`, `high`, `xhigh`, `max` |
| `claude-haiku-4-5-20251001` | Omit `reasoning_effort`; no configurable effort |
| `claude-sonnet-4-6` | `low`, `medium`, `high`, `max` (existing configurations) |

Pairwise evaluation writes one row per presentation with
`generation_ids`, `condition_ids`, anonymous `presented_conditions`, a strict
`winner` (`A`, `B`, `tie`, or `unjudgeable`), and `winner_condition_id`. Human evaluation
imports JSONL rows with a `generation_id` (or condition/task/repeat),
`rater_id`, criterion `ratings`, optional `comment`, and `is_test_data`.
Scores remain null unless a declared `score_scale` permits normalization.

The lightweight schema makes the execution bounds explicit. `tasks.path` points to a JSONL source (or `tasks.rows`
contains inline rows); `tasks.ids` is an optional exact subset, and `tasks.limit` and `tasks.seed` bound deterministic
selection. `tasks.reference_file_overrides` may replace a GDPval row's local reference files. `limits.max_tasks`,
`limits.max_retries`, and `limits.concurrency` bound the run; this slice requires concurrency `1`. Every model-backed
runtime records an explicit executor and model. Application, Skill-creation, scalar, and pairwise runtime settings are
limited to finite positive `timeout_seconds`, model-supported `reasoning_effort`, optional `auth_source_home`, and an
empty `toolchain_read_paths` list; Claude Code additionally accepts a positive integer `max_turns` and `tool_mode: files|sandboxed_shell` (default `files`). The harness owns
the native sandbox, so user supplied sandbox or non-empty toolchain path overrides are rejected. Mechanical and human
evaluation use `executor: none`, `model: null`, and their method-specific settings only. Preflight checks all selected
inputs, Skill documents, creator runtimes, evaluator authentication, and human rating source syntax before the first
participant generation.

The build mapping contains `name`, `executor`, `model`, `settings`, `prompt`, `inputs`, and `skills`. `name` is a
lowercase hyphenated Skill name and the output directory must use that name. Each `skills` entry names a selected Skill
directory; its `SKILL.md` body is delivered explicitly to the creator while its supporting files are staged. Creation
inputs and selected Skills are copied into a hidden frozen snapshot before the creator is called. A condition
intervention accepts one of `path` or `build`, and may also include the independent non-empty `prompt`; unknown
intervention fields are rejected.

The implemented evaluation methods are `scalar`, `pairwise`, `mechanical`, and `human`. Scalar and pairwise AI judging
use independent Codex or Claude runtimes; Claude GDPval requires `tool_mode: sandboxed_shell`. GSM8K retains its
benchmark-owned mechanical grader. GDPval mechanical evaluation requires explicit criteria and uses `executor: none`
with no model. Pairwise plans with fewer than two conditions are rejected before application execution. Legacy `settings.pairs` optionally
names the condition pairs to judge; each selected pair is presented in both orders for every task and repeat. Human
ratings use `executor: none`, `model: null`, and either inline `settings.ratings` or `settings.ratings_path` (the
`ratings_file` alias is also accepted), with optional `score_scale`; every criterion and explicit score must lie within
that declared scale. Human ratings are appended through `inputs/human_ratings.inbox.jsonl` on resume; consumed snapshots
and changed completed ratings are retained as immutable evidence. The mechanical grader records `task_success: true`
for a valid score of `1`, `false` for a valid score of `0`, and `null` for an invalid grade; AI and human methods leave
task success unknown unless a separate success rule is declared.

## Matched Skill comparisons and two kinds of repetition

`comparison_design` defaults to `general` to preserve experiments that intentionally compare application settings.
Use `matched_skills` for an N/S/A method comparison: every condition must use exactly the same application executor,
model and settings; every S/A creator must use exactly the same executor, model and settings. Only the selected creator
Skills differ. Existing Skills require their completed `skill_manifest.json` provenance. Additional intervention
prompts are rejected in this design. The generic creation brief and non-grading input fingerprints must also match; altered recorded Skill content is rejected.

`repeats` is the number of executions using a fixed Skill. `creation_repeats` defaults to 1; values greater than 1 require
build configurations for all Skill conditions and create independent cohorts. All cohorts' input snapshots are frozen
before the first creation. Each cohort has ordinary task/condition/repeat journals under `cohorts/creation_<index>`.
`creation_repeat`, `cohort_parent_id`, Skill `creation_id` and content hash distinguish creation variation from execution
variation. These are recording fields, never participant instructions. Run, evaluate, compare and resume accept the cohort container; check previews its counts, and build creates one Skill. Human ratings are entered separately for each child run so a condition/task/repeat tuple cannot accidentally rate multiple creations.
Resumption does not adopt later source edits or repeat completed creation, execution or grading.

## Independent judge panels

A scalar or pairwise evaluation may specify `judges` instead of the top-level runtime. Each member has a unique `id`
and its own executor/model/settings. The first member is the saved primary runtime for compatibility; a supplied
top-level runtime must match it. Panel runtime settings belong on each judge. Pair selection is `evaluation.pairs`;
omitting it schedules every unordered pair in both orders. A judge cannot see condition IDs, another judge's verdict,
creator metadata or any other task. Each presentation gets a fresh read-only workspace containing the two saved
submissions, current task references and current task's fixed grading information.

```yaml
method: pairwise
criteria: criteria.yaml
pairs: [[N, S], [N, A], [S, A]]
judges:
  - id: sol
    executor: codex
    model: gpt-5.6-sol
    settings: {reasoning_effort: medium, timeout_seconds: 600}
  - id: opus
    executor: claude-code
    model: claude-opus-5
    settings: {reasoning_effort: medium, timeout_seconds: 600, max_turns: 16, tool_mode: sandboxed_shell}
```

A tie means comparable submissions of equal quality. `unjudgeable` means insufficient evidence for a comparison; it is
not a half win, a model failure or an invalid JSON response. Preserve order conflicts, judge disagreements, their
reasons and the number of mutually usable comparisons. Report results per judge and criterion protocol.

## Frozen grading criteria

`evaluation.criteria` accepts a YAML/JSON path or the same mapping inline. Resolve it before any configured grading
call and preserve a canonical SHA256 plus full snapshot. Matched runs with automatic evaluation require explicit
criteria. Separate re-evaluations may select another declared version, but different versions are distinct protocols
and must not be pooled. Resume rejects changes to the frozen policy. Criteria are never supplied to creators or
application agents. A policy requires all fields below, and each task requires `mechanical` and `ai` lists with unique
item IDs; `*` declares common rules. Every selected task must have at least one item.

```yaml
version: audit-v1
benchmark: gdpval
policy:
  arithmetic: decimal
  rounding: half_up
  decimal_places: 2
  absolute_tolerance: 0.01
  relative_tolerance: 0
  missing: unconfirmed
  units: Numeric amounts use the units in the task; percentages are decimal fractions.
tasks:
  '*':
    mechanical:
      - {id: workbook, description: Required workbook, kind: file_exists, path: Sample.xlsx}
    ai:
      - {id: quality, description: Check completeness and clarity against this task and rubric.}
```

Supported mechanical kinds are `file_exists`, `text_contains` (`expected`), `json_number` (`key`, `expected`),
`sheet_exists` (`sheet`), `xlsx_cell` (`sheet`, `cell`, `expected`), and `xlsx_sum` (`sheet`, bounded `range`, `expected`).
Every rule has `id`, `description`, `kind`, and a submission-relative `path` selector. A value rule must select exactly
one file. Spreadsheet value/sum rules may pair `unit` with `unit_cell` for a literal unit check. No code, macros or
formulas are executed. Missing cached formula values use the declared `missing: fail|unconfirmed` policy.
Numeric checks use Decimal; rounding is `none|half_even|half_up|ceiling|floor`, decimal_places 0–12, and error tolerance
is max(absolute_tolerance, abs(expected)*relative_tolerance), with finite nonnegative tolerances.
AI items have only `id` and `description`. Save each item's pass/fail/unconfirmed status, evidence and reason separately
from machine findings. Missing or ambiguous evidence cannot silently pass. Native Codex/Claude structured-output
schemas constrain evaluator responses; missing or invalid output is a failed judgment with its raw attempt retained.

## Paired win rates and uncertainty

`compare --seed 0 --resamples 1000` records the seed, positive resample count, task aggregation unit and percentile 95%
bootstrap method. A win earns 1, a loss 0, and a tie 0.5, explicitly displayed. Both orders are matched to the same
generation pair; duplicate re-evaluations do not create new generations or tasks. Order disagreements and unjudgeable
comparisons are retained and excluded with reasons. Judge-specific rates and agreement remain visible.
Average usable paired execution results within each task, then weight tasks equally. Resample whole task clusters with
replacement, preserving all matched conditions/repetitions in each cluster. Fewer than two usable tasks, no usable
pairs or identical task scores produce null confidence bounds and an explicit reason. Small smoke trials do not
establish efficiency or Skill-method superiority.

Creation, application and evaluation retain separate elapsed time, token usage and cost availability. Reusing a Skill
keeps its creation identity/provenance but is not a new creation. Claude `reported_cost_usd` is the native CLI's
token-price estimate; `cost_usd` remains null when actual incremental subscription cost is unavailable. Never replace
missing cost with zero. Evaluation stage metrics distinguish the latest judgment from `all_attempts`, which includes
archived failed calls without adding generations or votes. Exact Claude account/effort checks make no generation calls and require active subscription
authentication and extra usage disabled. Automatic fallback, paid routes and ambient customizations are disabled.
