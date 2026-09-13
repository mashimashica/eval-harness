<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Migration state

Updated: 2026-09-13T09:44:20Z

Control branch: `checkpoint/migration-control`.
Procedure: [MIGRATION-WORKFLOW.md](MIGRATION-WORKFLOW.md).
This record preserves recoverable work; it does not declare the migration accepted.

## Latest recovery point: fixed Linux CI promoted; public boundary implementation

Implementation `checkpoint/pr-04` is saved at
`7ebef3f004fad1a8df88792dfac6f0db7b1dd3c7`, tree
`937e7d73b2179c0099b9f4a57279536beadb6c63`. Its source is the reviewed
`0c919a5cd1256af121a912bef5a42cf41d5e360b` plus a saved next-batch work record.
It adds the fixed Ubuntu candidate
provisioning/audit workflow and exact-vendor gate/attribution changes. Luna reports
YAML/TOML parsing, shell syntax including added run blocks, exact vendor selector checks
and scoped vendor pre-commit behavior passing at preceding `92408b9d`. Sol found two
workflow defects, both reproduced and source-closed in this correction: the installer's
resource directory is now physical/absolute, and preflight false/exception fails while
true alone continues. Luna's grouped correction checks all pass and Sol closed both
findings with no remaining delta defects. Parent ran
`pre-commit run --all-files` on the exact correction in a separate temporary worktree:
all applicable hooks pass and the worktree remains clean. See
`reports/m2-ci-preparation-validation.json`. Reviewed source was promoted unchanged to
Draft PR #43 (`migration/04-isolated-grader`, head `0c919a5c`, base PR #42 at
`6038a7828d62247ad98d000bc6e71c706f6d14a4`) to run real Linux checks; results are pending.
Luna is assigned public attestation/run followed by shared callers/readonly environment
resolution/old runner deletion, deadline 10:30 UTC, with coherent saves before validation
and within 15 minutes. Parent collects CI evidence. No other PR is being implemented.

The preceding preparation component is locally closed at `e2a5a6a7` (14 tests,
strict typing, Ruff, shell syntax and Sol). A separate parent whole-suite baseline on
that head failed locally: initial /tmp-symlink test setup was corrected once; the
physical-path attempt ran 610 unit methods with 11 failures and two errors involving
the existing Linux-only Cursor guard and case-insensitive collision fixtures. Measured
coverage is 10954/11791 = 92.90%, below the exact 96% gate. See
`reports/m2-local-suite-baseline.json`. Do not relax guards, count this as accepted,
or repeat the same local platform checks. Fixed Linux CI and meaningful additional
PR04 host/worker coverage remain required. Both local test sessions have finished.

Current interval deadline remains `2026-09-13T10:33:34Z`; after save/readback/report,
continue the next interval autonomously. The heartbeat id is `automation`. New issue-level
stop rules, preserved failure history, DCO/non-force/readback, 15-minute saves, role split,
one-PR implementation, no models/merge/release, CVE hold and final deletion requirements
below remain authoritative. Main and pre-existing user changes are protected.

## Autonomous continuation policy and preceding interval notes

Preparation component local closure is verified at
`e2a5a6a74c14a6577900859c7a4cc33d98482562`, tree
`84afcaa43ab36e025bf741882731a127c81a54ff`: 14 unit tests, scoped strict mypy,
Ruff lint/format, shell syntax and independent Sol review pass. See
`reports/m2-preparation-local-closure.json`. The two historical official uv failures
are retained, not reset. This is not Linux provisioning or PR04 acceptance.

