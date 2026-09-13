<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR06 GDPval bounded implementation task

> Handoff status (2026-09-13): API and semantic decisions are frozen. Luna must not start until `PR05_ACCEPTED_HEAD` below is replaced with the accepted immutable dependency head.

This is the required plan section 5.2 handoff from Sol to Luna. It is subordinate to `contracts/pr06-gdpval-evaluator-design-contract.md` and `contracts/pr06-gdpval-characterization-fixtures.md`; those two files define the accepted semantics and fixture oracles. This task does not authorize a different evaluator meaning, an external handoff, or a real-model run.

## Objective and starting point

Implement `gdpval.rubric.binary@2`, `gdpval.rubric.structured@2`, and `gdpval.pairwise@2` through the common evaluation runner. The implementation must consume one verified `BoundEvaluationView`, one or exactly two verified `CandidateBundle` values, a fully resolved judge plan, the shared judge runtime, and the shared durable record sink. It must return a normal `EvaluationResult` with the statuses and metric eligibility in the design contract.

The characterized source is `d5ce0c10162cad788a17cb90f34b8f60574e7f75`. The design checkpoint is `5a35d85d0c6af63fd95c672fda2584d26be4ba70`. Implementation starts only after the coordinator substitutes and records the exact accepted PR01--PR05 stack head below:

| Dependency | Required handoff value |
|---|---|
| Implementation base commit | `PR05_ACCEPTED_HEAD` -- must be replaced with one immutable commit before Luna starts |
| Candidate input | `eval_harness.candidate_bundle.BoundEvaluationView` and `CandidateBundle` from the accepted PR02 stack |
| Common job/request/result | `eval_harness.evaluation_runner.EvaluationJob`, `EvaluationPlanRequest`, `EvaluationJobRequest`, `EvaluationFailure`, and `EvaluationRecordSink`; `eval_harness.evaluators.base.EvaluationResult` plus its accepted terminal invariants |
| Judge runtime | `eval_harness.judge_runtime.BlindJudgePolicy`, `JudgeRuntimePreflightRequest`, `JudgeRuntimePreflightResult`, `JudgeInvocationRequest`, `JudgeInvocationResult`, and abstract `JudgeRuntime` |
| Durable sink calls | `EvaluationRecordSink.save_plan`, `.append_attempt_started`, `.append_attempt_terminal`, `.append_result`, and `.load_job` |

`PR05_ACCEPTED_HEAD` is the only permitted unresolved token and is a hard blocker until the coordinator replaces it with the accepted immutable dependency head. It is not permission to create a PR06-private runner, sink, request envelope, compatibility alias, or metadata dictionary convention. If the accepted dependency lacks a required field, return the exact delta to Sol and the PR05 owner before editing production.

## Exact write allowlist

Only these production paths may change. `A` means add and `M` means modify.

| Action | Path | Bounded purpose |
|---|---|---|
| A | `eval_harness/gdpval/__init__.py` | Export only the public PR06 types and entrypoints listed below |
| A | `eval_harness/gdpval/scoring.py` | Versioned prompt loading, rubric definition validation, strict binary/structured/pairwise response parsing, and pure eligible-trial folds |
| A | `eval_harness/gdpval/presentation.py` | Immutable anonymous projection, content blocks/filesystem materialization, Office/archive handling, and presentation/input manifests |
| A | `eval_harness/gdpval/panel.py` | Typed member/panel specs, capability filtering, deterministic weighted selection, position policy, and fully resolved trial plans |
| A | `eval_harness/gdpval/records.py` | Domain-separated identities, BattleRecord/result/attempt-history types, canonical serialization, integrity validation, and pure pairwise fold |
| A | `eval_harness/gdpval/prompts/gdpval_binary_rubric_v2.j2` | Licensed storage header plus exact versioned binary rubric payload extracted from the reviewed NVIDIA source |
| A | `eval_harness/gdpval/prompts/gdpval_structured_rubric_v2.txt` | Licensed storage header plus exact versioned structured rubric instruction payload |
| A | `eval_harness/gdpval/prompts/gdpval_pairwise_v2.j2` | Licensed storage header plus strict blind-pairwise payload with the characterized rendering |
| M | `eval_harness/evaluators/gdpval.py` | Replace external handoff completion with the two concrete common-runner evaluator classes; no path discovery or vendor calls |
| M | `eval_harness/evaluators/registry.py` | Register the three explicit evaluator IDs/revisions and the GDPval benchmark default without constructing a judge as a lookup side effect |
| M | `eval_harness/evaluators/__init__.py` | Export `GDPvalRubricEvaluator` and `GDPvalPairwiseEvaluator` |

Only these test/work-record paths may change:

| Action | Path | Bounded purpose |
|---|---|---|
| M | `tests/harness/test_gdpval_evaluator.py` | Replace external-handoff expectations with common-runner fake-runtime integration cases |
| M | `tests/harness/test_evaluator_registry.py` | Pin explicit GDPval evaluator descriptors/default and prove registry lookup has no judge call |
| A | `tests/harness/test_gdpval_scoring_v2.py` | Parser, prompt, scoring, invalid-response, and completion-policy oracles |
| A | `tests/harness/test_gdpval_presentation_v2.py` | Anonymous projection, byte preservation, Office/archive/media, collision, and digest oracles |
| A | `tests/harness/test_gdpval_panel_v2.py` | Panel RNG, capability, explicit member/position, and resolved-plan oracles |
| A | `tests/harness/test_gdpval_records_v2.py` | Identity, schema, semantic/evidence split, status, reuse, and fold oracles |
| A | `tests/harness/test_gdpval_judge_runtime_v2.py` | Port and strengthen every current local-judge isolation protection through the shared runtime |
| A | `contracts/pr06-gdpval-implementation-work-record.md` | Required checkpoint record with base/dependencies, changed paths, validation, unresolved items, and promotion status |

Everything else is read-only, including `resources_servers/gdpval/**`, `responses_api_agents/stirrup_agent/file_reader.py`, `eval_harness/local_judge_runner.py`, existing judge/vendor adapters, PR05 runner/sink modules, `pyproject.toml`, `uv.lock`, workflows, coverage configuration, and migration control files. A dependency import-path substitution may change an import line within the allowlist; it does not expand the allowlist. Any needed production or test path outside these tables returns to Sol for an amended task before editing.

## Hash and identity rules

All semantic JSON digests call the existing public `eval_harness.provenance.canonical_json_sha256`: UTF-8 JSON, `ensure_ascii=False`, sorted keys, compact separators, and non-finite numbers rejected. Runtime paths, times, raw response/reasoning, credentials, and attempt history never enter semantic identities.

The accepted PR05 boundary is exact; PR06 imports it without aliases:

