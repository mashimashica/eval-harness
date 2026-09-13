<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR-05 independent evaluation and common runner contract

**State:** reconstructed design contract, ready for dependency-SHA substitution and implementation review. This document is not implementation, validation, or acceptance evidence.

## Authority, base, and purpose

The authority is the canonical migration plan saved at control commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, file `eval-harness-neutrality-migration-plan-2026-09-12.md`, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`. The source APIs inspected for this design are the immutable PR-03 head `d5ce0c10162cad788a17cb90f34b8f60574e7f75`, tree `354943ebbb8ea81a30523bfdc12baf26771853b5`, plus the accepted PR-01/02a/02b/03 public contracts and the accepted PR-02c reconstruction contract.

The PR-05 implementation base must be the exact accepted PR-04 head, descending the exact accepted PR-02c head. Those two implementation SHAs do not yet exist as accepted heads and are the only unresolved implementation-input decision. Luna must not begin PR-05 source edits until the work record substitutes both full SHAs, verifies ancestry, and reads the dependency files back. This contract does not treat the current PR-02c work-in-progress checkpoint `4948b2c3f85ca82d94e44734de532c8769d7b04e` as accepted.

PR-05 makes evaluation a first-class operation over a verified `BoundEvaluationView` and sealed `CandidateBundle` values. It separates evaluator identity from benchmark defaults, adds explicit unary/pairwise/N-candidate planning, persists evaluation plans/attempts/results, supports strict reevaluation after runtime deletion, and supplies the minimal generation seam needed by PR-09 to reuse one snapshot and delay evaluation until a comparison group is sealed.

PR-05 also makes the existing AIME native evaluator a real locked CI dependency and validates its actual no-model verifier behavior. It consumes the PR-04 BigCode grader boundary without weakening or duplicating it. PR-06 owns GDPval rubric/pairwise projection, prompts, parsers, panel semantics, trial positions, completion policy, and `BattleRecord`; PR-08 owns AA-v2 stages/anchors/Elo; PR-09 owns Builder/N-S-A group planning and its experiment journal; PR-10 removes the old routes and records.

## Allowed implementation paths

Luna may change only these paths. A need outside this list returns to Sol for a contract amendment.

- `eval_harness/benchmarks/registry.py`
- `eval_harness/cli.py`
- `eval_harness/evaluation_records.py` (new)
- `eval_harness/evaluation_runner.py` (new)
- `eval_harness/execution_policy.py` (new)
- `eval_harness/generation_runner.py` (new)
- `eval_harness/failures.py`
- `eval_harness/runner.py`
- `eval_harness/evaluators/__init__.py`
- `eval_harness/evaluators/base.py`
- `eval_harness/evaluators/registry.py`
- `eval_harness/evaluators/aime26.py`
- `eval_harness/evaluators/bigcodebench.py`, only for adapting the accepted PR-04 evaluator to the common job/result envelope
- `eval_harness/evaluators/exact.py`
- `eval_harness/evaluators/pairwise.py`, only to remove replaced generic planning/transport behavior or adapt deterministic fixtures; no GDPval semantics
- `eval_harness/interventions/registry.py`, only for descriptors/listing
- `eval_harness/judge_runtime.py` (new)
- `eval_harness/judges/__init__.py`
- `eval_harness/judges/base.py`
- `eval_harness/judges/codex.py`
- `eval_harness/judges/claude_code.py`
- `eval_harness/run_manifest.py`, only to add the strict append-only `RunResultWriter.resume` capability specified below; no schema or reader fallback change
- `pyproject.toml`
- `uv.lock`
- `resources_servers/math_with_judge/requirements.txt`
- `.github/workflows/eval-harness-ci.yml`
- `tests/harness/test_eval_cli.sh`
- existing `tests/harness/test_*evaluator*.py`, `test_*runner*.py`, `test_*registry*.py`, and `test_local_judge*.py` files whose assertions exercise a changed contract
- `tests/harness/test_aime26_benchmark.py`
- `tests/harness/test_bigcodebench_benchmark.py`
- `tests/harness/test_boundary_failure_coverage.py`, only for assertions over the changed evaluation/failure boundary
- `tests/harness/test_executor_judge_reliability.py`, only for the shared guarded-runtime assertions
- `tests/harness/test_local_judge_executor.sh`
- `tests/harness/test_run_manifest.py`, only for the strict writer-resume cases
- new `tests/harness/test_evaluation_runner.py`
- new `tests/harness/test_evaluation_records.py`
- new `tests/harness/test_execution_policy.py`
- new `tests/harness/test_generation_runner.py`
- new `tests/harness/test_registry_extension.py`
- deterministic fixture files below `tests/harness/fixtures/evaluation/`

No PR-04 sandbox policy/launcher file, benchmark adapter, executor adapter, CandidateBundle/Snapshot/RunManifest schema, experiment/profile/Builder source, GDPval resource/prompt/parser, AA-v2 source, documentation, old entrypoint, or coverage/audit threshold is in scope.

## Frozen common types and canonical JSON

`eval_harness.evaluation_runner` defines `JSONValue` as the recursive strict JSON value type accepted by these records. Canonical values allow `None`, exact booleans, exact integers, finite floats, UTF-8 strings, ordered tuples, and mappings with non-empty UTF-8 string keys. Construction deep-freezes mappings/sequences; serialization rejects duplicate keys, NaN/infinity, non-string keys, subclasses that can change serialization, and unknown schema fields. Digests use the accepted canonical JSON serializer with sorted object keys, compact separators, UTF-8, and a trailing newline only for JSONL records.

The existing shared `Failure` type and CandidateBundle serialization do not change. Add exactly `FailureKind.INVALID_RESPONSE = "invalid_response"`; unlike `PROTOCOL`, it is not forced to `FailureImpact.RUN`. Runtime/envelope protocol faults remain `PROTOCOL/RUN`. A judge's semantically malformed response uses `INVALID_RESPONSE/TASK` and a precise stable parser code such as `empty_response` or `truncated_json`.

```python
@dataclass(frozen=True, slots=True)
class EvaluationFailure:
    failure: Failure
    retryable: bool

@dataclass(frozen=True, slots=True)
class EvaluationResumePolicy:
    max_attempts_per_job: int
    retry_interrupted: bool
    retryable_failures: tuple[Failure, ...]
    resume_skipped_after_retryable_run_stop: bool
    configuration_sha256: str = field(init=False)
