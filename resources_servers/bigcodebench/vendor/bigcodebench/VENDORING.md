<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Vendored BigCodeBench native metric

These four upstream artifacts are exact copies from BigCodeBench v0.2.5, commit
`9bd90fedee89d7dc3676838c75d9642cb0cd0702`. No generation/provider package is installed by this source selection.
The metric is not the security boundary; authored supervisor/worker logic lives in `eval_harness`.

| Path here | Upstream Git blob | SHA-256 |
| --- | --- | --- |
| LICENSE | 27115b77b9e6c6c80f9b6987d8734fc8d532093c | a858540b8dfd0c74db6953edaae85bde0b671643a7e2fb04a065f4dfd25fc28c |
| eval/__init__.py | 3596f53ddbdf92455805805890aba9d75e4e10a5e6f | d5fd553559ac1b76659ebc32ae30e3e779449ecd31c5201f2301319ceeee01fe |
| eval/utils.py | 6d34de9971902dcf499ff5fb649e4abff3e7cd95 | 9061f74fe937c4eb7a1b2bc423f7acab547ae01804d5e25933e2aa8a3cc2d685 |
| eval/_special_oracle.py | 4311cc9b30e5f0d4abd742e0c632daf535be69e7 | 0cf930163987d30f455547aec6cbc500a154bc58a2eb109aa247ef4e0962448b |

Upstream repository: https://github.com/bigcode-project/bigcodebench/tree/9bd90fedee89d7dc3676838c75d9642cb0cd0702

The root license is Apache-2.0. `eval/__init__.py` and `eval/utils.py` retain embedded OpenAI MIT notices.
`eval/_special_oracle.py` is covered by the root license and has no in-file header. Preserve all upstream
bytes, including original CRLF endings. This provenance document is separately authored.

The exact source evidence remains recoverable at `checkpoint/design-pr04` commit
`deb807e8454eb4fbb3652bb1f335489fa5325bea`, under `contracts/pr04-evidence/upstream-bigcodebench-v0.2.5/`.
