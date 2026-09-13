<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Local development

## Purpose and references

Shared rules for the five development Skills.
Product obligations are in [requirements.md](requirements.md).
CLI commands and configuration examples are in [SPEC.md](SPEC.md).
Repository permissions are in [AGENTS.md](../../AGENTS.md#authorization-and-remote-writes).
See [validation.md](validation.md#local-setup) for initial setup, authoring references, and validation history.
The [historical acceptance evidence](evidence/README.md) indexes the completed harness trials and integration record.

## Roles and workflow

| Skill | Initial assignee | Responsibility |
| --- | --- | --- |
| [control-development](../skills/control-development/SKILL.md) | Astra max | Plan, delegate, resolve findings, and accept work. |
| [design-change](../skills/design-change/SKILL.md) | Astra or a delegate | Define behavior, interfaces, and verification scope. |
| [implement-change](../skills/implement-change/SKILL.md) | Luna max | Implement, test, and update affected documentation. |
| [verify-change](../skills/verify-change/SKILL.md) | Luna max or a separate verifier | Establish actual behavior and its limits. |
| [review-change](../skills/review-change/SKILL.md) | Sol max when needed | Assess consequential boundaries or uncertainty. |

These are role preferences, not CLI model identifiers. Confirm supported model/settings at assignment time.
Use one controller and one implementation worker by default. Add at most one specialist when needed.
Keep one writer per scope. Nested delegation requires user approval.
Start with a small usable increment. Select only the Skills it needs.
One worker may implement and verify; identify this as self-verification.

## Assignments and records

The controller supplies these details directly or through precise references:

- Target, requirement IDs, acceptance criteria, and exclusions.
- Workspace, revision or local diff, relevant design, and existing evidence.
- Allowed edits, side effects, execution limits, and any independence requirement.
- The result needed next and where to return it.

Workers return the candidate identity, changes, check results, evidence locations, and unresolved issues.
Assigned workers own their design, code, or observations. The controller owns the plan and acceptance decisions.
Keep one plan with accepted work, remaining obligations, decisions, and next actions.
Notify affected workers when requirements, interfaces, or assignments change.
Reference shared information rather than copying it into each Skill or creating a parallel contracts hierarchy.

## Development standards and quality gates

- **Toolchain:** Use uv, `pyproject.toml`, and `uv.lock`. Align local and CI versions and settings.
  Write new owned code in typed Python. Run static typing and Ruff on changed owned code and affected interfaces.
  Unrelated upstream cleanup is not a prerequisite. Prefer existing tools over new validation machinery.
- **Tests:** Cover acceptance criteria and consequential failure paths. Use relevant content checks for documentation.
  Measure coverage to locate gaps, not to impose a universal percentage gate. Do not weaken assertions to pass.
- **CI:** Establish repository-owned GitHub Actions checks as merge gates. Required checks must pass for the merge candidate.
  Use targeted local checks while editing. Full CI is not required before saving work or opening a PR.
  Ordinary CI must not depend on real-model calls or personal subscription credentials.
- **Security:** Audit relevant runtime, development, and grader dependencies for vulnerabilities.
  Scan the publication surface for secrets.
  Fix genuine danger or disable the affected capability. Document narrowly justified false positives separately.
  Do not hide real findings. An incomplete scan is unconfirmed, not clean.
- **Real execution:** Run small authorized CLI trials early. Record the version, conditions, and observed result.
  Full grading-parity and broad hostile suites apply to the affected grader or boundary, not every change.

### Acceptance and review

Astra accepts ordinary changes from applicable evidence. Sol is not a required approver for every PR.
Mechanical checks and design preferences must not create additional approval waits.
Review once and check corrections once. Then the controller resolves remaining decisions.
Further specialist review needs a specific consequential reason. Mandatory criteria cannot be waived to end a review.

| Finding | Response |
| --- | --- |
| Blocker: a violation or missing prerequisite invalidates the next action. | Hold that action; correct or verify the affected condition. |
| Required: an obligation is due before an identified increment is accepted. | Assign it and complete it before that acceptance. |
| Follow-up: an optional improvement outside current obligations. | Track when useful; do not delay acceptance. |

Tie findings to an applicable criterion, failure condition or evidence gap, and impact.
Judge each criterion as met, not met, unconfirmed, or not applicable with a reason.
An unmet condition holds only dependent work or acceptance. Continue independent authorized work.
A clean review or successful tool exit does not establish missing acceptance evidence.

## Local work and publication

A development assignment permits installing its locked dependencies inside the project environment.
Global configuration changes and out-of-scope dependency additions require separate approval.
Agree runtime, model/settings, authentication, and workload/resource limits for each assignment.
Include task count, concurrency, and retries. Runs within those limits need no repeated approval.
Changes to the agreed scope or limits require renewed authorization.

Use local Git, logs, and the working plan for continuity. Remote checkpoints are not required after every edit.
Tie results to the candidate and execution conditions. Recheck affected evidence; retain unaffected results.
Use `git` for commits and authenticated pushes, and `gh` for PR operations. Direct APIs are also valid.
Follow the [repository write rules](../../AGENTS.md#authorization-and-remote-writes) for permissions and recovery.
Keep development instructions and unrelated condition data out of experimental participant contexts.
