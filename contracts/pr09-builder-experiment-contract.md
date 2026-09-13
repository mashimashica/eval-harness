<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR-09 Builder experiment and N/S/A consumer contract

Status: final design contract; implementation and real-model validation are not performed.  
Date: 2026-09-13  
Immutable source baseline: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`  
Canonical-plan control commit: `8518f25d107d9043df449a9198fbb41b00ba1c22`  
Canonical-plan SHA-256: `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`

This contract specifies the PR-09 consumer of the common snapshot, CandidateBundle, generation, and evaluation contracts. It makes no model-quality or ALPS-effectiveness claim. No model call is part of this design work.

## 1. Scope and ownership

PR-09 owns the experiment profile and controller for the three N/S/A arms, Builder invocation and sealed-intervention handoff, comparison-group sealing, experiment status/coverage, and the neutral Agent Skill workspace namespace. It consumes the common BenchmarkSnapshot and CandidateBundle contracts from PR-01/02, executor and capability contracts from PR-03/07, and the evaluation planner/result sink/BattleRecord contracts from PR-05/06. Protocol-specific evaluation, including AA-v2 stage or Elo meaning, remains with the selected evaluator/profile.

PR-09 does not add benchmark-name or `alps` branches to a common runner. ALPS is a pinned, allowlisted Builder input in the A arm. Builder is a stage that produces an Intervention; it is not a fifth comparison axis.

## 2. Baseline evidence and exact gap map

| Asset | Baseline SHA-256 | Observed responsibility |
|---|---|---|
| `eval_harness/experiments/base.py` | `2dfa932110bc1c76ff5a7a32cbfdd7e6d10d753fb53fd4948f904de0c8468e69` | v1 input, arm, profile, global run-config, and coarse summary records |
| `eval_harness/experiments/profile.py` | `559496d57357e33becf12bbc32e6ca3eaa66685f20cfb502f025e49cae245012` | strict profile JSON and allowlisted source/revision/bundle loading |
| `eval_harness/experiments/runner.py` | `c23c3360701937f58edb88c65a6000c291dd7a8dd3956fb4ba3e1424952e1f4d` | randomized task/arm schedule, Builder→application loop, mutable metadata |
| `eval_harness/builders/base.py` | `0c3937f7fababaf465cf34d826913e69807bfb77e34909f6c88e11230cf17ae1` | typed Builder input/request/result and build failure phases |
| `eval_harness/builders/inputs.py` | `d55dd27035a2caf7e55da4f7cbd64fbe5d1654045786a73e82c3eab179e882a8` | allowlisted input sealing and neutral-number staging under the legacy input root |
| `eval_harness/builders/prompt.py` | `ca6ce11e25007cbf12e4e9c6521b1d9922147a770c0bd2615e5a091a7ba37ce1` | Builder prompt and exact staged-input target regex |
| `eval_harness/builders/artifact.py` | `38e743ed79ae10928725db8ef72cc315a4e2102f38a1daf08224a9dea4c0b199` | generated Agent Skill validation and sealed handoff copy |
| `eval_harness/builders/executor_skill.py` | `2dd6b8feafd6e6e9a77570996ba3ad444cf416f0f26ec58dcc9c2ef5823af399` | one-executor Skill Builder, failure mapping, input revalidation, seal call |
| `eval_harness/executors/base.py` | `026d46343508ce03dab6823675d3529ebd5442358e73acfcef6e857841965eb0` | neutral `ExecutionRequest` roots/environment and the abstract executor boundary; no role/root-deny capability |
| `eval_harness/capabilities.py` | `aedcd7a7156f70556f9371be160561e7ae96659525d70348ad674e0d735d795b` | input/output capabilities only; no filesystem-read or environment-isolation claim |
| `eval_harness/executors/codex.py` | `6e27349ffa2b35029276bf29aae66875c51a4d4188d8ad8621aea521cd2f4642` | local Codex `workspace-write` launch and subscription-environment filtering |
| `eval_harness/executors/claude_code.py` | `345434b2c68d3c75a821505809795a3af1e9586b8796b0c5cdda44b8ab9b5f8a` | Claude tool/sandbox settings without a proved experiment role-root boundary |
| `eval_harness/executors/cursor.py` | `033e9181d53180ea0e8363063489c98cf88e852911505b82c00844442fe7b048` | Cursor workspace policy and protected-input setup without a generic experiment role proof |
| `eval_harness/interventions/agent_skill.py` | `4fb737c4e570114fcb9cf233f59fbe716a5656690ae5c6d78862c4edc3f6cb22` | Agent Skill schema validation and legacy workspace materialization |
| `eval_harness/interventions/files.py` | `396385c45cd64bac2287cfd4e5098b50f29888fcaed2c08c06c4fd171185a01e` | reserved application workspace roots |
| `config/experiments/alps-skill-creation.json` | `44d9ac6a362888b018750e2c48ca62d1c8cfe1c9aeab7ed4d6052aae0c7fe870` | current two-arm Skill Creator / Skill Creator+ALPS input relation |

Direct baseline evidence is indexed at [experiment contracts lines 189-381](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/experiments/base.py#L189-L381), [profile loading lines 140-380](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/experiments/profile.py#L140-L380), [schedule and metadata lines 418-850](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/experiments/runner.py#L418-L850), [the execution loop lines 867-1139](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/experiments/runner.py#L867-L1139), [Builder input staging lines 308-729](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/builders/inputs.py#L308-L729), [Builder prompt lines 22-102](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/builders/prompt.py#L22-L102), [Builder execution lines 104-330](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/builders/executor_skill.py#L104-L330), [the neutral execution request lines 34-64](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/executors/base.py#L34-L64), [Codex launch lines 201-276](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/executors/codex.py#L201-L276), [Claude launch lines 207-272](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/executors/claude_code.py#L207-L272), [Cursor workspace policy lines 274-386](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/executors/cursor.py#L274-L386), [generated-skill sealing lines 285-387](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/builders/artifact.py#L285-L387), and [Agent Skill loading/application lines 188-488](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/eval_harness/interventions/agent_skill.py#L188-L488).

The baseline procedure is exact:

1. Profile schema v1 requires at least one external input and one arm. An arm contains only `arm_id` and an ordered `builder_inputs` list. It cannot represent N's no-Builder transition, an arm role, a comparison group, or an evaluation strategy.
2. The shipped profile has two S/A-like arms: `skill-creator-only` consumes the five-file Skill Creator closure; `skill-creator-plus-alps` consumes that same input first and a pinned 14-file ALPS closure second. It has no N arm. The ALPS revision is `cf31ca93a1b5379e2ddbd430f9ea416192fb6797` and its expected bundle SHA-256 is `1feb183fb6e01f7b48469c3669968df0741d93ddde428cfaad6e05350c2f28c4`.
3. The strict loader rejects duplicate/unknown/missing JSON keys, malformed/non-finite values, unsafe/colliding allowlist paths, bad source bindings, selected worktree changes relative to a declared Git revision, and expected bundle hash mismatch. It loads all declared input bundles once before the first Builder call; this useful fail-closed behavior is retained.
4. `stage_builder_inputs` snapshots only allowlisted bytes, assigns inputs in arm-declared order, and revalidates the sources after copying. It currently materializes `reference_files/builder-inputs/input-NNN`, while the accepted PR-02c contract makes `task_inputs` the sole common protected input namespace and makes Cursor reject legacy `reference_files` before execution.
5. The Builder prompt receives the canonical task text and neutral numbered targets, not input IDs, source roots/revisions, or the arm ID. The current regex and explanatory text nevertheless hard-code the legacy `reference_files/builder-inputs` target.
6. `ExecutorSkillBuilder` uses one injected Builder executor and one shared run configuration, verifies the staged inputs after execution, accepts exactly one generated skill directory, and seals it before application. Its typed statuses distinguish preflight/input/execution/artifact-validation/handoff phases. It currently copies the whole ambient process environment, minus three legacy GDPval keys, into the Builder execution request. Path-disjoint runtime/source/artifact validation prevents accidental aliasing but does not prevent a local model tool from reading a disjoint parent or sibling. The base executor capabilities describe input/output channels only; local Codex `workspace-write`, Claude settings, and Cursor's protected-input mechanism are not by themselves an experiment role-root proof. The outer experiment runner stops at the first non-completed build rather than retaining an explicit missing-arm denominator and continuing eligible independent work.
7. The skill loader validates frontmatter/name, normalized paths, collision/symlink/file shape, exact file hashes, bundle hash, and manifest hash. The sealer copies only the validated skill to a disjoint immutable artifact root. Both the loader/materializer and sealer currently require `.gdpval/interventions/<skill>/SKILL.md`.
8. One `ExperimentRunConfig` already holds the Builder, application executor, and evaluator settings for every arm. This is a useful common-settings basis, but the baseline task hash covers the old TaskSpec path rather than one shared sealed BenchmarkSnapshot and its explicit Builder/Execution/Evaluation views.
9. The baseline makes the Cartesian task×arm schedule, shuffles it with `random.Random(order_seed)`, and gives each occurrence a random path-safe schedule ID. Paths are thereby label-blind. It neither records planned comparison slots nor separates a stable occurrence identity from random run navigation.
10. Before the first Builder call, it validates only one-candidate evaluator plans. For each schedule item it then builds, applies the skill, and calls `run_benchmark` immediately; the selected evaluator can run before other arms for the task exist. There is no exact `{N,S,A}` CandidateBundle group seal or multi-candidate MatchPlanner call.
11. Application receives the sealed generated InterventionBundle rather than the Builder workspace/input roots, and outer metadata retains Builder provenance. This useful handoff boundary is preserved and strengthened by using the common CandidateBundle index instead of nested runtime/result path discovery.
12. `experiment-metadata.json` is atomically replaced and keeps prior completed entry payloads on an ordinary stop, but it is one mutable document, has no append-only event/attempt history, has no safe resume, and has only `completed|failed|interrupted` summary states. Later schedule entries remain null; the file exposes neither exact planned/completed coverage nor a typed incomplete comparison-group result.

## 3. Frozen N/S/A semantics

The profile declares exactly these arm roles:

| Role | Builder | Builder inputs | Application intervention |
|---|---|---|---|
| `N` | never invoked | none | exact `none` intervention |
| `S` | the profile's one pinned Skill Creator Builder specification | the sealed `skill-creator` input closure | the newly generated, validated, sealed Agent Skill |
| `A` | byte-for-byte the same Builder specification used by S | the same `skill-creator` closure followed by the one pinned ALPS allowlist bundle | the newly generated, validated, sealed Agent Skill |

S and A differ in Builder-visible semantic input only by the addition of the ALPS bundle. Builder executor, model, requested reasoning effort, timeout, network policy, prompt/template revision, output schema, validation rules, task BuilderView, Skill Creator bytes, input order before the added ALPS bundle, and retry policy are identical. N has no synthetic empty build, no Builder run ID, and no generated skill.

Every arm binds the same BenchmarkSnapshot digest, ordered task/repeat manifest, canonical task bytes, ExecutionView, application executor/model/reasoning/timeout/network specification, evaluator/evaluation configuration, trial policy, and comparison-plan policy. Arm and condition labels remain outer provenance. They are absent from Builder task content except where the profile explicitly makes an input available, absent from application TaskSpec/prompt/workspace/environment, and absent from judge/evaluator projection.

PR-09 replaces the shipped file's strict schema v1 with `schema_version=2`; it never interprets a v1 empty input list as N. The named profile ID is `alps-skill-creation-nsa-v2`, a new PR-09 design identity rather than an observed baseline value, so results cannot be confused with the existing two-arm `alps-skill-creation-v1` profile. Its exact stored arm order and role relation are:

| `arm_id` | `arm_role` | `intervention_source` | ordered `builder_inputs` |
|---|---|---|---|
| `none` | `N` | `none` | `[]` |
| `skill-creator-only` | `S` | `builder` | `["skill-creator"]` |
| `skill-creator-plus-alps` | `A` | `builder` | `["skill-creator", "alps-work-design"]` |

Schema v2 adds `arm_role` (`N|S|A`) and `intervention_source` (`none|builder`) to each arm and adds top-level `treatment_additions` plus `evaluation`. N must have an empty input tuple. S and A must use `builder`; S must be an exact prefix of A, and A's suffix must equal `treatment_additions`, which is exactly `["alps-work-design"]` for this profile. `evaluation` contains the registered evaluator ID/revision, its complete resolved semantic config, and the typed strategy object. These fields are strict: unknown, missing, duplicate, or mismatched values fail profile loading. Runtime credentials/endpoints remain typed runtime provenance and cannot alter the semantic evaluator config or vary by arm. These profile names are data and never common-runner branches.

All declared Builder inputs are loaded and sealed once at experiment preflight. Both S and A bind the same in-memory/serialized Skill Creator manifest, bundle digest, ordered file paths, and raw file SHA-256 values. When staged into their isolated workspaces, those bytes occupy the identical neutral `input-001` subtree. A alone has `input-002`, whose bytes equal the one sealed ALPS manifest. Any other S/A request/config/prompt/environment difference fails group preflight before a Builder or application model call.

Evaluation strategy is explicit profile data and must match the resolved evaluator cardinality before any model work:

| Strategy | Required evaluator cardinality | Jobs after exact group seal |
|---|---|---|
| `per-candidate` | exactly one | one independent job for each of N, S, A, all using one evaluator/config digest |
| `pairwise-explicit` | exactly two | the exact ordered logical pairs stored in the profile; PR-05 receives one exactly-two job per pair |

The named GDPval N/S/A migration profile pins the exact strategy object `{"kind":"pairwise-explicit","pairs":[["N","S"],["N","A"],["S","A"]]}`. This list fixes both match order and each pair's logical candidate-reference order; the evaluator's own deterministic position/trial policy expands each pair, so PR-09 does not invent a second swap or panel mechanism. These three match slots and the three candidate slots are fixed planned denominators for every task/repeat. A unary/native profile instead evaluates all three candidates independently after the same three-candidate group seal and retains that evaluator's named metric meaning. The common experiment controller branches only on the typed strategy/cardinality contract, never on GDPval, ALPS, a metric name, or an evaluator implementation. It never falls back from a requested pairwise strategy to unary evaluation.

## 4. Planning and phase barriers

The controller resolves and hashes the complete experiment profile before invoking a Builder, application executor, or evaluator. It precomputes a deterministic schedule from the selected task/repeat set and order seed, but execution order never changes semantic identities or denominators.

The resolved experiment binds these canonical, content-hashed objects:

| Object | Required semantic payload |
|---|---|
| resolved profile | profile source/content digest; exact N/S/A role graph and input relation; evaluation strategy/pairs; all component revisions |
| task/repeat plan | BenchmarkSnapshot digest; ordered SnapshotReferences; task/canonical-prompt and Builder/Execution/Evaluation-view digests; explicit repeat indices |
| external inputs | every input manifest/bundle/file digest and revision status; exact S/A ordered binding; the ALPS expected digest when declared |
| common application spec | application executor/version/config, requested model/reasoning, timeout/network/capabilities, exact environment-name allowlist, execution-request template revision |
| Builder spec | Builder/executor/version/config, requested model/reasoning, timeout/network/capabilities, exact environment-name allowlist, prompt/artifact-validator revisions |
| role protection | exact Builder/application policy revisions, access/network/web flags, environment-name allowlists, executor/config evidence, and successful preflight evidence; absolute root sets remain audit evidence |
| evaluator spec | evaluator ID/type/version/revision/config, cardinality, selected strategy, opaque evaluator plan and digest, trial policy where applicable |
| experiment plan | order seed; all task×role application occurrences; all three-candidate group occurrences; candidate slots; match slots and planned denominators |

Each object has a schema/version and SHA-256 over canonical JSON with only its own digest field omitted. Use the accepted PR-01/02 canonical serializer. Stable semantic hashes exclude timestamps, absolute roots, random navigation IDs, attempt counts, and raw runtime history. Those values remain linked audit provenance.

`generation_occurrence_id` is the stable opaque PR-05 experiment-plan identity over resolved profile, snapshot/task/repeat, and arm role. It is passed unchanged into `CandidateGenerationRequest`; PR-05 keeps it outer-only and excludes it from candidate content, model input, and runtime path identity. The random `schedule_id` remains a navigation/path ID and cannot substitute for it. `comparison_group_occurrence_id` is stable over the shared task/repeat plus the ordered planned roles. Before candidate generation, each strategy also declares stable match-slot identities. After a complete group seals, each slot identity becomes the PR-05 `EvaluationJob.match_occurrence_id`. Candidate content hashes and remaining `EvaluationJob` values are bound then; an unresolved slot still remains in the planned denominator.

For each task/repeat, the intended comparison group is the exact set `{N,S,A}`. The controller executes these barriers:

1. validate the snapshot, BuilderView/ExecutionView/EvaluationView, all external Builder inputs, Builder/application/evaluator capabilities, exact role-scoped environments, disjoint role/output roots, both execution-protection policies and no-model preflights, and the full task/arm plan;
2. generate and validate the S and A intervention artifacts while recording N as Builder-not-applicable;
3. apply `none` for N and each sealed Agent Skill for S/A in isolated application workspaces, then seal one CandidateBundle per arm;
4. verify exact CandidateBundle set equality and every linked content hash for the task/repeat, and atomically mark the comparison group sealed;
5. only then ask the PR-05 planner to create `EvaluationJob` values for that group and dispatch them through the one selected evaluation path; every job uses the accepted `match_occurrence_id`, `evaluation_input_sha256`, `evaluation_job_id`, ordered `candidate_id`/`bundle_sha256` references, one SnapshotReference and `evaluation_view_sha256`, and the common evaluator identity/config plus opaque `evaluator_plan`/`evaluator_plan_sha256`;
6. reduce typed results using the evaluator/profile's named metrics and the explicit planned denominators.

No CandidateBundle from a task/repeat is evaluated while another planned arm in that group is still building, applying, running, unsealed, missing, corrupted, or in an unresolved terminal state. A later task's build may be scheduled independently only if durability and resource policy permit; it cannot make an incomplete earlier group eligible for evaluation.

Generation and evaluation are separate phases at the group boundary. PR-09 imports the frozen common seam from `eval_harness.generation_runner`: `ApplicationSpec`, `CandidateGenerationRequest`, `GenerationPlan`, opaque `BoundGenerationPlan`, and `GeneratedCandidate`; and `prepare_generation_plan`, `generate_candidate`, and `run_generation_plan`. The one `ApplicationSpec` has exactly `executor_id`, `requested_model`, `reasoning_effort_requested`, `timeout_seconds`, `network_access_enabled`, and `environment_allowlist`. Each candidate request has exactly one `generation_occurrence_id`, `SnapshotReference`, and explicit `Intervention`: the existing `NoneIntervention` for N or that occurrence's sealed Agent Skill for S/A. The calls are `prepare_generation_plan(plan, *, snapshot_binding, executor, run_root, environment, runtime_root=None)`, `generate_candidate(bound_plan, generation_occurrence_id)`, and `run_generation_plan(bound_plan)`.

`environment_allowlist` is an ordered tuple of exact environment names in the application semantic specification. The separately supplied `environment` mapping must have exactly that key set, is reused unchanged for every N/S/A application request, and is rejected if it contains an arm/profile label or an undeclared key. Values are operational, `repr`-excluded, and absent from every serialization and digest. The Builder specification carries its own exact role allowlist and mapping under the role-policy contract in section 5; S and A share both. Neither path may derive its mapping from ambient process state.

The build phase first records every planned N/S/A occurrence and attempts every scheduled S/A intervention build. It then creates exactly one experiment-level `GenerationPlan`. `ordered_tasks` is the unique SnapshotReference order from the experiment plan; repeated per-arm work appears only in `candidates`, in the already resolved global generation order. That candidate tuple contains N for every task/repeat and each S/A occurrence whose intervention sealed successfully. A task-impact failed S/A build remains an explicit missing outer-plan occurrence and has no fabricated `CandidateGenerationRequest`; it does not suppress an otherwise ready N or sibling-arm candidate. A run-impact build failure stops before generation-plan preparation.

PR-09 calls `prepare_generation_plan` once with that plan, the already acquired `VerifiedSnapshotBinding`, common executor, and disjoint run/runtime roots. The opaque bound plan proves all supplied occurrences/references, application/executor capability, interventions, paths, deterministic candidate identities, and the already-published `run_root/snapshot` before an application executor call, and establishes one RunManifest/index/writer for the experiment. Normal execution calls `run_generation_plan`; exact-occurrence recovery may call `generate_candidate`. Each `GeneratedCandidate` returns the same `generation_occurrence_id`, a `RunResultRow`, and sealed `CandidateBundle`. After generation, PR-09 seals and evaluates only exact complete N/S/A groups while retaining every incomplete group's original denominator. This API accepts no evaluator and dispatches none. PR-09 must not call the staged whole-run `run_benchmark` separately for each task/arm, reacquire the benchmark/snapshot, create per-group common run roots/writers, or invoke an immediate evaluator bridge.

## 5. Sealed handoff and information boundary

Builder receives only its explicit BuilderView, the selected arm's ordered sealed input bundles, and its execution envelope. It receives no EvaluationView, rubric, answer, tests, anchor candidates, judge configuration/output, candidate from another arm, prior Builder conversation/session, or prior application output.

S and A Builder requests have equal task ID/canonical task bytes, BuilderView digest, Builder/executor/model/reasoning/timeout/network/config, prompt/template and output-schema revisions, and role-scoped environment. After removing the expected extra `input-002` target and ALPS manifest from A and excluding occurrence/runtime/audit fields, their semantic and model-visible request payloads must be byte-equal. The controller retains input IDs, source revisions, roots, and arm roles in outer integrity/provenance records. The Builder adapter must omit `arm_id`, `arm_role`, profile/input/source names, source roots, output labels, evaluator metadata, and comparison outcomes from the model-visible TaskSpec, prompt, executor tool input, environment, and workspace paths. Auth uses only the selected executor's typed role mechanism; `dict(os.environ)` is forbidden as the Builder execution environment.

Builder completion is accepted only after the generated Agent Skill passes the shared artifact validator and is copied into an immutable InterventionBundle whose manifest binds normalized relative paths, file sizes and SHA-256 values, bundle digest, manifest digest, source/revision status, application method/target, Builder request digest, and execution-evidence digest. After sealing, application reads only that bundle plus its ordinary TaskSpec/ExecutionView. It cannot read Builder runtime, source input roots, experiment metadata, another arm, or evaluation storage.

The application CandidateBundle binds the common snapshot/task/repeat identity, canonical and effective prompt evidence, selected Intervention manifest/application digests, executor request/result, answer/artifact manifest, and terminal status. Builder provenance and arm identity remain in the outer experiment join and are not copied into the candidate's judge-visible projection.

The comparison-group seal is a controller-owned immutable manifest containing its occurrence ID, resolved-profile/task-plan digests, one SnapshotReference/evaluation-view digest, the ordered roles N/S/A, and for each role the `generation_occurrence_id`, `candidate_id`, and `bundle_sha256`. It also binds the evaluation strategy, planned match slots, and common evaluator-config digest. Its `comparison_group_sha256` is computed only after all three strict CandidateBundle loads and exact snapshot/task checks succeed. Resolved bundle locations, runtime paths, Builder records, arm display labels, and timestamps are excluded from this semantic manifest and remain outer audit links.

Evaluation reads only verified sealed CandidateBundles and the selected task's EvaluationView through PR-05. It must not discover candidates or task material through runtime paths. Moving a sealed bundle between disjoint runtime roots does not change its content digest.

### 5.1 Role-protection preflight and concrete enforcement

Path separation and manifest checks establish integrity; experiment eligibility additionally requires a model/tool read boundary. PR-09 consumes these exact PR-05 primitives from `eval_harness.execution_policy`: `WorkspaceAccess` with `READ_ONLY="read-only"` and `READ_WRITE="read-write"`; `RootDenyRolePolicy(policy_revision, workspace_access, network_access_enabled, web_search_enabled, environment_allowlist)`; `RolePolicyRequest(policy, workspace, protected_roots, runtime_read_paths, environment)`; `RolePolicyPreflightResult(ok, policy_revision, details)`; and `build_role_environment`, `build_codex_role_overrides`, and `probe_codex_role_policy`. The common constructors reject noncanonical roots, allowed/protected overlap, an environment key-set mismatch, and inconsistent network/web flags. The Codex probe uses the production command and policy, reads a random sentinel inside its allowed probe workspace, and proves denial of a separately generated sentinel below a protected root without a model request.

PR-09 adds this exact controller seam in `eval_harness.experiments.execution_policy`:

```python
class ExperimentExecutionRole(StrEnum):
    BUILDER = "builder"
    APPLICATION = "application"

