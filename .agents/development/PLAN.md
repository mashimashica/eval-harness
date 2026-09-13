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
[discovery and boundaries](evidence/2026-09-13.md). Other rows remain open until their full criteria are verified.

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
| Integration | main commit, required fork CI pass, DCO, security scans, reproducible user docs | not met |

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
