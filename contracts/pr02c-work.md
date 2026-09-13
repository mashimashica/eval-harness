<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR-02c work record

Status: incomplete implementation checkpoint. Validation and acceptance remain open.

- Repository: `mashimashica/eval-harness`
- Implementation owner: Luna (`/root/luna_restore_source`); design/review: Sol (`/root/sol_pr02c_design`); architecture/acceptance: Astra (`/root`).
- Branch: `checkpoint/pr-02c`; root temporarily owns remote writes during persistence recovery. Luna's implementation turn is paused.
- Immutable implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`, tree `354943ebbb8ea81a30523bfdc12baf26771853b5`.
- Dependency heads: PR01 `b0d4229f49c7cc2441efd0f3aa929b58a9096c55`; PR02a `86b03a910799ecf97b33d3dac230c069a44bde65`; PR02b `0b3f41a0edcfffc1b6f4b537bcb2cab2e55e39c4`; PR03 is the base above.
- Original plan: control commit `8518f25d107d9043df449a9198fbb41b00ba1c22`, `eval-harness-neutrality-migration-plan-2026-09-12.md`, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`.
- Contract: `contracts/pr02c-reconstruction.md` in this commit. The production/test path allowlist, fixed APIs, invariants, failure behavior, and gates in that file govern this slice.
- Accepted scope amendment: `contracts/pr02c-input-protection-amendment.md`, SHA-256
  `98c69de050dcbce42bad8db805243402f69633bb896a704e2a4628bdd9eba9c8`. It adds the Cursor and FilesIntervention
  paths and exact `task_inputs` protection/legacy rejection requirements described in that file.
- Control procedure: `checkpoint/migration-control:MIGRATION-WORKFLOW.md` (current control head at initialization: `ff85149636b55c207f7fdd388727db20475a7ab2`).

This checkpoint preserves a newly written, incomplete implementation of the candidate layout, snapshot generation handoff, Cursor task-input protection, FilesIntervention reservation, and initial fixture updates. It also includes the accepted input-protection amendment. It does not recover previously lost unpublished implementation. Original plan bytes and all 5,134 tracked files at the implementation base have been verified. Python 3.13.14 and uv 0.11.29 recreate the locked development environment.

Persistence correction: Luna created local commits through `909b95519aa2434d4c9b1c68ff5ee712267aed36`, but the remote branch still pointed to the initial contract commit. Those local commits were not durable checkpoints and their generic local DCO did not match the required user sign-off. Root paused further edits/tests, inspected the allowed nine-file delta, and is preserving the exact source tree through the required UTF-8 GitHub APIs with the correct DCO. Local commits are not being promoted into remote ancestry. A prior local work-record sentence claiming remote readback was incorrect and is replaced here.

Known remaining work before acceptance:

- Complete the GDPval `task_inputs` wrapper correction, the generation handoff integration tests, and all required fixture migrations, including the new common CLI Cursor coverage and explicit legacy rejection.
- Fix Cursor cleanup failure handling so a late integrity/restore failure clears successful output text and cannot violate the typed failed-result schema. Preserve an already typed primary timeout/interruption/process failure; record cleanup evidence without masking it.
- Review the initial generic intervention fixture change: retain meaningful materialized-file provenance coverage using valid file bytes, hashes, and manifest evidence rather than removing that behavior.
- Sol's source/API/security review is in progress against this incomplete tree; no review acceptance is claimed.

Next action: verify this remote checkpoint and changed bytes, return a fresh checkout of it to Luna, fix the reviewed Cursor/fixture issues in one bounded batch, save/read back that batch, then complete the remaining handoff implementation and tests. No source expansion or long test may precede its required checkpoint. No real model or judge execution, merge, or release is authorized in this phase.

Validation of this checkpoint: design reviewed by Sol and Astra; no source implementation tests run or claimed. Base PR03 exact-head validation remains historical evidence for that unchanged base only. PR02c requires focused tests, independent review, and all unchanged mandatory CI gates on its own saved implementation head.

Promotion: no formal PR yet. A reachable checkpoint is saved work, not a passed test or accepted migration slice.

## Cursor cleanup batch

Base: `4948b2c3f85ca82d94e44734de532c8769d7b04e`. Luna edited only `eval_harness/executors/cursor.py` and `tests/harness/test_cursor_executor.py`, then returned the batch without local commits or tests. Root reviewed the bounded diff and is saving it with this record before validation.

