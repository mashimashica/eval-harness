# PR-08 AA-v2 protocol characterization and design contract

Status: design checkpoint; implementation and real-model/real-anchor validation are not performed.  
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
| `resources_servers/gdpval/multistage_elo.py` | `8f6e7b0c...` | Pure task sampling, anchor selection/assignment, vote pooling, anchored MLE |
| `resources_servers/gdpval/multistage_orchestrator.py` | `92fc83c0...` | Stage execution, generation reuse, weak legacy journal/resume |
| `resources_servers/gdpval/comparison.py` | `62fb5b3a...` | Pairwise positions, permissive verdict parser, tally, anchored MLE |
| `resources_servers/gdpval/judge_panel.py` | `8b5355c3...` | Weighted deterministic panel sampling and AV routing |
| `benchmarks/gdpval/config.yaml` | `69e056db...` | Four trials, one generation repeat, three-member panel |
| `nemotron_recipes/lightning-3.5/instruct/gym/gdpval/gdpval.sh` | `9f49bb10...` | Legacy AA reference discovery, two stages, judge seed 42 |

The abbreviated hashes above are placeholders in this first checkpoint and must be replaced with full verified values before design completion.

## 3. Exact legacy procedure mapping

1. `./gdpval aa-v2 --refs DIR` requires the Stirrup executor, forbids a local judge executor and condition overrides, selects comparison mode, selects the `aa-v2` panel, and defaults to the pinned TSV manifest.
2. The recipe reads the TSV but checks only whether each top-level `<refs>/<anchor_id>` directory exists. Missing anchors are silently omitted. Zero found is fatal; one found runs an unstaged comparison; two or more found selects two stages and sets the second-stage reference count to `min(found, 4)`. This behavior is forbidden for the new formal profile.
3. With all anchors present, stage 0 samples 45 tasks and includes all nine anchors. Stage 1 omits `num_tasks`, meaning the full prepared distribution (documented as 220 tasks), and selects four anchors. `nested_tasks=false`, so stage samples are independent.
4. The distribution is grouped by occupation. Each task draw first chooses a live group using its saved percentage, then a task within the group, without replacement. Counts are capped at available tasks. The shell does not set a multistage seed, so fresh legacy task/assignment plans are not reproducible unless separately configured or replayed from the journal.
5. Stage 0 uses every available anchor sorted by ID. Later stages sort anchors by `(abs(fixed_elo - previous_stage_elo), anchor_id)`, take `num_models`, and return the selected IDs sorted.
6. Each selected task is assigned one included anchor uniformly. Assignment RNG is `random.Random(int(sha256("repr(run_seed)|repr(stage_seed)|stage_index")[:16], 16))` and consumes tasks in their sampled order.
7. Every materialized evaluation repeat for a task receives the same stage anchor. A task/repeat candidate generated in an earlier stage is reused in later stages. The old cache is path/marker based; its judgement key is only a short SHA-1 of sorted reference IDs and is not sufficient for the new contract.
8. For an assigned anchor/task, a legacy flat task directory is one anchor repeat; otherwise all lexical `repeat_*` directories are used. The evaluation candidate is compared with every available anchor repeat.
9. The panel has three members with implicit equal weight `1.0`: `gpt-5.5` / `openai/openai/gpt-5.5` / medium; `gemini-3.1-pro` / `gcp/google/gemini-3.1-pro-preview` / high / AV capable; `claude-opus-4.8` / `aws/anthropic/bedrock-claude-opus-4-8` / thinking enabled. Legacy environment overrides can change model IDs; the formal profile must not permit them.
10. Comparison judge sampling defaults to seed 42. For each `(task_id, anchor_id, anchor_repeat_dir_name)`, the RNG seed is the first 64 bits of SHA-256 over `repr(42)|task_id|anchor_id|anchor_repeat_name`. Four equal-weight member draws follow. Evaluation repeat is deliberately absent from this legacy draw identity.
11. Each matchup has four trials. Trial 0 presents A=anchor/B=evaluation; trial 1 A=evaluation/B=anchor; trial 2 A=anchor/B=evaluation; trial 3 A=evaluation/B=anchor. Panel draw and position alternate independently.
12. The legacy parser tests substring containment in A, B, TIE order. No token becomes TIE and an ambiguous A+B response becomes A. The new strict/fail-closed behavior must use a distinct GDPval pairwise evaluator revision owned by PR-06; invalid output is not a tie.
13. Counts are normalized to evaluation-candidate perspective. Per-matchup majority compares only A and B counts; equal A/B is a tie even if tie votes differ. AA aggregation uses the raw four trial votes, not the majority label.
14. A failed anchor-repeat judge call is skipped while other repeat matchups are retained; all failed matchups raise. A missing reference for a task is skipped, and no references yields a zero-reward error response. The formal profile instead requires an exact complete planned trial set before producing a formal aggregate.
15. Per-anchor wins/losses/ties are pooled. Ties contribute half a win. The fitted evaluation rating `R` is the unique root of `sum_i(s_i - n_i/(1 + 10**((anchor_elo_i-R)/400))) = 0`, with `s_i=wins_i+0.5*ties_i`; the implementation bisects 100 times over `[min(anchor)-4000, max(anchor)+4000]`. All-win/all-loss data clamps the overall rate to `.999/.001` around the game-weighted mean anchor. Normalized Elo is `(R-500)/2000`.
16. Each stage fits only that stage's votes, and its rating selects the next stage's anchors. The legacy headline is the last stage rating, with a pooled-stage fallback if the last stage has no rating. The formal profile must refuse a headline for an incomplete/invalid last stage and must never substitute the pooled descriptive fit.
17. The legacy journal fingerprints only stage specs, run seed, nested/reuse flags, distribution columns/task IDs/percentages, and fixed reference Elo. It stores stage plan and a bare `complete` marker; it does not bind snapshot bytes, candidate or anchor bytes, panel/trials/positions, evaluator revision, judge inputs, or evaluation jobs. It has no record hash chain or fsync, treats terminal/max-attempt failures as gated, can mark zero/partial-success stages complete, and deletes stale output. None of these weak semantics is accepted for the new formal profile.

