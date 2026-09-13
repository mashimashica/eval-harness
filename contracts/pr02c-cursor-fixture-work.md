<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR02c Cursor fixture port

Status: initialized, no edits/tests yet. This is a bounded part of PR02c, not another migration slice or formal PR.

Base: `3f37a1b7e7e6e74900d475dd018a25931acca04e`, tree `e12f03944e2123cdb75959b9c7715ee5718db444`. Contract: `contracts/pr02c-fixture-migration-map-31307d4.md`, SHA-256 `37e848eafdd8bfc8ca5d2ce6612eb0cc325b641384f4c7648aedb9185f84de47`.

Only `tests/harness/test_adapter_failure_coverage.py` and `tests/harness/test_executor_judge_reliability.py` may be edited, and only their Cursor execution/input/helper fixtures. Judge-only reference_files/presentation/isolation assertions remain. Preserve each protection, failure, decoding, no-output, cleanup, environment and durable-log check. Missing/non-real digest roots now fail closed and real directory structure is hashed; do not restore the old lax behavior. No production edits or mocked handoff success.

A dedicated Luna owns only `/workspace/scratch/f07c7ef4c195/pr02c-cursor-fixtures`. Root owns this record and all remote writes. Return one coherent batch within 10 minutes before tests, local commits or further edits. Root verifies the two-file allowlist, saves/readbacks with exact user DCO, then tests the saved head. Before combining into primary PR02c, verify baseline blobs on the destination are unchanged and preserve every other owner's file. Full PR02c acceptance requires combined-head review and unchanged required gates; this side batch cannot establish it alone.
