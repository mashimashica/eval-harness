<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Migration state

Updated: 2026-09-13T00:51:26.163Z

Control branch: `checkpoint/migration-control`.
Procedure: [MIGRATION-WORKFLOW.md](MIGRATION-WORKFLOW.md).
This file records durable state; it does not declare the entire migration accepted.

## Last durable implementation base

Repository: `mashimashica/eval-harness`.

Base commit: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`.
Base tree: `354943ebbb8ea81a30523bfdc12baf26771853b5`.

The control branch starts from that implementation base. Its operating documents are separate from implementation
acceptance. No new evaluator, executor, runner, or compatibility path is introduced by this checkpoint.

| Slice | Draft PR | Verified head | State |
| --- | --- | --- | --- |
| 01 | [#38][pr38] | `b0d4229f49c7cc2441efd0f3aa929b58a9096c55` | CI passed |
| 02a | [#39][pr39] | `86b03a910799ecf97b33d3dac230c069a44bde65` | CI passed |
| 02b | [#40][pr40] | `0b3f41a0edcfffc1b6f4b537bcb2cab2e55e39c4` | CI passed |
| 03 | [#41][pr41] | `d5ce0c10162cad788a17cb90f34b8f60574e7f75` | CI passed |

PR heads, open state, and Draft state were read back while creating this record.
All four PRs remain unmerged. The stack is 01 -> 02a -> 02b -> 03.
PR02c has not been published. The migration still uses the original eleven logical slices, with PR02 split.

## Preserved validation for PR03

[Eval Harness CI run 34716101531][ci03] passed.

- 515 harness unit tests and all six shell integrations passed.
- Additional suites of 45 and 5 tests passed.
- Coverage: 9,854 of 10,210 statements, or 96.513222%. The exact 96% integer gate passed.
- Ruff, strict mypy, dependency audit, copyright, and secret checks passed.
- Tested synthetic merge: `7eae33620cc25715d2f97f96ee3fb33cfced093a`.
  Its tree was verified equal to the implementation base tree above.

These results apply to the recorded PR03 source. They do not establish final migration acceptance.
Real-model experiments have not been run.

## Previous unpublished work was lost

The previous execution environment became unavailable. After reconnection, the expected scratch directories,
including source stages and interface-contract files, were absent.
No usable remote implementation checkpoint for the unpublished slices has been identified.

| Slice | Earlier activity | Current recoverable state |
| --- | --- | --- |
| 02c | Previously lost generation handoff implementation | New partial reconstruction saved; implementation and full validation still required |
| 04 | Grader isolation implementation and boundary tests | Source recovery, security fixes, native CI required |
| 05 | Pure evaluator/planner implementation and focused validation | Source recovery and CLI integration required |
| 06 | Pure rubric/pairwise/panel logic and focused validation | Source recovery and common-path integration required |
| 07 | Stirrup generation separation and partial validation | Source recovery and shared HTTP integration required |
| 08 | AA-v2 profile/aggregation logic and partial validation | Source recovery and full integration required |
| 09 | Design and implementation contract | Exact contract recovery required; implementation not completed |
| 10-11 | No completed implementation recorded | Old-route deletion, documents, extension test, final acceptance remain |

Earlier focused test reports are historical observations, not proof of currently available source.
Do not mark these slices restored or validated until their actual bytes are recovered and checked.

## Recovered canonical plan

Original user plan: `eval-harness-neutrality-migration-plan-2026-09-12.md`.
The user-provided canonical plan remains the scope authority.
The user reattached the original plan, and its complete UTF-8 bytes are saved in this control branch at
[`eval-harness-neutrality-migration-plan-2026-09-12.md`](eval-harness-neutrality-migration-plan-2026-09-12.md).
Provenance: user reattachment of `libfile_9e4457a4cf308191ad99ea93950cf903`; read from the provided scratch copy.
Size: 33790 bytes. SHA-256: `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.
Do not substitute this state summary for that plan. Missing unpublished contracts will be newly specified by Sol
from the restored plan and the immutable accepted source APIs; they are not recovered original contracts.

