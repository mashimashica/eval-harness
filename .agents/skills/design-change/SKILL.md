---
name: design-change
description: Design the responsibilities, interfaces, change scope, and verification approach for a bounded software change. Use when a requirement or consequential design choice needs resolution before implementation; not for unrelated redesign.
license: Apache-2.0
compatibility: Requires this repository checkout and its shared .agents/development context.
---

<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Change Design

## Purpose

Establish a sufficient, implementable design for the authorized change while preserving applicable requirements and
limiting changes to the responsibilities and interactions needed for that result.

## Outcomes

- The proposed behavior addresses the selected requirements within an explicit responsibility boundary.
- Affected interfaces and interactions are sufficiently specified for implementation and integration.
- Consequential design choices are justified by applicable constraints and available evidence.
- The proposed verification can distinguish the required behavior from relevant failure conditions.
- Unresolved assumptions have explicit effects on dependent implementation or acceptance.

## Activities & Tasks

The following tasks are required within the commissioned scope; perform them iteratively where evidence changes.

### Establish the design basis

1. Read the assignment, applicable requirements, existing code and design, and relevant verification evidence. Identify
   the desired change and neighboring responsibilities. Do not infer requirements from inherited implementation choices.
2. Inspect existing capabilities before proposing new components. Separate questions answerable by a bounded local CLI
   probe from choices requiring design judgment. Confirm authorization and execution limits before an empirical probe;
   record its conditions rather than inventing runtime behavior.

### Specify and challenge

1. Describe only the necessary behavior, responsibility allocation, interfaces, information flow, failure responses,
   and change scope. Preserve user-visible choices without assuming every combination of settings is valid.
2. Connect each selected requirement to an observable check. Consider a relevant counterexample: could the proposed
   check pass while the requirement fails? Include consequential boundaries and integration failures, not only happy paths.
3. Resolve material alternatives by their effects on the requirement, complexity, and verification cost. Do not create
   an abstraction, compatibility layer, or new process solely for a hypothetical future need.
4. Hand off the selected design, rationale, affected paths or interfaces, verification approach, and remaining assumptions.
   Return scope-changing choices to the controller. Revise only the affected design when implementation or verification
   supplies new evidence.

## Inputs and Outputs

Inputs are the bounded assignment, current implementation, and existing design evidence. Outputs are the selected design
and verification approach, or clearly scoped findings where the design remains unresolved. A design note can live in the
existing plan or PR; creating a document is not itself design success.

## Controls

Apply the [shared development context](../../../.agents/development/README.md) and the assignment's requirement and
acceptance references. Use current local capabilities and relevant official documentation as evidence for tool behavior.

## Constraints

Design does not authorize production implementation, changes to shared requirements, or external publication. Probes may
change only the explicitly permitted local scope. A design recommendation is not evidence that the system works.
