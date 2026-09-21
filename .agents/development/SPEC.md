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
use independent Codex or Claude runtimes; The legacy Claude GDPval environment requires `tool_mode: sandboxed_shell`; `gdpval-v1` uses the shared MCP route described below. GSM8K retains its
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

## Shared GDPval capability environment

Select `settings.environment.profile: gdpval-v2` explicitly for each creation, application and AI evaluation runtime.
This opt-in macOS environment uses the same local MCP tools and copied, locked Python dependencies for Codex 0.154.0
and Claude Code 2.1.270. It is a new experimental environment; existing runs keep their original settings and records.
Do not combine it with `tool_mode` or the legacy evaluation-level `office_rendering` option.

```yaml
settings:
  reasoning_effort: medium
  timeout_seconds: 600
  environment:
    profile: gdpval-v2
    network_policy: public_https
    executables:
      ffmpeg: /absolute/path/to/isolated-ffmpeg
      ffprobe: /absolute/path/to/isolated-ffprobe
      node: /absolute/path/to/isolated-node
    office_rendering:
      soffice: /absolute/path/to/soffice
      pdftoppm: /absolute/path/to/pdftoppm
```

Install the extended locked Python bundle with `uv sync --project harness --extra capabilities --group dev --locked`.
The prior `gdpval-v1` profile retains its smaller package set. Native executable paths are optional and explicit;
configure the programs needed by the task before freezing the comparison. Their bytes are copied into the private
runtime and fingerprinted. Do not expose an unaudited downloaded binary as an accepted capability.

`network_policy: public_https` allows anonymous HTTPS GET on port443, including public redirect targets discovered
by participants. Each hop validates all DNS answers, pins the connection address, verifies TLS, and shares bounded
time/bytes/redirect limits. Private, reserved and mixed public/private answers, URL credentials and non-HTTPS requests
are rejected. No ambient cookies, account headers or proxy configuration are used. Shell network access stays denied.
`search` tries fixed public DuckDuckGo HTML/Bing RSS backends; every attempt and available response body is retained,
including a failed attempt before successful fallback. Availability and result relevance are external conditions.

For legacy restricted configurations, omit `network_policy` or set `allowlist`, and supply explicit
`network_domains: [www.bing.com, pypi.org, files.pythonhosted.org]`. Public mode requires this list to be empty or
omitted. Research access does not authorize auxiliary AI, authenticated services, remote deployment, or another
model/billing route. A failed retrieval is not replaced with controller-selected research.

| Capability | Skill creation | Task execution | Evaluation |
| --- | --- | --- | --- |
| `shell`: bounded code, files and local helper tools | Write own workspace; supplied creation inputs read-only | Write own workspace; supplied references and Skill read-only | Read originals; write and execute inspection copies in `scratch/` |
| Python baseline | Same locked openpyxl, python-docx, python-pptx, Pillow, pypdf, XlsxWriter and transitive packages | Same | Same |
| `search`, `fetch` | Frozen public HTTPS or explicit-domain policy | Same; participant performs required research and selection | Same policy when required for evidence |
| Extended v2 libraries | NumPy, SciPy, pandas, Matplotlib, psd-tools, OCP, nbformat, ipywidgets and locked dependencies | Same | Same; installation alone is not capability proof |
| Explicit native commands | Configured FFmpeg/ffprobe/Node bytes | Same | Same; execute inspection copies |
| `install_wheel` | SHA256-pinned wheel into private task packages | Same; installation time is part of execution | Same, for inspection dependencies |
| `inspect_document` | DOCX revisions/comments, XLSX formulas/PivotTable structure, PDF page count, Office member inventory | Same | Same; structural presence alone is not a functional pass |
| `render_pages`, `view_image` | Selected pages or crop, native image content | Same | Same; frozen common PDFs for independent judges |
| Personal settings, other conditions, grading material | Not staged | Not staged | Only anonymous assigned submissions and declared grading material |