```python
@dataclass(frozen=True, slots=True)
class LogicalCandidateReference:
    candidate_id: str
    bundle_sha256: str

@dataclass(frozen=True, slots=True)
class EvaluationJob:
    match_occurrence_id: str
    snapshot_reference: SnapshotReference
    evaluation_view_sha256: str
    logical_candidates: tuple[LogicalCandidateReference, ...]
    evaluator_id: str
    evaluator_revision: str | None
    evaluator_config_sha256: str
    evaluator_plan: Mapping[str, JSONValue]
    evaluator_plan_sha256: str
    evaluation_input_sha256: str
    evaluation_job_id: str

@dataclass(frozen=True, slots=True)
class EvaluationPlanRequest:
    view: BoundEvaluationView
    candidates: tuple[CandidateBundle, ...]
    match_occurrence_id: str

@dataclass(frozen=True, slots=True)
class EvaluationJobRequest:
    job: EvaluationJob
    view: BoundEvaluationView
    candidates: tuple[CandidateBundle, ...]
    result_root: Path
    record_sink: EvaluationRecordSink
    judge_runtime: JudgeRuntime | None

@dataclass(frozen=True, slots=True)
class EvaluationFailure:
    failure: Failure
    retryable: bool

@dataclass(frozen=True, slots=True)
class JudgeRuntimeMember:
    member_id: str
    runtime_profile_id: str
    model: str
    reasoning_effort_requested: ReasoningEffortOption
    timeout_seconds: float

@dataclass(frozen=True, slots=True)
class JudgeContentBlock:
    block_id: str
    media_type: str
    logical_path: str
    size: int
    sha256: str

@dataclass(frozen=True, slots=True)
class JudgeInvocationRequest:
    trial_id: str
    member: JudgeRuntimeMember
    prompt: str
    content_blocks: tuple[JudgeContentBlock, ...]
    anonymous_workspace: Path
    required_capabilities: tuple[str, ...]
    policy: BlindJudgePolicy
    protected_roots: tuple[Path, ...]

class EvaluationStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    INVALID = "invalid"
    SKIPPED = "skipped"

@dataclass(frozen=True)
class EvaluationResult:
    evaluation_job_id: str
    task_id: str
    status: EvaluationStatus
    failure: EvaluationFailure | None = None
    metrics: Mapping[str, float] = field(default_factory=dict)
    outcomes: Mapping[str, JSONValue] = field(default_factory=dict)
    details: Mapping[str, JSONValue] = field(default_factory=dict)

def build_evaluation_job(
    *,
    match_occurrence_id: str,
    view: BoundEvaluationView,
    candidates: tuple[CandidateBundle, ...],
    evaluator_id: str,
    evaluator_revision: str | None,
    evaluator_config_sha256: str,
    evaluator_plan: Mapping[str, JSONValue],
) -> EvaluationJob: ...

def plan_evaluation_job(
    evaluator: Evaluator,
    *,
    match_occurrence_id: str,
    view: BoundEvaluationView,
    candidates: tuple[CandidateBundle, ...],
) -> EvaluationJob: ...

class JudgeRuntime(ABC):
    def preflight(self, request: JudgeRuntimePreflightRequest) -> JudgeRuntimePreflightResult: ...
    def invoke(self, request: JudgeInvocationRequest) -> JudgeInvocationResult: ...
```

`JSONValue` is PR05's recursive strict JSON type. `ReasoningEffortOption`, `JudgeRuntimeMember`, `JudgeContentBlock`, and every invocation-request field shown above are also PR05-owned. Auth/environment values belong to operational configuration inside the injected runtime profile; they never enter the request or a semantic record. The shown `EvaluationResult` field order and six status literals are PR05-owned. PR06 constructs it by keyword, echoes `request.job.evaluation_job_id`, and emits only `completed`, `partial`, `failed`, or `interrupted`; the common runner owns any `invalid` or `skipped` job-boundary result. The staged legacy `external` status is not accepted by the common planner, runner, sink, or aggregate. `plan_evaluation_job` validates the evaluator's cardinality and configuration identity, calls `evaluator.plan(EvaluationPlanRequest(...))` for one opaque mapping, and passes that mapping to the sole identity constructor `build_evaluation_job`. That constructor strictly verifies one or two same-task/snapshot bundles against the bound view and computes the plan, input, and job hashes. PR06 must not implement another evaluation-input or evaluation-job hash builder. Its evaluator plan contains its fully resolved trial/member/slot/presentation plan; PR05 stores and hashes that mapping opaquely. Reusing an `evaluation_job_id` with a different `evaluator_plan_sha256` is a hard conflict.

The runtime request binds `trial_id`, the exact selected `JudgeRuntimeMember`, anonymous prompt/workspace, required capabilities, `BlindJudgePolicy`, and protected roots. The result carries bounded raw bytes/text, exit/times/runtime-version/auth/policy/probe evidence and digests, plus a typed failure. Its terminal enum is exactly `completed`, `failed`, or `interrupted`; parser rejection is a PR06 `invalid_response`, never a runtime tie or runtime failure rewrite. PR05 adds `FailureKind.INVALID_RESPONSE = "invalid_response"`; it is permitted with `FailureImpact.TASK` and is not a forced-run failure. Runtime/envelope `PROTOCOL` remains run-impact. Attempt-terminal records and `EvaluationResult.failure` use `EvaluationFailure | None`.

PR06 calls only `EvaluationRecordSink.save_plan`, `.append_attempt_started`, `.append_attempt_terminal`, `.append_result`, and `.load_job`. `save_plan` is atomic/content-addressed and precedes all calls. Append methods flush and fsync. Creating a job refuses occupied output; resume requires exact plan/input/evidence revalidation. Semantic results and attempt/evidence history remain separate. These storage and invocation mechanics remain PR05-owned.

`records.py` adds only the PR06 trial identity builder:

```python
def build_battle_record_id(*, evaluation_job_id: str, trial_index: int) -> str: ...
```

Candidate order is the logical order, independent of presented A/B slots. Cardinality is one for rubric and exactly two distinct candidate IDs for pairwise. The common constructor's canonical identity payloads and PR06's battle ID payload are exactly:

```json
{
  "schema": "eval-harness.evaluation-input",
  "schema_version": 1,
  "task": {
    "snapshot_sha256": "...",
    "task_id": "...",
    "task_sha256": "...",
    "canonical_prompt_sha256": "...",
    "evaluation_view_sha256": "..."
  },
  "evaluator": {
    "evaluator_id": "...",
    "evaluator_revision": "...",
    "evaluator_config_sha256": "..."
  },
  "candidates": [
    {"candidate_id": "...", "bundle_sha256": "..."}
  ]
}
```

```json
{
  "schema": "eval-harness.evaluation-job",
  "schema_version": 1,
  "evaluation_input_sha256": "...",
  "match_occurrence_id": "..."
}
```

```json
{
  "schema": "eval-harness.battle-record-id",
  "schema_version": 1,
  "evaluation_job_id": "...",
  "trial_index": 0
}
```

For the fixture whose snapshot/task/prompt/view/config digests are respectively `0`/`1`/`2`/`3`/`4` repeated 64 times, evaluator `gdpval.pairwise` revision `2`, logical candidates `candidate-alpha`/`a` repeated 64 and `candidate-beta`/`b` repeated 64, and occurrence `occurrence-0007`, exact outputs are:

```json
{
  "evaluation_input_sha256": "98e3ea17c3a6755b39d1ebc1bd44a5bbeb123948a924df31e61ca9aa494f1e89",
  "evaluation_job_id": "12dcbe66dc6aa2b1408bd81c61b33669c21ff48e304c67fcf48a95f9c79b59a5",
  "battle_record_id_for_trial_0": "7d06ea1f110f12b29367f724b2cefb326f39508fd64dbd697e5fb1d3c6680a58"
}
```

Changing only `match_occurrence_id` preserves `evaluation_input_sha256` and changes both downstream IDs. Changing either bundle bytes/hash, logical candidate ID/order, view identity, evaluator revision, or configuration changes all downstream IDs.

## Public scoring and response API

`scoring.py` exposes these exact types and functions:

```python
class RubricMode(StrEnum):
    BINARY = "binary"
    STRUCTURED = "structured"

class CompletionPolicyKind(StrEnum):
    REQUIRE_COMPLETE = "require_complete"
    VALID_ONLY = "valid_only"

@dataclass(frozen=True, slots=True)
class CompletionPolicy:
    kind: CompletionPolicyKind
    min_valid: int | None

@dataclass(frozen=True, slots=True)
class RubricDefinition:
    rubric_json: JSONValue | None
    rubric_pretty: str
    maximum_points: float | None
    rubric_sha256: str

@dataclass(frozen=True, slots=True)
class ParsedRubricScore:
    raw_points: float
    maximum_points: float
    normalized_score: float
    canonical_result_sha256: str

class JudgeResponseError(ValueError):
    code: str

def rubric_from_view(view: BoundEvaluationView, *, mode: RubricMode) -> RubricDefinition: ...
def render_binary_rubric_prompt(*, task_prompt: str, rubric_pretty: str, deliverable_text: str) -> str: ...
def render_structured_rubric_prompt(*, task_prompt: str, rubric_pretty: str) -> str: ...
def render_pairwise_prompt(*, task_prompt: str) -> str: ...
def parse_binary_rubric_response(response_text: str) -> ParsedRubricScore: ...
def parse_structured_rubric_response(
    response_text: str, *, expected_maximum: float
) -> ParsedRubricScore: ...
def parse_pairwise_response(response_text: str) -> Verdict: ...
```

