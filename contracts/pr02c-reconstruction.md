<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR-02c reconstructed implementation contract: generation handoff integration

Status: reconstructed design contract for implementation; this is a new contract derived from the canonical plan and the accepted PR-01/02a/02b/03 code. It is not recovered unpublished source.

## Authority, base, and dependencies

- Canonical plan: `checkpoint/migration-control` commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, file `eval-harness-neutrality-migration-plan-2026-09-12.md`, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`. The complete original upload was read, including §§5.1, 5.2, and 6.
- Implementation base: immutable commit `d5ce0c10162cad788a17cb90f34b8f60574e7f75`, tree `354943ebbb8ea81a30523bfdc12baf26771853b5` (`mashimashica/eval-harness`, accepted PR-03 head).
- Fixed dependencies: PR-01 snapshot contracts, PR-02a execution/failure contracts, PR-02b candidate bundle/run manifest contracts, and PR-03 typed executor parsers. Their public APIs are inputs to this slice and must not be redesigned here.
- This contract is intentionally narrow: it connects the existing generic generation runner to `BenchmarkSnapshot`, `CandidateBundle`, `RunManifest`, and `RunResultWriter`. PR-05 owns the independent evaluation runner/CLI, PR-06 owns completed GDPval evaluation, PR-09 owns experiment-consumer migration, and PR-10 owns removal of replaced records/routes.

## Purpose and resulting behavior

For every attempted task, the generic runner must materialize the execution view from one sealed snapshot, execute the selected intervention/executor, seal the result as a self-contained `CandidateBundle` under `out`, append its strict `RunResultRow`, and only then invoke the currently staged evaluator. The authoritative generation handoff is:

1. `run-manifest.json`
2. the in-run sealed snapshot named by `RunManifest.snapshot_path`
3. `candidate-results.jsonl` named by `RunManifest.results_path`
4. indexed bundles under `candidates/`

The handoff must load and verify after the external runtime tree has been deleted or the complete `out` tree has been relocated. No new reader may search legacy task/executor paths or reconstruct candidates from `results.jsonl`.

This slice retains the current immediate evaluator call and legacy `results.jsonl` only for staged consumers. Candidate seal/index is the durability boundary and occurs before `Evaluator.evaluate` or any judge execution. Evaluator preflight and all-task `validate_plan` still run before executor/model work. New evaluation code must be able to obtain canonical task/evaluation data from the bound snapshot and candidate outputs/artifacts from the indexed bundle alone.

## Allowed paths

Production changes are limited to:

- `eval_harness/runner.py`
- `eval_harness/layout.py`
- `eval_harness/benchmarks/gdpval.py` only for the minimal execution-wrapper correction from `reference_files` to the snapshot execution-view directory `task_inputs`

Test changes are limited to:

- new `tests/harness/test_generation_handoff.py`
- `tests/harness/test_generic_runner.py`
- `tests/harness/test_runner_reliability.py`
- `tests/harness/test_reasoning_effort.py`
- `tests/harness/test_benchmark_snapshot.py` or `tests/harness/test_boundary_failure_coverage.py` only for the GDPval wrapper assertion
- `tests/harness/test_builder_experiment_runner.py` and `tests/harness/test_experiment_reliability.py` only to add fixed capability declarations to fake application executors and update assertions about the nested generic-run records; no experiment production behavior may change

One same-purpose test helper file may be used instead of duplicating fixture classes. Any production path outside this list, or any public-contract change, returns to Sol for a contract amendment before editing.

## Fixed input and output APIs

### Runner entry point

Keep the existing `run_benchmark(...) -> RunSummary` public signature and existing `RunSummary` meaning. Keep validation and preflight before model/executor work. The runner consumes the accepted typed APIs directly:

- `Benchmark.acquire_snapshot(limit, destination) -> BenchmarkSnapshot`
- `VerifiedSnapshotBinding.load(root)`, `.reference(task_id)`, `.bind_evaluation_view(reference)`, and `.materialize_execution(reference, workspace)`
- `SnapshotTask.task_spec() -> TaskSpec`
- `Benchmark.execution_task(BenchmarkTask, workspace, *, network_policy) -> TaskSpec`
- `Executor.network_access_enabled: bool`, `Executor.capabilities: ExecutorCapabilities`, and `Executor.execute(ExecutionRequest) -> ExecutionResult`
- `seal_candidate_bundle(...) -> CandidateBundle`
- `write_run_manifest(...)`, `RunResultWriter.create(...)`, and `RunResultWriter.append(...)`

Do not add compatibility probing with `getattr`, aliases, dictionary coercion, or fallback fields for these fixed contracts.

### Candidate layout and identity

Add one typed layout helper in `layout.py` and use it for both sealing and indexing:

```python
@dataclass(frozen=True)
class CandidateLayout:
    relative_path: str
    root: Path

