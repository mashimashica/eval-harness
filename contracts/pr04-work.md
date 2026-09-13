<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR04 implementation work record

State: exact frozen inputs recovered; code not started.

- Owner: Luna implementation, Sol independent contract/delta review, Astra scope/checkpoint/acceptance.
- Base: PR02c `6038a7828d62247ad98d000bc6e71c706f6d14a4`, tree `4f7fc21be5195611ba7df8feeefe3a5cc962c2cb`, accepted Draft #42.
- Required dependencies: accepted PR01/02a/02b/03/02c stack. PR04 is the only active implementation slice.
- First working allowance: 90 minutes from 2026-09-13T04:30:56.162Z; save at most every 15 minutes and before tests/next independent batch.
- Original plan: control commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.
- Exact source contract and appendix: design commit `deb807e8454eb4fbb3652bb1f335489fa5325bea`, copied unchanged in this checkpoint. Contract blob `db8447d1cf3c9c4b0538fe8723150a6a8aa99834`; appendix blob `4eecd0a6b69378f091e33dc5121b07aa46d0031a`.
- User-approved purpose-first amendment: `7f7a260acf1119620282a540739fa1a4afd8c1ed`; approval recorded in control `f4b85f4592d4df6d6e062360b134dd6104c5fc81`.

## Scope and invariants

Use only the finite contract path list. Implement one shared fail-closed grader supervisor/worker route for evaluator and resource server; preserve native status meaning and distinguish infrastructure failure from score zero. Pinned real Linux isolation and all original quality gates remain required. No compatibility wrapper or direct legacy interpreter route may remain at slice completion.

The original design assumes a clean NLTK lock before preparation. The user's later amendment authorizes independent functional implementation and evidence while keeping the known standard audit failure and PR acceptance pending. Sol is defining only the finite operational clarification for truthful candidate/test manifests and independent CI execution. This does not authorize a false accepted manifest, audit exception, rejected backport, repeated M0 research, or a weaker sandbox.

## Validation and next action

No PR04 code or validation is claimed. Preserve the exact source/lock/data evidence from the saved design, with their original hashes, before implementation needs it. Next save the bounded operational clarification, then hand Luna the first coherent module/test batch. Root remains the sole remote writer and saves each returned delta before verification.

## Fixed inputs recovered

Root copied only the four exact upstream metric/license blobs, the two previously audited bubblewrap build inputs, and the NLTK metadata/reduced-index files from design `deb807e8`. Every copied file is byte- and blob-verified against its durable source. No NLTK data payload, rejected patch, grader dependency install, boundary launch or accepted manifest is included. The upstream CRLF bytes remain unchanged. The authored VENDORING document records source/license provenance.

This is an input-recovery checkpoint, not functional validation. Exact-vendor Ruff/copyright configuration, attribution and hash gates remain part of implementation; do not run an auto-formatting all-file hook against the vendored source before its accepted narrow exclusion is installed. The main locked development environment was recreated successfully with uv 0.11.29, Python 3.13.14 and offline locked sync. Next: save Sol's finite implementation clarification, then begin Luna's bounded code batch.