```

At the evaluation boundary `FailureImpact.TASK` means one trial/job can be isolated; `RUN` stops remaining jobs. `EvaluationFailure` validates an exact `Failure`, an exact bool, and stable secret-free codes. It is the only per-result retryability field. `EvaluationResumePolicy` validates an exact positive attempt bound, exact booleans, and a sorted duplicate-free tuple of exact stable `Failure` rules, then computes its canonical configuration digest. It is part of the evaluator's strict canonical configuration and is also persisted independently by the record sink. A result can advance on explicit resume only when both its own retryable bit and this exact stored policy permit it; the policy never upgrades `retryable=False`.

## Extensible benchmark and evaluator registration

Benchmark lookup and evaluator lookup become independent registries. `EvaluatorRegistry` is keyed only by exact evaluator ID. It never accepts a benchmark name as an evaluator alias and never falls back to another evaluator.

```python
@dataclass(frozen=True, slots=True)
class EvaluatorDescriptor:
    evaluator_id: str
    evaluator_type: EvaluatorType
    version: str | None
    revision: str | None
    candidate_count: int                 # exactly 1 or 2
    requires_judge_runtime: bool
    status: str
    requirements: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()
    isolation_requirement: str | None = None

type EvaluatorFactory = Callable[[Mapping[str, JSONValue]], Evaluator]

class EvaluatorRegistry:
    def register(self, descriptor: EvaluatorDescriptor, factory: EvaluatorFactory) -> None: ...
    def descriptor(self, evaluator_id: str) -> EvaluatorDescriptor: ...
    def create(self, evaluator_id: str, config: Mapping[str, JSONValue]) -> Evaluator: ...
    def list(self) -> tuple[EvaluatorDescriptor, ...]: ...
```

Registration rejects duplicate/case- or Unicode-colliding IDs. `create` deep-validates the config, invokes exactly the registered factory, and requires the returned evaluator's ID, type, version, revision, cardinality, runtime requirement, canonical configuration, and `configuration_sha256` to match the descriptor/request. Factories are config-only: output roots, runtime instances, auth values, snapshots, bundles, and sinks are never captured in them.

`BenchmarkDescriptor` gains `default_evaluator_id: str | None`; benchmark factories live in an equivalently injectable `BenchmarkRegistry`. A default is only a reference to an exact evaluator ID and is validated against the selected evaluator registry before preparation. A benchmark may have no default. A native default cannot silently change to a judge evaluator. GDPval has no selectable default until PR-06 registers its completed evaluator; execution therefore requires explicit `--execution-only` in this stage. The old `gdpval-external` implementation may remain physically present until PR-06, but the new registry/runner must not select it or accept its `external` result as completed evaluation.

The default registry contains AIME `aime26-native` and BigCode `bigcodebench-tests` under their exact IDs. Module-level create/list functions may delegate to the default registry as the primary API, but benchmark-key aliases and compatibility lookup loops are removed. Tests use fresh registry instances; they do not mutate global registries or monkeypatch orchestration.

`./eval benchmarks`, `executors`, `evaluators`, `interventions`, and `profiles` are distinct list categories. PR-05 implements truthful benchmark/evaluator/intervention listings. `profiles` is a stable empty category until PR-08/09 register concrete profiles; it must not advertise the legacy file-path experiment as a completed registered profile.

## Shared generation seam

`eval_harness.generation_runner` extracts the one-candidate generation operation from the accepted PR-02c runner. It never imports an Evaluator, Benchmark implementation, Builder, experiment profile, or benchmark-specific adapter.

```python
@dataclass(frozen=True, slots=True)
class ApplicationSpec:
    executor_id: str
    requested_model: str | None
    reasoning_effort_requested: ReasoningEffortOption
    timeout_seconds: float
    network_access_enabled: bool
    environment_allowlist: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class CandidateGenerationRequest:
    generation_occurrence_id: str
    snapshot_reference: SnapshotReference
    intervention: Intervention

@dataclass(frozen=True, slots=True)
class GenerationPlan:
    application: ApplicationSpec
    ordered_tasks: tuple[SnapshotReference, ...]
    candidates: tuple[CandidateGenerationRequest, ...]

@dataclass(frozen=True, slots=True)
class GenerationOccurrenceBinding:
    sequence: int
    generation_occurrence_id: str
    snapshot_reference: SnapshotReference
    intervention_id: str
    intervention_type: InterventionType
    intervention_bundle_sha256: str
    intervention_manifest_sha256: str

@dataclass(frozen=True, slots=True)
class GenerationPlanRecord:
    run_id: str
    run_fingerprint_sha256: str
    application: ApplicationSpec
    ordered_tasks: tuple[SnapshotReference, ...]
    occurrences: tuple[GenerationOccurrenceBinding, ...]
    generation_semantics_sha256: str
    generation_plan_record_sha256: str

class BoundGenerationPlan:  # token-constructed capability; caller cannot instantiate it
    @property
    def record(self) -> GenerationPlanRecord: ...

@dataclass(frozen=True, slots=True)
class GeneratedCandidate:
    generation_occurrence_id: str
    result_row: RunResultRow
    bundle: CandidateBundle

@dataclass(frozen=True, slots=True)
class GenerationResume:
    bound_plan: BoundGenerationPlan
    completed: tuple[GeneratedCandidate, ...]
    remaining_occurrence_ids: tuple[str, ...]

def prepare_generation_plan(
    plan: GenerationPlan,
    *,
    snapshot_binding: VerifiedSnapshotBinding,
    executor: Executor,
    run_root: Path,
    environment: Mapping[str, str],
    runtime_root: Path | None = None,
) -> BoundGenerationPlan: ...

def resume_generation_plan(
    plan: GenerationPlan,
    *,
    snapshot_binding: VerifiedSnapshotBinding,
    executor: Executor,
    run_root: Path,
    environment: Mapping[str, str],
    runtime_root: Path | None = None,
) -> GenerationResume: ...

def generate_candidate(
    plan: BoundGenerationPlan,
    generation_occurrence_id: str,
) -> GeneratedCandidate: ...

