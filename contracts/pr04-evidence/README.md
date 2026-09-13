<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR04 dependency-lock research evidence

Status: **research checkpoint; neither lock is accepted for production**.

These files preserve the exact inputs, hash-locked resolutions, and decisive
`pip-audit` JSON used while designing the BigCodeBench grader boundary. The
resolution target was CPython 3.10.21 on
`x86_64-unknown-linux-gnu`. Resolution ran with `uv 0.12.11`; the lock-file
comments state that actual tool version. PR04's repository gate remains pinned
to `uv 0.11.29`, so an accepted lock must be regenerated and compared with that
exact binary before implementation.

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
grader environment. They do not justify an interpreter fallback. NLTK remains
a hard acceptance blocker: the official advisory marks versions through
3.10.3 affected and lists no patched release. The open upstream remediation PR
is broad (49 files and 5,170 additions at the observed head), so PR04 must not
wholesale-backport it or claim that a local version string clears the audit.

## Primary provenance

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

The JSON reports retain duplicate aliases because `--aliases` was deliberate;
the counts above are report-entry counts, not unique root-cause counts.