def candidate_layout(run_root: Path, sequence: int) -> CandidateLayout:
    ...
```

`sequence` must have exact type `int` (reject `bool`) and be non-negative. The result is exactly:

- name: `candidate-{sequence:08d}`
- relative path: `candidates/candidate-{sequence:08d}`
- root: `run_root / "candidates" / f"candidate-{sequence:08d}"`

The opaque globally unique candidate ID is exactly `f"{run_id}:candidate-{sequence:08d}"`. `run_id` is a new cryptographically random opaque run ID generated once by `run_benchmark` using `secrets.token_hex(16)`, separate from every per-task `application_run_id`. Neither ID nor path may contain benchmark, condition, intervention, executor, vendor, model, or arm labels.

### Snapshot acquisition and views

After successful evaluator/intervention/executor preflight and one `benchmark.prepare()` call, acquire exactly one sealed snapshot in a controller-only temporary sibling of the planned `out_root`. Use `tempfile.TemporaryDirectory` under `out_root.parent`, and call `benchmark.acquire_snapshot(limit, temporary_root / "snapshot")` exactly once. Do not call `benchmark.load_tasks`, `benchmark.materialize`, or `benchmark.snapshot_task` separately in the runner.

Before benchmark preparation or snapshot acquisition, require a successful intervention preflight to contain the fixed `InterventionBundle` and exact `InterventionManifest` supplied by the accepted contract. Reject a missing/wrong manifest before any executor/model call; never fabricate an identity manifest or defer this validation until candidate sealing.

Load a `VerifiedSnapshotBinding` against that temporary sealed snapshot. From that binding, construct and validate every evaluator plan and every intervention task before `out_root` or an external runtime root exists. If acquisition, safe task-ID checking, binding, plan validation, or intervention task validation fails, clean the controller temporary directory, leave both planned roots absent, and perform no executor/model/judge call. This preserves the accepted early-plan-failure lifecycle while sourcing all evaluation metadata from the immutable snapshot.

After all-task validation succeeds, create `out_root` exclusively and atomically rename the already sealed `temporary_root / "snapshot"` to exactly `out_root / "snapshot"` on the same filesystem. Fsync `out_root`, discard the temporary binding, and load a new `VerifiedSnapshotBinding` from the published path before any materialization or bundle sealing. Never keep using the pre-rename binding: its root/seal capability is tied to the old path. Re-resolve the same ordered references from the published binding and require them to match the pre-publication values. Create the external runtime root, when requested, only after snapshot publication. Preserve snapshot task order as `RunManifest.ordered_tasks`.

For each snapshot task:

- use `SnapshotTask.task_spec()` as the canonical executor `TaskSpec`;
- use `binding.bind_evaluation_view(reference)` to build and validate the existing `EvaluationPlan` before the first executor invocation;
- create only `BenchmarkTask(execution=snapshot_task.task_spec())` for the existing `Benchmark.execution_task` wrapper; do not reconstruct materialization/evaluation dictionaries and do not add adapter-name branches;
- call `binding.materialize_execution(reference, task_layout.workspace)` exactly once; the workspace must be fresh;
- write any legacy runtime prompt/provenance file from the bound canonical prompt only. It is not a handoff input.

The minimal GDPval wrapper fix changes `_reference_listing` and its generated instructions to list/read/protect `task_inputs`. It must not change snapshot acquisition, evaluation presentation, the legacy judge, AgentSkill `.gdpval` workspace layout, or introduce a GDPval branch in the runner.

### Network capability and execution request

Read `executor.network_access_enabled` directly before benchmark preparation, validate that its exact type is `bool`, and bind that value to the existing execution network-policy wrapper/configuration/provenance. Do not read the removed `network_enabled` attribute and do not default a missing value to `False`. Preserve the CLI/requested policy checks already enforced by the runner. The fixed `CandidateBundle` schema has no separate network field, so its candidate-level evidence is the exact effective wrapper/intervention prompt: tests must use a neutral wrapper that embeds the supplied policy and assert the sealed `effective_executor_prompt` contains `enabled` for `True` and `disabled` for `False`. Do not change `ExecutorEvidence` to duplicate this field.

Read `executor.capabilities` through the typed PR-03 contract. Use that exact declaration in `ExecutorEvidence.declared_capabilities`; do not infer capabilities from produced files or output text.

Build the existing `ExecutionRequest` with the intervention application's effective `TaskSpec`, the snapshot-materialized workspace, the assigned workspace `deliverables` and executor directories, requested model/timeout, and the current sanitized executor environment.

### Run manifest and configuration

Create `RunManifest` after snapshot publication and before the first executor invocation with:

- `run_id`: the opaque run ID
- `snapshot_path`: exactly `"snapshot"`
- `snapshot_sha256`: the verified snapshot digest
- `results_path`: exactly `"candidate-results.jsonl"`
- `configuration`: a secret-free stable whitelist described below
- `configuration_sha256=None` and `run_fingerprint_sha256=None`, allowing the fixed constructor to compute them
- `ordered_tasks`: the snapshot references in snapshot order

Create the exclusive `RunResultWriter` before publishing the manifest, then write `out_root / "run-manifest.json"` with `write_run_manifest`. Existing-output/refusal behavior remains fail-closed.

The configuration whitelist contains semantic requested setup only: benchmark identity and source/revision availability; executor ID, declared version/auth/invocation mode, requested model, typed network policy, requested reasoning effort, and typed declared capabilities; evaluator stable ID/type/version and explicit judge executor/model/auth/reasoning fields when present; intervention stable manifest identity/type/source revision/revision status/bundle and manifest digests/application mapping; task limit and timeout. Reuse existing serialization helpers where their output meets this whitelist.

The configuration must exclude `run_id`, timestamps, status/failure/application-run IDs, repository commit/dirty evidence, absolute or runtime paths, `runtime_layout`, preflight detail strings, environment values, credentials/tokens, executor result/model IDs, effective reasoning evidence, output digests, and condition/arm labels. Repository commit/dirty evidence stays only in the outer legacy metadata. Relocating runtime/out paths must not change `configuration_sha256` or `run_fingerprint_sha256`.

### Bundle sealing and authoritative indexing

After `Executor.execute`, validate all existing identity/path invariants and the fixed PR-03 fields before evaluating. This includes task ID, executor ID/version, invocation mode/auth mode, `ExecutionResult.runtime == executor.runtime`, assigned workspace, and assigned deliverables path. Preserve a typed failure unchanged; never fabricate an answer or empty artifact tree.

Call `seal_candidate_bundle` with this exact mapping:

| Argument | Source |
| --- | --- |
| `destination` | `candidate_layout(out_root, sequence).root` |
| `candidate_id` | `f"{run_id}:candidate-{sequence:08d}"` |
| `snapshot_binding` / `snapshot_reference` | verified run binding / ordered reference |
| `effective_executor_prompt` | `InterventionApplication.task.prompt` |
| `executor_evidence` | fixed `ExecutorEvidence` mapping below |
| `intervention_evidence` | `InterventionEvidence(intervention_preflight.bundle.manifest, application)` |
| `status`, `output_text`, `available_outputs`, `failure` | copied unchanged from `ExecutionResult` |
| `artifacts_root` | `result.deliverables_dir` only when `ExecutorOutput.ARTIFACT_FILES` is declared in `result.available_outputs`; otherwise `None` |

Build `ExecutorEvidence` using: executor name; validated result executor version; result runtime and invocation/auth/model IDs; the run's requested model; executor requested reasoning effort; result requested/effective reasoning fields including availability; exact `executor.capabilities`; and result timestamps/exit code. Do not add runner-local labels or paths.

Immediately after a successful seal, append exactly one `RunResultRow(sequence, candidate_id, snapshot_reference, bundle_path=layout.relative_path, bundle_sha256=bundle.bundle_sha256)`. Sequence starts at zero and is contiguous. The row append must finish before any `Evaluator.evaluate`/judge call or before raising a systemic `RunAbort`.

`candidate-results.jsonl` is authoritative and append-only. A seal failure leaves no complete bundle and no row. An index append failure may leave a complete but unindexed bundle; the strict loader must ignore it, and the runner must not delete or invent a row for it. Both failures stop the run, persist the legacy outer failure status where possible, and never call the evaluator. A later task failure preserves all prior indexed bundles and rows.

### Staged current evaluator

Only after bundle seal and index append may the existing immediate evaluator API receive its current `EvaluationCandidate` bridge. Preserve current evaluation result/legacy-row behavior for current callers. The bridge may use the already bound canonical view and sealed candidate material available in this process, but it must not establish a new prompt-file/path-search contract.

- On an executor result with a `Failure` whose impact is `RUN`, seal and index the failed candidate first, persist the existing skipped-evaluation legacy record, then raise the same `RunAbort`; no evaluator/judge call occurs.
- On evaluator exception/interrupt or evaluator result identity failure, keep the already indexed candidate, persist current failure evidence/status, and propagate the exception.
- Normal wrong/empty model output is a candidate outcome, not a runner integrity failure. Evaluation retains the existing semantic status/metric behavior.

PR-05 will replace this bridge with the common evaluation runner/CLI. PR-06 removes GDPval external handoff as a completion route. PR-09 migrates experiment consumers. PR-10 removes legacy `results.jsonl`, prompt-path/judge routes, and the AgentSkill `.gdpval` workspace dependency. PR-02c must not implement those later responsibilities.

## Invariants and failure behavior

- One run uses one immutable snapshot. Every indexed candidate binds to an entry in that snapshot and verifies through `load_run_results(manifest, snapshot_binding=binding)`.
- Canonical prompt/evaluation data come only from the bound snapshot; intervention affects only `effective_executor_prompt` and its explicit evidence.
- `TaskSpec` never contains evaluation-only data. Snapshot execution materialization contains no evaluation-only bytes.
- `out` owns all durable handoff bytes. External runtime logs/workspaces may be deleted without breaking handoff verification or access to declared candidate outputs/artifacts.
- Moving the complete `out` tree preserves verification because manifest/index paths are logical relative paths.
- Auth, quota, protocol, integrity, transport/process/timeout, and interruption kinds and their `FailureImpact` remain unchanged. Systemic failures stop remaining tasks. None becomes a zero score, tie, success, or execution-only success.
- Bundle/path/capability mismatch is an integrity failure in the generation handoff: no evaluator call, no fallback, no silently downgraded output channel. Preserve the accepted exception boundary: runner identity/path validation raises its existing `ValueError`; bundle/schema/capability validation raises `CandidateBundleError`; the outer legacy run status becomes `failed`. Do not synthesize a `Failure` or candidate bundle for an invalid result.
- Existing `out` is never overwritten. Partial snapshot/manifest/index/bundles and legacy logs/metadata remain durable and diagnosable.
- Configuration/provenance are deterministic, secret-free, and condition-blind. Do not serialize raw preflight details or environment values into fingerprints.
- No code in common runner/layout branches on `gdpval`, `aime`, `bigcode`, `alps`, an intervention/condition name, or a vendor name.

## Required tests and exact expected results

All tests use fakes/local fixtures and make zero real model, judge, provider, or external-network calls.

1. **Successful end-to-end handoff with separated runtime.** Two fake tasks run in snapshot order. Assert the manifest paths are exactly `snapshot` and `candidate-results.jsonl`; rows are sequences `0,1`; paths are `candidates/candidate-00000000` and `...00000001`; IDs are `<run_id>:candidate-00000000/1`; each bundle binds to the expected reference and contains the effective intervention prompt plus declared output/artifact bytes. Assert both evaluator calls occur strictly after the matching bundle is sealed and its row is durably appended.
2. **Runtime deletion and relocation.** After success, delete the external runtime tree, move the complete out tree, load `RunManifest`, `VerifiedSnapshotBinding`, and `load_run_results`, then read final text and copied artifact bytes from both bundles. Expected: strict verification succeeds and no legacy prompt/task/executor runtime path is read.
3. **Single acquisition/load.** Instrument a benchmark and assert `prepare == 1`, `load_tasks == 1` (through `acquire_snapshot` only), `snapshot_task == number of tasks`, and bound `materialize_execution == number of attempted tasks`. `Benchmark.materialize` may be called by the adapter's `snapshot_task` during that one acquisition (the default implementation calls it once per task), but its count must not increase after acquisition and the runner must never call it directly for execution. Evaluator plan validation sees bound evaluation data and finishes before `executor.execute` count becomes nonzero.
4. **GDPval task-input wrapper.** A bound GDPval execution workspace containing `task_inputs/a.txt` produces a wrapper that lists `task_inputs/a.txt`, says to protect `task_inputs`, and does not instruct use/protection of `reference_files`. Snapshot/evaluation-only bytes remain excluded from execution materialization.
5. **Network true/false provenance.** For two typed fake executors, `network_access_enabled=True` and `False` propagate respectively to the benchmark wrapper's `network_policy`, stable manifest configuration, outer metadata, and the sealed candidate's exact `effective_executor_prompt`. An executor missing the property or returning `0`, `1`, or `None` is rejected before benchmark preparation/snapshot acquisition/execution and before either planned root exists; no `getattr(..., default)` fallback exists.
6. **Deterministic semantic identity.** Repeat the same semantic configuration with different out/runtime roots and repository dirty evidence. Expected: equal `configuration_sha256` and `run_fingerprint_sha256`; run IDs/candidate IDs may differ. Change requested model, network policy, intervention digest, evaluator/judge semantic config, timeout, or ordered snapshot reference and assert the corresponding digest changes. Assert configuration JSON contains no absolute roots, `runtime_layout`, status, preflight detail sentinel, secret environment sentinel, condition/arm label, result model ID, or timestamps.
7. **Failed systemic candidate is durable before abort.** Parameterize representative typed AUTH, QUOTA, PROTOCOL, and INTEGRITY RUN-impact failures (and preserve existing timeout/process/interruption coverage). Expected: one failed bundle and one authoritative row verify; bundle keeps the exact failure kind/code/impact, has no available outputs, evaluator/judge call count is zero, next task is not executed, legacy status is failed/interrupted as currently defined, and `RunAbort`/interrupt propagates.
8. **Seal/index/path/capability failures fail closed.** Cover output channel absent from declared capabilities, artifact symlink/path escape, result workspace or deliverables mismatch, bundle destination collision, and forced index append failure. Expected: no evaluator call; no authoritative row for an unsealed candidate; an index failure can leave only an ignored unindexed sealed bundle; prior rows/bundles remain loadable; no zero/tie/result fabrication and no fallback path scan.
9. **Mutation and missing-byte verification.** After a successful run, independently tamper with/remove the in-run snapshot, an indexed bundle manifest/blob, and an index digest/path. Expected: `VerifiedSnapshotBinding.load`, `load_candidate_bundle`, or `load_run_results` rejects each deterministically. A syntactically valid unindexed bundle is ignored.
10. **Staged legacy compatibility.** Existing generic runner/reliability/reasoning tests continue to observe `results.jsonl`, current `RunSummary`, immediate evaluation results, provenance, and partial failure persistence. Also assert `candidate-results.jsonl` is authoritative and no new reader/fallback consumes legacy rows or executor prompt paths.
11. **Neutrality.** The handoff integration test uses an unknown fixture benchmark name and works without core branches or registry edits. Assert condition/model/intervention labels are absent from candidate IDs/paths and evaluator input.
12. **Controller snapshot publication lifecycle.** A late-task `validate_plan` or `intervention.validate_task` failure sees canonical bound snapshot content but leaves no out/runtime root and makes zero executor/evaluate/judge calls; instrument the benchmark to prove `load_tasks` ran once. On success, assert the temporary binding is not reused after the atomic rename, the published binding resolves exactly the same ordered references, and no controller staging directory remains.

## Acceptance commands and expected gates

Run from the exact implementation checkout using the locked Python 3.13.14 environment. At minimum:

```bash
.venv/bin/python -m unittest \
  tests.harness.test_generation_handoff \
  tests.harness.test_generic_runner \
  tests.harness.test_runner_reliability \
  tests.harness.test_reasoning_effort \
  tests.harness.test_benchmark_snapshot \
  tests.harness.test_boundary_failure_coverage
