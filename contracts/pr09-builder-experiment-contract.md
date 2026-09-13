<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR-09 Builder experiment and N/S/A consumer contract

Status: early design checkpoint; source characterization and shared API spelling alignment remain in progress.  
Date: 2026-09-13  
Immutable source baseline: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`  
Canonical-plan control commit: `8518f25d107d9043df449a9198fbb41b00ba1c22`  
Canonical-plan SHA-256: `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`

This contract specifies the PR-09 consumer of the common snapshot, CandidateBundle, generation, and evaluation contracts. It makes no model-quality or ALPS-effectiveness claim. No model call is part of this design work.

## 1. Scope and ownership

PR-09 owns the experiment profile and controller for the three N/S/A arms, Builder invocation and sealed-intervention handoff, comparison-group sealing, experiment status/coverage, and the neutral Agent Skill workspace namespace. It consumes the common BenchmarkSnapshot and CandidateBundle contracts from PR-01/02, executor and capability contracts from PR-03/07, and the evaluation planner/result sink/BattleRecord contracts from PR-05/06. Protocol-specific evaluation, including AA-v2 stage or Elo meaning, remains with the selected evaluator/profile.

PR-09 does not add benchmark-name or `alps` branches to a common runner. ALPS is a pinned, allowlisted Builder input in the A arm. Builder is a stage that produces an Intervention; it is not a fifth comparison axis.

## 2. Frozen N/S/A semantics

The profile declares exactly these arm roles:

| Role | Builder | Builder inputs | Application intervention |
|---|---|---|---|
| `N` | never invoked | none | exact `none` intervention |
| `S` | the profile's one pinned Skill Creator Builder specification | the sealed `skill-creator` input closure | the newly generated, validated, sealed Agent Skill |
| `A` | byte-for-byte the same Builder specification used by S | the same `skill-creator` closure followed by the one pinned ALPS allowlist bundle | the newly generated, validated, sealed Agent Skill |

S and A differ in Builder-visible semantic input only by the addition of the ALPS bundle. Builder executor, model, requested reasoning effort, timeout, network policy, prompt/template revision, output schema, validation rules, task BuilderView, Skill Creator bytes, input order before the added ALPS bundle, and retry policy are identical. N has no synthetic empty build, no Builder run ID, and no generated skill.

Every arm binds the same BenchmarkSnapshot digest, ordered task/repeat manifest, canonical task bytes, ExecutionView, application executor/model/reasoning/timeout/network specification, evaluator/evaluation configuration, trial policy, and comparison-plan policy. Arm and condition labels remain outer provenance. They are absent from Builder task content except where the profile explicitly makes an input available, absent from application TaskSpec/prompt/workspace/environment, and absent from judge/evaluator projection.

## 3. Planning and phase barriers

The controller resolves and hashes the complete experiment profile before invoking a Builder, application executor, or evaluator. It precomputes a deterministic schedule from the selected task/repeat set and order seed, but execution order never changes semantic identities or denominators.

For each task/repeat, the intended comparison group is the exact set `{N,S,A}`. The controller executes these barriers:

1. validate the snapshot, BuilderView/ExecutionView/EvaluationView, all external Builder inputs, Builder/application/evaluator capabilities, output roots, and full task/arm plan;
2. generate and validate the S and A intervention artifacts while recording N as Builder-not-applicable;
3. apply `none` for N and each sealed Agent Skill for S/A in isolated application workspaces, then seal one CandidateBundle per arm;
4. verify exact CandidateBundle set equality and every linked content hash for the task/repeat, and atomically mark the comparison group sealed;
5. only then ask the PR-05 planner to create evaluation jobs for that group and dispatch them through the one selected evaluation path;
6. reduce typed results using the evaluator/profile's named metrics and the explicit planned denominators.

No CandidateBundle from a task/repeat is evaluated while another planned arm in that group is still building, applying, running, unsealed, missing, corrupted, or in an unresolved terminal state. A later task's build may be scheduled independently only if durability and resource policy permit; it cannot make an incomplete earlier group eligible for evaluation.

## 4. Sealed handoff and information boundary

Builder receives only its explicit BuilderView, the selected arm's ordered sealed input bundles, and its execution envelope. It receives no EvaluationView, rubric, answer, tests, anchor candidates, judge configuration/output, candidate from another arm, prior Builder conversation/session, or prior application output.

Builder completion is accepted only after the generated Agent Skill passes the shared artifact validator and is copied into an immutable InterventionBundle whose manifest binds normalized relative paths, file sizes and SHA-256 values, bundle digest, manifest digest, source/revision status, application method/target, Builder request digest, and execution-evidence digest. After sealing, application reads only that bundle plus its ordinary TaskSpec/ExecutionView. It cannot read Builder runtime, source input roots, experiment metadata, another arm, or evaluation storage.

The application CandidateBundle binds the common snapshot/task/repeat identity, canonical and effective prompt evidence, selected Intervention manifest/application digests, executor request/result, answer/artifact manifest, and terminal status. Builder provenance and arm identity remain in the outer experiment join and are not copied into the candidate's judge-visible projection.

Evaluation reads only verified sealed CandidateBundles and the selected task's EvaluationView through PR-05. It must not discover candidates or task material through runtime paths. Moving a sealed bundle between disjoint runtime roots does not change its content digest.

## 5. Neutral Agent Skill namespace

New Agent Skill interventions use `.eval-harness/interventions/agent-skills/<skill-name>/SKILL.md` and place the skill's remaining files below the same directory. The exact application target is part of the sealed Intervention manifest. No new core source, manifest, prompt, fixture, or test may emit `.gdpval` or `GDPVAL_TASK.md`; there is no compatibility alias or fallback for old workspace paths.

PR-09 owns the coordinated change in the Agent Skill materializer and the generated-skill artifact validator/sealer, including collision/path/symlink checks and exact target validation. It also owns updating every generic runner/Builder/Intervention test that asserts the old namespace. Benchmark-specific adapters may retain their own names internally only when the data format requires them; the final common Builder/Intervention/application path may not.

## 6. Result, denominator, and failure contract

The experiment result declares, per task/repeat, all three planned arm occurrences, candidate state/digest when available, the sealed comparison-group state/digest, planned evaluation job IDs, completed result IDs/digests, and typed failure evidence. Counts derive from the plan, never from whichever result files happen to exist.

At minimum it reports:

- planned tasks, task/repeats, arms, candidates, comparison groups, jobs, and trials;
- completed-valid counts and coverage for each of those levels;
- per-arm availability and named evaluator outcomes/metrics;
- complete-group count and coverage, with explicit identities for every incomplete group;
- stable semantic result digest separated from timestamps, runtime paths, attempts, and audit-history digest.

A missing N, S, or A candidate remains in the planned denominator and makes that task/repeat group incomplete. It is never silently removed, imputed, replaced by another run, or treated as a loss/tie/zero unless the chosen evaluator's versioned metric explicitly defines that outcome for the recorded failure class. Pairwise plans cannot be emitted for an incomplete three-arm group. A partial experiment result may preserve completed builds, applications, candidates, and evaluation records, but it carries `partial` aggregate status and cannot publish a complete N/S/A comparison metric.

Ordinary per-arm build/application invalidity records a durable typed terminal state and permits policy-defined work on independent groups; systemic authentication, quota, protocol/schema, snapshot-integrity, content-mismatch, or isolation failure stops new dispatch. Interruption records the running occurrence as interrupted, preserves every completed sealed artifact/result, and never truncates or overwrites prior evidence. Resume/retry semantics must reuse only exact verified occurrences and will be aligned to the accepted common journal APIs; current baseline experiment code has no safe resume merge.

## 7. Required deterministic tests

1. A three-arm fake fixture proves N never invokes Builder and applies `none`; S and A invoke the same Builder specification; the Builder request diff is exactly one added ALPS input in A.
2. All three applications bind the same snapshot/task/repeat/application executor configuration, and all evaluation jobs bind the same evaluator configuration. Mutating any common field invalidates the entire group rather than creating an unmatched arm.
3. No evaluation call occurs until N, S, and A CandidateBundles for that task/repeat are sealed and reverified. A missing or corrupted arm produces zero evaluation jobs for that group and remains in every planned denominator.
4. Builder runtime/session/input roots and outer arm labels are absent from application TaskSpec, prompt, workspace, environment, CandidateBundle evaluation projection, and judge request. Only sealed generated-skill files cross the Builder-to-application boundary.
5. Out and runtime roots are disjoint. Copying sealed bundles to another runtime root preserves content identity and evaluation behavior; symlink, path escape, collision, mutation, missing file, and undeclared file fail closed before application/evaluation.
6. Agent Skill generation, validation, sealing, application, and generic-runner tests use the neutral namespace. A repository scan over the final common core finds no `.gdpval` or `GDPVAL_TASK.md` reference.
7. Failures before Builder, during S/A build, during intervention application, during application execution, while sealing a candidate/group, and during evaluation persist distinct typed states and exact planned/completed counts. Systemic failure stops later dispatch; interruption leaves durable resumable evidence.
8. Named evaluator metrics and their own denominators pass through unchanged. The experiment controller does not average unlike metrics, invent Elo for arbitrary pairs, or emit a universal score.
9. A benchmark fixture whose name is unrelated to GDPval/ALPS runs through the same Builder, intervention, application, sealing, and evaluation interfaces without a common-core code change.

## 8. Pending source/API alignment

- The PR-05 generation/evaluation planner and result-sink Python names are pending. This does not reopen the semantic barriers, content identities, exact group membership, or denominator rules above.
- The current source runner supports only Builder-produced arms and evaluates each arm immediately after its build/application; exact line-level characterization and replacement map will be completed in the next revision.
- The current pinned profile has S/A-like arms but no N arm. The final profile schema needs an explicit arm role and `none` intervention without constructing a Builder request.
- The current Agent Skill materializer/sealer uses `.gdpval/interventions/...`; every producer, validator, consumer, and test must change together to the neutral namespace above.
- The durable experiment event/journal representation will reuse accepted common hashing and failure primitives. Field spelling remains pending; prior bytes and semantic status requirements do not.

## 9. Implementation boundary

Expected PR-09 edits are confined to experiment profile/contracts/controller/CLI wiring, the N/S/A profile, coordinated Agent Skill materializer and generated-artifact validation paths, deterministic fixtures/tests, and focused documentation. Snapshot/CandidateBundle identity changes return to PR-01/02; generic executor changes return to PR-03/07; common evaluation-job/result/BattleRecord behavior returns to PR-05/06; evaluator-specific aggregation remains with that evaluator/profile.