The shell permits one foreground process. Prefix external programs with `exec`, such as `exec python -c 'print(1)'`. Use Python for file operations and sequencing, or separate tool calls; the OS denies child processes, pipelines, subprocesses and background jobs. Invoke `exec soffice ...` separately for copied native conversion. This explicit restriction prevents code from detaching beyond its measured execution boundary. Python runs from a copied private runtime. Wheel installation does not run package setup scripts, rejects unsafe archive
paths and `.pth` files, and never writes global packages. Entries and CRCs are validated in staging before publication;
caught write failures roll back newly written files and directories. The downloaded wheel and failure stay recorded.
This is not a power-loss/SIGKILL transaction guarantee. Dependencies requiring system installation or an unsupported
binary platform need an explicitly revised environment. The native LibreOffice/Poppler paths are optional, but required
for rendered inspection. They are hashed with the Python packages, interpreter and harness code. CLI-native shell,
web, plug-ins and autonomous subagents are disabled; file/code operations pass through the shared service. A native
positive/negative sandbox probe must succeed before execution. The supported boundary is macOS Seatbelt; another OS
fails preflight instead of running without isolation.

For JavaScript tests, invoke installed library APIs in one `exec node` process. Native `npm test` runners that spawn
children are outside this shell boundary. Task-local package tarballs can be retrieved with `fetch`, verified by exact
hash, and safely extracted in the workspace; package lifecycle scripts are not a prerequisite. The known-content
acceptance exercised React Testing Library 16.3.0, Sinon 21.1.2, TypeScript 5.8.3 and JSDOM 26.1.0 this way. These are
additional task-local dependencies, not an implicit baseline bundle or proof of native browser/accessibility behavior.

For fresh notebook execution, the verified route creates an actual `ipykernel.inprocess` kernel in one Python process,
executes ordered cells and captures their output/error messages. Install compatible exact-hash wheels as task-local
dependencies; the baseline `nbformat` library alone only handles notebook files. This route does not enable a separate
Jupyter server, socket-based child kernel or native notebook UI. Dependency setup and helper construction remain part
of the participant's measured task time, with the same opportunity in each Skill condition.

Both CLIs receive the seven shared work tools. Codex also retains native MCP resource-discovery helpers; the sole
configured service exposes no resources or resource templates. Claude additionally exposes its output-only
`StructuredOutput` formatter when a judgment schema is requested; it grants no file, code or network access. Explicit
MCP settings, empty personal configuration sources and disabled native Skill/plugin discovery control the tool inventory.
Codex limits `enabled_tools` to that seven-tool list and preauthorizes it with `default_tools_approval_mode: approve`.
The service enforces each call's filesystem, public-network and process limits; the CLI keeps `approval_policy: never`.

### Original files, research and inspection evidence

`reference_files/` contains only task-provided materials. A URL that the task asks the participant to investigate is
research, not a supplied file to prefetch. The participant calls `search`/`fetch` and receives retrieved files in
`research/`. The harness preserves requested/final URLs, redirect history, query, timestamp, response status, byte hash,
raw response and tool outcome separately from supplied materials. The exact selection rationale remains in the model
and tool transcript. Evaluation receives only the selected submission's anonymous research evidence, without its
runtime/condition identity.

Saved outputs remain authoritative and unchanged. For inspection, judges use `scratch/` to expand, render, recalculate
or execute copies. The `.harness_evidence/` directory records the environment receipt, effective prompt, tool calls,
full command output, elapsed time, retrieved bytes, derived files, image hashes and requested page/crop ranges. The
manifest is written outside the participant's permission boundary after execution and verified on re-evaluation.
These files are evidence, not submission deliverables. Existing model usage and nullable cost fields still apply;
helper execution and dependency installation are included in elapsed time. Tool failures remain visible in the ledger.

Independent judges share the same saved PDF bytes per source hash. `render_pages` accepts one to four one-based pages
per call with no initial 20-page attachment limit; later pages and regions can be requested as needed. The record
distinguishes available page count from actually viewed pages. A failed conversion stays `unavailable`; the original
remains inspectable and the affected visual criterion remains unconfirmed. A changed source or derivative is an error,
not an invitation to regenerate cached evidence on resume.

### Content, appearance and function are separate findings

AI evaluation with this profile requires explicit, frozen criterion IDs. Criteria that can be checked in the environment
must cite observed evidence. Native PivotTable parts, formulas, validations and revision/comment XML can be inspected;
recalculation and changed-input behavior require actual checks on copies. A screenshot does not establish refresh,
editable Track Changes, audio quality, video timing, or interactive application behavior. Microsoft Office-specific
behavior and perceptual audio/video judgments need an explicitly assigned human or compatible native evaluation path.
They remain unconfirmed until that path is exercised. V2 provides OCP geometry APIs and optional FFmpeg processing;
the CLI tools still do not give judges auditory perception, temporal playback perception, or native desktop UI control.
Inspecting waveforms, metadata or selected frames cannot establish those perceptual properties. Professional subject
matter alone does not require human grading: source-grounded AI judgments remain available, with expert escalation
when a specific evidence gap requires it.

