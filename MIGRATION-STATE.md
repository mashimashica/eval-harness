<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Migration state

Updated: 2026-09-13T00:24:04.831Z

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
| 02c | Generation handoff implementation and focused validation | Source recovery and full validation required |
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

Only PR02c implementation is active. Luna owns its isolated worktree and checkpoint branch.
Sol design/review proceeds independently; drafts below are saved work, not implementation acceptance.

| Slice | Checkpoint branch | Saved commit | Saved contract / state |
| --- | --- | --- | --- |
| 02c | `checkpoint/pr-02c` | `039f5524b8fc4a7d51f2bf2521cbdbf1a71cc705` | `contracts/pr02c-reconstruction.md`, `contracts/pr02c-work.md`; design accepted, Luna implementing; no new test claim |
| 04 | `checkpoint/design-pr04` | `31b3344c9c0f0f66d25265153f405d06dfa25c20` | Grader boundary contract, evidence, and checkpoint record; draft, remaining sandbox/lock proof |
| 06 | `checkpoint/design-pr06` | `2b4a597d94f800fc28bcce70e6ccbfc419303f1c` | GDPval rubric/pairwise/panel design draft; exact fixtures still being completed |
| 08 | `checkpoint/design-pr08` | `bd490241c0b29ceef11133693117ea6499c7e427` | AA-v2 protocol design draft; exact hashes/fixtures/resume rules being completed |

PR02c contract SHA-256: `a755aa7ef611238258308146ac8d602e4b9debd1e644a1e9b795616c95ce86fc`.
Its two files and ref were read back and matched the saved bytes/Git blobs before implementation started.
Sol also owns bounded PR05 and PR07 design work; no source implementation is running for those slices.
New design documents are reconstructions from the original plan and accepted APIs, not recovered lost files.

Next actions, in order:

1. Luna implements PR02c within the saved path/API contract and checkpoints each coherent batch before testing.
2. Sol reviews the saved implementation; close focused tests and all unchanged required gates on its resulting head.
3. Root promotes the reviewed slice to the Draft stack, verifies the saved head and CI commit/tree evidence.
4. Advance through PR04–09 one accepted implementation slice at a time.
5. Delete replaced routes in PR10 and close fourth-benchmark/final-head acceptance in PR11.

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