## Active work and reachable checkpoints

Only PR02c implementation is active. Luna edits one bounded source/test batch at a time in an isolated checkout.
Root owns remote checkpoint writes during the persistence correction described below.
Sol design/review proceeds independently; drafts below are saved work, not implementation acceptance.

| Slice | Checkpoint branch | Saved commit | Saved contract / state |
| --- | --- | --- | --- |
| 02c | `checkpoint/pr-02c` | `66c01eefbce311592a65e9bba7d294318be3139b` | Cursor cleanup plus bound snapshot/executor provenance fixes saved/read back; latest runner tests pending, incomplete |
| 04 | `checkpoint/design-pr04` | `a2a9f9adcc60a117ddafb5c58e8449936a76e793` | Grader contract plus exact rejected locks/audit evidence; draft, dependency CVE closure and real sandbox proof remain |
| 06 | `checkpoint/design-pr06` | `5a35d85d0c6af63fd95c672fda2584d26be4ba70` | GDPval semantic contract and exact characterization fixtures saved; 26 baseline fake tests passed; implementation appendix pending |
| 07 | `checkpoint/design-pr07` | `4ab6f321be221e5e8b393d6c905fbcd72512dc5b` | Stirrup generation contract draft saved; exact dependency resolution/audit pending |
| 08 | `checkpoint/design-pr08` | `c8b923a80d778dae1dc5980c40107b57cae915fc` | Protocol, numeric and cross-stage occurrence fixtures saved; shared identity fields aligned with PR05/06 |

PR02c contract SHA-256: `a755aa7ef611238258308146ac8d602e4b9debd1e644a1e9b795616c95ce86fc`.
Its two files and ref were read back and matched the saved bytes/Git blobs before implementation started.
PR09 draft is also reachable on `checkpoint/design-pr09` at `aa50f441f23397980b755b6296071f61803240a1`
(`contracts/pr09-builder-experiment-contract.md`); exact API/source mapping is still being completed.
Sol also owns bounded PR05 design work; no source implementation is running for those slices.
New design documents are reconstructions from the original plan and accepted APIs, not recovered lost files.

Next actions, in order:

1. Luna completes PR02c within the saved path/API contract, returning each bounded edited batch to root for
   direct API checkpoint/readback before tests or another editing batch.
2. Sol reviews the saved implementation; close focused tests and all unchanged required gates on its resulting head.
3. Root promotes the reviewed slice to the Draft stack, verifies the saved head and CI commit/tree evidence.
4. Advance through PR04–09 one accepted implementation slice at a time.
5. Delete replaced routes in PR10 and close fourth-benchmark/final-head acceptance in PR11.

PR02c's task-input protection amendment is saved with its implementation checkpoint (SHA-256
`98c69de050dcbce42bad8db805243402f69633bb896a704e2a4628bdd9eba9c8`).
Cursor must protect `task_inputs`; file interventions must reserve that namespace.
No fix or test pass is claimed until the resulting implementation is reviewed and validated.

Persistence correction: Luna had created local commits through `909b95519aa2434d4c9b1c68ff5ee712267aed36`
while GitHub still held the initial contract. Those local commits and their incorrect generic local sign-off were
not promoted. Root paused editing, corrected an inaccurate local work-record save claim, and saved all nine
changed UTF-8 files through the required APIs with the exact user DCO. Ref and every changed file's bytes/Git blob
were read back at `4948b2c3f85ca82d94e44734de532c8769d7b04e`, tree
`e557804dcdac7e28ce3a6f3bacc2fb6962167b35`. No implementation bytes were lost.
A fresh checkout and locked environment were created from that actual saved commit. Root now controls remote
saves between Luna's bounded editing tasks. Subsequent saved commits `d8bfa21554bfbe4adb9f592ddfaece65d78fff0c`
and `ec2b0862335ce9eb9da8ad7f36839c804b0b3663` fix late and preparation-time Cursor cleanup. The latter exact
clean head passed all 13 Cursor tests and scoped Ruff; its two strict-mypy test callback errors are addressed in
`66c01eefbce311592a65e9bba7d294318be3139b`, together with snapshot/provenance checks and meaningful fixture
migrations. All four changed files and the new ref were read back exactly; this latest batch is not yet validated.
Remaining GDPval wrapper, generation handoff, fixture and full-gate work is recorded with the code.

