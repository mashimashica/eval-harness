<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Initial lifecycle Skill validation

Date: 2026-09-13. Scope: the five lifecycle Skills and their shared development context, authored from reset base
`52557f80297314c8cd3459338a68790946d67bc0`. This is an author-side structural check and description review, not an
independent model evaluation, a performance comparison, or proof that the intended local work system is effective.

## Checks performed

- Parsed all five YAML frontmatters with PyYAML; checked allowed fields, names, descriptions, directory agreement,
  compatibility length, unique process title, Purpose/Outcomes/Tasks/Controls/Constraints sections, and the size guideline.
- Checked all new local Markdown links. Checked all five Claude aliases for target identity and checked each Skill's
  shared-context links through both the canonical path and its alias. Both paths reach the same files.
- Checked UTF-8, final newlines, trailing whitespace, conflict markers, Markdown filenames, and license markers in the
  added Markdown. Ran `git diff --no-index --check` over each new document and the focused root-instruction change.
- Reconstructed the original root `AGENTS.md` and verified its Git blob identity against
  `9785d430e7d444f2cbf6fc258da4519b1033af3d`; retained its original content and inserted only the lifecycle entry point.
- Reviewed the five descriptions against ALPS purposes, outcomes, neighboring responsibilities, shared information,
  necessary conditions, and the distinction between evidence and acceptance. The implementation Skill was adjusted to
  allow meaningful content-only checks rather than requiring irrelevant runtime tests for documentation changes.

These checks passed for the initial package. The PR identifies the submitted revision. Repeat affected checks after
changes; this historical result is not evidence for a later revision.

## Representative description cases

The following are author-performed walkthroughs of the instructions, not runs by Codex, Claude, or independent delegates.
They examine what the written rules require; they do not measure whether an agent actually follows them.

| Case | Expected decision | Rule checked / description review result |
| --- | --- | --- |
| A reviewer requests a cleaner class name after the criteria and checks are satisfied. | Treat it as Follow-up, not a reason to reopen architecture or stop acceptance. | Shared finding classes and review scope support this disposition. |
| A concrete code path supplies a grading rubric to the application agent. | Hold the affected execution/comparison, retain independent work, and request a specific correction. | R08, review grounding, and controller dependency handling cover the violation without requiring a harmful reproduction. |
| A required integration check has not run, but a reviewer finds no Blocker. | Leave the criterion unconfirmed; do not accept the dependent scope. | Controller acceptance and the Required due-criterion rule prevent approval from replacing evidence. |
| A third review requests optional improvements; one review and correction check already occurred. | Return the decision to the controller and track useful improvements separately. A new consequential defect must still be addressed. | The budget bounds repetition without making serious defects acceptable. |
| CLI help rejects the requested effort or the account session is unavailable. | Report the actual limitation; do not substitute a model, effort, or API. Unexecuted integration claims remain unconfirmed. | Runtime configuration, R10, and verification preconditions keep the failure distinct from success. |
| A command exits successfully but the required deliverable is invalid or missing. | Assess the actual acceptance criterion as not met, rather than infer success from the exit code. | Verification inspects the intended result, not only processing completion. |
| A documentation-only assignment needs a link correction. | Make the bounded content change and check its references; no compulsory architecture review or model rollout. | Implementation supports content-only checks; control selects only needed processes. |
| A local session resumes after one interface changed. | Identify the current candidate, revisit dependent evidence, preserve unrelated accepted work, and continue from the single plan. | Control reconciliation and shared information ownership define the affected scope. |
| An experimental participant starts a fresh session inside the development checkout. | Check inherited Skills and instructions; do not assume a fresh session makes the condition clean. | R08/R09 and the development-versus-experiment boundary identify the contamination risk. |
| The assignment is review-only, and the reviewer can edit the repository. | Return grounded findings without rewriting, merging, or creating new obligations. | Review constraints separate capability from authorization. |

## Not performed in this authoring environment

