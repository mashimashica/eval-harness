<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Eval Harness requirements

This is the development baseline authorized by the repository owner on 2026-09-13. It describes intended capability,
not capability already present. The controller may refine acceptance criteria without changing these meanings; a change
to scope or obligations requires the owner's authorization. No old fork implementation or PR is a design requirement.

| ID | Requirement |
| --- | --- |
| R01 | Fairly and repeatedly compare how agents, models, and Skills affect artifact quality, elapsed time, and usage. |
| R02 | Support multiple existing benchmarks, including GDPval. Separate common experiment functions from benchmark-specific input, output, and grading behavior. |
| R03 | Support Codex CLI and Claude Code using their account/subscription authentication. These are the only required agent runtimes. |
| R04 | Select the benchmark, runtime, model/settings, added prompt or Skill, and evaluation method independently. Reject unsupported combinations explicitly. |
| R05 | Allow optional Skill creation before application, with separately configurable creation and application conditions. Support comparisons such as no Skill, skill-creator, and skill-creator plus ALPS without product logic dedicated to one Skill. |
| R06 | Complete task selection, optional Skill creation, task execution, artifact capture, evaluation, and comparison aggregation. Re-evaluate saved artifacts without regenerating them. |
| R07 | Support benchmark-specific mechanical grading, LLM grading or anonymous comparison, and human criterion ratings with comments. Configure AI grading separately from creation and application. |
| R08 | Separate creation, application, and grading sessions and supplied information. Do not give answers, grading materials, or other conditions' artifacts to creation/application agents. Hide condition identities during comparisons and control presentation-order bias. |
| R09 | Associate input/Skill versions, runtime conditions, logs, artifacts, judgments, elapsed time, and available usage/cost measurements. Distinguish execution completion, evaluation completion, and task success. Show variation across repeated trials; unavailable usage or cost is not zero. |
| R10 | Check prerequisites before execution; bound task count, concurrency, and retries. Resume interrupted work while preserving completed work. Do not hide failures through unapproved runtime, model, setting, or billing-route changes. |

## Application boundaries

- A small increment may establish only part of this capability; its exclusions and remaining requirements stay visible.
- Account authentication does not grant permission for an unlimited experiment. The active assignment sets execution limits.
- Benchmark-required mechanical graders are not additional agent runtimes.
- Local comparison results must not be represented as an official score unless that claim's protocol has actually been met.
- Development instructions are not an implicit intervention in experimental conditions. Keep them out of participant
  contexts unless explicitly selected and recorded as part of the experiment.
