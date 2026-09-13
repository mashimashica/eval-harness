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
| 02c | `checkpoint/pr-02c` | `f972a82558609255f84723b9d4c060503eef894a` | Real handoff tests saved/read back; exact clean head passes all 8 integrations, scoped strict typing and Ruff; negative cases/fixture/full gates remain |
| 04 | `checkpoint/design-pr04` | `28d759b24e1e0a3ff50c1771f97aaba03dd33926` | Exact runtime/source/worker/CI design saved; strict NLTK audit red and initial patch independently rejected; replacement/proof pending |
| 05 | `checkpoint/design-pr05` | `129daf7a50652afdf9faaf144e359b71f6c2b6b2` | Independent evaluation, protected roles, semantic/full plan identity and verified generation/result resume contracts saved; implementation pending |
| 06 | `checkpoint/design-pr06` | `7815a113d46e2fd9a98cc8575668183372f3ff3e` | GDPval semantic/fixture/implementation appendix saved; final resume alignment pending; initial NLTK patch reviewed/rejected |
| 07 | `checkpoint/design-pr07` | `4ab6f321be221e5e8b393d6c905fbcd72512dc5b` | Stirrup generation contract draft saved; exact dependency resolution/audit pending |
| 08 | `checkpoint/design-pr08` | `4579b77f14cb0b66e0fcdb207b6fe8b7af210686` | Final protocol/fixtures and 45+175 verified-prefix generation/resume contract saved; implementation pending |

PR02c contract SHA-256: `a755aa7ef611238258308146ac8d602e4b9debd1e644a1e9b795616c95ce86fc`.
Its two files and ref were read back and matched the saved bytes/Git blobs before implementation started.
PR09 contract is reachable on `checkpoint/design-pr09` at `a26a92a31a7657799573337dc8c9876b440b5842`
(`contracts/pr09-builder-experiment-contract.md`), with frozen input/barrier/namespace/protection/resume semantics.
PR10/11 bounded deletion/acceptance task contracts are started on `checkpoint/design-pr10-11` at
`3eb2d84ed8dafd8284abebfea695be61e04b98f9`; exact final source inventory is still being completed.
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
migrations. All four changed files and the new ref were read back exactly. A separate clean diagnostic checkout
ran 526 harness unit tests: one failure and 33 errors, identifying the scoped legacy fixture ports. Its 48 focused
Cursor/generic tests had two old metadata assertions to update; strict typing identified four concrete issues.
The next bounded fix is saved/read back at `621be5d6b43ef65b0f4c75d3c414aca0bb05a7f9`; on that exact clean
head, all 48 focused tests, strict mypy of three changed files, and Ruff lint/format pass. Full-suite/coverage and
acceptance are not claimed. The minimal GDPval `task_inputs` execution wrapper change is saved/read back at
`6e7bc240de3a3ad0faaf05c4e2b4bde787314c4b`; that exact clean head passes all 31 snapshot and benchmark-boundary
tests, scoped strict mypy of its three source/test files, and Ruff lint/format. The first real generation handoff
file was saved at `9a9f144537f4dc276e18c029666be229547e371c` and passed all eight integration tests. Its five
static type/import issues were fixed at `f972a82558609255f84723b9d4c060503eef894a`; this exact clean head passes
all eight integrations, scoped strict mypy and Ruff lint/format. Luna is adding systemic-failure and seal/index/path
cases next; Sol independently reviews the saved production source. Tamper cases, fixture ports and full gates remain open.

PR04 dependency audit identified an unresolved official NLTK advisory
[GHSA-8mgp-746c-j5xp / CVE-2026-81726](https://github.com/nltk/nltk/security/advisories/GHSA-8mgp-746c-j5xp).
The official advisory reports no patched release as inspected on 2026-09-13. Exact rejected requirement locks
and full audit reports are saved in the PR04 design checkpoint. The Python 3.11.16 candidate lock has 160
distributions and exactly the NLTK finding. Its initial minimal backport is rejected after independent Sol review:
normal tagger loading raises NameError, hardlinked outside data can be truncated before rejection, and normal
defaults/special-file paths are not correctly covered. Prior source/evidence stays recoverable; a bounded replacement
option is under review. Its truthful local package version also cannot produce a clean standard pip-audit result.
No CVE ignore rule, false version, sandbox-based exemption, gate weakening or acceptance is authorized. Any proposed
exception would require the user's explicit plan amendment. Runtime provisioning and other authorized preparation continue.

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
