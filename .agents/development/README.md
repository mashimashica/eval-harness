<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Development work system

This checkout supplies five reusable development Skills. Their Process Descriptions are the source of meaning for the
work; this file supplies their shared controls, information interface, and local execution configuration. It is not a
sixth Skill or a mandatory five-stage pipeline. The [project requirements](requirements.md) are the source for product
obligations, not a claim of existing functionality.

## Select the work needed

| Skill | Use |
| --- | --- |
| [control-development](../skills/control-development/SKILL.md) | Start, resume, allocate, assess, and steer an authorized development scope. |
| [design-change](../skills/design-change/SKILL.md) | Resolve behavior, boundaries, interfaces, and consequential design choices. |
| [implement-change](../skills/implement-change/SKILL.md) | Change code, meaningful tests, and affected documentation; self-check. |
| [verify-change](../skills/verify-change/SKILL.md) | Establish actual behavior against selected criteria through applicable checks. |
| [review-change](../skills/review-change/SKILL.md) | Assess an assigned concern and evidence without owning implementation or acceptance. |

A normal increment is bounded by criteria, implemented and checked, then assessed by the controller. Use design when a
choice needs resolution and independent review when consequences or uncertainty justify it. The same worker may implement
and verify, but must identify self-verification as such. Do not require separate documents, agents, commits, or approvals
solely because the work has separate Skill names. Existing domain Skills remain tools for selected specialist work, not
an alternative lifecycle controller.

## Shared controls and decision rules

These rules apply to all five Skills in this repository. Must / must not are requirements; should is a recommendation;
may is permission. The current user request and applicable repository rules govern authorization. Within this fork,
[requirements.md](requirements.md) governs new harness capability; inherited NeMo implementation guidance applies where
that retained implementation is being changed, not as a mandate to add model-server or API execution routes.

For each claim distinguish **met**, **not met**, **unconfirmed**, and **not applicable with rationale**. Record the
subject, criterion, evidence, and affected scope. Format validity, a created artifact, a successful tool exit, and an
approval are not interchangeable with successful execution or fulfilled requirements.

| Finding | Meaning | Required response |
| --- | --- | --- |
| Blocker | A concrete violation, consequential failure path, or missing mandatory prerequisite makes the next dependent action unsafe or its result invalid. | Hold that action or acceptance claim, establish the smallest correction/check, and continue independent authorized work. |
| Required | An applicable obligation must be met before an identified increment or milestone can be accepted, but does not invalidate other current work. | Assign an owner and due criterion. It cannot remain outstanding when accepting the scope to which it applies. |
| Follow-up | Optional improvement, design preference, or future capability outside the current obligations. | Track only when useful; do not delay acceptance on this basis. |

A finding needs its applicable requirement/criterion, exact location or subject, failure condition or evidence gap,
impact, and basis/confidence. A reasoned code path can justify a risk; dangerous reproduction is not required. Conversely,
an unbounded hypothetical is not a Blocker. New evidence can justify reclassification; schedule pressure cannot.

Ordinary review is limited to one scoped review and one correction check per increment. At that point the controller must
resolve the remaining decision, not keep handing the same work back and forth. Additional narrowly scoped review needs a
stated consequential reason. This budget never permits ignoring a serious finding or accepting an unmet mandatory
criterion. Optional improvements do not need unanimous agreement. Whole-plan design review belongs at milestone boundaries
or when new evidence invalidates an important assumption, not at every PR.

## Local execution configuration

| Role | Initial preference | Authority |
| --- | --- | --- |
| Controller | Astra max | Plan, allocate, resolve design choices and findings, integrate, and accept within user authority. |
| Implementer / verifier | Luna max; a different setting only by explicit agreement | Execute bounded assignments and ordinary implementation decisions. |
| Specialist / independent reviewer | Sol max, when needed | Investigate or review the assigned consequential concern and return evidence. |

These are role preferences from the commissioning discussion, not literal CLI model IDs or guaranteed effort values.
The controller must resolve and record supported runtime/model/settings in the actual local environment. Do not silently
substitute a rejected model or effort. Changes of assignment are execution choices, not edits to the Skill's meaning.

Default to the controller and one implementation worker. Add at most one specialist when needed; keep a single writer
for each scope. Workers must not create nested delegates unless the user authorizes that configuration. A missing
subagent facility does not justify pretending delegation occurred: the controller may perform compatible work itself and
record the loss of independence, or hold a check that explicitly requires an independent actor.

Use the existing editor, shell, Git, test runners, and installed CLIs. Prefer a small real probe to speculative argument
about runtime behavior. Before model work, establish authentication mode, exact invocation, allowed task count, concurrency,
retry limits, and relevant resource/billing permission. Use separate temporary probe workspaces where needed; preserve
unrelated edits and never log credentials. Do not install dependencies or change global configuration without permission.

Local files retain work between sessions. Do not add a separate artifact-backup approval gate to every step. The controller
records where the current plan and evidence live, then resumes from actual state. A paid API fallback is not an acceptable
repair for an unavailable subscription runtime.

These development Skills apply to development agents, not implicitly to benchmark builders, participants, or judges. When
implementing or verifying experiment execution, check that the selected workspaces and invocation do not inherit repository
instructions, development Skills, or unrelated condition data. A fresh session alone does not prove isolation.