Next coherent PR04 batch: Luna adds the frozen Ubuntu 24.04 CI environment path to the
existing eval-harness workflow, with strict audit kept red and a separately named
non-acceptance candidate job using the saved installer. It must genuinely provision,
run pip check and invoke the public preflight seam; the still-unimplemented seam must
fail, not be mocked, skipped or reported as a completed boundary test. Add only the
already authorized exact-vendor lint/copyright exclusions and source attribution needed
for the PR gate. Parent then promotes the reviewed batch to a Draft PR against accepted
`migration/02c-generation-handoff` (`6038a7828d62247ad98d000bc6e71c706f6d14a4`) and
collects actual Linux evidence while Luna implements public attested launch/common callers.
No new workflow is dispatched merely for checkpoint saving. All final security/parity/
coverage gates remain mandatory. GitHub Actions is enabled; existing workflow triggers
are pull requests and main pushes, so no merge or unreviewed dispatch is needed.

Current saved/tested implementation is `bbf96b7e3616d670cf784b2087aff39eab8d5e74`,
tree `05dc5cb7e8c06f65d73890f08b965a406f54428b`. All 13 preparation unit methods,
strict mypy (three files), Ruff lint/format and shell syntax pass. Sol closes existing
archive preservation and both owned partial-output cleanup branches, plus the earlier
test defects and shell multiline rejection. Two shell-only findings remain: quoted
executable capture for paths containing spaces, and embedded CR rejection. See
`reports/m2-preparation-cleanup-closure.json`. One bounded Luna correction is assigned
only the shell installer and preparation test file, before the public boundary/caller
implementation. No real Linux or PR04 acceptance is implied.

Sol's fixed-head review and parent evidence reconciliation are complete; see
`reports/m2-preparation-revised-correction.json`. The original official uv refusal is
closed with its two-failure history retained. Existing archive deletion is source-closed.
Remaining preparation corrections are partial-creation cleanup, test portability/type/
format, and a distinct shell multiline-validation defect found by parent reproduction.
Luna receives these in one batch, also explicitly selecting the already pinned Ninja
build tool rather than inheriting a host executable. No dependency pins are changed.

Latest implementation checkpoint: `26a87464f980ab9bf911a120f2f1cf8bceaf4008`, tree
`8567d56333ec27a869e5bc34d01627130235afee`. Test-first checkpoint
`64dc8d615e4d145ecfc211ea5c1bd59cd98cab5f` reproduced both uv refusal and existing
archive deletion (two expected errors). The revised correction is saved/read back.
Its grouped checks report 11/12 unit methods passing, including the official uv suffix
regression; the archive test stops at macOS realpath string comparison, one strict-mypy
test import error remains and the test file needs Ruff formatting. Ruff lint and shell
syntax pass. Sol is reviewing this exact head read-only, including prior unclosed
preparation findings. Luna is idle pending one consolidated review/verification return.
No successful batch or preparation/PR04 acceptance is claimed.

An active thread heartbeat, automation id `automation`, continues this same task every
90 minutes under these rules. It must reuse active work/agents rather than duplicate
them and stop itself at final completion or a genuine whole-task safety/authority block.
Local scheduled work requires the computer and application to remain running. Normal
active work in this segment continues; this is not a reason to wait for the next tick.

The user explicitly changes the two-failure rule. Two failures end that correction
approach, not all migration work. Preserve the failure history, save, analyze the cause
and revise the approach. One additional correction/validation is authorized without
confirmation when its specific cause and verification can be stated. If that extra
attempt fails, hold the issue and dependent acceptance; continue independent in-plan
work. Stop the whole task only when no safe work remains or new authority/requirements
need user judgment. Do not reset counts at a new interval or owner. This supersedes
the stop instructions retained below as history and applies to the current uv issue.

The current interval begins `2026-09-13T09:03:34Z` and ends no later than
`2026-09-13T10:33:34Z`. After saving, readback, state update and a concise progress
report, continue another interval without user confirmation unless the revised stop
conditions apply. Save each coherent batch before validation and within 15 minutes.

