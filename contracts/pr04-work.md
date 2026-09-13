<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR04 implementation work record

## User-authorized test-first continuation, 2026-09-13T06:54:57Z

### Current component state: host findings closed; offline bootstrap saved

At `e012ccc43d0129124efa63d14b223a1b4027d79f`, all 37 unit methods, strict mypy of
the two changed files and Ruff lint/format pass. Sol independently closed both original
P1 findings and found no remaining actionable defect in that fixed host delta. Parent
accepts only that component closure. Exact evidence is in control
`reports/m2-host-closure-validation.json`; real Linux/PR04 acceptance is still outstanding.

Luna now adds only `eval_harness/bigcodebench_sitecustomize.py` and
`tests/harness/test_bigcodebench_sitecustomize.py`: literal-policy-only configuration,
retained pinned downloader, fixed local index/data paths and bound aliases. This save
precedes grouped bootstrap unit/mypy/Ruff verification and independent delta review.
It does not install NLTK, prepare its data, or prove fresh/spawn/real-sandbox behavior.
Existing frozen offline evidence is reused; CVE research remains closed.

Fixed implementation base: `7be35da9fae98c5e56ba14bf13a15a4cdbb9a8e7`;
control recovery: `2d36c56c8056bd34186ed11da5004e0e01188dc8`. Both refs and clean local
worktrees match; no repeated plan/design/dependency investigation is needed. Root remains
on main. Astra, Luna and Sol retain their previous ownership and separate write scopes.

This user-authorized segment ends no later than `2026-09-13T08:24:57Z` (90 minutes).
First create deterministic reproductions of the two saved P1 findings in only
`tests/harness/test_bigcodebench_runner.py`, save them and demonstrate failure on the
unchanged host. Then Luna fixes both in `eval_harness/grader_sandbox.py` with associated
regressions; save once before combined unit/strict-mypy/Ruff checks and fixed-head Sol
review. No third failed correction for the same issue in this new segment is permitted.
The expected red baseline is reproduction evidence, not a failed corrective verification.

After closure, continue the existing PR04 design: fixed environment and offline bootstrap,
attestation/preflight, shared callers, old runner deletion, real Linux probes and 1,140-task
parity. CVE-only blockers hold acceptance but do not block independent implementation;
no audit workaround, accepted candidate manifest, new design or model experiment is allowed.
PR05–11 follow sequentially from their frozen designs. Final old-route/contract deletion,
fourth benchmark and all original quality gates remain mandatory. Save and read back within
15 minutes. Parent uses the existing DCO/non-force UTF-8 API checkpoint helper; source and
work record are saved together before validation. Report functions/findings/barriers,
not checkpoint count. No new validation has run at this record-only save.

### Test-first reproduction checkpoint

### First combined correction, parent review still requires closure

The final batch now also bounds the initial dead-process drain by the existing phase
deadline and adds a pre-START late-exit regression. All source and tests are saved before
one combined verification and Sol review. No test expectations were weakened.

The final corrective batch now carries absolute deadlines through cleanup helpers and
checks the reaped SIGKILL result, with internal no-op-kill and termination-latency tests.
The parent also requested preserving the pre-terminal phase deadline when a dead process
first begins draining; this queued clarification remains part of the same bounded batch.
Save before any further refinement or grouped validation. No corrective test result or
independent closure is claimed yet.

At `3081b86a`, all three reproductions failed for the expected reasons (6 versus 5,
2 versus 1, infrastructure error absent); no host changes existed at that red baseline.
Luna returned shared cleanup state, one cleanup invocation and a termination receipt.
Before running checks, parent review finds that the receipt still means only that
`Popen.kill()` was called: its internal poll may observe natural exit and send no signal.
Also, passing remaining seconds into a helper that establishes a new deadline after
kill can extend the absolute budget by termination latency. These are incomplete closure
of the same two findings, not new scope. Save this first correction before returning the
remaining details to the same owner. The next correction must use actual termination
readback and carry an absolute deadline through helpers, with corresponding regressions.
No corrective test run or independent acceptance is claimed. One corrective review in
this resumed segment has not closed the findings; a second failure triggers the stop rule.

