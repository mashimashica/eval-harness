<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Completion plan

Controller: Astra; implementation/self-verification: Luna max; Sol max only for a consequential boundary review.
One implementation writer and at most one specialist; no nested delegation. Baseline main:
`98f7634747b6e489309f73df97f7d08529592e9a`. Initial checkout clean; origin agrees. Branch:
`codex/complete-local-harness`. The user authorizes scoped local setup, trials, DCO commits, pushes, PRs and merges
after applicable acceptance and checks. No global setup, API billing fallback, destructive history, release or deployment.

## Environment and discovery

2026-09-13: macOS arm64; Codex CLI `0.154.0-alpha.6.2`, login reports ChatGPT; Claude absent from PATH;
uv `0.7.16` is older than the upstream minimum. gh account authenticated with repo/workflow authority.
Use project-local tools/dependencies. The host exposes the five canonical development Skills and model overrides
`gpt-6-astra`, `gpt-5.6-luna`, `gpt-5.6-sol`, including max effort. Actual worker dispatch is recorded below.
Claude Skill aliases exist and resolve; native Claude discovery remains unconfirmed until installation/authentication.
Development Skill discovery is distinct from participant isolation and benchmark verification.

## Milestones and work order

1. Inspect retained data preparation, graders, CLI wrappers, skills and artifacts. Adapt reusable pure functions;
   avoid making API/model servers or the full upstream ML dependency graph a required local CLI route.
2. Deliver GDPval one-task Codex run, saved artifacts and independent CLI evaluation; establish typed Python,
   uv lock, Ruff, focused tests and fork CI from the first implementation.
3. Connect Claude, a second existing benchmark, generic Skill creation/application, mechanical/scalar/pairwise/human
   evaluation, repeats, aggregation, re-evaluation and resume. Update SPEC beside implementation decisions.
4. Exercise the full small comparison, failure/resume boundaries, dependency and secret scans, fresh-checkout setup;
   accept against every row below and merge passing PR(s) to main.

## Acceptance ledger

Acceptance is evidence-based; implementation alone does not satisfy live-evidence requirements.
Real evidence: [GDPval](evidence/gdpval-pilot-01.json), [Claude GSM8K](evidence/claude-gsm8k-01.json),
[discovery and boundaries](evidence/integration-acceptance.json). The [evidence index](evidence/README.md) explains
the historical scope and original-artifact availability. This ledger records the implementation acceptance;
earlier trial notes below retain the history of excluded attempts and corrections.

| Criterion | Required evidence | Status / evidence |
| --- | --- | --- |
| R01 | Shared task/repeat scheduling; N/S/A comparison; quality/time/usage variation | met: corrected N/S/A 2 repeats each, quality/time/token variation, unknown costs preserved; nsa-comparison-02.json |
| R02 | GDPval + existing benchmark use common pipeline; reuse decisions grounded in code | met: GDPval + retained GSM8K real pipeline; evidence files below |
| R03 | Codex and Claude account-authenticated real execution; no API fallback | met: real Codex GDPval and Claude GSM8K, pinned CLI versions, account-only environments |
| R04 | Independent runtime/model/settings/intervention/evaluation; early invalid-combination rejection | met: independent role configs and prompt/Skill fields; strict runtime settings and unsupported combinations rejected; test_config_validation/test_pipeline/test_cli |
| R05 | Standalone and inline creation; versioned reuse; separate creation/application inputs | met: real independent standalone S + inline A, explicit body delivery and content hashes; nsa-comparison-02.json |
| R06 | Full pipeline, immutable artifacts and re-evaluation without generation | met: real create/run/mechanical/compare and saved GDPval scalar + GSM8K mechanical re-evaluation without regeneration |
| R07 | Mechanical, AI scalar, anonymous pairwise and criterion/comment human import/aggregation | met: GDPval scalar, GSM8K mechanical, 4 real anonymous Claude judgments, human fixture append/import/resume/aggregate; grading-and-aggregation-01.json |
| R08 | Fresh isolated participant contexts, withheld grading/other conditions; balanced pair order | met: exact native boundary probes + selected prompt/Skill audits + both pair orders; read-only real judges, no implicit development Skills |
| R09 | Input/Skill hashes, logs, artifacts, judgments, elapsed/usage/cost and distinct statuses | met: real evidence + frozen input/artifact manifests; incorrect completed task has task_success false; missing metrics stay null |
| R10 | Read-only preflight; bounded workload/retries/timeouts; frozen resume preserves completion | met: all-role preflight; all creators frozen before first call; real partial resume + input mutation/deletion/receipt/failure regression tests |
| check | No generation/grading; config, auth, inputs and support validation | met: actual account/input preflight and fake-CLI zero-generation prerequisite tests |
| build | New output; reusable Skill from independent creation config | met: real standalone creation, reused unchanged across repeats; tests reject existing output/invalid Skill |
| run | Creation through evaluation/aggregation; same shared tasks/repeats | met: corrected N/S/A actual run completed with mechanical evaluation and comparison |
| evaluate | New evaluation identity; existing generation IDs and artifact bytes preserved | met: four evaluation routes exercised; same saved source hashes and no application calls |
| compare | No model calls; method/task/sample identities preserved, repeats reported | met: 3-method CLI aggregate reports 6 distinct samples and 2 per condition; nonexistent CLI paths prove no calls |
| resume | Frozen settings/inputs; only incomplete stages continue, completed work preserved | met: actual 4-complete/2-pending resume and human append; frozen creator/source/evaluation mutation guards and receipt regression |
| Integration | main commit, required fork CI pass, DCO, security scans, reproducible user docs | met: PR46 merged at f917ebc59e46d2e4b03af7d5735be442eddbd611; main CI34768895116 passed; integration-acceptance.json and fresh-checkout-01.json |

