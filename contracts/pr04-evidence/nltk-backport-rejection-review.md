<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Rejection review: NLTK 3.10.3 minimal GHSA-8mgp backport

## Decision

Reject `nltk-3.10.3-ghsa-8mgp-minimal.patch` as a PR04 remediation candidate. Its nine narrow outside-path tests pass, but the patch breaks a normal allowed-root load and can destroy an outside file before reporting that a hardlink is forbidden. The unchanged clean `pip-audit` gate remains red; this review does not adopt the patch or grant an audit exception.

## Exact reviewed and tested inputs

| Item | Identity |
|---|---|
| Migration control checkpoint containing the option | `78472030009015e3697c0cf3ad68184f3b1ee60e` |
| NLTK source commit used for pristine and patched trees | `303f6e2ba8e4548a5f54fd65d86bb5c9a949f1db` (`3.10.3`) |
| Saved patch | SHA-256 `12501c601acdd38310f16a7c6c7a8cf51b81fd4541b60b0c090911c979209717` |
| Saved nine-test regression | SHA-256 `68ee16522ea0acd9c6f50d44ae5ed6295a58bc751aaf5fb23b5552740291afed` |
| Independent interpreter | CPython `3.13.14`, Clang `22.1.3`, cache tag `cpython-313` |
| Test platform | Linux `6.18.35` x86_64, glibc `2.39` |
| Imported test dependencies | `regex 2026.9.10`, `numpy 2.3.2`, `scipy 1.18.0` |

The patched tree was the source commit above with the saved patch applied as four tracked modifications (`nltk/VERSION`, `nltk/classify/maxent.py`, `nltk/parse/transitionparser.py`, and `nltk/tag/perceptron.py`). No model, network service, or dataset was used.

## Blocking findings

### 1. Allowed save/load raises `NameError`

The patch deletes `_authorize_private_dir` but leaves this call in `PerceptronTagger.load_from_json`:

```python
loc_path = getattr(loc, "path", None)
if loc_path and os.path.isdir(loc_path):
    _authorize_private_dir(loc_path)
```

Saving a minimal tagger under the configured allowed NLTK data root succeeds. Loading the same model then raises `NameError: name '_authorize_private_dir' is not defined`. The saved nine-test suite has no allowed-root save/load roundtrip, so it does not detect this normal-path regression.

### 2. Hardlink refusal truncates the victim first

For write modes, `nltk.pathsec._os_open_flags` adds `O_TRUNC`. `_hardened_open` calls `os.open` with those flags before `fstat` rejects `st_nlink > 1`. Opening an allowed-root hardlink therefore truncates the linked outside inode before the patch raises `PermissionError`.

The reproducer starts with `b"outside-victim-must-survive"`; after the rejected `AveragedPerceptron.save`, the outside victim is `b""` and still has link count two. This contradicts the saved validation claim that unsafe destinations are refused before bytes are written. `PerceptronTagger.save_to_json` also uses a local `O_TRUNC` opener and has no hardlink-count check.

The write primitive must open without truncation, verify the pinned descriptor's type, link count, ownership, and landed path, and only then truncate/write. Tests must assert victim bytes remain identical for every affected write sink.

### 3. Historical defaults become unusable

With enforcement enabled, `PerceptronTagger.save_to_json()` retains a shared-`/tmp` default that `validate_path` now rejects. `save_maxent_params(tab_dir="/tmp")` likewise retains its historical default and fails before doing useful work. The saved validation discloses the tagger compatibility change but omits the maxent default break. Any replacement must make and record a private staging directory inside an allowed root or explicitly revise and test the public behavior.

### 4. Companion hardening and controls are missing

The locally reviewed upstream companion commits are:

| Commit | Relevant scope absent from the minimal patch |
|---|---|
| `cbc98458b43de5f792f0382583c16df39e5c5117` | tagger load/tool path validation, removal of the stale load call, and safe staging |
| `2a92b71827d754ae8920261e7ed0c4bb283ab2d7` | maxent private staging, permissions/newline behavior, and returned selected directory |
| `a44a7af69bca87e92d9c4a701fcbbe4512e8d450` | exact TransitionParser pickle globals and `numpy.lib` denylist |

The saved test matrix checks negative outside paths but lacks benign in-root roundtrips, hardlinks at each write sink, default calls, direct language/path-shaped inputs, and FIFO/device/socket handling. Because `_hardened_open` validates file type only after opening, a FIFO can block before it is rejected. A bounded replacement should port or rederive the complete companion behavior and add those positive and hostile controls.

## Reproduction

From the workspace root, the saved narrow regression behaves as documented:

```bash
PYTHONPATH="$PWD/external-nltk-backport" \
  "$PWD/pr07-dependency-probe-v1/smoke-venv/bin/python" \
  -m unittest -v contracts/pr04-evidence/test_nltk_ghsa_8mgp_backport.py
# Ran 9 tests ... OK

PYTHONPATH="$PWD/external-nltk" \
  "$PWD/pr07-dependency-probe-v1/smoke-venv/bin/python" \
  -m unittest -v contracts/pr04-evidence/test_nltk_ghsa_8mgp_backport.py
# Ran 9 tests ... FAILED (failures=8); the negative control passes
```

The two required controls expose the rejection reasons:

```bash
PYTHONPATH="$PWD/external-nltk-backport" \
  "$PWD/pr07-dependency-probe-v1/smoke-venv/bin/python" \
  -m unittest -v contracts/pr04-evidence/test_nltk_backport_rejection_repro.py
```

Expected against the saved patch: the roundtrip errors with the stale-call `NameError`, and the hardlink control fails because the actual victim bytes are empty. Expected for an acceptable replacement: both tests pass.
