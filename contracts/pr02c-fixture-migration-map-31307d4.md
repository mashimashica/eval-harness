<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR-02c fixture migration map and common CLI runtime-root amendment

**State:** bounded implementation instructions derived from the full all-suite diagnostic. This document is design evidence, not implementation or test evidence.

## Authority and inspected state

- PR-02c reconstructed contract: `contracts/pr02c-reconstruction.md`, accepted checkpoint commit `039f5524b8fc4a7d51f2bf2521cbdbf1a71cc705`, based on `d5ce0c10162cad788a17cb90f34b8f60574e7f75`.
- Accepted input-protection amendment: `contracts/pr02c-input-protection-amendment.md`.
- Canonical migration plan: `checkpoint/migration-control` commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, plan SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.
- Source inspected for this map: `31307d471c3e240ad2f3a52aa7a5514607e8b175`.
- Diagnostic inspected in full: `pr02c-diagnostic-66c01eef.log`, produced from earlier checkpoint `66c01eefbce311592a65e9bba7d294318be3139b`. It reports 526 tests with 33 errors and one failure. The generic-runner unavailable-revision error and configuration-fingerprint failure in that log are already corrected in source `31307d4`; they require no further fixture edit.

Most remaining diagnostic failures are fixture migrations caused by the fixed PR-02a/02b/03 contracts and the PR-02c `task_inputs` boundary. The apparent unavailable-revision fixture failures expose one real staged-consumer defect: `_SelectedTaskBenchmark` drops typed benchmark availability and custom snapshot hooks, then rejects the fresh canonical `BenchmarkTask` reconstructed by the common runner. That adapter must be repaired rather than weakening fixtures. All changes must preserve failure, protection, metric, provenance, snapshot, and durability assertions.

## Added CLI amendment and allowed paths

The accepted common Cursor integration requires durable output and disposable runtime roots to be supplied through the real `./eval run` entrypoint. Source `31307d4` exposes `runtime_root` in `run_benchmark` but not in the `run` CLI. The smallest accepted production amendment is therefore:

- `eval_harness/cli.py`: add only optional `--runtime-root` to the `run` subcommand and forward the parsed `Path | None` unchanged to `run_benchmark`.

Exact parser declaration:

```python
run_parser.add_argument(
    "--runtime-root",
    type=Path,
    help="Store disposable executor workspaces and logs outside the durable run output",
)
```

The `run_benchmark(...)` call in `_run` gains exactly `runtime_root=args.runtime_root`. Omission continues to pass `None`, preserving the runner's existing default. Do not normalize, resolve, create, validate, or derive this path in the CLI. Do not change stdout, exit-status, default-output, experiment, registry, or benchmark-specific behavior.

Production remains limited to the previously accepted PR-02c paths plus:

- `eval_harness/cli.py`
- `eval_harness/experiments/runner.py`, only for the `_SelectedTaskBenchmark` repair specified below

Fixture-only edits for this migration are limited to:

- `tests/harness/test_adapter_failure_coverage.py`
- `tests/harness/test_builder_experiment_runner.py`
- `tests/harness/test_cli_registry_reliability.py`
- `tests/harness/test_cursor_executor.sh`
- `tests/harness/test_executor_judge_reliability.py`
- `tests/harness/test_experiment_reliability.py`
- `tests/harness/test_generation_handoff.py`
- `tests/harness/test_reasoning_effort.py`
- `tests/harness/test_runner_reliability.py`

No other experiment change and no snapshot, candidate-bundle, manifest, evaluator, judge, sealer, loader, or registry production change is authorized by this map.

## Staged selected-task adapter amendment

`_SelectedTaskBenchmark` remains the existing one-task adapter used by the legacy experiment controller to invoke the common runner. It gains no fallback, second source, or new orchestration role. Repair it as follows:

1. In `__init__`, copy the fixed typed benchmark metadata directly from `original`: `name`, `source`, `source_availability`, `revision`, and `revision_availability`. Do not use `getattr`, infer availability from a value, or substitute unavailable metadata.
2. Override `snapshot_source_paths()` and return `self._original.snapshot_source_paths()` unchanged. This preserves the original adapter's source-stability protection.
3. Validate a supplied task by exact `TaskSpec` value: `task.execution == self._selected.execution`. This binds both canonical task ID and canonical prompt. Object identity is invalid because the common runner intentionally reconstructs `BenchmarkTask(execution=canonical_task)` from the verified snapshot. A mismatched ID or prompt raises the existing stable `ValueError("selected benchmark wrapper received a different task")` before calling the original adapter.
4. `snapshot_task(task, workspace)` validates the task, then calls `self._original.snapshot_task(self._selected, workspace)`. Passing the stored original task is required because concrete snapshot hooks consume its materialization/evaluation metadata and may publish distinct execution and evaluation file sets.
5. Retain `materialize` for the abstract benchmark surface, but apply the same value validation and delegate `self._original.materialize(self._selected, workspace)`.
6. `execution_task(task, workspace, *, network_policy)` applies the same value validation and delegates with `self._selected`, preserving original benchmark metadata while accepting the snapshot-reconstructed minimal task.
7. Keep `is_prepared`, `prepare`, and the exact `limit == 1` rule unchanged. Do not reload tasks, reacquire a source, rebuild evaluation data, or branch on benchmark name.

Add a focused regression in `test_builder_experiment_runner.py` using a fixture benchmark with an existing source file and a custom `snapshot_task`. The custom hook must return different execution and evaluation file projections plus private evaluation data, and record that it received the stored original task. Through a real `_SelectedTaskBenchmark.acquire_snapshot(...)`, assert:

- source and revision values and both `Availability.AVAILABLE` states survive;
- the original `snapshot_source_paths` and `snapshot_task` hooks are called;
- execution and evaluation views contain only their respective exact files/data;
- `execution_task(BenchmarkTask(execution=snapshot_task.task_spec()), ...)` succeeds and delegates the stored task;
- a changed ID or changed prompt fails before either original materialization/execution hook runs.

This regression must use real snapshot acquisition and verification. It must not mock acquisition, binding, source fingerprinting, or view construction.

## Fixed fixture contracts

Every `Executor` fake used by the common runner must expose an exact `ExecutorCapabilities` value. Import `ExecutorCapabilities`, `ExecutorInput`, and `ExecutorOutput` from `eval_harness.capabilities`. Preserve the fake's existing preflight and result identities; a fixture must not replace version, auth, runtime, invocation, path, or reasoning evidence with `None` to avoid validation.

| Fixture | Inputs | Outputs | Required result alignment |
|---|---|---|---|
| `test_builder_experiment_runner._ApplicationExecutor` | `PROMPT_TEXT`, `WORKSPACE_FILES` | `FINAL_TEXT` | Successful result retains final text and declares exactly `FINAL_TEXT`; failure declares no outputs. |
| `test_experiment_reliability.ReliabilityApplicationExecutor` | `PROMPT_TEXT`, `WORKSPACE_FILES` | none | It currently produces no text or artifacts, so every result declares no outputs. |
| `test_experiment_reliability.ReliabilityBuilderExecutor` | `PROMPT_TEXT`, `WORKSPACE_FILES` | `ARTIFACT_FILES` | Preserve the real skill artifact and declare exactly `ARTIFACT_FILES` on success. |
| `test_reasoning_effort._FakeExecutor` | `PROMPT_TEXT`, `WORKSPACE_FILES` | `FINAL_TEXT`, `ARTIFACT_FILES` | The fake writes its answer/skill deliverable and returns text, so its successful `available_outputs` must contain both. |
| `test_runner_reliability.ReliabilityExecutor` | `PROMPT_TEXT`, `WORKSPACE_FILES` | `FINAL_TEXT` | Successful/no-deliverable behavior and failed empty-output behavior remain explicit. |

The corresponding fixed evidence pairs remain exact:

- `_ApplicationExecutor`: preflight/result version `application-1`, auth `test`, runtime `test`, invocation `fake`, requested effort `None`.
- `ReliabilityApplicationExecutor` and `ReliabilityBuilderExecutor`: version `1`, auth `local`, runtime `test`, invocation `deterministic`, requested effort `None`.
- `_FakeExecutor`: version `fake-codex-1`, auth `fake`, runtime `test`, invocation `fake-codex`, result requested effort equal to its configured `reasoning_effort`.
- `ReliabilityExecutor`: version `reliability-executor-v1`, auth `local`, runtime `test`, invocation `reliability`, requested effort `None`.

## File-by-file migration

### `tests/harness/test_builder_experiment_runner.py`