`CompletionPolicy(REQUIRE_COMPLETE, None)` is the only complete-policy shape. `VALID_ONLY` requires a positive integer `min_valid`; evaluator config validation also requires `min_valid <= num_trials`. Booleans do not count as integers. Non-positive trial/attempt counts and non-finite/non-positive timeouts fail configuration before any call.

`JudgeResponseError.code` is exactly one of `empty_response`, `truncated_json`, `malformed_json`, `ambiguous_response`, `missing_score`, `non_numeric_score`, `non_finite_score`, `maximum_mismatch`, `score_out_of_range`, or `invalid_verdict`. It is caught at the evaluator boundary and becomes `battle_status=invalid_response` plus `EvaluationFailure(Failure(INVALID_RESPONSE, code, TASK), retryable=<resolved policy>)`; it never becomes a score, vote, tie, or runtime `failed` status.

`rubric_from_view` reads only `view.evaluation_data["rubric_json"]` and `["rubric_pretty"]`. When present, the JSON value must be a strict JSON list or mapping; `rubric_pretty` must be a string. At least one form must be nonempty. When pretty text is empty, the presenter uses `json.dumps(rubric_json, ensure_ascii=False, sort_keys=True, indent=2)`. Structured mode additionally requires nonempty JSON so it can compute the denominator. Missing/invalid required rubric data is `rubric_missing` preflight failure. `rubric_sha256` hashes schema `eval-harness.gdpval-rubric`, version 2, the canonical JSON value (or null), and the exact selected pretty string. `sector`, `occupation`, attachment URLs, and every other evaluation-data field are excluded from judge input, though the already bound evaluation-view digest still commits to the full evaluator-only view.

Binary parsing accepts exactly one JSON object with unique keys, optionally inside one complete code fence. It preserves score-key precedence `overall_score`, `total_score`, `score`, `average_score`, `final_score`; otherwise it uses the finite numeric mean of dictionary entries in `criteria_scores[*].score`, with a missing `score` in such an entry contributing `0.0` as in the characterized valid path. It clamps a finite numeric result to `[0,1]`. Truncation recovery, no-score JSON, booleans, non-numeric/non-finite conversion, duplicate keys, multiple objects/fences, and trailing non-whitespace are invalid.

Structured parsing requires exactly one `FINAL_SCORE[x]` and one `MAX_POSSIBLE_SCORE[y]`, a finite positive configured maximum, the legacy inclusive check `abs(y - expected_maximum) <= 0.01`, and `0 <= x <= y`. Duplicate/conflicting tags are invalid. Valid normalized score is `x/y`. `rubric_from_view` computes the expected maximum by iterating either a top-level rubric list or a mapping's `criteria` list and, for every dictionary item, adding its finite numeric `score` when present or otherwise its finite numeric `weight`; missing values contribute zero. A non-list shape, a boolean/non-numeric/non-finite contribution, or a total that is not finite and positive fails before any call. The aggregate preserves the current first-valid-denominator rule: `raw_points_mean` is the mean of completed trial points, `maximum_points` is the first completed trial's parsed maximum in trial-index order, and `normalized_score = raw_points_mean / maximum_points`. Pairwise delegates to the already characterized strict standalone case-insensitive `BOXED[A|B|TIE]` parser; no substring or default-tie path is added.

Prompt asset bytes are fixed acceptance data:

| Asset | Exact bytes/hash | Render oracle |
|---|---|---|
| `gdpval_binary_rubric_v2.j2` | 1,609-byte licensed asset SHA-256 `3db57bcbfdaa92489cf5a2062e88d49fda3f47a0ff0f722b5b925a338c99d8ef`; its 1,436-byte payload is exact source blob `0285b21e5fb8f0930037d805715fcb6eedd67cb6`, SHA-256 `f0af9a09cb0e067c53a7e51922064d89092dbc01857268add93e78d519587768` | `Canonical task` / `Pretty rubric` / `Deliverable` renders 1,399 characters, SHA-256 `eb2cdadcab2f620f7fae53d3ec46816bb79b1b07fe6c403e9e940caa88b15737` |
| `gdpval_structured_rubric_v2.txt` | 1,027-byte licensed asset SHA-256 `6d4b9b4b21e78bb9cd7930cd69e05768ad156b7e084b754157bfe4489915e49c`; its 866-byte payload is exact `STRUCTURED_JUDGE_PROMPT`, terminal LF, SHA-256 `f993ab2daf3a5f7f47cbbac22fe6076f8923d8ce7bbb6b68d7526cf1eee49c72` | structured message framing is pinned by the `4/5`, `2/99`, and `2/5` fixtures |
| `gdpval_pairwise_v2.j2` | 852-byte licensed asset SHA-256 `1c442e8f41514247ca1f924930d21a0e5823ba89a48dbf458d785ea2333d508d`; its 679-byte payload is exact reviewed `build_judge_prompt` text with only the task value replaced by `{{ task_prompt }}`, terminal LF, SHA-256 `64a9a07ab08e7a5e859f06ab4cf4af08554a746692f6a8114816efaa32afaac2` | `Canonical task` renders 676 characters, SHA-256 `be0f88fbcfd48f0d76243d0d349d26586b346510dd68e40dc7e263116bd560ce` |

The two `.j2` files begin with these exact three LF-terminated lines: `{# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. #}`, `{# SPDX-License-Identifier: Apache-2.0 #}`, `{# GDPVAL_PROMPT_PAYLOAD #}`. The `.txt` file uses the same three lines with `# ` comments and no closing delimiters. The loader validates and removes exactly those three storage-header lines, then hashes/renders the payload. Load assets with explicit UTF-8. Render only the exact, count-checked placeholder tokens with literal replacement, rejecting missing or extra template variables; this adds no template dependency. Both rendered templates preserve their payload terminal LF, matching the characterized hashes and keeping pairwise byte-equal to `build_judge_prompt`. The evaluator config binds both whole-asset and payload hashes. Any prompt text change requires a new evaluator/config revision and fixture update; it is not a formatting cleanup.

## Public presentation API

`presentation.py` exposes:

```python
class PresentationMode(StrEnum):
    FILESYSTEM = "filesystem"
    CONTENT_BLOCKS = "content_blocks"

class PresentationRole(StrEnum):
    TASK_INPUT = "task_input"
    RUBRIC = "rubric"
    SUBMISSION = "submission"
    SUBMISSION_A = "submission_a"
    SUBMISSION_B = "submission_b"

class PresentationFileStatus(StrEnum):
    COPIED = "copied"
    DERIVED = "derived"
    OMITTED_OPTIONAL = "omitted_optional"

@dataclass(frozen=True, slots=True)
class PresentationPolicy:
    policy_id: str
    revision: str
    mode: PresentationMode
    submission_source_policy_id: str
    max_file_bytes: int
    max_archive_members: int
    max_archive_uncompressed_bytes: int
    max_archive_depth: int
    supported_suffixes: frozenset[str]
    optional_logical_paths: frozenset[str]
    office_renderer_id: str | None

@dataclass(frozen=True, slots=True)
class PresentedFile:
    role: PresentationRole
    source_logical_path: str
    source_sha256: str
    source_size: int
    media_type: str
    status: PresentationFileStatus
    presented_logical_path: str | None
    derived_sha256: str | None
    derivation_id: str | None

@dataclass(frozen=True, slots=True)
class PresentationManifest:
    presenter_id: str
    presenter_revision: str
    mode: PresentationMode
    submission_source_policy_id: str
    files: tuple[PresentedFile, ...]
    content_blocks: tuple[JudgeContentBlock, ...]
    required_capabilities: frozenset[JudgeCapability]
    rendered_prompt_sha256: str
    presentation_sha256: str
    judge_input_sha256: str

@dataclass(frozen=True, slots=True)
class PresentedJudgeInput:
    prompt: str
    anonymous_workspace: Path
    content_blocks: tuple[JudgeContentBlock, ...]
    manifest: PresentationManifest
    judge_input_sha256: str

class GDPvalPresentationError(ValueError):
    code: str

def plan_rubric_presentation(
    *,
    view: BoundEvaluationView,
    candidate: CandidateBundle,
    prompt: str,
    policy: PresentationPolicy,
) -> PresentationManifest: ...

def plan_pairwise_presentation(
    *,
    view: BoundEvaluationView,
    slot_a: CandidateBundle,
    slot_b: CandidateBundle,
    prompt: str,
    policy: PresentationPolicy,
) -> PresentationManifest: ...

def materialize_rubric_presentation(
    *,
    expected: PresentationManifest,
    view: BoundEvaluationView,
    candidate: CandidateBundle,
    prompt: str,
    policy: PresentationPolicy,
    destination: Path,
) -> PresentedJudgeInput: ...

def materialize_pairwise_presentation(
    *,
    expected: PresentationManifest,
    view: BoundEvaluationView,
    slot_a: CandidateBundle,
    slot_b: CandidateBundle,
    prompt: str,
    policy: PresentationPolicy,
    destination: Path,
) -> PresentedJudgeInput: ...
```

`GDPvalPresentationError.code` is exactly one of `destination_not_fresh`, `source_changed`, `unsafe_path`, `path_collision`, `unsupported_required`, `oversize_required`, `archive_unsafe`, `archive_limit`, `conversion_failed`, `presentation_mismatch`, or `output_channel_missing`.

`JudgeContentBlock` is the accepted PR05 metadata type `JudgeContentBlock(block_id: str, media_type: str, logical_path: str, size: int, sha256: str)`. Its safe neutral POSIX path is beneath `anonymous_workspace`. Planning performs every read/conversion needed to freeze ordered blocks, source and derived hashes, capabilities, and `judge_input_sha256` without retaining a readable candidate path. Materialization repeats those operations into the explicit fresh destination and fails on any mismatch with `expected`; it cannot revise the saved plan. Both presentation modes produce an anonymous workspace and the exact ordered block tuple. The runtime re-reads and verifies the declared exact file set, sizes, and hashes; local CLI exposes only the workspace, while HTTP transport creates provider-native ordered blocks from the same files and metadata. `destination` must be fresh and disjoint from source/snapshot/result roots. The semantic manifest uses logical paths only; the runtime workspace path is never hashed.

The implementation reads task inputs only through `view.allowed_task_inputs`, rubric data only through `view.evaluation_data`, and candidate bytes only through `CandidateBundle.read_artifact`. It rejects symlinks, path escape, Unicode/casefold or file/directory collisions, unsupported required content, required oversize content, archive traversal/bombs, failed conversion, and changed source bytes. A file may be omitted only when its exact normalized logical path is in `optional_logical_paths`; glob or suffix inference cannot make a file optional. Archive members retain safe member-relative paths and are bounded by all three archive limits. Office conversion reads a copied source under the fresh root and writes a separate derived subtree; it cannot create/delete beside source. Filesystem copies are mode `0444`, directories `0555`, and mtime `2000-01-01T00:00:00Z` exactly as characterized.

The default v2 supported suffix set is explicit and lowercase: text/code `.txt`, `.csv`, `.json`, `.xml`, `.html`, `.md`, `.yaml`, `.yml`, `.py`, `.sh`, `.bash`, `.c`, `.cpp`, `.java`, `.js`, `.tsx`, `.sol`, `.ts`, `.log`; document/image `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`, `.heif`; Office `.docx`, `.pptx`, `.xlsx`; audio `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg`, `.oga`, `.opus`, `.wma`, `.aiff`, `.aif`; video `.mp4`, `.m4v`, `.mov`, `.avi`, `.mkv`, `.webm`, `.wmv`, `.flv`, `.x-flv`, `.mpeg`, `.mpg`, `.3gp`, `.3gpp`; and archive `.zip`. The policy stores this set, so adding/removing a type changes the evaluator configuration digest. Text decoding uses UTF-8 with replacement and records the derived text hash. Office formats require the named renderer; PDF/image/audio/video must be emitted as actual content blocks or readable files, never labels alone.

The shipped v2 policies use `max_file_bytes=262144000` (250 MiB), `max_archive_members=4096`, `max_archive_uncompressed_bytes=1073741824` (1 GiB), `max_archive_depth=1`, and an empty `optional_logical_paths`. These are hash-bound resource limits. A profile may choose stricter positive limits or enumerate exact optional paths under a distinct config digest; it may not silently relax a failed plan.

Rubric uses `submission_source_policy_id="artifacts-then-final-text-v1"`: a nonempty verified artifact manifest is presented in full; final output text is used only when the successful bundle has no artifact channel/content; a required artifact read/conversion failure cannot fall back to text. Pairwise uses `"artifacts-only-v1"`: it presents both verified artifact trees, records an explicit empty tree when successful artifacts are empty, and never substitutes executor output text or finish metadata. Any other policy ID is rejected in PR06.

`judge_input_sha256` hashes the prompt asset/revision and rendered bytes, canonical task hash/text, allowed reference logical paths/bytes, anonymous submission logical paths/bytes, allowed rubric fields, presentation policy, and derivations. Candidate IDs, bundle manifests/provenance, effective prompts, absolute paths, and controller/runtime values are absent from the prompt, blocks, workspace, argv, environment, and digest.

## Public panel and resolved-plan API

`panel.py` exposes:

```python
class JudgeCapability(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILESYSTEM = "filesystem"

@dataclass(frozen=True, slots=True)
class JudgeMemberSpec:
    runtime_member: JudgeRuntimeMember
    capabilities: frozenset[JudgeCapability]
    weight: float
    public_config: Mapping[str, JSONValue]
    member_spec_sha256: str

@dataclass(frozen=True, slots=True)
class JudgePanelSpec:
    panel_id: str
    revision: str
    members: tuple[JudgeMemberSpec, ...]
    panel_sha256: str

class GDPvalPlanError(ValueError):
    code: str

def select_judge_members(
    panel: JudgePanelSpec,
    *,
    required_capabilities: frozenset[JudgeCapability],
    count: int,
    selection_policy_id: str,
    seed: int,
    selection_parts: tuple[str, ...],
    explicit_member_ids: tuple[str, ...] | None = None,
) -> tuple[JudgeMemberSpec, ...]: ...

def resolve_pairwise_trial_plan(
    *,
    candidates: tuple[LogicalCandidateReference, LogicalCandidateReference],
    members: tuple[JudgeMemberSpec, ...],
    num_trials: int,
    position_policy_id: str,
    position_seed: int,
    position_task_key: str,
    explicit_position_order: tuple[tuple[str, str], ...] | None = None,
) -> tuple[PairwiseTrialPlan, ...]: ...

def resolve_rubric_trial_plan(
    *,
    candidate: LogicalCandidateReference,
    members: tuple[JudgeMemberSpec, ...],
    num_trials: int,
) -> tuple[RubricTrialPlan, ...]: ...
```