The change clears output text whenever cleanup adds a typed failure, represents a cleanup interruption explicitly, and adds focused regressions for late mutation, restore failure, and primary-failure preservation. Tests have not been run on this batch. It does not yet fix the separately identified setup-write cleanup gap, complete other fixture migration, or close PR02c acceptance.

Next: run the focused Cursor tests on this saved head, fix any concrete failure, then bring policy/prompt preparation inside the cleanup lifetime and address the remaining reviewed runner/fixture requirements in bounded saved batches.

## Cursor preparation cleanup batch

Base `d8bfa21554bfbe4adb9f592ddfaece65d78fff0c` was read back and checked out cleanly. `python -m unittest tests.harness.test_cursor_executor` passed all 10 tests on that exact head. An isolated clean checkout of the same head ran `test_generic_runner`: 33 tests, 4 failures and 1 error, all recorded as remaining input-path/descriptor/duplicate-ID/unavailable-revision fixture migration work; no full-suite or acceptance pass is claimed.

This batch changes only Cursor and its focused tests: policy/prompt preparation now lies inside the restoration lifetime, and a failed digest immediately after isolating inputs restores the original namespace before propagating. Focused tests assert original bytes, a real directory, and zero subprocess calls after setup failure/interruption. These new tests have not yet run. Root saves this returned batch before validation; source review, typing and all remaining handoff work stay open.

## Bound snapshot and executor provenance batch

Base `ec2b0862335ce9eb9da8ad7f36839c804b0b3663` was read back and checked out cleanly. All 13 Cursor tests and scoped Ruff passed. Scoped strict mypy found two argument-type errors in the new `Path.write_text` test callback; this batch supplies its explicit signature. No full-suite, coverage, or PR02c acceptance is claimed.

Luna returned a bounded three-file edit without tests, commits, or remote writes. Runner acquisition now checks the returned snapshot's exact type and recomputed digest against its sealed binding before publishing output/runtime roots. Known executor version/auth provenance and requested reasoning must match exactly before sealing. Legacy intervention failures retain `evaluation=None`, and the legacy row helper uses concrete types. Generic runner fixtures now use `task_inputs`, correct content hashes, declared capabilities and revision availability; a real FilesIntervention test preserves file provenance coverage. Focused regressions reject incoherent snapshot metadata and missing/mismatched execution provenance without producing candidates or invoking evaluation.

Root inspected the diff and saves it together with this record before validation. Next commands on the saved head: Cursor and generic runner unit tests, scoped Ruff, and strict mypy of the changed modules/tests. Then complete the minimal GDPval wrapper change, generation handoff integration tests, and remaining fixture migrations. All full acceptance gates remain required.

## Typed sealing and canonical fingerprint fixture batch

Exact clean head `66c01eefbce311592a65e9bba7d294318be3139b` ran 48 Cursor/generic runner tests: one failure and one error, both old metadata/fingerprint expectations. Scoped strict mypy found four errors (optional sealed digest, two nested JSON objects, fixture revision annotation); Ruff lint passed and runner formatting needed correction. A separate clean checkout of that same head ran all 526 harness unit tests, with one failure and 33 errors. Remaining diagnostics identify the already scoped Cursor namespace/helper migrations and missing capabilities/revision availability in Builder, reasoning, and reliability fakes. No full-suite pass is claimed.

This two-source-file batch explicitly validates the sealed digest before indexing, uses typed fixture JSON/revision fields, updates the canonical availability key, and verifies the semantic fingerprint from the persisted RunManifest snapshot references while retaining the separate legacy prompt hash assertion. Root caught and corrected a draft assertion that had confused those two task digests before saving. Scoped Ruff formatting is included. No tests have run on this batch.

Next: validate these focused tests/types on the saved head, then complete the GDPval wrapper, new generation handoff tests, and the enumerated fixture ports. Root remains the sole remote checkpoint writer; Luna returns each bounded edit before testing or further scope.

## GDPval execution input wrapper batch

Exact clean head `621be5d6b43ef65b0f4c75d3c414aca0bb05a7f9` passed all 48 Cursor/generic runner tests, scoped strict mypy of three changed modules/tests, and Ruff lint/format. These are focused results, not full acceptance.

Luna returned a three-file GDPval wrapper/test edit before tests or commits. The execution prompt now lists and protects only `task_inputs`. A real sealed snapshot is reopened through VerifiedSnapshotBinding, its execution files are materialized from the bound view, and the wrapper is checked for nested input paths and canonical-task preservation. The legacy direct materialization test remains separate for its staged consumer; no downloader or legacy fallback was added. Root reviewed and saves this batch before its scoped snapshot/boundary tests, typing and Ruff.