- Codex CLI and Claude Code discovery or live Skill applications: neither executable is installed here.
- Independent Astra/Luna/Sol trials: no independent developer/reviewer session was executed.
- `pre-commit run --all-files`: the executable and a full local checkout are unavailable; the attempted public clone
  failed at DNS resolution. Targeted checks above are not represented as the full upstream pre-commit suite.
- Benchmark rollouts or product regression tests: no harness implementation is changed by this PR. A Skill discovery
  check is still distinct from the product CLI integration tests required by a later implementation increment.

## First local acceptance exercise

Use a disposable checkout or worktree with the intended CLIs and a small, explicitly authorized workload. Preserve
symlinks. Record the actual CLI versions, resolved model/settings, Skill source revision, assignments, observations,
and judgments separately from these expected results.

1. Confirm all five Skill names are discoverable in each CLI and can read their shared references. Invoke them explicitly;
   report discovery problems rather than silently substituting manual file loading.
2. Give the controller one bounded local task with clear criteria and authority. Check that it establishes one plan,
   chooses only necessary processes, and sends the worker the target/state/authority/return context.
3. Apply design, implementation, and verification to a representative small change where each is needed. Include a
   content-only request separately to check that unnecessary work is omitted. Verify outcomes rather than file counts.
4. Give a fresh reviewer a candidate with an actual requirement violation and a separate optional improvement. Check
   classification, evidence, no unauthorized edits, and a scoped recommendation. Do not supply this expected-results
   table to the tested worker or reviewer.
5. Return a missing-evidence case and a corrected candidate to the controller. Check that it neither claims unsupported
   success nor loops on optional findings, and can resume from actual local state.

Assess these criteria with human inspection of the outputs and execution evidence. Record material failures and useful
partial results, not a single blanket pass. A successful trial supports only its examined conditions; it does not establish
that these Skills outperform the no-Skill baseline.

## Local setup

The canonical Skills are `.agents/skills/<name>/SKILL.md`.
The `.claude/skills/<name>` aliases point to those folders. Preserve symlinks when cloning.
Keep the shared `.agents/development` context and sibling Skills with the checkout.
The five Skill folders are not independently distributable packages.

Check discovery and shared links in the installed host before relying on native Skill loading.
If discovery fails, report it. Explicitly reading the canonical file is a manual application, not native discovery.
If delegation is unavailable, the controller may do compatible work and report the loss of independence.
A check requiring an independent actor must remain pending until one is available.

Start with an explicit request:

```text
Use control-development for this repository. Read .agents/development/requirements.md.
Inspect local state, establish one plan, and select a small first increment.
Apply .agents/development/README.md and delegate only the work needed.
```

Use the host's supported Skill-selection interface. The exercise above is for initial validation, not every change.
ALPS is authoring and revision support, not a mandatory step during ordinary development.

## Design basis

Initial authoring used both ALPS design responsibilities at commit `1b3d41093c37da24385765907e9fb858d28b498f`.
The Skill descriptions define the work. The shared README configures its local execution.
Consult these references when revising that design:

- [Process Description Design](https://github.com/mashimashica/alps/blob/1b3d41093c37da24385765907e9fb858d28b498f/skills/design-process-description/SKILL.md)
- [Process Framework](https://github.com/mashimashica/alps/blob/1b3d41093c37da24385765907e9fb858d28b498f/skills/design-process-description/references/process-framework.md)
- [Agent Work System Design](https://github.com/mashimashica/alps/blob/1b3d41093c37da24385765907e9fb858d28b498f/skills/design-agent-work-system/SKILL.md)
- [Work-system design principles](https://github.com/mashimashica/alps/blob/1b3d41093c37da24385765907e9fb858d28b498f/skills/design-agent-work-system/references/agent-work-system-design.md)
- [Agent Skills format](https://agentskills.io/specification)
- [Codex Skills documentation](https://developers.openai.com/codex/skills/)
- [Claude Code Skills documentation](https://code.claude.com/docs/en/skills)

The initial authoring record dates consultation of external format and host documentation to 2026-09-13.
Those live documentation links are not version pins.
