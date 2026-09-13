<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR-02c independent review of checkpoint `4948b2c3`

Status: review findings for a saved work-in-progress checkpoint. This is not PR-02c acceptance and does not claim that its required tests or CI pass.

## Reviewed identity and authority

- Repository: `mashimashica/eval-harness`.
- Durable checkpoint: `checkpoint/pr-02c` commit `4948b2c3f85ca82d94e44734de532c8769d7b04e`, tree `e557804dcdac7e28ce3a6f3bacc2fb6962167b35`.
- Immutable implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`, tree `354943ebbb8ea81a30523bfdc12baf26771853b5`.
- Governing contracts: `contracts/pr02c-reconstruction.md` and `contracts/pr02c-input-protection-amendment.md`.
- Canonical plan: control commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.
- Review was read-only. No production source or implementation branch was changed by the reviewer.

## Required source corrections

### P1 — Cursor finalization must always restore inputs and return a valid typed failure

In `eval_harness/executors/cursor.py`, `_isolate_task_inputs()` runs before `_write_workspace_policy()` and the prompt write, while the `try/finally` starts afterward. A policy or prompt write error can therefore leave the original directory moved and `workspace/task_inputs` as a symlink. The protection lifecycle must enter a `try/finally` immediately after successful isolation so every later exit attempts restoration and performs no model fallback.

The final digest or restore step can also add an integrity `Failure` after a successful response was parsed without clearing `output_text`. Constructing `ExecutionResult` then raises its own failed-result invariant instead of returning the typed failure. Use one finalization rule:

- Preserve an already typed timeout, interruption, process, protocol, auth, or quota failure; a cleanup/hash diagnostic must not replace the primary failure.
- If there is no primary failure, a detected byte mutation produces exactly `Failure(FailureKind.INTEGRITY, "task_input_mutation", FailureImpact.RUN)`; an unverifiable tree or failed restoration uses a stable integrity code.
- Every failed result clears `output_text`, reports no available output channels, and uses `ExecutionStatus.FAILED` except where an existing typed timeout/interruption status is preserved.
- Restore the visible real directory after success, nonzero exit, malformed protocol, timeout, interruption, spawn failure, mutation, setup failure after isolation, and cleanup failure whenever restoration remains possible.

Add focused tests that force a failure in policy creation, prompt persistence, the final digest, and restoration after an otherwise successful parse. Each must make the typed status/failure/output invariants and final visible-path state explicit.

### P1 — Bind all snapshot metadata to the verified sealed digest

`eval_harness/runner.py` verifies every returned task against `VerifiedSnapshotBinding`, but later reads benchmark ID, source/revision availability, source/revision, and summary identity from the object returned by the overridable `Benchmark.acquire_snapshot`. The sealed directory must remain authoritative for all those semantics.

No binding API expansion or second file load is needed. Before either planned root is created:

1. Require `type(snapshot) is BenchmarkSnapshot`.
2. Require `snapshot.compute_snapshot_sha256() == snapshot.snapshot_sha256`.
3. Require that digest to equal `temporary_binding.reference(snapshot.tasks[0].task_id).snapshot_sha256`.
4. Keep the existing ordered task-by-task equality checks against `temporary_binding.resolve(reference)`.

The snapshot digest covers benchmark ID, source and availability, revision and availability, and ordered task semantics. The equality checks therefore bind the returned immutable metadata to the exact sealed snapshot without accessing a private binding member. A mismatch must fail before `out`/`runtime` creation and before executor/evaluator calls.

### P1 — Preserve legacy `evaluation: null` for pre-execution intervention failure

The staged old record used `evaluation: null` when intervention application failed or was interrupted before an executor result existed. The WIP routes these cases through `_evaluation_error_payload()` or `_evaluation_interrupt_payload()`, changing current consumer behavior and producing an evaluation-error message for a failure in another phase.

Type the legacy persistence helper to accept an optional evaluation payload and persist `None` for both intervention-application failure paths. Keep their intervention evidence and outer run status unchanged. Candidate handoff rows remain absent because no valid `ExecutionResult` exists.

### P1 — Reject contradictory executor evidence before sealing

When evaluator/executor preflight returns a known executor version or auth mode, a result with a missing value currently bypasses the mismatch checks. The runner also records configured requested reasoning effort in `RunManifest.configuration` while accepting a different `ExecutionResult.reasoning_effort_requested` into `ExecutorEvidence`.

Before candidate sealing, require:

- if preflight version is known, `result.executor_version == executor_preflight.version`;
- if preflight auth mode is known, `result.auth_mode == executor_preflight.auth_mode`;
- `result.reasoning_effort_requested == reasoning_effort`, where `reasoning_effort` is the already validated typed executor request.

Mismatch is an existing executor-result integrity/identity error: persist the staged legacy failure row, create no CandidateBundle/index row, call no evaluator, and re-raise. Do not silently prefer one evidence source.

### P2 — Use concrete types in the legacy persistence helper

`persist_legacy_row()` accepts `task_layout_value: object` and uses `hasattr()` before dynamically reading `executor_dir`. Import and accept the fixed `TaskLayout` type directly. Type the execution result and evaluation payload as their actual optional forms. This is a local quality correction, not a compatibility hook.

### P2 — Restore real materialized-intervention evidence coverage

The WIP changed `FakeIntervention.materialized_files` from a fabricated file entry to empty and weakened the assertion to an empty list so strict bundle validation would pass. A prompt-overlay intervention correctly has no materialized workspace files, but the prior provenance boundary still needs a valid test.

Keep the prompt-overlay fixture internally coherent, and add a real or exact fake files intervention that writes the declared bytes, returns matching `InterventionFile` evidence, seals successfully, and retains assertions over path, size, SHA-256, bundle/manifest binding, and absence of source paths/secrets. Do not reintroduce fabricated evidence.

## Planned work still absent at this WIP checkpoint

These are accepted-contract tasks still to implement, rather than additional design findings:

- `eval_harness/benchmarks/gdpval.py` still lists and protects `reference_files`; it must consume the bound `task_inputs` namespace exactly as specified.
- The existing Cursor fixtures in `test_executor_judge_reliability.py`, `test_adapter_failure_coverage.py`, and `test_cursor_executor.sh` still exercise removed legacy success behavior and must be migrated. The old `./gdpval` Cursor case becomes the required pre-invocation rejection.
- The required `./eval` end-to-end Cursor generation test and the comprehensive `test_generation_handoff.py` cases are absent.
- Remaining generic-runner, reliability, reasoning, snapshot, boundary, experiment-fixture, strict typing, coverage, and unchanged CI gates have not passed on this checkpoint.

## Verification evidence at review time

The reviewed source compiled. A focused run of `test_executor_judge_reliability.py` plus `test_adapter_failure_coverage.py` collected 43 tests and produced 38 passes, 26 passing subtests, and seven failures. All seven failures were attributable to unmigrated Cursor `reference_files` fixtures or removed helper names. A broader partial run exposed additional fixture updates still required for typed executor capabilities, snapshot materialization paths, revision availability, and expanded executor descriptors; it was stopped after 13 failures and is not acceptance evidence.

The final review gate is the exact corrected, durably saved head with the full contract suite and unchanged repository CI. No real model, judge, provider, paid API, or external-network execution is part of this review.
