<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR02c selected consumer and typed fixture work

Status: initialized bounded implementation batch; no edits or validation performed yet.

- Parent/base: `3f37a1b7e7e6e74900d475dd018a25931acca04e`, tree `e12f03944e2123cdb75959b9c7715ee5718db444`.
- Sole remote writer: root/Astra. Implementation: a dedicated Luna in its own `pr02c-fixtures` checkout. Sol owns design/review.
- Branch: `checkpoint/pr-02c-selected-consumer`; this is part of PR02c, not a new migration slice or formal PR.
- Fixed contract: `contracts/pr02c-fixture-migration-map-31307d4.md`, SHA-256 `37e848eafdd8bfc8ca5d2ce6612eb0cc325b641384f4c7648aedb9185f84de47`, copied/read back from Sol `b46537358ae0355be4d926a0d606a095a197273a`.
- Edit allowlist: `eval_harness/experiments/runner.py` only `_SelectedTaskBenchmark`; `tests/harness/test_builder_experiment_runner.py`; `tests/harness/test_experiment_reliability.py`; `tests/harness/test_reasoning_effort.py`; `tests/harness/test_runner_reliability.py`; this work record owned by root.

Preserve source/revision availability and the original adapter snapshot hooks. Execution wrapping uses the fresh canonical minimal task without evaluation/materialization metadata. Keep all original non-null fixture revisions and available-revision assertions, real materialized file bytes, named metrics, fixed denominators, typed primary failures and durable partial results. Add exact fake capabilities/provenance and authoritative nested-run loader assertions. Do not change production experiment orchestration, public schemas, CLI or Cursor files, weaken tests, add compatibility fallback, or fabricate persisted handoff records.

Return one coherent <=15-minute editing batch before tests, next independent edit, local commit, or remote write. Root saves UTF-8 files with the required Mashimashica DCO, rechecks the ref, reads back exact bytes, and then validates this immutable saved head. Before combining into the primary PR02c branch, root verifies the common base blob for each changed source/test path is unchanged on the destination and applies only the reviewed delta; no force/history rewrite is used. The primary owner works on disjoint Cursor/CLI/handoff paths. Full PR02c gates run only after integration; passing this side batch alone is not acceptance.