`GDPvalPlanError.code` is exactly one of `invalid_panel`, `duplicate_member`, `invalid_weight`, `invalid_count`, `missing_member`, `judge_capability_insufficient`, `invalid_position_order`, or `invalid_candidate_pair`.

Supported selection policies are `legacy-weighted-sha256-v1` and `explicit-v1`. The legacy policy exactly preserves the reviewed `make_rng`: join `repr(seed)` followed by the raw string parts with `|`, hash those UTF-8 bytes with SHA-256, seed `random.Random` from `int(digest[:16], 16)`, preserve member order, then use `random.choices`. Negative/zero weight becomes zero and an all-zero eligible set samples uniformly. Non-finite weights, duplicate IDs, empty members, count less than one, missing explicit IDs, or explicit count mismatch fail configuration. Capability filtering occurs before selection; an empty capable set is `judge_capability_insufficient` with zero calls. Credentials and secret-bearing configuration cannot inhabit `JudgeMemberSpec` or either digest.

`member_spec_sha256` is recomputed from schema `eval-harness.judge-member`, version 1, the complete `runtime_member` semantic projection, capabilities, weight, and `public_config`; `panel_sha256` is recomputed from schema `eval-harness.judge-panel`, version 1, panel ID/revision, and the ordered complete member projections. Constructors reject supplied hash mismatches. The public runtime projection includes member ID, runtime profile ID, model, requested reasoning effort, and timeout. `public_config` may contain only additional runtime knobs safe to persist and show to the controller; authentication material and environment values belong to the injected runtime profile and cannot enter this mapping.

Supported position policies are `alternating-a-first-v1`, `alternating-seeded-v1`, and `explicit-slots-v1`. GDPval default is four entries under A-first alternation. The seeded policy computes its first swap as the low bit of the first byte of `sha256(f"{position_seed}:{position_task_key}".encode("utf-8")).digest()`, then alternates; its fixture uses seed 42 and the bound task ID. `explicit_position_order` must contain exactly `num_trials` pairs, and every pair must be one occurrence of each logical candidate. AA-v2 supplies its exact order and member IDs; no hidden seed swap occurs. A retry uses the same resolved member and slots.

## Public BattleRecord and fold API

`records.py` also exposes:

```python
@dataclass(frozen=True, slots=True)
class PresentedSlot:
    candidate_id: str
    bundle_sha256: str

@dataclass(frozen=True, slots=True)
class PairwiseTrialPlan:
    trial_index: int
    slot_a: PresentedSlot
    slot_b: PresentedSlot
    judge_member_id: str
    judge_member_spec_sha256: str

@dataclass(frozen=True, slots=True)
class RubricTrialPlan:
    trial_index: int
    candidate: LogicalCandidateReference
    judge_member_id: str
    judge_member_spec_sha256: str

class BattleStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    INVALID_RESPONSE = "invalid_response"

class WinnerKind(StrEnum):
    CANDIDATE = "candidate"
    TIE = "tie"

@dataclass(frozen=True, slots=True)
class BattleWinner:
    kind: WinnerKind
    candidate_id: str | None

@dataclass(frozen=True, slots=True)
class BattlePlanEntry:
    battle_record_id: str
    evaluation_job_id: str
    evaluation_input_sha256: str
    match_occurrence_id: str
    trial_index: int
    task_id: str
    task_sha256: str
    snapshot_sha256: str
    canonical_prompt_sha256: str
    evaluation_view_sha256: str
    evaluator_id: str
    evaluator_revision: str
    evaluator_config_sha256: str
    panel_sha256: str
    presentation_sha256: str
    judge_input_sha256: str
    logical_candidates: tuple[LogicalCandidateReference, LogicalCandidateReference]
    slot_a: PresentedSlot
    slot_b: PresentedSlot
    judge_member_id: str
    judge_member_spec_sha256: str

@dataclass(frozen=True, slots=True)
class BattleResult:
    presented_verdict: Verdict
    winner: BattleWinner
    canonical_result_sha256: str

@dataclass(frozen=True, slots=True)
class BattleRecord:
    plan: BattlePlanEntry
    battle_status: BattleStatus
    result: BattleResult | None
    battle_semantic_sha256: str | None
    failure: EvaluationFailure | None
    attempt_history_sha256: str

@dataclass(frozen=True, slots=True)
class PairwiseAggregate:
    candidate_wins: Mapping[str, int]
    ties: int
    requested_trials: int
    valid_trials: int
    invalid_trials: int
    failed_trials: int
    interrupted_trials: int
    unattempted_trials: int
    coverage: float
    winner: BattleWinner | None

@dataclass(frozen=True, slots=True)
class RubricPlanEntry:
    battle_record_id: str
    evaluation_job_id: str
    evaluation_input_sha256: str
    match_occurrence_id: str
    trial_index: int
    task_id: str
    task_sha256: str
    snapshot_sha256: str
    canonical_prompt_sha256: str
    evaluation_view_sha256: str
    evaluator_id: str
    evaluator_revision: str
    evaluator_config_sha256: str
    panel_sha256: str
    presentation_sha256: str
    judge_input_sha256: str
    logical_candidate: LogicalCandidateReference
    judge_member_id: str
    judge_member_spec_sha256: str

@dataclass(frozen=True, slots=True)
class RubricTrialResult:
    raw_points: float
    maximum_points: float
    normalized_score: float
    canonical_result_sha256: str

@dataclass(frozen=True, slots=True)
class RubricTrialRecord:
    plan: RubricPlanEntry
    battle_status: BattleStatus
    result: RubricTrialResult | None
    battle_semantic_sha256: str | None
    failure: EvaluationFailure | None
    attempt_history_sha256: str

@dataclass(frozen=True, slots=True)
class RubricAggregate:
    requested_trials: int
    valid_trials: int
    invalid_trials: int
    failed_trials: int
    interrupted_trials: int
    unattempted_trials: int
    coverage: float
    raw_points_mean: float | None
    maximum_points: float | None
    normalized_score: float | None

def normalize_battle_result(plan: BattlePlanEntry, verdict: Verdict) -> BattleResult: ...
def build_battle_record(
    *,
    plan: BattlePlanEntry,
    battle_status: BattleStatus,
    result: BattleResult | None,
    failure: EvaluationFailure | None,
    attempt_history_sha256: str,
) -> BattleRecord: ...
def validate_battle_record(record: BattleRecord) -> None: ...
def fold_pairwise_records(
    *,
    candidates: tuple[LogicalCandidateReference, LogicalCandidateReference],
    records: tuple[BattleRecord, ...],
    requested_trials: int,
    completion_policy: CompletionPolicy,
) -> PairwiseAggregate: ...

def normalize_rubric_result(
    plan: RubricPlanEntry, parsed: ParsedRubricScore
) -> RubricTrialResult: ...
def build_rubric_trial_record(
    *,
    plan: RubricPlanEntry,
    battle_status: BattleStatus,
    result: RubricTrialResult | None,
    failure: EvaluationFailure | None,
    attempt_history_sha256: str,
) -> RubricTrialRecord: ...
def validate_rubric_trial_record(record: RubricTrialRecord) -> None: ...
def fold_rubric_records(
    *,
    records: tuple[RubricTrialRecord, ...],
    requested_trials: int,
    completion_policy: CompletionPolicy,
) -> RubricAggregate: ...
```

The canonical pairwise completed-result payload is schema `eval-harness.battle-result`, version 1, with `presented_verdict` and `winner={"kind": ..., "candidate_id": ...}`; tie requires `candidate_id=null`. The rubric equivalent is schema `eval-harness.rubric-trial-result`, version 1, with the three finite score fields. Each result hash is `canonical_result_sha256`. `battle_semantic_sha256` hashes schema `eval-harness.battle-semantic`, version 1, the exact canonical plan entry payload, and the corresponding completed-result payload. It is present only for `completed`. The builders reject every inconsistent status/result/failure/retryability combination and recompute rather than trust semantic digests.