## Authorized small real-trial envelope

Before calls: each batch records exact data/model/settings and purpose here or in linked evidence. Initial batch:
GDPval one selected public task, Codex application and Codex judge using `gpt-5.6-luna`, reasoning `medium`;
one application + one scalar judge, concurrency 1, timeout 600 seconds per call, automatic retries 0.
Prerequisite/discovery calls do not generate and are separately logged. Use native sandbox with a fresh working
directory outside the development checkout, clean runtime configuration and only intended inputs.
Do not launch if account authentication or isolation is unverified. Subsequent batches will be specified before running.

## Current work / decisions

### Batch 1 launch record (2026-09-14 00:10 JST)

- First real application: GDPval `83d10b06-26d1-4636-a32c-23f92c57f30b`, one execution; separate scalar judge,
  one call. Both standalone Codex 0.154.0, `gpt-5.6-luna`, medium, timeout 600 seconds, concurrency 1,
  harness automatic retries 0. Native unbounded retries disabled; the pinned CLI's built-in transport retry behavior
  stays subject to the process-group timeout (the built-in provider cannot be overridden).
- Frozen launch config: `.audit/pilot/experiment.yaml`, SHA256
  `28784d708f32b3473b1cdf0cf0ba15a55cc1c55497a18883d7413fb06dc407aa`.
  Candidate source hashes: `.audit/pilot/source-sha256.json`; raw outputs under `runs/gdpval-pilot-01`.
- No-model gates passed on actual generated executor configuration: isolated ChatGPT auth; no default Skill or
  multi-agent/development input at the selected Luna model; native workspace write plus auth/repo read denial.
  Initial specialist overstatement about a separate process boundary is corrected by exact configured probes.
- `check .audit/pilot/experiment.yaml` passed. First batch remains two calls maximum; no fallbacks.
- User completed Claude login; latest status confirms `claude.ai`, firstParty, Max subscription. Previous pending
  auth blocker is resolved. Claude model/settings and trial will be separately recorded before its generation.

### Current state after batch 1

- Parent owns plan, executors, native probes, CI, docs and integration. Luna owns common pipelines and focused tests.
- Project-local uv 0.12.13, Python 3.13.14, standalone Codex 0.154.0, Claude Code 2.1.270 installed.
  Both account routes verified; Claude reports claude.ai / firstParty / Max, extra usage disabled in account metadata.
- GDPval application completed, workbook captured. First scalar judge returned JSON but created a replacement workbook
  in its own workspace, so its 0.94 is **excluded** from quality acceptance. Original artifact hash is unchanged.
- Corrective boundary: evaluation workspace is native read-only; Claude evaluation exposes Read/Glob/Grep only.
  Actual Codex sandbox reads the 1,517-row reference via openpyxl and denies replacement creation. Executor tests: 13 pass.
- Next: corrected GDPval re-evaluation, Claude GSM8K trial, standalone/inline creation and N/S/A repeated comparison;
  human/pairwise grading, immutable resume, aggregate verification, fresh checkout and main integration remain open.
