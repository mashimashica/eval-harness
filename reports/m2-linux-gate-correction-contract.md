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

### Full-tracked baseline supplement

At `7282be1a149c7352b91fd3df1a3b9f712ef9d1b5`, the five-path hook passes and a
private unrelated negative control is detected. The first full-tracked hook finds two
additional existing public integrity values in `config/experiments/alps-skill-creation.json`:
line 22 source_revision (40 hex) and line 40 expected_bundle_sha256 (64 hex). Parent
verified the file is byte-identical to accepted base `6038a782`; it defines the
alps-work-design reference input's immutable revision and expected bundle hash.
Sol independently permits exactly these two same-file/same-detector/value-fingerprint
entries. Preserve the existing 64 entries and every setting, yielding 66; do not modify
the config, add exclusions or alter CVE handling. Full-tracked hook must then pass and
the independent private negative control must still fail. This extends the finite
classification based on new full-scope evidence, not a repeat of the prior 62 findings.

## Remaining existing work

### Second-Linux capability inspection and upstream skip diagnostics

Sol reviewed formal `d3dc022f6eae7d2fbc12a1078ef7e8079e813782` and the second
Linux evidence on control `3c10ebe0ac0d343667bc1af320f8ae38ef3754ca`. Ninja now
passes actual configuration/build and is closed after one correction. The next failure
is a distinct initial `getcap` lookup failure: installer PATH omits `/usr/sbin`;
whether libcap2-bin was physically installed was not recorded. Do not repeat version
investigation or infer that the host lacked the package.

Replace only the external getcap inspection with the already verified harness Python,
quoted and invoked with `-I -B`, calling
`os.getxattr(binary, "security.capability", follow_symlinks=False)`. Only an OSError
whose errno equals Linux `errno.ENODATA` proves absence and passes. Every returned
value, including empty bytes, proves attribute presence and fails. Every other errno
and unexpected exception fails with a fixed, secret-free diagnostic: no path, errno,
traceback or exception text. Preserve existing regular/non-symlink, mode, link count,
owner, version, ELF and subsequent content-hash checks. No new package, relaxed
capability requirement, PATH fallback or elevated host-policy operation is permitted.

Required negative controls cover empty/nonempty attributes, EPERM/EACCES/ENOTSUP/EIO,
an unexpected exception, exact path and follow_symlinks=False, diagnostic redaction and
absence of any remaining getcap command. ENODATA alone passes. This kernel-bounded
metadata inspection removes an unnecessary external-tool dependency without weakening
the frozen no-file-capabilities requirement. The issue has one initial failed run and
zero corrective attempts before this change.

The same semantic rule applies to public host metadata inspection: the first public
correction independently retained getcap there. Its removal is part of that unclosed
public correction, separate from the reviewed installer-only delta.

Use Meson's verbose test output to retain actual reasons for the five upstream skips.
Keep tests enabled, do not turn skip into pass or disable namespace restrictions, and
do not change host sysctls/security policy. Real preflight, hostile fixtures and native
parity remain independent required gates; none has yet run.

### Third-Linux Python installer and read-only host diagnosis

Sol reviewed formal `2d022f7649f8ee159a63593028f74b23b5b665fd`, candidate job
`103715743292`. Shell xattr inspection and hosted secret scanning pass. The Python
installer then fails after about 0.11 seconds with a generic provisioning diagnostic.
Its `_verify_bwrap` still invokes PATH-dependent getcap at line 457. This is compatible
with the observed failure, not proof of its cause. Replace that invocation with the same
strict direct xattr semantics above: follow_symlinks=False, ENODATA alone passes, every
return including empty bytes and every other exception fails. Keep metadata, ELF,
version, hash and build-record checks. No PATH/package fallback is needed or permitted.

Expose only fixed allowlisted phase codes on CLI failure, never str(exc), command,
path, environment, captured stdout/stderr or traceback. The finite phase vocabulary is:
platform-inputs, harness, policy, uv, bwrap-metadata, bwrap-version, bwrap-elf,
bwrap-capability, bwrap-provenance, root-create, python-download, python-extract,
python-identity, venv, sync, check, bootstrap, nltk, runtime-write. Unexpected exceptions
must fail nonzero with fixed phase=internal. Test nested secret-bearing exceptions and
prove no sensitive text escapes. This is diagnostic precision, not success or fallback.