Attempt event IDs and objects use schemas `eval-harness.battle-attempt-id` and `eval-harness.battle-attempt-event`, version 1. `attempt_id` hashes `battle_record_id` plus positive `attempt_number`. Each event contains that identity, event kind `started` or `terminal`, lifecycle status, UTC timestamp, runtime/version/auth and role-policy/probe evidence, exit code, typed failure/retryability, raw stdout/stderr/response hashes, logical evidence references, and completed semantic digest when present. `attempt_event_sha256` hashes the whole event excluding its own hash. `attempt_history_sha256` hashes schema `eval-harness.battle-attempt-history`, version 1, `battle_record_id`, and the ordered exact event-digest list. Attempts/times/paths/raw evidence/history are excluded from `battle_semantic_sha256`.

Invalid, failed, interrupted, planned, or running records have no result, semantic digest, winner, or vote. Failed/interrupted/invalid records carry one `EvaluationFailure`; planned/running/completed records carry none. An invalid response uses `FailureKind.INVALID_RESPONSE`, task impact, the stable `JudgeResponseError.code`, and the explicitly resolved retryability policy. Diagnostics and provider text are evidence, never failure codes. Aggregate counts partition every requested trial into valid, invalid, failed, interrupted, or unattempted; coverage is `valid_trials/requested_trials`. An aggregate with zero eligible records has no winner. Only a completed explicit `TIE` increments `ties`; the aggregate winner is candidate A when A wins exceed B wins, candidate B when B wins exceed A wins, otherwise an aggregate tie, but zero valid trials still has no winner. `valid_only` may publish only after its positive `min_valid` threshold and must return partial coverage; `require_complete` publishes only the exact complete set.

## Evaluator entrypoints and exact result shapes

`eval_harness/evaluators/gdpval.py` exposes:

```python
@dataclass(frozen=True, slots=True)
class GDPvalRubricConfig:
    mode: RubricMode
    completion_policy: CompletionPolicy
    num_trials: int
    max_attempts_per_trial: int
    presentation: PresentationPolicy
    panel: JudgePanelSpec
    selection_policy_id: str
    selection_seed: int
    selection_parts: tuple[str, ...]
    explicit_member_ids: tuple[str, ...] | None
    blind_policy: BlindJudgePolicy

@dataclass(frozen=True, slots=True)
class GDPvalPairwiseConfig:
    completion_policy: CompletionPolicy
    num_trials: int
    max_attempts_per_trial: int
    presentation: PresentationPolicy
    panel: JudgePanelSpec
    selection_policy_id: str
    selection_seed: int
    selection_parts: tuple[str, ...]
    explicit_member_ids: tuple[str, ...] | None
    position_policy_id: str
    position_seed: int
    position_task_key: str
    explicit_position_order: tuple[tuple[str, str], ...] | None
    blind_policy: BlindJudgePolicy

class GDPvalRubricEvaluator(Evaluator):
    def __init__(self, *, config: GDPvalRubricConfig) -> None: ...
    def judge_runtime_preflight_requests(
        self, view: BoundEvaluationView
    ) -> tuple[JudgeRuntimePreflightRequest, ...]: ...
    def plan(self, request: EvaluationPlanRequest) -> Mapping[str, JSONValue]: ...
    def evaluate(self, request: EvaluationJobRequest) -> EvaluationResult: ...

class GDPvalPairwiseEvaluator(Evaluator):
    def __init__(self, *, config: GDPvalPairwiseConfig) -> None: ...
    def judge_runtime_preflight_requests(
        self, view: BoundEvaluationView
    ) -> tuple[JudgeRuntimePreflightRequest, ...]: ...
    def plan(self, request: EvaluationPlanRequest) -> Mapping[str, JSONValue]: ...
    def evaluate(self, request: EvaluationJobRequest) -> EvaluationResult: ...
```

Each instance exposes its exact `evaluator_id`, revision `"2"`, required candidate count, and `evaluator_config_sha256`; the config digest binds every dataclass field plus parser/prompt/presenter/panel-policy revisions and prompt asset SHA-256 values. `judge_runtime_preflight_requests` returns one no-model request for every configured member that could be selected. Every request must pass before generation/evaluation proceeds; a failed member is not removed and the weights are not renormalized as an availability fallback. Candidate-artifact modalities cannot be known from the view alone, so `plan` later applies capability filtering and fails with `judge_capability_insufficient` before judge calls if the already-preflighted exact panel lacks support.

`plan` validates the bound view/bundles, computes the rubric and anonymous presentation manifests, filters capabilities, resolves every member and slot, and returns one strict JSON mapping with schema `eval-harness.gdpval-evaluator-plan` and version 1. The mapping has `evaluator_id`, `evaluator_revision`, `evaluator_config_sha256`, `completion_policy`, `panel_sha256`, `presentation_policy`, `num_trials`, and ordered `trials`. Each trial has `trial_index`, `judge_member_id`, `judge_member_spec_sha256`, the full presentation-manifest projection, `presentation_sha256`, and `judge_input_sha256`; rubric adds one `logical_candidate`, while pairwise adds `slot_a` and `slot_b`. It contains no attempt, timestamp, runtime path, secret, or AA field.

The execution request supplies `job`, `view`, `candidates`, a fresh `result_root`, `record_sink`, and `judge_runtime`. GDPval requires a non-null runtime. Pairwise has exactly two candidates; rubric has exactly one. The evaluator verifies the request capabilities and every job/view/bundle/evaluator/config/plan hash before it asks the sink to save the immutable job/trial plan. It derives each `battle_record_id` from the now-complete `evaluation_job_id` plus trial index. Construction, plan validation, materialization, capability/member/position checks, runtime preflight, and `save_plan` all finish before the first invocation. Runtime preflight and every call use the exact resolved member and the accepted blind role policy. There is no fallback member, model, provider, transport, reasoning setting, API, resources server, or local judge runner.

Each bundle must be a verified successful `completed` or accepted `no_deliverable` outcome and must expose the output channel selected by the presentation policy. Bundle snapshot reference, task ID/hash, canonical prompt text/hash, candidate ID, and bundle digest must match the job/view exactly. Missing, failed, modified, incoherent, or duplicate pairwise candidates fail before sink intent or runtime invocation; identical artifact bytes for distinct candidate IDs remain valid.

A completed binary-rubric result for task `task-1`, one normalized score `0.75`, and `require_complete` has exactly this envelope:

```json
{
  "evaluation_job_id": "<evaluation_job_id>",
  "task_id": "task-1",
  "status": "completed",
  "failure": null,
  "metrics": {"rubric_score": 0.75},
  "outcomes": {
    "requested_trials": 1,
    "valid_trials": 1,
    "invalid_trials": 0,
    "failed_trials": 0,
    "interrupted_trials": 0,
    "unattempted_trials": 0,
    "coverage": 1.0,
    "raw_points_mean": 0.75,
    "maximum_points": 1.0,
    "record_ids": ["<battle_record_id>"],
    "semantic_record_sha256s": ["<battle_semantic_sha256>"]
  },
  "details": {
    "evaluator_id": "gdpval.rubric.binary",
    "evaluator_revision": "2",
    "evaluator_config_sha256": "<evaluator_config_sha256>",
    "evaluation_input_sha256": "<evaluation_input_sha256>",
    "evaluation_view_sha256": "<evaluation_view_sha256>",
    "evaluator_plan_sha256": "<evaluator_plan_sha256>",
    "panel_sha256": "<panel_sha256>",
    "presentation_sha256s": ["<presentation_sha256>"],
    "judge_input_sha256s": ["<judge_input_sha256>"],
    "completion_policy": {"kind": "require_complete", "min_valid": null},
    "attempt_history_sha256s": ["<attempt_history_sha256>"],
    "failure_evidence_sha256s": []
  }
}
```

