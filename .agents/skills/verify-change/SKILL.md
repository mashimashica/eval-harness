---
name: verify-change
description: Execute targeted checks and authorized real CLI trials to establish what a specific change satisfies. Use for integration, end-to-end, regression, or failure-path verification; report failed and unconfirmed criteria without rewriting the implementation.
license: Apache-2.0
compatibility: Requires this repository checkout and its shared .agents/development context.
---

<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Change Verification

## Purpose

Establish which applicable requirements a specific candidate satisfies, using appropriately scoped observations and
explicit limits on what the evidence can support. Verification may complete while the candidate fails a requirement.

## Outcomes

- Observations are attributable to an identified candidate and execution conditions.
- Each selected criterion has a justified met, not met, unconfirmed, or not applicable judgment.
- The evidence discriminates the required behavior from the consequential failures within the verification scope.
- Unperformed checks and limitations are explicit for dependent decisions.

## Activities & Tasks

The following tasks are required within the commissioned scope; required preconditions must precede their dependent runs.

### Prepare applicable checks

1. Read the assignment, requirements, candidate diff, design decisions, and existing evidence. Identify what the current
   evidence does and does not establish. Verify the candidate baseline before reusing results.
2. Select the checks needed for the acceptance claim, including relevant integration and failure paths. For CLI behavior,
   inspect the installed version and supported arguments, authentication mode, and local prerequisites. Verify the permitted
   model, settings, task count, concurrency, and retry limits before issuing model work; do not expose credentials.
3. Use controlled temporary data or workspaces where execution changes state. Keep development instructions and unrelated
   condition information out of benchmark participant contexts. Record whether the check is a mock, dry run, or real
   execution and what isolation was actually verified.

### Execute and interpret

1. Run the bounded checks. Inspect observable behavior, artifacts, and failure effects against the criteria rather than
   interpreting an exit code, a created file, or a success label as proof of task success. Preserve the original observations.
2. For comparisons, examine the declared conditions and relevant leakage or ordering paths. For continuation behavior,
   check preservation of completed work and unintended repeated execution. Apply these checks when the change or acceptance
   claim depends on those behaviors, not as an unconditional suite for every edit.
3. Assign each selected criterion its evidence-based status. Missing credentials or an unavailable runtime makes dependent
   checks unconfirmed, not passed or inapplicable. A justified exclusion must explain why the criterion does not apply.
4. Return the candidate identity, commands, conditions, observations, criterion judgments, and limitations. Refer failures
   to the controller or implementer. After correction, rerun affected checks without discarding still-applicable evidence.

## Inputs and Outputs

Inputs are the candidate, applicable criteria, and prior evidence. Outputs are observations and criterion-level judgments.
Verification owns its evidence, not the product's acceptance decision or the implementation under examination.

## Controls

Apply the [shared development context](../../../.agents/development/README.md) and the assigned acceptance criteria.
Use existing test runners and installed CLIs; add verification machinery only when existing tools are insufficient.

## Constraints

Do not silently repair the candidate during verification. Correcting a test or implementation requires an authorized
implementation scope and a newly identified candidate. Do not substitute a different runtime or paid API when a check
cannot run. Report empirical verification only for executions actually performed.