Recovery verified remote implementation `90dc9d17f0c10532028ace4f8657240b6e742a26`
and control `271a2a0e3e19ef818705e5ecfb626cfbfc4cce54`. Main is clean and unchanged.
Reuse Luna as sole source writer and Sol as read-only fixed-commit reviewer. Parent
owns scope, routine checkpoint transport, consolidated evidence and acceptance.
No grandchildren, no simultaneous PR implementation, no real-model experiments,
merge or release. Preserve all quality, CVE hold and final contract-deletion requirements.

### Revised preparation correction: explicit cause and verification

Uv failure history remains two failed corrective rounds. Root cause: prefix slicing
retains a delimiter space while the next predicate requires an opening parenthesis.
Retire the contradictory chained prefix/suffix checks. Validate the complete version
output against one explicit exact-version grammar: bare `uv 0.11.29` or that exact
version followed by a well-formed nonempty parenthesized official build suffix. Reject
near versions, extra tokens, missing/empty/malformed suffixes and embedded newlines.
Reuse the already saved official-output regression and add boundary cases before
the one authorized additional correction. Do not fetch or research the fixed tool again.

Bundle the independent archive cleanup defect with this correction. Exclusive-create
failure must not delete pre-existing bytes or symlinks. Reproduce in a private temporary
fixture first; cleanup may remove only files created by this invocation. Test refusal
and partial-write cleanup without touching real user data. Then save the source/test
delta before the grouped unit/strict-mypy/Ruff/shell checks and Sol fixed-head review.

Luna's bounded assignment uses base `90dc9d17f0c10532028ace4f8657240b6e742a26`,
only installer Python/shell and preparation tests, plus parent-owned work records.
Deadline `2026-09-13T09:32:00Z`; parent will independently prepare the existing Linux
validation workflow path, without reviewing mutable implementation or repeating closed
host/bootstrap/dependency work. The preparation module is not real sandbox acceptance.

## Previous stop record: second corrective failure, 2026-09-13T08:47:25Z

The explicit resume at `2026-09-13T08:42:27Z` preserved the previous failure count.
The saved second preparation correction at
`7757c8ae9cd18681c789e2294d02597bcc4c39e3`, tree
`dd4c83b28cbbc138236154c7aee0714f4339cec1`, was checked once in the clean detached
review worktree. Ten of eleven preparation unit methods passed; the official fixed uv
version output was still rejected. Strict mypy (three files), scoped Ruff lint/format
and bubblewrap installer shell syntax passed. These are partial local checks, not a
successful validation batch, actual Linux installation, or PR04 acceptance.

Sol independently confirmed that `_verify_uv_version` retains the separating space
in the substring tested for an opening parenthesis. The official `uv 0.11.29` build
metadata is therefore still rejected: the same issue remains after corrective round
two. Sol also identified that `_install_nltk_package` unlinks an existing archive after
exclusive creation refuses it. Other prior findings have no additional independent
closure from this stopped review. Evidence: `reports/m2-preparation-second-correction.json`.

The user's two-failure stop rule is active. No third correction, further quality test,
installation, external job or subsequent PR implementation was started. Further work
requires explicit user direction addressing this stop; a resume must not reset the
failure count. The original design and quality requirements remain unchanged.

Durable implementation checkpoint: `checkpoint/pr-04` at
`90dc9d17f0c10532028ace4f8657240b6e742a26`, tree
`9512e2469b787a7f82703b050d52415a78d5022e`. This adds only the stop record in
`contracts/pr04-work.md`; production and test sources are identical to the tested head.
It was saved with DCO, a non-force ref update and remote ref/tree/blob/byte readback.
This control record and the consolidated evidence are saved separately using the same
procedure. Existing history and checkpoint branches are preserved.

Luna and Sol are stopped/completed. All parent commands have returned; no residual
process session or CI job was started by this segment. Main remains untouched and clean
on `main` at `adb6adf4ec0113790a326a67325ced5716dc6837`. Worktrees are aligned only
after proving their local saved bytes match the remote checkpoint.

