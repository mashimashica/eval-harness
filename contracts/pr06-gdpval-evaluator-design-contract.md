<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR06 GDPval evaluator design contract

> Checkpoint status (2026-09-13): saved design draft, not accepted implementation or migration state. This document records verified baseline behavior and the proposed PR06 boundary while characterization fixtures are completed.

## Checkpoint identity

| Field | Value |
|---|---|
| Design owner | Sol (`/root/sol_gdpval_semantics`) |
| Control parent | `8518f25d107d9043df449a9198fbb41b00ba1c22` |
| Source baseline | `d5ce0c10162cad788a17cb90f34b8f60574e7f75` (tree `354943ebbb8ea81a30523bfdc12baf26771853b5`) |
| Canonical plan | `eval-harness-neutrality-migration-plan-2026-09-12.md`, 33,790 bytes, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f` |
| Scope | Design and deterministic characterization only; no production edits and no live model calls |
| Next action | Complete exact fixture matrix, finalize interfaces and gates, then append a descendant checkpoint commit |

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

## Verified incompatibilities that require an explicit revision

These are observed legacy behaviors, not proposed compatibility behavior:

1. `comparison.parse_judgement` maps empty, malformed, lower-case, or otherwise missing verdicts to `BOXED[TIE]`; multiple verdicts use A-first substring precedence. `compute_comparison_reward` also maps every unrecognized winner to `0.5`.
2. Binary/visual rubric parsing can return a nonzero score recovered from truncated JSON while returning `judge_result=None`. Valid JSON without a recognized score becomes a valid-looking zero. Numeric scores are clamped after parsing.
3. Structured rubric trials silently skip invalid formatting. Exhausting every trial returns score `0.0` plus an error dictionary, which `app.py` marks `invalid_judge_response=False` because the dictionary is non-null.
4. A zero-trial pairwise configuration returns `BOXED[TIE]` with zero votes. A successful zero-vote reference repeat can therefore produce a neutral reward.
5. `select_av_judges` returns the full incapable panel when no judge advertises AV support.
6. Comparison Office preconversion writes derived PDFs beside evaluation and reference inputs. Stirrup visual conversion can create and then delete a same-stem PDF beside the original. Neither may run against sealed bundle/snapshot storage.

PR06 therefore introduces a new evaluator/protocol revision. Invalid or truncated responses have no vote and no score. Zero valid trials is a failed evaluation with `winner=null` and `score=null`, never a tie or neutral reward. AV content with no capable panel member fails preflight before any judge call. Original candidate and snapshot bytes remain unchanged.

## Proposed evaluator boundary

PR06 receives exactly one verified `BoundEvaluationView` and verified `CandidateBundle` values from the common runner. Rubric evaluation accepts exactly one candidate. Pairwise evaluation accepts exactly two distinct candidate identities; N-candidate expansion remains a planner responsibility.

The evaluator verifies that every bundle binds the same snapshot, task, canonical-task hash, and evaluation-view hash. It projects only:

- `BoundEvaluationView.canonical_task_prompt`;
- allowed task inputs, anonymously staged as reference material;
- candidate outcome artifacts, anonymously staged as one submission or slots A/B; and
- the rubric asset for rubric mode.

It never projects candidate IDs, model/executor/condition/intervention metadata, effective prompts, bundle manifests, absolute source paths, or credentials. Candidate identities remain in controller-side records only.

The shared judge runtime needs one narrow call: accept a hashable anonymous judge input plus a preselected judge-member spec, and return typed process/transport status, raw response bytes/text, timestamps, exit code, and adapter metadata. PR06 owns parsing and score/vote semantics. PR05 owns invocation, cancellation, result-root freshness, and an append-capable durable record sink.

## Pairwise plan and BattleRecord minimum contract

The plan contains exactly `num_trials` entries and must be completely resolved before the first call. Each entry supplies `trial_index`, `attempt`, explicit slot-A and slot-B bundle assignments, and a preselected judge-member ID/spec hash. Position policy is evaluator configuration: GDPval legacy parity is A-first alternating (`A/B`, `B/A`, ...); seeded initial reversal remains available only under its own named revision. A hidden seed-derived first swap is forbidden because AA-v2 must persist an explicit legacy order.

`evaluation_job_id` is content-addressed from profile-independent task/evaluation-view identity, evaluator ID/revision/config hash, and the ordered logical pair of candidate IDs plus bundle SHA-256 values. Stage, anchor role, Elo, and headline fields are excluded, allowing PR08 to reuse an identical matchup across stages.

Each durable terminal `BattleRecord` includes:

- schema version, record/trial ID, `evaluation_job_id`, trial index, and attempt;
- task, snapshot, canonical-prompt, evaluation-view, evaluator-config, panel, presentation, and judge-input hashes;
- logical candidate identities and bundle hashes plus explicit presented slot A/B assignments;
- judge-member ID/spec hash and runtime provenance;
- lifecycle status (`completed`, `invalid_response`, `judge_failed`, or `interrupted`), typed failure code/retryability, and response/result hashes;
- blind verdict for completed trials, normalized winner candidate ID or explicit tie, and no verdict/winner for every other status.

The durable sink records intent before invocation and a terminal event immediately afterward. Planned/running work without a terminal event is unresolved, retained as attempt history, and retried only as a new attempt. Reuse requires a completed record and exact equality of every bound semantic/content hash. Invalid/failed/interrupted records never enter vote totals.

## Rubric trial status

Binary and structured modes use the same durable trial-status rule. A completed rubric record has a finite parsed score, validated denominator/range, normalized score, judge/input hashes, and response/result hashes. Malformed JSON, truncated JSON, missing score fields, invalid tags, mismatched maximum, non-finite values, or out-of-range values produce `invalid_response` and no score. Formatting retries are attempts of one planned trial and remain auditable. Any policy that permits completion from fewer valid trials than requested must be a separately named evaluator revision; the strict PR06 default requires the configured valid-trial set.

## Presentation contract

All presentation work runs in a fresh disposable directory materialized from verified inputs. Source logical paths and SHA-256 values are recorded before presentation and rechecked afterward. Derived PDFs/content blocks carry source hash, derived hash, converter identity/version, and status. Runtime absolute paths are excluded from semantic hashes. Archives require traversal-safe extraction and preserve member-relative paths; basename flattening is forbidden. Unsupported, oversized, or failed required material causes typed presentation/preflight failure rather than filename-only judging.

## Completion gates (draft)

- Fake-judge tests cover exact one-candidate rubric and exactly-two pairwise cardinality, snapshot/task/view coherence, anonymous projection, A-first reversal, optional explicitly seeded position policy, configured trial count, deterministic panel draw plan, strict verdict parsing, and vote normalization.
- Fixture tests pin valid binary and structured rubric math plus invalid/truncated/no-score/max-mismatch behavior under the new revision.
- Failure tests prove all-judge failure, zero trials, partial trials, AV capability insufficiency, interruption, and invalid responses cannot produce a successful score or tie.
- Presentation tests hash all source bytes before/after Office and archive handling and prove identical bytes, safe member paths, deterministic output hashes, and typed failures.
- Durability tests prove intent-before-call, terminal-after-call, attempt history, complete-hash reuse, and refusal to count incomplete records.
- Integration tests use fake judge adapters only and prove the common runner returns a normal `EvaluationResult`; no external handoff counts as completion.

