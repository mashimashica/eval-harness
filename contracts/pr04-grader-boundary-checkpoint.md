<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR04 grader boundary checkpoint

**State:** design-freeze candidate/unvalidated checkpoint, 2026-09-13 UTC.

- Owner: Sol design/security research; Luna implementation only after Sol review.
- Implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`.
- Control base for this checkpoint branch: `8518f25d107d9043df449a9198fbb41b00ba1c22`.
- Deliverables: `contracts/pr04-grader-boundary-contract.md`, finite Luna handoff `contracts/pr04-grader-boundary-implementation-appendix.md`, `contracts/pr04-grader-boundary-evidence.md`, and the exact research inputs/reports under `contracts/pr04-evidence/`.
- Decision: one runtime boundary, bubblewrap 0.12.0 with mandatory user/mount/PID/network/IPC/UTS namespaces and no fallback; unsupported environments fail before model work.
- Decision: pinned BigCodeBench 0.2.5 remains native metric code but is explicitly not the security sandbox.
- Decision: grader infrastructure raises and stops the run; wrong, empty, candidate timeout, and candidate resource limit remain separate normal outcomes.
- Decision: CI acceptance requires real hostile fixtures on fixed Ubuntu 24.04; mocked or skipped security tests do not count.
- Dependency checkpoint: the explicit CPython 3.11.16 / uv 0.11.29 lock resolves 160 hash-complete distributions and clears every observed Python 3.10 finding except NLTK. Strict audit reports exactly `PYSEC-2026-3740` / `GHSA-8mgp-746c-j5xp` / `CVE-2026-81726`, no fix; the lock remains rejected. Earlier Python 3.10 locks and full reports remain preserved.
- Native source selection: vendor only BigCodeBench v0.2.5 `eval/{__init__,utils,_special_oracle}.py` exact blobs plus its root Apache-2.0 license; `__init__`/`utils` retain embedded OpenAI MIT notices. Recoverable bytes with original CRLF endings are now saved under `contracts/pr04-evidence/upstream-bigcodebench-v0.2.5/`. Exact VENDORING/ATTRIBUTIONS, Ruff preservation and a documented copyright-rule exception are required. All authored code and installed/task packages remain gated.
- NLTK remediation evidence: **rejected**. The prior narrow patch passes its 9 focused tests and builds reproducibly, but independent controls reproduce a normal-load `NameError` and destructive hardlink truncation before rejection; it also lacks safe FIFO/special/default-path coverage. The wheel must not be installed. Standard audit remains red.
- Boundary contract: exact mounts/env/limits are selected; the result channel uses a 32-byte per-run HMAC key, `PR_SET_DUMPABLE=0`, a host `close_fds=True, pass_fds=()` launch, CLOEXEC result duplicate, descriptor replacement, forced multiprocessing `spawn`, and exact authenticated START/RESULT/ERROR frames. Rlimits are set and verified by the trusted inner runner before it reads the key/payload, avoiding unsafe host `preexec_fn`. Real `/proc`, raw-FD, child/grandchild, signal and forgery fixtures are mandatory. Trusted host/runner logic is frozen under measured, typed `eval_harness` modules; the legacy executable resource-server shim is removed.
- Data lock: seven official NLTK ZIPs match Git blobs/index hashes; the prepared 167-file tree and reduced offline index are exact and functional. A measured site bootstrap is required because `NLTK_DATA` alone does not redirect the module-global downloader. Official metadata marks `punkt`, `punkt_tab`, and `stopwords` licenses unclarified. Those bytes are not vendored or called Apache-compatible; fixed-commit ephemeral provenance/compatibility retrieval may continue while repository review decides artifact packaging.
- Interpreter selection: immutable Astral `python-build-standalone` release `20260901` asset ID `539915682`, size `30778779`, SHA-256 `64427febea27864d136db46c8efe968eb6fa5ca2813ce1dca4bb95aec31cb2e4`; uv remains 0.11.29 with managed downloads disabled. Safe extraction and executable/license hashes are recorded.
- Build input: bubblewrap uses hash-locked Meson 1.9.1/Ninja 1.13.0. uv 0.11.29 sync, version checks, `uv pip check`, and strict pip-audit 2.10.1 passed locally (two distributions, zero findings); exact hosted build remains not run.
- Copyright/vendoring: exact BigCodeBench source remains byte-for-byte. Ruff excludes only its exact directory from formatting. The pinned reusable copyright workflow gets a one-file `_special_oracle.py` `additional-find-args` exclusion, with exact workflow blob and caller syntax preserved; the vendor manifest/hash/license test covers it and authored code stays gated.
- Remaining mandatory blocker: unchanged standard NLTK audit gate. Remaining implementation proofs are the prepared interpreter/venv manifest, all-canonical semantic/limit/mount run, same-UID protocol containment and full hosted-CI production policy. The three data-license uncertainties remain an explicit repository/artifact packaging decision.
- Next action: root/primary Sol reviews this frozen candidate; Luna implements only after that review, while Gate A remains red until an official NLTK release yields a clean lock.
