<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Rejected NLTK GHSA-8mgp minimal-backport validation

**State:** **REJECTED** remediation experiment, not an acceptable dependency and not a clean standard audit result. The narrow test/build results below remain factual but were insufficient. Independent controls in `nltk-backport-rejection-review.md` show a benign load `NameError` and destructive hardlink truncation before rejection.

## Exact source and patch

- Base: official NLTK tag `3.10.3`, commit `303f6e2ba8e4548a5f54fd65d86bb5c9a949f1db`, tree `6bd488f92cce89d9e5616a70fdb6707e26946ce8`.
- Base blobs: `nltk/classify/maxent.py` `73ff4b093ee4f069cd33d033f3b68c9ca417b4c0`; `nltk/parse/transitionparser.py` `94ab45bc2e849affa4032d11c2b1648f18d89e29`; `nltk/tag/perceptron.py` `640839b50fbf35ac07ee5909d63c10e93e63ea88`; `nltk/pathsec.py` `0a79bc5a5aad84a29f535257021575ebed28f578`; `LICENSE.txt` `d645695673349e3947e8e5ae42332d0ac3164cd7`.
- Patch: `nltk-3.10.3-ghsa-8mgp-minimal.patch`, SHA-256 `12501c601acdd38310f16a7c6c7a8cf51b81fd4541b60b0c090911c979209717`, 9,891 bytes, 239 lines.
- The patch is a narrow derivation of fixes already merged to official NLTK `develop`: transition parser commit `a44a7af69bca87e92d9c4a701fcbbe4512e8d450`, maxent commit `2a92b71827d754ae8920261e7ed0c4bb283ab2d7`, and perceptron commit `cbc98458b43de5f792f0382583c16df39e5c5117`. It is not a wholesale backport of open PR 3753.
- The version is truthfully `3.10.3+evalharness.ghsa8mgp1`. The upstream Apache-2.0 license remains intact.

## Regression result

`test_nltk_ghsa_8mgp_backport.py` exercises a pathsec negative control, every API named by the advisory, a symlink write, and a path-shaped PerceptronTagger filename component.

```text
PYTHONPATH=<pristine-3.10.3> python -m unittest -v \
  contracts/pr04-evidence/test_nltk_ghsa_8mgp_backport.py
# Ran 9 tests: FAILED (failures=8); only the pathsec negative control passed.

PYTHONPATH=<patched-source> python -m unittest -v \
  contracts/pr04-evidence/test_nltk_ghsa_8mgp_backport.py
# Ran 9 tests in 1.213s: OK.
```

That narrow matrix omitted normal allowed-root roundtrips, validate-before-truncate hardlink controls, FIFO/device/socket handling, default-path behavior, and complete companion changes. The rejected patch also left a deleted-helper call in `load_from_json`. Passing these nine tests therefore provides no acceptance evidence.

## Deterministic wheel build

Two fresh trees were made from the exact tag archive, the exact patch was applied, and each was built with CPython 3.11.16, uv 0.12.11, setuptools 84.0.0, wheel 0.46.3, `PYTHONHASHSEED=0`, and `SOURCE_DATE_EPOCH=1786571315`:

```text
PYTHONHASHSEED=0 SOURCE_DATE_EPOCH=1786571315 uv build \
  --wheel --no-build-isolation --python <python-3.11.16> \
  --out-dir <fresh-output> <fresh-patched-source>
```

Both wheels were byte-identical:

```text
nltk-3.10.3+evalharness.ghsa8mgp1-py3-none-any.whl
size: 1,799,409 bytes
sha256: 1a2006cfdb05170246aecfe84d24ffa7d659fc67055d9ef8e297d1b5715605a0
```

Omitting `PYTHONHASHSEED=0` changed only ordering of `Requires-Dist` entries in wheel metadata and therefore changed the wheel hash. The fixed seed is part of the required build recipe.

## Standard audit remains red

The unmodified Python 3.11.16 lock resolves 160 distributions and strict `pip-audit` 2.10.1 reports exactly NLTK `PYSEC-2026-3740`, aliases `CVE-2026-81726` and `GHSA-8mgp-746c-j5xp`, with no fix version.

The deterministic wheel contains the rejected code and must not be installed. Independently, a truthful local-version wheel cannot be represented as a clean ordinary audit:

- strict hashed requirements audit rejects the direct URL: `nltk: URL requirements cannot be pinned to a specific package version`;
- strict installed-path audit exits 1: `Dependency not found on PyPI and could not be audited: nltk (3.10.3+evalharness.ghsa8mgp1)`.

Changing the distribution name, pretending it is upstream 3.10.4, or ignoring the finding would evade rather than satisfy the gate. The existing clean standard audit gate remains unresolved. Under the unchanged migration gate, acceptance requires an official fixed release and a regenerated clean lock. Any alternate audit policy would require the user’s explicit plan amendment. No such amendment exists.