Earlier host and bootstrap component closures are retained without retesting. PR04
fixed Linux provisioning, public preflight/launch, common evaluator/resource-server
callers, old runner removal, real sandbox checks and all 1,140 native parity cases
remain unfinished. PR05–11 remain unimplemented. NLTK CVE and relevant acceptance are
still held; no audit exclusion or version spoofing is permitted. Final old-route and
`contracts/*.md` deletion, fourth benchmark and whole-head quality gates remain pending.
No real-model experiment, merge, release, PR04 acceptance or migration completion is
claimed.

## Previous resume record, 2026-09-13T08:42:27Z

The user explicitly resumed at `2026-09-13T08:42:27Z`. The work interval ends no later
than `2026-09-13T10:12:27Z` (90 minutes). No failure count is reset by this resumption.
One preparation corrective round failed; the second saved correction remains unverified.
If its verification/review leaves the same issue, save and stop under the existing rule.

Fresh remote-ref and local recovery checks agree on implementation
`checkpoint/pr-04` at `7757c8ae9cd18681c789e2294d02597bcc4c39e3`, tree
`dd4c83b28cbbc138236154c7aee0714f4339cec1`, and prior control head
`6e8a5f94e6ca2793a0310d24905e4ff0a75dd7fd`. All worktrees were clean; root remains
unchanged on main. Reuse Luna (source implementation) and Sol (read-only review); parent
owns consolidated verification, evidence, checkpoints and acceptance. No grandchildren
or concurrent implementation PRs. Closed host/bootstrap evidence and fixed design inputs
are reused without reopening their investigation.

First action: parent runs preparation unit/mypy/Ruff/shell checks on the exact saved
implementation; Sol independently reviews the fixed second-correction delta. No new
implementation or real installation starts before that judgment. If closed, continue
the existing PR04 fixed Linux/common-callers/legacy-removal/real-boundary/parity plan,
then the saved PR05–11 designs. All CVE, quality, final contract deletion, no-model,
no-merge/release and 15-minute durable-save constraints remain unchanged.

## Previous pause state, 2026-09-13T07:57:15Z

The user requested a safe pause because communication is unstable. Do not start new
implementation, validation, review or external jobs until the user explicitly resumes.

Exact implementation resume branch: `checkpoint/pr-04`.
Exact resume SHA: `7757c8ae9cd18681c789e2294d02597bcc4c39e3`.
Tree: `dd4c83b28cbbc138236154c7aee0714f4339cec1`.
Its four changed files (second preparation correction in three source/test files plus
`contracts/pr04-work.md`) were saved with DCO sign-off and non-force ref update. The
remote ref, tree modes, Git blobs, decoded bytes and current local bytes were read back
and matched. The implementation worktree has no unsaved changes after alignment.

Validated earlier: host findings closed at `e012ccc4` (37 tests, strict mypy, Ruff and
Sol review); offline bootstrap closed at `debe87e5` (6 tests, strict mypy, Ruff and
Sol review of identical production source). These are component results, not PR04
acceptance. Preparation first correction at `d8e7653b` has five unit passes but four
mypy errors and independently confirmed remaining defects; see
`reports/m2-preparation-first-correction.json`.

The second preparation correction at the resume SHA is UNVERIFIED: no parent unit/mypy
run and no Sol fixed-head closure review. Luna reported only scoped Ruff/format/diff
checks before the pause. No new checks were started after the stop instruction.
There is one failed corrective round for preparation; this untested second correction
does not count as another failed verification. Preserve the two-failure stop rule.

