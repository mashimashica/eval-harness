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

## Code-start review closed

Sol reviewed the frozen candidate and confirmed no other code-start blocker after the finite amendment recorded in `contracts/pr04-code-start-amendment.md`. Astra accepts the truthful non-acceptance candidate environment/manifest/CI sequencing, authenticated native-signal result union, and exact trusted-mount versus untrusted-root clarification. The final trusted spec field is `manifest_path: Path | None = None`; production constructors cannot select candidate mode. All original security and acceptance gates remain.

The recovered local source/build/data files match all seven frozen SHA-256 values. Root also corrects a transcription error in the VENDORING document's __init__.py Git-blob text; source bytes themselves were and remain exact. Next Luna implements only the three-file pure type/codec/parser batch, with no process launch or native import, then returns it before testing for root checkpoint and Sol review.

## Pure protocol implementation checkpoint

Luna returned the bounded three-file foundation with immutable types, canonical BCBI/BCBO framing, HMAC verification, bounded incremental state parsing and status/signal mapping. It contains no process launch, native import, resource-limit execution or claim of sandbox readiness. Root inspected public types, interfaces and test assertions, and applied scoped Ruff formatting. No tests or strict typing have run on this batch.

Root identified follow-up fixture integration requirements before acceptance: the pure tests must participate in the existing unittest-based coverage driver and run under the frozen Python 3.11 worker interpreter as well as Python 3.13; avoid a new type-ignore for the frozen-field assertion. Independent Sol review of the saved codec delta is next. The finite vendor-hook and legacy fixture scope additions approved by Sol are appended to the code-start amendment; they do not exempt authored code.