Next: validate this saved wrapper batch, add the required generation handoff integration file, and port the already enumerated typed-executor/Cursor fixtures. Full tests, coverage, audit, independent review and formal PR CI remain open.

## Real generation handoff test batch

Exact clean head `6e7bc240de3a3ad0faaf05c4e2b4bde787314c4b` passed all 31 snapshot/BenchmarkBoundary tests, strict mypy of its three changed source/test files, and Ruff lint/format.

Luna returned one new test file, `tests/harness/test_generation_handoff.py`, before tests or commits. Root read the complete file. It uses an unknown benchmark, typed fake roles, and real snapshot acquisition, binding, candidate sealing/indexing and authoritative loaders. It covers indexed candidates visible before evaluation, runtime deletion and out relocation, execution/evaluation file separation, single acquisition/materialization, typed network provenance, semantic fingerprint exclusions and changes, label-independent identities, and validation-before-publication/binding reopen. Instrumented methods wrap their actual implementations; the tests do not fabricate successful handoff records.

This is an unvalidated test checkpoint. Next run this file and scoped strict typing/Ruff on the saved head; correct concrete fixture/API errors before adding the contract's systemic-failure, seal/index/path and tamper cases. Old typed-executor and Cursor fixtures plus the full required gates remain open.

## Handoff test static-contract correction

Exact clean head `9a9f144537f4dc276e18c029666be229547e371c` passed all eight real generation handoff tests. Strict mypy found five test-only issues: references to non-reexported imported symbols and an untyped heterogeneous semantic-configuration override tuple. Ruff found import ordering and one unused import. This returned one-file batch imports instrumentation symbols from their defining APIs, declares an exact total-false TypedDict for configuration changes, and fixes the imports/format. No test or production behavior changes. Root saves it before rerunning the focused static and integration checks.

Sol is independently reviewing the saved production source while Luna completes tests. The next bounded test batch covers systemic failures, failed sealing/indexing and corrupt/missing-byte rejection. Existing fixture ports and all full acceptance gates remain required.

## Failure durability and sealing rejection tests

Exact clean head `f972a82558609255f84723b9d4c060503eef894a` passed all eight generation handoff integrations, strict mypy of the test module, and scoped Ruff lint/format. Luna returned the next one-file test batch without tests or commits. Root reviewed the whole diff and corrected its tuple annotation, empty-parent expectation after a rejected seal, and portable fsync observer before saving.

The batch verifies AUTH/QUOTA/PROTOCOL/INTEGRITY run failures are sealed and indexed before abort without evaluation or a second execution; undeclared channels, wrong result roots, symlink artifacts, and destination collisions reject without indexing; an index append failure preserves the earlier authoritative prefix and leaves a sealed but unindexed bundle undispatched; and actual nonempty index fsync completes before each evaluator call. New tests have not yet run.

Independent production review is saved at `checkpoint/design-pr05:01f781cbeaff00aee3fb0bea3597dee3bd58e2df`, `contracts/pr02c-review-9a9f1445.md`. It requires four corrections before acceptance: unambiguous strict Cursor tree sealing/restoration, integrity error classification, log-persistence failure preservation, and provenance capture before run-created paths. Next validate this saved test batch, implement those reviewed source corrections and regressions, then complete tamper tests, remaining fixture migrations, and full gates.

## Independent production review correction batch

Exact clean head `31307d471c3e240ad2f3a52aa7a5514607e8b175` passed all ten generation handoff tests and Ruff. Strict mypy found only two test imports of a non-reexported `os` symbol. This four-file batch uses direct `os.fsync` instrumentation, moves the single benchmark preparation and repository provenance capture before staging/output/runtime paths, frames Cursor task-input tree entries and bytes, rejects invalid protected roots and restores after isolation interruption, consolidates input verification in finalization, and preserves typed failures across independent log write errors. New regressions cover digest framing, empty directories, invalid trees/restoration, symlink-creation interruption, primary/log failure combinations and provenance ordering.

Root reviewed the complete returned diff before saving. The batch is not yet validated. Follow-up hardening remains for file/directory identity and timestamp checks throughout tree traversal, nonblocking/no-follow opens on the supported Linux platform, and explicit regression coverage for post-execution unreadable/missing/replaced inputs. These are kept visible rather than treating the initial fix as acceptance.

