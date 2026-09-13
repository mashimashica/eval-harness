<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR-02c work record

Status: incomplete implementation checkpoint. Validation and acceptance remain open.

- Repository: `mashimashica/eval-harness`
- Implementation owner: Luna (`/root/luna_restore_source`); design/review: Sol (`/root/sol_pr02c_design`); architecture/acceptance: Astra (`/root`).
- Branch: `checkpoint/pr-02c`; root temporarily owns remote writes during persistence recovery. Luna's implementation turn is paused.
- Immutable implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`, tree `354943ebbb8ea81a30523bfdc12baf26771853b5`.
- Dependency heads: PR01 `b0d4229f49c7cc2441efd0f3aa929b58a9096c55`; PR02a `86b03a910799ecf97b33d3dac230c069a44bde65`; PR02b `0b3f41a0edcfffc1b6f4b537bcb2cab2e55e39c4`; PR03 is the base above.
- Original plan: control commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, `eval-harness-neutrality-migration-plan-2026-09-12.md`, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.
- Contract: `contracts/pr02c-reconstruction.md` in this commit. The production/test path allowlist, fixed APIs, invariants, failure behavior, and gates in that file govern this slice.
- Accepted scope amendment: `contracts/pr02c-input-protection-amendment.md`, SHA-256
  `98c69de050dcbce42bad8db805243402f69633bb896a704e2a4628bdd9eba9c8`. It adds the Cursor and FilesIntervention
  paths and exact `task_inputs` protection/legacy rejection requirements described in that file.
- Control procedure: `checkpoint/migration-control:MIGRATION-WORKFLOW.md` (current control head at initialization: `ff85149636b55c207f7fdd388727db20475a7ab2`).

This checkpoint preserves a newly written, incomplete implementation of the candidate layout, snapshot generation handoff, Cursor task-input protection, FilesIntervention reservation, and initial fixture updates. It also includes the accepted input-protection amendment. It does not recover previously lost unpublished implementation. Original plan bytes and all 5,134 tracked files at the implementation base have been verified. Python 3.13.14 and uv 0.11.29 recreate the locked development environment.

Persistence correction: Luna created local commits through `909b95519aa2434d4c9b1c68ff5ee712267aed36`, but the remote branch still pointed to the initial contract commit. Those local commits were not durable checkpoints and their generic local DCO did not match the required user sign-off. Root paused further edits/tests, inspected the allowed nine-file delta, and is preserving the exact source tree through the required UTF-8 GitHub APIs with the correct DCO. Local commits are not being promoted into remote ancestry. A prior local work-record sentence claiming remote readback was incorrect and is replaced here.

Known remaining work before acceptance:

- Complete the GDPval `task_inputs` wrapper correction, the generation handoff integration tests, and all required fixture migrations, including the new common CLI Cursor coverage and explicit legacy rejection.
- Fix Cursor cleanup failure handling so a late integrity/restore failure clears successful output text and cannot violate the typed failed-result schema. Preserve an already typed primary timeout/interruption/process failure; record cleanup evidence without masking it.
- Review the initial generic intervention fixture change: retain meaningful materialized-file provenance coverage using valid file bytes, hashes, and manifest evidence rather than removing that behavior.
- Sol's source/API/security review is in progress against this incomplete tree; no review acceptance is claimed.

Next action: verify this remote checkpoint and changed bytes, return a fresh checkout of it to Luna, fix the reviewed Cursor/fixture issues in one bounded batch, save/read back that batch, then complete the remaining handoff implementation and tests. No source expansion or long test may precede its required checkpoint. No real model or judge execution, merge, or release is authorized in this phase.

Validation of this checkpoint: design reviewed by Sol and Astra; no source implementation tests run or claimed. Base PR03 exact-head validation remains historical evidence for that unchanged base only. PR02c requires focused tests, independent review, and all unchanged mandatory CI gates on its own saved implementation head.

Promotion: no formal PR yet. A reachable checkpoint is saved work, not a passed test or accepted migration slice.

## Cursor cleanup batch

Base: `4948b2c3f85ca82d94e44734de532c8769d7b04e`. Luna edited only `eval_harness/executors/cursor.py` and `tests/harness/test_cursor_executor.py`, then returned the batch without local commits or tests. Root reviewed the bounded diff and is saving it with this record before validation.

The change clears output text whenever cleanup adds a typed failure, represents a cleanup interruption explicitly, and adds focused regressions for late mutation, restore failure, and primary-failure preservation. Tests have not been run on this batch. It does not yet fix the separately identified setup-write cleanup gap, complete other fixture migration, or close PR02c acceptance.

Next: run the focused Cursor tests on this saved head, fix any concrete failure, then bring policy/prompt preparation inside the cleanup lifetime and address the remaining reviewed runner/fixture requirements in bounded saved batches.

## Cursor preparation cleanup batch

Base `d8bfa21554bfbe4adb9f592ddfaece65d78fff0c` was read back and checked out cleanly. `python -m unittest tests.harness.test_cursor_executor` passed all 10 tests on that exact head. An isolated clean checkout of the same head ran `test_generic_runner`: 33 tests, 4 failures and 1 error, all recorded as remaining input-path/descriptor/duplicate-ID/unavailable-revision fixture migration work; no full-suite or acceptance pass is claimed.

This batch changes only Cursor and its focused tests: policy/prompt preparation now lies inside the restoration lifetime, and a failed digest immediately after isolating inputs restores the original namespace before propagating. Focused tests assert original bytes, a real directory, and zero subprocess calls after setup failure/interruption. These new tests have not yet run. Root saves this returned batch before validation; source review, typing and all remaining handoff work stay open.

## Bound snapshot and executor provenance batch

Base `ec2b0862335ce9eb9da8ad7f36839c804b0b3663` was read back and checked out cleanly. All 13 Cursor tests and scoped Ruff passed. Scoped strict mypy found two argument-type errors in the new `Path.write_text` test callback; this batch supplies its explicit signature. No full-suite, coverage, or PR02c acceptance is claimed.

Luna returned a bounded three-file edit without tests, commits, or remote writes. Runner acquisition now checks the returned snapshot's exact type and recomputed digest against its sealed binding before publishing output/runtime roots. Known executor version/auth provenance and requested reasoning must match exactly before sealing. Legacy intervention failures retain `evaluation=None`, and the legacy row helper uses concrete types. Generic runner fixtures now use `task_inputs`, correct content hashes, declared capabilities and revision availability; a real FilesIntervention test preserves file provenance coverage. Focused regressions reject incoherent snapshot metadata and missing/mismatched execution provenance without producing candidates or invoking evaluation.

Root inspected the diff and saves it together with this record before validation. Next commands on the saved head: Cursor and generic runner unit tests, scoped Ruff, and strict mypy of the changed modules/tests. Then complete the minimal GDPval wrapper change, generation handoff integration tests, and remaining fixture migrations. All full acceptance gates remain required.

## Typed sealing and canonical fingerprint fixture batch

Exact clean head `66c01eefbce311592a65e9bba7d294318be3139b` ran 48 Cursor/generic runner tests: one failure and one error, both old metadata/fingerprint expectations. Scoped strict mypy found four errors (optional sealed digest, two nested JSON objects, fixture revision annotation); Ruff lint passed and runner formatting needed correction. A separate clean checkout of that same head ran all 526 harness unit tests, with one failure and 33 errors. Remaining diagnostics identify the already scoped Cursor namespace/helper migrations and missing capabilities/revision availability in Builder, reasoning, and reliability fakes. No full-suite pass is claimed.

This two-source-file batch explicitly validates the sealed digest before indexing, uses typed fixture JSON/revision fields, updates the canonical availability key, and verifies the semantic fingerprint from the persisted RunManifest snapshot references while retaining the separate legacy prompt hash assertion. Root caught and corrected a draft assertion that had confused those two task digests before saving. Scoped Ruff formatting is included. No tests have run on this batch.

Next: validate these focused tests/types on the saved head, then complete the GDPval wrapper, new generation handoff tests, and the enumerated fixture ports. Root remains the sole remote checkpoint writer; Luna returns each bounded edit before testing or further scope.