def run_generation_plan(plan: BoundGenerationPlan) -> tuple[GeneratedCandidate, ...]: ...
```

`ApplicationSpec` contains only semantic application configuration. It rejects non-finite/non-positive timeout, a non-bool network value, invalid reasoning effort, a mismatched executor, and unsafe/duplicate environment names. `environment` keys must equal the ordered allowlist as a set; its values are operational, repr-excluded, and never serialized or hashed. The exact same application mapping is used for every occurrence in one plan. Passing `dict(os.environ)` or adding arm/condition/profile keys is forbidden. Runtime paths, auth values, result-derived model/effort, timestamps, run/occurrence IDs, benchmark/arm/condition labels, and environment values are excluded.

`prepare_generation_plan` accepts an already published, fully verified `run_root/snapshot`; it must prove that the binding root is exactly `run_root / "snapshot"` and that no run manifest, result index, or candidate namespace already occupies the generation paths. It does not call `Benchmark.prepare`, `load_tasks`, `acquire_snapshot`, or materialize through an adapter. It resolves every unique `ordered_tasks` entry and every candidate reference, requires each candidate reference to occur in `ordered_tasks`, rejects duplicate/colliding occurrence IDs, and validates the executor preflight/capabilities/config, the exact role-scoped environment-key set, plus every intervention preflight/manifest/task/source-output separation and deterministic destination before an executor call. `ExecutionRequest.environment` receives only the supplied mapping. Vendor subscription-environment filtering is defense in depth and does not make an ambient mapping acceptable.

After all validation, it generates one new `run_id` with `secrets.token_hex(16)`, creates the sole authoritative `RunResultWriter`, writes the accepted `RunManifest` exclusively against that exact snapshot binding, and prepares candidate/runtime directories without following symlinks. It also exclusively writes exactly `run_root / "generation-plan.json"` as canonical `GenerationPlanRecord` schema/version 1. Existing reserved output files, candidate paths, or overlapping snapshot/out/runtime/intervention roots reject the plan. Other controller-owned files in an experiment root are allowed only outside all reserved generation paths.

Sequence is plan order. The exact PR-02c identity and path remain `candidate_id = f"{run_id}:candidate-{sequence:08d}"` and `candidates/candidate-{sequence:08d}`. `generation_occurrence_id` is an opaque outer join key. Its raw value appears only in the immutable generation-plan controller record, `GeneratedCandidate`, and the caller's journal; it never enters `RunManifest.configuration`, candidate ID/path/content, TaskSpec/prompt/environment/workspace, or evaluator projection.

The record carries two deliberately different digests. `generation_semantics_sha256` hashes a domain/schema/version plus the exact `ApplicationSpec`, ordered snapshot references, and ordered candidate snapshot/intervention ID/type/bundle/manifest identities; it excludes `run_id`, every `generation_occurrence_id`, roots, environment values, attempts, and runtime evidence. Only this semantic digest enters `RunManifest.configuration` and therefore its run fingerprint. `generation_plan_record_sha256` hashes the complete canonical controller record except its own field, including `run_id`, the manifest's run fingerprint, sequence, and opaque occurrence IDs. PR-08/09 journals bind that full record digest. Changing only run/occurrence IDs leaves generation semantics, manifest configuration, and run fingerprint unchanged while changing the full controller-record digest.

`generate_candidate` may execute only the next remaining prevalidated occurrence once. It materializes only `VerifiedSnapshotBinding.materialize_execution`, applies the exact preflighted intervention, executes the stored executor, validates all typed identity/path/capability/evidence invariants, seals the CandidateBundle, appends/fsyncs its `RunResultRow`, and returns only after the row is durable. A second call, out-of-plan ID, out-of-order call, invalid result, seal error, or append error fails; it never fabricates a row/bundle or calls an evaluator. `run_generation_plan` invokes the remaining suffix in plan order and returns the full ordered set, including an already verified prefix on a resumed bound plan.

`resume_generation_plan` is the only reopen path. It requires the existing canonical manifest, `generation-plan.json`, snapshot, result index, and indexed bundles; reruns executor/intervention preflight without model work; reconstructs the expected record from the supplied immutable plan; and requires exact record, semantic/config/run-fingerprint, environment-key, executor, intervention, and binding equality. It calls `load_run_results` and requires every row/bundle to equal the corresponding leading occurrence by exact sequence, derived candidate ID/path, snapshot reference, intervention evidence, application/executor semantics, and digest. The candidates directory must contain exactly the indexed prefix and no orphan, temporary, symlinked, partial, or unindexed entry.

The narrow `eval_harness.run_manifest.RunResultWriter.resume(path, *, expected_rows: tuple[RunResultRow, ...]) -> RunResultWriter` amendment rereads a canonical contiguous index, requires byte-for-byte equality with `expected_rows`, captures a stable file identity/seal, restores next sequence/candidate/path sets, and appends without rewriting old bytes. It rejects empty-line/truncated/noncanonical content, a changed file between verification and seal, duplicates, path overlap, or a nonregular/symlinked file. It does not load bundles, infer rows, truncate, repair, or create an alternate index.

The returned `GenerationResume.completed` is the exact verified prefix and `remaining_occurrence_ids` is the exact suffix in plan order. When work remains, `runtime_root` must name a fresh absent root; an old runtime is never read, deleted, or reused. A fully complete plan may reopen without creating runtime. An indexed task-impact failed candidate remains a completed occurrence and may permit later plan entries; an indexed interruption or run-impact failure preserves the stop and forbids suffix execution. A crash before a complete index append, a truncated index, or an orphan/partial next candidate fails closed without deletion; recovery then requires a fresh run root. This slice does not overwrite or retry an already indexed generation occurrence.

PR-09 uses one experiment-level `GenerationPlan` and one RunManifest/index for its one shared snapshot. After its Builder phase, `candidates` contains N and every S/A occurrence whose intervention is ready; missing Builder outcomes remain in the outer experiment denominator. All ready candidates are generated before any complete group is passed to evaluation. This permits partial candidate evidence without per-group writers and never reacquires task data.

PR-08 orders its one adaptive plan by stable first appearance over `stage0_order + stage1_order`: all 45 formal stage-0 task/repeat occurrences first, followed by the 175 stage-1 occurrences absent from stage 0. Stage 0 therefore generates exactly the prefix; after its verified aggregate, stage 1 reuses those candidates wherever they recur and generates unseen tasks in the remaining-plan order. Anchor/job/trial expansion may remain adaptive because it is outside generation identity. PR-09 already knows its complete ready-candidate order after the Builder phase and resumes the same way.

This seam proves path freshness/separation and exact environment delivery; it does not claim that an ordinary local Executor cannot read a disjoint sibling/root. PR-09 must use its fail-closed `ExperimentExecutionPolicy` capability/preflight and may advertise only executors that enforce the declared Builder/application role roots. PR-09 makes local Codex eligible only through the common root-deny writable-workspace policy and a passing production-equivalent no-model probe. PR-07 contained Stirrup is the other accepted protected route. Claude and Cursor remain ineligible for experiment roles until an equivalent declared probe succeeds. This restriction does not alter ordinary non-experiment `./eval run` support.

The refactored `run_benchmark` uses this seam. It first acquires and binds one snapshot through the accepted PR-02c staging/publication lifecycle, then generates the entire plan. If evaluation is requested, it plans/dispatches only after all candidates have sealed and been reloaded from `RunManifest` + `VerifiedSnapshotBinding` + `load_run_results`. Execution-only performs no evaluator or judge preflight/call and never labels the run evaluated.

## Evaluation identity and planning

The public logical reference and job are exact:

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
```

