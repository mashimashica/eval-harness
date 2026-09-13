<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR-02c amendment: protect bound `task_inputs`

Status: accepted scope amendment to `contracts/pr02c-reconstruction.md`. This amendment closes a protection regression discovered during PR-02c implementation; it does not recover lost source or change the fixed snapshot/bundle/manifest APIs.

## Authority and reason

- PR-02c contract: saved commit `039f5524b8fc4a7d51f2bf2521cbdbf1a71cc705`, parent/base `d5ce0c10162cad788a17cb90f34b8f60574e7f75`.
- Canonical plan: `checkpoint/migration-control` commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, plan SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`; §§3.1–3.3 and 5.1 require explicit execution views, immutable content evidence, fail-closed integrity, and migration of real protection tests.
- Accepted PR-01 snapshots materialize benchmark execution inputs as `workspace/task_inputs`. At the PR-03 head, Cursor instead isolates, denies writes to, digests, and restores only `workspace/reference_files`. PR-02c would therefore silently bypass Cursor's existing read-only input protection.
- `FilesIntervention` rejects replacement of an existing path but currently permits adding a new file beneath an existing `task_inputs` directory. Existing collision/non-overwrite checks do not protect the benchmark-owned namespace.

## Added allowed paths

Production changes added to the PR-02c allowlist:

- `eval_harness/executors/cursor.py`
- `eval_harness/interventions/files.py`

Primary tests:

- `tests/harness/test_generation_handoff.py`
- `tests/harness/test_cursor_executor.py`
- `tests/harness/test_file_intervention.py`

The following files contain Cursor `reference_files` fixtures found by repository-wide `rg`; they may change only where needed to replace Cursor input-isolation names, paths, metadata, failure codes, or the staged legacy expectation:

- `tests/harness/test_adapter_failure_coverage.py`
- `tests/harness/test_executor_judge_reliability.py`
- `tests/harness/test_cursor_executor.sh`

`tests/harness/test_execution_capabilities.py` also contains a generic manually constructed `reference_mutation` failure, but it is not a Cursor fixture and should remain unchanged unless the implementation proves a direct compile/test dependency. References used solely by judge presentation/isolation remain `reference_files` and are outside this amendment.

No other production path is allowed. In particular, do not change `eval_harness/local_runner.py`, snapshot/bundle/manifest contracts, evaluator/judge code, registries, or experiment code.

## Exact behavior

### Cursor

Replace the Cursor-specific execution-input implementation; do not add a second lookup or fallback:

- `_isolate_reference_files` becomes `_isolate_task_inputs` and examines exactly `workspace / "task_inputs"`.
- `_restore_reference_files` becomes `_restore_task_inputs` and restores exactly that path.
- The protected sibling path is exactly `workspace.parent / "cursor-task-inputs-readonly"`.
- `.cursor/cli.json` denies exactly `Write(task_inputs/**)` for benchmark inputs; it must not retain `Write(reference_files/**)` as a compatibility alias.
- `.cursor/sandbox.json.additionalReadonlyPaths` contains the resolved protected sibling when `task_inputs` is present.
- A present `task_inputs` symlink or non-directory is rejected before `subprocess.run`. On platforms where the protected symlink cannot be created, restore the original directory and raise the current clear fail-closed symlink-support error before invocation.
- Hash the protected `task_inputs` tree before invocation and again before restoration. Mutation yields `ExecutionStatus.FAILED`, no output channels/text, and the exact `Failure(FailureKind.INTEGRITY, "task_input_mutation", FailureImpact.RUN)`; subsequent tasks/evaluation stop under the existing runner rules.
- Always restore the original real `workspace/task_inputs` directory after success, nonzero exit, malformed protocol, timeout, interruption, spawn failure, or detected mutation.
- Cursor metadata keys become `task_inputs_isolation` and `task_inputs_integrity_verified`; remove the replaced `reference_files_isolation` and `reference_integrity_verified` keys. Stable value text may describe `outside-workspace + additionalReadonlyPaths` without an absolute path.
- A present or symlinked legacy `workspace/reference_files` is rejected with `ValueError("Cursor executor does not accept the legacy reference_files input namespace")` before policy subprocess/model invocation. Do not isolate both namespaces, infer which is newer, rename legacy input, or continue without protection.
- Absence of both namespaces remains valid for prompt-only tasks.

### Files intervention

`FilesIntervention` must reserve both case-folded top-level names `task_inputs` and `reference_files` during the staged migration:

- `task_inputs` protects the authoritative PR-02c execution view.
- `reference_files` remains reserved only because the old runner still executes before PR-10; blocking writes into it is a guard, not an input alias or fallback.
- A source containing either exact or case/Unicode-colliding spelling fails preflight, produces no bundle, and performs no workspace/model write.
- PR-10 removes the obsolete `reference_files` reservation together with the old runner. PR-02c must not remove other existing reserved roots.

## Required tests and expected results

1. Cursor unit tests use `task_inputs/input.txt`. During the fake invocation the visible path is a symlink, its resolved sibling is listed in `additionalReadonlyPaths`, and `Write(task_inputs/**)` is denied. After each non-mutation terminal path the visible input is a real directory with unchanged bytes.
2. A fake mutation of `task_inputs/input.txt` returns the exact run-impact integrity failure above, empty outputs, false `task_inputs_integrity_verified`, a stable mutation diagnostic, and restores the visible path as a real directory. The disposable execution copy may contain the detected mutation; the sealed source snapshot must remain unchanged and no candidate is fabricated from it. A symlink/non-directory input and forced symlink-creation failure make zero subprocess/model calls and preserve source bytes.
3. A legacy `reference_files` workspace makes zero `-p`/execution calls and raises the exact `ValueError`; bytes remain unchanged. Update `tests/harness/test_cursor_executor.sh` so its old `./gdpval ... --executor cursor` case expects a nonzero command, no `-p` entry, no deliverable, and the stable legacy-namespace diagnostic. Do not leave an old-path Cursor success assertion.
4. Port the removed substantive success/protection coverage to the common PR-02c generation path. Drive `eval_harness.cli.main(["run", ...])` (the `./eval` handler) with registered/patched local fixture factories, a neutral snapshot-backed benchmark, the real `CursorExecutor` around a fake local command, separated out/runtime roots, and no network/model. Assert preflight plus one execution, task-input isolation during the call, restored input, typed result provenance, sealed/indexed bundle artifact/text, and strict handoff load after runtime deletion. Factory substitution may supply local fixtures; do not monkeypatch `run_benchmark`, sealing, indexing, or loaders.
5. `FilesIntervention.preflight()` rejects source roots containing `task_inputs/x`, `Task_Inputs/x`, `reference_files/x`, and a case variant. It still accepts an unrelated top-level file. Application cannot add or overwrite any benchmark input.
6. Existing Cursor auth/network/protocol/timeout/interruption tests and non-Cursor judge `reference_files` tests retain their meanings. Focused and full unchanged PR-02c quality gates pass with zero real model/judge/network calls.

## Done and ownership

- Luna owns the implementation branch and is the only code writer. This amendment and its hash must be added to the PR-02c work record and durably checkpointed before production scope expands.
- Sol reviews that the new generation path actually exercises input protection and that legacy Cursor fails closed rather than falling through. Astra accepts the amended PR-02c head after required CI.
- Checkpoint, validation, and acceptance remain separate facts. No PR-02c acceptance is allowed while `task_inputs` is writable through the previously claimed Cursor protection or injectable through `FilesIntervention`.
