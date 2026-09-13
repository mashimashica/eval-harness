<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR-02c work record

Status: design accepted for implementation; source implementation and tests have not begun.

- Repository: `mashimashica/eval-harness`
- Implementation owner: Luna (`/root/luna_restore_source`); design/review: Sol (`/root/sol_pr02c_design`); architecture/acceptance: Astra (`/root`).
- Branch: `checkpoint/pr-02c`; one writer, Luna, after this initial contract checkpoint.
- Immutable implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`, tree `354943ebbb8ea81a30523bfdc12baf26771853b5`.
- Dependency heads: PR01 `b0d4229f49c7cc2441efd0f3aa929b58a9096c55`; PR02a `86b03a910799ecf97b33d3dac230c069a44bde65`; PR02b `0b3f41a0edcfffc1b6f4b537bcb2cab2e55e39c4`; PR03 is the base above.
- Original plan: control commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, `eval-harness-neutrality-migration-plan-2026-09-12.md`, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.
- Contract: `contracts/pr02c-reconstruction.md` in this commit. The production/test path allowlist, fixed APIs, invariants, failure behavior, and gates in that file govern this slice.
- Control procedure: `checkpoint/migration-control:MIGRATION-WORKFLOW.md` (current control head at initialization: `ff85149636b55c207f7fdd388727db20475a7ab2`).

This checkpoint contains the reviewed reconstructed contract and this work record only. It does not recover any unpublished old implementation. Original plan bytes and all 5,134 tracked files at the implementation base have been verified. Python 3.13.14 and uv 0.11.29 recreate the locked development environment.

Next action: create an isolated worktree from this saved checkpoint; read the exact contract; implement candidate layout and the single-snapshot generation handoff in small saved batches. Save source and update this record before tests or handoffs. Return fixed-contract conflicts to Sol before broadening scope. No real model or judge execution, merge, or release is authorized in this phase.

Validation of this checkpoint: design reviewed by Sol and Astra; no source implementation tests run or claimed. Base PR03 exact-head validation remains historical evidence for that unchanged base only. PR02c requires focused tests, independent review, and all unchanged mandatory CI gates on its own saved implementation head.

Promotion: no formal PR yet. A reachable checkpoint is saved work, not a passed test or accepted migration slice.