Fixture refinement now drains both EOFs before the success cleanup and arms natural exit
from the second resource sample, after the caller's alive poll but at the cleanup helper's
poll. Tests import their own time module for strict typing. Production remains byte-identical
to the saved defective host; parent will run only these three reproductions after this save.

Luna added three fake-clock/selector, pipe-backed regressions; production is unchanged.
No unit run has occurred yet. Parent read-through identified two fixture corrections
before the intended red baseline: drain stdout EOF so the success-cleanup case reaches
the actual success cleanup, and trigger natural exit after the limit sample/caller poll
rather than earlier in the event loop. These stay with Luna in the test-only scope.
The same save includes Sol-reviewed finite registry-path and physical-interpreter setup
clarifications; they do not alter this host source or relax any boundary/quality gate.

## Resumed host-supervisor segment, 2026-09-13

Current state: stopped under the user's two-failed-correction rule; PR04 is not accepted.
The protocol/worker checkpoint `aa7e2cc9df25795be50559ea5c5d986af020c933`
was recovered in an independent worktree. Root checkout remains clean on `main`.
Control recovery is `02cba161d480f45d3eb955eaad035488bde936c4`; the control branch is
not an implementation base. Draft PR heads 38–42 and design refs match the recovery index.

- Owners: Astra parent/checkpoint/acceptance; Luna implementation; Sol read-only independent review.
- Fixed implementation base: `aa7e2cc9df25795be50559ea5c5d986af020c933`; accepted dependency is PR02c `6038a7828d62247ad98d000bc6e71c706f6d14a4`.
- Working allowance: 2026-09-13T05:58:23Z through 2026-09-13T07:28:23Z, maximum 90 minutes including recovery; no silent extension.
- Next authorized continuation: close the saved teardown-budget and resource-enforcement race findings in `eval_harness/grader_sandbox.py` and `tests/harness/test_bigcodebench_runner.py`. No third corrective round is started in this segment. Root alone edits this record and remote refs.
- Frozen contract SHA-256: `03f3d13954135fa3a1802bbda1146ff2c4305925edaa35a7339fc403dab621c1`; appendix `da2efc8cd3703dd6d65df02f80156e280c8824c4e251712cf62f0faf4463edde`; amendment `f6237fa9264fa2168ac5ac2472c0544ecad00b010aa728e0f5636ec6717c3350`.
- Validation: no new test run. Previous worker evidence applies only to its exact recorded head. New supervisor tests, strict typing, Ruff and independent fixed-commit review are required; real sandbox/native parity and whole-head gates remain open.
- NLTK acceptance remains blocked; closed dependency investigation and rejected patches are not reopened. Candidate environments cannot be selected by production constructors.
- Latest user requirement: remove all tracked `contracts/*.md` from the final implementation head after integrating necessary permanent specification into formal documentation. Preserve history/checkpoints. This takes priority over saved designs.
- Stop conditions: second failed correction for one problem, permission obstacle, or allowance expiry; preserve source and evidence and report the unfinished scope.

### Segment stopped after independent correction review, 2026-09-13T06:33:12Z

Latest source/test head `5678340634362d155a5b98f296b1a75a34c8dc07`, tree
`55941cbeba7255823d4b6a5b64d907e238231871`, passes all 31 unittest methods on CPython
3.13.14, strict mypy of the two changed authored files, and Ruff lint/format. No warnings
remain. Control `reports/m2-host-local-validation.json` records exact commands and source
blobs. This is local partial verification only, not security or slice acceptance.

Sol reviewed fixed host blob `254e90ebe0e77100fd751c938dde1d592c00b40e` at `058a5878`
(unchanged at the tested head). Root confirmed two unresolved correctness defects:

1. Post-exit draining starts a fresh teardown deadline instead of preserving the current
   absolute phase/terminal deadline. Successful cleanup followed by the exception path
   can start another full cleanup wait. The teardown budget can therefore be exceeded.
