<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR04 initial fixed-preparation review

Reviewer: Sol, read-only. Parent: Astra. Implementer: Luna.
Fixed base `debe87e56552f073d029eb5038a102784f9d2348`; reviewed head
`88fdbcffead2adb63c0f1871fd4805cf6c07d056`.
Criteria: saved PR04 boundary contract, appendix and finite amendments. Existing host
supervision, worker and bootstrap closure is not reopened.

All seven findings block installation readiness, not only final PR acceptance:

1. P1, candidate policy and installer lines 299/344: pretty JSON is sent to the compact
   canonical policy reader. Candidate must be canonical; frozen NLTK metadata bytes must
   stay exact and be hash-verified before ordinary JSON parsing.
2. P1, installer lines 323–338/370/416: NLTK extraction drops category/id hierarchy and
   the generated path differs from the selected sandbox data root. Exact seven package
   identities, 167 files, 85,741,209 bytes and the separate content-inventory digest are
   not verified.
3. P1, installer lines 341–355/395–420: accepted-looking input with candidate=False can
   issue an eligible runtime while retaining the rejected candidate lock. This interim
   installer must be candidate-only; no accepted output is authorized.
4. P1, installer lines 366–430 and candidate policy: source/policy/runtime binding is
   incomplete, including Python/build lock, runner/bootstrap/vendor/data identity,
   bubblewrap binary hash and OS build-package versions.
5. P1, installer lines 359–415 and shell lines 32–40/129–132: fixed uv, Ubuntu and harness
   interpreter identity are not verified.
6. P1, installer lines 261–279/392–415: the physical venv Python copy lacks exact
   version/architecture/SOABI, sys.prefix and pyvenv.cfg home readback checks.
7. P1, shell lines 141–151: the mode glob rejects valid 0755; owner, single-link and
   ELF x86-64 machine checks are also missing.

Required regressions include actual archive success and traversal/duplicate/link/special
cases, candidate/accepted separation, policy/source identity mutation, correctly prepared
data layout/content inventory, interpreter/platform/toolchain and binary metadata failure
cases. The initial archive test only covers traversal despite its broader name.

The parent ran the separate grouped unit/static checks recorded in
`m2-preparation-initial-validation.json`. No network retrieval, environment installation,
NLTK execution, real sandbox or parity ran. This is the initial draft review; no corrective
round has yet been verified. Luna receives one consolidated bounded correction; unchanged
evidence and closed dependency investigation are not repeated.
