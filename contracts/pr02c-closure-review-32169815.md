<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR-02c closure review of four production findings at `32169815`

**Result:** all four production findings recorded in `contracts/pr02c-review-9a9f1445.md` are resolved in the exact reviewed source. No remaining finding was identified within this bounded closure scope.

## Reviewed identity and scope

- Repository: `mashimashica/eval-harness`.
- Reviewed commit: `32169815cd455f3c5929ca643ebc69fe00260969`.
- Reviewed tree: `ea524ff73208cd7764257388293c1511c97b422b`.
- Governing findings: the two Cursor P1 findings, Cursor log-write P2 finding, and repository-provenance P2 finding in `contracts/pr02c-review-9a9f1445.md`.
- Source review used a separate `git archive` of exactly the reviewed commit. The reviewed archive blobs matched the commit: `cursor.py` `7e9e4990fa808a83f1bfb84f56228fc12594a972`, `runner.py` `cd88667375e4ff979932c694c2f4f0d7df7ca59f`, `test_cursor_executor.py` `40a21afb9894d4d485697e38b8b696ca38d54969`, and `test_generation_handoff.py` `e72799d1cd54f1ba27c221da9d20ba911fa6ce05`.
- The separately accepted selected-task consumer and CLI `--runtime-root` amendment is excluded from this review.

No implementation source or implementation checkpoint was modified during review.

## Finding closure

### 1. Framed, fail-closed Cursor tree integrity — resolved

`eval_harness/executors/cursor.py::_tree_digest` now:

- requires the root and every directory node to remain real directories;
- frames the entry type, logical-path byte length/path, and regular-file content length/content;
- includes empty directories in the digest;
- rejects symlinks and special nodes;
- opens files with `O_NOFOLLOW | O_NONBLOCK`, checks the opened descriptor is the same regular file observed by `lstat`, and verifies before/after file and directory stat signatures;
- raises `_TreeDigestError` when the root is missing, type-changed, unreadable, or changes during traversal.

`_restore_task_inputs` independently requires the protected node to remain a real directory. `_isolate_task_inputs` attempts restoration if initial digesting or protected-symlink creation fails, including interruption.

The real-tree regressions pin the formerly colliding `a:X,b:Y` and `a:X + framed bY` trees as different, bind empty-directory structure, reject an internal symlink and FIFO, detect file/directory stat changes, and reject missing/regular-file roots. Execute-level cases delete the protected root, replace it with a symlink, add an internal symlink, and perform the original framed-content mutation. Each fails with empty output channels; restoration produces a visible real directory whenever the protected original remains recoverable.

### 2. Post-execution verification classification and primary-failure preservation — resolved

Post-subprocess digesting is isolated in the `finally` finalization path. With no earlier failure:

- a digest mismatch becomes `INTEGRITY/task_input_mutation/RUN`;
- an unreadable, missing, or type-invalid protected tree becomes `INTEGRITY/task_input_integrity/RUN`;
- a restoration failure becomes `INTEGRITY/task_input_restore/RUN`;
- a cleanup interruption becomes `INTERRUPTED/interrupted/RUN`.

When timeout, interruption, process-exit, output-protocol, or prior integrity failure already exists, digest/restore cleanup records only stable metadata and preserves the original failure and status. After any failure discovered during finalization, the implementation clears `output_text` and exposes an empty `available_outputs` set before constructing `ExecutionResult`.

The regressions exercise a post-digest `OSError` after a successful parse and after timeout, process, protocol, and interruption outcomes; late digest mismatch; restoration error; restoration interruption; and combined cleanup failures. They assert the exact primary kind/code, terminal status, and empty channels.

### 3. Log-write failures and interruptions — resolved

`stdout.log` and `stderr.log` are persisted in independent guarded operations. An `OSError` after an otherwise successful parse fails closed as `PROCESS/log_persistence/RUN`; a `KeyboardInterrupt` after success becomes `INTERRUPTED/interrupted/RUN`. With an existing timeout, process, protocol, integrity, or interruption failure, either log error preserves that primary. The other log is still attempted, and metadata contains only the stable failed log filename list, not exception text. Every failed result clears output text and channels.

The regression matrix covers both log paths for success and every applicable primary class, for both ordinary write errors and write interruptions. It also proves the unaffected log persists and raw `disk full` text does not enter metadata.

### 4. Repository provenance timing — resolved

`eval_harness/runner.py::run_benchmark` now calls `benchmark.prepare()` once, immediately captures and normalizes repository provenance, and only then creates the controller staging parent/directory, durable run root, snapshot publication, candidate index/manifest, or external runtime root. The captured value is reused in outer metadata; there is no later provenance call that can observe the run's own files.

`test_prepare_and_repository_provenance_precede_run_root_creation` observes provenance capture with exactly one completed prepare call while the output root, runtime root, and controller staging directory are all absent.

## Independent verification

From the exact archive, with bytecode writes disabled and no real model, judge, provider, network, or paid API call:

```text
python -B -m unittest \
  tests.harness.test_cursor_executor \
  tests.harness.test_generation_handoff.GenerationHandoffTests.test_prepare_and_repository_provenance_precede_run_root_creation

Ran 25 tests in 0.090s
OK
```

This record closes only the original four production findings. Full PR-02c acceptance, staged fixture migration, selected-task repair, CLI coverage, and repository-wide gates remain separately tracked by the parent workflow.