- Fork CI uses a hosted runner and no account credentials; NVIDIA-only inference/runner/publish routes are gated.
  main initially has no protection/rulesets. Configure required Harness quality after candidate CI success.
- Completion is not claimed while mandatory rows remain open.

### Batch 1 correction (authorized before launch)

Exactly one additional scalar evaluation of saved `runs/gdpval-pilot-01`; **zero application generations**.
Codex 0.154.0, gpt-5.6-luna, medium, timeout 600 seconds, concurrency 1, harness retries 0.
Output `runs/gdpval-pilot-evaluation-02`. Corrected explicit evaluator-only prompt + native read-only workspace.
Source hashes stored in `.audit/pilot/reevaluation-source-sha256.json`; actual native probe in
`.audit/judge-readonly-probe.json`. Preserve and identify the excluded first evaluation; never overwrite it.

### Batch 2: Claude common-pipeline smoke (before launch)

One real GSM8K application (`gsm8k-0001`, retained prepared test row, Janet eggs), Claude Code 2.1.270,
claude-sonnet-4-6, medium, standard context, fast disabled, max turns 12, timeout 300 seconds, concurrency 1,
CLI/API retries 0, harness retries 0. claude.ai Max account, extra usage disabled as locally reported.
Mechanical evaluation and comparison require zero additional model calls. Config `.audit/claude-pilot/experiment.yaml`,
output `runs/claude-gsm8k-01`. Codex batch 1 correction completed: original workbook unchanged, read-only AI score 0.81
with specific observed deficits; this establishes the first milestone, not overall completion.

### Batch 3: bounded N/S/A repeated integration (before first creation)

- Shared task: actual GSM8K prepared test row gsm8k-0001 (Janet eggs), same two repeats per condition.
- Conditions: N no Skill; S existing result of standalone build using skill-creator; A inline build using skill-creator
  plus ALPS0.7.0 design-process-description and design-agent-work-system. Both creators receive the identical general
  math Skill brief and local official Skill format reference; no benchmark tasks, answers or rubrics.
- Exactly two creator calls: Claude Code2.1.270, claude-sonnet-4-6, medium, max_turns24, timeout600s each,
  standard context/fast disabled, claude.ai Max, CLI retries0. Skill name word-problems for both.
- Exactly six application calls maximum: Codex0.154.0, gpt-5.6-luna, medium, timeout300s each, ChatGPT.
- Concurrency1 across calls, harness retries0. Mechanical evaluation, re-evaluation and compare add no model calls.
- Configs .audit/nsa/build-s.yaml, build-a.yaml, experiment.yaml; launch-config-sha256.json and build-source-sha256.json.
  Outputs runs/nsa-build-s/word-problems and runs/nsa-gsm8k-01. Pairwise real judge calls will be separately planned.

Batch3 observed: both creators completed; N0/N1/S0/S1 completed, A0/A1 remained pending after a nested Skill
path defect. Original artifacts and four completed records are saved in .audit/nsa/completed-before-resume.json.
Resume consumes only the two originally planned remaining application calls; no creator rerun.
Treatment audit also found A creator did not read ALPS bodies despite staged files. This batch is excluded from
ALPS comparison acceptance. Explicit selected Skill body delivery is being implemented for all subsequent creator
and application calls; supporting files stay staged. A corrected comparison batch will be recorded before launch.

### Batch4: corrected explicit-Skill delivery comparison (before launch)

Replace only the unaccepted comparison evidence; keep all earlier artifacts. Same real GSM8K0001, N/S/A,2repeats.
Exactly2creator calls (Claude2.1.270,claude-sonnet-4-6,medium,24turns,600s) plus6application calls
(Codex0.154.0,gpt-5.6-luna,medium,300s). Concurrency1,harness retries0,Claude native retries0, nofallback.
Both S and A receive every selected creator SKILL.md body in the prompt; same generalbrief and formatreference.
Applications also receive their selected SKILL.md body, with supportingfiles staged. Each deliveredbody/hash/prompt
is retained. Outputs runs/nsa-v2-build-s/word-problems and runs/nsa-v2-gsm8k-01.
Configs and launch/source hashes under .audit/nsa-v2. Mechanical evaluation adds no modelcalls.
The additional bounded calls correct the observed delivery defect; they are not a performance-ranking experiment.

