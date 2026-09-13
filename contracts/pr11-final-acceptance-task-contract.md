<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR-11 fourth-benchmark and final-acceptance task contract

Status: frozen Sol-to-Luna implementation contract; this file is design evidence, not implementation or final acceptance.  
Date: 2026-09-13  
Immutable characterization baseline: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`  
Canonical-plan control commit: `8518f25d107d9043df449a9198fbb41b00ba1c22`  
Canonical-plan SHA-256: `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`  
Astra acceptance-map SHA-256: `ad8870927701889f4f99e9cdda33ce57aa995281d6a9db7a48fb7dd888153710`

## 1. Implementation input and stop conditions

PR-11 starts from `<PR10_ACCEPTED_HEAD_SHA>`. Luna substitutes the migration owner's exact 40-character accepted PR-10 head only after it exists, proves ancestry through the accepted PR-01 through PR-10 stack, and records the source commit and tree. Saved design/checkpoint heads, including current PR-02c/05/07 inputs, never fill this placeholder.

The final evidence record substitutes `<FINAL_PR11_HEAD_SHA>` only after source review freezes the exact candidate. A deterministic check run is credited only when it ran that head, or when its recorded synthetic-merge tree is byte-for-byte equal to that head's tree.

Stop before editing and return the exact finding to its owner if the accepted base lacks any contract used below: injectable fresh `BenchmarkRegistry` and `EvaluatorRegistry`; common generation and strict resume; typed CandidateBundle load; independent evaluation and `EvaluationRecordSink.create/resume`; the accepted PR-09 experiment runner, journal, protected Builder/application executor binding, and unary group strategy; or the neutral PR-10 suite entrypoint. PR-11 closes integration evidence. It does not redesign or repair a predecessor in common code.

No model, judge, provider, public network, paid API, credential, release, merge, publication, Actions dispatch, or control-state edit is authorized.

## 2. Exact outcome and ownership boundary

PR-11 adds a small test fixture benchmark named `orchard-notes`, registers it and its unary evaluator in fresh ordinary registries, generates a real CandidateBundle with a fake runtime and intervention, reloads and reevaluates the bundle after runtime deletion and durable relocation, and drives the same benchmark through the accepted N/S/A Builder handoff. This proves that a fourth benchmark can use the completed contracts without a GDPval/AIME/BigCode/ALPS branch.

The fixture evaluator ID is `orchard-notes-exact`, revision `1`, cardinality one. Its only metric is `note_exact_match`; the metric's explicit numerator and denominator are preserved. This fixture supplies no universal `score`, no aggregate across unrelated metrics, and no pairwise/Elo behavior.

The registration is test-scoped. Each test creates fresh `BenchmarkRegistry` and `EvaluatorRegistry` instances, registers exact descriptors/factories through their public methods, and passes them through the accepted orchestration injection seam. It neither mutates a module-level default registry nor advertises a synthetic benchmark in public production listings. Duplicate, case-folding, and Unicode-normalization collisions fail before factory construction.

There is no Builder registry in the accepted design. The experiment uses the ordinary accepted `ExecutorSkillBuilder` construction/factory seam with a protected bound Builder executor. Luna must not invent a registry, plugin framework, benchmark-specific Builder, or alternate experiment runner to satisfy the word “registration.”

PR-11 may add only test fixture code/assets, one integration test, and its work record. It may not modify a production module, common runner, Executor, Builder, Intervention, snapshot, generation, CandidateBundle, evaluator runner/sink, experiment runner/journal, CLI, workflow, dependency file, config, or public documentation. A required production change is an unresolved predecessor defect and stops the slice.

## 3. Exact affected-path allowlist

PR-11 adds exactly these tracked paths:

```text
contracts/pr11-final-acceptance-record.md
tests/harness/fixtures/fourth_benchmark/__init__.py
tests/harness/fixtures/fourth_benchmark/adapter.py
tests/harness/fixtures/fourth_benchmark/evaluator.py
tests/harness/fixtures/fourth_benchmark/README.md
tests/harness/fixtures/fourth_benchmark/data/dataset.jsonl
tests/harness/fixtures/fourth_benchmark/data/task_inputs/source.txt
tests/harness/fixtures/fourth_benchmark/data/evaluation/expected-note.txt
tests/harness/fixtures/fourth_benchmark/intervention/style.md
tests/harness/fixtures/fourth_benchmark/builder_inputs/creator-kit/SKILL.md
tests/harness/fixtures/fourth_benchmark/builder_inputs/added-method/method.md
tests/harness/fixtures/fourth_benchmark/expected-results.json
tests/harness/test_fourth_benchmark_extension.py
```

There are no modify, rename, or delete paths. The accepted neutral `tests/harness/test_eval_cli.sh` discovers the new Python test through its existing full `unittest` discovery; PR-11 does not add another suite entrypoint or edit the neutral one. The work record is evidence only and contains no executable behavior.

Python and Markdown additions carry the repository's NVIDIA-2026/Apache-2.0 SPDX header. JSON/JSONL and semantic plain-text fixture bytes do not accept comments; their SHA-256 values and intentional lack of comment headers are recorded in the fixture README and work record.

The following path sets are expressly forbidden in the PR-11 diff:

```text
.github/**
README.md
EXPERIMENTS.md
UPSTREAM.md
UPSTREAM-ENVIRONMENTS.md
benchmarks/**
config/**
eval_harness/**
nemo_gym/**
nemotron_recipes/**
pyproject.toml
resources_servers/**
responses_api_agents/**
scripts/**
uv.lock
```

If a predecessor already owns an accepted fourth-fixture path with the same name, that is a collision, not permission to overwrite it. Sol supplies a new unrelated fixture ID and amends this contract before Luna continues.

## 4. Fixture contract

### 4.1 Benchmark and views

The fixture dataset contains exactly one task, `orchard-note-001`, and a pinned source/revision declared available. Its canonical prompt asks the application to read `task_inputs/source.txt` and write `deliverables/note.txt`. The public source file contains a short deterministic orchard observation. The expected response is stored separately in `data/evaluation/expected-note.txt`.

`adapter.py` implements the accepted `Benchmark` interface only for test use. `prepare` validates the pinned local assets and performs no download. `load_tasks(limit)` returns the one task for a positive limit and keeps expected bytes out of `TaskSpec`, materialization, and application-visible metadata. `snapshot_source_paths` binds every source byte. Snapshot acquisition produces all accepted view manifests and exact hashes:

| View | Visible fixture bytes | Forbidden bytes |
| --- | --- | --- |
| Canonical/controller | task ID, canonical prompt, pinned source/revision and view identities | runtime attempts, evaluator result |
| BuilderView | the task text and only the controller-selected Builder inputs for that arm | expected note, evaluator config/outcome, another arm |
| ExecutionView | canonical prompt and `task_inputs/source.txt` | expected note, Builder source roots, arm/condition label |
| EvaluationView | expected-note bytes and the minimum task/rubric identity needed by the evaluator | Builder runtime/source, application runtime, another task |

The test asserts complete file-set equality for each materialized view, absence of `expected-note.txt` from application and Builder workspaces, exact content digests, source-mutation rejection, and strict reload after the original source directory is unavailable. Acquisition never reads a public service.

### 4.2 Registry and evaluator

The fixture registers a `BenchmarkDescriptor` for exact ID `orchard-notes` whose default evaluator reference is exact ID `orchard-notes-exact`. It registers an `EvaluatorDescriptor` with candidate count one, native/no-judge type, revision `1`, no network/runtime requirement, and only fixture assets. Factories accept only the configuration allowed by the accepted registry contract and must return objects whose IDs, revision, cardinality, canonical configuration, and configuration digest match their descriptors.

`evaluator.py` implements the accepted unary `Evaluator` contract. It receives one verified candidate reference and one EvaluationView through `EvaluationJobRequest`; it does not discover filesystem roots. It reads only the CandidateBundle-declared `note.txt` deliverable, checks its bound size/hash, decodes strict UTF-8, and normalizes at most one terminal LF from both candidate and expected bytes. It performs an exact comparison after that stated normalization. It emits exactly one of these semantic outcomes:

| Input state | `EvaluationStatus` | Metric | Semantic outcome/failure |
| --- | --- | --- | --- |
| Exact note | `completed` | `note_exact_match`: numerator `1`, denominator `1`, value `1.0` | `exact_match` |
| Valid different note | `completed` | numerator `0`, denominator `1`, value `0.0` | `content_mismatch` |
| Valid bundle declares no `note.txt` | `completed` | numerator `0`, denominator `1`, value `0.0` | `no_deliverable`; no file is fabricated |
| Structurally valid artifact has non-UTF-8 note bytes | `invalid` | none | task-impact `INVALID_RESPONSE`, stable code `note_not_utf8` |
| Bundle/view identity, size, hash, path, or schema fails validation | no evaluator call/result | none | common integrity failure at the strict loader/planner boundary |

Wrong and missing answers are scored outcomes, not infrastructure failures. Invalid semantic artifact content is not silently scored zero. No row is averaged with another evaluator or coerced into a generic score.

## 5. Real common-generation and reevaluation proof

The primary success test creates fresh registries and acquires the one-task snapshot once. It creates a real `PromptOverlayIntervention` from `intervention/style.md`, preflights it, and supplies it to a one-occurrence `CandidateGenerationRequest`. The ordinary accepted generation APIs prepare and run the plan through an actual supported vendor adapter whose local fake executable writes the declared deliverable. The test does not patch `prepare_generation_plan`, `generate_candidate`, `run_generation_plan`, the authoritative writer, sealer, index, or loaders and does not fabricate any successful `ExecutionResult`, `RunResultRow`, CandidateBundle, index, or manifest bytes.

The assertions bind the prompt overlay manifest/application evidence into the generated CandidateBundle, prove the exact RunManifest/index row and generation occurrence join, and strict-load every linked digest. Failure cases may register a declared fixture `Executor` that implements the ordinary `Executor.execute()` contract and returns a deterministic, identity/path/channel-conformant typed task-impact or run-impact `ExecutionResult` from inside that method. Tests must invoke it only through the unchanged common generation route; they cannot bypass `execute()`, patch generation to return a prefabricated result/candidate, or write sealer/index/bundle/manifest success themselves. For a typed task-impact failure, the common writer seals and indexes its failed CandidateBundle/row, evaluation records one skipped/no-metric result with zero evaluator calls, and outer evidence retains the planned denominator. A typed run-impact failure persists the common stop and forbids suffix dispatch. An invalid result envelope instead produces neither row nor bundle and remains covered by the predecessor's common-generation tests.

For reevaluation, the test:

1. completes and fsyncs the snapshot, generation plan, result index, and CandidateBundle;
2. deletes the external executor runtime root;
3. copies the durable run root as a whole to a new parent, deletes the original durable location, and starts a fresh process with no in-memory registry objects or path cache;
4. recreates the fixture registries, loads the moved snapshot/manifest/index/bundle strictly, creates `EvaluationRecordSink` with the exact evaluator-owned `EvaluationResumePolicy`, and evaluates through the common runner; and
5. repeats the load/evaluation request through `EvaluationRecordSink.resume`, proving that a completed current result makes zero evaluator calls and preserves its semantic digest.

Absolute source/runtime/original-run paths cannot appear in semantic records or be consulted during the fresh-process reload. The moved result has the same candidate, evaluation input, job, result and metric semantics. Location and audit evidence may differ where the accepted schemas explicitly permit it.

The fake executable and any subprocess test mode are selected only by injected test factories/configuration; no production environment-variable backdoor or benchmark-name branch is added. The test scans its captured invocation for credentials and real provider endpoints and proves zero network access.

## 6. Interruption, failure and resume proof

The test suite uses the common `EvaluationRecordSink.create/resume`, `EvaluationResumePolicy`, dispatcher and fixture evaluator. It never edits record files to manufacture a successful result.

- An evaluator attempt interrupted after a durable evaluator event leaves the immutable started/event/revision evidence. Explicit resume under the exact stored policy appends a new attempt and completed revision. The final `current_result` and `semantic_result_sha256` equal a clean uninterrupted evaluation of the same exact input, while attempt IDs, ordered attempt/event chain and `history_sha256` differ and both histories remain valid.
- A changed evaluator config, resume policy, candidate/view byte, linked digest, or source record fails before retry or reuse. Completed or eligible-partial current results never replay.
- In a three-job unary plan, an injected run-impact integrity failure on the first evaluator invocation persists exactly one failed current result and two causally skipped/no-metric results. The planned denominator remains three; the suffix is never silently omitted. An exact-policy resume can advance only if the stored failure is explicitly retryable and the source stop clears.
- A task-impact invalid result affects only that occurrence. It cannot vote, contribute a metric, or be rewritten as a completed zero.

Attempt timestamps, runtime paths and raw attempt evidence remain in immutable history and are excluded from stable result semantics. The test compares semantic equality and history inequality; it does not demand byte-identical complete logs across retry histories.

## 7. Unknown-benchmark Builder/N/S/A handoff

The same `orchard-notes` snapshot is passed to the accepted PR-09 experiment runner under a test-scoped resolved profile with unary strategy. All three arms use the exact same snapshot, `ApplicationSpec`, application executor/config/environment, evaluator ID/revision/config/resume policy, task order and repeat count. Evaluator cardinality compatibility is checked before any Builder or application execution. Requested comparison cannot fall back to unary; this fixture explicitly requests unary.

The arm graph is exact:

| Arm | Builder calls | Ordered Builder inputs | Application intervention |
| --- | ---: | --- | --- |
| N | 0 | none | accepted `NoneIntervention` |
| S | 1 | `input-001`: exact raw `creator-kit` bytes | sealed generated Agent Skill |
| A | 1 | the same byte-identical `input-001`, then `input-002`: exact raw `added-method` bytes | sealed generated Agent Skill |

S and A share Builder implementation, protected executor, application prompt/template revision, model/reasoning/timeout/network values, role environment, task/BuilderView bytes and `input-001` bytes. After excluding the declared additional input-002 binding and outer audit/occurrence values, their model-visible request payloads are byte-equal. No arm/condition/profile/source label appears in a target path, TaskSpec, prompt, environment, workspace path, executor input or generated skill.

The deterministic fake Builder is invoked through the accepted protected experiment-executor binding and ordinary `ExecutorSkillBuilder`. It emits one valid skill at `.eval-harness/interventions/agent-skills/orchard-notes-method/SKILL.md`; the common validator/sealer must accept and hash it before application. The test does not construct an `InterventionBundle` by hand or copy a Builder runtime directory into an application workspace.

The test uses the accepted production role-policy preflight path. For local Codex it calls the real no-model root-deny probe and executes with the exact bound overrides/environment; for contained Stirrup it would require PR-07's real measured `preflight_role_policy`. A mock/fake return value cannot claim isolation evidence. If the accepted dependency does not expose a deterministic protected local test command without a model request, this is a PR-05/09 acceptance gap and the PR-11 test stops; it does not substitute an unprotected executor.

After both skill bundles are sealed, one common GenerationPlan contains N, S and A in resolved order. All three CandidateBundles seal and the comparison group proves exact set/hash equality before any evaluation. Unary strategy then creates three independent jobs with fixed denominator three. The fixture evaluator reads each sealed arm only after the same group barrier and reports `note_exact_match` under the named per-arm aggregate. No common runner branches on `orchard-notes`, N/S/A, GDPval or ALPS.

Task-impact S Builder failure leaves S missing, preserves the three-arm planned denominator, permits independently ready N/A candidate evidence, and makes that group ineligible for evaluation. It does not fabricate S or silently compare/evaluate the remaining arms. A run-impact build failure stops before generation and persists the remaining planned states.

## 8. Exact deterministic tests and numeric oracle

`tests/harness/test_fourth_benchmark_extension.py` defines these nine tests exactly; helpers may live in the fixture package, but no test is split into a second entrypoint:

1. `test_fresh_registries_list_create_and_reject_identity_collisions`
2. `test_snapshot_separates_public_and_evaluator_only_bytes`
3. `test_common_generation_intervention_index_and_bundle_are_real`
4. `test_runtime_deletion_relocation_and_strict_reevaluation`
5. `test_wrong_no_deliverable_invalid_and_candidate_failure_are_distinct`
6. `test_run_impact_failure_persists_failed_and_skipped_denominators`
7. `test_evaluation_interruption_resume_preserves_history_and_semantics`
8. `test_unknown_benchmark_nsa_builder_handoff_and_unary_group_barrier`
9. `test_fixture_addition_changes_no_common_core_path`

`expected-results.json` contains these exact semantic expectations, with schema/revision fields and no runtime-generated identity literal. The status-count columns are evaluation-job counts; the candidate-task-failure row separately binds the failed candidate state and its causally skipped evaluation job.

| Case | Planned | Completed | Failed | Invalid | Skipped | Metric numerator/denominator/value | Evaluator calls |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| correct | 1 | 1 | 0 | 0 | 0 | `1/1 = 1.0` | 1 |
| wrong | 1 | 1 | 0 | 0 | 0 | `0/1 = 0.0` | 1 |
| no deliverable | 1 | 1 | 0 | 0 | 0 | `0/1 = 0.0` | 1 |
| non-UTF-8 | 1 | 0 | 0 | 1 | 0 | none | 1 |
| candidate task failure | 1 | 0 | 0 | 0 | 1 | none | 0 |
| run-impact evaluator stop | 3 | 0 | 1 | 0 | 2 | none | 1 |
| complete N/S/A unary group | 3 | 3 | 0 | 0 | 0 | three named `1/1 = 1.0` arm results | 3 |

The complete N/S/A case additionally asserts candidate count `3`, comparison-group candidate-slot count `3`, Builder-call count `2`, generation coverage `3/3`, evaluation coverage `3/3`, and zero evaluation before group seal. The task-impact Builder-failure case asserts planned arms `3`, Builder calls `2`, generated ready candidates `2` for N/A, sealed complete groups `0`, evaluation jobs/calls `0`, and one explicit missing S occurrence.

Test 9 obtains the PR-11 diff from the recorded accepted base and asserts exact equality to the add-only allowlist in section 3. It is an acceptance inventory, not a self-fulfilling source scan: the work record independently captures the same Git diff and reviewer verifies it.

## 9. Final quality gates: unchanged scope

Run the exact accepted PR-10 deterministic workflow on `<FINAL_PR11_HEAD_SHA>`, with no scope, threshold, dependency or platform reduction:

- `uv lock --check --offline`, with `uv.lock` byte-identical to the accepted PR-10 base;
- the locked harness environment with the same accepted `dev`, `eval-harness`, Stirrup and dedicated grader/build/runtime scopes;
- Ruff check and format check over the same production, harness-test and named script/unit-test paths;
- strict mypy over `eval_harness`, all `tests/harness`, `scripts/ci/run_eval_harness_coverage.py`, `scripts/update_env_list.py`, and the accepted updater/HF unit-test paths;
- the subprocess-aware coverage driver invoking only `bash tests/harness/test_eval_cli.sh`, with all existing measured source retained and the exact integer predicate `covered_lines * 100 >= num_statements * 96`;
- dependency exports with hashes and the same extras/groups, strict aliased `pip-audit`, plus every separately locked grader/Builder/Stirrup runtime audit;
- every retained unit/integration/inventory/reliability test, the PR-10 documented-command fake tests, and the nine new tests above, with no skip, xfail, deselection or network/model dependency;
- PR-04's real supported-Ubuntu grader-boundary job and PR-07's real supported Apptainer 1.5.3 containment/preflight job, using their accepted non-mock criteria; and
- tracked-path/import/retired-literal/owner-uniqueness, generated-environment, copyright, secret and DCO checks.

Coverage includes the new fixture adapter/evaluator because they are Python under `tests/harness`; no omission/exclusion is added. Test-only fixture code may not be counted as production source to inflate the production numerator. Existing historical fixtures and recorded outputs are byte-identical unless a prior accepted contract explicitly required their migration.

## 10. Final acceptance record

`contracts/pr11-final-acceptance-record.md` is completed only after source is frozen and includes this exact evidence table:

| Evidence | Required value |
| --- | --- |
| Source identity | `<PR10_ACCEPTED_HEAD_SHA>` commit/tree and ancestry proof; `<FINAL_PR11_HEAD_SHA>` commit/tree; exact diff |
| Dependency stack | exact accepted PR-01 through PR-10 heads/trees; no checkpoint substituted |
| Fixture identity | every fixture byte SHA-256, snapshot/view/manifest/index/bundle/evaluation-input/job/result semantic digest |
| Registry proof | descriptors, fresh-list/create results, collision cases, constructor counts |
| Generation/reevaluation | fake invocation counts, runtime deletion, relocation, fresh-process strict loads, completed reuse count zero |
| Builder/experiment | two Builder calls, input/target equality evidence, skill bundle digests, three candidate slots/jobs, barriers and failure denominators |
| Resume | immutable revision/event/attempt digests, equal final semantic digest, unequal valid history digest, retry-policy digest |
| PR-10 acceptance | deleted-path/import/literal inventories; neutral entrypoint and documented CLI example results |
| Quality | exact commands, test counts, coverage numerator/denominator, Ruff/format/mypy/lock/audit results |
| Platform boundaries | exact supported grader and Stirrup job URLs/head/tree/results; no mock/skip substitution |
| Review | independent Sol findings/resolutions and exact accepted head |
| Migration closure | mandatory unresolved item count exactly `0`; Gate-B items separately labeled and not counted as Gate-A completion |

No secret, raw auth value, paid-service output, model output, fabricated job URL, or guessed dependency SHA appears in the record. Timestamped audit history may differ from semantic digests and is preserved.

## 11. Completion and prohibitions

PR-11 is complete only after its exact add-only diff receives independent Sol review, all section 9 gates pass on the frozen head (or a proven equal tree), the final record contains exact evidence, and the migration owner records zero unresolved mandatory Gate-A items. Draft PRs remain unmerged.

- No production/common-core/config/workflow/dependency/doc edit, new alias/plugin framework, fixture-name branch, universal score, arbitrary pair Elo, or second vendor/runtime/metric implementation.
- No fabricated candidate/bundle/record, record mutation/truncation, retry-history erasure, output repair/conversion, compatibility reader, path fallback, registry-global mutation, or claimed isolation from a fake preflight result.
- No real model/judge/provider/web call, credential, Actions dispatch, merge, release, publication, force push, control-branch edit, or historical output deletion.
- No quality narrowing, skip/xfail/deselection, arbitrary audit allowlist, mock replacement for a required supported-platform boundary, or result from a different unproven tree.

Any need to violate the add-only allowlist returns to the predecessor owner with the exact failing public contract and test evidence. A requested change to migration scope or acceptance strength returns to Astra.