1. Give `_ApplicationExecutor` the exact capability contract above.
2. Keep `_Benchmark.revision == "revision-1"`; give it a stable nonempty `source`, `source_availability = Availability.AVAILABLE`, and `revision_availability = Availability.AVAILABLE`. Preserve the outer experiment assertion `revision_status == "available"` and add the corresponding source-status assertion. Its existing default `snapshot_task` must bind the same `benchmark.txt` bytes previously produced by `materialize`, now under `task_inputs/benchmark.txt`.
3. Preserve every existing schedule, task-order, intervention application ID, artifact, source-input, fingerprint, metric, and stop-on-failure assertion.
4. Where a successful application already reads nested `run-metadata.json` and legacy `results.jsonl`, additionally use the real `load_run_manifest`, `VerifiedSnapshotBinding.load`, and `load_run_results`. Assert one identity/path-conformant indexed candidate for that application, the exact snapshot task/reference, final text, intervention provenance, and completed evaluation. Retain the existing `accuracy == 1.0` and outer aggregation checks.
5. For the typed failed application case, strictly load the indexed failed bundle and assert `PROCESS/test_failure/RUN`, no output channels/text, and skipped evaluation. The following schedule entry remains unbuilt. For a direct exception or `KeyboardInterrupt` thrown before a valid `ExecutionResult`, accept a created manifest/index with zero indexed candidates; never fabricate a candidate.

### `tests/harness/test_experiment_reliability.py`

1. Keep `ReliabilityBenchmark.revision == "revision"`; give it a stable nonempty `source`, `source_availability = Availability.AVAILABLE`, and `revision_availability = Availability.AVAILABLE`. Its empty default snapshot content remains valid. Where metadata is asserted, require available source and revision status.
2. Add the exact application and builder capability contracts above. Preserve Builder artifact bytes, manifest/source evidence, application task provenance, `score == 1.0`, outer counts, and evaluator-call counts.
3. Map typed application terminal failures exactly:
   - `INTERRUPTED` -> `Failure(INTERRUPTED, "interrupted", RUN)`;
   - `TIMED_OUT` -> `Failure(TIMEOUT, "timeout", RUN)`;
   - `FAILED` -> `Failure(PROCESS, "test_failure", RUN)`.
4. Add strict manifest/bundle loading to the existing success, typed-failure, and typed-interruption coverage using the same rules as the builder fixture above. A typed application failure is indexed and prevents evaluation. A Python exception before a valid result leaves no fabricated row. Preserve all partial experiment-journal assertions.

### `tests/harness/test_reasoning_effort.py`

1. Keep `_FakeBenchmark.revision == "reasoning-revision"`; give it a stable nonempty `source`, `source_availability = Availability.AVAILABLE`, and `revision_availability = Availability.AVAILABLE`. The fixture is shared by direct and legacy experiment tests, and both paths must preserve the same available metadata.
2. Add `_FakeExecutor.capabilities` and align its successful `available_outputs` to both `FINAL_TEXT` and `ARTIFACT_FILES` as specified above. Keep requested reasoning effort identical in configured executor and `ExecutionResult`.
3. In the direct-run configuration assertion, remove `runtime_layout` from the exact `configuration` key set and assert it is absent. Continue to assert top-level `run-metadata.json["runtime_layout"] == "run-output"` for the default layout.
4. The nested executor configuration has a stable `reasoning_effort_requested` field even when unset. Change the baseline nested assertion to `is None`; keep the top-level baseline metadata field absent. Preserve all requested-effort, configuration-digest, fingerprint, legacy resume, old-Codex `max`, process-exit, and stopped-evaluation assertions.
5. Assert the nested executor capability projection is exactly inputs `prompt_text`, `workspace_files` and outputs `artifact_files`, `final_text` in canonical sorted order.

### `tests/harness/test_runner_reliability.py`

1. Preserve `ReliabilityBenchmark.revision = "reliability-revision"` and explicitly set `revision_availability = Availability.AVAILABLE` after importing `Availability` from the snapshot module.
2. Give `ReliabilityExecutor` the exact capability contract above.
3. Correct its failure construction and the systemic-failure test expectations:

| Execution status | Failure kind | Code | `RunAbort` text | Run metadata status |
|---|---|---|---|---|
| `FAILED` | `PROCESS` | `test_failure` | `test_failure` | `failed` |
| `TIMED_OUT` | `TIMEOUT` | `timeout` | `timeout` | `failed` |
| `INTERRUPTED` | `INTERRUPTED` | `interrupted` | `interrupted` | `interrupted` |