`logical_candidates` has exactly one or two entries in caller-supplied semantic order. IDs are distinct. Every CandidateBundle must be strictly reloaded against the same `VerifiedSnapshotBinding`; its exact snapshot reference, task ID, canonical prompt/hash, candidate ID, bundle digest, manifest, and blobs must still verify and match the one `BoundEvaluationView`.

The sole identity constructor is:

```python
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
```

It deep-freezes `evaluator_plan`, computes its digest, and computes the following two domain-separated hashes. Tests pin the exact canonical bytes and golden SHA-256 values; no evaluator/profile reimplements them.

- `evaluation_input_sha256` covers schema/version/domain, `snapshot_reference`, `evaluation_view_sha256`, ordered `{candidate_id,bundle_sha256}` entries, `evaluator_id`, `evaluator_revision`, and `evaluator_config_sha256`.
- `evaluation_job_id` covers schema/version/domain, `evaluation_input_sha256`, and opaque `match_occurrence_id`.

The input hash excludes occurrence, evaluator plan, timestamps, attempts, paths, runtime/auth evidence, stage/anchor/profile/arm labels, and raw judge data. The job ID excludes `evaluator_plan_sha256` by design. Reusing one job ID with a different plan hash is therefore a hard occupied-output conflict, never a second meaning for the same occurrence. Equal content with a different occurrence produces a different job and fresh trials. Equal occurrence/content with exact plan may resume after complete integrity revalidation.

```python
@dataclass(frozen=True, slots=True)
class EvaluationPlanRequest:
    view: BoundEvaluationView
    candidates: tuple[CandidateBundle, ...]
    match_occurrence_id: str

def plan_evaluation_job(
    evaluator: Evaluator,
    *,
    match_occurrence_id: str,
    view: BoundEvaluationView,
    candidates: tuple[CandidateBundle, ...],
) -> EvaluationJob: ...
```

`plan_evaluation_job` checks the evaluator's exact cardinality/config identity, calls `evaluator.plan(EvaluationPlanRequest) -> Mapping[str, JSONValue]`, then delegates identity only to `build_evaluation_job`. Concrete evaluators own their resolved plan content and semantic validation; they do not own common input/job identity.

For N supplied candidates, planning is always explicit:

```python
@dataclass(frozen=True, slots=True)
class EvaluationMatchSpec:
    match_occurrence_id: str
    candidate_ids: tuple[str, ...]

class MatchPlanner:
    @staticmethod
    def plan(
        evaluator: Evaluator,
        *,
        view: BoundEvaluationView,
        candidates: tuple[CandidateBundle, ...],
        matches: tuple[EvaluationMatchSpec, ...],
    ) -> tuple[EvaluationJob, ...]: ...
```

Each match has exactly the selected evaluator's cardinality. Occurrence IDs are unique, pairwise IDs are distinct, every ID resolves exactly once, and all content checks occur before the first evaluator/judge call. The planner preserves supplied match and candidate order. It never invents all-pairs, baseline, anchor, reversal, repeat, or stage rules and never silently changes a pairwise plan to unary.

## Evaluator and result envelope

Concrete evaluator constructors take only their strict semantic config. The base exposes exact identity/config/cardinality properties, retains `preflight(run_dir) -> EvaluatorPreflightResult` for the accepted PR-04 boundary, and adds:

```python
def judge_runtime_preflight_requests(
    self,
    view: BoundEvaluationView,
) -> tuple[JudgeRuntimePreflightRequest, ...]: ...

@property
def resume_policy(self) -> EvaluationResumePolicy: ...

def plan(self, request: EvaluationPlanRequest) -> Mapping[str, JSONValue]: ...
def evaluate(self, request: EvaluationJobRequest) -> EvaluationResult: ...
def aggregate(self, request: EvaluationAggregateRequest) -> EvaluationAggregate: ...
```

The default judge-preflight hook returns empty. A judge evaluator returns one request for every configured member that could be selected for the bound view. Every request must pass; the runner never removes a failed member and resamples a different panel. Candidate-artifact capability filtering occurs later in `plan` against that exact preflighted panel and rejects an insufficient panel before a judge invocation.

`EvaluationResult` remains the one public type `eval_harness.evaluators.base.EvaluationResult`; PR-05 does not introduce an alias or second result type. Its exact extended envelope is:

```python
@dataclass(frozen=True, slots=True)
class EvaluationResult:
    evaluation_job_id: str
    task_id: str
    status: EvaluationStatus
    failure: EvaluationFailure | None = None
    metrics: Mapping[str, float] = field(default_factory=dict)
    outcomes: Mapping[str, JSONValue] = field(default_factory=dict)
    details: Mapping[str, JSONValue] = field(default_factory=dict)
```

The new-run `EvaluationStatus` literals are exactly `completed`, `partial`, `failed`, `interrupted`, `invalid`, and `skipped`. The staged `external` member may exist only for the old GDPval class until PR-06 and is rejected by all new runner/sink/aggregate paths; `deferred` is not a supported alias in the new contract. Evaluators echo `EvaluationJobRequest.job.evaluation_job_id` exactly.

An `EvaluationResult` binds `evaluation_job_id`, task ID, status, metrics, outcomes, semantic details, and `EvaluationFailure | None`. Mappings are deep-frozen strict JSON; metric values are finite. `completed` alone requires `failure is None`. `partial` requires a non-retryable task-impact summary failure and may contain metrics only when the evaluator's hash-bound plan names a `valid_only` threshold and the recorded valid count satisfies it; precise trial failures remain in evaluator-owned trial records. `failed`, `interrupted`, `invalid`, and `skipped` require a failure and contain no metrics. Interrupted requires kind `INTERRUPTED`; skipped copies the stable causal stop classification and retryability without manufacturing evaluator output. Raw judge output, reasoning, timestamps, attempts, absolute paths, auth/env data, and prior failures are not semantic details.

The PR-04 BigCode mapping is preserved exactly. Completed outcomes use only `native_status` values `passed`, `failed_tests`, `empty_output`, `no_code_block`, `candidate_timeout`, and `candidate_resource_limit`, with optional stable `limit_kind`; their only metric is `pass_rate`. Preflight/result provenance keeps `dataset_revision`, `grader_version`, `grader_source_commit`, `grader_lock_sha256`, `sandbox_version`, and `sandbox_policy_revision` as independent secret-free fields. `GraderInfrastructureError` and grader unavailable/launch/dependency/protocol/unknown-status faults become `failed`, empty metrics/outcomes, stable phase/type/failure, and a run stop. A failed CandidateBundle bypasses the evaluator and is `skipped` with no metric. Infrastructure is never score zero.

AIME uses the real `math-verify==0.8.0` library only, never its LLM fallback. Correct, wrong, empty/no-deliverable results are completed with exact named `accuracy` semantics. Import/version/verifier-shape/runtime infrastructure faults are failed with no metric and stop; they are never converted to `accuracy=0`.

