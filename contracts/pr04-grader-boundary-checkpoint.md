<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR04 grader boundary checkpoint

**State:** draft/unvalidated design checkpoint, 2026-09-13 UTC.

- Owner: Sol design/security research; Luna implementation only after Sol review.
- Implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`.
- Control base for this checkpoint branch: `8518f25d107d9043df449a9198fbb41b00ba1c22`.
- Deliverables: `contracts/pr04-grader-boundary-contract.md`, `contracts/pr04-grader-boundary-evidence.md`, and the exact research inputs/reports under `contracts/pr04-evidence/`.
- Decision: one runtime boundary, bubblewrap 0.12.0 with mandatory user/mount/PID/network/IPC/UTS namespaces and no fallback; unsupported environments fail before model work.
- Decision: pinned BigCodeBench 0.2.5 remains native metric code but is explicitly not the security sandbox.
- Decision: grader infrastructure raises and stops the run; wrong, empty, candidate timeout, and candidate resource limit remain separate normal outcomes.
- Decision: CI acceptance requires real hostile fixtures on fixed Ubuntu 24.04; mocked or skipped security tests do not count.
- Dependency checkpoint: the unmodified Python 3.10.21 resolution has 319 alias-inclusive audit entries across 17 distributions. A first security-override candidate still has nine entries across `cryptography`, `keras`, and `nltk`; both locks are rejected and their full JSON reports are preserved.
- Audit blocker: official NLTK `GHSA-8mgp-746c-j5xp` / `CVE-2026-81726` affects all released versions through 3.10.3 and has no patched release. Upstream PR 3753 is too broad for wholesale backport. No ignore, version spoof, or silent package omission is allowed.
- Approved research direction: resolve an explicit CPython 3.11.16 grader policy with current fixed `cryptography` and `keras`; there is no interpreter fallback. Separately identify and source-review only the minimal NLTK advisory fix and regression coverage. An unresolved NLTK gate blocks acceptance, not remaining design work.
- Remaining blockers: prove same-UID multiprocessing/protocol containment, select and exercise exact limits/mounts, close a truthful NLTK audit/remediation gate, and run the full production policy on hosted CI.
- Next action: Sol closes the exact boundary contract and remediation gate; Luna implements only after approval.
