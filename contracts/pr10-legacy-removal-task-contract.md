<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR-10 legacy-route removal and documentation task contract

Status: early durable design checkpoint; exact source/test deletion matrix is pending baseline inventory. This is a Luna implementation contract, not implementation or acceptance evidence.  
Date: 2026-09-13  
Sol owner: PR-10/11 design review  
Immutable characterization baseline: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`  
Canonical-plan control commit: `8518f25d107d9043df449a9198fbb41b00ba1c22`  
Canonical-plan SHA-256: `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`  
Astra acceptance-map SHA-256: `ad8870927701889f4f99e9cdda33ce57aa995281d6a9db7a48fb7dd888153710`

## 1. Immutable implementation inputs

PR-10 implementation must start from `<PR09_ACCEPTED_HEAD_SHA>`. Luna substitutes the exact 40-character accepted PR-09 head only after the migration owner supplies it, verifies that it descends the accepted PR-01 through PR-09 stack, and reads every predecessor contract/changed path from that commit. A symbolic branch, this design branch, the baseline, or a current checkpoint is not an implementation base.

The currently saved PR-02c checkpoint `9a9f144537f4dc276e18c029666be229547e371c` and saved PR-05 through PR-09 contracts are characterization inputs. They do not fill `<PR09_ACCEPTED_HEAD_SHA>` and do not prove that their described production interfaces have landed.

## 2. Objective and phase boundary

PR-10 deletes superseded GDPval entrypoints, harness controllers, duplicate transports, compatibility readers, scripts, configs, and tests only after their required behavior is demonstrated through the accepted neutral path. It makes `./eval` the sole harness CLI, moves the complete harness self-test entrypoint to `tests/harness/test_eval_cli.sh`, and updates user/developer documentation to commands proven by deterministic fake execution.

This slice preserves benchmark adapters, evaluator-owned GDPval rubric/pairwise semantics, AA-v2 profile assets, reusable NVIDIA renderer/parser/panel/numerical code still imported by the accepted path, AIME/BigCode named metrics, grader isolation, and all common durability/security behavior. It performs no real model, judge, provider, paid API, release, merge, or publication work.

## 3. Nonnegotiable implementation rules

1. Every deletion has an accepted replacement owner and a passing behavior test before removal. Old names receive no shim, alias, dual reader, auto-converter, environment fallback, or wrapper.
2. `tests/harness/test_eval_cli.sh` exists, runs the complete retained unit and shell suite, and is invoked by coverage/CI before `tests/harness/test_gdpval_cli.sh` is deleted.
3. `scripts/ci/run_eval_harness_coverage.py` retains subprocess coverage and the exact integer threshold `covered_lines * 100 >= num_statements * 96`. Ruff, formatting, strict mypy, locked dependencies, CVE audit, copyright, secret scanning, DCO, and inventory checks remain unchanged in scope and strength.
4. Common runner, Executor, Builder, and evaluation layers retain one owner for each transport, runtime, record sink, and metric. PR-10 deletes unused duplicates; it does not fork vendor code or move evaluator metrics into the CLI.
5. New public `./eval list/run/evaluate/experiment` examples are executed by local fake tests. Execution-only remains explicit; reevaluation uses sealed CandidateBundles; named metrics keep their own denominators.
6. Retired strings are scanned honestly. Explicit negative tests may contain a literal old command/path only in a reviewed exact-location allowlist and only to assert rejection. Any executable/compatibility use fails acceptance.
7. Historical outputs/logs remain untouched. New readers reject unsupported old schemas and paths without discovery or migration.

## 4. Preliminary removal surface

The detailed retained/migrated/deleted table will be frozen in the next checkpoint. At minimum the inventory covers root `gdpval`; `scripts/gdpval_provider.sh`, `scripts/gdpval_preflight.sh`, and `scripts/gdpval_run_metadata.py`; `eval_harness/local_runner.py` and `eval_harness/local_judge_runner.py`; GDPval external/deferred evaluator selection; legacy experiment prompt/result readers; old AA shell/controller/recipe routes; obsolete `.gdpval` and `GDPVAL_CONDITION*` common paths; old configs; and `tests/harness/test_gdpval_cli.sh` after its neutral replacement is proven.

The inventory must separately mark reusable files retained under their accepted adapter/evaluator/profile owner. A filename containing `gdpval` is not deletion evidence.

## 5. Early completion gate

Luna may begin implementation only after this contract replaces the pending matrix with exact repository paths, replacement tests, deletion order, allowed changed paths, and dependency SHA placeholders. Completion requires the final PR-10 head to pass the scoped deterministic gates and independent review. PR creation/update remains Draft; merge belongs to later explicit authorization.