Native format conversion can reuse saved formula values. A functional check must record changed inputs/selectors and
the resulting dependent values; conversion success alone does not establish recalculation. If needed, invalidate formula
caches and request full recalculation only in the inspection copy, retaining that transformation and its hashes.
Distinguish the AI's reported judgment from the actual inspection trace. A later controller check is separate evidence
and must not be represented as work performed by the original judge.

If any AI scalar criterion is `unconfirmed`, the saved overall score is `null` and `assessment_status` is `unconfirmed`;
the raw judgment and per-item findings are retained. Reports show unconfirmed and failed counts, preserve the planned
sample denominator, and exclude unavailable numbers from arithmetic. They do not turn missing evidence into zero or a
successful assessment. Pairwise `unjudgeable` retains its existing meaning and contributes no win credit.

AI scalar and pairwise evaluators can recover their current task after CLI context compaction from the read-only
`evidence/evaluation-inputs/` directory. It contains the exact prompt and original rubric fields, the AI criteria and
policy already shown to that judge, the current task's inspection rules, the response schema, and the complete evaluator
prompt. It excludes other tasks, raw source/gold metadata and controller-only mechanical expected answers. These files
are instructions and task context, not submission evidence. They are staged only for evaluation and archived with its
workspace. A missing criterion statement requires rereading them; it does not permit guessing from an item ID.

Poppler page rendering uses the configured LibreOffice bundle's fonts and a private Fontconfig cache. The explicit
`bundled-libreoffice-v1` policy, configuration and hash are saved in rendering receipts; ambient user font configuration
and shared caches are not imported. Standard Helvetica/Times/Courier families use the bundled Liberation fallbacks.
Missing bundle fonts fail explicitly. These substitutions can affect appearance: keep the recorded renderer identity
and use a new evaluation identity when comparing revised previews. LibreOffice conversion settings remain separate.

### Freeze the inspection procedure separately from the rubric

