<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# M1 acceptance and remaining work

M1 is accepted as an unmerged Draft stack entry. This is slice acceptance, not completion of the entire migration.

| Item | Evidence |
| --- | --- |
| Delivered | PR02c [#42](https://github.com/mashimashica/eval-harness/pull/42), head `6038a7828d62247ad98d000bc6e71c706f6d14a4`; common snapshot-to-CandidateBundle/index handoff, real Cursor adapter through fake CLI, runtime deletion and relocation |
| Required gates | [Eval Harness CI](https://github.com/mashimashica/eval-harness/actions/runs/34737905018), [lint](https://github.com/mashimashica/eval-harness/actions/runs/34737905024), [copyright](https://github.com/mashimashica/eval-harness/actions/runs/34737905252), [secrets](https://github.com/mashimashica/eval-harness/actions/runs/34737905236): all success |
| Exact source | Hosted checkout `73f403d8e1e9334f783f0bb7005d01aa6ba00c4e` is the synthetic merge of base `d5ce0c1` and PR head; its tree equals head tree `4f7fc21be5195611ba7df8feeefe3a5cc962c2cb` |
| Tests | Hosted 553 Python tests, six shell integrations, 45 compatibility and five inventory tests; strict mypy, all-file pre-commit and dependency audit all pass |
| Coverage | Hosted integer guard: 10070/10469 statements, 96.18874773139746%; unchanged scope/exclusions/threshold |
| Review/DCO | Independent source and final test-delta reviews closed; exact formal commit has the required Mashimashica sign-off |
| Remaining acceptance issue | PR04 NLTK CVE is still unresolved. It does not affect PR02c's unchanged passing dependency scope, but blocks acceptance of PR04 and affected later heads |
| Work allowance | Started 2026-09-13T03:56:46Z; M1 acceptance recorded 2026-09-13T04:30:56.162Z. Approximately 34 minutes elapsed, within the 90-minute working limit. Hosted CI ran 81 seconds (04:26:51–04:28:12), overlapping record preparation. There was one corrective verification round for each found fixture/type/review issue, with no repeated failed fix. Billing token totals and a reliable combined root/agent tool-call total are unavailable |
| Next | M2: implement and validate the frozen PR04 boundary with the approved CVE acceptance distinction; keep one implementation owner and no concurrent future implementation |

## Remaining estimates and stop limits

These are initial planning ranges based on the frozen scope, not promised completion times or token charges. Each PR keeps a first working allowance of at most 90 minutes, checkpointed at no more than 15 minutes and before verification. External CI duration is recorded separately. A working allowance expiry triggers the already agreed saved exception report instead of silently extending work. Normal successful milestones continue without a new approval gate.

| Milestone | Remaining implementation | Initial working estimate |
| --- | --- | --- |
| M2 | PR04: host/worker boundary, callers, pinned provisioning, real Linux boundary/parity evidence | 2–4 hours across bounded allowances; first allowance 90 minutes |
| M3 | PR05–06: independent evaluation, GDPval rubric/pairwise/panel | 2–4 hours across two PRs; first allowance per PR 90 minutes |
| M4 | PR07–08: Stirrup generation, AA-v2 aggregation/resume | 2–4 hours across two PRs; first allowance per PR 90 minutes |
| M5 | PR09: common N/S/A builder/application/evaluation | 1–2 hours; first allowance 90 minutes |
| M6 | PR10: port remaining behavior, remove old routes, update docs and executable examples | 1–2 hours; first allowance 90 minutes |
| M7 | PR11: add-only fourth fixture, complete matrix and final acceptance | 1–2 hours plus required CI; first allowance 90 minutes |

The estimates have substantial uncertainty, especially native sandbox provisioning and whole-dataset parity. Re-estimate at the next milestone or stop condition; do not increase investigation scope to consume the estimate. No NLTK backport/repeated M0 investigation, real-model experiment, merge, release or publish is authorized here.