Aggregation is evaluator-owned and pure. `EvaluationAggregate` records evaluator ID/revision/config hash, planned and per-status job counts, named metrics with explicit numerator/denominator where the evaluator defines them, structured outcomes, coverage, and a semantic digest. The common runner validates count/digest coherence and groups outputs; it never averages arbitrary metric maps. AIME and BigCode retain separate `accuracy` and `pass_rate` values and denominators. Pairwise outcome aggregation remains PR-06/08 and no generic Elo or universal score is added.

## Blind judge runtime boundary

PR-05 first extracts the root-deny policy construction and no-model proof from the existing Codex judge so PR-09 can apply the same verified mechanism to a writable Builder/application role without copying a sandbox implementation:

```python
class WorkspaceAccess(StrEnum):
    READ_ONLY = "read-only"
    READ_WRITE = "read-write"

@dataclass(frozen=True, slots=True)
class RootDenyRolePolicy:
    policy_revision: str
    workspace_access: WorkspaceAccess
    network_access_enabled: bool
    web_search_enabled: bool
    environment_allowlist: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class RolePolicyRequest:
    policy: RootDenyRolePolicy
    workspace: Path
    protected_roots: tuple[Path, ...]
    runtime_read_paths: tuple[Path, ...]
    environment: Mapping[str, str]

@dataclass(frozen=True, slots=True)
class RolePolicyPreflightResult:
    ok: bool
    policy_revision: str
    details: tuple[str, ...]

def build_role_environment(request: RolePolicyRequest) -> dict[str, str]: ...
def build_codex_role_overrides(request: RolePolicyRequest) -> tuple[str, ...]: ...
def probe_codex_role_policy(command: str, request: RolePolicyRequest) -> RolePolicyPreflightResult: ...
```

These exact primitives live in `eval_harness.execution_policy`. They require canonical nonoverlapping roots; reject any allowed runtime path that overlaps a protected root; require environment keys to equal the policy allowlist; construct root-deny plus only minimum runtime-read and exact workspace access; preserve explicit network/web settings; and run the same production config through a non-model command that reads a randomized allowed sentinel and fails to read a randomized protected sentinel. Evidence contains policy/version/result facts but no environment values or sentinel bytes. `READ_WRITE` changes only the workspace grant; it never grants a sibling/root. Building a config without a passing probe is not capability proof.

`BlindJudgePolicy` contains a `RootDenyRolePolicy` fixed to `READ_ONLY`, network false, and web false. Its runtime delegates environment/config/probe behavior to these functions. PR-09 later owns `ExperimentExecutionPolicy`, exact Builder/application protected roots, and the Codex `READ_WRITE` use/tests; it must reuse these primitives. PR-07 Stirrup proves the same role-boundary semantics through its contained execution rather than Codex TOML. Claude/Cursor remain ineligible for protected experiment roles until a declared equivalent probe succeeds.

`eval_harness.judge_runtime` is an injectable one-attempt transport. It does not parse rubric/verdicts, select panels, construct matchups, reverse candidates, aggregate, discover datasets, or know GDPval/AA/profile labels.

The exact transport records are:

```python
class JudgeRuntimeStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

@dataclass(frozen=True, slots=True)
class BlindJudgePolicy:
    root_policy: RootDenyRolePolicy
    max_output_bytes: int

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
class JudgeRuntimePreflightRequest:
    member: JudgeRuntimeMember
    policy: BlindJudgePolicy
    protected_roots: tuple[Path, ...]
    probe_workspace: Path
    required_capabilities: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class JudgeRuntimePreflightResult:
    member_id: str
    ok: bool
    runtime_version: str | None
    auth_mode: str | None
    capabilities: tuple[str, ...]
    policy_revision: str
    details: tuple[str, ...]
    evidence_sha256: str

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

@dataclass(frozen=True, slots=True)
class JudgeInvocationResult:
    trial_id: str
    status: JudgeRuntimeStatus
    output_bytes: bytes
    output_text: str
    exit_code: int | None
    started_at: str
    finished_at: str
    runtime_version: str | None
    auth_mode: str | None
    policy_revision: str
    evidence: Mapping[str, JSONValue]
    failure: EvaluationFailure | None

class JudgeRuntime(ABC):
    def preflight(self, request: JudgeRuntimePreflightRequest) -> JudgeRuntimePreflightResult: ...
    def invoke(self, request: JudgeInvocationRequest) -> JudgeInvocationResult: ...
```

Invocation result status is exactly `completed|failed|interrupted`; semantic invalid response is parsed by the evaluator as `INVALID_RESPONSE`, not a runtime protocol success. Completed has no runtime failure; failed/interrupted require one, and interruption preserves `INTERRUPTED`. All text, IDs, paths, MIME values, sizes, digests, time order, capability sets, and output bounds are strictly validated.

PR-06 owns richer presentation semantics, then materializes each attachment at its declared neutral safe POSIX `logical_path` below the fresh anonymous workspace and supplies the ordered `JudgeContentBlock` tuple. Before invocation the runtime requires exact workspace file-set equality and rereads every size/digest. A local CLI receives only that workspace and the evaluator-authored prompt containing its neutral references. An HTTP runtime constructs provider-native ordered text/file/image parts from those exact bytes and declared media types. Unsupported media or capability fails before a call; an advertised AV label without actual block delivery is invalid.

Requests carry a stable `trial_id`, the exact anonymous prompt/blocks/workspace, selected member runtime profile/model/reasoning/timeout, required capabilities, `BlindJudgePolicy`, and explicit protected roots. Operational auth/environment values live only inside the injected runtime profile; they are not request or semantic-record fields. Results carry bounded raw UTF-8/bytes, exit/status, timestamps, runtime/version/auth/policy/probe evidence, and only logical evidence paths plus sizes/digests. Subprocess decoding uses `errors="replace"`.

`BlindJudgePolicy` is not caller-weakenable. For a supported local CLI judge it requires root-deny reads; read access only to the anonymous workspace and minimum resolved CLI/runtime paths; protected snapshot, candidate, output, source, home, auth, and unrelated runtime roots unreadable; isolated HOME/TMP/cache; inherited environment reduced to a literal allowlist without candidate identities/labels/unrelated secrets; network and web search disabled; and writes limited to assigned runtime evidence. Preflight uses the production policy and a no-model probe proving the anonymous workspace readable and a randomized outside secret unreadable. It fails closed when this cannot be proved.

Refactor the existing Codex guarded judge transport to implement this boundary and the shared `execution_policy` primitives; do not create a second Codex CLI implementation. Claude judge preflight remains false even with accepted subscription auth because no documented non-model read-confinement probe exists. Ordinary unprobed `CodexExecutor` workspace-write is insufficient for blind judging. No test may replace actual path denial with prompt-only anonymity.

