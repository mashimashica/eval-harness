<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR-11 fourth-benchmark and final acceptance task contract

Status: early durable design checkpoint; exact fixture paths and final evidence matrix are pending baseline inventory. This is a Luna implementation contract, not implementation or acceptance evidence.  
Date: 2026-09-13  
Sol owner: PR-10/11 design review  
Immutable characterization baseline: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`  
Canonical-plan control commit: `8518f25d107d9043df449a9198fbb41b00ba1c22`  
Canonical-plan SHA-256: `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`  
Astra acceptance-map SHA-256: `ad8870927701889f4f99e9cdda33ce57aa995281d6a9db7a48fb7dd888153710`

## 1. Immutable implementation inputs

PR-11 implementation must start from `<PR10_ACCEPTED_HEAD_SHA>`. Luna substitutes the exact 40-character accepted PR-10 head only after the migration owner supplies it, verifies ancestry through the accepted PR-01 through PR-10 stack, and reads all dependency contracts/changed paths from that commit. No current checkpoint or guessed future SHA fills this placeholder.

The final validation record later substitutes `<FINAL_PR11_HEAD_SHA>` only after source is frozen. Validation from a different or synthetic head is not credited unless its exact tree equality to `<FINAL_PR11_HEAD_SHA>` is recorded.

## 2. Objective and phase boundary

PR-11 adds a fourth small benchmark fixture through the ordinary adapter/evaluator registration seams, exercises it with the accepted common Executor, Intervention, Builder, generation, CandidateBundle, and reevaluation paths, and closes remaining deterministic integration evidence. The fixture has a name unrelated to GDPval, AIME, BigCodeBench, Skill Creator, or ALPS. Its addition may touch its adapter/evaluator/fixture code and explicit registration points; it may not change common runner, Executor, Builder, generation, intervention, CandidateBundle, snapshot, evaluation-job, or record-sink behavior.

The slice runs deterministic local fakes only. Gate-B model/provider/judge work, performance claims, merge, release, and publication remain outside scope.

## 3. Required fourth-benchmark proof

The final fixture must demonstrate all of the following through public contracts rather than a fabricated handoff:

1. acquisition creates one sealed snapshot with separate ExecutionView and EvaluationView bytes and content hashes;
2. a fake executor performs real common generation with an explicit Intervention and produces a strict RunManifest/index/CandidateBundle;
3. the bundle remains valid after external runtime deletion and relocation to a different runtime root;
4. `./eval evaluate` reevaluates the saved bundle through a registered unary evaluator with one named metric and explicit denominator;
5. correct, incorrect, empty/no-deliverable, candidate failure, evaluator invalidity, and systemic failure retain distinct typed outcomes;
6. the ordinary Builder registration creates and seals an Intervention, hands only that artifact to application, and supports an unknown-benchmark experiment without an arm/benchmark branch in common code;
7. a fresh registry instance can register the benchmark/evaluator without monkeypatching orchestration, while the explicit default registration makes public listing and CLI selection truthful.

## 4. Final-head quality and evidence

PR-11 preserves the exact existing quality scope and thresholds. The final acceptance run records exact commands, integer coverage totals, strict typing/lint/format results, locked dependency and CVE-audit scope, copyright/secret results, actual supported-platform grader-boundary proof, fourth-benchmark results, removed-route inventory, Draft PR/check URLs, and zero unresolved mandatory migration items.

All new or changed public CLI examples have deterministic fake-execution coverage. The neutral `tests/harness/test_eval_cli.sh` suite is the only harness suite entrypoint. No test is deleted, skipped, xfailed, narrowed, or converted to a mock assertion merely to make the final head green.

PR-05 evaluation resume remains part of final acceptance: `EvaluationRecordSink.create/resume` binds the exact `EvaluationResumePolicy`; immutable ordered `EvaluationResultRevision` history and `EvaluationJobRecord.current_result` survive interruption; completed and eligible-partial results do not replay; retryable failed/invalid/interrupted/skipped results advance only under the stored policy; evaluator-specific trial events remain in `append_evaluator_event`/`load_evaluator_events`.

## 5. Early completion gate

The next checkpoint freezes the exact fixture ID, source/test/registration paths, CLI commands and expected fake results, unchanged CI path matrix, and final evidence template. Luna starts only from the supplied accepted dependency SHA. Completion requires independent Sol review and required deterministic CI against `<FINAL_PR11_HEAD_SHA>`; a saved checkpoint alone is not acceptance.

