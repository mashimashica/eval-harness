<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Migration final acceptance and deletion map

Status: Astra acceptance inventory against `d5ce0c10162cad788a17cb90f34b8f60574e7f75`; this is not a completed PR10/11 implementation or Sol-to-Luna contract. The canonical original plan at control commit `8518f25d107d9043df449a9198fbb41b00ba1c22` governs scope. Reconcile this inventory with each accepted predecessor before the deletion slice begins.

## Required replacements before deletion

| Existing route or dependency | Replacement owner | Protection or behavior that must be verified before removal |
| --- | --- | --- |
| Root `gdpval`, `scripts/gdpval_provider.sh`, `scripts/gdpval_preflight.sh`, `scripts/gdpval_run_metadata.py` | PR05 CLI, PR07 provider, PR08 profile, PR09 experiment | Explicit selection, supported auth/model/reasoning/timeout combinations, fresh output refusal, secret-free semantic configuration and provenance, systemic abort; no alias or shell wrapper |
| `eval_harness/local_runner.py` and old runtime prompt/deliverables handoff | PR02c, PR05, PR09 | Snapshot materialization once, typed outputs, bundle/index durability before evaluation, runtime deletion and complete output relocation |
| `eval_harness/local_judge_runner.py` | PR05/06 | Exactly-two coherence, anonymous projection, actual source-read restrictions, preflight before invocation, invalid response handling, per-trial persistence and interruption evidence |
| Duplicate local vendor judge transport under `eval_harness/judges/` | PR05/06 | One implementation with explicit judge isolation policy; ordinary workspace-write generation settings are not proof of blind judge read isolation |
| GDPval external evaluator, its aliases, external/deferred status as a completed GDPval route | PR05/06 | Rubric and pairwise return normal typed evaluation results through common bundle reevaluation; execution-only is explicit and never claims scored completion |
| Stirrup GDPval generation `/verify`, `judge_only`, old recipe/provider orchestration | PR07/08 | Mock-provider generation never invokes scoring; full AA stage control uses common generation/evaluation contracts |
| Old AA multistage shell/controller route | PR08 | Bound reference bytes, explicit complete trial plan, stage-specific occurrences, native vote/Elo rules, append-only attempt evidence and verified resume |
| Experiment legacy result and prompt-path readers | PR09 | Same sealed snapshot/application/evaluator setup for N/S/A, every comparison group's candidates sealed before evaluation, missing arms remain visible in denominators |
| `.gdpval/interventions` in AgentSkill and Builder artifact validation | PR09/10 | One neutral path, exact sealed manifest mapping, collision/nonoverwrite and source-integrity behavior preserved, no alternate old-path reader |
| `GDPVAL_CONDITION*` filtering in common runner/Builder | PR09/10 | Conditions remain controller-only using the final neutral configuration/environment boundary; no benchmark-specific core branch |

Retain reusable NVIDIA benchmark, renderer, parser, grader, panel, and numerical assets with their licenses where the new path uses them. Delete replaced harness control and unused duplicate implementations. A benchmark adapter, explicit GDPval evaluator, AA profile, dataset input column, or historical design record may legitimately name GDPval; a blanket string deletion is not an acceptance test.

## Specific integration findings that cannot wait for PR10

1. Cursor currently protects `reference_files`, while the snapshot materializer publishes `task_inputs`. PR02c integration must preserve its existing input protection and mutation detection on the new path, with explicit ownership of staged old consumers and no new fallback.
2. Generic file-intervention reserved namespaces must protect the actual snapshot input namespace. Collision checks must be exercised even for a new file below an otherwise existing task-input directory.
3. The old blind Codex judge uses a custom permission profile and read probes. Reusing normal Executor invocation is acceptable only when its explicit judge role preserves this isolation. Sanitized prompt text alone is insufficient proof.

These findings were sent to the responsible Sol agents before source review. They are open until an accepted saved implementation and tests close them.

## Test and CI transition

`tests/harness/test_gdpval_cli.sh` currently owns both obsolete CLI assertions and the complete unit/six-shell-test suite. Do not delete it without moving that suite entrypoint and every still-required behavior to a neutral self-test command.

- Replace old CLI syntax/provider/metadata assertions with new public CLI behavior tests; only assertions of an intentionally removed command name are obsolete.
- Port local-executor, local-judge, condition, fresh-path, source-mutation, auth, timeout, interruption, and no-fallback protections to the matching new integration tests before deleting their old test harnesses.
- Update `scripts/ci/run_eval_harness_coverage.py` to invoke the neutral suite. Preserve subprocess coverage and the integer rule `covered_lines * 100 >= num_statements * 96`.
- Remove deleted script paths from `pyproject.toml` and workflow type-check commands, and add any new production modules that are outside the existing measured/type-checked package. Never narrow coverage or type checking merely to pass.
- Preserve locked Python/uv setup, Ruff and formatting, strict mypy, dependency compatibility, inventory tests, dependency CVE audit, copyright/secret scans, and DCO. Include actual supported-platform grader boundary proof and its distinct audited dependency lock.

## Fourth fixture benchmark proof

Add one small benchmark adapter and necessary registration/evaluator fixture with an unknown name. Use the already accepted common entrypoints, Executor and Builder contracts. The addition must not edit common runner, Executor, or Builder implementation. A general plugin framework is not required.

The fixture must exercise: acquisition and canonical/evaluation input separation; actual generation with a fake runtime and intervention; strict run-manifest/index/bundle load; deletion of external runtime and relocation; reevaluation from saved bundles; named metric and explicit failure outcomes. Test registration may inject an adapter/factory through the ordinary registry, but may not patch orchestration or fabricate a handoff in place of generation. Include the N/S/A builder boundary or a separate unknown-benchmark builder test using the same core.

## Final-head evidence

After PR10/11 source review, fix one immutable final Draft-stack head. Run every required deterministic CI gate on that head. If a check uses a synthetic merge, record its commit and prove its source tree equals the final head; otherwise run the exact head. Record coverage integer totals, check/run URLs, dependency audit scope, real grader boundary result, fourth-benchmark result, removed route inventory, and zero unresolved mandatory migration items in the control branch. Control evidence updates must not silently change the tested implementation head.

README, EXPERIMENTS, UPSTREAM and development guidance must match final `./eval` list/run/evaluate/experiment commands. Command examples must have a corresponding fake-execution test. Explain named metrics and explicit execution-only behavior, provider/judge configuration and limits, bound reference requirements, output/runtime layout, supported sandbox/platform, and Gate B's separately authorized real-model phase. Do not claim performance, official AA score reproduction, or vendor live-environment validation from fake CI.

Completion is PR creation/update, independent review and deterministic CI success through all original logical slices. Drafts remain unmerged; releases, publication and real model experiments are outside this phase.
