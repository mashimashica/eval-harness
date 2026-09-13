<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR04 code-start amendment and review

Astra accepts Sol's bounded review of design `deb807e8454eb4fbb3652bb1f335489fa5325bea` under the user's approved purpose-first amendment `7f7a260a`. The original frozen contract and appendix remain exact provenance. This document changes only the following operational details and closes their code-start ambiguities; it is not implementation or acceptance evidence.

## Candidate functional evidence and unchanged acceptance

The existing hash-complete 160-distribution grader lock may be installed only into an ephemeral credential-free functional test environment. Its NLTK CVE remains unresolved and strict audit remains red. No rejected patch, audit exclusion, false version or repeat M0 investigation is authorized.

Add one allowed path: `resources_servers/bigcodebench/grader-manifest.candidate.json`. Its canonical JSON has `manifest_role: "functional-boundary-candidate"`, `acceptance_eligible: false`, `dependency_audit_state: "blocked"`, and `grader_lock_sha256` containing the exact candidate lock hash, plus every original policy/provenance hash. The generated runtime manifest repeats/binds the role, eligibility, candidate-manifest digest and installed inventories. Candidate bytes must never populate `grader-manifest.json` or be described as an accepted grader.

Add exactly one final trusted spec field: `manifest_path: Path | None = None`. None resolves exclusively to `resource_dir / "grader-manifest.json"`, requiring an accepted manifest. Production evaluator/app constructors leave it None; request, YAML and environment input cannot select candidate role/path. Only dedicated test/CI code may explicitly supply the exact candidate-manifest path. Parse and bind the resolved path, role and eligibility into spec/attestation digests. A successful candidate preflight means functional readiness only, never PR acceptance.

Strict grader-lock audit is a separate first CI job/step, with no ignore/allowlist/continue-on-error. Preserve its JSON using an always-run artifact upload and retain its failed conclusion. The candidate functional job depends on that audit with an always-run condition, verifies candidate identity, and performs provisioning, strict sync, pip check, real preflight, hostile fixtures, parity and coverage. Its name, logs and artifacts explicitly identify non-acceptance candidate evidence. Final acceptance has ordinary successful dependencies and requires clean strict audit, an accepted manifest and every original functional/security/API gate; it remains failed while the CVE is unresolved. The build-tool audit remains required.

After an official fixed release becomes available, regenerate the full lock and accepted canonical manifest, clean-audit it, and rerun real gates on the exact accepted environment. Candidate evidence never substitutes for that final proof. The existing prohibition on redistributing the three unclarified NLTK data packages is unchanged; only the already allowed fixed-commit ephemeral retrieval is used.

## Authenticated native signal result

RESULT body is exactly one of:
- `{"schema_version":1,"native_status":"pass"|"fail"|"timeout"}`;
- `{"schema_version":1,"native_signal":"sigxcpu"|"sigxfsz"}`.

The notation above describes finite string alternatives, not literal JSON union syntax. Runner emits the signal form only when the single captured native Process exitcode equals negative SIGXCPU or SIGXFSZ. Host maps them to CPU or FILE_SIZE. Both keys, unknown/numeric signals, malformed frames or invalid sequence are infrastructure failures. Existing HMAC, START timing, key handling, direct host wall/memory/process enforcement and all other native signal semantics remain unchanged.

## Exact trusted mounts and untrusted roots

`forbidden_roots` identifies dynamic untrusted run/executor/workspace roots. Exact measured runner/vendor files may live under the trusted checkout; secure CPython/venv/bwrap/data roots may live under the trusted setup RUNNER_TEMP/home. Bind only the exact verified files/subtrees from the original policy, never their checkout/home/host-temp ancestors or siblings.

Reject selected binds equal to an untrusted root, selected artifacts under an untrusted mutable root, and recursively bound artifacts containing a forbidden root. Keep venv/base/vendor/data mutually disjoint. Real probes must show unselected checkout/home/tmp sibling sentinels invisible. This removes an impossible ancestor-separation requirement without widening the mount set or weakening content attestation.

## First implementation batch

Only `eval_harness/grader_sandbox.py`, `eval_harness/bigcodebench_runner.py` and `tests/harness/test_bigcodebench_runner.py`: frozen public types, pure canonical BCBI/BCBO codecs and incremental host state parsing, including the signal union and rejection cases. No process launch, native import or resource-limit execution in this batch. It is saved before deterministic verification and independent delta review. Subsequent process/isolation implementation remains mandatory.