## 4. Formal profile contract

### 4.1 Identity and immutable inputs

The formal profile ID is `gdpval-aa-v2-reproduction-v1`. The word `reproduction` is part of the ID. A partial experiment uses `gdpval-aa-v2-partial-v1:<resolved-anchor-set-digest-prefix>` and never emits the formal headline metric.

The formal profile resolves before any policy or judge call and binds these canonical JSON objects by SHA-256:

- profile definition and protocol revision;
- BenchmarkSnapshot ID/digest and exact EvaluationView digest;
- task/repeat manifest;
- nine-anchor manifest and all anchor CandidateBundle digests;
- panel specification, evaluator ID/revision/config digest, trials, position plan, and seeds;
- task sampling, stage selection/assignment, reuse, verdict, and aggregation algorithm revisions.

Canonical JSON means UTF-8, keys sorted lexicographically, no insignificant whitespace, JSON primitives only, finite numbers only, and a trailing newline only for stored files. A content digest is SHA-256 over the canonical bytes without the trailing newline. Runtime IDs, timestamps, absolute paths, secrets, API keys, and whole environment values are excluded from content identity.

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

The task/repeat manifest declares every selected task and evaluation repeat before generation: task ID, snapshot task digest, canonical-prompt digest, EvaluationView digest, repeat index, logical candidate ID, and the CandidateBundle digest once sealed. The formal benchmark has the complete declared snapshot task set; a CLI limit or silently absent materialized row is invalid.

### 4.3 Panel, trials, and positions

The formal profile pins the three panel entries from section 3 with exact member ID, model ID, reasoning/create overrides, AV capability, and weight `1.0`. Model ID or reasoning overrides create a different profile and cannot retain the formal ID. Endpoint/auth location is runtime provenance, not panel content, but a runtime must prove it can serve every pinned member before execution. AV content with no capable pinned judge fails preflight.

The profile pins judge seed `42`, four trials per evaluation job, the legacy judge-draw identity `(task_id, anchor_id, anchor_repeat_id)` excluding evaluation repeat, and the fixed position vector `[anchor/evaluation, evaluation/anchor, anchor/evaluation, evaluation/anchor]`. The fully resolved stage plan persists the four chosen member IDs and two presented candidate IDs for every trial. Resume uses that plan; it never redraws.

### 4.4 Stage planning and generation reuse

The formal plan has two independent-sampling stages (`nested_tasks=false`) and one evaluation-candidate repeat unless a future profile revision says otherwise:

