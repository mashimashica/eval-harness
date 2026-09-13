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

### Source-backed prepared runtime locator and legacy deletion

Sol additionally reviewed fixed `1df1ef8cbf363c7e69a43d119f816a6666f79b36` after
the public-boundary draft exposed a missing connection from the standard factory and
resource app to the installer layout. Parent accepts this finite clarification.

The single trusted host setting is `BIGCODEBENCH_GRADER_SETUP_ROOT`. It supplies only
an absolute, canonical, physical setup directory, never a manifest path, policy role or
candidate selector. Missing, relative, dot/dot-dot aliases and symlink roots fail closed.
Code derives exactly these installer-owned locations beneath it:

- `pr04-bigcodebench-runtime/runtime-manifest.json`
- `pr04-bigcodebench-resources`
- `pr04-bigcodebench-venv`
- `pr04-cpython-3.11.16+20260901`
- `pr04-bwrap-0.12.0/bin/bwrap`

Runtime resolved_paths are used only for complete equality checks against those derived
paths (including the fixed NLTK child), not as executable-path inputs before verification.
No resource-local manifest shadow, arbitrary redirect, YAML/source-root fallback or new
GraderSandboxSpec field is authorized. Every production spec keeps manifest_path=None
and selects only the accepted manifest. Candidate CI continues to use its explicit trusted
candidate spec, not this factory/app environment path. The locator setting never appears
in the sandbox's literal environment allowlist and must be absent in a real child.

Permit `eval_harness/evaluators/registry.py` only for the BigCodeBench descriptor's
assets/status/isolation provenance and its BigCodeBench factory branch reading this
trusted root and passing the derived prepared resource path through the existing
constructor. Other descriptors, selection behavior and central CLI/runner remain unchanged.
Permit only the corresponding old-.bcb_venv assertion port in
`tests/harness/test_evaluator_registry.py`; no other test behavior changes in that file.
Resource app uses the same helper and removes source/YAML resource fallbacks.

Delete `resources_servers/bigcodebench/setup_bcb_venv.py` entirely; shared host resolution
makes its new compatibility wrapper redundant and prohibited. The existing CI strict-mypy
invocation may remove only that now-nonexistent path; all remaining authored resolver code
stays in measured/strict eval_harness. Remove old imports/calls/tests, not replace them with
ignored aliases or wrappers. No interpreter may be executed before its full trusted
expected identity is verified.

Required regressions include standard factory and app reaching the same fixed resolver
with a configured root; missing/relative/alias/symlink root rejection; every path redirect
and source-local shadow rejected; explicit candidate data under a production root refused;
the locator variable absent inside the sandbox; and no legacy symbol/path remaining.
This is not an accepted environment or a change to CVE/security gates.

The six strict-mypy errors are all in the legacy resource app already assigned for shared
caller replacement. Do not remove that file from typing. All 610 Linux unit methods and
CLI self-tests pass, but 11047/11791 = 93.69% coverage fails 96%; authored worker/host
failure paths need meaningful additional tests. Existing exact upstream vendor CRLF and
trailing bytes remain untouched; full applicable pre-commit passes.

Luna remains the sole implementation owner. Apply these corrections at a coherent
checkpoint boundary with the current PR04 work, save before grouped validation and
within 15 minutes, and return the fixed delta to Sol. No model experiment, merge,
release, runtime installation, candidate acceptance or audit exception is authorized.
