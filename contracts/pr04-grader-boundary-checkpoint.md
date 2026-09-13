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
- Dependency checkpoint: the explicit CPython 3.11.16 / uv 0.11.29 lock resolves 160 hash-complete distributions and clears every observed Python 3.10 finding except NLTK. Strict audit reports exactly `PYSEC-2026-3740` / `GHSA-8mgp-746c-j5xp` / `CVE-2026-81726`, no fix; the lock remains rejected. Earlier Python 3.10 locks and full reports remain preserved.
- Native source selection: vendor only BigCodeBench v0.2.5 `eval/{__init__,utils,_special_oracle}.py` exact blobs plus MIT license; do not install its unrelated provider/generation dependency stack. All installed and task-required packages remain in lock/audit.
- NLTK remediation evidence: **rejected**. The prior narrow patch passes its 9 focused tests and builds reproducibly, but independent controls reproduce a normal-load `NameError` and destructive hardlink truncation before rejection; it also lacks safe FIFO/special/default-path coverage. The wheel must not be installed. Standard audit remains red.
- Boundary contract: exact mounts/env/limits are selected; the result channel uses a 32-byte per-run HMAC key, `PR_SET_DUMPABLE=0`, descriptor replacement, forced multiprocessing `spawn`, and authenticated START/RESULT frames. Real `/proc`, raw-FD, child/grandchild, signal and forgery fixtures are mandatory. Trusted host/runner logic is frozen under measured, typed `eval_harness` modules; the legacy executable resource-server shim is removed.
- Data lock: seven NLTK assets and the exact official index are pinned to `nltk_data` commit `550b6625bcef1f2abff2ff770a5a0d272c9c6b2a` for offline read-only grading.
- Interpreter selection: immutable Astral `python-build-standalone` release `20260901` asset ID `539915682`, size `30778779`, SHA-256 `64427febea27864d136db46c8efe968eb6fa5ca2813ce1dca4bb95aec31cb2e4`; uv remains 0.11.29 with managed downloads disabled. Safe extraction and executable/license hashes are recorded.
- Build input: bubblewrap uses hash-locked Meson 1.9.1/Ninja 1.13.0. uv 0.11.29 sync, version checks, `uv pip check`, and strict pip-audit 2.10.1 passed locally (two distributions, zero findings); exact hosted build remains not run.
- Remaining blockers: unchanged standard NLTK audit gate; prepared interpreter/venv manifest proof; all-canonical semantic/limit/mount proof; same-UID protocol containment; full hosted-CI production policy.
- Next action: Sol closes the exact boundary contract and remediation gate; Luna implements only after approval.
