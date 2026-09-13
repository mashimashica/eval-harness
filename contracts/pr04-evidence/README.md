<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR04 dependency-lock research evidence

Status: **research checkpoint; no lock is accepted for production**.

These files preserve the exact inputs, hash-locked resolutions, and decisive
`pip-audit` JSON used while designing the BigCodeBench grader boundary. The
first resolution target was CPython 3.10.21 on
`x86_64-unknown-linux-gnu`. The newer candidate explicitly targets CPython
3.11.16 and was regenerated with the repository-pinned `uv 0.11.29`.

## Files

| File | Meaning | Acceptance state |
|---|---|---|
| `bigcodebench-v0.2.5-requirements-eval.txt` | Exact BigCodeBench v0.2.5 upstream evaluation requirements input | Evidence only; unsafe pins |
| `bigcodebench-v0.2.5-upstream-py310.lock` | Hash-complete resolution of the unmodified upstream input | Rejected by audit |
| `bigcodebench-v0.2.5-upstream-py310-pip-audit.json` | Full audit result for the upstream resolution | 319 alias-inclusive findings across 17 distributions |
| `bigcodebench-v0.2.5-py310-security-overrides.txt` | First-pass security override input | Research input only |
| `bigcodebench-v0.2.5-candidate-py310.lock` | Hash-complete first-pass candidate resolution | Rejected by audit |
| `bigcodebench-v0.2.5-candidate-py310-pip-audit.json` | Full audit result for the candidate resolution | Nine alias-inclusive findings across three distributions |
| `bigcodebench-0.2.5-pypi.json` | PyPI project/release metadata captured for package provenance | Evidence |
| `bigcodebench-v0.2.5-py311-security-overrides.txt` | Explicit Python 3.11.16 compatibility/security overrides | Research input |
| `bigcodebench-v0.2.5-candidate-py311.lock` | uv 0.11.29, 160-distribution hash-complete candidate | Rejected by NLTK audit |
| `bigcodebench-v0.2.5-candidate-py311-pip-audit.json` | Full strict aliased audit | One NLTK finding, no fix |
| `bigcodebench-v0.2.5-candidate-py311-sync-dryrun.txt` | Exact uv 0.11.29 hash-required sync dry run | Resolves all 160 |
| `nltk-3.10.3-pypi.json` | Official PyPI release/artifact metadata | Provenance |
| `nltk-3.10.3-ghsa-8mgp-minimal.patch` | Narrow advisory experiment | **Rejected; do not install** |
| `test_nltk_ghsa_8mgp_backport.py` | Incomplete negative-control/advisory-API regression | 9/9 patched, but insufficient |
| `nltk-backport-validation.md` | Historical commands/build/audit record | Rejected evidence |
| `nltk-backport-rejection-review.md` | Independent normal-path/hardlink review | Decisive rejection |
| `test_nltk_backport_rejection_repro.py` | Exact benign-roundtrip/destructive-hardlink reproducer | Fails rejected patch |
| `nltk-data-index-550b6625.xml` | Exact official data index at commit `550b6625...` | Data-lock input |
| `cpython-3.11.16-20260901-provenance.md` | Immutable interpreter asset/API/source and extraction evidence | Artifact selected; CI install unvalidated |
| `requirements-bwrap-build.in` | Exact Meson/Ninja build-tool input | Research input |
| `requirements-bwrap-build.lock` | uv 0.11.29 hash-complete Meson/Ninja lock | Sync and `pip check` passed |
| `requirements-bwrap-build-pip-audit.json` | Strict aliased pip-audit 2.10.1 report | Two distributions, zero findings |

The audit invocation was equivalent to:

```text
uvx --from pip-audit==2.10.1 pip-audit \
  --require-hashes --disable-pip --strict --aliases --format json \
  --requirement <lock-file>
```

Each command exited `1` because findings were present. The first-pass
candidate leaves these material findings:

| Distribution | Resolved version | Finding aliases in JSON | Published fix represented in audit data |
|---|---:|---:|---|
| `cryptography` | 49.0.0 | 2 | 50.0.0 |
| `keras` | 3.12.3 | 6 | latest required fix is 3.15.0 |
| `nltk` | 3.10.3 | 1 | none |

`cryptography` and `keras` can be investigated in an explicit CPython 3.11.16
grader environment. That candidate clears their findings and leaves only NLTK.
NLTK remains a hard acceptance blocker: the official advisory marks versions
through 3.10.3 affected and lists no patched release. The preserved narrow backport is rejected: the added independent controls expose
a normal-load regression and destructive hardlink truncation. Its truthful local
version also cannot be attested by ordinary strict pip-audit. PR04 must not install
or claim this patch as remediation.

## Primary provenance

* CPython grader artifact: immutable Astral release `20260901`, asset ID
  `539915682`, source target `4bb01f09aaf362c71e891be4a41cb6d6ddf830b3`:
  <https://github.com/astral-sh/python-build-standalone/releases/tag/20260901>
* Exact uv source entry for that artifact, provenance only (production remains uv 0.11.29):
  <https://github.com/astral-sh/uv/blob/4b53f66b79c59c69eef428289904300df9e4df92/crates/uv-python/download-metadata.json>
* BigCodeBench tag `v0.2.5`: commit
  `9bd90fedee89d7dc3676838c75d9642cb0cd0702`, requirements blob
  `82e1e6bf0b1f27f8bcea60f0f6f667ee24f8d572`.
  <https://github.com/bigcode-project/bigcodebench/tree/9bd90fedee89d7dc3676838c75d9642cb0cd0702>
* BigCodeBench PyPI release metadata and artifacts:
  <https://pypi.org/pypi/bigcodebench/0.2.5/json>
* NLTK advisory `GHSA-8mgp-746c-j5xp` / `CVE-2026-81726`:
  <https://github.com/nltk/nltk/security/advisories/GHSA-8mgp-746c-j5xp>
* NLTK remediation PR 3753, observed head
  `e767d22787a88b89ab7063050d879e9d24f3a028`:
  <https://github.com/nltk/nltk/pull/3753>
* Draft NLTK 3.10.4 release PR 3826, observed head
  `37da42aaad1e0a07699ddc4de1f7c2a8773f296a`:
  <https://github.com/nltk/nltk/pull/3826>
* NLTK tag `3.10.3`, commit
  `303f6e2ba8e4548a5f54fd65d86bb5c9a949f1db`:
  <https://github.com/nltk/nltk/tree/303f6e2ba8e4548a5f54fd65d86bb5c9a949f1db>
* Official merged minimal-fix commits:
  <https://github.com/nltk/nltk/commit/a44a7af69bca87e92d9c4a701fcbbe4512e8d450>,
  <https://github.com/nltk/nltk/commit/2a92b71827d754ae8920261e7ed0c4bb283ab2d7>,
  <https://github.com/nltk/nltk/commit/cbc98458b43de5f792f0382583c16df39e5c5117>.
* NLTK data index commit `550b6625bcef1f2abff2ff770a5a0d272c9c6b2a`:
  <https://github.com/nltk/nltk_data/tree/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a>.

The JSON reports retain duplicate aliases because `--aliases` was deliberate;
the counts above are report-entry counts, not unique root-cause counts.