Next validate focused Cursor/handoff tests and strict typing/Ruff on this saved head, then complete the remaining reviewed regressions, tamper cases and fixture ports. No full-suite/coverage/CI acceptance is claimed. Separately, the unchanged main dependency inputs were audited in clean `66c01eefbce311592a65e9bba7d294318be3139b`: 153 packages, zero findings and skips; exact audit evidence is saved on the control branch at `7a9cfafafdb13afcc23fe727418b50ec6b0dbd3e`. The distinct PR04 grader NLTK audit remains unresolved.

## Observed input mutation and interruption regression checkpoint

Exact clean head `2cd4b02547bda84d230b46a0fbb0c20404089f66` passed all 63 Cursor/generation-handoff/generic-runner tests, strict mypy of its four changed source/test files, and scoped Ruff lint/format. Root paused the next two-file editing task at a persistence boundary and inspected the complete current diff before saving it. No tests on this new batch are claimed.

The Cursor tree reader now uses explicit Linux no-follow/nonblocking file opens, context-managed traversal, stable type/identity/size/timestamp observations before/after reads, and static integrity errors. It preserves explicit process-level exit behavior and typed primary failures during per-log interruption. Real execute regressions cover deletion of an empty protected directory, protected/internal symlink changes, the framed-content mutation, valid real-directory restoration, unreadable final input checks, observed directory/file changes, special entries, and both log-write interruption paths across primary failure classes. This is observed content-integrity checking, not a claim of a complete OS sandbox or atomic immutability against concurrent processes.

Next run focused Cursor/handoff tests, strict typing and Ruff on this saved head; resume only for concrete failures or still-missing requirements. Sol is separately freezing two necessary staged-consumer amendments: the common run CLI runtime-root option and preservation of the existing selected-task Benchmark adapter's source/revision availability, snapshot hooks and fresh canonical execution task. Setting fixture revisions to unavailable to hide that adapter regression is rejected. These amendments must be saved before editing those additional paths. Tamper tests, fixture ports, full coverage/pre-commit/CI and formal PR acceptance remain open.

## Accepted CLI and selected-task consumer amendment

Exact clean head `32169815cd455f3c5929ca643ebc69fe00260969` passes all 35 Cursor/handoff tests, strict mypy of the two changed files, and Ruff lint/format. The saved source includes every observed-input and log-interruption correction; independent source review remains required.

The complete finite migration map is copied byte-for-byte from Sol design commit `b46537358ae0355be4d926a0d606a095a197273a`, SHA-256 `37e848eafdd8bfc8ca5d2ce6612eb0cc325b641384f4c7648aedb9185f84de47`. Astra accepts its narrow additions: optional run CLI runtime-root plumbing, and repair of the existing selected-task Benchmark adapter's typed metadata/snapshot hook delegation and canonical execution view. Original fixture revisions and available-revision assertions are preserved; execution wrapping receives a fresh minimal task without evaluation/materialization data.

Next, complete the map's independent non-Cursor consumer/fixture port in a separate checkout of this saved head while the primary Cursor/handoff owner completes tamper and CLI/Cursor tests. Both batches belong to the same PR02c slice and have disjoint source/test paths. Root remains the sole remote writer, saves each returned batch before validation, and verifies unchanged baseline blobs before combining reviewed deltas. No future implementation slice is started; no source handoff may depend only on scratch.

## Durable handoff tamper batch

Base `3f37a1b7e7e6e74900d475dd018a25931acca04e` contains the independently reviewed source at `32169815`. Luna returned a one-file test batch without tests, commits, or remote writes. The tests create a fresh real run for each snapshot, candidate and index corruption, remove runtime, then require strict durable readers to reject modified execution/evaluation bytes, missing or changed artifact bytes, changed manifest text/digest, and malformed/changed index links. Executor and evaluator counts remain unchanged. Existing real sealing/indexing paths are used.

Root reviewed the bounded diff and saves it before focused execution and strict static checks. These new tests are not yet claimed passing. The disjoint selected-consumer and Cursor fixture branches remain separate; the primary owner's next batch is the accepted common CLI runtime-root plumbing and integration, including the legacy Cursor rejection. Full-suite, coverage and exact-head CI remain mandatory.

## CLI runtime root and legacy Cursor rejection batch

Exact saved head `549339ab6f36a788a5eb7fa83851af9d7546fcf6` passes all 13 handoff tests, strict mypy and scoped Ruff. Independent review requests two narrow test refinements for the following handoff batch: remove one snapshot CAS blob, and use a syntactically valid missing indexed bundle path. No new production finding was identified.