Next concrete action ONLY AFTER EXPLICIT RESUME: restore this exact SHA, then run the
preparation unittest module, strict mypy over `eval_harness/grader_sandbox.py`,
`scripts/ci/install_bigcodebench_grader.py` and
`tests/harness/test_bigcodebench_grader_boundary.py`, scoped Ruff/format and shell syntax
as one validation batch. Sol then reviews this fixed correction read-only. If the same
finding remains after this second correction, save and stop; do not start a third fix.
If closed, continue the saved PR04 design with actual Linux provisioning, public
preflight/attested launch, common callers, old runner deletion and real sandbox/1,140-task
parity. Those features and all PR05–11 implementation remain unfinished. NLTK CVE,
unclarified data redistribution licenses, final old-route/contract deletion, fourth
benchmark and whole-head quality gates remain unresolved; nothing is accepted by waiver.

Process/job state at pause: Luna and Sol both show completed/idle and were sent explicit
stop instructions. All parent tool commands and diagnostic subprocesses have returned;
there are no residual sessions or CI jobs started by this segment and no job IDs to
resume. No destructive process termination was used. No real-model experiment, PR04
promotion, merge or release was started. Existing external jobs and history are untouched.
The main root remains clean on `main` at
`adb6adf4ec0113790a326a67325ced5716dc6837`. Worktree ownership and frozen designs are
unchanged. The control checkpoint containing this record is saved/read back separately.

## Pre-pause context: M1 accepted; M2 host findings closed, remaining PR04 incomplete

The user explicitly resumed from the saved implementation head and requires reproductions
before the two P1 corrections. Verified recovery is implementation
`7be35da9fae98c5e56ba14bf13a15a4cdbb9a8e7` and control
`2d36c56c8056bd34186ed11da5004e0e01188dc8`; no local edits needed protection beyond
keeping the clean main root untouched. Current implementation checkpoint is
`d8e7653b704d2ba8a3b03ca966f9caf31b1f9bfc`, tree
`f483df8105dd8bf1ca8c1662d423cf07843943a1`, saved and read back.

All three new reproductions fail as intended against the unchanged host: simulated
terminal/exit teardown lasts 6 instead of 5 seconds, success/exception cleanup lasts 2
instead of 1 second, and the natural-exit race returns a resource result without raising
infrastructure error. See `reports/m2-host-red-reproductions.json`. These are expected-red
baseline results, not failed corrections. After one incomplete parent corrective review,
the final batch passes all 37 unit methods, strict mypy and Ruff on the saved head.
Sol's fixed-head independent delta review has no remaining actionable finding: shared
absolute deadlines and actual reaped termination outcomes close both P1 issues. Parent
accepts this component closure only, not PR04. See `reports/m2-host-closure-validation.json`.
The separate offline bootstrap passes six unit methods, strict mypy and Ruff at
`debe87e5`. Its fresh stdlib venv tests execute actual isolated interpreter startup and establish
fatal failure before user code for missing/malformed NLTK, without leaking an exception's
secret-bearing message. Policy-absent startup needs no NLTK. Sol independently closed the
automatic-startup finding on the identical production source at `8699bcee`; see
`reports/m2-bootstrap-local-validation.json`. This is component closure, not actual NLTK,
Linux sandbox or PR04 acceptance. The first fixed-environment preparation batch is now
saved. Five preparation unit methods have four passes and one error (candidate JSON is
not canonical); strict mypy finds two new test typing errors, while Ruff and shell syntax
pass. Parent review additionally identifies incomplete NLTK layout/identity, bwrap mode
handling and runtime provenance. Sol completed the fixed-head review and confirmed seven
blocking preparation issues; `reports/m2-preparation-review-88fdbcff.md` records them.
The first correction passes five unit methods (0.014 s), Ruff and shell syntax, but has
four installer mypy errors. Parent actual-file probes confirm the package-id directory
is still dropped and an empty vendor hash map is accepted. Sol independently confirms
remaining Ubuntu/identity/runtime binding and regression gaps. See
`reports/m2-preparation-first-correction.json`. One corrective round has failed to close
the preparation findings; a second failure for the same issue requires saving and stopping.
No real installation is authorized by these partial results. Host supervision
remains unchanged except allowed preparation helpers. No Linux job or dependency install
has executed, and common callers/preflight/old-runner removal remain outstanding.
Parent also verified the immutable v0.1.4 parity Parquet hash, size, all 1,140 unique IDs and
required canonical fields without running any solution. See `reports/m2-parity-input-identity.json`.
This is input identity evidence, not executed parity. No other PR is implemented in parallel.

