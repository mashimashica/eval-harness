# Eval Harness

[![Eval Harness CI](https://github.com/mashimashica/eval-harness/actions/workflows/eval-harness.yml/badge.svg)](https://github.com/mashimashica/eval-harness/actions/workflows/eval-harness.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Compare agents, models, and Skills on benchmark tasks with account-authenticated Codex CLI and Claude Code.

This repository is a fork of [NVIDIA NeMo Gym](https://github.com/NVIDIA-NeMo/Gym). It keeps the upstream environment library and adds a focused local harness for reproducible agent and Skill comparisons.

## Start with the harness guide

Read the [Local Eval Harness guide](fern/versions/latest/pages/get-started/eval-harness.mdx) before installing tools or authenticating an account. It is the canonical guide for the pinned toolchain, account setup, isolation model, supported combinations, configuration schema, and result interpretation.

## What it provides

- Runs Codex CLI and Claude Code with account or subscription authentication.
- Compares no-Skill, existing-Skill, and independently created-Skill conditions.
- Separates creation, application, and grading sessions and preserves their inputs, logs, artifacts, and hashes.
- Supports mechanical grading, AI scoring, anonymous pairwise comparison, and human criterion ratings with comments.
- Re-evaluates saved artifacts and compares reports without regenerating participant outputs.
- Runs GDPval and GSM8K with deterministic task selection, repeats, and bounded retries.

## Six commands

| Command | Purpose |
| --- | --- |
| `eval-harness check <experiment.yaml>` | Validate inputs, supported combinations, Skills, and authentication without a model call. |
| `eval-harness build <build.yaml> --out <skill-dir>` | Create a reusable Skill from an independently configured creation run. |
| `eval-harness run <experiment.yaml> --out <run-dir>` | Create optional Skills, execute tasks, save artifacts, evaluate, and aggregate. |
| `eval-harness evaluate <run-dir> --config <evaluation.yaml> --out <evaluation-dir>` | Grade saved artifacts without regenerating them. |
| `eval-harness compare <result-dir>... --out <report-dir>` | Aggregate saved evaluations without a model call. |
| `eval-harness resume <result-dir>` | Continue incomplete runs or evaluations from frozen inputs and state. |

## Minimal GSM8K run

After following the [installation and authentication guide](fern/versions/latest/pages/get-started/eval-harness.mdx), run one retained GSM8K task from the repository root:

```bash
uv run --project harness --no-sync python benchmarks/gsm8k/prepare.py
uv run --project harness --no-sync eval-harness check harness/examples/gsm8k-one-task.yaml
uv run --project harness --no-sync eval-harness run harness/examples/gsm8k-one-task.yaml --out runs/gsm8k-one-task
uv run --project harness --no-sync eval-harness compare runs/gsm8k-one-task --out reports/gsm8k-one-task
```

The example uses one Codex application call and benchmark-owned mechanical grading without a judge model. For GDPval, see the guide's verified spreadsheet example, which uses Codex with spreadsheet-capable tools.

## Verified scope

The currently verified local setup is:

- macOS with Python 3.13.14, uv 0.12.13, and the project-local harness environment.
- Standalone Codex CLI 0.154.0 and Claude Code 2.1.270, authenticated through their account or subscription flows.
- GDPval execution and AI evaluation through Codex; the restricted Claude file-tool route cannot inspect or generate office-file contents through scripts.
- GSM8K execution through Codex or Claude Code and mechanical evaluation without a judge CLI.
- Serial scheduling with `limits.concurrency: 1`; task count, retries, and each CLI timeout are explicit bounds.

Missing token or cost measurements remain `null`. Claude's reported USD value is an API-equivalent estimate, not a subscription charge. Small local trials demonstrate the workflow and do not constitute official benchmark scores.

## Results and source layout

A run records its resolved configuration, frozen inputs, execution journals, artifacts, and optional evaluations:

```text
runs/<name>/run_manifest.json
runs/<name>/run_state.json
runs/<name>/inputs/
runs/<name>/conditions/<condition>/tasks/<task>/repeat_<n>/
runs/<name>/evaluations/
runs/<name>/comparison/
```

The lightweight package is in [`harness/`](harness/), with benchmark adapters under [`harness/src/eval_harness/`](harness/src/eval_harness/) and focused tests under [`harness/tests/`](harness/tests/). Its retained benchmark preparation scripts and source data are under [`benchmarks/`](benchmarks/) and [`resources_servers/`](resources_servers/). Use the [harness package index](harness/README.md) for the project-local command reminder.

## Contributing and support

Use this fork's [issues](https://github.com/mashimashica/eval-harness/issues) for bug reports and feature requests.
The [contributing guide](CONTRIBUTING.md) covers the development entry points and targeted checks. The
[historical acceptance evidence](.agents/development/evidence/README.md) links the small real CLI trials and requirement-level evidence.

## Origin and licensing

This fork builds on NVIDIA's NeMo Gym project. See the [Apache 2.0 license](LICENSE), [third-party attributions](ATTRIBUTIONS.md), and [upstream repository](https://github.com/NVIDIA-NeMo/Gym) for project history and licensing context.

## Citation

If you use the retained NeMo Gym project in research, cite it with:

```bibtex
@misc{nemo-gym,
  title = {NeMo Gym: An Open Source Library for Scaling Reinforcement Learning Environments for LLM},
  howpublished = {\url{https://github.com/NVIDIA-NeMo/Gym}},
  author={NVIDIA},
  year = {2025},
  note = {GitHub repository},
}
```

## External materials notice

This software automatically retrieves, accesses or interacts with external materials. Those retrieved materials are not distributed with this software and are governed solely by separate terms, conditions and licenses. You are solely responsible for finding, reviewing and complying with all applicable terms, conditions, and licenses, and for verifying the security, integrity and suitability of any retrieved materials for your specific use case. This software is provided "AS IS", without warranty of any kind. The author makes no representations or warranties regarding any retrieved materials, and assumes no liability for any losses, damages, liabilities or legal consequences from your use or inability to use this software or any retrieved materials. Use this software and the retrieved materials at your own risk.