2. A trusted process can exit between the caller's alive check and the termination helper's
   poll. The helper then sends no kill, but the caller still returns a candidate resource
   outcome. An infrastructure exit can therefore become a zero-scoring limit result.

The same teardown-bound problem remained after the e839a8cb and 058a5878 correction
reviews. Astra therefore applied the user's two-failed-correction stop condition before
the 90-minute cap; no third correction or new implementation is authorized in this segment.
The independent offline-bootstrap batch was stopped before any edits, so it remains
unimplemented. No source changes are left unsaved. Parent preserves the review and control
state next, then reports the partial state. Public preflight/launch, provisioning, shared
caller replacement, old-runner deletion, real Linux sandbox and all-1,140 native parity,
full-head quality gates, PR05–11 and final `contracts/*.md` removal remain unfinished.

### Lifecycle and procfs correction checkpoint

Luna returned the bounded post-exit pipe deadline, cleanup polling before observation,
zombie/no-RSS handling, fail-closed live procfs parsing, exact optional-mount fixtures and
parser/selector-construction failure regressions. The two-file batch is saved before
tests. Prior head `e839a8cba1416e600910c90171a72a15b910a23c` passed 26 unit methods;
strict typing and import sorting were not clean. This is still partial host implementation,
not preflight, real isolation, native parity or PR04 acceptance. Root's read-through also
flags selector file-object narrowing and test module export typing for the same owner to
resolve before the next corrective verification.

## Earlier records

### Consolidated host-supervisor correction checkpoint

The initial `64e9855b` validation had 17/18 unit methods pass, seven strict-mypy
errors and scoped Ruff issues. Sol's fixed-head review returned nine concrete findings,
preserved in control branch `reports/m2-host-review-64e9855b.md`. Luna returned a
consolidated two-file correction and pipe-backed supervisor regressions without running
tests. Root separately recorded the source-verified read-only root/device and real-UID
thread-count clarification. The amended contract SHA-256 is
`79a0441d35cbb3b42f8ae4416ec72971585dea580995b98593d71870ea06fbcf`.

This checkpoint precedes correction validation and review. Root's read-through identifies
two follow-up lifecycle cases to resolve in this same correction cycle: bound draining
after the trusted process has exited while a descendant still holds a pipe, and ensure
ordinary zombie/no-RSS process races do not become observation failures. Cleanup must
still reap the outer process when process-tree observation itself fails. No acceptance,
public launch readiness or hosted security proof is claimed.

### First host-supervisor batch saved before validation

Luna added the explicit read-only bubblewrap command builder, trusted path separation,
UID lock, host process/RSS sampling and bounded selector supervisor in the two-file scope.
Four unit cases cover command policy, forbidden mounts, lock metadata and pre-launch input
size rejection. No tests, strict typing or Ruff checks have run on this batch yet.
Public preflight and launch still deliberately raise; this source cannot establish readiness
or PR04 acceptance. Root inspected the scoped diff and whitespace check before API save.

Next: Sol reviews this fixed source delta, while root runs focused correctness/static checks.
Review must examine successful and failed cleanup, pre-START resource handling, bounded I/O
and error classification as well as the command. Expand regressions with fixes before
implementing attestation/provisioning. Full Linux probes, native parity, caller replacement,
96% whole-head coverage, strict dependency audit and formal CI remain outstanding.

State: exact frozen inputs recovered; code not started.

- Owner: Luna implementation, Sol independent contract/delta review, Astra scope/checkpoint/acceptance.
- Base: PR02c `6038a7828d62247ad98d000bc6e71c706f6d14a4`, tree `4f7fc21be5195611ba7df8feeefe3a5cc962c2cb`, accepted Draft #42.
- Required dependencies: accepted PR01/02a/02b/03/02c stack. PR04 is the only active implementation slice.
- First working allowance: 90 minutes from 2026-09-13T04:30:56.162Z; save at most every 15 minutes and before tests/next independent batch.
- Original plan: control commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.
- Exact source contract and appendix: design commit `deb807e8454eb4fbb3652bb1f335489fa5325bea`, copied unchanged in this checkpoint. Contract blob `db8447d1cf3c9c4b0538fe8723150a6a8aa99834`; appendix blob `4eecd0a6b69378f091e33dc5121b07aa46d0031a`.
- User-approved purpose-first amendment: `7f7a260acf1119620282a540739fa1a4afd8c1ed`; approval recorded in control `f4b85f4592d4df6d6e062360b134dd6104c5fc81`.