### Batch4 acceptance and remaining integration work

Corrected N/S/A run `ade140dd511a40d4bfd87c220c39bb11` completed all six applications. Every selected creator Skill
body was supplied explicitly; generated Skills were delivered in all S/A application prompts. A nested path defect
was fixed and covered by a full pipeline regression. Actual resume retained four completed records byte-for-byte
and executed only the two pending applications, without rerunning either creator.

A formatting false negative (`$18 per day`) in the original mechanical evaluation was fixed. Separate evaluation
`1433cb3c730e4f6d8471e3bafc6160c1` graded the six saved answers correctly; all artifact hashes and run records
remained unchanged. Original evaluation is retained and excluded from quality acceptance. Evidence:
[evidence/nsa-comparison-02.json](evidence/nsa-comparison-02.json). This is integration evidence, not a quality ranking.

Next: bounded four-call N/A anonymous pairwise judgment, human fixture import/append/resume and aggregate checks;
finish all-role preflight, freeze/resume edge validation and added-prompt support; final CI/security/fresh checkout,
DCO commit, PR, required check and main merge. No acceptance is inferred from the unfinished rows.

### Batch5: anonymous saved-artifact judgment (recorded before launch)

Use only corrected batch4 saved GSM8K0001 outputs. Select condition pair N/A for each of two repeats, both
presentation orders: exactly four judge calls, zero application or creator calls. Claude Code2.1.270,
claude-sonnet-4-6, reasoning medium, max_turns12, timeout300 seconds per call, standard context/fast disabled,
claude.ai subscription, concurrency1, CLI retries0, harness automatic retries0. Save to runs/nsa-v2-pairwise-01.
Input config and source hashes are recorded in .audit/acceptance before launch. Parent verifies read-only A/B
workspace content and result identities; no further calls without an additional bounded plan entry. Human fixtures,
mechanical re-evaluation, compare and resume of completed work use zero model calls.

Batch5 accepted: evaluation `5bf1a2f7837049a79d829362e96337e9` completed exactly four Claude judgments, all ties,
with both N/A orders for each repeat. Actual initialization exposed only Read/Glob/Grep and the exact selected model.
Human fixture evaluation `b7e43dec2f0f443682c91b97751dab4d` progressed 0→1→6 valid rows via append/resume;
first completed rating was unchanged. All human rows are explicitly synthetic test data, not real human assessments.
Three-method compare with nonexistent CLI binary paths succeeded and retained six generated samples.
[evidence/grading-and-aggregation-01.json](evidence/grading-and-aggregation-01.json) contains actual judgments and checks.

### Batch6: clean-checkout reproduction (before launch)

After the implementation candidate is committed, create an isolated checkout at that exact commit under
.audit/fresh-checkout. Install the locked harness non-editably with project-local uv/Python, prepare data using the
retained GSM8K script, and use the documented harness/examples/gsm8k-one-task.yaml. Exactly one application call:
GSM8K0001, Codex0.154.0, gpt-5.6-luna, medium, timeout600s, concurrency1, automatic retries0, ChatGPT account.
Mechanical auto-evaluation, compare, saved-artifact re-evaluation and completed resume require no model calls.
Use existing pinned local CLI executables via PATH; no global tool/config changes. Record the candidate commit,
installation/import paths, source hashes, command exits and results before final acceptance. This single call is
reproduction verification, not another performance experiment.

### Implementation acceptance before integration

Final local installed-package checks: 82 behavioral tests passed; Ruff and format pass; mypy checks all15source
files without errors. Measured coverage is approximately80%, with no universal threshold imposed. Auth and actual CLI
paths also have separate real evidence; unit coverage is not presented as runtime proof. Locked runtime/dev dependency
audit scanned52installed distributions with no known vulnerabilities. Fern check0errors/1warning,14link tests pass.

Controller accepts R01–R10 and all six commands against the listed evidence. Outstanding project acceptance is now
fresh-checkout reproduction, submitted-change secret scan, fork CI and authorized main integration. Luna performed
implementation/self-verification; Sol's independent review was limited to runtime boundaries, not a blanket approval.

### Fresh checkout and PR acceptance

Candidate `3849a49134bdf4061fabf91329e5bd66fde307ba`, PR46, passed all Harness quality steps on GitHub Actions
run34768555001. Secret scanning of the actual submitted commits passed, along with tests, typing, lint, dependency
audit and documentation checks. main now requires the GitHub Actions Harness quality check against an up-to-date
branch, including for administrators; force pushes and deletion are disabled. No bypass was used.

