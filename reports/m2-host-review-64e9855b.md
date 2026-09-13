<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Initial host-supervisor independent review

Reviewer: Sol (gpt-5.6-sol), read-only detached worktree. Fixed head:
`64e9855b796047d351e67c2b14006eccf5ad2414`; base:
`9bed63c6c3a26eb2542ce22d6cd9669a618cd8ec`. No duplicate test runs or source edits.
Disposition: corrections required; not PR04 acceptance.

| Finding | Fixed-head evidence | Required correction |
| --- | --- | --- |
| Unsized writable root and device tmpfs | `grader_sandbox.py:339` | Nonrecursive remount-ro of `/dev` and `/` after construction, retaining sized nested scratch; exact argv and real write probes |
| Successful result bypasses cleanup | `grader_sandbox.py:651` | Require recorded descendants gone on success before lock release |
| Pre-START resource excess ignored | `grader_sandbox.py:583` | Enforce process/RSS caps before START as infrastructure |
| Trusted death can become candidate limit | `grader_sandbox.py:575` | Check live process state at direct enforcement; dead trusted process without terminal frame is infrastructure |
| Sampling failure becomes empty/zero | `grader_sandbox.py:440,473` | Distinguish disappeared processes from live/global observation failure; fail closed |
| Wrong NPROC baseline | `grader_sandbox.py:297` | Parse real UID and sum positive Threads fields; proc-directory owner and leader count are insufficient |
| Setup failure leaks child/handles | `grader_sandbox.py:526` | Own all post-Popen resources in cleanup, including parser/selector failure and missing pipes |
| Input cap rejects valid frame boundary | `grader_sandbox.py:523` | Preserve 8 MiB JSON payload plus 41-byte framing/key, without widening payload limit |
| Command fixture not exact | `test_bigcodebench_runner.py:97` | Compare complete normalized operations using contract literals, including mounts/env/cwd/flags/caps |

The parent sent every finding to the same Luna implementation owner for one consolidated
correction with regressions. Initial local test/static failures are separately preserved in
`m2-host-initial-validation.json`; no correction result is yet claimed.

The finite root/device read-only and NPROC clarification is appended to the implementation
branch's `contracts/pr04-code-start-amendment.md` in the correction batch. Root verified
the pinned bubblewrap source and nonrecursive remount documentation directly at commit
`2a76602a8c71f36c1527cf9fc3417d9149822e0c`: `bubblewrap.c` blob
`9192550540d3c4f173a7308c11e518e18ef4c303`, and `bwrap.xml` blob
`ca717abd6001a4e07557253578d41b0e813aaf31`.

Public preflight/launch wiring, environment provisioning, callers, hosted real boundary,
all-1,140 native parity and whole-head acceptance remain explicitly subsequent work.
The known NLTK audit blocker is unchanged and was not reinvestigated.
