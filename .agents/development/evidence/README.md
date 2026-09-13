<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Historical acceptance evidence

These records document the small local trials and development acceptance on September 13–14, 2026.
The implementation was merged in [PR #46](https://github.com/mashimashica/eval-harness/pull/46) at
[`f917ebc`](https://github.com/mashimashica/eval-harness/commit/f917ebc59e46d2e4b03af7d5735be442eddbd611).
They establish what was checked at that time; they do not certify later revisions, current dependency security,
official benchmark scores, or ALPS superiority. Use the [product guide](../../../fern/versions/latest/pages/get-started/eval-harness.mdx)
for current setup and usage.

## Records

The [acceptance summary](integration-acceptance.json) records the accepted commit, CI receipts, quality checks,
upstream reuse decisions, isolation findings, excluded trials and limitations.
The [acceptance ledger](../PLAN.md#acceptance-ledger) maps R01–R10 and all six CLI commands to their evidence,
including regression tests that complement these real CLI trials.

| Record | What it establishes |
| --- | --- |
| [GDPval pilot](gdpval-pilot-01.json) | Codex account execution, a saved spreadsheet and separate read-only AI evaluation. |
| [Claude GSM8K](claude-gsm8k-01.json) | Claude subscription execution through confined file tools and mechanical grading. |
| [N/S/A comparison](nsa-comparison-02.json) | No Skill, skill-creator, and skill-creator + ALPS: two repeats each, separate creation/application inputs, Skill hashes, answers, usage, partial resume and re-evaluation. |
| [Grading and aggregation](grading-and-aggregation-01.json) | Four anonymous Claude judgments in both presentation orders; six synthetic human ratings with criteria/comments; append, resume and method-separated aggregation. |
| [Fresh checkout](fresh-checkout-01.json) | Locked installation and a one-task run; command results, re-evaluation and resume without duplicating generation or changing saved artifacts. |

Each trial retains its original run IDs, execution conditions and relevant input, Skill and artifact hashes.
Trials ran on identified development candidates; their success is not a claim that every later commit was rerun
against real models. Missing measurements remain `null`; Claude's reported USD is an API-equivalent estimate,
not a subscription charge.

## Interpretation and original material

- The first GDPval judgment (**0.94**) was excluded because the judge created a replacement workbook.
  The accepted separate read-only evaluation was **0.81**.
- The first N/S/A attempt omitted the ALPS body and is excluded from comparison acceptance.
  The corrected comparison is the record linked above; its initial mechanical formatting false negative
  and subsequent re-evaluation are both identified.
- All human ratings here are **synthetic test inputs**, not actual human quality judgments.
- Original workbooks, full CLI logs, prompts and audit outputs are local-only under the recorded `runs/` and
  `.audit/` paths. Relative local paths use the originating checkout as their base unless otherwise stated.
  A path and hash identify an artifact but do not make it downloadable from a new checkout.

The [full original records](https://github.com/mashimashica/eval-harness/tree/3edb1797adef6846d0b032fa190bc3e3dfda6828/.agents/development/evidence)
remain in Git history. Each compact record carries an immutable original-file link and SHA-256.
The dated diary, separate quality snapshot and excluded resume record were consolidated into the acceptance
summary; their original-file links and hashes are in its `consolidated_records` list. Detailed source hash maps
omitted from compact records remain available in those originals. This organization did not rerun experiments,
alter raw local artifacts, or rewrite history.