## Evaluation request and durable record sink

```python
@dataclass(frozen=True, slots=True)
class EvaluationJobRequest:
    job: EvaluationJob
    view: BoundEvaluationView
    candidates: tuple[CandidateBundle, ...]
    result_root: Path
    record_sink: EvaluationRecordSink
    judge_runtime: JudgeRuntime | None
```

Construction revalidates the view/job/candidate order, identity and content. A runtime is required exactly when the evaluator descriptor says so. The trusted evaluator receives the bound view and bundles; only its evaluator-owned anonymous projection reaches `JudgeRuntime`.

`eval_harness.evaluation_records.EvaluationRecordSink` is the sole evaluation plan/attempt/result store. Public constructors are `EvaluationRecordSink.create(result_root, *, resume_policy: EvaluationResumePolicy)` for a fresh root and `EvaluationRecordSink.resume(result_root, *, resume_policy: EvaluationResumePolicy)` for explicit resume. Both exclusively require the exact evaluator-owned policy whose canonical payload and digest are present in the evaluator configuration. Resume rejects a changed policy even when every job input is otherwise equal. Its operation names remain exactly:

```python
save_plan(job: EvaluationJob) -> None
append_attempt_started(record: EvaluationAttemptStarted) -> None
append_attempt_terminal(record: EvaluationAttemptTerminal) -> None
append_result(job: EvaluationJob, result: EvaluationResult) -> EvaluationJobRecord
load_job(
    job: EvaluationJob,
    *,
    view: BoundEvaluationView,
    candidates: tuple[CandidateBundle, ...],
) -> EvaluationJobRecord | None
```

Each job has an immutable canonical plan, append-only attempt history, immutable result revisions, and content-addressed evidence. The root has one append-only authoritative result index. `save_plan` for every planned job completes before the first evaluator call. Attempt-start is appended/flushed/fsynced before invocation; terminal evidence is appended/flushed/fsynced immediately after. `append_result` occurs only after terminal evidence for an invoked attempt, except that an unstarted `skipped` revision records a causal stop without inventing an attempt.

```python
@dataclass(frozen=True, slots=True)
class EvaluationResultRevision:
    revision: int
    attempt_number: int | None
    result: EvaluationResult
    previous_revision_sha256: str | None
    result_revision_sha256: str

@dataclass(frozen=True, slots=True)
class EvaluationJobRecord:
    job: EvaluationJob
    attempts: tuple[EvaluationAttemptRecord, ...]
    result_revisions: tuple[EvaluationResultRevision, ...]
    current_result: EvaluationResult | None
    semantic_result_sha256: str | None
    history_sha256: str
```

Revision numbers start at one and are contiguous. Every revision is canonical and links the prior revision digest; an invoked revision binds exactly its terminal attempt number, while skipped uses `None`. A duplicate result for one attempt, a result without its terminal evidence, a noncontiguous revision, or a new revision without an allowed state transition is a hard conflict. No prior result byte is replaced or relabeled.

Create mode rejects any existing root. Resume mode rejects an absent, symlinked, malformed, forked, truncated, unknown, or conflicting record. It never truncates, repairs, overwrites, follows path discovery, or falls back to legacy records. The same job with a different plan hash, same path with another job, unexpected result, duplicate same-attempt result, noncontiguous attempts/revisions, or occupied evidence path is a hard conflict. Temporary files are never accepted as records.

`current_result` is the latest valid revision. `semantic_result_sha256` binds job ID plus only that normalized current semantic payload and excludes revision/attempt numbers, times, run-local paths, raw judge output/reasoning, and superseded failures. It is `None` before any result. The history digest binds the immutable plan, resume policy, every start/terminal event, evidence file digest, and every result revision/link. Equal normalized successful results after a retry have equal semantic result digests and different history digests.

A `completed` or eligible `partial` current result is final and can only be skipped after `load_job` revalidates the exact job/input/plan/config/view/snapshot/candidate/current-result/evidence bytes and hashes. It is never invoked again. A `failed` or `invalid` result can start a later attempt only when its `EvaluationFailure.retryable` is true, its exact inner `Failure` occurs in the stored policy, and the attempt bound is not exhausted. An `interrupted` result requires the same retryable bit, `retry_interrupted=True`, and an available attempt. A skipped result becomes eligible only when it copied a retryable causal interruption or exact policy-listed failure, `resume_skipped_after_retryable_run_stop=True`, the source stop is successfully cleared on the same exact resume, and its content/plan still revalidate. Policy/config change, non-retryable state, or exhausted attempts makes zero new calls.

PR-09 supplies this sink through `EvaluationJobRequest` and records returned job/result links. Its non-evaluation Builder/candidate/group journal is separately owned as `eval_harness.experiments.journal.ExperimentRecordSink`; PR-05 does not overload evaluation schemas with experiment events.

## Dispatch, stop, cancellation, and reuse

`run_evaluation_jobs(evaluator: Evaluator, requests: tuple[EvaluationJobRequest, ...]) -> EvaluationRunSummary` is the common dispatcher. All requests use the same exact evaluator identity/revision/config and one sink, preserve caller order, and are fully checked before dispatch.

The caller first runs `Evaluator.preflight`. For each distinct view it then obtains `judge_runtime_preflight_requests`; if any exist, the supplied runtime runs all of them before generation in `./eval run`, or before plan persistence in `./eval evaluate`. No configured member is excluded/resampled after a failed preflight. All evaluator plans and sink destinations are validated, and all job plans are saved, before the first evaluator/judge invocation.

For each job the dispatcher appends a start, calls exactly the selected evaluator, appends terminal evidence, then appends a semantic result revision/index. A task-impact failure records that job and continues later independent jobs. Auth, quota, runtime protocol, integrity, or other run-impact failure records the current failed/invalid revision, appends skipped/no-metric revisions for every unstarted planned job, and stops. It does not infer severity from exception text. No implicit retry occurs; only an evaluator's hash-bound within-attempt completion policy or an explicit exact-policy resume permits another job attempt.

`KeyboardInterrupt`/cancellation records the running attempt and result revision as interrupted, marks unstarted jobs skipped due to interruption, flushes all evidence, and returns/raises through the CLI's stable interrupted path. It never converts interruption to failed or completed. A crash after start but before terminal leaves an immutable incomplete attempt; explicit resume first appends its interrupted terminal and result revision, then may start a new attempt only under the exact stored policy.

On resume the dispatcher reopens and revalidates all planned jobs in original order. It skips exact completed/eligible-partial results. It retries an eligible failed/invalid/interrupted source job by appending a new attempt and result revision. A run-impact source must resolve before its causally skipped suffix can become eligible; if it stops again, no duplicate skipped revision is appended and dispatch stops. Once cleared, eligible skipped jobs receive their first real attempt in original order. Non-retryable or policy-disallowed run-impact state remains a stop. The latest normalized successful result becomes the semantic result; all prior failures and skipped/interrupted revisions remain in history.