`evaluation.criteria` retains the original item IDs and descriptions. Optional
`evaluation.inspection_protocol` points to a separate JSON/YAML document, bound to the canonical SHA256 of those
criteria. It must cover every selected AI item exactly. The protocol declares required evidence methods, any allowed
inference, specific conditions requiring an unconfirmed result, and human handoffs. It cannot replace descriptions or
change original tolerances. These are custom harness procedures; equivalence to official GDPval grading is unconfirmed.
[The official grading guidance](https://evals.openai.com/gdpval/grading) identifies pairwise human expert preferences as
the standard and rubric-based LLM judgments as an estimate. This harness's evidence-bound scalar checks, null handling
and optional human handoffs have not been calibrated to that expert preference procedure; report their results under
the frozen harness protocol, not as an official GDPval score. This correspondence was checked on 2026-09-21.

[The paper's automated-grader appendix](https://arxiv.org/html/2510.04374v1#A1.SS6) reports restrictions on internet,
non-Python execution and sound inspection, and excludes 12 tasks from its automated-grader analysis. Those limitations
are not exclusions from this harness's all-220 assignment. Its published agreement measures compare pairwise preferences;
they do not establish the accuracy of this harness's item scores, evidence validator or newer CLI models.

```yaml
method: scalar
executor: codex
model: gpt-5.6-sol
criteria: tasks/example/criteria.json
inspection_protocol: tasks/example/inspection_protocol.json
settings:
  reasoning_effort: medium
  timeout_seconds: 600
  environment:
    profile: gdpval-v2
    network_policy: public_https
```

Include the explicitly selected native tools and Office rendering paths in the environment when needed. A criterion
rule uses `required_methods` (`content`, `structure`, `visual`, `functional`, `research`, or exclusively `human`),
`acceptable_inference` (null or an explicitly described alternative with its required methods),
`unconfirmed_conditions`, and `human_review`. A filename or occupational keyword is not sufficient to choose a route.
For example, PivotTable presence is structural; changing a week selector and observing resulting values is functional;
scientific accuracy may require a comparison with authoritative sources. Supplied-document comparison can use the
supplied original without an unnecessary external search.

Every reported item distinguishes `observation_kind: direct|inference|unconfirmed`. Its `evidence_refs` identify the
workspace-relative file, byte SHA256, specific location, completed tool `call_id`, and evidence `method`. Tool responses
provide the call IDs and captured output paths. Shell inspections must print a JSON record containing
`schema_version: 1`, `source_artifacts: [{path, sha256}]`, and nonempty `checks: [{action, observation}]`.
Each `action` is a nonempty string. An `observation` may be a nonempty string, list or object, a finite number, or a
boolean. Empty lists/objects are recorded query results (for example, no matching comments or named values); they
must describe the performed action, and do not establish that its query or interpretation was correct. Missing/null
observations, blank strings and nonfinite numbers remain insufficient. Nested blank/null values can describe cells.
Source entries may include `size` or `bytes` only when they match the original file's nonnegative byte size.
Record actual operations and results; functional checks need the relevant changed input and observed output.
Reference `captured_stdout_path` with `stdout_sha256`, or `captured_stderr_path` with `stderr_sha256`, for shell evidence.
These canonical `.harness_evidence/outputs/...` paths are materialized after the session; do not use temporary absolute
paths or construct a stream filename from `call_id`. Include an explicit reference for every required method on each
criterion. Match the original criterion ID to its description; another item's references do not supply missing coverage.
`inspect_document` supplies structure evidence; content readings need an actual captured shell record. A checked absence
can be recorded as `observation: {matches: [], count: 0}` or `observation: []` with the query described in `action`.
The check list itself must remain nonempty. A captured zero-result query is distinct from a missing inspection;
source hashes, successful captured calls, required methods and native/human gates remain mandatory. This revises the
earlier format rule that rejected all top-level empty collections; retain old validation and record any saved-evidence
revalidation separately under the changed validator identity. Do not rewrite old judgments or infer semantic accuracy.
A scratch workbook or a modified copy alone does not bind the inspected original to a recorded check.
A research comparison must bind the inspected submission and source bytes. Newly fetched sources use the persistent
`.harness_evidence/research/<sha256>.bin` path in references and shell source records; the returned `scratch/research/`
path is a reading location during the session. Participant research already staged under `research/` and provided
`reference_files/` keep their original relative paths. A pairwise check must cover both anonymous submissions.

#### Evidence from a derived image or PDF

A shell record may also contain `derived_artifacts`. Each entry has exactly `path`, `sha256`, `source_paths` and
`location` (a nonempty string, not an object or list). For example, a frame extraction record has this shape; replace
both hash placeholders with the actual file SHA256 values and record the operation and result that occurred:

```json
{
  "schema_version": 1,
  "source_artifacts": [{"path": "submission/clip.mp4", "sha256": "ORIGINAL_SHA256"}],
  "checks": [{"action": "Extract the frame at 00:00:01.000", "observation": {"frames_written": 1}}],
  "derived_artifacts": [{
    "path": ".harness_evidence/scratch/frames/frame-0001.png",
    "sha256": "DERIVATIVE_SHA256",
    "source_paths": ["submission/clip.mp4"],
    "location": "timestamp 00:00:01.000"
  }]
}
```

Use the canonical `.harness_evidence/scratch/...` path for each captured derivative. `source_paths` is a nonempty list
of distinct, exact paths from `source_artifacts` in that same successful shell record. Every declared original and
derivative must still exist with the recorded byte hash. Absolute paths, basename aliases, traversal and symlinks are
rejected. Records are bounded to 2 MiB. In a pairwise record, list only the originals used for each derivative: a frame
whose `source_paths` contains only `submission_A/...` cannot establish coverage for `submission_B/...`, even when the
record's source list includes both submissions. Only records declaring the actual viewed source hash are candidates
for that view's lineage check. An unrelated historical scratch file may have been edited later; its obsolete declaration
does not invalidate a different view. Every source/check/derivative guard still applies to a matching record.

After extraction, call `view_image` on the derivative and cite its returned `captured_path`, `rendered_sha256` and
`call_id` with `method: visual` and a specific location. For a derived PDF, use `render_pages` and cite the PDF's canonical
`.harness_evidence/scratch/...` path, returned `source_sha256` and `call_id`. The session's `scratch/...` reading path is
not a persistent reference. The captured rendered image may have different bytes from the extracted file. The controller
matches the view/render receipt's `source_sha256` to the declared derivative hash, verifies the captured shell stream
against its successful journal-bound receipt, and checks original and derivative bytes. Extraction or a declaration
without an actual view does not establish visual inspection. Matching this chain records provenance; it does not prove
transformation truth. A modified copy shows its modified state, not the original's unchanged layout or values.
A shell-written report of what the model saw is a procedure log. Cite the actual `render_pages` or `view_image` call
for a visual-method reference; a shell self-report cannot supply that method. Use `scratch/...` to call the live tool and
the canonical captured path in the final evidence reference. Still-image inspection does not establish unobserved
motion or sound.

After execution, the controller checks these references against captured files, journal and receipts. It retains raw
model claims separately and makes insufficiently supported items unconfirmed. This validates recorded provenance and
activity, not the truth of a judgment, the adequacy of every locator, or whether a chosen perturbation is meaningful.
The procedure still needs criterion-level review. Resume verifies the frozen protocol; changed procedures use a new
evaluation directory rather than altering a completed judgment.


### Item-bound observations

A frozen rule may add `required_observations: {pass: [source_comparison]}` or
`{pass: [input_change]}` (and independently a `fail` list). Requirements apply only to the listed statuses and
criteria. They do not impose searches or dynamic tests on unrelated predicates. Old protocols remain loadable;
new requirements produce a different protocol hash and require separately recorded reevaluation.

A matching successful shell `checks[].observation` must name `kind` and `criterion_ids`, and be referenced on that
item using the corresponding `research` or `functional` method. Each submission needs its own observation.

- `source_comparison`: `submission` and `reference` each contain a source-bound `path`, precise `location`, and
  `observed` text containing actual relevant passages or concrete values. `comparison` states the comparison and
  limitations. The reference comes from supplied `reference_files/` or captured `research/` bytes. Hashes alone
  do not constitute a comparison. Preserve source identity/version and the applicable original conditional branch.
- `input_change`: `artifact_path` names the original submission in `source_artifacts`; `engine`, `operation`,
  `operation_mode` (`direct_cell_write`, `existing_control`, `existing_filter`), and `update_mode` (`automatic`,
  `manual_recalculation`, `manual_refresh`, `not_observed`) describe the actual operation. `before` and `after`
  each have nonempty `inputs` and `outputs` maps from locations to values. Inputs must differ; observed outputs
  may stay unchanged. `expected` maps output locations to independently expected values, and `comparison`
  describes what was observed. Preserve relevant copies/derivatives with the usual evidence procedure.

The validator checks record completeness and source/criterion binding. It cannot certify that the recorded
passages were actually compared correctly, that input changes were meaningful, or that every required output
was examined. Review actual commands and observations for the claim being made. Direct cell writes do not prove
UI input behavior; manual recalculation does not prove automatic updates. Leave unobserved predicates unconfirmed.
Do not add missing formulas, PivotTables, filters, input controls or connections to a submitted artifact during
inspection. The participant owns their design, implementation, dependency selection and self-checks. The harness
provides generic isolated execution means; task-specific solution helpers or repairs are outside this boundary.


### Human responsibility and pending work

The initial draft's 239 human-tagged items are a provisional routing population, not a count of inherently human-only
criteria. The source-bound observation review classifies those original items without changing their descriptions,
conditions, scoring units or signed weights:

| Necessary observation | Route and acceptance condition |
| --- | --- |
| Numeric, structural, text or still-image facts | Mechanical inspection or current AI tools, with an applicable common proof and actual artifact evidence |
| Application opening, editing, updating or control behavior | Functional inspection; an unverified operation remains infrastructure/verification pending, rather than inherently human-only |
| Currently unavailable perception of sound or motion | A provisional human observes the specified intervals and qualities; metadata and stills do not substitute for this observation |
| Ambiguous original predicate or insufficient evidence | Unconfirmed with its reason and affected task/item IDs |

Mixed items list their component observations but keep one original criterion and weight. A provisional human may
integrate recorded machine checks with the remaining perceptual observation; this does not make numeric components
human-only. Specialist or qualitative judgment alone does not require a human route.

An optional nonempty per-item `pending_reason` freezes an unresolved inspection prerequisite. A plausible result or
valid references alone cannot clear this gate. The only machine exception is an explicitly predeclared
`machine_alternative` for a sufficient branch of the unchanged original OR criterion:

```yaml
machine_alternative:
  condition: "Exact sufficient branch from the original OR criterion"
  required_methods: [visual]
```

The field has exactly `condition` and `required_methods`; the methods must be nonhuman. Confirm from the original
criterion that the stated branch is sufficient before freezing the protocol. The model must report `status: pass`,
`observation_kind: direct`, a reason naming the observed branch, and nonempty `evidence_refs` that validate all required
methods and submission scopes. Permitted inference alone cannot establish this exception. The controller records
`inspection_branch: machine_alternative`; it checks evidence provenance, not the semantic truth of the branch claim.
A failed, unobserved or insufficiently supported branch remains unconfirmed: it cannot fail the full OR criterion while
another branch is unobserved. A separately supplied human receipt takes precedence for the full original criterion;
an invalid or incomplete human receipt does not fall back to the machine alternative.

Without that supported predeclared alternative, resolve the prerequisite and freeze a new protocol to remove the gate;
unrelated items can proceed. Keep one original criterion, scoring unit and signed weight across its branches. This
does not change the existing null aggregate rule or reinterpret earlier v1 protocols and judgments.

For this development acceptance, the requester is the human-review coordination owner. Actual reviewers must be named
before the comparison experiment. A pending rule may specify
`human_review: {coordination_owner: user, reviewer: null, procedure: ...}`. AI checks can proceed; without a supported
predeclared machine alternative, those human items remain unconfirmed. The generated `human_handoffs.json` binds
task/item IDs, original criterion, artifact and protocol
hashes, procedure and responsibility. A pending handoff is not an evaluation result.

Before actual human review, the coordination owner names a reviewer and freezes a new protocol identity. The reviewer
receives the unchanged criterion, anonymous original artifacts, necessary references and isolated inspection copies.
They perform the stated native interaction, listening, playback or other unavailable observation, recording the
application/version, inspected pages/times/actions, observed results, evidence, an explicit pass/fail/unconfirmed
decision and a timezone-qualified completion time. The owner verifies reviewer identity and preserves the receipt
beside the handoff; hashes alone do not authenticate a person.

The controller API `human_handoff`, `validate_human_receipt` and `apply_inspection_protocol(human_receipts=...)` supports
hash-bound item receipts and rejects completion while a reviewer is unassigned. AI output cannot supply these receipts.
There is no automatic CLI merge of human item decisions into an AI aggregate. The existing `method: human` inbox remains
the path for separately recorded overall human ratings; do not overwrite AI results or label an unperformed review as
complete. Report the AI and human scopes separately until an explicit combined scoring procedure is frozen.

### Reproduce the full-task preparation and correspondence

The development helpers consume the pinned original public dataset, never gold deliverables or research substituted
for participant work:

```sh
uv run --project harness --no-sync python .agents/development/scripts/gdpval_startup_check.py \
  --source /path/to/public-tasks.jsonl --source-sha256 SOURCE_SHA256 \
  --revision DATASET_COMMIT --output .audit/all-task-inputs --fetch \
  --download-timeout 900 --max-download-mib 2048
uv run --project harness --no-sync python .agents/development/scripts/gdpval_inspection_plan.py \
  --source /path/to/public-tasks.jsonl --source-sha256 SOURCE_SHA256 \
  --review .agents/development/evidence/gdpval-220-requirements-review.json \
  --routing-review .agents/development/evidence/gdpval-239-observation-routes.json \
  --code-routing-review .agents/development/evidence/gdpval-143-code-routes.json \
  --out .audit/all-task-inspection-v2 --human-coordination-owner user
```

The startup helper verifies all 220 original prompts and 261 provided files, their staged byte hashes, and absence of
rubrics/gold in participant inputs. It binds the exact provided-path set to metadata from the pinned dataset revision,
checks remote size and LFS SHA256 or Git blob SHA1, and requires the same identity check for cached files. Partial or
mismatched downloads cannot become completed inputs. Existing receipts remain unchanged; failed attempts and received
partial bodies are retained. Downloads have explicit byte/time limits; preserve failed reports and use a new
`--report-name` for a further attempt. Without `--fetch`, missing metadata or inputs stop preparation.

Successful identity checks establish faithful acquisition, not semantic validity. A malformed file that matches the
pinned source remains a source-input issue; do not silently repair the original or count affected criteria as failed.
Record the precise readable portion, affected task/item IDs and any unresolved interpretation separately. Use the
recorded local input paths as `tasks.reference_file_overrides` in experiment configurations.

The inspection helper writes per-task `criteria.json`, `source_scores.json`, `candidate_plan.json` and, where assignment
policy permits, `inspection_protocol.json`, plus a manifest. All 10,453 original criteria are represented; 94 negative
source weights remain signed in the sidecar. No automatic official weighted score is claimed. Generated procedures are
drafts: confirm applicability for each item before adopting them. All 220 remain included; unresolved content conflicts,
missing empirical checks and pending human assignments are visible independently in the readiness ledger.

`--routing-review` requires exact coverage of the original provisional-human population and verifies source, review,
row and original-item hashes, descriptions and signed weights before writing anything. It writes a new v2 inspection
identity, component evidence requirements and pending-route IDs. Without either route-review option, the helper
reproduces the legacy conservative v1 draft; its broad modality tags must not be reported as established human-only requirements.

The optional `--code-routing-review` separately covers exactly 143 original criteria in the three reviewed code tasks.
It verifies the source, row, prompt, item, description and signed score identities before applying only their reviewed
methods. Behavioral requirements retain `functional` evidence; source, query and documentation requirements use
`content` or `structure`. The two review populations must not overlap. Its file hash is recorded in the protocol version,
provenance and manifest. Route selection preserves original branches and weights and does not establish artifact success.
Existing generated directories, trial protocols, outputs and judgments are retained. Procedure-only corrections use
saved originals in a new evaluation identity; no generation rerun is implied.

Source hashes, component-specific proof, failed attempts and current limitations are recorded in
`.agents/development/evidence/gdpval-220-capabilities.json`. The readiness ledger connects that evidence to the original
task/item IDs. Registration, an installed library or a successful participant answer alone is not acceptance proof.

Common-route requirements must follow each original deliverable and criterion. A paper form with handwriting space
does not imply electronic form fields; a supplied form does not imply external acquisition; a PDF containing PNGs
does not imply an editable Word document. A notebook's screen-interaction prerequisite applies to its actual UI
criterion, not to independent calculations, random seeds or CSV output. Source-bound correction supplements retain
the initial review and identify changed task/item mappings. Optional strengthening, such as executing an Overpass
query when the deliverable is query text and instructions, is recorded separately and cannot create a required-route
gap. Removing an inapplicable prerequisite is a classification correction, not new execution evidence or an artifact
pass. Actual common-operation verification is recorded separately, with its applicable environment and limitations.


### Applying an environment change to existing experiments

Freeze task IDs, provided-file hashes, criteria, model/billing route, network domains, dependency/tool versions, time,
concurrency and retry limits before the first session. Keep N/S/A environments equal except for the intended Skill
intervention. The saved environment fingerprint rejects resume after capability code, dependency or native tool changes.
Create a new run for application changes; create a new evaluation identity for changed inspection/criteria when existing
saved submissions and research evidence suffice. Missing participant research cannot be repaired retrospectively by
controller research. Keep the old runs and report the changed protocol separately. Generic capability acceptance is not
proof that a participant solves a task, or that all pages and functional criteria of another task have been inspected.

The development readiness ledger covers all 220 frozen tasks with eight sections per task: identity, primary route,
required capabilities, task-specific checks, Codex/Claude support, assessment methods and inspected scope, evidence,
and inclusion in this acceptance. Current summaries keep content readiness, environment acceptance and acceptance
inclusion independent. A planned method is not an executed check; an unreviewed file, URL or criterion stays unconfirmed.
The earlier content partition is retained in a separate dated historical evidence file and does not constrain current
classifications. All 220 tasks remain in scope. The two owner-selected tasks start real-CLI verification in their
original order; they do not limit coverage. Current content feasibility is recorded independently as `candidate`,
`needs_clarification`, or `undetermined`, with reasons and assumptions. Input reading, output authoring and evaluation
are separate requirements. Creating an artifact or registering a route does not establish functional acceptance.
Where a verified retrieval tool can obtain public materials, exact requested-source availability and version can still
remain unconfirmed. The ledger preserves these separately under
`task_specific_checks.external_data.source_input_obligations`, with the original source/year constraints and affected
criterion IDs. A shared retrieval route does not assert that a particular document was obtained. The participant
performs the required search, acquisition and selection; the harness does not preselect replacements.
