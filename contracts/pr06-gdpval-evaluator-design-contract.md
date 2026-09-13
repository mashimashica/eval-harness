<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR06 GDPval evaluator design contract

> Checkpoint status (2026-09-13): complete design/characterization handoff, not accepted implementation or migration state. No production code or real-model result is represented by this document.

## Checkpoint identity

| Field | Value |
|---|---|
| Design owner | Sol (`/root/sol_gdpval_semantics`) |
| Control parent | `8518f25d107d9043df449a9198fbb41b00ba1c22` |
| Source baseline | `d5ce0c10162cad788a17cb90f34b8f60574e7f75` (tree `354943ebbb8ea81a30523bfdc12baf26771853b5`) |
| Canonical plan | `eval-harness-neutrality-migration-plan-2026-09-12.md`, 33,790 bytes, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f` |
| Scope | Design and deterministic characterization only; no production edits and no live model calls |
| Companion evidence | `contracts/pr06-gdpval-characterization-fixtures.md` |
| Bounded implementation appendix | `contracts/pr06-gdpval-implementation-task-appendix.md` |
| Next action | Substitute the accepted PR05 stack commit in the bounded appendix, then hand that frozen task to Luna |

## Baseline source map

The source was read from the exact baseline above. Git blob IDs identify the reviewed bytes.

| Source | Blob | Observed responsibility | PR06 disposition |
|---|---|---|---|
| `resources_servers/gdpval/app.py` | `25edad0f2f11adff3d480f996a645a2161c072b1` | Rubric/comparison routing, reference-repeat expansion, result aggregation | Replace server/path routing with a common-runner evaluator; preserve only explicitly versioned semantics |
| `resources_servers/gdpval/scoring.py` | `d8646f79482e7775e8f3aba3558479656bf881ba` | Binary, visual, and tagged structured rubric scoring | Extract prompt construction and valid score math as pure logic; judge transport belongs to the shared runtime |
| `resources_servers/gdpval/comparison.py` | `5bb7dbcce2096bcfb5b8669dc730fac727e558f6` | Presentation blocks, legacy verdict parser, reversal, votes, ELO helpers | Reuse valid tally meaning; use the existing strict parser/staging layer; keep AA/ELO out of PR06 |
| `resources_servers/gdpval/judge_panel.py` | `b46a7d893a4974c4172bf5d39097938aed0af63f` | Stable RNG, weighted sampling, AV detection/routing | Extract deterministic selection; replace incapable AV fallback with preflight failure |
| `resources_servers/gdpval/preconvert.py` | `6b88b4197164dc76af3b24028a3a864b6c4bd94` | Recursive Office-to-PDF derivation | Run only in fresh presentation storage; preserve source bytes and record derivation identity |
| `resources_servers/gdpval/prompts/judge_prompt.j2` | `0285b21e5fb8f0930037d805715fcb6eedd67cb6` | Binary rubric prompt | Copy/version as a hash-bound evaluator asset |
| `responses_api_agents/stirrup_agent/file_reader.py` | `892854920e45b8c8bba23a3e6a81745b88384193` | Text extraction and visual blocks | Treat as behavior evidence; replace mutation-prone Office conversion with a pure presenter |
| `eval_harness/judges/pairwise.py` | `290fef2944b7d7e3de2671981600d1154c8f83fd` | Strict standalone verdict parser, normalization, anonymous staging, aggregation | Reuse its pure protocol and hardening; adapt inputs to verified bundles and one bound view |
| `eval_harness/evaluators/pairwise.py` | `fba665b0ae0b394ffc7a815c7bffc772460476e5` | Exactly-two validation and fail-fast injected-judge loop | Reuse cardinality and coherence rules; replace one-judge/output shape with panel plan and durable records |
| `eval_harness/local_judge_runner.py` | `db6822eeb81674dd1952cdf4d7bebd172a3944a4` | Strict invalid handling and per-trial persistence | Behavior source only; fixed dataset paths and environment wiring are not reusable |
| `eval_harness/evaluators/gdpval.py` | `4314fc5c9901dc36bce0f045f12a2f9321c790bb` | External handoff bundle | Retire as GDPval completion path when common evaluation lands |
| `eval_harness/candidate_bundle.py` | `fdc93ec63392b7cad6a0750d454a54e3d3306d25` | Sealed, verified candidate artifacts and execution evidence | Consume the opaque verified bundle API; never project its provenance to the judge |
| `eval_harness/benchmarks/snapshot.py` | `cdcceed76b0c2d80b4afaf67295a0def306ce944` | Immutable task, execution, and evaluation views | Consume one verified bound evaluation view; never reconstruct evaluator inputs by path search |
| `eval_harness/judges/base.py`, `codex.py`, `claude_code.py` | `c8bdd1e790edaef3c0c4f1f028b09333fb5b38cd`, `758461713e08614cb2381506fed9470fde072ae6`, `32dd0de288fd47f12ee30e2e73009040fefc6969` | Judge request/result, subscription-auth checks, blind read confinement, and vendor CLI adapters | Put the guarded behavior behind the shared injectable runtime; reuse normal Executor transport only with an explicit blind-judge role that preserves the guards and probes |
| `eval_harness/executors/codex.py`, `claude_code.py` | `3c037656375cedf2d83f3f8604746f34952305b3`, `e1a6739a61dc11ff5e6f37b60023d3c466a0cfec` | Normal application executor lifecycles and vendor transport | Reuse lifecycle/transport where possible, but do not use their ordinary permission profiles for blind judging |

## Verified incompatibilities that require an explicit revision

These are observed legacy behaviors, not proposed compatibility behavior:

1. `comparison.parse_judgement` maps empty, malformed, lower-case, or otherwise missing verdicts to `BOXED[TIE]`; multiple verdicts use A-first substring precedence. `compute_comparison_reward` also maps every unrecognized winner to `0.5`.
2. Binary/visual rubric parsing can return a nonzero score recovered from truncated JSON while returning `judge_result=None`. Valid JSON without a recognized score becomes a valid-looking zero. Numeric scores are clamped after parsing.
3. Structured rubric trials silently skip invalid formatting. Exhausting every trial returns score `0.0` plus an error dictionary, which `app.py` marks `invalid_judge_response=False` because the dictionary is non-null.
4. A zero-trial pairwise configuration returns `BOXED[TIE]` with zero votes. A successful zero-vote reference repeat can therefore produce a neutral reward.
5. `select_av_judges` returns the full incapable panel when no judge advertises AV support.
6. Comparison Office preconversion writes derived PDFs beside evaluation and reference inputs. Stirrup visual conversion can create and then delete a same-stem PDF beside the original. Neither may run against sealed bundle/snapshot storage.

PR06 therefore introduces a new evaluator/protocol revision. Invalid or truncated responses have no vote and no score. Zero valid trials is a failed evaluation with `winner=null` and `score=null`, never a tie or neutral reward. AV content with no capable panel member fails preflight before any judge call. Original candidate and snapshot bytes remain unchanged.

### Mechanical migration versus revised semantics

| Behavior | Classification | Contract |
|---|---|---|
| Valid binary score-key precedence, finite numeric clamping, criteria-score mean fallback | Mechanical parity | Preserve and pin with fixtures |
| Valid structured weighted-total normalization and mean of eligible trials | Mechanical parity | Preserve and pin with fixtures |
| Explicit A/B reversal normalization; explicit tie counts as half only in aggregates that define it | Mechanical parity | Preserve and pin with fixtures |
| A-first four-trial GDPval position sequence and legacy weighted panel draw | Mechanical parity when selected | Expose as named, hash-bound policies and persist the resolved plan |
| CandidateBundle/BoundEvaluationView wiring, anonymous staging, shared runtime, result sink, immutable presentation | Mechanical architecture migration | Does not change valid score/vote meaning; every input/output digest becomes auditable |
| Root-deny blind-judge reads, environment/temp isolation, subscription-auth checks, and no-model confinement probes | Mechanical protection parity | Preserve behind the shared runtime; weakening these guards does not qualify as transport reuse |
| Malformed/multiple/missing pairwise verdict maps to invalid rather than tie | Algorithm change | `gdpval.pairwise@2` |
| Truncated/no-score/non-finite rubric response maps to invalid rather than numeric score | Algorithm change | `gdpval.rubric.binary@2` and visual equivalent |
| Boolean scores and duplicate JSON keys map to invalid rather than Python numeric coercion or last-key wins | Algorithm change | `gdpval.rubric.binary@2` and visual equivalent |
| All-invalid structured trials fail rather than return a valid-looking zero | Algorithm change | `gdpval.rubric.structured@2` |
| Non-positive/invalid structured denominator is rejected | Algorithm change | `gdpval.rubric.structured@2` |
| Awarded structured points outside `[0, parsed maximum]` are rejected instead of reaching the final clamp | Algorithm change | `gdpval.rubric.structured@2` |
| Non-positive trial count is rejected | Algorithm/config validation change | pairwise/rubric revision 2 |
| AV-capable member absent causes preflight failure rather than incapable fallback | Panel-selection behavior change | panel selector revision 2, included in evaluator config digest |
| Non-finite panel weights are rejected rather than bypassed, zeroed, or passed into `random.choices` | Panel/config validation change | panel selector revision 2, included in evaluator config digest |
| Unsupported/oversized required content fails instead of filename-only or omission-based judging | Presentation behavior change | presenter revision 2, included in evaluator config and judge-input digests |

Completion policy is reusable configuration, not duplicated evaluator logic. `require_complete` publishes a metric only for the exact requested completed set. `valid_only(min_valid=N)` may publish from completed records once its threshold is met, but returns status `partial` and explicit requested/valid/invalid/failed counts plus coverage. A GDPval partial uses the non-retryable task-impact summary failure `INVALID_RESPONSE/gdpval_partial_valid_trials`; precise parser codes remain on individual trial records. Runtime-failed or interrupted trials make the job ineligible rather than changing that summary's meaning. Invalid records never become votes. Policy ID and threshold enter the configuration digest; AA-v2 selects the generic policy in PR08.

## Proposed evaluator boundary

PR06 receives exactly one verified `BoundEvaluationView` and verified `CandidateBundle` values from the common runner. Rubric evaluation accepts exactly one candidate. Pairwise evaluation accepts exactly two distinct candidate identities; N-candidate expansion remains a planner responsibility.

The evaluator verifies the `BoundEvaluationView` once, then requires every bundle's `snapshot_reference` to equal the view's reference and every bundle's canonical task text/hash to equal the view's canonical task text/hash. CandidateBundles do not carry an evaluation-view hash; the verified view supplies that identity and its allowed assets. The evaluator projects only:

- `BoundEvaluationView.canonical_task_prompt`;
- allowed task inputs, anonymously staged as reference material;
- candidate outcome artifacts, anonymously staged as one submission or slots A/B; and
- the rubric asset for rubric mode.

It never projects candidate IDs, model/executor/condition/intervention metadata, effective prompts, bundle manifests, absolute source paths, or credentials. Candidate identities remain in controller-side records only.

`judge_input_sha256` is computed from a canonical manifest of the exact anonymous prompt asset/revision, canonical task text, allowed reference bytes/logical labels, anonymous submission bytes/logical labels, permitted rubric fields, and resolved presentation mode/derivations. It excludes candidate IDs and provenance, controller slot bindings, timestamps, run IDs, and runtime paths. The controller record separately binds that anonymous input digest to the logical candidate/slot map. Tests inspect prompt text, payload blocks, workspace names/content, argv, and environment to prove that no forbidden identity reaches the judge.

The shared judge runtime needs one narrow call: accept a hashable anonymous judge input plus a preselected judge-member spec and explicit role policy, and return typed preflight/process/transport status, raw response bytes/text, timestamps, exit code, and adapter metadata. PR06 owns parsing and score/vote semantics. PR05 owns invocation, cancellation, result-root freshness, the enforced runtime role, outer job attempts/result revisions, and the append-capable durable record sink. PR06 persists subtrial state only through PR05's opaque evaluator-event stream.

### Mode contracts

| Evaluator ID/revision | Candidates | Evaluation-only inputs | Completed output |
|---|---:|---|---|
| `gdpval.rubric.binary@2` | exactly 1 | required rubric JSON/pretty representation from `BoundEvaluationView.evaluation_data`; optional allowed task inputs | one finite metric in `[0,1]`, completed trial record, coverage 1 |
| `gdpval.rubric.structured@2` | exactly 1 | required rubric with a finite positive total or an explicit validated maximum; optional allowed task inputs | configured eligible-trial mean divided by the validated maximum, trial/attempt records, coverage |
| `gdpval.pairwise@2` | exactly 2 | canonical task plus allowed task inputs; rubric is not exposed unless a future separately identified evaluator explicitly requires it | logical win/loss/tie counts and winner/score only when completion policy is satisfied, BattleRecords, coverage |

The GDPval evaluator-internal defaults are explicit: binary rubric has one trial and one attempt per trial; structured rubric has two trials with three attempts per trial and `valid_only(min_valid=1)` to preserve the legacy eligible-score mean while exposing partial coverage; pairwise has four trials, one attempt per trial, `alternating-a-first-v1`, and `require_complete`. Every profile separately supplies one explicit PR05 `EvaluationResumePolicy`; there is no hidden job-resume default. Its complete canonical payload/digest enters the evaluator configuration digest, and its positive `max_attempts_per_job` is independent of the positive PR06 trial and per-trial attempt counts. A profile may override supported values, and every override changes the evaluator configuration digest.

Candidate outcomes must be successful sealed outcomes (`completed` or the accepted `no_deliverable` success state) and expose the channels required by the chosen presenter. Empty deliverables remain an explicit anonymous empty submission; a missing, failed, unverified, or modified bundle is a plan failure rather than an implicit loss. Candidate IDs must differ. Identical artifact bytes from two distinct candidates are allowed.

Rubric results publish the named `rubric_score` metric only when the configured completion policy permits it, plus raw-point/maximum/trial coverage in outcomes/details. Pairwise results publish candidate-keyed win counts, explicit tie count, requested/valid/invalid/failed counts, coverage, and an optional winner candidate ID in outcomes. The generic pairwise evaluator emits no implicit Elo and no orientation-dependent universal reward. A profile aggregate may derive a focal-candidate rate or Elo from the completed BattleRecord set under its own named rules.

All task/snapshot/view/cardinality/capability/presentation validation and the full position/member plan complete before the first judge call. Any failure at this phase produces no trial intent, no score, and a typed preflight failure. The common runner must not expand an N-candidate set inside the evaluator; `MatchPlanner` supplies one- or two-candidate evaluation jobs as appropriate.

### Frozen interfaces required from PR05

The coordinated PR05 contract at design commit `01f781cbeaff00aee3fb0bea3597dee3bd58e2df` (contract blob `837a4eb58802f0c151360d8bfbe014eb281d126f`) provides these capabilities without acquiring GDPval-specific logic. PR06 implementation still waits for the coordinator to identify the accepted immutable PR05 implementation head:

1. **Evaluation job and planning.** `eval_harness.evaluation_runner` owns strict `JSONValue`, `LogicalCandidateReference`, `EvaluationPlanRequest`, `EvaluationJob`, `EvaluationJobRequest`, `EvaluationFailure`, `EvaluationResumePolicy`, `EvaluationMetricAggregate`, `EvaluationAggregateRequest`, `EvaluationAggregate`, the sole `build_evaluation_job` identity constructor, and `plan_evaluation_job`. PR06's evaluator produces the opaque fully resolved `evaluator_plan`; PR05 verifies the view/bundles and owns evaluation-input/job identity hashing. Each GDPval evaluator exposes its explicit config-bound `resume_policy`. The generic `FailureKind.INVALID_RESPONSE` is task-local and retains a precise parser code plus the one `EvaluationFailure.retryable` policy bit; runtime/envelope `PROTOCOL` remains systemic.
2. **Injectable judge runtime.** `Evaluator.judge_runtime_preflight_requests(view)` lets the common runner preflight configured judge members before generation or evaluation. PR06 returns every member that could be selected and requires every returned request to pass; it neither drops a failed member nor renormalizes the panel. `eval_harness.judge_runtime.JudgeRuntime.preflight(JudgeRuntimePreflightRequest)` and `.invoke(JudgeInvocationRequest)` execute one sanitized anonymous invocation under `BlindJudgePolicy`. The invocation binds the selected `JudgeRuntimeMember`, prompt, fresh anonymous workspace, and ordered hash-verified `JudgeContentBlock` metadata so local and HTTP transports consume the same exact presented bytes. `JudgeInvocationResult` is terminal `completed`, `failed`, or `interrupted`; GDPval owns parser-level `invalid_response`. The runtime does not parse scores/verdicts, choose panel members, reverse candidates, or aggregate.
3. **Durable evaluation record sink.** `eval_harness.evaluation_records` owns `EvaluationRecordSink`, its exact `create(result_root, *, resume_policy)` and `resume(...)` constructors, outer attempt records, immutable `EvaluationResultRevision` values, `EvaluationJobRecord`, `EvaluationEvidenceReference`, and opaque `EvaluatorEvent`. The common dispatcher calls `.save_plan`, `.append_attempt_started`, `.append_attempt_terminal`, `.append_result`, and `.load_job`; PR06 calls only `.append_evaluator_event` and `.load_evaluator_events` for trial/BattleRecord state. A plan exists before the first event, every append flushes and fsyncs, and load revalidates the one per-job event hash chain plus every evidence byte. Completed/eligible-partial results never replay; other outer states resume only under the exact stored policy. Semantic result digests remain separate from outer revision, runtime evidence, and evaluator-event history. PR06 creates no private filesystem journal.

The preferred local judge adapter reuses the normal Executor lifecycle and vendor transport with a sanitized judge `TaskSpec`/`ExecutionRequest`: opaque trial identity, blind prompt, anonymous materialized workspace, no Intervention, and an explicit blind-judge role configuration. This reuse is permitted only when that role enforces and proves the isolation contract below. The baseline ordinary `CodexExecutor` `workspace-write` profile permits a broader read surface and is insufficient unchanged. If the normal Executor abstraction cannot express the required role, retain one refactored guarded judge runtime that shares vendor transport rather than weakening isolation or creating a second transport stack. A transport adapter may satisfy the same runtime interface for structured multimodal payloads. Neither path may invoke `eval_harness/local_judge_runner.py`, the GDPval resources server, benchmark dataset discovery, fixed `GDPVAL_*` paths, or a silent alternative runtime.

PR06 owns rubric/pairwise prompt assets, presentation, parsers, panel selection, resolved trial plans, BattleRecord semantic payloads, and protocol aggregates. PR05 owns generic invocation/cancellation/storage mechanics only. If PR05 cannot provide the three capabilities above, the interface delta must return to design review; PR06 must not embed a private common runner.

### Blind-judge runtime isolation contract

Anonymous filenames and prompts do not stop a local agent from reading other host paths. For a local CLI member, `blind-judge` therefore means all of the following:

- The model/tool process can read the anonymous presentation workspace and only the minimal command/runtime libraries needed to launch. Its filesystem policy starts with root deny. CandidateBundle roots, snapshot stores outside the staged view, other candidate/run roots, result/history directories, controller files, and credential/config homes remain unreadable. Runtime allowances that overlap a protected root are rejected.
- The anonymous workspace is read-only to the model/tool process. The host adapter may write raw output only to a fresh isolated evidence directory that is outside the model's readable tree. Network and web search are disabled for a local subscription judge.
- The host launcher receives only a reviewed runtime/auth allowlist. Candidate paths, candidate IDs/labels, condition/provenance fields, and unrelated parent secrets are absent. The model shell inherits no parent environment; its synthetic `HOME` is the anonymous workspace, `PATH` is the minimal system path, and `TMPDIR`/`TMP`/`TEMP` point to one fresh runtime directory disjoint from every bundle, snapshot, and output root.
- Preflight validates command/version, an explicitly permitted auth mode, required capabilities, and the applied sandbox role. Before any model call, a deterministic probe must prove that a file inside the anonymous workspace is readable and a sibling outside-secret file is unreadable. Missing, unsupported, unverifiable, or failed confinement is a typed preflight failure with zero judge calls.
- Evidence records the adapter/runtime version, non-secret auth classification, role-policy ID/revision/digest, probe ID/result, network policy, environment-policy ID, and temp-root relationship. It records no credential contents or unrestricted environment dump.

At the baseline, `CodexJudgeExecutor` supplies a `gdpval-harness-blind-judge` permission profile with root deny, minimal/runtime reads, workspace read, and network disabled; it rejects API/access-token or unidentified login and runs a no-model `codex sandbox` read probe. Its judge command is ephemeral, ignores user config, forces ChatGPT subscription auth, disables web search and approvals, forbids a login shell, and gives the model shell an `inherit="none"` environment. These behaviors are protection parity requirements, although the GDPval-prefixed role name must become neutral.

`ClaudeCodeJudgeExecutor` recognizes only logged-in first-party `claude.ai` Pro/Max/Team/Enterprise subscription status and rejects Console/API, OAuth-token, gateway, Bedrock, Vertex, and Foundry modes. Its intended policy denies read/write at root, allows read of the anonymous workspace, uses an empty strict network allowlist, fails if sandboxing is unavailable, permits only sandboxed Bash, and disables Read/Edit/Write/WebFetch/WebSearch/MCP tools. It nevertheless fails preflight today because no documented no-model probe proves that configuration. PR06 must preserve that fail-closed result until a tested probe or stronger independently verified isolation primitive exists; a settings declaration alone is not evidence.

An HTTP/structured-payload judge uses a separate explicit transport policy: the adapter sends only the hash-bound anonymous payload to the configured endpoint, holds credentials outside the payload, and records the endpoint/provider policy identity without secrets. Local-filesystem permission claims do not transfer to that transport, and it cannot be a silent fallback for a failed local member.

## Pairwise plan and BattleRecord minimum contract

The semantic plan contains exactly `num_trials` entries and must be completely resolved before the first call. Each entry supplies `trial_index`, explicit slot-A and slot-B bundle assignments, and a preselected judge-member ID/spec hash. Attempt numbers belong to execution history, not this plan. Position policy is evaluator configuration: GDPval legacy parity is A-first alternating (`A/B`, `B/A`, ...); seeded initial reversal remains available only under its own named policy ID. A hidden seed-derived first swap is forbidden because AA-v2 must persist an explicit legacy order.

Panel planning filters capabilities before selection, applies the named deterministic weight policy, and freezes the selected member for each trial. A retry invokes that same member; it never silently substitutes another panel member, provider, model, or reasoning setting. Zero/negative effective weights retain the characterized selector behavior (non-positive becomes zero; an all-zero panel samples uniformly), while non-finite weights, duplicate member IDs, or missing member specs fail configuration validation. Panel/member order, sanitized specs, weights, capabilities, selection-policy ID/input, and resolved draws are content-hashed; credentials are excluded.

`evaluation_input_sha256` is content-addressed from the task/evaluation-view identity, evaluator ID/revision/config hash, and the ordered logical pair of candidate IDs plus bundle SHA-256 values. It identifies identical evaluation content independently of scheduling. `evaluation_job_id` additionally binds an opaque, deterministic planner-supplied `match_occurrence_id`. Trial identity is the job ID plus trial index. Thus repeated occurrences can share CandidateBundles and the same input digest while still requiring separate judge calls and records. Stage, anchor role, Elo, and headline fields remain absent from the generic schema; PR08 derives its opaque occurrence identity from the resolved profile/stage/task-repeat/anchor-repeat plan.

These cross-PR field spellings are fixed by this contract so PR05, PR06, and PR08 can share records without translation:

| Python/JSON spelling | Contract meaning |
|---|---|
| `match_occurrence_id` | opaque deterministic planner identity for one scheduled occurrence; its internal AA-v2 dimensions remain outside the generic schema |
| `evaluation_input_sha256` | digest of reusable evaluation content/configuration, including the ordered logical candidates and bundle hashes, but excluding occurrence |
| `evaluation_job_id` | digest-bound job identity over schema/domain, `evaluation_input_sha256`, and `match_occurrence_id` |
| `battle_record_id` | stable trial identity over schema/domain, `evaluation_job_id`, and `trial_index`; unchanged across attempts |
| `battle_status` | current logical state: `planned`, `running`, `completed`, `failed`, `interrupted`, or `invalid_response`; `partial` exists only at aggregate `EvaluationResult` level |
| `battle_semantic_sha256` | digest of the immutable plan entry plus canonical completed result; present only when `battle_status=completed` |
| `attempt_id`, `attempt_number` | identity and positive ordinal of one invocation attempt for the stable battle record |
| `attempt_event_sha256` | digest of one append-only attempt event/evidence object, including its runtime evidence references |
| `attempt_history_sha256` | digest of the canonical ordered attempt-event chain; it changes when an interrupted/failed battle is retried and is excluded from `battle_semantic_sha256` |

Any later spelling change is a coordinated schema revision across those PRs, not an adapter-local alias. `invalid_response` is never serialized as `tie`; `failed` denotes runtime/transport/policy failure rather than parser invalidity.

Each planned trial has a durable `BattleRecord` identity derived from `evaluation_job_id` and trial index, plus an immutable semantic plan entry. A completed trial adds this stable semantic result payload:

- schema version, `battle_record_id`, `evaluation_job_id`, `evaluation_input_sha256`, `match_occurrence_id`, and `trial_index`;
- task, snapshot, canonical-prompt, evaluation-view, evaluator-config, panel, presentation, and judge-input hashes;
- logical candidate identities and bundle hashes plus explicit presented slot A/B assignments;
- judge-member ID/spec hash;
- completed status, strict blind verdict, normalized winner candidate ID or explicit tie, and a canonical parsed-result hash.

Its `battle_semantic_sha256` is computed only from the immutable plan entry and completed canonical result payload. It excludes attempt number, timestamps, run ID, run-local/absolute paths, raw reasoning text, exit-log locations, and earlier interrupted/failed attempts. An interrupted run followed by a retry that produces the same parsed result therefore has the same semantic record digest as an uninterrupted run. A trial whose current terminal state is `invalid_response`, `failed`, or `interrupted` remains a durable BattleRecord with no semantic result digest.

Invocation history is a separate append-only evidence stream encoded as PR05 `EvaluatorEvent` objects. Exact GDPval event types are `gdpval.battle-attempt-started.v1`, `gdpval.battle-attempt-terminal.v1`, and `gdpval.battle-record-reused.v1`; their opaque payloads carry the versioned battle/attempt identity, contiguous per-battle event sequence, lifecycle state, timestamps, typed failure/retryability, and a completed semantic digest only when eligible. Runtime/version/auth provenance, exit code, and raw stdout/stderr/response remain linked `EvaluationEvidenceReference` objects. The shared `event_sha256` is the GDPval `attempt_event_sha256` projection for start/terminal events; `attempt_history_sha256` binds the ordered exact shared event digests for that battle. A completed event links to the stable BattleRecord semantic digest. `invalid_response`, `failed`, and `interrupted` events have no semantic result payload/digest, verdict, normalized winner, or vote. Reuse is recorded only after complete evidence revalidation and makes no judge call.

The common runner saves the plan and outer attempt intent before invoking PR06. The evaluator records each trial intent before its judge call and its terminal event immediately afterward. Planned/running work without a terminal event is unresolved, retained as attempt history, closed as interrupted on explicit resume, and retried only as a new positive per-trial attempt within the configured bound. Reuse requires the same planned occurrence ID, a completed semantic record, and exact integrity revalidation of snapshot/evaluation view, both CandidateBundles, evaluator/config, panel/member, presented slots, judge input, canonical parsed result, and every linked evidence object. Identical input content in another planned occurrence is not reusable as a completed battle; it receives new calls and records. PR08 may aggregate a sorted exact set of completed semantic record IDs/digests even when retry histories differ. Invalid/failed/interrupted attempt records never enter vote totals.

## Rubric trial status

Binary and structured modes use the same durable trial-status rule and the same semantic/evidence split. A completed rubric record has a finite parsed score, validated denominator where applicable, normalized score, judge/input hashes, and canonical result hash. Binary finite numeric values retain the legacy `[0,1]` clamp; malformed JSON, truncated JSON, missing score sources, float conversion failure, and non-finite values produce `invalid_response` and no score. Structured invalid tags, a maximum outside the legacy inclusive absolute tolerance `0.01`, a non-positive/non-finite maximum, or awarded points outside `[0, parsed maximum]` do the same. The aggregate preserves the first valid trial's parsed maximum as its denominator. Formatting retries are attempt history for one planned trial and remain auditable. A supported partial-trial policy is named configuration with a distinct digest and explicit coverage; it does not require duplicated mechanism or a new code revision for every threshold.

Binary parsing accepts one JSON object with unique keys, optionally inside one complete code fence, and preserves the characterized key precedence and criteria fallback. Additional non-whitespace payload, incomplete/multiple fences, a non-object root, duplicate keys, a boolean score, or ambiguous score conversion is invalid. Structured parsing requires exactly one final-score tag and exactly one maximum tag in the required final result form; duplicate/conflicting top-level tags are invalid rather than first-match wins. The rubric/prompt canonical bytes and parser revision are evaluator assets and enter the config digest.

## Evaluation status and failure contract

The coordinated PR05 `EvaluationResult` has these unambiguous terminal meanings for GDPval:

| State | Metric allowed | Meaning |
|---|---|---|
| `completed` | yes | Completion policy is fully satisfied; every counted trial has a completed semantic record |
| `partial` | only when the configured `valid_only` policy threshold is satisfied | At least one planned trial is parser-invalid, no trial is runtime-failed/interrupted, and counts/coverage are explicit |
| `failed` | no | Preflight, presentation, capability, parser/coverage, or judge failures prevent an eligible result |
| `interrupted` | no | Stop/cancellation left no final eligible result; durable prefix and attempt history remain |

Failure payloads carry a stable `kind`, code, exact `FailureImpact.TASK` or `FailureImpact.RUN`, and retryability. Missing/modified inputs, cardinality/coherence violations, unsupported rubric, and capability/presentation insufficiency are deterministic task-impact job failures and make zero judge calls. Invalid response is an attempt outcome, never a tie or score. Auth/quota/runtime protocol failure with run impact stops remaining tasks; a normal completed judge verdict or rubric score does not. An all-judge/all-trial failure yields `failed`, winner/score `null`, valid count zero, and full attempt evidence. Aggregators consume only eligible completed semantic records and must not infer a zero, loss, tie, or denominator exclusion from failure status.

## Presentation contract

All presentation work runs in a fresh disposable directory materialized from verified inputs. Source logical paths and SHA-256 values are recorded before presentation and rechecked afterward. Derived PDFs/content blocks carry source hash, derived hash, converter identity/version, and status. Runtime absolute paths are excluded from semantic hashes. Archives require traversal-safe extraction and preserve member-relative paths; basename flattening is forbidden. Unsupported, oversized, or failed required material causes typed presentation/preflight failure rather than filename-only judging.

Task-input, grader-asset, and candidate-artifact roles remain distinct in the presenter manifest. Pairwise sees allowed task inputs and two anonymous candidate artifact trees. Rubric sees allowed task inputs, one anonymous candidate artifact tree/output text, and only the rubric fields its evaluator consumes. The selected judge member must advertise every modality required by the resolved presentation. In particular, audio/video detection includes nested manifest paths and safely inspected supported archives; an AV judge must also receive the actual media payload or filesystem file, not merely be selected by name.

Presentation mode and source policy are explicit and hash-bound (`extracted-text`, rendered/multimodal blocks, or anonymous filesystem). Rubric's artifact-preferred rule may use final output text only when no required artifact representation exists; it may not hide a conversion/read failure by silently substituting the executor's summary. Pairwise presents candidate artifact trees and represents an empty successful artifact set explicitly; it does not substitute executor output text or finish metadata. The current automatic text/visual choice is therefore resolved during preflight and captured in the plan rather than inferred differently during retries.

## Implementation extraction boundary

| Layer | PR06 action |
|---|---|
| Strict verdict parse/normalize and anonymous copy hardening | Reuse/refactor the pure logic in `eval_harness/judges/pairwise.py`; replace candidate-directory reference discovery with one bound-view materialization |
| Binary and structured rubric prompt/valid score math | Extract from `resources_servers/gdpval/scoring.py` with retained NVIDIA SPDX; isolate pure construction/parsing from any OpenAI client or retry loop |
| Weighted panel selection and AV detection | Extract from `judge_panel.py` into reusable typed panel/plan logic; revision/hash the selector and fail closed on missing capability |
| Artifact presentation and Office conversion | Reimplement around verified manifests and a fresh derived root, borrowing file-type/rendition semantics from `file_reader.py`, `preconvert.py`, and `comparison.py` without their source-tree mutation or unsafe archive assumptions |
| BattleRecord semantic payload and trial aggregation | Add reusable generic records/pure folds owned by PR06; exclude stage/anchor/Elo fields |
| Judge process/transport, blind-role isolation, outer resume/result revisions, and durable event storage | Consume the exact PR05 interfaces; persist subtrials only through its opaque event stream, port the existing protection behavior/tests, and do not copy transport/retry/storage loops into evaluator code |
| AA-v2 reference binding, stage plan, draw inputs, completeness set, and Elo | Leave entirely to PR08; PR08 supplies explicit slots/member IDs and consumes completed BattleRecord semantic digests |
| Old GDPval resources server, external handoff, and local judge runner | Keep as characterization sources until their scheduled removal; the new path must not call them |

Expected new implementation scope is the GDPval rubric/pairwise evaluators, prompt assets, a safe presenter, reusable panel/BattleRecord pure modules, evaluator registration/integration against accepted PR05 APIs, and focused unit/integration fixtures. Changes to the common runner are limited to the previously reviewed generic interface delta. No production implementation was created on this design branch.

This remains one logical PR06 because its evaluator revision, judge projection, presentation digest, and durable trial result must be reviewed together. If implementation size requires a physical split, `06a` may land pure presenter/parser/panel/record types and fixtures, followed by `06b` common-runner integration. Both inherit this complete acceptance set; the split cannot defer failure handling or leave external handoff as the completed path.

## Completion gates

- Fake-judge tests cover exact one-candidate rubric and exactly-two pairwise cardinality, snapshot/task/view coherence, anonymous projection, A-first reversal, optional explicitly seeded position policy, configured trial count, deterministic panel draw plan, strict verdict parsing, and vote normalization.
- Fixture tests pin valid binary and structured rubric math plus invalid/truncated/no-score/max-mismatch behavior under the new revision.
- Failure tests prove all-judge failure, zero trials, partial trials, AV capability insufficiency, interruption, and invalid responses cannot produce a successful score or tie.
- Presentation tests hash all source bytes before/after Office and archive handling and prove identical bytes, safe member paths, deterministic output hashes, and typed failures.
- Blind-runtime tests port every assertion in `tests/harness/test_local_judge_isolation.py`, inspect the actual role-policy argv/settings/environment, and use a no-model subprocess probe to prove workspace-read/outside-deny. They also prove the ordinary `workspace-write` Executor profile is rejected for the judge role, protected runtime allowances fail preflight, the model shell receives no parent secrets or provenance, temp/output roots are disjoint, network is disabled, unsupported auth fails, and Claude remains unavailable while confinement is not probe-verifiable.
- Durability tests prove exact resume-policy binding, common plan/outer-attempt ordering, evaluator-event intent-before-call and terminal-after-call, fsynced reloadable trial prefixes, complete-hash reuse, no replay of completed/eligible-partial results, refusal to count incomplete records, and equal semantic digests after an interrupted retry that reaches the same parsed result despite different result revisions/history/evidence digests.
- Integration tests use fake judge adapters only and prove the common runner returns a normal `EvaluationResult`; no external handoff counts as completion.
- The exact current outputs and required revised outputs in `contracts/pr06-gdpval-characterization-fixtures.md` become automated fixture oracles. No test invokes a real model, paid API, subscription quota, the legacy resources server, or the old local judge runner as a fallback.
