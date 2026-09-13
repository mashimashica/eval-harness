<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Migration state

Updated: 2026-09-13T03:09:14.600Z

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

Only PR02c implementation is active. Luna owners edit bounded disjoint source/test batches in separate checkouts.
Root owns all remote checkpoint writes, saves each batch before validation, and verifies common-base blobs before
combining reviewed deltas. Each branch has one writer; no future migration slice is implemented in parallel.
Sol design/review proceeds independently; drafts below are saved work, not implementation acceptance.

| Slice | Checkpoint branch | Saved commit | Saved contract / state |
| --- | --- | --- | --- |
| 02c | `checkpoint/pr-02c` | `549339ab6f36a788a5eb7fa83851af9d7546fcf6` | Saved handoff tamper batch passes 13 tests/strict typing/Ruff; independent review requests two bounded test refinements; CLI/fixture/full gates remain |
| 04 | `checkpoint/design-pr04` | `deb807e8454eb4fbb3652bb1f335489fa5325bea` | Final grader design/appendix, exact dependencies/source/licenses and rejected patch evidence saved; strict NLTK audit red; implementation pending |
| 05 | `checkpoint/design-pr05` | `7e7629c330ca0841ee92612f534db72c0a459b2b` | Final PR05 APIs plus PR02c fixture/consumer amendment and four-finding closure review saved; implementation pending |
| 06 | `checkpoint/design-pr06` | `f598dbe34b38dcb9f5bb8f9309283c88c7a2dab9` | Final GDPval API contract/appendix aligned with PR05 exact resume/events/aggregate interfaces; implementation pending |
| 07 | `checkpoint/design-pr07` | `e0fab6018c59338f5301a13e29e6c5c39f5e3305` | Final Stirrup/provider/dependency/protected-role contract saved; real Apptainer CI and implementation remain |
| 08 | `checkpoint/design-pr08` | `4579b77f14cb0b66e0fcdb207b6fe8b7af210686` | Final protocol/fixtures and 45+175 verified-prefix generation/resume contract saved; implementation pending |

PR02c disjoint work branches, both based on `3f37a1b7e7e6e74900d475dd018a25931acca04e`:

- `checkpoint/pr-02c-selected-consumer` at `3a077a4ad3bb68a27e3acd89b185bc04158f9afd`: existing selected-task
  adapter and four non-Cursor fixture files saved/read back; 48 tests and scoped Ruff pass. Strict mypy finds two
  test-only conversions from object to dict; a bounded fix and independent source review are active.
- `checkpoint/pr-02c-cursor-fixtures` at `6fb7952b76587259d5145aaf6b83208cf20ca891`: two Cursor fixture files
  only; initialized/saved before editing; no validation yet.

Primary owner is implementing the exact CLI runtime-root plumbing and legacy Cursor shell rejection in three disjoint files.
Its following handoff integration batch also fixes the independently reviewed snapshot-missing-byte and valid-but-missing
indexed-bundle-link test cases. The saved tamper source itself passes all 13 handoff tests, strict mypy and Ruff.
All source/test scopes are disjoint. Side-branch bytes must be saved/read back and reviewed before combination.
The four original production findings are independently closed at exact `32169815cd455f3c5929ca643ebc69fe00260969`;
review record: `checkpoint/design-pr05:7e7629c330ca0841ee92612f534db72c0a459b2b`,
`contracts/pr02c-closure-review-32169815.md`, SHA-256 `02a7d52c8d42fdc24a969e6d6c1dd2e360d818a8afb1719d8aecbd05795aaac7`.
Independent verification passed 25 targeted tests; this does not close all PR02c gates.

PR02c contract SHA-256: `a755aa7ef611238258308146ac8d602e4b9debd1e644a1e9b795616c95ce86fc`.
Its two files and ref were read back and matched the saved bytes/Git blobs before implementation started.
PR09 contract is reachable on `checkpoint/design-pr09` at `a26a92a31a7657799573337dc8c9876b440b5842`
(`contracts/pr09-builder-experiment-contract.md`), with frozen input/barrier/namespace/protection/resume semantics.
PR10/11 bounded deletion/acceptance task contracts are started on `checkpoint/design-pr10-11` at
`7a3ce1d3859dca02d43828db6d970d7c0b47c45d`; exact legacy removal/behavior-port inventory and add-only fourth-fixture
acceptance contracts are frozen. The PR08 formal CLI spelling and future accepted implementation heads remain explicit
acceptance-time inputs. The fourth fixture uses fresh registries, ordinary execute() for typed fake failures, real
handoff/loaders, unchanged production coverage scope, and an offline diff check with the base provisioned in CI setup.
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
all eight integrations, scoped strict mypy and Ruff lint/format. The next bounded checkpoint `31307d471c3e240ad2f3a52aa7a5514607e8b175`
passes all ten handoff integrations and Ruff; strict mypy identifies two test-only imported-module symbol errors.
Sol's independent review at `01f781cbeaff00aee3fb0bea3597dee3bd58e2df` identifies four production corrections:
strict framed Cursor tree sealing/restoration, correct post-execution integrity classification, log-persistence error
preservation, and provenance capture before run-created paths. Luna is implementing these fixes with regressions in
a bounded four-file batch, saved/read back at `2cd4b02547bda84d230b46a0fbb0c20404089f66`. That exact clean head
passes all 63 Cursor/handoff/generic tests, strict mypy of the four changed source/test files, and Ruff lint/format.
A final two-file Cursor batch closes observed traversal identity/type changes and adds real execute regressions for
missing/replaced inputs, post-execution digest errors, and log-write interruption. Tamper cases, fixture ports and
all full acceptance gates remain open.

The unchanged main dependency audit is saved in `contracts/pr02c-evidence/locked-dependency-audit.md` and its exact
JSON report: 153 dependencies, zero findings/skips. This is dependency-only evidence from the identical dependency
inputs at clean `66c01eef`; formal CI on the resulting implementation head is still required.

PR04 dependency audit identified an unresolved official NLTK advisory
[GHSA-8mgp-746c-j5xp / CVE-2026-81726](https://github.com/nltk/nltk/security/advisories/GHSA-8mgp-746c-j5xp).
The official advisory reports no patched release as inspected on 2026-09-13. Exact rejected requirement locks
and full audit reports are saved in the PR04 design checkpoint. The Python 3.11.16 candidate lock has 160
distributions and exactly the NLTK finding. Its initial minimal backport is rejected after independent Sol review:
normal tagger loading raises NameError, hardlinked outside data can be truncated before rejection, and normal
defaults/special-file paths are not correctly covered. Prior source/evidence stays recoverable and is explicitly
marked rejected; it is not installed or adopted. No replacement is approved. Its truthful local package version also cannot produce a clean standard pip-audit result.
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
