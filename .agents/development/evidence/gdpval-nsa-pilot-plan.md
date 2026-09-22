<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Three-task N/S/A exploratory trial — 2026-09-22

## Authority and scope

The owner explicitly commissions this small comparison, relayed from task
`01a0c290-ff84-71e1-a873-3d614f4cc139`. This authorizes the finite29-session envelope below, separately from exhausted
acceptance envelopes. It does not authorize a220-task production experiment, merge, extra billing, API fallback,
quota resets, model substitution or auxiliary AI. The main task owns execution, analysis, visualization and PR records.

Baseline: `e1d5cf0914157366848278ba02de4578e122c3dd`. Control-development governs orchestration. The controller owns
selection, brief, frozen configurations, all real model dispatch and final reporting; one worker prepares a once-only
runner, and one specialist checks only selected-task prerequisites. No nested delegation.

## Population and random draw

Freeze the191 `common_routes_applicable_with_limits` IDs from ledger SHA256
`e5c0430b3917feb6599f7c5c8edf7f73ad192a097490cdf2118fab83ff8cbf86` in sorted-ID order. Uniform sampling without
replacement uses CPython3.13.14 `random.Random(int(seed_hex,16)).sample(population,3)`, with a single256-bit OS-random seed.
The pre-outcome seed, algorithm, complete population and hashes are saved in `.audit/2026-09-22-nsa-pilot/draw.json`
and `population.json`. Population SHA256: `1394d137782a142c8443c97dba0eada50cc8b956142aec1e2c316e6f2113258d`.

Selected draw order:

1. `8079e27d-b6f3-4f75-a9b5-db27903c798d` — historical S&P500 valuation workbook.
2. `ce864f41-8584-49ba-b24f-9c9104b47bf0` — employee workload and March budget tracker.
3. `11593a50-734d-4449-b5b4-f8986a133fd8` — eligible-home summary and map PDFs.

No replacement for difficulty, prerequisite failures or outcomes.191 means applicable common routes with limits,
not fully accepted tasks. Historical market-source availability and original housing prompt/rubric conflicts remain
explicit uncertainties. Only affected actions or judgments are blocked. Participants perform their own additional research.
Original prompts, supplied bytes, rubric descriptions, IDs and signed weights remain unchanged.

## Intervention and execution

N receives no added Skill. S receives one Skill created using the selected skill-creator. A receives one Skill created
using the same creator, skill-creator, generic brief and inputs, plus the two selected ALPS Skills. Reuse each frozen
created Skill across all3tasks: `creation_repeats=1`, `repeats=1`, matched Skills, one cohort. The common brief was
written before viewing the drawn task contents; it covers professional deliverable work generally and includes no
sample task, solution, gold answer, rubric or result. Freeze the complete selected Skill resources and generated outputs.

| Stage | Model / effort | Count | Per-session bound |
| --- | --- | ---: | --- |
| Creator S then A | Claude `claude-opus-5` / medium | 2 | 600s, max_turns24 |
| Applications | Codex `gpt-5.6-sol` / medium | 9 | 900s |
| Scalar judges | Codex `gpt-5.6-sol` / medium and Claude `claude-opus-5` / medium | 18 | 1200s, Claude max_turns40 |

Total29sessions; serial1; automatic retries0; existing subscriptions only. Sum of model/tool timeout limits30,900s
(8h35m), not a duration forecast. Setup, verification, controller/human work and quota waiting are separate.
A started failure, timeout or limit error consumes its slot. Persist an exclusive start marker before every model
request; never use built-in resume to repeat a consumed slot. Authentication/model/environment checks precede dispatch.
If a client hits its quota, stop that client's unstarted slots, preserve resume state and only continue independent
work for which the other authorized client and required saved inputs remain available. No silent sample reduction.

Order is fixed before outputs: creator S,A; applications condition-major N,S,A and within each the draw order above;
judges follow the same artifact order, Codex then Claude for each. This is not randomized interleaving. Separate
per-slot canonical run/evaluation records may implement the matched design if necessary for strict once-only dispatch;
the shared immutable Skill/cohort and equal settings must be verified explicitly. No undeclared panel/pairwise calls.

The selected-task review verifies all5 supplied files and108 original rubric units. Fourteen housing units have
demonstrated source/count/format contradictions and are frozen as unconfirmed in evaluator-only procedures; other
units retain original conditions and alternatives. The housing prompt also expressly requires participant research
(e.g. MLSLI.com), despite the older coarse ledger external-data flag. No listings, pictures or coordinates are prefetched.

The existing scalar API does not judge partial artifacts when the participant execution failed or timed out. Such
artifacts and logs are preserved; their planned judge slots remain unstarted with the explicit source-status blocker,
all original quality items remain unknown, and time/usage and planned denominators remain visible. Do not relabel a
failed source run as completed or silently remove it to enable grading. This limitation is fixed before outcomes.

All application conditions share tools, dependencies, permissions, task inputs, timeout and environment fingerprint.
Judges receive anonymous submissions and evaluator-only task/rubric/protocol context; no condition/creator labels,
Skills, other submissions or other judges' results. Inspection uses copies without repairing missing mechanisms or
changing calculation/refresh settings to create a pass. Unassigned human observations remain unconfirmed.

## Predeclared aggregation and interpretation

Report each judge separately. Display execution completion and evaluation completion separately from quality.
For each original criterion, retain reported and evidence-validated pass/fail/unconfirmed and any controller qualification.
Never equate unknown with pass or zero. Preserve the full planned denominators3tasks×3conditions×2judges.

The primary quality presentation is original-item status and coverage. A descriptive signed-weight score is secondary,
custom, and not claimed equivalent to official GDPval scoring. For original weight `w_i` and criterion truth score
`s_i` in[0,1], complete score is `100 * sum(w_i*s_i) / sum(max(w_i,0))`; a negative predicate retains its negative
weight. Do not clamp negative values. If any item is unknown, the point score is null. Show a possible range by giving
each unknown positive-weight term[0,w_i] and negative-weight term[w_i,0], using the same fixed positive denominator.
This is an uncertainty interval, not a confidence interval or imputed result. Keep raw signed totals and sidecars.

Count coverage is confirmed items/all original items; weighted coverage is confirmed absolute weight/all absolute
weight. Show two-judge agreement only over their commonly confirmed items, together with that overlap denominator
and all unknowns. Across tasks, use equal-task summaries only where defined; missing task scores leave the planned
aggregate point score null, with ranges/counts retained. No significance or general ALPS-superiority claim from3tasks,
one Skill per creator condition and one execution per task/condition.

Record creation, application and judgment time/usage separately, including failures. Cache counts are subsets where
reported, not extra tokens to add. Subscription cost unavailable means null; provider price estimates are not actual
incremental spend. Report both total and any explicitly labeled per-three-use creation amortization.

## Handoff

Produce a clear interactive local report showing all three tasks and N/S/A, each artifact, the complete actual S/A
Skills and supporting files, judged quality/unknowns/time/usage, and concrete differences. Trace Skill instructions to
observed logged actions and artifact evidence; include ignored instructions, wasted work, adverse effects and failures.
Do not infer private reasoning or causation from one sample. Preserve configuration, random draw, source hashes,
logs, partial/unstarted slots and safe continuation instructions. Update existing PR53 as appropriate; no merge.
