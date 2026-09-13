<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Copyright workflow source and exact PR04 scope

The repository calls the reusable NVIDIA workflow at immutable commit `d7f020b83b60462b762eca9c24403e976dc549f2` (`v0.55.0`). Its official source file is `.github/workflows/_copyright_check.yml`, Git blob `2dc70bccaf8de76c8e4d3fa8dbcdb3c161139af0`:

<https://github.com/NVIDIA-NeMo/FW-CI-templates/blob/d7f020b83b60462b762eca9c24403e976dc549f2/.github/workflows/_copyright_check.yml>

The source declares optional string input `additional-find-args`. It interpolates that input directly after `find ./ -type f -name '*.py'`, then excludes `.git` and every `__init__.py`. For remaining files it examines the first ten lines and accepts NVIDIA copyright, MIT-license or Apache-license patterns.

Applied to the exact BigCodeBench v0.2.5 source selection:

- `eval/__init__.py` is already covered by the reusable workflow's global `__init__.py` exclusion and retains its upstream OpenAI MIT notice.
- `eval/utils.py` contains `# The MIT License` in its first line and passes the pinned check unchanged.
- `eval/_special_oracle.py` has no embedded notice. Adding one would change the verified upstream bytes.

PR04 therefore changes the caller only to:

```yaml
jobs:
  copyright-check:
    uses: NVIDIA-NeMo/FW-CI-templates/.github/workflows/_copyright_check.yml@d7f020b83b60462b762eca9c24403e976dc549f2
    with:
      additional-find-args: '-not -path "./resources_servers/bigcodebench/vendor/bigcodebench/eval/_special_oracle.py"'
```

The exception is one exact file, not the vendor directory. A repository test must require this literal input and verify the upstream license, `VENDORING.md`, tag/commit, Git blobs and content hashes. Ruff's separate `extend-exclude` covers the exact vendor directory so formatting cannot alter upstream bytes. Authored supervisor, runner, site bootstrap, installer and adapter code remain in normal copyright, Ruff, typing, test, secret-scan and applicable coverage gates.