### Remote writes

Use an available direct GitHub API for ordinary remote commits, branch updates, and PRs. Use UTF-8 content; do not use
Actions, temporary workflows, or Base64 payload construction as editing mechanisms. On a recoverable conflict, reread the
branch/files and retry against the new state without overwriting unrelated work. For an uncertain write response, inspect
the resulting state before retrying. If the direct route is unavailable or denied, report the concrete cause and stop
remote publication; independent local work may continue. Do not route around a denied operation. Merge, release, publish,
and destructive history changes require their own applicable authorization. An internal acceptance is not that authority.

## Context interface and information ownership

The controller supplies a short assignment, either directly or by precise references:

- **Target:** purpose, bounded scope, requirement IDs, acceptance criteria, and exclusions.
- **State:** repository/workspace, branch and revision or identifiable local diff, relevant design and prior evidence.
- **Authority:** permitted edits and side effects, execution limits, write owner, and whether independence is required.
- **Return:** the decision or evidence needed next, including the plan/evidence location to update or report to.

Workers load the relevant sources, not the entire development history. They return the examined revision, changes or
observations, criterion judgments, evidence locations, and unresolved issues. A missing necessary source limits dependent
work; it does not justify inventing context. This is an information interface, not a mandatory form or new schema.

| Information | Responsible writer | Readers and change effects |
| --- | --- | --- |
| Product requirements | Owner-authorized controller | All roles; changes trigger reconsideration of affected designs, criteria, and evidence. |
| Working plan, assignments, acceptance | Controller | All assigned workers; changed scope or ownership must reach affected workers. |
| Selected design | Design assignee; controller resolves scope choices | Implementer, verifier, reviewer; changed interfaces invalidate affected checks. |
| Candidate code, tests, usage documentation | Assigned implementer | Verifier, reviewer, controller; results must identify the candidate they concern. |
| Observations and verification judgments | Assigned verifier; self-check evidence from implementer | Reviewer and controller; retain original observations and explain supersession. |
| Review findings | Reviewer; disposition recorded by controller | Implementer and controller; corrections receive a focused recheck when needed. |

Keep one working plan in an existing local file or issue and announce its location. The plan must retain the active
increment, remaining product obligations, evidence references, decisions, and next work; its format is not prescribed.
Do not copy requirements, Process Outcomes, or full logs into every Skill or maintain a parallel `contracts/` hierarchy.
Process changes revise the affected Skill and shared references; ordinary assignments and model allocation do not.

## Loading and first use

The canonical Skills are `.agents/skills/<name>/SKILL.md`. The corresponding `.claude/skills/<name>` entries are Git
symlinks to the canonical folders, following the existing checkout convention; preserve symlinks when cloning. Shared
links in the five Skills explicitly reach the repository's `.agents/development` directory from either host path.
These are repository-local Skills, not independently distributable single folders: retain the shared context and sibling
Skills with the checkout. They need no bundled processing script or mandatory ALPS invocation during normal development.

In a fresh local session, confirm the five names appear in the host's available Skills. Start with an explicit request:

```text
Use control-development for this repository. Read .agents/development/requirements.md.
Inspect the current local state, establish one working plan and a bounded first increment,
then select and delegate only the work required by its acceptance criteria.
Use the local role configuration in .agents/development/README.md.
Do not merge or publish without authorization.
```

Codex's explicit skill selection may use `$control-development`; Claude Code may use `/control-development`. Check the
installed host's supported interface. Do not treat an intended discovery path as proof that this version loaded a Skill.
If discovery fails, report it and explicitly read the canonical file for authorized manual application; do not call that
native discovery. The [validation record](validation.md) distinguishes checks performed here from local host trials still
needed. Its test prompts are validation material, not instructions to load for ordinary development.

## Design basis

The five Skills were authored using both ALPS design responsibilities at commit
`1b3d41093c37da24385765907e9fb858d28b498f`: first their purposes, observable results, and boundaries, then this allocation
of agents, existing tools, information, and execution conditions. These are authoring/revision references, not runtime
steps or a claim of universal effectiveness:

- [ALPS Process Description Design](https://github.com/mashimashica/alps/blob/1b3d41093c37da24385765907e9fb858d28b498f/skills/design-process-description/SKILL.md)
- [ALPS Process Framework](https://github.com/mashimashica/alps/blob/1b3d41093c37da24385765907e9fb858d28b498f/skills/design-process-description/references/process-framework.md)
- [ALPS Agent Work System Design](https://github.com/mashimashica/alps/blob/1b3d41093c37da24385765907e9fb858d28b498f/skills/design-agent-work-system/SKILL.md)
- [ALPS design principles](https://github.com/mashimashica/alps/blob/1b3d41093c37da24385765907e9fb858d28b498f/skills/design-agent-work-system/references/agent-work-system-design.md)
- [Agent Skills format](https://agentskills.io/specification)
- [Codex Skills documentation](https://developers.openai.com/codex/skills/)
- [Claude Code Skills documentation](https://code.claude.com/docs/en/skills)

External format and host documentation was consulted on 2026-09-13; those live pages are not version pins.