The digest placeholders take the actual lowercase SHA-256 values. A completed pairwise result for task `task-1`, logical candidates `candidate-alpha`/`candidate-beta`, completed logical verdicts A, B, TIE, A, and `require_complete` has exactly:

```json
{
  "evaluation_job_id": "<evaluation_job_id>",
  "task_id": "task-1",
  "status": "completed",
  "failure": null,
  "metrics": {},
  "outcomes": {
    "candidate_wins": {"candidate-alpha": 2, "candidate-beta": 1},
    "ties": 1,
    "requested_trials": 4,
    "valid_trials": 4,
    "invalid_trials": 0,
    "failed_trials": 0,
    "interrupted_trials": 0,
    "unattempted_trials": 0,
    "coverage": 1.0,
    "winner": {"kind": "candidate", "candidate_id": "candidate-alpha"},
    "record_ids": ["<trial-0-id>", "<trial-1-id>", "<trial-2-id>", "<trial-3-id>"],
    "semantic_record_sha256s": ["<trial-0-sha256>", "<trial-1-sha256>", "<trial-2-sha256>", "<trial-3-sha256>"]
  },
  "details": {
    "evaluator_id": "gdpval.pairwise",
    "evaluator_revision": "2",
    "evaluator_config_sha256": "<evaluator_config_sha256>",
    "evaluation_input_sha256": "<evaluation_input_sha256>",
    "evaluation_view_sha256": "<evaluation_view_sha256>",
    "evaluator_plan_sha256": "<evaluator_plan_sha256>",
    "panel_sha256": "<panel_sha256>",
    "presentation_sha256s": ["<trial-0-presentation-sha256>", "<trial-1-presentation-sha256>", "<trial-2-presentation-sha256>", "<trial-3-presentation-sha256>"],
    "judge_input_sha256s": ["<trial-0-input-sha256>", "<trial-1-input-sha256>", "<trial-2-input-sha256>", "<trial-3-input-sha256>"],
    "completion_policy": {"kind": "require_complete", "min_valid": null},
    "attempt_history_sha256s": ["<trial-0-history-sha256>", "<trial-1-history-sha256>", "<trial-2-history-sha256>", "<trial-3-history-sha256>"],
    "failure_evidence_sha256s": []
  }
}
```

Every result uses the same detail keys in that order; arrays follow trial-index order. `failure_evidence_sha256s` contains the ordered persisted evidence digests for noncompleted records and is empty for a complete result. The rubric outcome keys are fixed as shown. Pairwise adds the fixed candidate-keyed counts, ties, and winner shown. For an ineligible post-plan result, `metrics={}`, pairwise `winner=null`, and completed-only semantic hashes include only records that actually completed; all planned record IDs and count fields remain. A failure before plan persistence has empty record/evidence arrays, zero requested/valid/invalid/failed/interrupted/unattempted counts, and coverage `0.0`. No result detail contains a secret, diagnostic/provider text, runtime path, or unrestricted environment.

`winner` is `{"kind":"candidate","candidate_id":"..."}` or `{"kind":"tie","candidate_id":null}` only when the completion policy is eligible; otherwise it is null and no score/reward/tie is inferred. Pairwise produces no rubric metric, universal score, Elo, anchor/stage/headline value, or orientation-dependent reward.

`require_complete` is eligible only when all requested records are completed. `valid_only(min_valid=N)` is eligible when at least `N` records are completed, every requested trial is in a terminal state, and there is no run-impact failure or interruption; it returns `partial` whenever coverage is below 1.0. `completed` requires top-level `failure=null`. An eligible `partial` carries the first noncompleted trial's `Failure` in trial-index order, wrapped with `retryable=False`; the exact per-trial failures remain in their records. `failed` and `interrupted` also require a non-null top-level failure; interruption uses `FailureKind.INTERRUPTED`. A run-impact failure, any interruption, a remaining planned/running record, or insufficient valid count returns no metric/winner regardless of already valid records. Retryability controls whether another attempt may be appended under the configured attempt limit; it never changes a terminal invalid/failed record into a counted record.

Default configs are binary one trial/one attempt/`require_complete`; structured two trials/three attempts per trial/`valid_only(min_valid=1)`; pairwise four trials/one attempt/`alternating-a-first-v1`/`require_complete`. A parser-invalid structured attempt may retry while its fixed three-attempt budget remains; runtime-retryable failures use the same budget. Every retry keeps the planned member, presentation, and slots, receives the next positive attempt number, and is persisted. Counts are positive. Any supported override changes the configuration digest.

## Focused test inventory and exact commands

The new/rewritten focused files contain exactly 53 non-skipped cases: 10 scoring, 8 presentation, 6 panel, 8 records, 11 evaluator, 8 shared-runtime isolation, and the existing two registry cases with the GDPval expectation revised. Parameterization must not make the collected count ambiguous for this gate.

Use these exact case names and keep each listed name as one collected case:

| File | Exact test functions |
|---|---|
| `test_gdpval_scoring_v2.py` | `test_prompt_asset_bytes_and_render_hashes`; `test_binary_score_precedence_and_criteria_mean`; `test_binary_finite_clamping`; `test_binary_truncated_missing_and_nonfinite_are_invalid`; `test_binary_ambiguous_json_is_invalid`; `test_structured_valid_score_math`; `test_structured_missing_or_duplicate_tags_are_invalid`; `test_structured_maximum_and_range_validation`; `test_rubric_definition_maximum_and_hash`; `test_pairwise_strict_verdict_matrix` |
| `test_gdpval_presentation_v2.py` | `test_filesystem_projection_is_anonymous_and_normalized`; `test_content_blocks_preserve_roles_paths_and_bytes`; `test_office_derivation_preserves_every_source_byte`; `test_zip_paths_collisions_traversal_and_limits`; `test_required_and_explicitly_optional_file_policy`; `test_audio_video_is_present_and_requires_capabilities`; `test_rubric_and_pairwise_submission_source_policies`; `test_plan_materialization_digest_match_and_mismatch` |
| `test_gdpval_panel_v2.py` | `test_member_and_panel_hashes_reject_secrets_and_mismatch`; `test_legacy_weighted_draw_fixture`; `test_nonpositive_and_all_zero_weights`; `test_capability_filter_and_av_insufficiency`; `test_a_first_and_seeded_position_fixtures`; `test_explicit_members_and_slots_are_frozen_and_validated` |
| `test_gdpval_records_v2.py` | `test_common_identity_and_battle_id_goldens`; `test_occurrence_changes_job_and_trial_not_input`; `test_completed_battle_normalizes_presented_slots`; `test_noncompleted_records_have_no_semantic_result_or_vote`; `test_attempt_history_does_not_change_semantic_digest`; `test_pairwise_fold_fixture`; `test_completion_policy_counts_and_eligibility`; `test_rubric_record_fold_and_all_invalid` |
| `test_gdpval_evaluator.py` | `test_binary_completed_result_shape`; `test_structured_completed_result_matches_legacy_math`; `test_structured_partial_result_retains_invalid_attempts`; `test_pairwise_completed_result_shape`; `test_pairwise_invalid_response_is_not_tie`; `test_cardinality_and_view_bundle_coherence_fail_before_calls`; `test_av_insufficiency_fails_before_calls`; `test_all_judges_failed_has_no_result`; `test_interruption_preserves_attempt_history`; `test_plan_saved_before_call_and_reuse_revalidates`; `test_runtime_request_is_anonymous_and_has_no_fallback` |
| `test_gdpval_judge_runtime_v2.py` | `test_codex_preflight_environment_is_provenance_free`; `test_claude_preflight_fails_without_read_probe`; `test_safe_temp_root_is_disjoint_from_all_protected_roots`; `test_temp_overrides_do_not_copy_parent_paths`; `test_blind_role_argv_and_settings_reject_ordinary_executor_policy`; `test_outside_read_probe_and_protected_runtime_allowance_fail_closed`; `test_http_runtime_receives_only_anonymous_payload`; `test_terminal_runtime_evidence_is_typed_and_never_falls_back` |
| `test_evaluator_registry.py` | retain `test_native_evaluator_versions_and_assets_are_advertised`; rename the GDPval case to `test_gdpval_descriptors_are_concrete_and_have_no_default_judge` |