New allowance: `2026-09-13T06:54:57Z`–`2026-09-13T08:24:57Z`, maximum 90 minutes.
Luna first edits only the existing runner test file to reproduce late-exit/cleanup budget
restart and third-poll trusted exit; host source remains unchanged for the expected-red
baseline. Then save a combined correction, run related tests/mypy/Ruff together and have
Sol review the fixed head. Parent owns evidence/checkpoint integration. No grandchildren,
one active implementation PR, same stop/save/quality requirements. Prior designs and
closed dependency evidence are reused. GitHub Actions is enabled for the required later
Linux job; no job or PR was started just to save this checkpoint.

After the two findings close, continue PR04 fixed environment/preflight/shared callers,
old-runner deletion and real probes/parity. CVE-only blockage holds acceptance while
independent implementation continues. Final deletion, fourth benchmark and all quality
gates remain incomplete. Progress reports focus on behavior/findings/barriers.

## Previous segment: stopped under the two-failed-correction rule

The user resumed the migration from `aa7e2cc9df25795be50559ea5c5d986af020c933`.
Root recovered the complete original plan, workflow, latest/historical state, M1 acceptance
and M2 worker evidence from control `02cba161d480f45d3eb955eaad035488bde936c4`.
All remote Draft heads 38–42 and the frozen design refs were checked and match this index.
The previously reported local clone was absent, so a fresh clone was made; its root remains
clean on `main`. Implementation runs in a separate worktree from the exact PR04 checkpoint.

Current implementation checkpoint: `checkpoint/pr-04` at `7be35da9fae98c5e56ba14bf13a15a4cdbb9a8e7`,
tree `fa72b8f742f60496e9380353f7c8f7c3b3c515f0`; ref and changed UTF-8 files/Git blobs
were read back. This final save changes only the work record. Its source/test blobs are
identical to `5678340634362d155a5b98f296b1a75a34c8dc07`, whose 31 unit methods, strict
mypy of both files and Ruff lint/format pass without ResourceWarnings. See
`reports/m2-host-local-validation.json`; this is partial validation, not PR04 acceptance.

Sol's fixed-host review leaves two P1 defects, independently confirmed by Astra:
teardown deadlines restart across outer exit/cleanup and exceed the contract budget;
and a trusted-exit race can return a candidate resource-limit result without actual host
enforcement. The latter can misclassify infrastructure as zero score. Other host-delta
findings closed, but the two counterexamples are not covered by passing unit checks.
See `reports/m2-host-review-058a5878.md` for exact locations and recovery instructions.

The teardown-bound problem remained after two corrective reviews (e839a8cb, 058a5878).
Astra applied the user's stop rule before the 90-minute cap: no third correction, no new
implementation, save and report. Luna stopped the independent bootstrap batch before
editing files. Both agents are idle. Public attestation/launch remain closed; preflight,
provisioning, caller replacement, old runner deletion, real Linux validation and native
parity remain unfinished. No formal PR04 Draft was promoted. PR05–11 remain unimplemented.
Root's finite read-only implicit-root clarification is preserved in the amended contract.
Luna is the sole implementation owner; Sol reviews saved commits without source edits;
Astra owns API checkpoints, integration and acceptance. No grandchildren are used.

Current allowance is 2026-09-13T05:58:23Z–07:28:23Z (90 minutes including recovery).
On a user-authorized continuation, first close the two saved host findings in only
`eval_harness/grader_sandbox.py` and `tests/harness/test_bigcodebench_runner.py`; preserve
the fixed contract/amendment and save before consolidated validation and independent review.
Runtime provisioning, caller replacement, real Linux boundary/native parity and full PR04
acceptance remain pending. The local host is macOS arm64, not the required Linux acceptance
platform. The locked development environment was recreated successfully with uv 0.11.29 and
CPython 3.13.14; `uv.lock` is unchanged. The attached original plan matches the control-branch
copy exactly at SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.