## Finite vendor-byte and legacy fixture scope

Astra accepts Sol's source-backed scope clarification. Add `.pre-commit-config.yaml` solely for the same anchored exclusion on `end-of-file-fixer` and `trailing-whitespace`:
`^resources_servers/bigcodebench/vendor/bigcodebench/eval/(?:__init__|utils|_special_oracle)\.py$`.
Retain each hook's existing Python selector and all other hook behavior. The frozen source has three trailing-space lines in __init__.py and seven in utils.py; these hooks otherwise modify exact upstream bytes. Only those three upstream files are excluded; authored code remains fully checked. Exact vendor blob/content hashes remain mandatory and must reject drift. The existing narrow Ruff and one-file copyright rules remain unchanged.

Add only `tests/harness/test_benchmark_evaluator_edge_coverage.py` and `tests/harness/test_boundary_failure_coverage.py` for equivalent existing grader preflight/status/error fixture ports. Replace old runner/interpreter/installer patches with the typed spec and shared preflight/run seam; retain empty/no-code no-call checks and infrastructure propagation without zero metrics. These unit mocks test orchestration only. Hosted real boundary tests remain unmocked and unskipped. No other test/config scope is added.

## Native arguments for already-authorized attested fixture limits

The appendix's fixed native call `untrusted_check(code, test_code, entry_point, 8192, 6144, 10)` describes production limits. Contract sections on limits already authorize smaller values only in dedicated, attested test specifications. The worker therefore passes its validated AS/DATA/STACK byte limits converted to positive whole MiB into those same three native arguments. Reject non-integral MiB values before native import. The production call remains exactly 8192/6144/10, and public requests, YAML and environment cannot select smaller limits. This avoids the unchanged vendored child trying to raise inherited hard limits during a smaller test fixture. No default native timing or other metric argument changes. Sol reviewed this finite clarification with the worker correction.

## Read-only implicit root and device filesystem

During independent review of host checkpoint `64e9855b796047d351e67c2b14006eccf5ad2414`,
Sol identified that bubblewrap's implicit root and `--dev` filesystem are separate tmpfs
mounts without the private scratch size limits. Leaving them writable permits candidate
files outside the intended bounded `/tmp` and `/dev/shm` trees. Per-file rlimits and process
RSS do not establish a bound for that aggregate file storage.

Astra approves this finite correction to realize the existing filesystem/resource boundary:
after all mountpoints, directories, binds and symlinks have been created, the sole command
builder adds nonrecursive `--remount-ro /dev` followed by `--remount-ro /`. Nested `/tmp` and
`/dev/shm` remain separately mounted writable tmpfs with their original size limits;
the private devpts mount retains its device semantics. No new writable host bind, sandbox
fallback, dependency exemption, or changed native metric is introduced.

The exact-operation unit fixture must include both operations, and the real Linux probe
must verify that root, `/etc`, unselected `/opt` siblings and `/dev` reject regular-file
creation while bounded private scratch still works. This is an additional acceptance
requirement, not proof that it has passed. All prior accepted worker/protocol facts remain
scoped to their immutable source, and final policy/manifest hashes must bind the final code.

For the installed `RLIMIT_NPROC` baseline, count Linux tasks belonging to the real UID:
sum the positive `Threads` value for matching first `Uid` values in numeric process status
records. Proc-directory ownership and process-leader count do not measure that kernel limit.
Transient disappearance may be ignored; unreadable or malformed live records fail closed.

Root read the exact pinned upstream source to confirm this amendment: bubblewrap commit
`2a76602a8c71f36c1527cf9fc3417d9149822e0c`, `bubblewrap.c` blob
`9192550540d3c4f173a7308c11e518e18ef4c303` (root tmpfs at lines 3232–3260 and
device/devpts mounts at 1431–1478), and `bwrap.xml` blob
`ca717abd6001a4e07557253578d41b0e813aaf31` (next-tmpfs-only size and nonrecursive
remount semantics at 277–285 and 315–316). Source URLs:
[implementation](https://github.com/containers/bubblewrap/blob/2a76602a8c71f36c1527cf9fc3417d9149822e0c/bubblewrap.c)
and [option reference](https://github.com/containers/bubblewrap/blob/2a76602a8c71f36c1527cf9fc3417d9149822e0c/bwrap.xml).