All three remain run-impact failures with no output channels/text. For each, retain `evaluator.calls == 0`, evaluation status `skipped`, empty metrics/outcomes, the stable skip detail, and durable status counts.
4. Where the existing reliability cases inspect a legacy row, add strict manifest/result loading sufficient to prove that typed returned failures are sealed and indexed before abort. Cases that raise directly from `execute`, intervention application, or evaluator retain their existing phase-specific durability expectations and must not gain fabricated successful bundles.
5. `reference_files` paths in this module are judge-presentation fixtures, not Cursor execution inputs. Leave them unchanged.

### `tests/harness/test_adapter_failure_coverage.py`

Only Cursor execution-input fixtures change. The `_judge_request` helper and every judge-only `reference_files` assertion remain unchanged.

1. In `test_cursor_reference_isolation_restores_on_symlink_failure_and_replaces_stale_protection`, use `workspace/task_inputs`, sibling `cursor-task-inputs-readonly`, and `_isolate_task_inputs`. Keep the forced `Path.symlink_to` failure, unchanged source bytes, restored real input directory, and stale-protection cleanup assertions.
2. In `test_cursor_execution_handles_no_deliverable_interrupt_and_replacement_decoding`, create `task_inputs/source.txt` for the interrupted Cursor request. Preserve the exact interrupted result, empty outputs/text, `INTERRUPTED/interrupted/RUN`, durable log, and unchanged restored real inputs.
3. In `test_cursor_execution_restores_references_and_fails_on_mutation_or_timeout`, rename the execution paths/helpers to `task_inputs`, mutate `task_inputs/input.txt`, and use metadata key `task_inputs_integrity_verified`. Preserve:
   - success restores a real directory with unchanged bytes and records verified integrity;
   - late mutation clears output text and outputs and returns exact `INTEGRITY/task_input_mutation/RUN` with false integrity metadata and a stable log;
   - timeout stays `TIMEOUT/timeout/RUN`, and interruption stays `INTERRUPTED/interrupted/RUN`; cleanup or hashing must not mask either primary failure;
   - direct `_isolate_task_inputs`/`_restore_task_inputs` no-input and cleanup checks remain.

### `tests/harness/test_executor_judge_reliability.py`

Only the Cursor executor block changes. Pairwise/judge presentation and judge isolation continue to use `reference_files`.

1. The fake Cursor command mutates `cursor-task-inputs-readonly/input.txt`. Real Cursor execution setup and restoration use `task_inputs`; policy assertions use `Write(task_inputs/**)`, `additionalReadonlyPaths`, `cursor-task-inputs-readonly`, `task_inputs_isolation`, and `task_inputs_integrity_verified`.
2. Rename the direct isolation/restore helper calls to `_isolate_task_inputs` and `_restore_task_inputs`. Keep stale protection, symlink-creation failure, restoration, mutation, timeout, interruption, subprocess-error, durable-log, and environment-scrubbing coverage.
3. Update the low-level tree-digest expectations to the final fail-closed implementation: missing, symlinked, or non-directory roots raise the stable integrity exception; a real empty directory has a digest; and adding a nested empty directory changes that digest because directory structure is bound. Retain secret-environment scrubbing assertions. Do not recreate the old behavior in which absent and empty/nested-empty trees shared a digest.

### `tests/harness/test_cursor_executor.sh`

Keep this script as the staged legacy negative and preflight coverage; it must no longer claim a successful old-path Cursor execution.

1. Keep the temporary GDPval row that materializes `reference_files`, then run old `./gdpval run --executor cursor`. Require nonzero exit, the exact diagnostic `Cursor executor does not accept the legacy reference_files input namespace`, no `-p` entry in the argument log, no deliverable, and unchanged reference bytes.
2. Remove the old-path success checks for copied reference files, deliverable output, prompt, policy metadata, and completed results.
3. Retain the no-limit rejection and API-key/account-auth preflight negatives, including zero execution/model calls. Judge fixtures are not routed through this bridge.

### `tests/harness/test_cli_registry_reliability.py`

1. Add `runtime_root: None` to `run_args` defaults.
2. Parser coverage must assert omission yields `None`, `--runtime-root runtime/place` yields `Path("runtime/place")`, and `run --help` contains both `--runtime-root` and the exact help text above.
3. Update the existing `_run` routing test to assert the supplied `Path` and omitted `None` are forwarded as the `runtime_root` keyword. That mocked routing test is only argument plumbing evidence; it cannot satisfy generation/handoff acceptance.
4. Do not change experiment `--runtime-root`, generic output JSON, validation ordering, or default output behavior.

