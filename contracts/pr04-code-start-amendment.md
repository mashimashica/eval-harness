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