uv run --locked --extra dev ruff check eval_harness/runner.py eval_harness/layout.py eval_harness/benchmarks/gdpval.py tests/harness
uv run --locked --extra dev ruff format --check eval_harness/runner.py eval_harness/layout.py eval_harness/benchmarks/gdpval.py tests/harness
```

Also run the repository's unchanged strict type, full harness/unit, coverage (at least 96%), audit, secret, copyright, and DCO workflows exactly as CI defines them. Expected result: every required check passes on the exact saved PR-02c head; no threshold, scope, dependency lock, or workflow weakening; zero real model/judge calls.

## Done criteria

PR-02c is done only when all of the following are true on one immutable, durably saved head:

- the allowed diff implements and tests the mapping above without changing fixed public contracts;
- every attempted task that reaches a valid, identity/path/channel-conformant typed `ExecutionResult` is sealed and indexed before evaluation or systemic abort; an invalid result is rejected without a fabricated bundle or row;
- the complete authoritative handoff loads, verifies, relocates, and exposes declared candidate outputs after runtime deletion;
- snapshot tasks are acquired once and canonical/evaluation/execution views remain separated;
- all-task plan/intervention validation uses the temporary verified binding, retains the accepted no-output-root early failure behavior, and reopens the binding after atomic snapshot publication;
- typed true/false network capability and typed executor capabilities are recorded correctly, with missing/malformed contracts rejected;
- all negative cases preserve the original typed failure semantics and stop or continue exactly according to their impact;
- staged legacy consumers remain green while no new legacy fallback/shim is added;
- focused tests and every unchanged required CI gate pass on the exact commit;
- Sol reviews the saved implementation against this contract, then Astra independently accepts the resulting slice. A checkpoint alone is saved, not validated or accepted.

## Prohibitions

- No changes to fixed `candidate_bundle.py`, `run_manifest.py`, snapshot, failure, executor, intervention, or evaluator public contracts without returning to Sol.
- No evaluator registry/CLI/common evaluation runner, grader sandbox, GDPval rubric/pairwise completion, Stirrup provider, AA-v2, Builder/N/S/A, experiment-consumer migration, local-judge redesign, or legacy deletion in this slice.
- No fallback reader, alias, dual-write of a second candidate schema, directory search, task-prompt-file lookup, or old judge fixed-path dependency for the new handoff.
- No duplicate benchmark task load/acquisition, adapter-specific runner branch, evaluation data in `TaskSpec`, evaluation-only file in execution workspace, or mutation of a sealed snapshot/bundle.
- No silent model/API/cloud/reasoning/network/output fallback; no conversion of protocol/auth/quota/integrity/runtime failure into a score, tie, or success.
- No condition/arm/benchmark/model label in candidate identity/path; no volatile/runtime/path/secret data in semantic configuration fingerprints.
- No real model, judge, provider, paid API, or external network execution.
- No dependency, lock, workflow, coverage threshold, source-license, generated artifact, or unrelated documentation change.

## Closed decisions and unresolved items

Closed: deterministic candidate path; run-scoped opaque candidate ID; authoritative filename; staged legacy writer; exact snapshot-once strategy; configuration exclusions; typed network property; seal/index-before-evaluate ordering; runtime deletion boundary; minimal GDPval `task_inputs` wrapper correction; later-PR ownership.

Unresolved critical design decisions: none. If an accepted API makes the exact mapping impossible, stop implementation and return the concrete conflict to Sol rather than widening scope.
