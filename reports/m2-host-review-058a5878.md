<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR04 host correction review and segment stop

Reviewer: Sol (`gpt-5.6-sol`), source read-only; implementation owner: Luna
(`gpt-5.6-luna`); checkpoint/acceptance owner: Astra. No grandchildren.

Fixed review commit: `058a5878cef8014ff3d8598118cbaa6f2e68962d`.
Host blob: `254e90ebe0e77100fd751c938dde1d592c00b40e`, unchanged at tested
`5678340634362d155a5b98f296b1a75a34c8dc07` and record-only stop checkpoint
`7be35da9fae98c5e56ba14bf13a15a4cdbb9a8e7`.

## Unresolved P1 findings

1. **Teardown budget restarts.** `eval_harness/grader_sandbox.py:650–660,682–686,760–763`.
   An outer process that exits nearly five seconds after its terminal frame causes a fresh
   `now + teardown_seconds` deadline while a descendant retains its pipe. This can extend
   the terminal-to-cleanup interval to about ten seconds. A timeout in the successful cleanup
   path also enters exception cleanup and begins another full wait. Use a single absolute
   deadline without restarting the phase/cleanup budget. Add deterministic clock regressions
   for late outer exit and remaining descendants; a fixture dead from the beginning does
   not detect the extension.
2. **Trusted exit misclassified as candidate resource enforcement.**
   `eval_harness/grader_sandbox.py:674–680`, with helper at `551–556`.
   The outer process may exit after the caller's alive poll and before the helper's poll.
   The helper then omits the kill, but the caller still returns a candidate resource result.
   This can convert infrastructure failure to a zero-scoring outcome. Require evidence of
   actual host enforcement before returning a limit result and add a third-poll-exit
   regression. The existing second-poll-exit case does not cover this window.

Astra independently read the exact source and confirmed both control-flow defects.
The same teardown-bound issue remained after the e839a8cb correction review and the
058a5878 correction review. The user's two-failed-correction rule is therefore applied:
stop new implementation, preserve all work, report; do not begin a third correction.

## Closed within the reviewed host delta

Root/dev read-only mounts; successful cleanup invocation; pre-START resource classification;
procfs/RSS fail-closed handling and zombie/no-RSS races; real-UID task baseline; parser and
selector initialization cleanup; BCBI fixed framing allowance; exact optional-bind/argv
assertions; typed registered streams; a finite post-exit pipe drain. These closures do not
override the two remaining defects or establish real Linux isolation.

## Evidence and resume boundary

At `56783406`, 31 unittest methods, strict mypy of the changed two files, and Ruff lint/format
pass; no ResourceWarnings remain. See `m2-host-local-validation.json`. These passing checks
do not cover the remaining reviewer counterexamples. The record-only stop head has identical
source/test blobs; no claim is made that the new full head has rerun acceptance checks.

Luna stopped the independent bootstrap batch before editing any files. Both agents are idle.
Root remains clean on main; work is confined to the independent PR04/control/review trees.
NLTK acceptance remains blocked, and closed dependency research is not repeated. There is
no PR04 Draft promotion, Linux sandbox acceptance, 1,140-task native parity, full-head
coverage/audit, PR05–11 implementation, model experiment, merge or release in this segment.

On a user-authorized continuation, fix these two findings with the same implementation
owner and fixed-base contract, save before consolidated regression/static checks, then
obtain independent fixed-head review. Only after closure resume preflight/provisioning,
shared callers and old-runner deletion. All final gates, including removal of tracked
`contracts/*.md`, remain mandatory and incomplete.
