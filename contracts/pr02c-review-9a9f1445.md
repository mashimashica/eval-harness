<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR-02c independent production review of checkpoint `9a9f1445`

Status: finite production-source findings for the saved PR-02c checkpoint. This is not PR-02c acceptance. The fixture migrations, required negative cases, full quality gates, and formal acceptance remain separate work.

## Reviewed identity and authority

- Repository: `mashimashica/eval-harness`.
- Reviewed checkpoint: `9a9f144537f4dc276e18c029666be229547e371c`, tree `8ac9d43a7a720fdb1d1cf4ae35103ca5bc1dd2be`.
- Immutable implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`, tree `354943ebbb8ea81a30523bfdc12baf26771853b5`.
- Governing contracts: `contracts/pr02c-reconstruction.md` and `contracts/pr02c-input-protection-amendment.md`.
- Canonical plan: control commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, plan SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.
- Review scope: the five changed production files only. The review did not modify the implementation checkpoint or production source.

## Required source corrections

### P1 — Cursor's tree digest permits deterministic mutation collisions and accepts a missing protected tree

`eval_harness/executors/cursor.py:68-81` hashes each path length and path followed by unframed file bytes. It does not include the content length, entry type, or empty directories; it follows file symlinks; and it returns the SHA-256 of empty input when the root is missing or is not a directory. `CursorExecutor._restore_task_inputs()` at lines 352-361 then silently does nothing when the protected root is not a directory and can rename a protected symlink back as the visible input.

This is an exploitable encoding ambiguity without finding a SHA-256 collision. These distinct trees produce the same current digest:

- tree A: file `a` contains `b"X"`; file `b` contains `b"Y"`;
- tree B: its only file `a` contains `b"X" + (1).to_bytes(8, "big") + b"bY"`.

An exact-checkpoint fake invocation replaced tree A with tree B. Cursor returned `completed`, `failure=None`, and output `answer`, then restored the mutated one-file tree. A second reproduction deleted an originally empty protected directory; Cursor likewise returned success and left `workspace/task_inputs` absent.

Replace this with an unambiguous, fail-closed tree seal. It must frame entry type, logical path, and regular-file content length/content; preserve the directory structure if the contract claims it; reject symlinks and special entries; and treat a missing or non-real protected root as an integrity failure. Restoration must require a real protected directory or raise the stable restoration integrity failure. Every exit after moving the original directory, including interruption during symlink creation, must attempt restoration. Add real-tree tests for the framed collision above, protected-root deletion/type replacement, an internal symlink, and the final visible real-directory state.

### P1 — A post-execution input-verification error is mislabeled as a process-spawn failure

The first post-subprocess `_tree_digest()` call at lines 420-425 remains inside the broad `except OSError` at lines 455-460. If the model process returns successfully but the protected tree cannot be read, that exception is handled as `Failure(FailureKind.PROCESS, "process_spawn", FailureImpact.RUN)`. The second failed digest in `finally` preserves this newly fabricated process failure.

An exact-checkpoint reproduction using digest outcomes `"baseline"`, `OSError`, `OSError` returned `failed/process/process_spawn` with `task_inputs_integrity_verified=False`. No process launch failed. Run the post-execution and final input checks through one explicit finalization path. When no earlier typed failure exists, an unverifiable protected tree must produce the stable `INTEGRITY/task_input_integrity` failure. When timeout, interruption, process, or protocol failure already exists, retain that primary failure and attach only a stable cleanup diagnostic.

### P2 — Log-write cleanup can erase an already typed execution failure

`stdout.log` and `stderr.log` are written unguarded in the `finally` block at lines 494-495. A log persistence error therefore escapes instead of returning an already established timeout, interruption, process, protocol, or integrity `ExecutionResult`. An exact-checkpoint reproduction with `TimeoutExpired` followed by `OSError("log full")` while writing `stdout.log` raised the raw `OSError`; the promised typed timeout was lost.

Guard both writes independently. Preserve an existing typed failure/status, expose a stable secret-free log-persistence diagnostic, and keep failed-result output channels empty. Define and test the fail-closed behavior for a log-write failure after an otherwise successful parse as well as after each existing primary failure class.

### P2 — Repository dirty evidence observes the run's own output

`eval_harness/runner.py:662` calls `repository_provenance()` after publishing the snapshot, candidate index, and run manifest and after creating an external runtime root. When a caller selects an unignored path inside the source repository, the recorded dirty state describes the newly created run files rather than the source state that began the run.

In an exact-checkpoint clean temporary git checkout, a run to `unignored-run/` began with empty porcelain status but persisted `repository.worktree_status == "dirty"`. Move the single `benchmark.prepare()` before controller staging, capture repository provenance after preparation and before creating the staging/output/runtime paths, and reuse that captured outer record later. This retains preparation-induced source changes without allowing the run to contaminate its own evidence. Add an ordering regression that inspects root existence when provenance is captured.

## Verified production behavior

The runner's core handoff ordering conforms to the accepted contract:

- evaluator, intervention, and executor preflights occur before benchmark preparation and model work;
- one sealed temporary snapshot is checked against its returned exact `BenchmarkSnapshot`, all tasks/plans are bound before publication, and the published binding is reopened;
- the authoritative `RunResultWriter` is created before `run-manifest.json` is published;
- each identity/path/channel-conformant `ExecutionResult` is sealed at the deterministic candidate path and indexed before evaluator dispatch or systemic `RunAbort`;
- configuration excludes run IDs, runtime paths/layout, repository evidence, arbitrary preflight details, result metadata/model evidence, and environment values;
- runtime deletion and full-out relocation use only the manifest, bound snapshot, candidate index, and bundle links;
- GDPval's execution wrapper uses only `task_inputs`; `FilesIntervention` reserves both staged names; common runner/layout contain no benchmark/vendor branch.

The earlier `4948b2c3` review corrections for snapshot metadata binding, strict executor provenance, legacy `evaluation: null`, concrete helper types, coherent materialized-file evidence, setup-time Cursor restoration, late-output clearing, and the GDPval wrapper are present at this checkpoint. The structural Cursor issues above remain.

## Independent verification evidence

From an archive of exactly `9a9f144537f4dc276e18c029666be229547e371c`:

- `tests.harness.test_generation_handoff` plus `tests.harness.test_cursor_executor`: 21 tests passed;
- strict mypy: no issues in the five changed production files;
- Ruff lint and format checks: passed for the five changed production files;
- `git diff --check` against the immutable base: passed for the five changed production files.

The collision, missing-root, wrong-failure-kind, log-write masking, and self-dirty provenance behaviors were separately reproduced with local fakes and no model, judge, provider, paid API, or network call.

## Acceptance work deliberately not reclassified as source findings

At this saved checkpoint, the contract's systemic-failure, seal/index/path/capability, tamper/missing-byte, real `./eval` Cursor handoff, enumerated legacy Cursor fixture migrations, and full repository quality gates were still recorded as unfinished test work. Passing the 21 focused tests does not close those gates. They must run against the corrected saved production head before Astra acceptance.
