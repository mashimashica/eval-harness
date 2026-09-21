<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Claude dashboard evaluator recovery: proposed one-session acceptance check

Status: **explicitly owner-approved on 2026-09-22 JST**, maximum1 session. This is a new finite batch, separate from the spent historical11/10
and the approved six-session batch. No remaining session is inferred from them.

## Purpose and fixed inputs

The six-session batch's Claude dashboard evaluation completed but left all57 criteria unconfirmed after context
compaction removed their descriptions from available conversation. The harness had supplied them only in the prompt.
The correction retains current-task criteria/instructions in protected evaluator files;181 affected tests, exact
57/46-item source round trips and real model-free isolation checks pass. This check tests use of those files and
item-bound evidence on the same saved dashboard. It does not seek a favorable score, regenerate a deliverable or change
the original rubric. The earlier result and its usage stay intact.

- Task: `9e39df84-ac57-4c9b-a2e3-12b8abf2c797`; saved Claude artifact collection SHA256
  `91a38133510400e69599e1abf8e226f57dab964a02c5bd3e218183e04be62966`.
- Existing57-item criteria and reviewed v2 protocol; protocol SHA256
  `b7423ab0e8805ba9162e27e1841cae6e364a5658f7e97f8ded26965ffcbd41a7`.
- Combined durable-context/private-font environment fingerprint
  `ecd1071aac425229104a253df7de66b92e89c6fbcaf0b4c76848a4c08d9328e4`.
- Prepared config SHA256 `2b601ffaac58382f0fad673a03afb66cd40b2cf2adcd1c863d2aecd2873674df`;
  local proposal/config under `.audit/2026-09-22-dashboard-recovery/`.

## Execution envelope

| Setting | Fixed limit |
| --- | --- |
| Model | Claude `claude-opus-5`, medium |
| New model-backed CLI sessions | Maximum1 |
| Session timeout | 1,200 seconds (20 minutes) |
| Claude max_turns | 40 |
| Parallelism / automatic retries | 1 / 0 |
| Billing | Existing subscription only; no API route, auxiliary AI or extra billing |
| Order | After the already-approved science Codex and Claude evaluations finish |

Preparation, authentication checks and capture/cleanup are measured separately from model time. A native error or
timeout consumes this slot. There is no automatic corrective retry. The current source, binaries, config, rubric,
protocol and preserved inputs must match their hashes before dispatch.

## Acceptance and impact

Record actual retrieval of durable criterion text, any native compaction, method coverage and evidence references,
changed-input operations, source conflicts, native-operation gates, source preservation, elapsed time and usage.
File availability alone does not establish that the model recovered or judged correctly. Unknown items remain null;
participant failures remain distinct from evaluator/infrastructure failures. The two unsupported native-control items
remain gated, and the original day/night rubric/source conflict is retained. There is no all-220 or ALPS production
acceptance from this one session. It creates a new evaluation identity and preserves all earlier records.