Luna returned the exact three-file CLI batch before tests or commits: run --runtime-root parses Path or None and forwards it unchanged; parser/plumbing tests cover both values; the old GDPval Cursor shell route requires the exact legacy-input rejection before any -p call, with no result and unchanged input bytes. Existing no-limit/authentication negatives remain. Root inspected the diff, added help exit-code and whitespace-normalized help-text checks to respect argparse line wrapping, and scoped formatting. The common real Cursor CLI integration and its migrated success/protection assertions follow in the next saved batch before acceptance. No new tests or full gates have run on this batch.

## Reviewed selected consumer integration

The disjoint selected-consumer branch is saved/read back at `77f33247e6436f92d186a1e89ef4cf538ff1ab9e`, parent `3a077a4ad3bb68a27e3acd89b185bc04158f9afd`. The parent passes all 48 relevant tests and scoped Ruff. Its two test-only object-to-dict typing errors are fixed by direct verified-data equality; the resulting exact head passes the affected real snapshot test, strict mypy of all five files, and Ruff. Sol independently reviewed the parent source and test delta against the accepted b465 contract and reported no concrete findings. The two assertion-only fixes preserve those reviewed semantics.

Root verified that every one of the five source/test blobs still equals its common base `3f37a1b7` on primary `e8571865`, then promotes only those reviewed blobs and their side work record. The primary CLI batch at `e8571865` passed all 14 CLI registry tests, the Cursor shell rejection integration, strict mypy of two files and scoped Ruff. No all-suite, coverage or final CI pass is claimed; the primary next batch is the common real Cursor CLI integration and the two reviewed tamper refinements.

## Cursor fixture integration and in-progress CLI test checkpoint

The Cursor fixture side branch is saved/read back at `9bcdee9ab8c5b8732bcb2a044ae998303154d0f5`; the durable control record `65ba5260` records all 43 tests, strict mypy and Ruff passing and an independent review without findings. Root verified both changed test blobs on primary `b2a4ea43` remain identical to the common base `3f37a1b7`, then integrates only those two reviewed tests and the side work record.

The current handoff test file also contains the two reviewed tamper refinements (missing evaluation-view snapshot blob and a valid-but-missing indexed bundle path), plus initial imports and a fixture class for the common Cursor CLI test. This is explicitly an incomplete implementation checkpoint; its unused new imports are not claimed lint-clean. No new test pass is claimed for this partial file or the combined head. Root preserves these exact current bytes before the next bounded Luna handoff. Next: complete only the real Cursor CLI integration in this test file, save/read back, run focused checks, then whole-suite coverage/static/pre-commit/CI and independent final slice review.

## Common Cursor CLI completion batch

Luna returned the bounded real Cursor CLI integration in the existing handoff test file. It uses a fake executable with the real executor, common CLI, snapshot publisher, candidate writer and strict readers; it checks protected task inputs, scrubbed provider environment, typed authentication/version/runtime evidence, nested output bytes, and durable loading after runtime removal and output relocation. Root inspected the entire delta and applied scoped Ruff formatting before this checkpoint. New tests have not yet run.

Sol independently reviewed immutable head `2aa8c28b` and found no additional concrete source or contract findings. The previously closed review issues remain closed. Next validate this saved test batch and send its immutable delta for independent review, then run the required whole-head gates. The approved purpose-first amendment permits independent migration work while PR04's known NLTK advisory remains an explicit acceptance blocker; this batch does not change dependencies or reopen that investigation.

## First whole-head gate corrections

Saved head `a248c407` passed all 14 handoff tests, all-file pre-commit, 45 dependency compatibility tests, five inventory tests, and a strict audit of all 153 exported runtime/development dependencies with zero findings or skips. Whole harness execution ran 553 tests and found one stale execution-view namespace expectation. Strict mypy checked 111 files and found one untyped default-capturing fixture lambda. No full coverage pass is claimed because that harness failure stopped the coverage driver before shell integrations.

Sol's immutable completion-diff review identified two test gaps: the real CLI evaluator must check durable indexing during evaluation, and the fake command must reject leaked provider variables during version/status preflight as well as execution. The current test-only delta addresses both, replaces the fixture lambda with an explicitly typed closure, and changes only the two execution-view namespace literals in `test_benchmark_evaluator_edge_coverage.py`. Astra accepts this additional test path as a finite scope amendment supported by the reproduced failure; Sol independently confirmed that the direct `_reference_listing` fixture is execution-only. All raw dataset fields, legacy materialization, and judge presentation paths remain as required by their existing staged meanings. No production or public-contract expansion is made.

Root inspected the complete three-file correction diff before saving. Next validate the saved head, obtain closure review, and rerun the required whole-head harness/static gates. These are the first corrective attempts for the identified issues.
