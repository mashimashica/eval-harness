---
name: control-development
description: Plan and control a bounded development effort, delegate work, assess evidence, and decide acceptance or the next action. Use to start, resume, or steer development; not as a mandatory step for every edit.
license: Apache-2.0
compatibility: Requires this repository checkout and its shared .agents/development context.
---

<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Development Control

## Purpose

Keep authorized development aligned with its intended results, selecting and coordinating work until the agreed scope
is accepted or its remaining work has an explicit disposition. Control does not replace design, implementation,
verification, or review evidence.

## Outcomes

- The active scope has observable acceptance criteria consistent with the authorized requirements.
- The selected work and its dependencies cover the active scope without conflicting ownership.
- Progression and acceptance decisions are supported by evidence applicable to the candidate being assessed.
- Unfinished work has an explicit status, impact, and next action or justified stopping condition.
- Changes to scope or execution arrangements remain within the applicable authority.

## Activities & Tasks

The following tasks are required within the commissioned scope; their numbering does not prescribe a fixed lifecycle.

### Frame and allocate

1. Read the applicable request, requirements, current plan, repository instructions, and local state. Confirm the branch,
   revision, existing edits, available runtimes, and granted authority. On resumption, reconcile recorded progress with
   actual state instead of restarting accepted work or trusting an old completion claim.
2. Define the smallest useful increment and its acceptance evidence, dependencies, exclusions, and execution limits.
   Keep the full requirement set visible across increments. Treat an externally observable vertical slice as the default
   starting point, not a requirement to complete every abstraction before any real execution.
3. Select only the processes needed. Delegate a bounded assignment using the shared context interface; give one worker
   ownership of each write scope. Use a specialist review for consequential uncertainty, not as universal approval.

### Assess and steer

1. Assess the returned changes and evidence against the agreed criteria. Distinguish implementation completion,
   verification findings, reviewer advice, and actual acceptance. Revalidate only evidence affected by changed inputs,
   code, tools, or conditions; retain evidence whose basis remains valid.
2. Resolve findings using the shared decision rules. Prefer a bounded local probe for empirical uncertainty and make
   design decisions directly when further review would only repeat a preference. Stop affected dependent work when
   prerequisites are unmet; continue independent authorized work.
3. Accept only the scope supported by applicable evidence, or return a specific correction, defer eligible work, or
   escalate a decision outside the granted authority. A smaller increment must not silently remove a product requirement.
4. Update the single working plan with the decision, evidence locations, remaining obligations, and next work. Report
   milestone results and material changes to the user. Complete the authorized integration or PR handoff without treating
   an internal acceptance decision as permission to merge, release, or publish.

## Inputs and Outputs

Inputs are the current work state and returned design, implementation, verification, and review information. Outputs are
assignments, the updated plan, and reasoned acceptance or continuation decisions. Existing local files or issue records
may carry these information items; additional documents are not required merely to fill a template.

## Controls

Apply the [shared development context](../../../.agents/development/README.md), especially its context interface,
decision rules, information ownership, and project requirement reference. Read the selected Skill when assigning work;
do not load all Skills as a mandatory sequence.

## Constraints

The controller must not waive a user requirement, convert missing evidence into success, or reclassify a genuine
blocking condition solely to satisfy a review budget. Missing authorization prevents only the actions requiring it.