## Scope and invariants

Use only the finite contract path list. Implement one shared fail-closed grader supervisor/worker route for evaluator and resource server; preserve native status meaning and distinguish infrastructure failure from score zero. Pinned real Linux isolation and all original quality gates remain required. No compatibility wrapper or direct legacy interpreter route may remain at slice completion.

The original design assumes a clean NLTK lock before preparation. The user's later amendment authorizes independent functional implementation and evidence while keeping the known standard audit failure and PR acceptance pending. Sol is defining only the finite operational clarification for truthful candidate/test manifests and independent CI execution. This does not authorize a false accepted manifest, audit exception, rejected backport, repeated M0 research, or a weaker sandbox.

## Validation and next action

No PR04 code or validation is claimed. Preserve the exact source/lock/data evidence from the saved design, with their original hashes, before implementation needs it. Next save the bounded operational clarification, then hand Luna the first coherent module/test batch. Root remains the sole remote writer and saves each returned delta before verification.

## Fixed inputs recovered

Root copied only the four exact upstream metric/license blobs, the two previously audited bubblewrap build inputs, and the NLTK metadata/reduced-index files from design `deb807e8`. Every copied file is byte- and blob-verified against its durable source. No NLTK data payload, rejected patch, grader dependency install, boundary launch or accepted manifest is included. The upstream CRLF bytes remain unchanged. The authored VENDORING document records source/license provenance.

This is an input-recovery checkpoint, not functional validation. Exact-vendor Ruff/copyright configuration, attribution and hash gates remain part of implementation; do not run an auto-formatting all-file hook against the vendored source before its accepted narrow exclusion is installed. The main locked development environment was recreated successfully with uv 0.11.29, Python 3.13.14 and offline locked sync. Next: save Sol's finite implementation clarification, then begin Luna's bounded code batch.

## Code-start review closed

Sol reviewed the frozen candidate and confirmed no other code-start blocker after the finite amendment recorded in `contracts/pr04-code-start-amendment.md`. Astra accepts the truthful non-acceptance candidate environment/manifest/CI sequencing, authenticated native-signal result union, and exact trusted-mount versus untrusted-root clarification. The final trusted spec field is `manifest_path: Path | None = None`; production constructors cannot select candidate mode. All original security and acceptance gates remain.

The recovered local source/build/data files match all seven frozen SHA-256 values. Root also corrects a transcription error in the VENDORING document's __init__.py Git-blob text; source bytes themselves were and remain exact. Next Luna implements only the three-file pure type/codec/parser batch, with no process launch or native import, then returns it before testing for root checkpoint and Sol review.

## Pure protocol implementation checkpoint

Luna returned the bounded three-file foundation with immutable types, canonical BCBI/BCBO framing, HMAC verification, bounded incremental state parsing and status/signal mapping. It contains no process launch, native import, resource-limit execution or claim of sandbox readiness. Root inspected public types, interfaces and test assertions, and applied scoped Ruff formatting. No tests or strict typing have run on this batch.

Root identified follow-up fixture integration requirements before acceptance: the pure tests must participate in the existing unittest-based coverage driver and run under the frozen Python 3.11 worker interpreter as well as Python 3.13; avoid a new type-ignore for the frozen-field assertion. Independent Sol review of the saved codec delta is next. The finite vendor-hook and legacy fixture scope additions approved by Sol are appended to the code-start amendment; they do not exempt authored code.

## Codec fixture/static correction checkpoint