A detached fresh checkout installed its own uv0.12.13, Python3.13.14 and locked noneditable package, without PYTHONPATH
or global installation. The documented one-task GSM8K run completed using the existing pinned Codex0.154.0 executable:
run `d2fd94341ac843f6be32d79f9394a52c`, one attempt, mechanical score1.0. Separate mechanical re-evaluation and both
comparison commands succeeded with nonexistent CLI paths. Completed resume retained the original state and execution
journals, and every deliverable matches its original recorded hash. Two evaluation IDs still aggregate to one generation.
[Fresh-checkout evidence](evidence/fresh-checkout-01.json) records setup, exact source/config hashes, commands and results.

The setup instructions now use `uv python install --no-bin` so Python stays project-local; existing pinned standalone
CLI installations can be reused. Only documentation/evidence changed after the reproduced candidate. Next: run CI for
this final PR revision, merge through the required check, verify main CI, and record the actual integration receipt.
All mandatory product behavior and fresh-checkout acceptance are met; main integration is still pending.

### Final acceptance and actual integration

PR46 was merged through the enforced check at `f917ebc59e46d2e4b03af7d5735be442eddbd611`
on2026-09-13T16:32:31Z. Its tree exactly matches the passing candidate `bd3cb2dbc82b20a115aa13f8655ec36e69c6d240`.
GitHub Actions main run34768895116 then passed Harness quality, including82behavioral tests, typing, Ruff,
dependency audit, documentation checks and the submitted-commit secret scan. The source commits and merge commit
all carry DCO sign-off. Branch protection was respected and remains enabled for administrators.

[Integration receipt](evidence/integration-acceptance.json) records the actual main commit, checks, protection,
evidence index and supported-use constraints. R01–R10, all six commands, fresh-checkout reproducibility and main
integration are accepted. There are no remaining product acceptance items. The final follow-up changes only this
acceptance record and its receipt; it goes through the same required check and PR merge.

Usage starts with the canonical [local harness guide](../../fern/versions/latest/pages/get-started/eval-harness.mdx).
Preserve the existing raw runs and excluded attempts. No additional model calls, release, package publication,
deployment or global setup is needed for this assignment.

## Repository presentation follow-up

User requested README and repository presentation improvements and selected English. Baseline:
`baddbeb5f632db46971abd721fc6e6f8d7838078`, clean main. Work branch: `codex/polish-repository-docs`.
This is documentation and repository-entry maintenance; R01–R10 and the six-command behavior remain accepted.

- Acceptance: README presents Eval Harness first, links install/auth → one-task run → saved results, and states the
  verified support limits. Contribution and Issue/PR entry points match the fork's actual workflow.
- Preserve the generated upstream environment-table block and its markers, NVIDIA attribution/citation and external
  materials notice, licenses, retained implementation and all existing experiment evidence.
- Canonical usage stays in Fern; requirements/spec/process records stay in .agents/development. Existing root entry
  documents are updated because the user explicitly requested repository presentation, including README.md.
- Luna owns README.md, harness/README.md and CONTRIBUTING.md. Astra owns this plan, Fern entry/guide, Issue/PR templates,
  GitHub About links and integration. No specialist review is needed for this content-only change.
- No model trials, runtime changes, dependency/lock changes, release or deployment. Check actual paths/anchors, CLI help,
  preserved generated text, Fern validation and submitted-content secrets; run the existing required CI before merge.
- Next: prepare and review the focused documentation diff, update the fork About link, then DCO commit, PR, passing
  Harness quality and main integration under the continuing repository-maintenance authorization.

Content acceptance: README, package/contribution entry points, Issue/PR templates, Fern entry/guide and GitHub About
now describe this fork consistently. The existing 177-row generated upstream table (SHA256
`b4217ffe5d81a45a919540dccd55b760417856a2d5f4bdc0e362c61843855843`), BibTeX and external-materials notice remain
byte-identical. The table stays within its original generator markers in a collapsed section. Canonical usage remains
in Fern; product code, CLI semantics, requirements, dependencies, workflows and licenses are unchanged.