## CLI behavior

`./eval run BENCHMARK` adds mutually exclusive evaluation selection:

- `--execution-only`; or
- `--evaluator EVALUATOR_ID` with optional strict JSON `--evaluator-config FILE`; or
- omission of both only when the benchmark declares an exact default evaluator.

Supplying evaluator/judge options with execution-only is an error. A missing default is an error before benchmark preparation/output/model work. Execution-only prints candidate/run status and no metric/evaluated-success field. With evaluation, evaluator/grader/judge readiness and static view/cardinality checks precede executor calls; generation completes and reloads from its authoritative index before evaluation begins.

`./eval evaluate` accepts existing bundles only through:

```text
./eval evaluate --snapshot SNAPSHOT_DIR \
  --candidate BUNDLE_DIR [--candidate BUNDLE_DIR ...] \
  --evaluator EVALUATOR_ID [--evaluator-config FILE] \
  --out EVALUATION_ROOT \
  (--match-occurrence-id OPAQUE_ID | --jobs JOBS_JSON) [--resume]
```

`--match-occurrence-id` builds one job and therefore requires the number of candidates to equal evaluator cardinality. `--jobs` is a strict versioned JSON object containing ordered `{match_occurrence_id,candidate_ids}` entries and is required to express more candidates/combinations. It may also express one job. There is no implicit all-pairs/baseline plan. Candidate IDs come only from strictly loaded manifests; duplicate roots/IDs/digests, unused candidates in CLI input, missing IDs, wrong cardinality, mixed tasks/snapshots, and conflicting occurrences reject before preflight/invocation. `--resume` requires an existing exact root and the exact resume policy in the selected evaluator's unchanged canonical config; without it the root must be fresh. The CLI has no flag that can widen the stored policy or force replay of a completed/non-retryable result.

`./eval evaluate` needs no benchmark adapter and reads no runtime, `results.jsonl`, executor directory, task prompt path, judge prompt path, `.gdpval`, or environment-named candidate root. After loading, deleting the entire generation runtime tree cannot affect the plan, evaluation, aggregate, or result digests.

CLI parse/config/registry/plan/preflight/integrity errors exit nonzero with stable secret-free text and no model call. Interrupted evaluation uses the existing shell interruption convention. Result JSON reports evaluator ID/revision, planned/per-status counts, exact named metric values and denominators, result root, and terminal run status; it does not print a common score.

## Locked AIME dependency and shared HTTP seam

Add a dedicated optional extra `eval-harness = ["math-verify==0.8.0"]` with the repository-required license/update rationale, and include it in `all`. The Eval Harness CI test/type/audit environments use `--extra dev --extra eval-harness` with `--locked`/`--no-sync` as appropriate. The dependency-audit export uses the same extras and explicitly asserts `math-verify` is present before strict hash-required `pip-audit`. Regenerate `uv.lock`; do not install dynamically, use a mutable requirements URL, or retain a test-only monkeypatch as native verification evidence. Align `resources_servers/math_with_judge/requirements.txt` to the same project extra so the version has one declared source.

PR-07 owns the one shared async HTTP lifecycle addition; PR-05 records and freezes the seam so no evaluator/generation code creates a duplicate transport. Provider policy calls use the existing `nemo_gym.server_utils.request(..., connection_attempts=1, attempts=1)`. PR-07 adds `async def close_client_session() -> None`, which closes and resets the singleton on its owning event loop, and calls it from Stirrup's execute-coroutine `finally`. Defaults for all other callers stay unchanged. Judge transports remain behind `JudgeRuntime` and do not use this provider lifecycle implicitly.

## Required deterministic tests and expected results

