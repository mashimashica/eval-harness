<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR05 readiness under held PR04 acceptance

This is parent dependency accounting, not a new design, implementation assignment,
acceptance decision or permission to implement two PRs simultaneously.

The complete saved PR05 contract was read at
`7e7629c330ca0841ee92612f534db72c0a459b2b`, path
`contracts/pr05-independent-evaluation-contract.md`, SHA-256
`a7bc2f7c9e28e8965032a829e09a1c1db01a908c87211b8b3ef521844b91eca0`.
Its exact APIs, scope, strict storage/resume semantics, no-fallback requirements and
tests remain binding. No redesign is needed. Accepted PR02c is
`6038a7828d62247ad98d000bc6e71c706f6d14a4`; parent verified it is an ancestor of
both current implementation `55fc13bb` and formal `2d022f76`.

The later user instructions permit independent planned implementation while an issue
and its affected acceptance are held. They supersede the design's older rule requiring
all PR04 acceptance before any PR05 source edit; they do not supersede PR05 acceptance
gates. Before activation, freeze the actual PR04 resume head, record its full SHA/tree,
read back consumed public APIs, and enumerate open defects and exact dependency holds.
Do not substitute an unaccepted head while labeling it accepted. Only one slice may
have an active source writer. The current slice is still PR04.

PR05's generic registry selection, strict evaluation job identities and record sink,
generation extraction/reopen, explicit planning, exact retry/stop semantics, guarded
judge-runtime extraction, independent CLI and fourth-benchmark fixture do not themselves
require the BigCode grader to execute. They can be implemented and deterministically
tested after a coherent PR04 source checkpoint is frozen, without altering PR04 sandbox
files, invoking unavailable isolation, or representing a fake as actual boundary proof.
Native AIME's locked verifier and audit are a separate real no-model gate, not waived by
the NLTK hold. Existing accepted snapshot/bundle/index APIs must be consumed unchanged.

The BigCode adapter must consume the frozen PR04 interface and preserve failure,
provenance and no-score-on-infrastructure semantics. Actual BigCode isolation and native
parity, PR04 acceptance, and dependent PR05/full-migration acceptance stay held until
their real gates pass. A source defect affecting a consumed API is not merely a CVE or
environment hold: isolate that dependency explicitly and do not call the adapter accepted.

No PR05 source edits have started. Activate only through a saved one-owner work record
and bounded Luna assignment after the current PR04 correction/review disposition.
Final head must still remove old routes and all tracked contracts/*.md after permanent
specification integration, and pass every original quality gate.