The user explicitly requires removal of all tracked `contracts/*.md` from final implementation
head after incorporating necessary permanent specification into formal docs. History and
checkpoint refs remain preserved. This requirement supersedes conflicting saved designs.
The NLTK CVE acceptance hold, closed investigation, no model experiments/merge/release,
two-failed-correction stop rule and all quality gates remain unchanged.

## Previous segment status: M1 accepted; M2 partial and paused after user progress report

The user's latest steering requested an immediate intermediate report because elapsed time was excessive.
Root reported progress and limited the remaining segment to the existing worker correction, verification
and durable save, ending no later than 2026-09-13T05:41:18.195Z. No host supervisor or later slice was started.
This segment is now stopped after saving the result below. The overall migration goal is unchanged.

| Logical scope | Durable state | Next completion work |
| --- | --- | --- |
| PR01–03 and additional PR02c / M1 | Implementation gates passed; five Draft PRs remain unmerged | Revalidate affected behavior at final migration head |
| PR04 / M2 | Protocol and inner-worker source corrected, reviewed and locally validated | Host supervisor, provisioning, caller replacement, real boundary/parity and PR gates |
| PR05–09 / M3–M5 | Exact design checkpoints preserved; implementation not started in this recovery | Independent evaluation, benchmark and experiment-path integration |
| PR10–11 / M6–M7 | Not implemented | Old-path deletion, documentation, fourth benchmark and final acceptance |

