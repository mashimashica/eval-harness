---
name: review-change
description: Review a bounded design or implementation and its evidence for consequential requirement violations and missing justification. Use for an assigned risk or milestone review; classify findings without taking over implementation or final acceptance.
license: Apache-2.0
compatibility: Requires this repository checkout and its shared .agents/development context.
---

<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Change Review

## Purpose

Provide a scoped, evidence-based assessment of a design or implementation so the controller can make a sound progression
decision without turning optional improvements into unbounded rework.

## Outcomes

- The review judgments use criteria and evidence applicable to the identified target.
- Consequential violations and evidence gaps found within the reviewed scope have explicit impact and basis.
- Required corrections are distinguishable from optional improvements.
- The recommendation states its examined scope and limits without claiming product acceptance.

## Activities & Tasks

The following tasks are required within the commissioned scope; the shared review budget limits ordinary repetition.

### Examine the assigned concern

1. Read the assignment, exact target revision or diff, relevant requirements, and verification evidence. Confirm the review
   question and independence requested. A design review does not require an implementation; an implementation review must
   not infer runtime success from the existence of a design.
2. Inspect the assigned boundary and directly affected interactions. Concentrate on incorrect results, invalid comparisons,
   unauthorized effects, failure recovery, and missing evidence where relevant. Do not reopen unrelated architecture or
   raise hypothetical future capabilities as current requirements.
3. Ground each substantive finding in a concrete failure condition, reproduction, code path, or specific evidence gap.
   Distinguish a demonstrated violation from an unconfirmed risk. A plausible consequential code path does not require
   destructive reproduction; a vague possibility does not justify blocking the whole plan.

### Classify and recommend

1. Apply the shared Blocker / Required / Follow-up decision rules. For each finding, provide the applicable criterion,
   location, failure condition or missing evidence, impact, confidence, and smallest useful correction or check. State
   exactly which action or acceptance claim is affected.
2. Return a scoped recommendation: proceed, proceed with explicitly tracked obligations, or hold the affected work.
   No Blocker is not proof that all acceptance criteria are met. The controller owns acceptance and any authorized
   prioritization; mandatory requirements remain binding regardless of the recommendation.
3. On correction review, inspect the correction and directly affected behavior rather than restarting the entire review.
   Escalate a new consequential finding, but route new optional improvements to follow-up. After the ordinary review
   budget is exhausted, return the unresolved decision to the controller instead of opening an endless revision loop.

## Inputs and Outputs

Inputs are the assigned design or implementation, criteria, and verification evidence. Outputs are scoped findings and a
recommendation, including an explicit statement when no blocking issue was found in the examined scope.

## Controls

Apply the [shared development context](../../../.agents/development/README.md), especially its finding classifications,
review budget, and authority boundaries. Assess the assigned target, not a preferred alternative project.

## Constraints

Review-only work must not rewrite code, alter requirements, merge a PR, or create new required work without authorization.
Read-only inspection is permitted; executable probes require the same authorization and limits as verification. Do not
call a same-author review independent. Do not suppress a material finding to satisfy the review budget.
