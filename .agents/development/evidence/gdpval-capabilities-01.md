<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# GDPval environment acceptance record — 2026-09-16

## Decision and applicable version

The isolated work tools, incremental inspection, saved evidence and unconfirmed-result accounting are implemented
and verified for the declared macOS paths. Complete task-quality acceptance remains **unconfirmed**. This change is
ready for a draft PR with the limits below; it does not authorize an ALPS comparison, merge or a claim that all 220
tasks are executable. The original two tasks were retained in the prescribed order, using the frozen prompts and
provided files. No task was replaced after seeing results.

Baseline: `0cb774f706a50e8fc4117cd2903ee32b9b6b4069`.
The authoritative baseline and exact runtime fingerprints are in the [machine-readable receipt](gdpval-capabilities-01.json).
The task-1 applications and successful known-page probes retain their earlier source fingerprint. Worker cleanup was
then corrected to precede original verification and artifact collection; two regression cases reproduced the defect.
All four judgments and both task-2 applications use the final fingerprint
`b96e51e2f8365cee10f93a8bb3e73756d6eb2039b70ccf472688b1d6e7fbaca2`.
No old run was relabeled as the new environment.

## Outcome evidence

| Outcome | Verified scope | Limit or required next action |
| --- | --- | --- |
| O1 | Both CLIs used the same isolated file/code tools; participants authored their own helpers. Scientific research was performed by participants and saved. A separate no-model check exercised pinned-wheel installation. | Shell supports one foreground process; exact-domain networking is intentional. ESO's `elt.eso.org` redirect was blocked in the frozen acceptance configuration. Revise and revalidate the configuration before a future condition requiring that source. |
| O2 | Both CLIs viewed pages 1, 21 and 30 of the same 30-page document. OOXML inspection distinguishes native pivots and revisions from appearance. Isolated copies of both actual dashboards passed 24 changed-input/selector value checks; chart-cache changes were recorded. | Native Word opening and hyperlink activation need the declared human review. Native Excel UI/filter-refresh behavior is unconfirmed. AI judgments sometimes asserted passes beyond their actual inspection; raw reports are retained, and those assertions are not accepted as verified quality. |
| O3 | Seven common work tools, pinned libraries, account routes and role permissions are documented. Positive/negative native tests cover creator, participant and judge boundaries. Actual model calls cover participant and judge roles. | Creation under this new profile has boundary/regression evidence, without a new model-backed creator trial. This profile is macOS-specific. |
| O4 | Provided files, acquired source bytes, queries/URLs, redirects, failures and timestamps/hashes are separate. Evaluation receives saved research alongside immutable originals. | Available sources are not necessarily sources the judge actually inspected. Missing participant research cannot be repaired with controller prefetching. |
| O5 | All 220 task IDs have eight sections and three independent current axes. The fixed two tasks have actual generation/evaluation receipt references. Historical partitions and corrections are preserved separately. | The other 218 tasks are outside this acceptance execution. No complete file/rubric audit or full task acceptance is claimed for the 220 tasks. |
| O6 | 209 regression tests, typing for 29 runtime files, Ruff, documentation checks, completed resume and saved comparison. Unknown scores and usage remain null; counts retain unconfirmed assessments. | Raw task-1 scores are evaluator claims and have unsupported evidence ranges. They are not accepted quality measures for this infrastructure trial. |