Saved head `a3ea79b8` passed all 12 pytest cases; strict mypy found two redundant casts and one missing test-list annotation. Luna converted the same cases to unittest/subTest for the existing measured harness and stdlib-only Python 3.11, replaced the frozen-field type-ignore with setattr, corrected those three typing errors and removed the requested unused aliases/re-exports. Root scoped formatting before saving. This corrective head is not yet tested.

Sol independently reviewed `a3ea79b8` and found three concrete source defects: NUL rejection must apply only to identifiers, the incremental output cap must count all received bytes including consumed START frames, and deeply nested JSON RecursionError must normalize to ProtocolError. The remaining framing/HMAC/state/signal/default interfaces match the frozen contract. Next fix these three defects and the remaining unused encode_input/decode_input/parse_bcbo aliases in a bounded saved batch before further verification or process implementation. No sandbox readiness or full PR gate is claimed.

## Independent codec findings corrected

The two-file correction addresses all three Sol findings: code/test NUL bytes round-trip while identifier NULs reject, total received protocol bytes are counted across consumed frames, and recursive JSON failures normalize to ProtocolError. The remaining unused codec aliases are removed. Root inspected the full delta and strengthened the cumulative-bound regression to supply a valid incomplete frame header; the old parser would wait for more body bytes instead of rejecting, so the test cannot pass merely because arbitrary bytes have invalid magic. No new tests have run yet.

Next run this saved head's unittest module under exact Python 3.13.14 and frozen Python 3.11.16, strict mypy and scoped Ruff. Both frozen interpreter executable and license hashes match the contract, and the local interpreter reports the exact 3.11.16/x86_64/SOABI identity. Sol then reviews only this correction delta for closure. No process implementation starts before this foundation closes.

## Codec foundation closed; inner worker saved for review

At head `03791275ade265013e1efb9c1d96c49df34be610`, all 10 unittest methods and their subcases pass on Python 3.13.14 and frozen Python 3.11.16; strict mypy for the three authored files and scoped Ruff pass. Sol independently closed the three codec findings. These are protocol correctness results, not live sandbox security evidence.

The next two-file batch adds worker dumpability/rlimit setup, bounded framed input, CLOEXEC protocol FD handling and standard-FD replacement, forced spawn, native invocation/start/result handling and two unit tests. Root scoped Ruff checks/formatting pass; this worker batch is saved before unit/static validation and independent review. Root has identified a review question about the exact multiprocessing.Process class patched by the native start hook; this checkpoint is not accepted. Host sandbox supervision, provisioning, live boundary/parity coverage and caller replacement remain outstanding. The first M2 allowance still ends at 06:00:56 UTC; no extension or full PR04 acceptance is implied.

## Consolidated inner-worker correction

First validation of saved `febf165642e07c1b79dd482aae2bd3b05e483837` had 11/12 unittest methods pass on each frozen interpreter and seven strict-mypy errors. The failing new test supplied a one-argument callback to the two-argument frame writer. Independent Sol review additionally found the wrong multiprocessing Process class, fixed native memory arguments incompatible with smaller trusted test limits, and lost authentication on oversized input after a complete key. Root independently confirmed the default and spawn-context Process classes have distinct identities.

The consolidated two-file correction targets the exact module-level Process method, preserves bounded input-key availability on overflow, validates trusted whole-MiB limits before native import, and repairs fixture/static typing issues. Regression cases exercise distinct Process classes, production and smaller native arguments, invalid limit rejection, and bounded-reader overflow through authenticated ERROR(0). The narrow already-authorized test-limit interpretation is recorded in the code-start amendment. This checkpoint precedes its validation; no live isolation, whole PR04 acceptance or full migration completion is claimed.

The user requested an immediate report because elapsed time was excessive. Root reported logical slices 01–03/02c accepted, 04 partial, 05–09 designed/unimplemented, and 10–11 outstanding, then limited this segment to the current correction/verification/save with no host-supervisor or further implementation scope. Segment deadline: 2026-09-13T05:41:18.195Z, earlier than the original 90-minute allowance. Save validation/evidence and remaining work, then stop at this boundary.