1. **Identity goldens.** Pin canonical bytes and SHA-256 for unary and pairwise jobs. Changing snapshot/task/view/candidate order or digest/evaluator ID/revision/config changes input and job IDs. Changing only occurrence changes job ID, not input. Changing only evaluator plan changes plan hash but neither input nor job; reuse then rejects the conflict. Paths/timestamps/attempts/raw evidence do not change semantic IDs.
2. **Strict unary reevaluation.** Generate a candidate through `prepare_generation_plan`/`run_generation_plan`, load it only with `RunManifest`, `VerifiedSnapshotBinding`, and `load_run_results`, delete runtime, evaluate from another working directory, move the complete run tree, rebind/reload, and obtain the same native result digest. No runtime/legacy file is read.
3. **Explicit pairwise/N planning.** One candidate with a unary evaluator and two with a pairwise evaluator pass. Wrong cardinality, duplicate candidate, mixed task/snapshot, missing/changed bundle, mismatched view, N candidates without explicit matches, undeclared pair, duplicate occurrence, and implicit fallback all reject before evaluator/judge calls. An explicit ordered N plan emits exactly its supplied jobs in order.
4. **Generation reuse/barrier/reopen.** One plan uses repeated references for multiple interventions while `ordered_tasks` remains unique. The snapshot is neither acquired nor loaded through a benchmark twice. All candidates seal/index before a counting evaluator is called. Occurrence IDs never appear in prompts/workspaces/bundles/paths or raw manifest configuration. Changing only run/occurrence IDs preserves `generation_semantics_sha256`, configuration, and run fingerprint but changes `generation_plan_record_sha256`. In one process generate a strict prefix, then in a new process call `resume_generation_plan`; expect exact reconstructed `completed`, ordered suffix, preserved old bytes/IDs/sequences, a fresh runtime, and a full ordered return. Complete reopen makes zero executor calls. Changed plan/config/environment/intervention, truncated/noncanonical index, tampered/missing bundle, unindexed/orphan/partial candidate, symlink, or indexed run-impact stop rejects without reacquisition, deletion, repair, evaluator call, or append.
5. **Evaluation durability/revisions/reuse.** Assert plan-before-call, fsynced start-before-invoke, terminal-before-result, monotonic attempts/revisions/index, and immutable old bytes. In one process persist an interrupted result and causally skipped suffix; discard every live object, then in a new process reopen with the exact policy, append a second attempt/completed revision, and run the skipped job. Expect the same final semantic result digests as an uninterrupted fixture, distinct history digests, and all old failure/result bytes retained. Completed/eligible-partial jobs make zero calls. Repeat for an explicitly policy-listed retryable run-impact source failure. Changed policy/config, non-retryable/exhausted source, create-on-occupied, resume-on-fresh, plan conflict, corruption, unexpected file, symlink/path escape/collision, truncated JSONL, fork, duplicate same-attempt result, and missing evidence fail closed without overwrite/fallback.
6. **Failure semantics.** Completed wrong answers stay evaluator outcomes and alone have no failure. Eligible partial carries a non-retryable TASK summary failure. `INVALID_RESPONSE/TASK` can be retried/continued only under explicit exact policy. A task-impact evaluation failure continues; auth/quota/runtime-protocol/integrity run-impact stops and marks remaining jobs skipped/no metric. On exact resume a retryable listed source must clear before policy-enabled causal skips run; another stop preserves the existing skips. Interrupt stays interrupted. Failed/invalid/interrupted/skipped require failure and cannot carry metrics. A partial metric fails unless its bound `valid_only` threshold is satisfied.
7. **Role-policy, content delivery, and blind isolation.** Pin canonical root-deny overrides for read-only and read-write workspaces and prove environment-key equality, allowed/protected overlap rejection, network/web flags, and the common production no-model probe. Using fake local CLI processes and randomized sentinels, prove anonymous workspace readability and denial of snapshot, bundles, output, source, home/auth, sibling runtime, and unrelated env; isolated HOME/TMP; no network/web; bounded output; logical evidence digests; and cleanup. Verify exact block file-set/size/hash/media order reaches fake CLI and HTTP transports, and missing/extra/changed/unsupported AV bytes fail before invocation. Codex judge preflight delegates to the common probe. Claude with valid fake subscription status still fails before invocation because confinement cannot be proved. Prompt-only anonymity or a capability label without block delivery is insufficient.
8. **AIME actual verifier.** In the locked CI environment, call the real `math-verify==0.8.0` path with deterministic correct, wrong, empty, and no-deliverable candidates. Expect named `accuracy` 1/0/0/0 with denominator one and no LLM call. Inject import/version/invalid-shape/runtime infrastructure faults and expect failed/no metric plus remaining-job stop, never accuracy zero.
9. **BigCode adapter.** Against the accepted PR-04 fake/real sandbox fixtures, preserve its exact pass/test-fail/empty/no-code/candidate-limit mappings. Inject `GraderInfrastructureError`; expect failed/no metric and stop. Failed executor candidates are skipped and never enter the grader. No raw grader path/error is copied into semantic result.
10. **Registry/default/CLI.** Exact evaluator IDs select implementations; benchmark names are rejected by evaluator lookup; default and explicit selection agree; no default requires execution-only or explicit evaluator; execution-only makes zero evaluator/judge calls and prints no metric. List all five categories truthfully. Unknown IDs/config keys and native-to-judge fallback fail before output/model work.
11. **Fourth benchmark extension.** In fresh local registries, register a benchmark with an unrelated ID and a unary evaluator factory. Use a fake executor/runtime, the real snapshot acquisition/binding, common generation entrypoint, authoritative loaders, common planner/runner/sink, runtime deletion, and strict reevaluation. Do not edit/branch/monkeypatch runner, Executor, Builder, or fabricate CandidateBundle/RunResult rows. The same registry APIs list/create it and its native named metric/denominator remains intact. PR-11 repeats this against the final stack including Builder.
12. **Aggregate semantics.** Mixed completed/failed/skipped fixtures retain planned and status denominators. AIME accuracy and BigCode pass-rate are separate evaluator-named aggregates. Outcome-only pairwise records have no numeric metric. The generic runner never averages unlike keys, excludes failures by inference, creates Elo, or emits universal score.

All tests use local deterministic fakes or the pinned native verifier/sandbox. They issue zero real model, judge, provider, subscription, paid API, or external-network calls.

## Acceptance gates and done criteria

PR-05 is done only when:

- the exact accepted PR-02c and PR-04 dependency SHAs are recorded and the implementation head descends both;
- Sol reviews source against this contract and the PR-02c/04 public APIs;
- the independent CLI evaluates sealed bundles with runtime deleted and no legacy lookup;
- explicit evaluator IDs/defaults, unary/pairwise/N planning, verified partial-generation reopen, guarded runtime, immutable evaluation result revisions, exact-policy retry/stop behavior, sink durability, and evaluator-owned aggregates pass the tests above;
- real `math-verify==0.8.0` is present in the locked/audited measured CI environment and native AIME fixtures pass;
- focused tests, the complete deterministic harness suite, all shell integrations, Ruff, strict mypy, exact integer 96% coverage, strict dependency/CVE audit, secret scan, copyright checks, and DCO pass on the exact promoted head;
- the Draft PR/head/tree and all changed bytes are read back, CI is tied to that exact head, and saved, validated, and accepted states are reported separately.

No real-model quality claim follows from these gates.

## Prohibitions

- No evaluator selection by benchmark-name alias, implicit judge/native switch, pairwise-to-unary fallback, implicit N pairing, common metric average, universal score, or generic Elo.
- No reading/fabricating bundles from `results.jsonl`, executor/runtime directories, old judge prompt paths, `.gdpval`, environment-named run paths, or alternate snapshot/prompt paths.
- No CandidateBundle/Snapshot/RunManifest schema expansion, evaluator data in TaskSpec, provenance projected wholesale to judges, arm/condition labels in model input, or secrets/auth/env values in hashes/records.
- No GDPval rubric/pairwise prompt/parser/panel/BattleRecord semantics, AA stage/anchor/Elo, experiment group/journal, Builder, Stirrup, or old-route deletion in this slice.
- No duplicate vendor CLI or HTTP transport, ordinary workspace-write Executor as blind-judge confinement, unverified Claude judge, network/web-enabled blind judge, model-backed isolation probe, or silent failed-member resampling.
- No overwrite/truncate/repair-on-read, auto-resume, old-schema fallback, symlink/path escape, fabricated skipped score, infrastructure-as-zero, exception-message severity inference, or swallowed interruption.
- No dependency or runtime download during evaluation, loose math verifier version, audit/coverage/type/CVE weakening, deleted behavioral test, real model/provider/judge call, production credential, force push, merge, release, or publication.

## Closed and unresolved decisions

All semantic/API decisions in this contract are closed, including the job/input hash split, occurrence identity, exact public names, one experiment-level GenerationPlan, semantic/full generation-plan digest split, verified prefix reopen, result revisions, exact resume policy, role-scoped environment delivery, evaluator-owned plan/aggregate, guarded runtime/content-block delivery, sink ownership, GDPval default behavior, AIME dependency group, and PR-07 HTTP seam. Protected local Codex and PR-07 contained Stirrup are the accepted experiment routes; Claude and Cursor are ineligible until an equivalent role-policy probe is accepted. The only unresolved PR-05 values are the future accepted PR-02c and PR-04 full implementation SHAs/tree identities. Substituting dependency identities in the PR-05 work record does not authorize changing this contract; any actual API conflict returns to Sol, and a migration-policy change returns to Astra.
