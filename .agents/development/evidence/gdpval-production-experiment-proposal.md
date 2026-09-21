<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# GDPval N/S/A production experiment — decision proposal

**Draft only, 2026-09-22. No production run, model call, installation, permission change, quota reset, extra billing or merge is authorized by this document.** The current continuation authorizes separate acceptance work, not this experiment. Today's reported 15% weekly allowance is not a production budget.

## 1. Question and conditions

Estimate the effect of the Skill-creation method on artifact quality, execution time and usage, separating variation between independently created Skills from variation when reusing one Skill.

| Condition | Creator information | Application intervention |
| --- | --- | --- |
| N | No creation | No added Skill |
| S | Frozen generic brief/inputs + selected `skill-creator` | Its generated, immutable Skill |
| A | Identical brief/inputs + the same `skill-creator` + the two selected ALPS Skills | Its generated, immutable Skill |

Use `comparison_design: matched_skills`. Within an application-model stratum, all N/S/A application settings, task inputs, tool access, time limits and environment fingerprints match. S/A creator runtime and generic inputs also match; only creator Skills differ. Freeze the actual selected Skill versions/hashes, not just their names. The old word-problem Skills demonstrate pipeline behavior and are not GDPval production interventions.

Creators receive no task answers, original rubrics, evaluator protocols or other conditions' artifacts. Applications receive only their original task, supplied files and condition Skill. Participant agents retain responsibility for their formulas, Pivots, source selection, code, controls, dependencies and self-checks. Do not distribute benchmark solutions, task-specific helpers, worked templates or automatic repair, even symmetrically across N/S/A.

## 2. Decisions to approve before any production dispatch

| Decision | Proposed starting choice | Alternative / limit |
| --- | --- | --- |
| Application model | One stratum: Codex `gpt-5.6-sol`, `medium` | Add Opus 5 as a separately budgeted replication stratum; do not mix model effects with Skill effects. Sol is proposed because current GDPval-v2 application evidence exists. |
| Creator | Claude `claude-opus-5`, `medium`, same for S/A | Different creator is a new declared condition; exact account/model preflight required. |
| Replication | `creation_repeats: 2`, `repeats: 2` | Two creation samples are only a minimum; report per-cohort results. One cohort/one repeat is a smaller conditional comparison, not evidence of creation/execution variability. |
| Primary judgment | Original-item scalar inspection, independent Sol + Opus panel, reported separately | One predeclared judge reduces cost but removes panel disagreement evidence. No majority repair or cherry-picked judge. |
| Pairwise judgments | Optional secondary protocol, all three condition pairs and both orders | Not automatically included in the scalar budget. If chosen, freeze its scope and rubric before outputs; insufficient evidence remains unjudgeable. |
| Time/attempt limits | Creator 600 s; application 900 s; scalar/pairwise 1,200 s; serial; automatic retries 0 | Proposed finite caps based on existing acceptance calls, not proof that every task completes within them. Claude creator/application/evaluator max turns: 24/60/40. New retry or changed limit needs its own declared envelope. |

A full first production configuration should be approved only after the controller resolves the present evidence defects and decides the treatment of every remaining route/human-observation obligation. The current ledger says **191 bounded common routes /29 route gaps**, not 191 successful tasks. The latest spreadsheet entry-point probe establishes no new acceptance. A full official Office bundle has now been acquired and signature-checked, but its one isolated operation-entry probe failed. Usable native bootstrap/operation and isolation evidence, or a separately authorized isolated Excel route, remain prerequisites; binary presence is insufficient.

## 3. Original population and unresolved inputs

Include **all 220 frozen original tasks and all 10,453 original criterion IDs**, including 94 negative signed weights. Dataset SHA256: `4d58ee30485093010bf8b0a11708f80924831eef2a643db4c2d23b72fd426470`. Bind all 261 supplied files to the existing pinned remote-object identities and stage the original bytes. No exclusions based on page count, difficulty, current tools or observed performance.

Freeze original prompts, source scores, source-bound inspection procedures and evaluator-only context before applications. Preserve the 201 candidate /16 clarification /3 undetermined content classification independently of environment support; these are not quality outcomes. Keep malformed supplied-file uncertainty and exact external-source/version obligations separate. A source-matched truncated WAV cannot be repaired into its missing tail; controller-selected replacements or missing participant research cannot be supplied retrospectively.

Before launch, the owner must choose to resolve source interpretation conflicts or retain the exact affected original items as unconfirmed. Any clarified alternative policy has a separate version and cannot be pooled with literal original-rubric results. Assign the required human observation roles/raters before depending on that route. Lack of human evidence is unconfirmed, never an automatic failure or an exclusion. Keep each mixed criterion intact and preserve its original OR branches.

## 4. Execution, evaluation and resumption

Use fresh creation/application/evaluation contexts and the same final isolated capability environment. Evaluator-only durable task/rubric/protocol/schema inputs must remain readable after compaction and protected from writes. Judges inspect anonymous saved artifacts and the same frozen render bytes; they cannot see condition labels, creator provenance, other judges or other-task material.

Evaluation may enter values, select existing options/filters, and refresh/recalculate only as permitted by the original criterion. It must not add missing controls/formulas/Pivots/connections, unprotect, repair, or change calculation mode to manufacture a pass. Direct writes plus reopening/recalculation do not establish ordinary UI entry or automatic updates. Keep evidence provenance validation separate from the semantic adequacy of the observation.

