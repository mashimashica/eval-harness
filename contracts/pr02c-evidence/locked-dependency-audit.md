<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR02c unchanged dependency audit

This is dependency-only evidence, not PR02c or final migration acceptance. The separate PR04 grader dependency lock remains unresolved.

The clean immutable checkout `66c01eefbce311592a65e9bba7d294318be3139b` supplied the unchanged dependency inputs: `uv.lock` Git blob `d35adbb6a5792de03406fc3538f3f8acbaf7b344`, `pyproject.toml` blob `5d46297218daee3b3fe0ac5c8f9fa0407dd29421`, and CI workflow blob `c07b9574ccb0747a5cd809c2c5b739a1dfd8c1ee`.

On 2026-09-13, uv 0.11.29 / Python 3.13.14 exported `--locked --extra dev --no-emit-project` with hashes. Scope checks confirmed openai, pre-commit, pytest, ruff, and anyio, without a local/workspace/project entry. `pip-audit==2.10.1 --require-hashes --disable-pip --strict --format json --aliases --requirement REQUIREMENTS` exited zero: 153 dependencies, zero vulnerabilities, zero skips. The exact report is `locked-pip-audit.json`.

Export SHA-256: `766febfc895e434e2b7a7ae462cc790503f1097cf96d40d499e799761b0ce8a3`.
Report SHA-256: `5cd0039cf642f8c0eb8f0e81d56bbd2261c5199d18701d4f9aa9c9ff524d4994`.

The formal PR must still run its unchanged dependency audit with the other required CI checks on the resulting saved head. No main dependency change has been made in PR02c.
