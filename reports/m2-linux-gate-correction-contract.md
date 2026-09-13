<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR04 finite first-Linux gate corrections

Parent accepts Sol's read-only review of implementation
`0c919a5cd1256af121a912bef5a42cf41d5e360b` and first hosted run `34750244430`.
This is a bounded implementation clarification, not acceptance evidence or a new design.
Source/evidence are preserved in `reports/m2-linux-first-validation.json`.

## Exact Ninja distribution versus binary identity

Retain the complete build lock, its hash, Ninja distribution `1.13.0`, Meson `1.9.1`
and the fixed absolute build-venv executable paths. The official Linux wheel is
`ninja-1.13.0-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl`, 180716 bytes,
SHA-256 `fb46acf6b93b8dd0322adc3a4945452a4e774b75b91293bafcc7b7f8e6517dfa`.
Its wheel METADATA version is `1.13.0`; the executable member
`ninja-1.13.0.data/scripts/ninja` contains the version literal
`1.13.0.git.kitware.jobserver-pipe-1`. The same distribution's actual macOS binary
emits that literal. The current CI script incorrectly compares this binary output
with the distribution-only version and stops before compilation.

Require both `importlib.metadata.version("ninja") == "1.13.0"` in the build venv
and exact executable stdout equal to that one observed literal. Do not allow an arbitrary
suffix, prefix-only version, alternate distribution, weaker hash or inherited Ninja.
Keep executable quoting and add official-output, near-version, extra-line/CR and
space-containing path regressions. Then verify the actual Linux build output and tests.
The current issue has one failed initial hosted run and zero corrective attempts.

The official [PyPI release metadata](https://pypi.org/pypi/ninja/1.13.0/json) proves
distribution/wheel identity, not the exact binary string: its prose mentions a different
suffix. Binary-string evidence comes from the hash-verified wheel and actual execution;
do not silently treat the inconsistent prose as a second accepted binary version.

## Exact secret-detector false positives

Sol classified all 62 findings from run `34750244668`, job `103705371214`, as public
package/content/tree/license digests or Git identifiers; all are Hex High Entropy String.
The five path counts are candidate manifest 7, index.xml 14, NLTK manifest 32,
grader installer 7 and bubblewrap installer 2. No credential-indicating finding appeared.
Candidate local bindings match actual source/lock/data bytes; index digests match the
seven data packages. Do not output these values as credentials or rewrite exact source
and canonical manifests to avoid the detector.

Add only `.github/workflows/config/.secrets.baseline` to the PR04 allowed path list.
With detect-secrets `1.5.0`, add only these exact filename/value-hash findings, retaining
the existing two entries and every plugin/filter setting. The reviewed fixed source
therefore yields 64 entries. If a subsequently reviewed measured-source change updates
one of these provenance digests, record that exact old/new binding and regenerate only
its corresponding finding; classify any unexpected new finding before including it.
Do not add file/directory exclusions, disable plugins, hide genuine credentials, change
audit rules or rewrite history. This false-positive treatment is unrelated to the NLTK CVE.

Required checks: same-version hook succeeds on the reviewed source; only this finite
baseline delta exists; and a new private temporary high-entropy fixture not in the baseline
still fails the hook. Keep the synthetic value out of persisted logs. Sol reviews the
fixed baseline/source delta before a formal PR update. The actual hosted secret gate
must pass on the promoted head; local classification alone is not acceptance.

## Remaining existing work

The six strict-mypy errors are all in the legacy resource app already assigned for shared
caller replacement. Do not remove that file from typing. All 610 Linux unit methods and
CLI self-tests pass, but 11047/11791 = 93.69% coverage fails 96%; authored worker/host
failure paths need meaningful additional tests. Existing exact upstream vendor CRLF and
trailing bytes remain untouched; full applicable pre-commit passes.

Luna remains the sole implementation owner. Apply these corrections at a coherent
checkpoint boundary with the current PR04 work, save before grouped validation and
within 15 minutes, and return the fixed delta to Sol. No model experiment, merge,
release, runtime installation, candidate acceptance or audit exception is authorized.