M1 accepted unmerged Draft [#42](https://github.com/mashimashica/eval-harness/pull/42):
branch `migration/02c-generation-handoff`, head `6038a7828d62247ad98d000bc6e71c706f6d14a4`,
tree `4f7fc21be5195611ba7df8feeefe3a5cc962c2cb`, base `d5ce0c10162cad788a17cb90f34b8f60574e7f75`.
All four required hosted workflows pass; synthetic merge tree matches. Coverage is 10070/10469
(96.18874773139746%), with 553 Python, six shell, 45 compatibility and five inventory tests passing,
strict typing, DCO and a clean locked main dependency audit. See `reports/m1-acceptance.md`.
M1 elapsed approximately 34 minutes, starting 2026-09-13T03:56:46Z and accepted 04:30:56.162Z.

M2 started 2026-09-13T04:30:56.162Z. Its saved and tested checkpoint is
`aa7e2cc9df25795be50559ea5c5d986af020c933` on `checkpoint/pr-04`, tree
`b55c6d32c394f25d1ba77467e5d8cc68a6fb0590`. The local worktree is clean.
The implementation base is accepted PR02c. Frozen vendor/build/data inputs and interpreter hashes match.
Exact contracts, reviewed finite amendments and the work record are on that branch.

At this head, all 14 unittest methods and subcases pass on exact Python 3.13.14 and 3.11.16;
strict mypy of three authored files and scoped Ruff lint/format pass. Sol verified the immutable
worker blob and closed all three worker findings: exact default Process interception, native limits
derived from trusted whole-MiB values before import, and authenticated overflow failure after a key.
Production and smaller-limit native regressions are both retained. The seven initial typing errors
and failing mock callback are fixed in this consolidated corrective validation round.
See `reports/m2-worker-validation.json` for exact source identity, local logs and evidence limits.

These are unit correctness results. No real sandbox security, host supervision, provisioning,
all-1,140 parity, final caller replacement, whole PR04 coverage or hosted PR04 CI is claimed.
PR04 has no formal Draft PR yet. Old grader routes still remain and must be deleted before completion.

The known NLTK CVE remains an acceptance blocker for PR04 and affected later heads; it does not
block independent authorized implementation. M0 investigation remains closed: no repeated investigation,
rejected patch, audit ignore, false version or sandbox-based exemption. Candidate-only functional
preparation is explicitly non-acceptance and cannot be selected by production constructors.
All quality gates remain unchanged. No real-model experiments, merge, release or publish.

Before resuming, use this exact checkpoint and its existing contracts; do not repeat closed codec/worker
reviews or dependency research. The next coherent implementation target is the host supervisor and its
callable path, followed by provisioning and caller integration. Keep one Luna implementation owner,
Sol review and Astra acceptance; report exceptions early, save within the checkpoint interval, and
do not silently extend the agreed working allowance.

## Historical records

The following sections preserve earlier recovery states. Their pending-state wording is historical
and superseded by the current status above.

## Historical implementation base at PR03

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

M1 implementation is active under the user-approved amendment. Previously returned PR02c batches remain saved.
Root owns all remote checkpoint writes, saves each batch before validation, and verifies common-base blobs before
combining reviewed deltas. Each branch has one writer; no future migration slice is implemented in parallel.
Sol design/review proceeds independently; drafts below are saved work, not implementation acceptance.

| Slice | Checkpoint branch | Saved commit | Saved contract / state |
| --- | --- | --- | --- |
| 02c | `checkpoint/pr-02c` | `2aa8c28b3f074f5e8887fcdccf883123b85199a1` | Reviewed Cursor fixture delta integrated; common CLI handoff test remains incomplete; whole-head gates pending; active M1 under the 90-minute budget |
| 04 | `checkpoint/design-pr04` | `deb807e8454eb4fbb3652bb1f335489fa5325bea` | Final grader design/appendix, exact dependencies/source/licenses and rejected patch evidence saved; strict NLTK audit red; implementation pending |
| 05 | `checkpoint/design-pr05` | `7e7629c330ca0841ee92612f534db72c0a459b2b` | Final PR05 APIs plus PR02c fixture/consumer amendment and four-finding closure review saved; implementation pending |
| 06 | `checkpoint/design-pr06` | `f598dbe34b38dcb9f5bb8f9309283c88c7a2dab9` | Final GDPval API contract/appendix aligned with PR05 exact resume/events/aggregate interfaces; implementation pending |
| 07 | `checkpoint/design-pr07` | `e0fab6018c59338f5301a13e29e6c5c39f5e3305` | Final Stirrup/provider/dependency/protected-role contract saved; real Apptainer CI and implementation remain |
| 08 | `checkpoint/design-pr08` | `4579b77f14cb0b66e0fcdb207b6fe8b7af210686` | Final protocol/fixtures and 45+175 verified-prefix generation/resume contract saved; implementation pending |

PR02c disjoint work branches, both based on `3f37a1b7e7e6e74900d475dd018a25931acca04e`:

- `checkpoint/pr-02c-selected-consumer` at `77f33247e6436f92d186a1e89ef4cf538ff1ab9e`: 48 tests pass
  at its source parent, the two assertion-only typing fixes pass the affected real snapshot test and strict typing
  of all five files; Ruff and independent source review pass. Promoted into primary b2a4ea43 after five unchanged
  common-base blob checks.
- `checkpoint/pr-02c-cursor-fixtures` at `9bcdee9ab8c5b8732bcb2a044ae998303154d0f5`: two Cursor fixture files
  saved/read back; all 43 tests, strict mypy and Ruff pass. Independent fixture review reports no findings; primary
  promotion is preserved at 2aa8c28b; combined-head acceptance remains open.

The real Cursor common CLI integration remains incomplete in the saved handoff test file; its implementation resumes at M1.
CLI runtime-root plumbing and legacy Cursor rejection are saved and validated at e8571865. The current batch also fixes the independently reviewed snapshot-missing-byte and valid-but-missing
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

Next actions under the accepted purpose-first amendment:

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