See the [103-criterion matrix](gdpval-acceptance-criteria.json),
[220-task ledger](../gdpval-task-readiness.json), [historical triage](gdpval-content-triage-2026-09-16.json),
[specification](../SPEC.md#shared-gdpval-capability-environment) and [working plan](../PLAN.md).
The source dataset is pinned by its SHA256; the ledger and pre-execution plan use explicitly recorded JSON encodings
for per-row hashes. The equivalence check confirms that those encodings describe the same original rows.

## Bounded CLI trials

Codex 0.154.0 used `gpt-5.6-sol/medium`; Claude Code 2.1.270 used `claude-opus-5/medium`.
There were 11 model sessions: four applications (900s limit), four judgments (600s limit), and three multipage probes
(300s limit, including the explicitly authorized corrective Codex session). Model concurrency was 1; automatic harness
retries were 0. Existing subscriptions were used, Claude extra usage was disabled, and no API or auxiliary AI was used.
The strict-config attempt before inference consumed zero model sessions and is retained separately (39.28s).

| Session | Workflow seconds | Native input tokens | Output tokens | Result |
| --- | ---: | ---: | ---: | --- |
| probe config-fixed-codex | 88.29 | 99179 | 1765 | infrastructure failure: MCP approval |
| probe claude-code | 101.50 | 8 | 1029 | image transport verified; 9/9 recognition |
| application 1-claude-code | 647.01 | 46 | 41781 | completed |
| probe approval-fixed-codex | 79.81 | 81909 | 1629 | image transport verified; 8/9 recognition |
| application 1-codex | 650.25 | 986563 | 27870 | completed |
| evaluation 1-codex | 210.64 | 151123 | 9988 | completed; assessed |
| evaluation 1-claude-code | 236.74 | 30 | 14320 | completed; assessed |
| application 2-codex | 509.45 | 1574371 | 21821 | completed |
| application 2-claude-code | 580.62 | 58 | 42669 | completed |
| evaluation 2-codex | 183.94 | 108891 | 8497 | completed; unconfirmed |
| evaluation 2-claude-code | 305.17 | 22 | 21031 | completed; unconfirmed |

Total measured workflow time across the 11 model sessions: **3593.43s**.
The receipt retains execution-only time, cached/reasoning tokens and Claude's reported USD estimates separately.
Actual incremental subscription charges are unknown (`null`). Native cache counters have different meanings between
CLIs; these acceptance timings were measured on a development host and are not an ALPS performance comparison.

## Findings that constrain acceptance

- The final common page transport worked in both CLIs. Claude recognized 9/9 known fields; Codex recognized 8/9,
  calling the page-21 square a rectangle. Exact image hashes match across CLIs; this is a reading error.
- The Claude dashboard contains four native PivotTables; the Codex dashboard contains none. This is a participant
  result, not a reason to exclude or replace the task. Both contain four charts.
- Native conversion initially reused spreadsheet formula caches. The retained corrective inspection invalidated caches
  only in isolated copies, forced recalculation, changed data/selectors and checked dependent values. The initial
  method failure and correction are separate evidence. Later controller checks do not retroactively become judge actions.
- Both scientific edits contain native insertions, deletions and anchored comments. Raw URL text alone does not prove
  click-through behavior in Microsoft Word. Native Word criteria remain unconfirmed and overall scalar scores stay null.
- Network timeouts, renderer errors, sandbox-denied commands and the ESO redirect denial remain in the tool journals.
  A completed model session is not a claim that every tool call or task requirement succeeded.
- Audio/video perception, CAD engines and native Office UI behavior beyond the declared paths remain unsupported or
  unconfirmed as recorded per task. Python's locked dependency audit found no known vulnerabilities in 52 packages;
  native dependency CVE coverage remains unconfirmed.

## Existing ALPS experiments

Existing records and conditions remain unchanged. Using the new participant environment requires new executions for
all compared N/S/A conditions under the same frozen environment. A changed creator environment likewise requires
matching creator conditions. Do not pool old and new source/environment/criterion versions.

Saved submissions can be evaluated again under a new evaluation identity when original inputs and required provenance
are available and the criteria still apply. If old runs lack participant research, new task execution is required;
controller research is not a substitute. Complete the declared human checks and address unsupported judge assertions
before accepting full quality scores. The fixed acceptance pair does not select a favorable ALPS task pool.

## Evidence retention

The JSON receipt records session identities, artifact hashes, per-item scope, preserved failures and local proof hashes.
Raw CLI events, retrieved bytes, native conversion copies and source snapshots are retained in the ignored local
`.audit/acceptance/` directory. They are not bulk-published. The tracked ledger generator accepts the frozen source
explicitly and derives current trial coverage from the tracked acceptance map without embedding quality scores.