The cases collectively assert every exact current/revised output in the characterization file, the three golden identity values above, both completion policies, no-vote invalid responses, all-judge failure, AV insufficiency before calls, explicit four-trial A-first order, explicit member plans, occurrence separation, semantic/history digest separation, immutable source bytes, and anonymous prompt/workspace/payload/argv/environment. The eight runtime cases include the four existing `test_local_judge_isolation.py` meanings plus argv/settings inspection, failed outside-read probe, protected-root rejection, and HTTP payload/no-fallback isolation.

From a clean accepted implementation checkout with the locked environment:

```bash
uv sync --locked --extra dev
uv run --no-sync pytest -q \
  tests/harness/test_gdpval_scoring_v2.py \
  tests/harness/test_gdpval_presentation_v2.py \
  tests/harness/test_gdpval_panel_v2.py \
  tests/harness/test_gdpval_records_v2.py \
  tests/harness/test_gdpval_evaluator.py \
  tests/harness/test_gdpval_judge_runtime_v2.py \
  tests/harness/test_evaluator_registry.py
```

Expected: exit code 0, `53 passed`, zero failed/error/skipped/xfailed/xpassed, zero network/model/provider calls, and no source/bundle/snapshot mutation. Then run the exact baseline protection regression:

```bash
uv run --no-sync pytest -q \
  tests/harness/test_pairwise_evaluator.py \
  tests/harness/test_local_judge_pairwise.py \
  tests/harness/test_local_judge_runner_control.py \
  tests/harness/test_local_judge_isolation.py
```

Expected on the characterized baseline set: exit code 0 and `22 passed`; when an accepted dependency legitimately adds cases, every collected case must pass and the work record states the new count. None may be deleted or weakened to preserve `22`.

## Full unchanged gates on the exact implementation head

Focused success is not acceptance. The commands below are transcribed from `.github/workflows/eval-harness-ci.yml` at source commit `d5ce0c10162cad788a17cb90f34b8f60574e7f75`, file SHA-256 `cb731754d3981155b80a43aebb4b91496c767cfd745408a183966947c5813048`. Recheck and use the accepted implementation base's unchanged workflow if that file hash differs. Run the gates on the exact promoted head using uv 0.11.29 and Python 3.13.14:

1. `uv sync --locked --extra dev` succeeds without changing `uv.lock`.
2. `uvx --from "pre-commit==4.3.0" pre-commit run --all-files --show-diff-on-failure` exits 0; this includes Ruff lint/format and repository hooks. No hook or ignore is weakened.
3. Run the workflow's subprocess-aware sequence unchanged: `coverage erase --rcfile=config/eval-harness-coveragerc`; `coverage run --rcfile=config/eval-harness-coveragerc scripts/ci/run_eval_harness_coverage.py`; `coverage combine --rcfile=config/eval-harness-coveragerc`; `coverage json --rcfile=config/eval-harness-coveragerc --pretty-print -o ci-artifacts/harness-tests/coverage.json`; `uv run --no-sync python scripts/ci/run_eval_harness_coverage.py --check-summary ci-artifacts/harness-tests/coverage.json`; and `coverage report --rcfile=config/eval-harness-coveragerc`. Expected output includes `gdpval harness self-test passed` and `coverage guard passed: X/Y statements meet the exact 96% threshold`, with integer `X * 100 >= Y * 96`.
4. `uv run --no-sync mypy --strict --explicit-package-bases --show-error-codes eval_harness tests/harness scripts/gdpval_run_metadata.py scripts/ci/run_eval_harness_coverage.py scripts/update_env_list.py tests/test_update_env_list.py tests/unit_tests/test_update_env_list.py tests/unit_tests/test_hf_utils.py` exits 0 with no errors.
5. These exact dependency-compatibility and environment-inventory commands both exit 0:

   ```bash
   uv run --no-sync pytest \
     tests/unit_tests/test_hf_utils.py \
     tests/unit_tests/test_dataset_source.py \
     tests/unit_tests/test_dataset_orchestrator.py \
     tests/unit_tests/test_server_utils.py
   uv run --no-sync pytest \
     tests/test_update_env_list.py \
     tests/unit_tests/test_update_env_list.py
   ```

6. Run the workflow's exact export, scope, and audit logic. The export and every scope assertion exit 0; the pinned audit reports no unhandled vulnerability. No dependency or lock change is expected for this slice.

   ```bash
   uv export --locked --extra dev --no-emit-project \
     --output-file ci-artifacts/dependency-audit/requirements.txt
   requirements=ci-artifacts/dependency-audit/requirements.txt
   ! grep -Ev '^[[:space:]]*(#|$)' "${requirements}" \
     | grep -Ein '(^|[[:space:]])(-e[[:space:]]+)?(\./|\.\./|/|file:|workspace:)'
   ! grep -Eiq '^nemo-gym([<=>!~]|$)' "${requirements}"
   for package in openai pre-commit pytest ruff anyio; do
     grep -Eiq "^${package}([<=>!~]|$)" "${requirements}"
   done
   uvx --from "pip-audit==2.10.1" pip-audit \
     --require-hashes \
     --disable-pip \
     --strict \
     --format json \
     --aliases \
     --output ci-artifacts/dependency-audit/pip-audit.json \
     --requirement ci-artifacts/dependency-audit/requirements.txt
   ```
7. Formal PR checks for copyright, secrets, DCO sign-off, lint, strict typing, tests, and coverage all pass on that same head. Every new source/test file retains NVIDIA SPDX. No workflow, coverage threshold, audit rule, secret baseline, or required check changes.

Record exact commands, head/tree, counts, and decisive outputs in `contracts/pr06-gdpval-implementation-work-record.md`. A later head invalidates the validation claim and reruns the affected gates.

## Completion conditions and prohibitions

PR06 is complete only when the common runner selects each explicit evaluator ID, validates and saves its complete plan before calls, invokes only fake adapters in tests, persists attempt intent and terminal evidence immediately, returns the result shapes above, and passes every focused/full gate. `eval_harness/evaluators/gdpval.py` no longer reports successful external handoff for these modes. Existing old paths remain only as read-only characterization sources for scheduled PR10 removal and are never imported/called as fallback.

Do not run a real model, paid API, subscription-backed judge, or GitHub Action for a checkpoint. Do not modify source CandidateBundles or snapshots; put derived presentation and evidence in fresh roots. Do not pass TaskSpec evaluation data, candidate/model/condition identity, credentials, or unrestricted environment to a judge. Do not synthesize tie/zero/loss/success for invalid, truncated, missing, unsupported, all-failed, zero-trial, or interrupted work. Do not add AA-v2 stage/anchor/Elo/headline logic, Builder/Stirrup generation logic, benchmark path discovery, vendor transport duplication, silent fallback, compatibility wrappers, new dependencies, or unrelated refactors.

Any contract conflict, missing PR05 capability, extra path, prompt/parser change, completion-policy change, or cross-PR responsibility change returns to Sol. Only a migration-wide policy change escalates to Astra. Checkpoint through direct UTF-8 GitHub blob/tree/commit APIs with DCO, move the scoped branch without force, and read back the ref/commit/files. Do not update the control branch, open a PR, dispatch Actions, use Base64, or use `git push` during the implementation checkpoint.
