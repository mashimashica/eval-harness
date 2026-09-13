---
name: implement-change
description: Implement a bounded change, update meaningful tests and affected documentation, and perform self-checks. Use when the required behavior and implementation authority are clear; escalate scope-changing decisions instead of expanding the work.
license: Apache-2.0
compatibility: Requires this repository checkout and its shared .agents/development context.
---

<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Change Implementation

## Purpose

Realize the authorized behavior in an integrable change, with meaningful self-checks and enough evidence for subsequent
verification and acceptance.

## Outcomes

- The implementation realizes the agreed behavior within the authorized change boundary.
- Self-checks distinguish the changed behavior or content from relevant incorrect results.
- Affected usage information is consistent with the implemented interface.
- The delivered change is identifiable and preserves unrelated work.
- Self-check evidence and unresolved limitations are available for the next decision.

## Activities & Tasks

The following tasks are required within the commissioned scope; self-check and correction may repeat within its limits.

### Implement the bounded change

1. Read the assignment, applicable requirements, selected design, repository instructions, and current diff. Confirm
   write ownership and the candidate baseline. A separate design document is unnecessary when the required behavior
   and boundaries are already clear.
2. Implement the smallest coherent change using suitable existing capabilities. Make ordinary implementation decisions
   within the assignment without repeated approval requests. Return decisions that change requirements, public behavior,
   responsibility boundaries, or execution limits to the controller.
3. Add or update behavior-based tests where behavior changes, and update affected usage documentation. For content-only
   changes, check the content and references rather than inventing an unrelated runtime test. Derive expected results
   from requirements or independent reference behavior, not by copying current output. Include relevant negative cases;
   do not weaken criteria or delete a failing assertion merely to obtain a passing run.

### Check and deliver

1. Run the applicable targeted tests and local repository checks. Inspect actual outputs, not only exit codes. Use
   authorized CLI probes where mocks cannot establish the required integration behavior; label mock and real evidence.
2. Correct failures within the assignment and rerun affected checks. For an uncertain state-changing result, inspect
   resulting state before retrying. Preserve the failing evidence when returning an unresolved issue.
3. Return the exact revision or identifiable local diff, changed behavior, commands and results, evidence locations,
   and remaining limits. Request verification where the self-checks do not establish the acceptance criteria. Perform
   remote commit or PR operations only when assigned, through the shared remote-write rules.

## Inputs and Outputs

Inputs are the authorized assignment, design decisions, source, and tests. Outputs are code, meaningful tests, affected
documentation, and self-check evidence. These outputs support acceptance; they do not authorize it.

## Controls

Apply the [shared development context](../../../.agents/development/README.md), the assignment's acceptance criteria,
and repository conventions applicable to the changed files.

## Constraints

Preserve unrelated local changes. Do not change execution identity, model settings, credentials, or billing routes to hide
a failure. Implementation self-checks must not be described as independent verification or review. Do not merge, release,
or publish without the applicable authorization.