### `tests/harness/test_generation_handoff.py`

Add one common CLI Cursor integration beside the existing unknown-benchmark handoff tests. It must call the real handler:

```python
cli.main([
    "run",
    "fixture-cursor",
    "--executor",
    "cursor",
    "--limit",
    "1",
    "--out",
    str(out_root),
    "--runtime-root",
    str(runtime_root),
])
```

Local fixture substitution may patch only the CLI's descriptor/factory lookups: `get_benchmark_descriptor`, `get_executor_descriptor`, `create_benchmark`, `create_evaluator`, and `create_executor`. They return a neutral snapshot-backed fixture benchmark, native fixture evaluator, and real `CursorExecutor(command=str(fake_command))`. The descriptor allows Cursor for `fixture-cursor`. Do not patch or wrap `run_benchmark`, `RunResultWriter`, candidate sealing/indexing, `load_run_manifest`, `load_run_results`, or `VerifiedSnapshotBinding`.

The fake command must implement production preflight and execution behavior without network/model access:

- `--version` returns the exact supported Cursor build.
- `status --format json` returns the documented authenticated account schema, with a temporary valid account-only Cursor auth store and API/provider environment variables removed.
- `-p` records its invocation and verifies during execution that `workspace/task_inputs` is a symlink, legacy `reference_files` is absent, the resolved sibling occurs in `.cursor/sandbox.json.additionalReadonlyPaths`, and `.cursor/cli.json` denies `Write(task_inputs/**)`.
- It reads the exact neutral task input, writes a nested deliverable, and emits one valid documented Cursor JSON result.

The test must then establish all of these facts:

1. Version/status preflight ran, exactly one `-p` execution ran, and no judge/model/network bridge ran.
2. The runtime workspace's visible `task_inputs` is restored as a real directory with unchanged bytes after execution.
3. The typed result records exact Cursor version, `cursor-account` auth, host-subprocess runtime, `agent -p` invocation, selected model semantics, exact capabilities, and true task-input integrity.
4. Real manifest and snapshot binding loaders resolve one indexed, path-conformant CandidateBundle containing the final text and exact nested artifact bytes. Keep the immediate evaluator's native metric assertion as staged legacy behavior.
5. Delete the external runtime root and strictly load the same bundle again. Move the entire durable output tree and reopen its manifest, snapshot binding, index, text, and artifact successfully from the new path.

The existing fake-executor relocation test remains useful but cannot substitute for this real `CursorExecutor` CLI path.

## Prohibitions

- Do not add a legacy Cursor input fallback, translate `reference_files` to `task_inputs`, accept both namespaces, or route the legacy shell success through `local_judge_runner`.
- Do not mock/wrap the common runner, sealer, index writer, manifest/snapshot/bundle loader, or evaluator success in the new Cursor integration.
- Do not remove existing metric/denominator, evaluator-call, stop-before-evaluation, source-byte, artifact, provenance, secret-scrubbing, timeout, interruption, or durable-log assertions merely to satisfy the stricter contracts.
- Do not make fake capabilities wider than the channels actually produced.
- Do not set a real or fixture revision to `None`, alter an available-revision assertion to unavailable, or infer availability to bypass snapshot validation. Declare coherent typed source/revision availability and repair the staged adapter.
- Do not modify production experiment orchestration. PR-09 owns its neutral consumer migration.
- Do not invoke a real Cursor/model/judge or use network access.

## Required verification and expected result

After the active Cursor source-regression batch is durably saved, run the changed Python modules, `tests/harness/test_cursor_executor.sh`, strict mypy on changed typed Python and production files, Ruff on changed Python files, and the full unittest discovery command used by `pr02c-diagnostic-66c01eef.log`. Expected result: all pass with zero real model, judge, or network calls.

The common CLI integration must fail if it accidentally uses the default in-output runtime layout, bypasses task-input protection, evaluates before candidate indexing, depends on the deleted runtime root, or stores absolute/runtime paths in the bundle. The legacy GDPval Cursor case must fail before `-p` exactly as specified.

All decisions in this finite migration map are closed. Any newly observed production defect requires a separate reviewed amendment; fixture failures should be resolved only within the paths and invariants above.