| Stage | Tasks | Included anchors | Assignment |
|---|---|---|---|
| 0 | 45 sampled proportionally without replacement over occupation | all nine | one uniform anchor per task |
| 1 | every task in the declared snapshot task manifest | four closest to stage-0 Elo; distance tie by anchor ID | one uniform selected anchor per task |

PR-08 must set and pin the task/assignment seed; the proposed fidelity value is `42`. This remains marked **pending source authority** because the legacy shell fixes the judge seed at 42 but leaves the multistage seed unset. The implementation must not advertise deterministic formal reproduction until this profile seed is explicitly accepted.

All task sets are planned before stage 0. A stage plan is persisted before its first job and binds ordered task IDs, included anchors, prior aggregate digest/rating, task-to-anchor assignment, anchor-repeat expansion, evaluation job IDs, and the explicit four-trial plans. Stage 1 cannot be planned until a complete verified stage-0 aggregate exists.

Generation identity is `(resolved profile's snapshot identity, task_id, evaluation repeat, execution request content digest)`, never stage. A sealed CandidateBundle with the exact expected digest is used in every stage that refers to it. No application session, mutable workspace, or conversation is reused. A content-identical evaluation job may also reuse the same completed PR-06 BattleRecords because stage is absent from evaluation-job identity.

### 4.5 BattleRecord join and pure aggregate

PR-08 consumes PR-06 records; it does not add AA fields to the common schema. Its stage plan joins each `evaluation_job_id` to `stage_index`, task/evaluation repeat, anchor ID/fixed Elo, and anchor repeat. A completed record must bind job/trial ID, explicit slots, judge member/spec/panel and judge-input hashes, evaluator revision/config, normalized winner candidate ID or tie, output/result hash, and terminal state.

Aggregation first verifies exact set equality between planned trial IDs and unique completed valid BattleRecord IDs. Missing, duplicate, invalid, failed, interrupted, hash-mismatched, or unplanned records make coverage incomplete. A formal stage aggregate and subsequent stage are unavailable until coverage is exactly 1.0. Invalid output never becomes a tie. No partial-reference skip or last-stage pooled fallback is allowed.

The pure reduction maps the normalized winner to evaluation-perspective win/loss/tie; sums four trials across every planned anchor repeat, evaluation repeat, and task; groups by fixed anchor; and applies the anchored MLE in section 3. Stage aggregates include ordered input record IDs/hashes, exact counts, task/job/trial denominators, coverage, per-anchor counts, Elo, normalized Elo, and aggregate digest. The formal headline is stage 1's rating only.

Metric names are protocol-specific: `gdpval_aa_v2/stage/<index>/{wins,losses,ties,judged,coverage,elo,normalized_elo,num_anchors,num_tasks}` and `gdpval_aa_v2/{elo,normalized_elo,coverage}` for a complete formal headline. Pooled cross-stage counts may be emitted only under `gdpval_aa_v2/descriptive/pooled/*`. A partial profile uses the `gdpval_aa_v2_partial/*` namespace and includes its anchor-set digest. Generic pairwise evaluation reports W/L/T and coverage only; no anchorless or arbitrary-pair Elo is created. No universal score conversion is permitted.

## 5. Resume journal contract

The journal is append-only canonical JSONL. Every event has `schema`, `run_id`, monotonic `sequence`, `event_type`, `created_at`, `previous_event_sha256`, `payload`, and `event_sha256`. The event hash covers the canonical object without `event_sha256`; the first previous hash is null. Each append is flushed and fsynced before dependent work begins.

Required event payloads are:

| Event | Required content |
|---|---|
| `run_bound` | resolved profile, snapshot, task/repeat, anchor, panel, evaluator, planner and execution-request digests; repository commit/dirty state as provenance |
| `stage_planned` | prior aggregate digest; ordered tasks/anchors/assignments; job and explicit trial plans; stage-plan digest |
| `trial_state` | PR-06 BattleRecord ID/digest, job/trial/attempt IDs, state, typed failure/stop reason |
| `stage_aggregated` | sorted complete BattleRecord ID/digest set, denominators/counts, rating, aggregate digest |
| `stage_completed` | stage-plan and aggregate digests plus exact coverage `1.0` |
| `run_stopped` | stop class/reason and last durable sequence |
| `protocol_completed` | both stage completion digests and formal headline aggregate digest |

