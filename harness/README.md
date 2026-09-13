# Local Eval Harness

`harness/` is the lightweight Python package for the repository's local, account-authenticated agent evaluation CLI.
It reuses retained benchmark inputs without starting NeMo Gym model or resource servers.

Start with the [canonical installation and usage guide](../fern/versions/latest/pages/get-started/eval-harness.mdx),
then see the [repository README](../README.md) for the short command overview and verified scope. The guide covers
authentication, native isolation, benchmark limits, evaluation methods, and resume behavior.

From the repository root, use the harness project explicitly:

```bash
uv sync --project harness --locked --no-editable
uv run --project harness --no-sync eval-harness --help
```

The package implementation is under [`src/eval_harness/`](src/eval_harness/), focused tests are under
[`tests/`](tests/), and runnable configurations are under [`examples/`](examples/). Harness development rules and
acceptance requirements are maintained in [`.agents/development/README.md`](../.agents/development/README.md).
