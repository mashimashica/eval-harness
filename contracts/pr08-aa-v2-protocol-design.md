<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR-08 AA-v2 protocol characterization and design contract

Status: final design contract; implementation and real-model/real-anchor validation are not performed.  
Date: 2026-09-13  
Immutable source baseline: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`  
Canonical-plan control commit: `8518f25d107d9043df449a9198fbb41b00ba1c22`  
Canonical-plan SHA-256: `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`

This contract specifies PR-08. It does not claim an official Artificial Analysis implementation or a reproduced score. Its evidence is static source characterization plus deterministic calls to the baseline's pure planning and Elo functions. No model or judge was called.

## 1. Scope and ownership

PR-08 owns the AA-v2 reproduction profile, exact anchor and fixed-Elo binding, the stage planner, the protocol journal, and the protocol-specific aggregate. It consumes the common BenchmarkSnapshot and CandidateBundle contracts from PR-01/02, the common evaluation runner from PR-05, the reusable GDPval blind-pairwise/panel/BattleRecord mechanism from PR-06, and the Stirrup generation adapter from PR-07.

PR-08 must not implement a second pairwise evaluator, presentation layer, judge client, verdict parser, panel sampler, or generic BattleRecord store. PR-06 must let the profile supply the exact per-trial judge and position plan and must expose content-addressed completed BattleRecords. AA-specific stage, anchor, fixed-Elo, and headline fields stay in PR-08's plan and aggregate records.

## 2. Baseline evidence

| Asset | Baseline SHA-256 | Observed responsibility |
|---|---|---|
| `config/gdpval-aa-v2-references.tsv` | `a04835451d016b2d63e301ffad6fa6b8c05d5f167ebcca76577cb2a572651596` | Nine anchor IDs and fixed Elo values |
| `resources_servers/gdpval/multistage_elo.py` | `8f6e7b0c8f3e7f249dcedd62cc71c3c5a9f03f47d4d2e0f23fb5eb68faad3f27` | Pure task sampling, anchor selection/assignment, vote pooling, anchored MLE |
| `resources_servers/gdpval/multistage_orchestrator.py` | `92fc83c0b7e66ade6bd9f9f4c7aae95d8f100370ce7bfb4f6e0d78c4e12b7030` | Stage execution, generation reuse, weak legacy journal/resume |
| `resources_servers/gdpval/comparison.py` | `62fb5b3abe7ff27d85325b833c4d62cea03c42aff96d44c06e2cf7035e1e6a4b` | Pairwise positions, permissive verdict parser, tally, anchored MLE |
| `resources_servers/gdpval/judge_panel.py` | `8b5355c3226826c4272b58dda560204bd249c80a56b1985a16f88b43992a076e` | Weighted deterministic panel sampling and AV routing |
| `resources_servers/gdpval/app.py` | `f4f84f4de434a5f815ca60f23081d2de13ef4b7f13988714cc92ee8f536c9e1b` | Anchor repeat discovery, failure policy, per-reference reduction, headline selection |
| `resources_servers/gdpval/preconvert.py` | `9a25d1a735b15037cfc455a425ac4e341923309f67edd842dc5abc70c2a98a49` | Legacy sibling-PDF derivation |
| `responses_api_agents/stirrup_agent/task_distribution.py` | `1bd966e0603d1a494708358a9159888caa9b8ec6700213c5a34ad6f0344443d7` | Ordered proportional-without-replacement task sampling |
| `benchmarks/gdpval/config.yaml` | `69e056dbd9dc335dc533e52b29b1068d40a38c918b86030b3d8c37e88286cb8d` | Four trials, one generation repeat, three-member panel |
| `nemotron_recipes/lightning-3.5/instruct/gym/gdpval/gdpval.sh` | `9f49bb10c2e8ed9dfacca9664d96ef6d2b00c1fbbe9a0252083d20f7c256935c` | Legacy AA reference discovery, two stages, judge seed 42 |
| `gdpval` | `8772e2f0c9c0d2584181d6a2ad6b06fca858644eff1bfef058e04dad152347f2` | Legacy profile entry and override rejection |
| `scripts/gdpval_preflight.sh` | `34a07793b2d9bb79be3d6ebda480c3e7b775701cc30004613fefa85470a7f9b1` | Legacy environment/path checks |
| `scripts/gdpval_run_metadata.py` | `dee17d49137811dd08c19a67d499af0925c217fa17826dc1dfb619c57e724c01` | Legacy run/config fingerprints |

Direct baseline evidence is indexed at [`gdpval` lines 204-223](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/gdpval#L204-L223), [the recipe lines 73-166](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/nemotron_recipes/lightning-3.5/instruct/gym/gdpval/gdpval.sh#L73-L166), [task sampling lines 257-308](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/responses_api_agents/stirrup_agent/task_distribution.py#L257-L308), [pure stage logic lines 85-282](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/resources_servers/gdpval/multistage_elo.py#L85-L282), [stage orchestration lines 376-548](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/resources_servers/gdpval/multistage_orchestrator.py#L376-L548), [legacy resume lines 635-930](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/resources_servers/gdpval/multistage_orchestrator.py#L635-L930), [pairwise parsing/trials/Elo lines 394-635](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/resources_servers/gdpval/comparison.py#L394-L635), [comparison reduction lines 477-908](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/resources_servers/gdpval/app.py#L477-L908), and [panel sampling/AV routing lines 114-205](https://github.com/mashimashica/eval-harness/blob/d5ce0c10162cad788a17cb90f34b8f60574e7f75/resources_servers/gdpval/judge_panel.py#L114-L205).

## 3. Exact legacy procedure mapping

1. `./gdpval aa-v2 --refs DIR` requires the Stirrup executor, forbids a local judge executor and condition overrides, selects comparison mode, selects the `aa-v2` panel, and defaults to the pinned TSV manifest.
2. The recipe reads the TSV but checks only whether each top-level `<refs>/<anchor_id>` directory exists. Missing anchors are silently omitted. Zero found is fatal; one found runs an unstaged comparison; two or more found selects two stages and sets the second-stage reference count to `min(found, 4)`. This behavior is forbidden for the new formal profile.
3. With all anchors present, stage 0 samples 45 tasks and includes all nine anchors. Stage 1 omits `num_tasks`, meaning the full prepared distribution (documented as 220 tasks), and selects four anchors. `nested_tasks=false`, so stage samples are independent.
4. The distribution is grouped by occupation. Each task draw first chooses a live group using its saved percentage, then a task within the group, without replacement. Counts are capped at available tasks. The shell does not set a multistage seed, so fresh legacy task/assignment plans are not reproducible unless separately configured or replayed from the journal.
5. Stage 0 uses every available anchor sorted by ID. Later stages sort anchors by `(abs(fixed_elo - previous_stage_elo), anchor_id)`, take `num_models`, and return the selected IDs sorted.
6. Each selected task is assigned one included anchor uniformly. Assignment seed payload is `"|".join([repr(run_seed), repr(stage_seed), str(stage_index)])`; the RNG is `random.Random(int(sha256(payload.encode("utf-8")).hexdigest()[:16], 16))` and consumes tasks in their sampled order.
7. Every materialized evaluation repeat for a task receives the same stage anchor. A task/repeat candidate generated in an earlier stage is reused in later stages. The old cache is path/marker based; its judgement key is only a short SHA-1 of sorted reference IDs and is not sufficient for the new contract.
8. For an assigned anchor/task, a legacy flat task directory is one anchor repeat; otherwise all lexical `repeat_*` directories are used. The evaluation candidate is compared with every available anchor repeat.
9. The panel has three members with implicit equal weight `1.0`: `gpt-5.5` / `openai/openai/gpt-5.5` / medium; `gemini-3.1-pro` / `gcp/google/gemini-3.1-pro-preview` / high / AV capable; `claude-opus-4.8` / `aws/anthropic/bedrock-claude-opus-4-8` / thinking enabled. Legacy environment overrides can change model IDs; the formal profile must not permit them.
10. Comparison judge sampling defaults to seed 42. For each `(task_id, anchor_id, anchor_repeat_dir_name)`, the seed payload is `"|".join([repr(42), task_id, anchor_id, anchor_repeat_name])`; the RNG seed is the integer value of the first 16 hexadecimal SHA-256 characters. Four equal-weight member draws follow. Evaluation repeat is deliberately absent from this legacy draw identity.
11. Each matchup has four trials. Trial 0 presents A=anchor/B=evaluation; trial 1 A=evaluation/B=anchor; trial 2 A=anchor/B=evaluation; trial 3 A=evaluation/B=anchor. Panel draw and position alternate independently.
12. The legacy parser tests substring containment in A, B, TIE order. No token becomes TIE and an ambiguous A+B response becomes A. The new strict/fail-closed behavior must use a distinct GDPval pairwise evaluator revision owned by PR-06; invalid output is not a tie.
13. Counts are normalized to evaluation-candidate perspective. Per-matchup majority compares only A and B counts; equal A/B is a tie even if tie votes differ. AA aggregation uses the raw four trial votes, not the majority label.
14. A failed anchor-repeat judge call is skipped while other repeat matchups are retained; all failed matchups raise. A missing reference for a task is skipped, and no references yields a zero-reward error response. The formal profile instead requires an exact complete planned trial set before producing a formal aggregate.
15. Per-anchor wins/losses/ties are pooled. Ties contribute half a win. The fitted evaluation rating `R` is the unique root of `sum_i(s_i - n_i/(1 + 10**((anchor_elo_i-R)/400))) = 0`, with `s_i=wins_i+0.5*ties_i`; the implementation bisects 100 times over `[min(anchor)-4000, max(anchor)+4000]`. All-win/all-loss data clamps the overall rate to `.999/.001` around the game-weighted mean anchor. Normalized Elo is `(R-500)/2000`.
16. Each stage fits only that stage's votes, and its rating selects the next stage's anchors. The legacy headline is the last stage rating, with a pooled-stage fallback if the last stage has no rating. The formal profile must refuse a headline for an incomplete/invalid last stage and must never substitute the pooled descriptive fit.
17. The legacy journal fingerprints only stage specs, run seed, nested/reuse flags, distribution columns/task IDs/percentages, and fixed reference Elo. It stores stage plan and a bare `complete` marker; it does not bind snapshot bytes, candidate or anchor bytes, panel/trials/positions, evaluator revision, judge inputs, or evaluation jobs. It has no record hash chain or fsync, treats terminal/max-attempt failures as gated, can mark zero/partial-success stages complete, and deletes stale output. None of these weak semantics is accepted for the new formal profile.
18. Legacy Office preconversion writes a sibling PDF into the evaluation or anchor source directory and skips conversion when that sibling already exists. The new artifact presenter must write a separately content-addressed derived render, bind source/converter/output digests, and leave every CandidateBundle and anchor bundle unchanged. Presenter mechanics remain PR-06-owned; PR-08 binds the accepted presenter revision and derived-evidence hashes.
19. Legacy comparison constructs one user message from the fixed comparison instruction, task prompt, reference-file section, and two anonymous submission sections. It exposes file names/content but not model or condition labels; ignores `finish_params.json`, history/log/metadata files, and the `reference_files` directory inside submissions; sorts top-level files and extracted ZIP members; and uses base judge parameters `max_tokens=65535` and `temperature=1.0` before member overrides. The new evaluator projection must use the canonical task and allowlisted EvaluationView, exclude CandidateBundle provenance, and bind the exact projected-input digest.
20. The legacy entry accepts `--limit`, but stage task IDs are sampled from the distribution independently of the limited materialized rows. Stage row construction silently skips any sampled task absent from those rows, so a nominal 45/full stage can execute fewer tasks. The formal profile forbids `--limit`, requires exact task-set equality, and never caps or skips.
21. If a legacy stage produces no fitted Elo, the running estimate remains unavailable; `select_references` then returns every anchor even when the next stage requests four. The formal profile stops before stage 1 unless a complete stage-0 aggregate yields a finite rating.

## 4. Formal profile contract

### 4.1 Identity and immutable inputs

The formal profile ID is `gdpval-aa-v2-reproduction-v1`. The word `reproduction` is part of the ID. A partial experiment uses `gdpval-aa-v2-partial-v1-<12-hex-anchor-set-digest-prefix>` and never emits the formal headline metric.

The formal profile resolves before any policy or judge call and binds these canonical JSON objects by SHA-256:

- profile definition and protocol revision;
- BenchmarkSnapshot ID/digest and exact EvaluationView digest;
- task/repeat manifest;
- nine-anchor manifest and all anchor CandidateBundle digests;
- panel specification, evaluator ID/revision/config digest, trials, position plan, and seeds;
- task sampling, stage selection/assignment, reuse, verdict, and aggregation algorithm revisions.

PR-08 must import the common canonical serializer and SHA-256 helper established by PR-01/02 rather than copy it. Canonical JSON means UTF-8, keys sorted lexicographically, no insignificant whitespace, JSON primitives only, finite numbers only, and a trailing newline only for stored files. A content digest is SHA-256 over the canonical bytes without the trailing newline. Runtime IDs, timestamps, absolute paths, secrets, API keys, and whole environment values are excluded from content identity.

Each PR-08 manifest has `schema`, `schema_version`, and `content_sha256`. Compute `content_sha256` from the canonical object with only that top-level field omitted. The required manifests and payloads are:

| Manifest | Required payload |
|---|---|
| task/repeat plan | profile ID/revision; snapshot and distribution digests; `task_count=220`; `repeats_per_task=1`; ordered tasks containing task ID, snapshot-task/canonical-prompt/EvaluationView digests, and repeat 0's logical candidate ID and execution-request digest |
| candidate bindings | task-plan digest; ordered `(task_id, repeat_index, candidate_id, CandidateBundle digest)` entries for sealed candidates; completeness/coverage; no stage field |
| distribution | `columns=["occupation"]`; an ordered group array containing group key, finite nonnegative percentage, and ordered unique task IDs; exact set equality with the task plan |
| anchor candidates | profile/snapshot/task-plan digests; the nine ordered anchor ID/fixed-Elo entries; for every anchor and task, an ordered nonempty repeat array binding repeat ID, CandidateBundle digest, artifact-manifest digest, and EvaluationView digest |
| resolved profile | profile/protocol revision; the four manifest digests above when available; panel/evaluator/planner/aggregate digests; trial count, position vector, and seeds |

There are two binding phases. Before any policy call, preflight seals the profile, snapshot, distribution, task/repeat plan, complete anchor manifest, panel, and algorithm configuration. CandidateBundle digests do not exist yet and are not guessed. Each completed generation atomically adds a content-verified candidate binding; before a job is planned or dispatched, its candidate binding is sealed and the job binds its exact digest. The stable final candidate manifest and protocol result bind every generated candidate used by either stage.

### 4.2 Fixed anchors

The formal anchor manifest must contain exactly these entries and fixed integer Elo values, with no substitutions, omissions, duplicates, or overrides:

| Anchor ID | Fixed Elo |
|---|---:|
| `deepseek_v4_pro` | 1307 |
| `glm51_fp8` | 1257 |
| `kimi_k26` | 1191 |
| `nemotron3_ultra` | 1164 |
| `qwen36_35b` | 1049 |
| `qwen35_397b` | 962 |
| `gptoss_120b` | 799 |
| `gemma4_26b` | 761 |
| `qwen3_30b_thinking` | 308 |

Each anchor entry contains `anchor_id`, `fixed_elo`, and a task map. Every formal task has at least one explicitly named anchor repeat. Each repeat binds the exact task ID, snapshot digest, CandidateBundle ID/digest, artifact manifest digest, and evaluation-view digest. Flat-directory inference and discovery of extra `repeat_*` paths are prohibited. Missing tasks/repeats, cross-snapshot bundles, unsafe paths, changed bytes, and undeclared repeats fail preflight.

The task/repeat manifest declares every selected task and evaluation repeat before generation: task ID, snapshot task digest, canonical-prompt digest, EvaluationView digest, repeat index, logical candidate ID, and the CandidateBundle digest once sealed. The formal profile requires the bound 220-task snapshot and exactly one evaluation repeat per task. A CLI limit, a snapshot with fewer than 220 tasks, a stage-0 sample capped below 45, or a silently absent materialized row is invalid. Any reduced task count requires a partial or characterization profile ID.

### 4.3 Panel, trials, and positions

The formal profile pins the three panel entries from section 3 with exact member ID, model ID, reasoning/create overrides, AV capability, and weight `1.0`. Model ID or reasoning overrides create a different profile and cannot retain the formal ID. Endpoint/auth location is runtime provenance, not panel content, but a runtime must prove it can serve every pinned member before execution. AV content with no capable pinned judge fails preflight.

The evaluator-config digest also binds the accepted PR-06 comparison prompt, anonymous projection/presenter revision, strict parser revision, base generation parameters (`max_tokens=65535`, `temperature=1.0` before member overrides), and explicit request retry/timeout policy. Candidate/model/executor/condition/Builder provenance is excluded from the judge projection. Only the canonical task, allowlisted EvaluationView/reference material, and the two presented artifact trees enter the judge-input digest.

AV routing is resolved per `(task, evaluation repeat, assigned anchor)` comparison group before expanding anchor repeats, matching the legacy verifier. If the evaluation candidate or any declared repeat of that assigned anchor contains audio/video, including inside a ZIP, every repeat matchup in that group uses exactly the AV-capable panel subset. With the pinned panel that means Gemini for all four trials of every group job. A group with no AV uses all three members. Empty eligible sets fail preflight; the legacy fallback to text-only judges is forbidden.

The profile pins judge seed `42`, four trials per evaluation job, the legacy judge-draw identity `(task_id, anchor_id, anchor_repeat_id)` excluding evaluation repeat, and the fixed position vector `[anchor/evaluation, evaluation/anchor, anchor/evaluation, evaluation/anchor]`. The fully resolved stage plan persists the four chosen member IDs and two presented candidate IDs for every trial. Resume uses that plan; it never redraws.

Raw judge responses are persisted as content-addressed UTF-8 evidence and their SHA-256 values are linked from the common BattleRecord. The normalized strict verdict and stable result digest are separate fields. Secrets and transport headers are never placed in either object. An unavailable, malformed, ambiguous, or unparseable final verdict records `battle_status=invalid_response` and cannot be normalized to tie.

### 4.4 Stage planning and generation reuse

The formal plan has two independent-sampling stages (`nested_tasks=false`) and one evaluation-candidate repeat unless a future profile revision says otherwise:

| Stage | Tasks | Included anchors | Assignment |
|---|---|---|---|
| 0 | 45 sampled proportionally without replacement over occupation | all nine | one uniform anchor per task |
| 1 | every task in the declared snapshot task manifest | four closest to stage-0 Elo; distance tie by anchor ID | one uniform selected anchor per task |

PR-08 pins task/assignment seed `42` as an explicit `reproduction-v1` design choice. This is not an observed legacy default and is not attributed to the external official protocol: the legacy shell pins only the judge seed and otherwise leaves multistage sampling unseeded. Changing this seed requires a new profile revision.

The `reproduction-v1` algorithm parameters are exact:

| Rule | Revision-1 behavior |
|---|---|
| stage task sampling | both stage seeds are null; one `random.Random(42)` stream drives independent proportional-without-replacement sampling in stage order; stage 0 requests exactly 45 and stage 1 requests exactly 220; choose a live ordered group by saved percentage, then `randrange` within its remaining ordered task list |
| stage anchor set | stage 0 is every fixed anchor sorted by ID; stage 1 ranks by `(abs(fixed_elo - exact_stage_0_elo), anchor_id)`, takes four, then sorts those four by ID |
| task-to-anchor assignment | per stage seed `int(SHA256("42|None|<stage_index>")[:16], 16)` into `random.Random`; consume ordered stage tasks and call `choice` over the sorted included-anchor IDs |
| judge-member draw | per matchup seed `int(SHA256("42|<task_id>|<anchor_id>|<anchor_repeat_id>")[:16], 16)` into `random.Random`; make four equal-weight `choices` calls over panel order GPT, Gemini, Claude |
| positions | trials 0/2 have anchor in A; trials 1/3 have evaluation candidate in A |
| aggregate | raw normalized trial votes, ties worth 0.5, 100-step anchored MLE bisection and degenerate clamp exactly as characterized in section 3 |

These algorithm names/implementations must be revisioned and regression-tested by the machine fixture. Switching RNG, seed serialization, panel order, task/group order, rounding, or Elo solver requires a new profile revision even if a particular sample happens to match.

The ordered task sets for both stages may be precomputed from the bound task manifest and seed before stage 0. The complete stage-1 plan cannot be produced then: its included anchors, assignments, jobs, and trial plan depend on a verified complete stage-0 aggregate. Each complete stage plan is persisted before its first job and binds ordered task IDs, included anchors, prior aggregate digest/rating, task-to-anchor assignment, anchor-repeat expansion, evaluation job IDs, and the explicit four-trial plans.

Generation identity is `(resolved profile's snapshot identity, task_id, evaluation repeat, execution request content digest)`, never stage. Its stable outer field is the PR-05 `generation_occurrence_id`; PR-05 excludes that occurrence ID from CandidateBundle content, model input, and runtime path identity. A sealed CandidateBundle with the exact expected digest is used in every stage that refers to it. No application session, mutable workspace, or conversation is reused.

PR-08 uses the frozen `eval_harness.generation_runner` seam. Before stage execution it constructs one `GenerationPlan` containing the Stirrup-backed `ApplicationSpec`, all 220 unique ordered task `SnapshotReference` values, and one `CandidateGenerationRequest(generation_occurrence_id, snapshot_reference, NoneIntervention)` per task/repeat. It passes the already acquired `VerifiedSnapshotBinding`, executor, and disjoint run/runtime roots to `prepare_generation_plan`, which returns an opaque `BoundGenerationPlan` and performs no evaluator work. When a stage first needs a task/repeat, PR-08 calls `generate_candidate` for that exact occurrence and consumes its `GeneratedCandidate(generation_occurrence_id, RunResultRow, CandidateBundle)`; later stages revalidate and reuse that sealed bundle. `run_generation_plan` is not required because adaptive evaluation occurs between generation subsets. No PR-08 code reacquires the benchmark/snapshot, calls the staged whole-run `run_benchmark`, accepts an evaluator in the generation phase, or copies the PR-05 identity/writer implementation.

Evaluation identity has two layers. `evaluation_input_sha256` binds the content shared by otherwise identical comparisons. `evaluation_job_id` also binds `match_occurrence_id`, an opaque planner occurrence ID derived by PR-08 from resolved-profile digest, stage index, task/evaluation repeat, anchor ID, and anchor repeat. Thus, if later-stage assignment repeats the same task/anchor content, it creates a new four-trial occurrence and denominator, matching fresh legacy execution. Completed BattleRecords are reused only while resuming the same planned occurrence with every input/evidence hash unchanged. The common runner treats `match_occurrence_id` as opaque and does not learn AA stage or anchor semantics.

### 4.5 BattleRecord join and pure aggregate

PR-08 consumes PR-06 records; it does not add AA fields to the common schema. Its stage plan joins each `match_occurrence_id` and `evaluation_job_id` to `stage_index`, task/evaluation repeat, anchor ID/fixed Elo, and anchor repeat. A completed record must bind `battle_record_id`, job/trial/occurrence identity, evaluation-input digest, explicit slots, judge member/spec/panel and judge-input hashes, evaluator revision/config, normalized winner candidate ID or tie, output/result hash, and `battle_status=completed`. PR-06 exposes completed-only `battle_semantic_sha256` separately from `attempt_id`, positive `attempt_number`, per-event `attempt_event_sha256`, ordered-chain `attempt_history_sha256`, timestamps, paths, and raw evidence. The attempt/history fields cannot perturb the semantic digest that PR-08 aggregates. Other PR-06 battle states are exactly `planned`, `running`, `failed`, `interrupted`, and `invalid_response`; none supplies a semantic digest or vote.

Aggregation first verifies exact set equality between planned `battle_record_id` values and unique records with `battle_status=completed` and valid `battle_semantic_sha256` values. Missing, duplicate, `invalid_response`, failed, interrupted, hash-mismatched, or unplanned records make coverage incomplete. A formal stage aggregate and subsequent stage are unavailable until coverage is exactly 1.0. Invalid output never becomes a tie. No partial-reference skip or last-stage pooled fallback is allowed.

`trial_coverage` is completed-valid planned trials divided by planned trials; `job_coverage` and `task_coverage` use the analogous exact planned sets. Every evaluation-repeat × declared anchor-repeat job contributes four raw trial votes with equal weight. Results are not first reduced to a task or matchup majority. A formal stage requires all three coverage values to equal `1.0`; the headline `coverage` is the last-stage trial coverage after both stages are complete.

The pure reduction maps the normalized winner to evaluation-perspective win/loss/tie; sums four trials across every planned anchor repeat, evaluation repeat, and task; groups by fixed anchor; and applies the anchored MLE in section 3. Stage aggregates include ordered stable BattleRecord semantic IDs/digests, exact counts, task/job/trial denominators, coverage, per-anchor counts, Elo, normalized Elo, and a stable semantic aggregate digest. The digest excludes timestamps, journal sequence, attempts, raw-response storage locations, and other runtime evidence, while each such item remains integrity-linked in the audit history. The formal headline is stage 1's rating only.

Metric names are protocol-specific: `gdpval_aa_v2/stage/<index>/{wins,losses,ties,judged,trial_coverage,job_coverage,task_coverage,elo,normalized_elo,num_anchors,num_tasks}` and `gdpval_aa_v2/{elo,normalized_elo,coverage}` for a complete formal headline. Pooled cross-stage counts may be emitted only under `gdpval_aa_v2/descriptive/pooled/*`. A partial profile uses the `gdpval_aa_v2_partial/*` namespace and includes its anchor-set digest. Generic pairwise evaluation reports W/L/T and coverage only; no anchorless or arbitrary-pair Elo is created. No universal score conversion is permitted.

## 5. Resume journal contract

The authoritative journal is a directory of immutable canonical-JSON event files, not a mutable JSONL file. Every event has `schema`, `run_id`, monotonic `sequence`, `event_type`, `created_at`, `previous_event_sha256`, `payload`, and `event_sha256`. The event hash covers the canonical object without `event_sha256`; the first previous hash is null. Publish an event by writing a same-directory temporary file, flushing and fsyncing it, atomically renaming it to `<zero-padded-sequence>-<event_sha256>.json`, and fsyncing the directory before dependent work begins. An atomically replaced `head.json` may accelerate lookup but is only a cache; recovery enumerates and verifies immutable events. A derived JSONL export may be created after completion but is not authoritative.

Required event payloads are:

| Event | Required content |
|---|---|
| `run_bound` | resolved profile, snapshot, task/repeat, anchor, panel, evaluator, planner and execution-request digests; repository commit/dirty state as provenance |
| `stage_planned` | prior aggregate digest; ordered tasks/anchors/assignments; job and explicit trial plans; stage-plan digest |
| `trial_state` | PR-06 `battle_record_id`, completed-only `battle_semantic_sha256`, `evaluation_job_id`, `match_occurrence_id`, `battle_status`, `attempt_id`/positive `attempt_number`, `attempt_event_sha256`, current `attempt_history_sha256`, and typed failure/stop reason |
| `stage_aggregated` | sorted complete stable BattleRecord semantic ID/digest set, denominators/counts, rating, stable semantic aggregate digest, linked evidence/history digest |
| `stage_completed` | stage-plan and aggregate digests plus exact coverage `1.0` |
| `run_stopped` | stop class/reason and last durable sequence |
| `protocol_completed` | both stage completion digests and formal headline aggregate digest |

On resume, verify the entire unique hash chain and every referenced artifact before skipping work. A temporary event that never reached its atomic rename is not part of the journal; retain or quarantine it as evidence instead of truncating or deleting any prior event. A missing sequence, fork, malformed immutable event, hash mismatch, or content mismatch fails closed. A `running` trial without a terminal record becomes `interrupted`, remains in history, and receives a new attempt event. A completed trial is skipped only when every snapshot, profile, candidate, anchor, panel, evaluator, input, result, and linked evidence hash revalidates. Recompute every stage aggregate from its exact stable BattleRecord semantic set and require its semantic hash to match before trusting `stage_completed`.

A mismatch never deletes or overwrites old output. Stop with a content-mismatch result; starting under changed inputs requires a new output/run ID. Systemic auth/quota/protocol failures stop remaining dispatch, while ordinary invalid verdicts and retryable judge failures retain their distinct record states. Neither state contributes a tie or denominator until a valid completed attempt exists. Given the same completed normalized verdicts, interrupted and uninterrupted executions yield the same stable BattleRecord semantic set, stage-result digest, and protocol-result digest. Their event-chain/history/raw-evidence digests may differ, and both histories remain valid audit records. The deterministic fake-judge tests require equal verdicts and therefore assert equal semantic results; a nondeterministic real judge retry is recorded as the result actually returned and is not claimed to reproduce an unobserved interrupted response.

## 6. Deterministic characterization fixture (computed)

The fixture uses the baseline pure code, a six-task/two-group synthetic distribution, task/assignment seed 42, judge seed 42, four trials, one anchor repeat, and the nine fixed anchors. It contains no actual model output.

Task outcome votes are fixed in evaluation perspective: `t0=3/1/0`, `t1=2/1/1`, `t2=1/2/1`, `t3=0/3/1`, `t4=4/0/0`, `t5=0/4/0` (wins/losses/ties). The raw position-relative tokens are respectively `[B,A,B,B]`, `[B,A,A,TIE]`, `[B,B,A,TIE]`, `[A,B,A,TIE]`, `[B,A,B,A]`, `[A,B,A,B]` under the fixed alternating position vector.

Expected planning and aggregation:

| Value | Stage 0 | Stage 1 |
|---|---|---|
| Ordered tasks | `t3,t4,t2,t0` | `t3,t0,t1,t5,t2,t4` |
| Included anchors | all nine sorted IDs | `deepseek_v4_pro,glm51_fp8,kimi_k26,nemotron3_ultra` |
| Assignment | `t3→glm51_fp8; t4→gemma4_26b; t2→deepseek_v4_pro; t0→kimi_k26` | `t3→kimi_k26; t0→glm51_fp8; t1→deepseek_v4_pro; t5→glm51_fp8; t2→nemotron3_ultra; t4→kimi_k26` |
| Totals | 8 wins, 6 losses, 2 ties | 10 wins, 11 losses, 3 ties |
| Elo | `1209.1488323308195` | `1212.9704159020607` |
| Normalized Elo | `0.35457441616540974` | `0.35648520795103034` |
| Anchors used in fit | 4 | 4 |

Stage 0 per-anchor totals are: deepseek `1/2/1`, gemma `4/0/0`, glm `0/3/1`, kimi `3/1/0`. Stage 1 per-anchor totals are: deepseek `2/1/1`, glm `3/5/0`, kimi `4/3/1`, nemotron `1/2/1`. Stage 1 is the fixture headline. Four candidate bundles recur in stage 1 (`t3,t0,t2,t4`), two are newly generated (`t1,t5`), so six distinct generations serve ten stage-task appearances.

The machine-readable fixture is `contracts/pr08-aa-v2-characterization-fixture.json`. Its profile ID is `gdpval-aa-v2-characterization-fixture-v1`; the reduced six-task setup must never be accepted under the formal profile ID. Its expected semantic-result SHA-256 is `2a15920e81fd97b8e24b51a37b36572d54f03e6e7ad9eea9e4b389cbd2fe9eb9`, fixture-payload digest (excluding the `hashes` member) is `ac0a12f23344bc126ed0788608a6d430b4f2ddebde3b0cf3f007727e91ab4ff6`, and stored-file SHA-256 is `fe65da1f4c06eb192883137c4b838830530a6044614c3572291de33e7c689826`. Required resume fixture: interrupt after a persisted running trial and after a complete stage-0 aggregate; both resumptions must yield the identical stable semantic record set and final semantic aggregate digest as an uninterrupted run while retaining distinct attempt history.

The second machine-readable fixture, `contracts/pr08-aa-v2-cross-stage-occurrence-fixture.json`, uses the same six tasks with task/assignment seed 0 solely to characterize occurrence identity. Baseline planning assigns `t5` to `qwen36_35b/repeat_0` in both stages. Its stage Elo values are `1053.4023880716363` (`0x1.0759c0b9e5feap+10`) and `1057.149571213491` (`0x1.0849929323978p+10`). The repeated matchup uses one evaluation CandidateBundle digest, one anchor CandidateBundle digest, and one evaluation-input digest, but two `match_occurrence_id` values, two evaluation-job IDs, and eight unique `battle_record_id`/`battle_semantic_sha256` pairs. Each occurrence contributes `0/4/0`; the correct combined votes are `0/8/0`, whereas content deduplication would incorrectly yield `0/4/0`. PR-08 treats the common PR-06 identity/digest literals as opaque and tests equality, distinctness, exact-set membership, status, and persisted round-trip rather than duplicating PR-06 canonicalization. Its expected SHA-256 is `cdccb5c530f345c0038727e79dd1307eda4be9f5c2ec5087826e91199508d16b`, fixture-payload digest is `b7b4886a849dd5e9abc667f8f8daa21a8459f425ef888cce519e5594fc9dc6a9`, and stored-file SHA-256 is `0c3c6c907a6629a3197a0d51ac3f557e7951f5fb824570a17e854d759b2be2a0`.

## 7. Required tests and completion gates

1. Full preflight accepts exactly nine correct anchors and every task/repeat/hash; missing, renamed, extra-declared, cross-snapshot, mutated, or unsafe anchor material fails before model/judge execution.
2. A partial anchor set is rejected under the formal ID and accepted only with its distinct partial ID/metric namespace.
3. Deterministic fixtures assert task order, stage anchors, assignments, explicit judge/position plans, BattleRecord-normalized votes, per-anchor totals, exact Elo values above, and stage-1 headline. The cross-stage fixture additionally proves one content digest can have two `match_occurrence_id` values/two planned jobs/eight `battle_record_id` values and that all eight votes enter their stage denominators.
4. A changed task sampling seed, panel weight/model/override, trials/positions, fixed Elo, snapshot/evaluation view, candidate bytes, anchor bytes, evaluator revision, or job input changes the appropriate digest and invalidates reuse.
5. Candidate generation happens once per task/repeat across stages. A repeated cross-stage matchup creates a distinct occurrence and four new trials; resume reuses only the same completed occurrence after exact content/evidence revalidation. Moving immutable bundles between runtime roots does not change their content identity.
6. Invalid/ambiguous/missing verdicts, a missing trial, all judge failures, one failed repeat, missing reference task, and insufficient AV judge capability cannot produce formal coverage or a headline.
7. Arbitrary two-candidate comparisons emit W/L/T without Elo. A complete formal profile emits named AA metrics without a universal score.
8. Interrupt/resume at each event boundary preserves existing immutable event files, retries only incomplete work, verifies the chain/content/evidence hashes, and produces the same semantic records and aggregate digests as uninterrupted execution. Full histories need not be byte-identical. Corruption/mismatch fails without deleting old output.
9. Integration uses the common evaluation runner and PR-06 BattleRecord path and proves the old shell, resources-server orchestrator, and old cache/journal code were not invoked. No model calls occur in CI.

## 8. Pending claims and decisions

- **Real 220-task snapshot:** the prepared GDPval dataset is gitignored and absent from the immutable source baseline. The formal profile requires its exact accepted BenchmarkSnapshot/task/EvaluationView manifests and hashes; documentation that the dataset has 220 tasks is not a substitute.
- **Real anchor completeness:** the repository contains IDs/Elo only, not the actual anchor bundles or their task/repeat hashes. Gate B must compare supplied anchors read-only against a resolved manifest; absence blocks the formal profile.
- **Protocol authority:** repository prose calls the path compatible/reproduction and notes that references are generated by the operator. The exact panel and anchor values are repository-pinned behavior, not proof of the external official protocol.
- **Strict evaluator revision:** baseline invalid-response-as-tie and AV fallback are characterized but must not survive under the new strict revision. The final PR-06 evaluator ID/revision must be bound here.
- **Exact anchor repeat count:** legacy accepts one or many and discovers them from paths. The resolved formal manifest must state every repeat explicitly; actual expected counts cannot be inferred from this repository.

## 9. Implementation handoff

Allowed PR-08 changes should be restricted to a new profile/config module, AA-specific planner/journal/aggregate modules, registration/CLI wiring required for `./eval experiment`, deterministic fixtures/tests, and focused documentation. Changes to common evaluation/BattleRecord semantics return to PR-06; changes to snapshot/CandidateBundle identity return to PR-01/02; changes to Stirrup generation return to PR-07.

Implementation is complete only when all section 7 tests pass under the locked quality gates, the formal profile cannot silently shrink, the new common path completes without an old runner, and documentation labels the result as a reproduction profile without claiming an unperformed real score reproduction.
