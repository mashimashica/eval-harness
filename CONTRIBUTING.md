# Contributing to this fork

This repository is a fork of [NVIDIA NeMo Gym](https://github.com/NVIDIA-NeMo/Gym) with a local,
account-authenticated Eval Harness. Contributions to the harness and to the retained NeMo Gym code have different
setup and validation paths.

## Start here

Read [`AGENTS.md`](AGENTS.md) and the [shared development context](.agents/development/README.md) before changing
code. The shared context is the authority for requirements, lifecycle roles, quality gates, and publication rules;
the [Local Eval Harness guide](fern/versions/latest/pages/get-started/eval-harness.mdx) is the authority for harness
installation and CLI usage.

Keep changes scoped to the assigned component, preserve unrelated work, and do not run candidate code before its
required isolation has been checked. Harness checks use local fixtures and do not require model calls, subscription
credentials, upstream NVIDIA access, or the retained NeMo Gym full test suite.

## Harness development

Install the locked project environment from the repository root:

```bash
uv sync --project harness --locked --no-editable
```

Run the targeted checks used by the harness workflow:

```bash
uv run --project harness --no-sync pytest -c harness/pyproject.toml harness/tests -q
uv run --project harness --no-sync ruff check harness
uv run --project harness --no-sync ruff format --check harness
uv run --project harness --no-sync mypy --config-file harness/pyproject.toml harness/src/eval_harness
```

After source changes, either refresh the non-editable package with
`uv sync --project harness --locked --no-editable --reinstall-package eval-harness`, or prefix each check with
`PYTHONPATH=harness/src` and keep `--no-sync`; otherwise the installed package may be stale. The non-editable install
is the fresh-checkout and CI path. Do not add account credentials, generated runs, or downloaded benchmark data to a
change. The harness's real CLI trials require the separate authentication and isolation procedure in the [Local Eval
Harness guide](fern/versions/latest/pages/get-started/eval-harness.mdx).

The fork-owned [`Eval Harness` workflow](.github/workflows/eval-harness.yml) runs the locked tests, lint, typing,
dependency and documentation checks. It does not invoke a live model or depend on personal account authentication.

## Retained NeMo Gym development

For changes to the retained environment, agent, model, or training code, follow the upstream [NeMo Gym development
documentation](https://docs.nvidia.com/nemo/gym/latest/contribute/development-setup) and the affected component's
instructions. The root project may have broader dependencies and checks than the lightweight harness project.

## Licensing and commits

Contributions must be compatible with Apache-2.0. See [`LICENSE`](LICENSE) and [`ATTRIBUTIONS.md`](ATTRIBUTIONS.md).
New source files need the standard NVIDIA SPDX header required by [`AGENTS.md`](AGENTS.md); preserve third-party
notices when modifying vendored code.

Include a DCO sign-off on every commit:

```bash
git commit -s -m "Describe the change"
```

Explain the user-visible behavior, relevant validation, and any unresolved limitation in the pull request. Do not
claim a local harness trial as an official benchmark score.