Verification: 34 new local/GitHub-source links and heading anchors resolve; six CLI help commands exit0; all14existing
documentation checks pass; Fern check passes with0errors/1existing warning; Markdown structure and diff whitespace
checks pass. No model calls. Luna implemented/self-checked the three entry documents; Astra reviewed and integrated
the content and checked the affected references. Existing Harness quality remains the required merge gate.

During editing, 44 untracked files named `* 2.*` appeared. All matched known committed versions exactly (43 matched
the starting main; the plan copy matched3849a491). Their contents were preserved without deletion under
`.audit/presentation/untracked-copies/`, with original paths, hashes and matching revisions in
`.audit/presentation/untracked-duplicates.json`. They are excluded from the submission. Content checks and CLI-help
receipts are also retained locally under `.audit/presentation/`.

### README scope correction

After PR48, the user questioned the `Retained NeMo Gym project` section. Remove that introduction and the unrelated
177-row catalog from the root README; the existing origin, license, citation and external-materials notice provide
the needed attribution. A duplicate catalog page is unnecessary. This supersedes the controller's earlier choice to
keep the generated table in a collapsed README section; it changes no product requirement.

Baseline main663b70372b3630ea8c08526c1655db3a1b11ad98; branch `codex/trim-upstream-readme`. Astra owns README,
this record and the AGENTS hook note. Luna removes only the catalog's now-inapplicable pre-commit hook. Retain the
upstream utility and implementation; no runtime changes or model calls. Verify remaining links and attribution,
pre-commit YAML/other hooks, whitespace and required CI, then integrate through the protected PR route.

Content accepted: README reduced from293to100lines; all13remaining local links resolve. The complete origin/licensing,
BibTeX and external-materials notice suffix is unchanged. YAML parsing confirms the catalog hook is the only removed
hook; other hook settings remain identical. Fern check passes with0errors/1existing warning; diff whitespace passes.
No new benchmark page, generated table, runtime change or model trial was needed.

## Acceptance-evidence organization PR

User requested a new independent PR to implement the evidence-retention decision. Baseline:
`3edb1797adef6846d0b032fa190bc3e3dfda6828`, clean main; branch `codex/organize-acceptance-evidence`.
Delivery stops at an open, checked PR; do not merge this follow-up. Existing product acceptance is unchanged.

Keep a concise historical acceptance index, a consolidated acceptance summary and five actual trial records.
Consolidate the dated diary's settled reuse and isolation decisions, the quality/security snapshot and the excluded
first resume trial into the acceptance summary; remove those
three redundant standalone files. Preserve factual outcomes, source identity, condition separation, judgments, synthetic
human labels and exclusion reasons. Link full originals at the immutable baseline commit and retain Git history/raw
local runs. Clarify that local paths/hashes alone do not make original artifacts publicly retrievable.

Luna owns compaction of N/S/A, grading/aggregation and fresh-checkout JSON. Astra owns the acceptance summary, small trial
metadata, human-readable evidence entry and affected references. No model calls, runtime/CLI/requirements/dependency/CI
changes, new benchmark data, or rewrite of prior PRs. Verify retained facts against original JSON, cross-record IDs,
references, normalized paths and secret scans; use existing required CI for the PR. Original byte snapshots and hashes
are retained under `.audit/evidence-cleanup/` for this verification only.

Local content accepted: evidence is now seven files (six JSON records and one README index), 69,083 bytes /
1,681 lines, down from nine files, 84,731 bytes / 2,155 lines. Luna's self-checks and Astra's original-record
comparison preserve all trial answers, IDs, scores, rationales, synthetic-rating labels, usage/cost measurements,
and relevant hashes. All nine original-file links/hashes match immutable Git objects. Redundant all-attempt metrics
were checked equal before omission; shell command strings round-trip to the original argument arrays. Historical
CI/protection/quality receipts, all nine reuse decisions and excluded resume facts are retained. Forty-one relative
documentation references resolve; current evidence has no machine-specific absolute paths. Two local deliverables
(GDPval spreadsheet and fresh-checkout answer) still match their original recorded SHA-256.

Documentation link tests: 14 passed. Fern check: exit 0, zero errors and one existing warning. Whitespace check
passed. Content-only scope needs no new runtime tests or model calls; the new PR runs the existing Harness quality
check. Detailed one-time comparison reports stay local under `.audit/evidence-cleanup/`; this cleanup adds no new
tracked development diary. Complete publication scanning and deliver the separate PR for review without merging.