The five upstream namespace/sandbox test skips now disclose the actual reason:
`bwrap: setting up uid map: Permission denied`. Zero sandbox subtests passed. This is
compatible with AppArmor/userns mediation but the specific host cause is unconfirmed.
For the next meaningful candidate CI run permit bounded, canonical JSON diagnostics
with strict field grammars and only these read-only facts:

- OS ID/VERSION_ID; uname system/release/machine, not nodename; real/effective UID/GID.
- `/proc/sys/user/max_user_namespaces`, `/proc/sys/kernel/unprivileged_userns_clone`,
  `/proc/sys/kernel/apparmor_restrict_unprivileged_userns`.
- `/sys/module/apparmor/parameters/enabled` and `/sys/kernel/security/lsm`.
- `/proc/self/uid_map`, `/proc/self/gid_map`, `/proc/self/setgroups`.
- `/proc/self/status` fields Uid, Gid, NoNewPrivs, Seccomp, Seccomp_filters,
  CapInh, CapPrm, CapEff, CapBnd and CapAmb only.
- Current AppArmor label classified only as unconfined/confined/unavailable, not raw.
- If loaded profiles are readable, boolean exact custom BUBBLEWRAP_PATH profile match;
  unavailable must remain distinct from false. Do not print profile text or paths.

No environment, cmdline, dmesg, audit logs, full status/profile bodies, credentials or
path dumps. No sudo, sysctl write, profile change, privilege elevation, namespace
weakening or skip-as-acceptance. Existing installer/preparation tests and candidate
workflow are the finite allowed source scope. Luna is the only source writer; apply at
a coherent boundary, save before validation, and obtain fixed-head independent review.
Actual isolation and dependent parity acceptance stay held while independent work proceeds.

### Fixed uv for the mandatory fresh preflight dependency check

Sol reviewed fixed `7282be1a` against frozen preflight item 1, which requires an actual
uv pip check before model work. Installer-time success alone is insufficient. This is
a finite implementation connection, not a selector/API redesign or new dependency.

During preparation copy the already verified uv 0.11.29 to exactly
`SETUP_ROOT/pr04-grader-tools/uv`. Create the tools root exclusively with mode 0700,
real-UID ownership and physical-path checks. Create the uv file exclusively as a regular,
single-link real-UID-owned file with exact 0755 mode and no file capability/set-ID bits;
never overwrite an existing destination or copy xattrs through copy2. Verify source hash
before/after copying equals copied content, then check the copy's exact version output.
On partial failure clean up only the destination/root created by this attempt.

The runtime manifest must bind the fixed path, copied SHA-256 and fully verified version
stdout (including the accepted official suffix) with an exact mandatory field schema.
Host code derives this one additional fixed child; runtime values are equality checks,
never executable selectors. Add the uv identity to preflight/attestation and grade-time
stale comparisons. Missing/extra/redirected/wrong-hash/version fields fail. Do not add a
Spec field, mount uv into the grader, or forward host UV settings to the sandbox.

Under the exclusive UID lock, revalidate layout, runtime, every existing identity and uv
metadata/hash before executing uv or bubblewrap. Use exact absolute executables and
fixed trusted cwd with a clear/explicit allowlisted environment (no inherited UV/PIP,
proxy, token or VIRTUAL_ENV settings). The fixed command is:

`uv --offline --no-cache --no-config --no-managed-python --no-python-downloads pip check --python <fixed-venv/bin/python>`

`--no-config` prevents cwd/ancestor uv.toml or pyproject discovery. Verify the actual
locked CLI accepts these controls. Keep stdin DEVNULL, close_fds, no passed fds, new
session, bounded stdout/stderr and total/cleanup deadlines. Nonzero, launch error,
timeout, output flood or observation failure produces a stable redacted infrastructure
failure and complete process-tree kill/reap. Recompare at least full venv inventory
after the check; mutation fails before bubblewrap. No downloads, sync or repair at grade
time is allowed.

Required regressions: fixed path versus runtime redirect; missing/extra/hash/version
identity; symlink/hardlink/mode/owner/capability; lock-wait drift rejected before Popen;
exact argv/env/cwd; nonzero/timeout/flood/cleanup; venv mutation during check. The real
Ubuntu job must exercise the locked uv on a valid environment and a private corrupted
fixture with expected nonzero. Unit doubles cover argument/error behavior only and do
not replace actual dependency/sandbox acceptance. Existing installer/host/preparation
test scope is sufficient; preserve candidate-only eligibility and all audit gates.

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