@dataclass(frozen=True, slots=True)
class ExperimentExecutionPolicy:
    role: ExperimentExecutionRole
    root_policy: RootDenyRolePolicy
    protected_roots: tuple[Path, ...]
    runtime_read_paths: tuple[Path, ...]

class BoundExperimentExecutor(Executor): ...  # token-constructed wrapper

def bind_experiment_executor(
    executor: Executor,
    *,
    policy: ExperimentExecutionPolicy,
    environment: Mapping[str, str],
    probe_workspace: Path,
) -> BoundExperimentExecutor: ...
```

`root_policy.workspace_access` is exactly `WorkspaceAccess.READ_WRITE`. `bind_experiment_executor` canonicalizes and validates the complete root set, requires the supplied environment keys to equal `root_policy.environment_allowlist`, runs the concrete executor's no-model protection preflight, and returns only on an `ok=True` `RolePolicyPreflightResult` with the same policy revision. The opaque wrapper exposes the ordinary `Executor` interface required by `ExecutorSkillBuilder` and `prepare_generation_plan`. For each actual `ExecutionRequest`, it constructs a fresh `RolePolicyRequest` using that request's workspace, revalidates its assigned `workspace`, `deliverables_dir`, `executor_dir`, network flag, root set, and environment key set, then executes with the exact preflighted protection. The probe workspace is fresh, role-private, contains synthetic sentinels only, and is never a task/model workspace. Policy revision, flags, allowlist, executor/config evidence, root-set audit digest, and preflight result enter the experiment journal; environment values and absolute roots stay outside semantic result hashes.

The controller creates the planned empty role/probe/output roots and resolves the following root sets before the first Builder call. Each tuple is complete, canonical, pairwise disjoint where its role requires, and closed under parent/symlink/case/Unicode collision checks; later unplanned sibling roots are occupied-output conflicts rather than implicit additions:

| Role | Model/tool writable | Model/tool readable | Protected from that role |
|---|---|---|---|
| Builder | only the current Builder `ExecutionRequest.workspace`, including its assigned `deliverables_dir`; Stirrup instead exposes its one executor-private output stage as described below | that same workspace, containing only the selected BuilderView and staged `task_inputs/builder-inputs`; minimal registered runtime paths needed to start tools | repository/control tree; authoritative snapshot and non-Builder views; original external-input/source checkouts; sealed Intervention/CandidateBundle stores; experiment/evaluation journals; every application and other Builder occurrence root; all credential/config roots and every unselected runtime path |
| Application | only the current application `ExecutionRequest.workspace`, including its assigned `deliverables_dir`; Stirrup uses its one executor-private output stage | that same workspace, containing only the materialized ExecutionView and selected sealed Intervention; minimal registered runtime paths needed to start tools | repository/control tree; authoritative snapshot and Builder/Evaluation views; external-input/source checkouts; every Builder runtime and sealed source-artifact root; experiment/evaluation and candidate-sealing/index roots; every other application occurrence root; all credential/config roots and every unselected runtime path |

`executor_dir` is host-side execution evidence and is absent from model/tool readable roots. The controller stages allowed bytes into the role workspace before execution, so original snapshot, Skill Creator, ALPS, and generated-skill source roots never need a read exemption. Host launch/auth code may access its one approved executable/config/credential source; model-invoked tools cannot. All other experiment and parent roots remain protected. Builder and application use distinct `BoundExperimentExecutor` instances, probe workspaces, execution roots, policies, and evidence. S and A reuse the exact same Builder instance/policy/evidence; N/S/A reuse the exact same application instance/policy/evidence.

Environment delivery is exact and role-scoped:

| Route | Builder request mapping | Application request mapping | Model/sandbox visibility |
|---|---|---|---|
| protected local Codex | keys equal the Builder policy's registered literal allowlist; S and A values are the same mapping | keys equal `ApplicationSpec.environment_allowlist`; N/S/A values are the same mapping | `build_role_environment` supplies only those names; API/provider/cloud-key aliases and ambient extras are rejected; vendor subscription filtering remains an additional removal step |
| contained Stirrup with bearer auth | exactly `{"BUILDER_MODEL_API_KEY": <secret>}` and Builder config names only `BUILDER_MODEL_API_KEY` | exactly `{"MODEL_API_KEY": <secret>}` and application config names only `MODEL_API_KEY` | the host transport resolves its one role-approved reference; `ExecutionRequest.environment` is never passed to the Apptainer sandbox |
| contained Stirrup with explicit `auth.mode="none"` | `{}` | `{}` | empty |

For local Codex, the role-bound adapter uses the exact output of `build_codex_role_overrides` for execution after `probe_codex_role_policy` succeeds; reconstructing ordinary `workspace-write` arguments is forbidden. A request with a changed workspace, protected root, runtime-read path, environment, network/web flag, command, or policy revision fails before the model call. Local Claude and Cursor are experiment-ineligible in PR-09 because neither has the equivalent declared root-deny probe; Cursor's PR-02c protection of `task_inputs` remains an input-integrity mechanism and is not promoted to a general read-isolation claim. There is no fallback to an unprotected local executor.

For Stirrup, the role-bound adapter uses existing `ExecutionRequest.workspace`, `deliverables_dir`, `executor_dir`, and `environment`. `StirrupExecutor` copies the allowed workspace into a fresh executor-private `input-stage`; `StirrupApptainerProvider` launches with containment, no home, clean environment, one explicit read-only input bind, and one writable output bind; only declared validated output is copied back. Builder and application require distinct executor instances and configuration evidence, distinct role roots, and the role-specific credential reference above. The Builder config cannot name the application reference. This is the concrete Stirrup boundary; it does not imply the same OS guarantee for another `Executor` implementation.

## 6. Neutral workspace namespaces

Builder creation inputs use exactly `task_inputs/builder-inputs/input-NNN`, with contiguous ASCII numbers `001..999`, and their manifest evidence paths use the same prefix. The Builder prompt target regex, target constructor/parser, namespace collision checks, copy/rollback/read-only logic, verification walker, fixtures, and tests change in one slice. `input-001` is Skill Creator for both S and A; `input-002` is ALPS only for A. No Builder target uses `reference_files`, no alternate path is probed, and Cursor receives the accepted PR-02c `task_inputs` tree through its one protected-input mechanism. These bytes remain a controller-selected BuilderView even though they share the neutral protected root name with ordinary executor inputs; the manifests and workspaces remain role-separated.

New Agent Skill interventions use `.eval-harness/interventions/agent-skills/<skill-name>/SKILL.md` and place the skill's remaining files below the same directory. The exact application target is part of the sealed Intervention manifest. The loader's target prefix/parser, generated-skill validator/sealer, application prompt, materializer destination, collision cleanup, fixtures, and tests change together. Old `.gdpval/interventions/...` manifests are invalid; there is no alias, dual reader, relocation, or fallback.

PR-09 owns the coordinated change in the Agent Skill materializer and the generated-skill artifact validator/sealer, including collision/path/symlink checks and exact target validation. It also owns updating every generic runner/Builder/Intervention test that asserts the old namespace. Benchmark-specific adapters may retain their own names internally only when the data format requires them; the final common Builder/Intervention/application path may not.

After this slice, `FilesIntervention` reserves the case-folded top-level set `{deliverables, task_inputs, reference_files, .eval-harness, .cursor, .claude, .agents}`. PR-09 replaces the obsolete `.gdpval` reservation with `.eval-harness` because it owns the new intervention namespace and no accepted generic consumer retains the old path. It retains `reference_files` solely as the staged legacy guard required by PR-02c; PR-10 removes that one reservation with the old runner. Tests cover exact, case, and Unicode-collision spellings and prove rejection before any workspace/model write.

No executable Builder, Intervention, experiment, common generation, or common evaluation producer, reader, materializer, prompt, fixture, or compatibility route may emit or accept `.gdpval` or `GDPVAL_TASK.md`. Focused repository scans report every literal hit rather than requiring an artificial zero count. The reviewed negative-test allowlist is exact: `tests/harness/test_builder_inputs.py` may contain `reference_files/builder-inputs` only in explicit rejection assertions; `tests/harness/test_builder_artifact.py` and `tests/harness/test_agent_skill_intervention.py` may contain `.gdpval/interventions` only in explicit rejected-manifest/target assertions; and `tests/harness/test_quality_input_intervention_boundaries.py` may contain those retired strings only as scanner needles plus the exact expected-location list. Any hit outside that list, or any listed hit used by an accepted producer/reader/path fallback, fails the slice. Benchmark adapters may still use their registered benchmark IDs and PR-10 owns unrelated legacy entrypoint/judge path deletion.

## 7. Result, denominator, and failure contract

The experiment result declares, per task/repeat, all three planned arm occurrences, candidate state/digest when available, the sealed comparison-group state/digest, every planned match/evaluation slot and any bound evaluation-job ID, completed result IDs/digests, and typed failure evidence. Counts derive from the plan, never from whichever result files happen to exist.

At minimum it reports:

- planned tasks, task/repeats, arms, candidates, comparison groups, jobs, and trials;
- completed-valid counts and coverage for each of those levels;
- per-arm availability and named evaluator outcomes/metrics;
- complete-group count and coverage, with explicit identities for every incomplete group;
- stable semantic result digest separated from timestamps, runtime paths, attempts, and audit-history digest.

A missing N, S, or A candidate remains in the planned denominator and makes that task/repeat group incomplete. It is never silently removed, imputed, replaced by another run, or treated as a loss/tie/zero unless the chosen evaluator's versioned metric explicitly defines that outcome for the recorded failure class. Pairwise plans cannot be emitted for an incomplete three-arm group. A partial experiment result may preserve completed builds, applications, candidates, and evaluation records, but it carries `partial` aggregate status and cannot publish a complete N/S/A comparison metric.

Let `G` be the declared task/repeat group count. The planned candidate denominator is always `3G`. The named pairwise profile has exactly `3G` planned match slots, one each for N/S, N/A, and S/A per group; if the evaluator plan declares `K` trials per match, its planned trial denominator is `3GK`. A unary profile has `3G` planned evaluation slots and the evaluator's declared per-job trial denominator. These values are fixed before generation. A missing candidate leaves the affected slots unresolved with no fabricated `evaluation_job_id`; it does not reduce a denominator.

Coverage is recorded at these separate levels:

| Field | Numerator / denominator |
|---|---|
| candidate coverage | evaluator-eligible, integrity-verified sealed CandidateBundles / `3G` planned candidate slots |
| per-role candidate coverage | eligible sealed bundles for that role / `G` |
| group coverage | exact `{N,S,A}` groups sealed for evaluation / `G` |
| match/job coverage | completed eligible EvaluationResults / all planned match/evaluation slots |
| trial coverage | completed valid evaluator-trial results (PR-06 BattleRecords for pairwise) / all planned trials |

The group state distinguishes `planned`, `building`, `candidate_incomplete`, `sealed`, `evaluating`, `completed`, and `failed`; interruption is a retained occurrence/attempt state and makes the enclosing group incomplete until a verified retry completes. A group receives `sealed` only when all three slot records and CandidateBundles exist, strict bundle/snapshot/task/view/config checks pass, and the selected evaluator accepts their statuses/cardinality. A sealed typed failed application CandidateBundle remains durable evidence but is not silently considered evaluation-eligible. A normal no-deliverable or empty result is eligible only when the selected evaluator's revision explicitly accepts and scores that state.

The experiment terminal status is `completed` only when every planned group and evaluation slot satisfies the profile. `partial` means scheduling ended normally after one or more task-impact arm/group failures and all eligible independent work was durably handled; its coverage and missing identities are mandatory and no complete comparison headline is emitted. `failed` means a run-impact/systemic or integrity failure stopped dispatch, even if a durable prefix exists. `interrupted` means cancellation stopped dispatch. Preflight rejection creates no run and no model call; if a failure occurs after the run journal is bound, that exact terminal evidence is preserved.

An arm occurrence with task-impact invalid/no-artifact failure records a durable typed terminal state, closes that group's missing candidate slot, and permits the remaining scheduled occurrences and other groups to finish. A run-impact authentication, quota, provider protocol, snapshot/candidate integrity, content-mismatch, or isolation failure stops every new Builder/application/evaluation dispatch. Interruption records the running occurrence as interrupted. All cases preserve every completed sealed artifact/result and never truncate or overwrite prior evidence. The common failure `kind`, stable code, impact, and retryability remain intact; the controller does not infer severity from exception text.

Pairwise aggregates report W/L/T and coverage separately for N/S, N/A, and S/A using the planned match denominators. They may also expose an explicitly labeled observed-only table, but it cannot replace the planned-denominator result. Unary/native aggregates retain each evaluator's named metric and denominator for each role plus experiment coverage. The controller neither averages unlike metrics nor constructs Elo for arbitrary pairs or a universal score.

## 8. Durability, interruption, and retry

The authoritative outer experiment record uses the PR-09-owned `eval_harness.experiments.journal.ExperimentRecordSink`. It reuses the common canonical-JSON, exclusive-write, fsync, path-safety, and content-verification primitives, but its Builder/candidate/group schemas do not enter the PR-05 evaluation sink. Each experiment event is an immutable canonical-JSON file published by same-directory temporary write, file flush/fsync, atomic rename, and directory fsync; a replaceable summary/head file is only a cache. No recovery path truncates, rewrites, or deletes an earlier event, Builder artifact, CandidateBundle, common evaluation record, or failure record.

The journal must express at least these semantic events:

| Event | Required binding |
|---|---|
| `experiment_bound` | resolved profile, snapshot/task-repeat, external-input, Builder/application/evaluator spec, strategy, role-policy/preflight evidence, and experiment-plan digests |
| `arm_planned` | `generation_occurrence_id`, group occurrence, task/repeat, role, N no-Builder marker or exact S/A Builder-input manifest set |
| `builder_state` | occurrence/attempt, typed BuildResult/status/phase, execution evidence, sealed Intervention digest when complete |
| `generation_plan_bound` | exact common ApplicationSpec/GenerationPlan/BoundGenerationPlan and RunManifest/index bindings; every ready candidate request plus every missing outer-plan occurrence |
| `candidate_state` | generation attempt/status and strict CandidateBundle ID/path/content digest or typed missing/ineligible reason |
| `group_state` | exact three candidate-slot states; sealed group digest only when eligible; all planned match slots |
| `evaluation_plan_bound` | group digest, strategy, resolved PR-05 job IDs/input digests/evaluator-plan digests, `EvaluationRecordSink` binding, or explicit unresolved slots |
| `evaluation_result_bound` | returned `EvaluationJobRecord` and common result/BattleRecord semantic IDs and digests, typed result status/failure, evidence-history digest |
| `experiment_terminal` | `completed|partial|failed|interrupted`, every planned/completed denominator, missing identities, stable result digest, audit-history digest |

Every event binds its predecessor and its own digest; every linked manifest/evidence object is revalidated on read. Attempt IDs/numbers, timestamps, random schedule/application/run IDs, absolute paths, retry events, and raw executor/judge evidence affect the audit/history digest and never the stable profile/group/result digest. N records Builder as not applicable without manufacturing an attempt.

On restart, the controller first verifies the unique event chain, the exact experiment plan, and every referenced snapshot/input/intervention/candidate/evaluation byte. It reuses only a completed occurrence with the same stable occurrence ID and all semantic/evidence hashes intact. A persisted running attempt becomes an immutable interrupted attempt before a new attempt starts. If a retry produces different generated skill or candidate bytes, the new content digest is the result actually used; no claim of byte-identical model output is made. Given the same final sealed candidates and normalized evaluation results, interrupted and uninterrupted fake runs must have equal group/experiment semantic digests while their attempt/audit histories may differ.

An orphan temporary event is retained or quarantined as evidence and is not part of the chain. A missing sequence, fork, malformed event, hash mismatch, unexpected artifact, changed input, or changed configuration fails closed with a new run-impact record. Changed inputs require a new experiment run/output root; the controller never splices old candidates into a different profile or comparison plan.

## 9. Required deterministic tests

1. A three-arm fake fixture proves N makes zero Builder calls and applies the exact `NoneIntervention`; S and A invoke the same Builder specification. Their semantic/model-visible request projections are byte-equal after removing only A's `input-002` target/ALPS manifest; occurrence, runtime-root, and audit fields are outer-only in both projections. Skill Creator source/manifest/raw file hashes and staged `input-001` bytes are exactly equal.
2. All three applications bind one shared snapshot/task/repeat/application-executor configuration, and every job binds one evaluator configuration. Mutating any common field invalidates the group before a model call rather than creating an unmatched arm. Different random navigation IDs/roots leave semantic hashes equal.
3. Evaluator cardinality and the profile strategy are checked before Builder/application calls. The named pairwise fixture emits exactly N/S, N/A, S/A slots in order. A unary fixture emits exactly N, S, A slots. Pairwise→unary fallback and an undeclared pair both fail.
4. No evaluation call occurs until N, S, and A CandidateBundles for that task/repeat are sealed and reverified and the group seal is durable. A missing/corrupted/ineligible arm produces zero evaluation jobs for that group while planned candidates/groups/matches/trials keep their original denominators.
5. Builder runtime/session/source roots and outer profile/input/arm labels are absent from model-visible TaskSpec, prompt, environment, target paths, application workspace, CandidateBundle evaluation projection, and judge request. Only the sealed generated-skill files cross Builder→application. The A Builder can read its intended ALPS bytes at neutral `input-002`; application cannot. Protected local Codex passes the production no-model allowed-workspace/denied-random-sentinel probe and uses the exact probed overrides; contained Stirrup exposes only its input/output binds and an empty sandbox environment. Claude, Cursor, an unprobed Codex policy, a changed post-probe request, and a Stirrup role/config credential mismatch all fail before a model call.
6. Builder/application/probe/out/runtime/source/protected roots are canonical and satisfy the exact role table in section 5.1. Each role can write its own workspace/output and cannot read a random sentinel under every representative protected-root class. Copying sealed intervention/candidate/group bundles to another runtime root preserves content identity and evaluation behavior. Symlink, path escape, collision, mutation, missing file, undeclared file, source/output overlap, and content-hash mismatch fail closed before the affected application/evaluation.
7. Builder input tests use exactly `task_inputs/builder-inputs/input-NNN`; Cursor's real fake-process fixture proves the directory is protected and restored under PR-02c. Old `reference_files/builder-inputs` is rejected and never probed. The BuilderView and application ExecutionView use separate workspaces/manifests despite the common root name.
8. Agent Skill generation, validation, sealing, application, generic runner, and collision tests use exactly `.eval-harness/interventions/agent-skills/<name>`. Negative tests use explicit retired literals and prove rejection. FilesIntervention reserves `.eval-harness`, retains staged `reference_files`, and rejects case/Unicode collisions before writes. The bounded common-core scan reports every retired-string hit and accepts only the exact scanner/negative-assertion locations listed in section 6; it proves that no executable or compatibility route accepts an old path.
9. Failures before Builder, during S/A build, intervention application, application execution, candidate/group sealing, plan expansion, and evaluation persist distinct typed states and exact planned/completed counts. Task-impact failure continues eligible independent work and finishes `partial`; representative auth/quota/protocol/integrity run-impact failures stop every later dispatch and finish `failed`; interruption finishes `interrupted`.
10. Restart at each event boundary retains every old event/evidence object, retries only incomplete exact occurrences, and revalidates all hashes. With deterministic fakes, interrupted/retried and uninterrupted runs have equal final candidate/group/evaluation semantic sets and result digests but distinct attempt-history digests. Corruption/fork/mismatch fails without deletion.
11. Pairwise W/L/T and coverage remain separate for N/S, N/A, and S/A. Unary AIME/BigCode-style fixtures retain their named metric/denominator per arm plus experiment coverage. The controller does not average unlike metrics, invent Elo for arbitrary pairs, or emit a universal score.
12. A benchmark fixture whose name is unrelated to GDPval/ALPS runs through the same Builder, intervention, application, group sealing, strategy planning, and evaluation interfaces without a common-core code change. Every test uses local fakes and makes zero real model, judge, provider, subscription, or network calls.

## 10. Integration prerequisites and evidence limits

- The PR-05 generation seam's module, types, functions, and fields are frozen exactly as named in section 4. PR-05 evaluation fields are likewise frozen as `match_occurrence_id`, `evaluation_input_sha256`, `evaluation_job_id`, ordered `candidate_id`/`bundle_sha256`, `SnapshotReference`/`evaluation_view_sha256`, and opaque `evaluator_plan`/`evaluator_plan_sha256`. Each `EvaluationJobRequest` receives `eval_harness.evaluation_records.EvaluationRecordSink`, whose methods are exactly `save_plan`, `append_attempt_started`, `append_attempt_terminal`, `append_result`, and `load_job`; PR-09 links the returned `EvaluationJobRecord` and its semantic/history digests. PR-06 BattleRecord identities and semantic digests remain opaque common outputs. PR-09 must not add aliases or reproduce common canonicalization.
- PR-09 owns the separate outer `ExperimentRecordSink` for the events in section 8. It must reuse common file/digest primitives, keep evaluation records in `EvaluationRecordSink`, and never overload either sink with the other's schema.
- PR-09 consumes the exact PR-05 `eval_harness.execution_policy` API and owns the `ExperimentExecutionPolicy` binding in section 5.1. Protected local Codex and contained PR-07 Stirrup are the only accepted PR-09 execution routes. PR-07 must provide the typed Builder/application credential scopes, containment/clean-environment input/output-bind evidence, and an equivalent `RolePolicyPreflightResult`. Claude and Cursor remain preflight-ineligible until a separately accepted implementation can enforce and probe the same declared roots; input protection or path disjointness alone is insufficient.
- The named GDPval profile requires the strict registered PR-06 pairwise evaluator ID/revision and its complete config before implementation can seal the profile. The exact N/S/A strategy, pair order, group barrier, and denominators are already fixed and cannot fall back if that evaluator is unavailable.
- The real Skill Creator source revision/content digest, provider credentials/capabilities, and benchmark snapshot are Gate-B run inputs. This design did not acquire them or execute Builder, application, evaluator, provider, subscription, or network work.

## 11. Implementation boundary

PR-09 owns this exact implementation surface:

| Repository path | PR-09 responsibility |
|---|---|
| `eval_harness/experiments/base.py` | schema-v2 roles, intervention source, treatment relation, typed strategy, group/result/coverage/failure records |
| `eval_harness/experiments/profile.py` | strict v2 parsing and N/S/A/input/evaluation relation validation; reject v1-as-N and unknown values |
| `eval_harness/experiments/runner.py`, new `eval_harness/experiments/execution_policy.py`, and new `eval_harness/experiments/journal.py` | bind distinct Builder/application role policies before model work, build phase, one common GenerationPlan, group barrier, EvaluationJob expansion, PR-09 `ExperimentRecordSink`/resume, planned-denominator reduction |
| `eval_harness/experiments/__init__.py` and `eval_harness/cli.py` | public exports and one profile-driven experiment path with no per-arm config override |
| `config/experiments/alps-skill-creation.json` | replace the two-arm v1 profile with `alps-skill-creation-nsa-v2`, exact N/S/A arms, treatment additions, and profile-selected evaluator/strategy |
| `eval_harness/builders/inputs.py` and `eval_harness/builders/prompt.py` | move every Builder target/parser/manifest/walker to `task_inputs/builder-inputs/input-NNN`; reject the old root |
| `eval_harness/builders/executor_skill.py` | accept the bound role-protected executor plus exact controller-supplied environment and remove whole-ambient-environment forwarding |
| `eval_harness/executors/codex.py` | expose the narrow protected-execution hook that consumes the exact common root-deny overrides/environment; ordinary non-experiment execution remains a separate route |
| `eval_harness/builders/artifact.py` and `eval_harness/interventions/agent_skill.py` | atomically change validator, manifest target, prompt, materializer, and cleanup to `.eval-harness/interventions/agent-skills/<name>` |
| `eval_harness/interventions/files.py` | reserve `task_inputs` and `.eval-harness`, remove `.gdpval`, retain staged `reference_files` until PR-10, and use the same Unicode/case collision rule |
| `tests/harness/test_{experiment_profile,alps_experiment_profile,builder_experiment_runner,experiment_execution_policy,experiment_reliability,experiment_cli}.py` | profile, group/order/config barriers, exact role roots/environment, Codex/Stirrup protection preflight, unsupported-route failure, denominator/failure, journal/resume, and CLI fake coverage |
| `tests/harness/test_{builder_inputs,builder_prompt,executor_skill_builder,builder_artifact,agent_skill_intervention,file_intervention}.py` and the existing Cursor fake-process boundary fixture | exact namespace, protected input, validator/materializer, collision, isolation, and label-leak checks |
| `tests/harness/test_quality_input_intervention_boundaries.py` and `EXPERIMENTS.md` | bounded common-core scan and documentation matching the implemented v2 command/config |

PR-09 consumes `eval_harness.generation_runner`, `eval_harness.execution_policy`, and the PR-05/06 evaluation path without editing or duplicating their identity, canonicalization, writer, planner, result, probe, or BattleRecord implementations. It owns only the experiment-role binding and narrow Codex execution hook listed above; PR-07 owns Stirrup enforcement and role-scoped configuration. Snapshot/CandidateBundle identity changes return to PR-01/02, and evaluator-specific aggregation remains with that evaluator/profile. Implementation is complete only when all section 9 tests pass through the locked local quality gates with zero real model or judge calls.
