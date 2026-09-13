<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Exact BigCodeBench v0.2.5 metric source evidence

The `*.source` files in this directory are byte-for-byte recoverable copies of the only BigCodeBench modules selected for PR04 native grading, plus the upstream root license. The `.source` suffix is evidence packaging only; implementation copies the same bytes to their original `.py`/`LICENSE` names under the documented vendor directory.

- Repository: <https://github.com/bigcode-project/bigcodebench>
- Tag: `v0.2.5`
- Commit: `9bd90fedee89d7dc3676838c75d9642cb0cd0702`
- Root license: Apache License 2.0
- Embedded notices: `eval/__init__.py` and `eval/utils.py` contain the upstream OpenAI MIT notice; `_special_oracle.py` has no embedded header and is governed by the root license.

| Evidence path | Upstream path | Git blob | Content SHA-256 |
|---|---|---|---|
| `LICENSE.source` | `LICENSE` | `27115b77b9e6c6c80f9b6987d8734fc8d532093c` | `a858540b8dfd0c74db6953edaae85bde0b671643a7e2fb04a065f4dfd25fc28c` |
| `bigcodebench/eval/__init__.py.source` | `bigcodebench/eval/__init__.py` | `3596f53ddbdf92455805890aba9d75e4e10a5e6f` | `d5fd553559ac1b76659ebc32ae30e3e779449ecd31c5201f2301319ceeee01fe` |
| `bigcodebench/eval/utils.py.source` | `bigcodebench/eval/utils.py` | `6d34de9971902dcf499ff5fb649e4abff3e7cd95` | `9061f74fe937c4eb7a1b2bc423f7acab547ae01804d5e25933e2aa8a3cc2d685` |
| `bigcodebench/eval/_special_oracle.py.source` | `bigcodebench/eval/_special_oracle.py` | `4311cc9b30e5f0d4abd742e0c632daf535be69e7` | `0cf930163987d30f455547aec6cbc500a154bc58a2eb109aa247ef4e0962448b` |

The two upstream modules use CRLF line endings and must retain them. Do not add NVIDIA headers, reformat, normalize line endings or otherwise alter these four source artifacts. Authored runner/protocol code does not live here.