Freeze a deterministic task/condition order and finite dispatch manifest. Keep the original dashboard then science sequence for acceptance gates. Production ordering must be fixed before outcome inspection; all remaining tasks stay scheduled. The current runner is serial and condition-major, so do not claim randomized interleaving it does not implement. If smaller batches are chosen, freeze all partitions and Skill provenance first; no outcome-based task substitution or stopping rule.

Every started failed/timeout session consumes its slot. Resume only within the approved remaining envelope; preserve completed creations, outputs and judgments. An explicitly approved retry keeps its old attempt and usage. Changed application environment requires a new run; changed inspection requires a separate evaluation identity against unchanged saved artifacts. Deterministic revalidation is neither a new judgment nor a new sample.

## 5. Analysis and reporting

Report original-item pass/fail/unconfirmed and coverage, execution completion, evaluation completion and task success separately. Preserve signed weights in the source sidecar. The current helper does not claim an official weighted GDPval score: approve any aggregate score definition before launching, and do not turn missing evidence into zero or silently renormalize to the observed subset.

Report quality/time/usage by condition, task and creation cohort; show creation cost separately and, if useful, its stated amortization across uses. Retain unsuccessful attempts in resource totals. Raw provider token categories are not interchangeable, cached usage is not a second generation, and unknown subscription cost is not zero. Claude's reported token-price estimate is not actual incremental spending.

For optional pairwise comparisons, use saved matched generation IDs, all declared orders, win/loss/tie/unjudgeable, per-judge rates and agreement denominators. Use the existing equal-task weighting and seeded task-cluster 95% bootstrap; votes/orders/re-evaluations are not independent tasks. Report cohort variation separately; two created Skills do not establish a precise general distribution of Skill creation outcomes. Do not infer ALPS superiority from acceptance fixtures.

## 6. Size and time estimate

For `T=220`, three conditions, `C` creation cohorts, `R` execution repeats and two scalar judges:

- Creator calls: `2C`.
- Application calls: `660CR`.
- Scalar calls: `1,320CR`.
- Optional complete two-judge pairwise panel: an **additional** `2,640CR` calls.

| Design, one application model | Creator | Application | Scalar | Total calls | Sum of proposed model/tool timeout limits |
| --- | ---: | ---: | ---: | ---: | ---: |
| C=1, R=1 | 2 | 660 | 1,320 | 1,982 | 605.3 hours |
| C=2, R=2 | 4 | 2,640 | 5,280 | 7,924 | 2,420.7 hours |

The second design's optional pairwise panel adds 10,560 calls and 3,520 timeout-hours. A second application model approximately doubles application/evaluation counts; shared creator reuse must be declared, not counted as new independent Skills.

**Observed reference, not a 220-task forecast:** two saved Sol applications took 584.59 and 747.90 seconds (mean 11.10 minutes). Two saved Sol evaluations took 403.46 and 597.74 seconds; the post-correction science and dashboard-recovery Opus evaluations took 660.95 and 859.25 seconds. Applying these narrow two-task means gives about **353 hours** for C=1/R=1 or **1,413 hours** for C=2/R=2, excluding creator/setup/human work and failed attempts. Different artifacts, dependencies and research can vary greatly; these figures are capacity illustrations, not statistical estimates of the population.

Four earlier generic Skill creations totaled 262.85 seconds, but that GSM8K/older-environment timing is not a validated GDPval creator forecast. Retain the failed 470.97-second Claude evaluation and earlier timeouts in historical attempt accounting. Account ceilings and reset waits may dominate calendar duration. No reliable dollar or remaining-allowance conversion is supported by these logs.

Approve the model/replication/judge/time choices and a finite initial dispatch budget only after the blockers are addressed. Preparing this proposal consumes **zero model sessions** and does not reserve or authorize the counts above.

## Source basis at drafting

- `.agents/development/requirements.md`: `3eda2837ccaa7619e1eeeae8d32071264185f3824d7557f9427adffbe0f069fa`.
- `.agents/development/SPEC.md`: `f0f71aaf728c3cbde5fa0449c6923891e674badc2fdf4d4623ecd0f327e636de` (matched Skills, cohorts, panel, frozen policy, resume and task-cluster aggregation).
- Current readiness ledger: `e5c0430b3917feb6599f7c5c8edf7f73ad192a097490cdf2118fab83ff8cbf86`.
- `.audit/2026-09-21-cli/session-summary.json`: `21417d3470f66d23a4a694849ddbb626d70686913e74a5aa3abbad353fdbd224` (application timings).
- `gdpval-six-session-acceptance-2026-09-22.json`: `a1e591adfe91b4913ba16d4a9cc6971841e7d0f857893cd4e17e8c61ebc0b60f`; `gdpval-dashboard-recovery-2026-09-22.json`: `2a0b26c69b263e8b663425abada47496fae8a7f4c8c5bd183c9c40a9c61932e7` (evaluation timings).
- `claude-nsa-acceptance.json`: `d8e7599d8ab455f56efbe6cd0e9442a907c5344f676de347d841d46ee3954294` (earlier creation/reuse/resume evidence).
- `.audit/2026-09-22-excel-controls/report.json`: `ea4a883ea714eeba838f974deb1a4cf40d905ecb50b9a4e515799158395f2fc4` (current native entry-point limitation).