On resume, verify the entire hash chain and every referenced artifact before skipping work. An unterminated final JSON fragment may be truncated only to the last newline after the preceding chain verifies; malformed or mismatched interior events fail closed. A `running` trial without a terminal record becomes `interrupted`, remains in history, and receives a new attempt event. A completed trial is skipped only when every snapshot, profile, candidate, anchor, panel, evaluator, input, and result hash matches. Recompute every stage aggregate from its exact BattleRecord set and require its hash to match before trusting `stage_completed`.

A mismatch never deletes or overwrites old output. Stop with a content-mismatch result; starting under changed inputs requires a new output/run ID. Systemic auth/quota/protocol failures stop remaining dispatch, while ordinary invalid verdicts and retryable judge failures retain their distinct record states. Neither state contributes a tie or denominator until a valid completed attempt exists.

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

The machine-readable fixture and its canonical component hashes are pending in this first checkpoint. Required resume fixture: interrupt after a persisted running trial and after a complete stage-0 aggregate; both resumptions must yield the identical ordered semantic record set and final aggregate digest as an uninterrupted run, while retaining attempt history.

## 7. Required tests and completion gates

1. Full preflight accepts exactly nine correct anchors and every task/repeat/hash; missing, renamed, extra-declared, cross-snapshot, mutated, or unsafe anchor material fails before model/judge execution.
2. A partial anchor set is rejected under the formal ID and accepted only with its distinct partial ID/metric namespace.
3. Deterministic fixture asserts task order, stage anchors, assignments, explicit judge/position plans, BattleRecord-normalized votes, per-anchor totals, exact Elo values above, and stage-1 headline.
4. A changed task sampling seed, panel weight/model/override, trials/positions, fixed Elo, snapshot/evaluation view, candidate bytes, anchor bytes, evaluator revision, or job input changes the appropriate digest and invalidates reuse.
5. Candidate generation happens once per task/repeat across stages; evaluation-job reuse occurs only for an exact content-addressed match. Moving immutable bundles between runtime roots does not change identity.
6. Invalid/ambiguous/missing verdicts, a missing trial, all judge failures, one failed repeat, missing reference task, and insufficient AV judge capability cannot produce formal coverage or a headline.
7. Arbitrary two-candidate comparisons emit W/L/T without Elo. A complete formal profile emits named AA metrics without a universal score.
8. Interrupt/resume at each event boundary preserves existing records, retries only incomplete work, verifies the chain/content hashes, and produces the same semantic records and aggregate digests as uninterrupted execution. Corruption/mismatch fails without deleting old output.
9. Integration uses the common evaluation runner and PR-06 BattleRecord path and proves the old shell, resources-server orchestrator, and old cache/journal code were not invoked. No model calls occur in CI.

## 8. Pending claims and decisions

- **Profile task/assignment seed:** proposed `42`; legacy does not pin it. This must be accepted as a new profile revision choice, recovered from stronger source evidence, or the formal profile must refuse reproducibility claims.
- **Real anchor completeness:** the repository contains IDs/Elo only, not the actual anchor bundles or their task/repeat hashes. Gate B must compare supplied anchors read-only against a resolved manifest; absence blocks the formal profile.
- **Protocol authority:** repository prose calls the path compatible/reproduction and notes that references are generated by the operator. The exact panel and anchor values are repository-pinned behavior, not proof of the external official protocol.
- **PR-06 schema names:** required semantics were sent to the PR-06 owner; PR-08 must use the accepted common names/types rather than fork them.
- **Strict evaluator revision:** baseline invalid-response-as-tie and AV fallback are characterized but must not survive under the new strict revision. The final PR-06 evaluator ID/revision must be bound here.
- **Exact anchor repeat count:** legacy accepts one or many and discovers them from paths. The resolved formal manifest must state every repeat explicitly; actual expected counts cannot be inferred from this repository.

## 9. Implementation handoff

Allowed PR-08 changes should be restricted to a new profile/config module, AA-specific planner/journal/aggregate modules, registration/CLI wiring required for `./eval experiment`, deterministic fixtures/tests, and focused documentation. Changes to common evaluation/BattleRecord semantics return to PR-06; changes to snapshot/CandidateBundle identity return to PR-01/02; changes to Stirrup generation return to PR-07.

Implementation is complete only when all section 7 tests pass under the locked quality gates, the formal profile cannot silently shrink, the new common path completes without an old runner, and documentation labels the result as a reproduction profile without claiming an unperformed real score reproduction.
