<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# GDPval evaluation acceptance follow-up — proposed six sessions

Status: prepared, awaiting explicit owner authorization. The old eleven-session and newer ten-session batches are
exhausted and preserved. This is a finite request for additional acceptance evidence, not a production ALPS run.
Baseline: PR #53, `89967aa6605655232d623f3b047156c8cbd69557`, plus the inspection prompt/derived-PDF correction.
The candidate environment fingerprint is `701baddb85dcb7eabd6440be838fd9e7d31f63e53d94caa935fa1cd965021d3e`.

## Diagnosis and correction before requesting inference

| Saved evaluator | Cause established from preserved records | Changed method |
| --- | --- | --- |
| Dashboard / Codex | 19 items lack required per-item method references; 2 native gates | Explicit per-item method coverage and canonical references |
| Dashboard / Claude | 55 items cite temporary scratch paths; 2 native gates; at least 5 explicit criterion/observation alignment errors | Persistent captured paths and original ID-to-description matching; no retrospective alias repair |
| Science / Codex | 6 missing-method items, 3 wrong-tool/method items, 1 disallowed inference, 2 native gates | Tool-specific methods and explicit inference limits |
| Science / Claude | 600-second timeout; no structured decisions for 46 items | Concise complete structured output and a finite 1,200-second budget |

The validator had a separately reproduced gap: rendering a declared derivative PDF did not follow the existing
exact-hash lineage used for images. The candidate fixes that path without accepting missing declarations, wrong
hashes, failed transformations or unrelated originals. All three completed saved judgments replay unchanged.
159 targeted tests, strict typing and Ruff passed; protocol/lineage coverage is 89%/93%.

The prior completed evaluators took 462–604 seconds, with only 16–53 seconds in capability calls. A longer finite
budget tests whether inspection and final structured output can finish; it is not a promise that they will.
The original science DOCX parses structurally. A model-free differential probe found that changing only namespace
prefix serialization in two package XML parts on a copy allows the pinned renderer to load it. Expanded-name XML
trees and all other ZIP member bytes were preserved. The original stays unchanged; no automatic repair or original
layout-equivalence claim has been introduced. This is not one of the five malformed provided files in the all-task audit.

The model-free 30-page probe reproduced the old page-21 image bytes, then returned an exact crop of the requested
region. The controller observed the known code/shape correctly on that crop. This verifies transport and the available
inspection procedure, not future model recognition. The prior Codex recognition error remains recorded.

## Finite execution plan

| Order | Input and purpose | Runtime / model | Sessions | Per-session model timeout |
| --- | --- | --- | --- | --- |
| 1–2 | Known 30-page DOCX/PDF, formula workbook, source comparison and unobservable audio; verify the corrected evidence contract, first full-page observations then a fixed crop, derivative-PDF lineage, and deliberate unconfirmed handling | Codex `gpt-5.6-sol/medium`; Claude `claude-opus-5/medium` | 1 each | 600 seconds |
| 3–4 | Saved original dashboard submissions; evaluate original 57 criteria with reviewed v2 inspection protocol | Same two runtimes/models, each corresponding saved submission | 1 each | 1,200 seconds |
| 5–6 | Saved original TRAPPIST-1 submissions; evaluate original 46 criteria with reviewed v2 inspection protocol | Same two runtimes/models, each corresponding saved submission | 1 each | 1,200 seconds |

Maximum **6 model sessions**, model timeout sum **6,000 seconds (100 minutes)**. Concurrency **1**, automatic
session retries **0**, Claude `max_turns: 40`. Native versions: Codex CLI **0.154.0**, Claude Code **2.1.270**.
Use existing account subscriptions only; no extra usage, API billing, model fallback or auxiliary AI.
Preparation/capture/cleanup have separate watchdog targets of 780 seconds per probe and 1,380 seconds per full
reevaluation (118 minutes summed targets), followed by interruption and owned-process cleanup. These targets are not
an OS-hard guarantee for total wall time; the enforced model timeout sum is 100 minutes. Preserve actual wall time,
native usage and unknown costs; unavailable telemetry remains null.

Each session starts in a fresh isolated workspace. Freeze current source/config/protocol/input hashes before dispatch;
verify authentication, prerequisites and native isolation. The fixture's known answers stay outside the model workspace.
Record the first full-page observations before the predetermined crop, retain both results, and do not keep retrying
until recognition is correct. The four real evaluations reuse original saved artifacts: no participant regeneration,
no rubric edits, no condition changes, and no replacement tasks.

## Acceptance and failure disposition

- Known fixture: actual method records and canonical references must validate; source disagreement must be detected;
  changed-input recalculation must be observed; the unobserved audio item must remain unconfirmed with a null score.
  Compare page/crop observations with controller-held truth separately from provenance validation.
- Real evaluations: inspect criterion/evidence alignment and actual method coverage for 55 available-route dashboard
  items and 44 available-route science items. Preserve participant deficiencies, including absent pivots. A low score
  does not fail the harness, and a high score does not accept it. Valid references alone do not prove semantic correctness.
- Two native gates per task remain explicit, with no machine alternative. They cannot be accepted by this batch.
  Full-220 native/browser, perception and source-meaning gaps remain in the existing task/item ledger.
- Every started attempt consumes its slot, including errors, timeout and missing structured output. A failed prerequisite
  holds dependent calls. A fixture failure is diagnosed before dependent evaluations; unaffected checks may continue
  within the same finite authorization. No automatic retries or substitution. Preserve all results and denominators.

## Traceability and experiment impact

Local prepared files are under `.audit/2026-09-21-next-acceptance/`: `prepared-plan.json`, four validated YAML configs,
`known-contract/manifest.json`, `crop-verification/report.json` and `source-render/report.json`. Detailed saved-record
diagnosis is `.audit/2026-09-21-next-acceptance-evaluation/diagnosis.json`, SHA256
`d5cad118b418660f13f733e7f7a2334521a0115027e309fce1d85768d49e1c3c`.
The accompanying [receipt](gdpval-next-acceptance-evidence.json) binds these local files and the code correction.
Raw artifacts and private local paths are not committed.

This batch addresses Outcomes 3–5: evaluation procedure, equal evaluator opportunities, evidence and repeatability.
It does not establish all-220 acceptance or resolve native Office/browser operations and perceptual human review.
The owner coordinates human evaluation; actual reviewers are assigned before an experiment. Procedure-only changes
create new evaluation identities for the same artifacts. Generation reruns are unnecessary for this correction;
previously identified execution-environment changes still require matched N/S/A units under a newly frozen environment.