PR04 dependency audit identified an unresolved official NLTK advisory
[GHSA-8mgp-746c-j5xp / CVE-2026-81726](https://github.com/nltk/nltk/security/advisories/GHSA-8mgp-746c-j5xp).
The official advisory reports no patched release as inspected on 2026-09-13. Exact rejected requirement locks
and full audit reports are saved in the PR04 design checkpoint. Sol is evaluating an explicit newer grader
interpreter and a minimal source-reviewed fix; no CVE ignore rule, false version, sandbox-based exemption, or
acceptance claim is authorized by this investigation. Other authorized preparation continues.

No merge, release, publish, or real-model experiment is part of this work.

## Accepted source and development environment recovered

The complete repository was recovered using a read-only Git clone at the accepted implementation base above.
All 5,134 tracked blobs were checked byte-for-byte and mode-for-mode against Git. The worktree was clean.
There were zero missing paths, content mismatches, mode mismatches, or unsafe symlinks.

Development environment recreation succeeded with:

- CPython 3.13.14.
- uv 0.11.29, invoked with `uvx --from uv==0.11.29 uv`.
- `uv sync --locked --extra dev --python 3.13.14`, using the accepted `uv.lock`.
- No source or lock-file modifications.

This is recovery and environment preparation evidence. No new implementation validation or acceptance is claimed.

## Verified recovery drill

Checkpoint tested: `e823f3b2739b2be49f12bfd7e757323dbca48d02`.

The three control files were fetched from that immutable remote commit into a newly empty local directory.
All three restored files matched their recorded Git blob hashes:

| File | Verified Git blob |
| --- | --- |
| `AGENTS.md` | `a1fd166e25ed240c7e8538d02b22699f3cc0d882` |
| `MIGRATION-WORKFLOW.md` | `43523cefe12d3a30b28edc53e3e2d2cbc0ed8896` |
| `MIGRATION-STATE.md` | `b88dfae67c1cfa4080b71452ed0fbea281cca28d` |

The remote comparison also confirmed that the checkpoint changed only these three paths.
No workflow runs were returned for that checkpoint when checked after publication.
This drill verifies recovery of the saved control documents. It does not recover the missing unpublished source
or provide implementation acceptance. This evidence is recorded in a descendant commit so that the tested commit
and file hashes remain immutable.

## Final acceptance inventory

Astra's current deletion, protection-porting, fourth-benchmark, and exact-final-head checklist is saved at
[`contracts/final-acceptance-map.md`](contracts/final-acceptance-map.md).
It identifies integration risks sent to the slice designers; none is claimed fixed by this document.

## Updating this control record

For each slice, record the reachable checkpoint branch and commit, saved contract paths, tested commit,
validation evidence, acceptance state, blocker, and next action.
Update after each saved code checkpoint, handoff, promotion, and validation result.
Keep implementation checkpoints self-describing even if this central record has not yet been updated.

[pr38]: https://github.com/mashimashica/eval-harness/pull/38
[pr39]: https://github.com/mashimashica/eval-harness/pull/39
[pr40]: https://github.com/mashimashica/eval-harness/pull/40
[pr41]: https://github.com/mashimashica/eval-harness/pull/41
[ci03]: https://github.com/mashimashica/eval-harness/actions/runs/34716101531
