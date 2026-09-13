<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR-10 legacy-route removal and documentation task contract

Status: frozen Sol-to-Luna implementation contract; no production change or acceptance claim is contained here.  
Date: 2026-09-13  
Immutable characterization baseline: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`  
Canonical-plan control commit: `8518f25d107d9043df449a9198fbb41b00ba1c22`  
Canonical-plan SHA-256: `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`  
Astra acceptance-map SHA-256: `ad8870927701889f4f99e9cdda33ce57aa995281d6a9db7a48fb7dd888153710`

## 1. Implementation input and stop conditions

PR-10 starts from `<PR09_ACCEPTED_HEAD_SHA>`. Before editing, Luna must substitute the migration owner's exact 40-character accepted PR-09 head, prove that it descends the accepted PR-01 through PR-09 stack, record its commit and tree, and inventory its tracked paths and imports. The initially supplied PR-02c checkpoint `9a9f144537f4dc276e18c029666be229547e371c`, its later review source `f972a82558609255f84723b9d4c060503eef894a`, and saved PR-05 through PR-09 design checkpoints are review inputs; none fills the placeholder or proves that an interface was accepted. Later corrective PR-02c commits likewise remain non-dependencies until accepted.

The interface review sources used to write this contract are exact but non-accepted: PR-05 `01f781cbeaff00aee3fb0bea3597dee3bd58e2df`, PR-06 `f598dbe34b38dcb9f5bb8f9309283c88c7a2dab9`, PR-07 `e0fab6018c59338f5301a13e29e6c5c39f5e3305`, PR-08 `4579b77f14cb0b66e0fcdb207b6fe8b7af210686`, and PR-09 `a26a92a31a7657799573337dc8c9876b440b5842`. They characterize ownership and API intent only. Luna reads the exact accepted changed-path manifests from `<PR09_ACCEPTED_HEAD_SHA>` and stops on a semantic mismatch; it never splices these checkpoint commits into the implementation base.

The following conditions stop PR-10 before deletion and return to the named owner:

| Condition found at `<PR09_ACCEPTED_HEAD_SHA>` | Return to | Required resolution |
| --- | --- | --- |
| Any accepted generation path still calls `eval_harness.local_runner`, reads its layout, or reconstructs a candidate from `results.jsonl` | PR-05 | Move the behavior to the common generation plan, RunManifest/index, and CandidateBundle loader |
| Any accepted evaluation path still calls `eval_harness.local_judge_runner` or an `eval_harness.judges.*` vendor subprocess | PR-05/06 | Use the one guarded JudgeRuntime and EvaluationRecordSink route |
| GDPval evaluator selection still yields `external`/`deferred` as scored completion or retains `gdpval-external` | PR-05/06 | Use the concrete registered v2 evaluator and typed execution-only result |
| The accepted AA profile imports a legacy resources server/orchestrator, discovers anchors by path, or needs legacy Tavily fallback/rotation | PR-08, and PR-07 for an executor capability | Resolve the profile through accepted typed inputs; do not retain a hidden fallback |
| The accepted N/S/A controller still reads legacy prompt/result layouts or filters `GDPVAL_CONDITION*` in common code | PR-09 | Use the accepted experiment plan/journal and role environment policy |
| A file in either legacy subtree below is still imported by any accepted production module after the explicit GDPval attachment-downloader migration in section 4 | Its replacement owner | Remove the import through the existing contract; do not exempt the file from deletion |

These are dependency failures, not permission for Luna to redesign another slice. PR-10 contains no model, judge, provider, subscription, paid API, release, merge, or publication work.

## 2. Outcome and ownership boundary

After PR-10:

- `./eval` is the sole Eval Harness CLI. Root `./gdpval`, its shell wrappers, recipes, aliases, and Python module entrypoints are absent; no shim or explanatory executable remains.
- generation uses the common snapshot, GenerationPlan, RunManifest/index, CandidateBundle, and generation-resume implementation;
- evaluation uses the common evaluator planner/runner, `EvaluationRecordSink.create/resume`, `EvaluationResumePolicy`, immutable `EvaluationResultRevision` history, evaluator events, and the PR-06 BattleRecord implementation;
- Stirrup application execution has one implementation in `eval_harness/executors/stirrup*.py`; local/HTTP judge invocation has one guarded PR-05 runtime path; GDPval rubric/pairwise metrics live only in `eval_harness/gdpval/**` plus `eval_harness/evaluators/gdpval.py`; AA stage/Elo meaning lives only in the accepted PR-08 path set;
- benchmark-specific names remain valid in the GDPval adapter, evaluator/profile/config assets, fixtures, and documentation. There is no blanket `gdpval` string ban and no universal-score rewrite;
- `tests/harness/test_eval_cli.sh` is the sole harness suite entrypoint and still executes the complete retained Python suite and the six logical shell suites described in section 6; and
- final docs describe only the accepted CLI/config/record paths and label real-model work as the separately authorized Gate-B phase.

PR-10 removes duplicated controllers and runtime owners. It does not alter AIME `accuracy`, BigCodeBench `pass_rate`, GDPval rubric/pairwise result meaning, AA-v2 Elo, experiment denominators, snapshot/bundle identity, executor output parsing, Builder behavior, role isolation, sandbox policy, retry policy, or coverage/audit scope.

## 3. Exact affected-path allowlist

### 3.1 Add

| Path | Purpose |
| --- | --- |
| `tests/harness/test_judge_runtime.sh` | Neutral fake-CLI replacement for the substantive guarded-judge shell checks formerly in `test_local_judge_executor.sh` |
| `tests/harness/test_experiment_cli.sh` | Profile-driven fake experiment CLI replacement for the substantive condition shell checks |
| `tests/harness/test_documented_cli_examples.py` | Execute every marked public command example through registered fakes/native no-model components |
| `tests/harness/test_gdpval_snapshot_inputs.py` | Test the adapter-owned local/HTTP attachment acquisition after the old Stirrup task module is removed |
| `tests/harness/test_quality_legacy_removal.py` | Exact tracked-path/import/retired-literal and owner-uniqueness acceptance inventory |
| `tests/harness/fixtures/cli/documented-examples-v1.json` | Strict example-ID to argv/placeholder/test-mode manifest; no credentials or runtime paths |
| `contracts/pr10-implementation-work-record.md` | Luna's base/tree, changed-path, behavior-port, deletion, command, count, and review evidence |

No added file may create a compatibility reader or production implementation.

### 3.2 Modify, with bounded purpose

| Path | Permitted PR-10 change |
| --- | --- |
| `eval_harness/benchmarks/gdpval.py` | Own the last required attachment-copy/download helper locally, remove the import from `responses_api_agents.stirrup_agent.tasks.gdpval`, and use `task_inputs` in every execution workspace/prompt/materialization path |
| `benchmarks/gdpval/prepare.py` | Remove legacy Stirrup/resources-server wording; retain the same dataset row fields and preparation behavior |
| `eval_harness/runner.py` | Remove only staged `results.jsonl`/legacy prompt-layout production and `GDPVAL_CONDITION*` filtering that survived PR-05/09; retain the accepted common coordinator and result semantics |
| `eval_harness/interventions/files.py` | Remove the staged `reference_files` reserved root left explicitly for PR-10; keep `task_inputs`, `.eval-harness`, `.cursor`, `.claude`, `.agents`, and `deliverables` protections and the same collision rules |
| `eval_harness/cli.py` | Remove stale alias/status/help branches, if present, and expose only the already accepted list/run/evaluate/experiment arguments; no new semantic option |
| `nemo_gym/_config_aliases.py` | Remove only the deleted `stirrup_agent/stirrup_gdpval` config-path alias; retain unrelated upstream aliases |
| `nemo_gym/rollout_collection.py` | Remove only the stale comment naming the deleted GDPval multistage orchestrator as a custom-driver consumer; do not change row resolution or materialized-input behavior |
| `scripts/ci/run_eval_harness_coverage.py` | Invoke `bash tests/harness/test_eval_cli.sh`; retain subprocess coverage and the exact integer 96-percent predicate |
| `pyproject.toml` | Remove `scripts/gdpval_run_metadata.py` from the strict-mypy file set; retain all accepted extras/groups, coverage settings, dependency pins, and thresholds |
| `.github/workflows/eval-harness-ci.yml` | Remove the deleted metadata-script mypy argument; rename the coverage log to `test-eval-cli.log`; retain every accepted job, runner, setup, extra/group, audit, and threshold |
| `tests/unit_tests/test_cli_main.py` | Remove the old alias-success row and add a bounded negative assertion that the deleted Stirrup flavor is not resolved; retain every unrelated alias case |
| `tests/unit_tests/test_rollout_collection.py` | Make the paired row-resolution test docstring neutral after the deleted orchestrator example is removed; do not change its assertions |
| `tests/harness/test_eval_cli.sh` | Become the neutral full-suite entrypoint described in section 6 while retaining its public CLI checks |
| `tests/harness/test_codex_executor.sh` | Exercise `./eval run` with a fake Codex process and authoritative bundle/index output; remove `./gdpval`, `check`, `GDPVAL_*`, and legacy deliverable-layout assertions |
| `tests/harness/test_claude_code_executor.sh` | Exercise accepted ordinary `./eval run` behavior with a fake Claude process; remove the old wrapper/env/check route |
| `tests/harness/test_cursor_executor.sh` | Exercise the accepted PR-02c `./eval run` task-input protection/handoff case; retain the explicit legacy-namespace rejection and remove old wrapper success behavior |
| `tests/harness/test_adapter_failure_coverage.py` | Replace imports/assertions over deleted local judge classes with the shared runtime/evaluation boundary |
| `tests/harness/test_benchmark_abstraction.py` | Change legacy GDPval workspace materialization expectations to the sealed `task_inputs` snapshot view |
| `tests/harness/test_benchmark_evaluator_edge_coverage.py` | Replace old downloader patches and external-evaluator helper tests with adapter-owned acquisition and concrete evaluator tests |
| `tests/harness/test_benchmark_snapshot.py` | Retain snapshot separation/digest tests and remove any old module import/path expectation |
| `tests/harness/test_boundary_failure_coverage.py` | Remove external-handoff/local-judge helper cases after their typed replacement cases are present; retain all unrelated boundary cases |
| `tests/harness/test_cli_registry_reliability.py` | Assert concrete evaluator IDs, execution-only, independent evaluate, new profiles, and old-command rejection; no benchmark-key evaluator alias |
| `tests/harness/test_executor_judge_reliability.py` | Use the one shared guarded JudgeRuntime and exact resume/event boundary |
| `tests/harness/test_experiment_execution_policy.py` | Add the bounded negative `GDPVAL_CONDITION*` environment case if PR-09 has not already done so |
| `tests/harness/test_generic_runner.py` | Remove imports/fixtures for external handoff, old candidate prompt lookup, and old judge types; preserve common runner tests under the accepted interfaces |
| `tests/harness/test_pairwise_evaluator.py` | Use the accepted common pairwise/GDPval runtime types and no deleted judge module |
| `tests/harness/test_reasoning_effort.py` | Remove wrapper parser/env cases; retain executor/application/judge configuration evidence cases |
| `tests/harness/test_runner_reliability.py` | Delete only the local-runner/local-judge test classes and port any still-unique durability assertion to PR-05/06/09 tests before doing so |
| `tests/harness/test_agent_skill_intervention.py` | Retain the explicit `.gdpval/interventions` rejected-target assertions allowed by section 7; accepted cases use `.eval-harness` |
| `tests/harness/test_builder_artifact.py` | Retain the explicit rejected old-manifest assertion; accepted cases use `.eval-harness` |
| `tests/harness/test_builder_inputs.py` | Retain the explicit rejected `reference_files/builder-inputs` assertion; accepted cases use `task_inputs/builder-inputs` |
| `tests/harness/test_file_intervention.py` | Assert the final reserved-root set after staged `reference_files` reservation removal |
| `tests/harness/test_quality_input_intervention_boundaries.py` | Update its exact reviewed negative-location inventory; do not hide literals by string splitting |
| `README.md` | Rewrite around the final neutral CLI and behavior table in section 8 |
| `EXPERIMENTS.md` | Document the final N/S/A v2 profile, role boundary, barriers, denominators, failures, resume, and fake-vs-Gate-B boundary |
| `UPSTREAM.md` | Describe retained upstream relationship and the new owned ports; remove claims that the old server/agent/root wrapper is active |
| `SUBSCRIPTION-EXECUTORS.md` | Rewrite local executor, authentication, task-input, sealed output, independent evaluation, role eligibility and billing guidance for `./eval`; remove old check/compare/AA routes and legacy layouts/environment flags |
| `benchmarks/gdpval/README.md` | Replace old Gym/server recipes with snapshot, explicit evaluator, AA-reproduction profile, bound-anchor, and Gate-B instructions |
| `nemotron_recipes/lightning-3.5/instruct/README.md` | Remove commands for the deleted recipe and point readers to the final Eval Harness docs without presenting a shim |
| `nemotron_recipes/lightning-3.5/reproducibility.md` | Replace the deleted recipe link with the retained GDPval adapter/profile documentation and state the separate authorization boundary |
| `nemotron_recipes/lightning-3.5/instruct/gym/.env.example` | Delete only the obsolete GDPval recipe variables/section and remove GDPval from shared-key/search comments; retain every other recipe variable byte-for-byte |
| `nemotron_recipes/lightning-3.5/instruct/gym/env.yaml.example` | Delete only the obsolete `gdpval_judge_model` block; retain every other model/config block byte-for-byte |
| `UPSTREAM-ENVIRONMENTS.md` | Run the accepted generator after deletions and commit its exact output only if it changes; never hand-edit or remove the unrelated Terminal Multi Harness Stirrup row |

If an accepted predecessor has already removed a bounded item in this table, Luna records `already absent at base` and does not recreate it. A need to edit another production, workflow, dependency, config, or documentation path returns to Sol before editing.

### 3.3 Delete exactly

Delete these individual entrypoints/controllers/configs:

```text
gdpval
scripts/gdpval_provider.sh
scripts/gdpval_preflight.sh
scripts/gdpval_run_metadata.py
eval_harness/local_runner.py
eval_harness/local_judge_runner.py
eval_harness/judges/__init__.py
eval_harness/judges/base.py
eval_harness/judges/claude_code.py
eval_harness/judges/codex.py
eval_harness/judges/pairwise.py
benchmarks/gdpval/config.yaml
nemotron_recipes/lightning-3.5/instruct/gym/gdpval/build-gdpval-sif.sh
nemotron_recipes/lightning-3.5/instruct/gym/gdpval/gdpval.sh
tests/harness/test_gdpval_cli.sh
tests/harness/test_local_judge_executor.sh
tests/harness/test_experiment_conditions.sh
tests/harness/test_experiment_conditions.py
tests/harness/test_local_judge_executors.py
tests/harness/test_local_judge_isolation.py
tests/harness/test_local_judge_pairwise.py
tests/harness/test_local_judge_runner.py
tests/harness/test_local_judge_runner_control.py
```

Delete every tracked file in `resources_servers/gdpval/` at the accepted base. The immutable-baseline manifest is:

```text
resources_servers/gdpval/README.md
resources_servers/gdpval/__init__.py
resources_servers/gdpval/app.py
resources_servers/gdpval/comparison.py
resources_servers/gdpval/configs/gdpval.yaml
resources_servers/gdpval/data/.gitignore
resources_servers/gdpval/data/example.jsonl
resources_servers/gdpval/data/example_metrics.json
resources_servers/gdpval/data/example_rollouts.jsonl
resources_servers/gdpval/judge_panel.py
resources_servers/gdpval/multistage_elo.py
resources_servers/gdpval/multistage_orchestrator.py
resources_servers/gdpval/preconvert.py
resources_servers/gdpval/prompts/judge_prompt.j2
resources_servers/gdpval/requirements.txt
resources_servers/gdpval/scoring.py
resources_servers/gdpval/setup_libreoffice.py
resources_servers/gdpval/task_data.py
resources_servers/gdpval/tests/__init__.py
resources_servers/gdpval/tests/test_app.py
resources_servers/gdpval/tests/test_multistage_elo.py
resources_servers/gdpval/tests/test_multistage_orchestrator.py
resources_servers/gdpval/tests/test_preconvert.py
resources_servers/gdpval/tests/test_setup_libreoffice.py
```

Delete every tracked file in `responses_api_agents/stirrup_agent/` at the accepted base. The immutable-baseline manifest is:

```text
responses_api_agents/stirrup_agent/README.md
responses_api_agents/stirrup_agent/__init__.py
responses_api_agents/stirrup_agent/app.py
responses_api_agents/stirrup_agent/apptainer_provider.py
responses_api_agents/stirrup_agent/client.py
responses_api_agents/stirrup_agent/configs/stirrup_agent.yaml
responses_api_agents/stirrup_agent/containers/gdpval.def
responses_api_agents/stirrup_agent/data/.gitignore
responses_api_agents/stirrup_agent/data/example.jsonl
responses_api_agents/stirrup_agent/file_reader.py
responses_api_agents/stirrup_agent/finish_tool_coercing.py
responses_api_agents/stirrup_agent/nemo_agent.py
responses_api_agents/stirrup_agent/nemo_client.py
responses_api_agents/stirrup_agent/overrides.txt
responses_api_agents/stirrup_agent/prompts/gdpval_user_prompt.txt
responses_api_agents/stirrup_agent/prompts/system_prompt.j2
responses_api_agents/stirrup_agent/prompts/user_prompt.j2
responses_api_agents/stirrup_agent/requirements.txt
responses_api_agents/stirrup_agent/setup_scripts/gdpval.sh
responses_api_agents/stirrup_agent/stirrup_utils.py
responses_api_agents/stirrup_agent/task_distribution.py
responses_api_agents/stirrup_agent/task_strategy.py
responses_api_agents/stirrup_agent/tasks/__init__.py
responses_api_agents/stirrup_agent/tasks/gdpval.py
responses_api_agents/stirrup_agent/tavily_search.py
responses_api_agents/stirrup_agent/tests/__init__.py
responses_api_agents/stirrup_agent/tests/test_app.py
responses_api_agents/stirrup_agent/tests/test_apptainer_provider.py
responses_api_agents/stirrup_agent/tests/test_finish_tool_coercing.py
responses_api_agents/stirrup_agent/tests/test_nemo_client.py
responses_api_agents/stirrup_agent/tests/test_task_distribution.py
responses_api_agents/stirrup_agent/tests/test_tasks_gdpval.py
responses_api_agents/stirrup_agent/tests/test_tavily_search.py
```

The accepted predecessor stack was required to leave both subtrees behaviorally unchanged, apart from the temporary legacy requirements pin authorized by PR-07. Any additional tracked file under either subtree is an unexpected expansion and stops deletion for Sol review; Luna does not silently preserve or delete an unreviewed addition.

### 3.4 Retain and do not duplicate

| Retained path/set | Sole retained responsibility |
| --- | --- |
| `benchmarks/gdpval/__init__.py`, `benchmarks/gdpval/prepare.py`, `benchmarks/gdpval/data/.gitignore`, `eval_harness/benchmarks/gdpval.py` | Dataset preparation, row normalization, acquisition and separate snapshot views |
| `config/gdpval-aa-v2-references.tsv` plus the accepted PR-08 manifests/configs | Nine anchor IDs/fixed Elo and hash-bound AA profile inputs; absence of anchor bundle hashes still blocks a formal run |
| `eval_harness/gdpval/__init__.py`, `scoring.py`, `presentation.py`, `panel.py`, `records.py`, and `prompts/*` | PR-06 renderer/parser/panel/BattleRecord behavior with NVIDIA attribution |
| `eval_harness/evaluators/gdpval.py` and the explicit evaluator registry entries | `gdpval.rubric.binary@2`, `gdpval.rubric.structured@2`, and `gdpval.pairwise@2`; no external/deferred alias |
| `eval_harness/evaluation_runner.py`, `evaluation_records.py`, `generation_runner.py`, `judge_runtime.py`, and `execution_policy.py` | Common plans, sinks/resume, generation, guarded judge transport, and role-policy primitives |
| The exact paths and behaviors in the accepted PR-02c and PR-05 changed-path manifests, including `tests/harness/test_generation_handoff.py` and the Cursor legacy-input rejection tests | Typed generation handoff, task-input protection, CandidateBundle/index durability, independent evaluation and verified resume; PR-10 may adjust only the separately allowlisted old-route joins |
| `eval_harness/executors/{codex,claude_code,cursor,stirrup,stirrup_config,stirrup_runtime,stirrup_sandbox}.py` and `nemo_gym/server_utils.py` | One application executor per vendor and the measured PR-07 Stirrup runtime/shared HTTP seam |
| PR-07 fixtures under `tests/harness/fixtures/executor_protocol/stirrup/` and its supported-runtime tests | Synthetic runtime and real contained-platform proof; the deleted production GDPval SIF recipe is not an alternate |
| The exact production/test/config paths introduced by the accepted PR-08 changed-path manifest | AA planner/journal/stage aggregate only. The saved design did not freeze production filenames, so PR-10 records and protects the accepted manifest instead of inventing names |
| `eval_harness/experiments/**`, `eval_harness/builders/**`, `.eval-harness` Agent Skill implementation, and `config/experiments/alps-skill-creation.json` | PR-09 N/S/A, Builder, role boundary, journal and neutral intervention behavior |
| `eval_harness/evaluators/aime26.py`, `eval_harness/evaluators/bigcodebench.py`, the accepted BigCode boundary modules/locks, and their tests | Existing named native metrics and the single accepted grader supervisor |
| Every non-GDPval `benchmarks/`, `resources_servers/`, `responses_api_agents/`, recipe, test, config and documentation asset | Unchanged upstream functionality; substring similarity to Stirrup/GDPval is not deletion authority |

`responses_api_models/**`, `resources_servers/terminal_multi_harness/**`, and its Stirrup-named rulebook/config are unrelated and stay. `uv.lock` and `ATTRIBUTIONS.md` stay unless an independently reviewed accepted dependency change requires an exact update; deleting an uninstalled legacy subtree is not permission to re-resolve dependencies or remove attribution.

## 4. Exact final migration joins

| Deleted source behavior | Required retained owner and pre-deletion proof |
| --- | --- |
| `_download_reference_files` in `responses_api_agents/stirrup_agent/tasks/gdpval.py` | Move its required local-file and HTTP/HF-auth acquisition into `eval_harness/benchmarks/gdpval.py`; inject transports in tests, validate every normalized target before a write, fail the snapshot on a missing/partial result, and bind copied bytes. No warning-and-continue outcome becomes a sealed snapshot |
| Stirrup server/Ray/session/tools/Apptainer/finish code | PR-07 `eval_harness/executors/stirrup*.py`; fake generation proves `/verify` and scoring are never invoked; supported-runtime proof uses the exact contained implementation |
| Legacy Tavily rotation/fallback | No retained owner in PR-07 schema v1. Delete it only after the accepted formal profiles prove they do not require that capability. A needed capability blocks PR-10; it is never simulated by network access or kept as a hidden import |
| Resources-server rubric/presentation/parser | PR-06 `eval_harness/gdpval/{scoring,presentation}.py` and prompts, through the common JudgeRuntime |
| Resources-server comparison/panel | PR-06 `panel.py`, `records.py`, and concrete pairwise evaluator; invalid response remains `invalid_response`, never an inferred tie |
| Resources-server multistage/task distribution/controller/cache | Accepted PR-08 task/stage/anchor planner, immutable event journal, common generation resume, BattleRecord join and pure aggregate |
| Old local runner/deliverable copy/resume metadata | PR-02c/05 snapshot, generation plan/record, RunManifest/index, CandidateBundle and exact-prefix resume |
| Old local judge paths/prompts/results/cache | PR-05/06 BoundEvaluationView, anonymous projection, EvaluationRecordSink/revisions/evaluator events and BattleRecord evidence |
| `gdpval-external`, exported deliverable handoff and deferred completion | Explicit `--execution-only` or the selected concrete evaluator; execution-only prints no metric/evaluated-success claim |
| `GDPVAL_CONDITION*`, old experiment prompt injection and mutable `experiment-metadata.json` | PR-09 strict profile inputs, one snapshot/application/evaluator setup, N/S/A plan/journal, role-scoped environment and fixed denominators |
| `.gdpval/interventions` and `reference_files/builder-inputs` | `.eval-harness/interventions/agent-skills` and `task_inputs/builder-inputs`; rejected old literals remain only in the exact negative list |
| Root/provider/preflight/metadata/recipe shell | Public `./eval` parser, typed executor/evaluator/profile configs, no-model preflight, semantic records and provenance |

The attachment helper is the only behavior migrated during PR-10. Every other row consumes an accepted predecessor and permits deletion/tests/docs only. If implementing a row requires new semantic code, return it to its owner.

## 5. Deletion order

1. Bind `<PR09_ACCEPTED_HEAD_SHA>`, inventory the accepted changed paths/import graph, and fill the PR-10 work record.
2. Port the attachment helper and its no-network deterministic tests. Add the neutral shell replacements and documented-example harness while every old file is still available for behavior comparison.
3. Run the replacement tests directly and show that production fake executions never import/call either legacy subtree, local runner, local judge runner, or old judge package.
4. Change `test_eval_cli.sh`, the coverage driver, workflow log/type paths, and `pyproject.toml`; run the neutral entrypoint successfully while `test_gdpval_cli.sh` still exists but is not invoked.
5. Rewrite documentation and remove source/config/alias references. Regenerate `UPSTREAM-ENVIRONMENTS.md` with its existing generator and accept only deterministic expected changes.
6. Delete the exact files/subtrees in section 3.3. Remove no unrelated file.
7. Run the exact retired-literal/import/path inventory, focused tests, full suite, strict types, coverage, dependencies/audit, supported-runtime jobs, copyright/secrets and DCO gates. A later source change invalidates the evidence and reruns affected gates.

No step truncates or rewrites historical output/log directories. New loaders reject old schemas/paths and do not discover or convert them.

## 6. Neutral suite entrypoint and behavior-port map

`tests/harness/test_eval_cli.sh` is an executable Bash script with `set -euo pipefail`. It resolves the repository root from its own location, syntax-checks itself, `eval`, and the five child scripts, compiles the complete tracked `eval_harness/**/*.py` set without writing bytecode into the source tree, runs `python3 -m unittest discover -s tests/harness -p 'test_*.py'`, invokes the child scripts in this fixed order, and finally prints exactly `eval harness self-test passed`:

1. `tests/harness/test_codex_executor.sh`
2. `tests/harness/test_claude_code_executor.sh`
3. `tests/harness/test_cursor_executor.sh`
4. `tests/harness/test_judge_runtime.sh`
5. `tests/harness/test_experiment_cli.sh`

The entrypoint itself is the sixth logical shell suite. It must not invoke itself, `test_gdpval_cli.sh`, a deleted script, a legacy recipe, or a real service. `scripts/ci/run_eval_harness_coverage.py` invokes it as a subprocess so child Python processes continue to emit/merge coverage data.

| Retired test responsibility | Replacement assertion before deletion |
| --- | --- |
| Root help/provider/executor listing and invalid combinations | Neutral CLI help plus all five registry listings; explicit Stirrup config/model/role checks in PR-07 and CLI fake tests |
| Provider shell environment mutation | Strict PR-07 config and role-approved environment tests; no provider preset or lookup chain |
| Metadata/reasoning/resume fingerprints | RunManifest, GenerationPlanRecord, evaluator configuration, EvaluationResumePolicy, experiment journal and typed executor evidence tests |
| Codex/Claude/Cursor shell execution | Same three shell files using `./eval run`, fake local binaries, authoritative index/bundle reload, fresh outputs and zero network/model calls |
| Local judge anonymous staging, root-deny, secret removal, invalid verdict, interruption and no-overwrite | `test_judge_runtime.sh`, PR-05 evaluation runner/records/execution-policy tests, and PR-06 presentation/panel/records/judge-runtime tests |
| Old condition file/label isolation, invalid input, mutation and resume mismatch | PR-09 strict profile/experiment-policy/journal tests plus `test_experiment_cli.sh`; labels remain outer-only and missing arms stay in denominators |
| External GDPval handoff/copy helpers | Concrete `test_gdpval_evaluator.py` and PR-06 v2 tests; no exported legacy deliverables directory |
| Resource parser/panel/Elo/controller tests | PR-06 scoring/presentation/panel/records fixtures and PR-08 stage/cross-stage/resume fixtures, including numeric Elo outputs |
| Legacy Stirrup server tests | PR-07 config/executor/runtime/sandbox/dependency/supported-runtime tests and shared `server_utils` tests |
| Old AA wrapper/recipe assertions | PR-08 formal/partial profile tests through common generation/evaluation, with no old-process invocation |

Pure assertions about removed command spelling may be deleted. A security, durability, parsing, metric, failure, resume, denominator, or information-boundary assertion must have an exact replacement case named in `contracts/pr10-implementation-work-record.md`; deleting it without a replacement fails review.

## 7. Honest retired-literal and route inventory

`tests/harness/test_quality_legacy_removal.py` scans tracked executable/config/test/doc surfaces. It excludes only immutable migration/design records under `contracts/`, Git metadata, generated caches/results, and third-party/upstream historical changelogs. It does not split, concatenate, encode, or dynamically construct a retired string to create a false zero-hit result.

The reviewed nonzero exceptions are exact:

| Literal | Permitted path(s) and use |
| --- | --- |
| `./gdpval` or root path `gdpval` | `tests/harness/test_eval_cli.sh` may assert that the tracked/executable root is absent; `tests/harness/test_quality_legacy_removal.py` contains the scanner needle and expected-location map |
| `responses_api_agents/stirrup_agent/configs/stirrup_gdpval.yaml` | `tests/unit_tests/test_cli_main.py` may assert that the removed alias is unresolved; quality scanner contains the needle/map |
| `.gdpval/interventions` | `tests/harness/test_agent_skill_intervention.py` and `tests/harness/test_builder_artifact.py` may construct only rejected manifests/targets; `tests/harness/test_quality_input_intervention_boundaries.py` and the new quality scanner contain needles and exact location lists |
| `reference_files/builder-inputs` | `tests/harness/test_builder_inputs.py` may construct only a rejected target; the two quality scanners contain needles/location lists |
| `GDPVAL_TASK.md` | `tests/harness/test_cursor_executor.py` and `tests/harness/test_cursor_executor.sh` may assert only that the retired task file is never accepted/materialized; `tests/harness/test_quality_legacy_removal.py` contains the scanner needle/location map |
| `GDPVAL_CONDITION`, `GDPVAL_CONDITION_FILE`, `GDPVAL_CONDITION_APPLIED` | `tests/harness/test_experiment_execution_policy.py` may supply them only as rejected unallowlisted role-environment keys; the quality scanner contains needles/map |
| Deleted module/script/subtree/recipe names | Only `tests/harness/test_quality_legacy_removal.py` scanner needles/map; there is no import, invocation, fallback or path discovery |

The scanner must distinguish legitimate GDPval names in `eval_harness/benchmarks/gdpval.py`, `eval_harness/evaluators/gdpval.py`, `eval_harness/gdpval/**`, accepted PR-08 assets, tests and docs from retired route strings. `reference_files` as an upstream dataset column is likewise legitimate; `reference_files/builder-inputs` and execution-workspace readers are not. Cursor's accepted fail-closed guard may name a top-level `reference_files` directory in its own negative error/test, but cannot materialize or read it.

Any exception outside the table fails. A listed occurrence also fails if it participates in a success path, alias, import, compatibility read, output write, or fallback. The work record includes the exact `rg`/tracked-path outputs, not only a count.

## 8. Public documentation and executable examples

The four public verbs are exactly list, run, evaluate and experiment as exposed by the accepted parser:

```text
./eval benchmarks
./eval executors
./eval evaluators
./eval interventions
./eval profiles
./eval run BENCHMARK ...
./eval evaluate --snapshot SNAPSHOT_DIR --candidate BUNDLE_DIR ...
./eval experiment PROFILE ...
```

Every complete Eval Harness command block in `README.md`, `EXPERIMENTS.md`, `SUBSCRIPTION-EXECUTORS.md`, and `benchmarks/gdpval/README.md` receives a stable example ID that also appears once in `tests/harness/fixtures/cli/documented-examples-v1.json`. External vendor login/status commands are labeled prerequisites rather than Eval Harness examples. The fixture stores each harness command's exact argv token sequence and typed placeholders; the test substitutes fresh paths and synthetic bytes, invokes the real CLI parser/dispatch with ordinary registered fake factories or the accepted native no-model verifier, and asserts exit status plus semantic output. It may inject factories through accepted registry seams; it may not patch the runner, fabricate RunResult rows/CandidateBundles, bypass a sink, or call a model/network service.

At minimum these exact example forms are present and exercised:

| Example ID | Documented command form | Fake/no-model expected result |
| --- | --- | --- |
| `list-all-v1` | the five list commands above | Deterministic truthful IDs/revisions/capabilities; no constructor side effect or service call |
| `run-execution-only-v1` | `./eval run gdpval --executor codex --execution-only --limit 1 --out RUN_ROOT --runtime-root RUNTIME_ROOT` | One sealed/indexed candidate, zero evaluator calls, no metric or evaluated-success field |
| `run-native-v1` | `./eval run aime26 --executor codex --limit 1 --out RUN_ROOT --runtime-root RUNTIME_ROOT` | Registered default `aime26-native`, one `accuracy` numerator/denominator, no judge |
| `run-claude-execution-only-v1` | `./eval run gdpval --executor claude-code --execution-only --limit 1 --out RUN_ROOT --runtime-root RUNTIME_ROOT` | One sealed/indexed candidate through the fake Claude command; zero evaluator calls and no metric |
| `run-cursor-execution-only-v1` | `./eval run gdpval --executor cursor --execution-only --limit 1 --out RUN_ROOT --runtime-root RUNTIME_ROOT` | One sealed/indexed candidate through the fake Cursor command; exact `task_inputs` protection/restore and zero evaluator calls |
| `run-stirrup-v1` | `./eval run gdpval --executor stirrup --executor-config STIRRUP_CONFIG --model MODEL_ID --execution-only --limit 1 --out RUN_ROOT --runtime-root RUNTIME_ROOT` | Strict fake Stirrup transport generates and seals only; no `/verify`, evaluator or real provider |
| `reevaluate-v1` | `./eval evaluate --snapshot SNAPSHOT_DIR --candidate BUNDLE_DIR --evaluator aime26-native --out EVALUATION_ROOT --match-occurrence-id docs-reeval-0001` | Runtime already deleted; moved snapshot/bundle load strictly; same named semantic result |
| `reevaluate-pairwise-v1` | `./eval evaluate --snapshot SNAPSHOT_DIR --candidate BUNDLE_A --candidate BUNDLE_B --evaluator gdpval.pairwise@2 --evaluator-config EVALUATOR_CONFIG --out EVALUATION_ROOT --match-occurrence-id docs-pairwise-0001` | Two strictly loaded bundles, fake guarded judge runtime, planned trials and W/L/T coverage; no local-judge subprocess or inferred tie |
| `experiment-nsa-v1` | `./eval experiment config/experiments/alps-skill-creation.json --input-root skill-creator=SKILL_CREATOR_DIR --input-root alps-work-design=ALPS_DIR --limit 1 --order-seed 42 --builder-executor codex --executor codex --out EXPERIMENT_ROOT --runtime-root RUNTIME_ROOT` | N zero Builder calls; S/A protected fake builds; candidates seal before evaluation; all planned denominators visible |
| `aa-formal-preflight-v1` | `<PR08_ACCEPTED_FORMAL_PROFILE_COMMAND>` | Exact formal profile selection with complete synthetic 220-task/nine-anchor manifests reaches successful no-model preflight only; zero generation/judge calls |

If the accepted PR-05/07/09 parser uses a different already-frozen option spelling, this table is amended by Sol before Luna edits; Luna does not add an alias to make the example pass. `<PR08_ACCEPTED_FORMAL_PROFILE_COMMAND>` is an explicit acceptance-time interface placeholder, not executable documentation. The saved PR-08 design did not freeze a production filename or exact formal/partial CLI spelling. Before Luna begins, Sol replaces that cell by copying the exact command and required executor/evaluator inputs from the accepted PR-08 changed-path manifest, then records the substitution in the work record. The resulting example tests preflight with complete synthetic fixture manifests and zero model calls. Do not invent a config path or present the six-task characterization profile as the formal 220-task profile.

The documentation also states:

- `aime26-native` reports `accuracy`; `bigcodebench-tests` reports `pass_rate`; GDPval rubric reports its named rubric metric; pairwise reports W/L/T and coverage; AA reproduction reports its stage/headline namespaces only when formally complete. No universal score is printed.
- execution-only is generation, never scored completion. Evaluator and judge runtime/model/auth/config are explicit, and a missing required config fails before generation.
- candidate/evaluation/experiment output roots are fresh; external runtime roots can be deleted; reevaluation reads the sealed snapshot, manifest/index and CandidateBundles only.
- the formal AA reproduction needs all nine hash-bound anchors, exact 220-task snapshot, panel/trials/positions/seeds and accepted runtime configuration. A partial profile has a separate ID/metric namespace.
- N/S/A uses one snapshot/application/evaluator configuration, sealed groups and fixed planned denominators; Builder inputs and application artifacts cross only their declared boundaries.
- supported local Codex and contained Stirrup role policies, the BigCode supported-platform grader job, and their limits are described precisely. Ordinary workspace separation is not called an OS sandbox.
- deterministic CI uses fakes and native verifiers. Gate B requires separate authorization and real credentials/artifacts; docs make no performance, official-AA-reproduction, ALPS-benefit, or live-vendor claim.

## 9. Deterministic tests and expected outcomes

1. Before deletion, an import/call sentinel around every legacy root shows zero use during fake `run`, independent `evaluate`, AA fixture, and N/S/A fixture paths.
2. GDPval snapshot acquisition copies local/file URLs, exercises an injected HTTP response/retry without public network, passes only the approved HF auth value operationally, normalizes names under `task_inputs`, preserves exact bytes, detects source mutation, rejects unsafe/colliding names and partial downloads, and never persists a credential.
3. Neutral shell entrypoint behavior and fixed order match section 6. Coverage sees child processes and prints `eval harness self-test passed`.
4. Every documented harness example, including the minimum rows in section 8 after its accepted-interface substitution, runs with fresh roots/fakes. Execution-only has zero evaluation jobs; reevaluation works after runtime deletion and whole-run relocation; examples contain no unsupported alias.
5. Every substantive retired test assertion has a passing named replacement. Invalid/ambiguous judge response is not a tie; interruption and resumed revisions/events retain old bytes; completed/eligible-partial jobs do not replay; retryable terminal/skipped work advances only under the exact stored `EvaluationResumePolicy`.
6. Deletion inventories are exact. Import discovery cannot resolve deleted modules; old root/config aliases and old CLI verbs fail; no accepted success route scans old layouts.
7. The literal scanner reports exactly the reviewed negative locations and proves each is rejection/scanner code. There is no string obfuscation and no unexpected hit.
8. One implementation owns each vendor/runtime/metric category. Static imports and fake call counters show no second Stirrup server, Codex/Claude judge subprocess, GDPval scorer/panel/Elo fold, BigCode grader launch, or generic metric averaging path.
9. All historical output fixtures outside deleted example-only subtrees remain untouched. Unsupported old run roots are rejected without deletion, repair, import fallback or conversion.

## 10. Quality gates and completion

Run the accepted final workflow commands on the exact PR-10 candidate head. At minimum:

- `uv lock --check --offline` passes and `uv.lock` is byte-identical unless a separately accepted dependency change says otherwise;
- the locked harness environment includes the accepted `dev`, `eval-harness`, and Stirrup executor dependency scopes;
- Ruff check and format check cover the same production/test scope;
- strict mypy covers `eval_harness`, `tests/harness`, `scripts/ci/run_eval_harness_coverage.py`, `scripts/update_env_list.py`, and the existing updater/HF unit tests, with only the deleted metadata path removed;
- the subprocess-aware coverage sequence runs the neutral entrypoint and satisfies `covered_lines * 100 >= num_statements * 96`; neither measured source nor exclusions narrow;
- dependency exports retain hashes and the accepted extras/groups, strict aliased `pip-audit` is clean, and separately locked grader/build/runtime dependencies remain audited by their dedicated jobs;
- PR-04's real supported-platform grader boundary and PR-07's real supported Stirrup containment tests still pass without mocks/skips; and
- inventory, copyright, secret, DCO and all unchanged required checks pass.

`contracts/pr10-implementation-work-record.md` records base/head/tree, full diff paths, deleted-path manifest, behavior-port table, exact commands, test counts, coverage numerator/denominator, audit scope/results, supported-job URLs, reviewed negative hits, review findings and unresolved items. It contains no secrets or synthetic success claim. PR-10 is complete only when the unresolved mandatory count is zero and independent Sol review accepts the exact head. The PR remains Draft; no merge or Actions dispatch is authorized by this contract.

## 11. Prohibitions and escalation

- No production compatibility shim, alias, dual writer/reader, schema converter, old path search, environment fallback, warning-and-continue acquisition, or retained importable stub.
- No new transport, JudgeRuntime, record sink, resume journal, panel selector, Elo implementation, universal score, benchmark/ALPS branch in common code, or duplicated vendor parser.
- No real model/judge/provider/web call, credential, release, publication, force push, merge, control-branch edit, or history/output deletion.
- No skipped/xfail/deselected security or supported-runtime acceptance, coverage/type/audit reduction, arbitrary CVE allowlist, or test removal without the section 6 mapping.

An API/path conflict with an accepted predecessor returns to the responsible Sol owner with the exact callsite and required delta. A change to migration policy, retained functionality, quality strength, or Gate-A meaning returns to Astra.
