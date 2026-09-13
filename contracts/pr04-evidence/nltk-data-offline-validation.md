<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# NLTK data offline preparation evidence

**State:** content/reproducibility validation passed; license acceptance is unresolved for three required packages; hosted sandbox validation has not run.

The source is official `nltk/nltk_data` gh-pages commit `550b6625bcef1f2abff2ff770a5a0d272c9c6b2a`. The exact full source index is 78,939 bytes, Git blob `65370112729759a945832b368c6411da7a657c87`, SHA-256 `97dce5e72320cd9850b7c20130196006710c18f9c03134c822a37da330198bf6`.

| Package | Git blob | ZIP bytes | ZIP SHA-256 | Expanded bytes | Files | ZIP-content inventory SHA-256 | License state in official inventory |
|---|---|---:|---|---:|---:|---|---|
| `averaged_perceptron_tagger` | `d5bfb6852aa5d288c8f33b3f0ef0fde343afa405` | 2,526,731 | `e1f13cf2532daadfd6f3bc481a49859f0b8ea6432ccdcd83e6a49a5f19008de9` | 6,138,625 | 1 | `271291c4bf1fbd30e8d2481343b38df54a5aab9808b3156e6ccb807fafd518df` | MIT |
| `averaged_perceptron_tagger_eng` | `b792e19546a5711218a05f4029ef17c8d62cd839` | 1,539,115 | `6025f530624335c67d6547d44757b357b4e79bae030a0383e9887a92c1718f0b` | 5,703,817 | 3 | `7baf7610f89708e1bc36cf5835f64c34af5684e789eadd32b1c9d65625c0fccd` | MIT |
| `punkt` | `da7ffbd1e6fd6cc5c2f6879c2d4da23c7691944c` | 13,905,355 | `51c3078994aeaf650bfc8e028be4fb42b4a0d177d41c012b6a983979653660ec` | 37,245,719 | 41 | `d4bbe3e1dfa8ca4f6ccf9b499bef17fb405600865bc8ccce409382890a28c394` | **unclarified** |
| `punkt_tab` | `5e5ff6137d5ee6025e400d1c3a7b21914c48b635` | 4,319,076 | `e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106` | 10,885,330 | 77 | `e63284e77c3753edfbeffb6228e6de8625f1545e311f4176e0cee4d65d295147` | **unclarified** |
| `stopwords` | `56d35b5d204d64480f71edc0f5f82aebce6730b6` | 37,733 | `48c0e52d8b52546e827f53761fb30300c0ab94f70660d28bd65ba0a86270946b` | 89,446 | 34 | `8ba432c914480d4015d69d63a3ce90126979eeee1afd9eee05fa3697df7d2b82` | **unclarified** |
| `vader_lexicon` | `c8d4b96e5f0648ee28fb2829276da0f85a1165f1` | 90,486 | `8adba4294eef3964d820bf655e37e61bdc3a341994356af59b74fb3b4a36ce5c` | 434,147 | 1 | `db7110719f1b9eb4ce16fa5e9d158fbf6c0a492277b5d34225a84ca4c8643549` | MIT; ZIP intentionally remains compressed |
| `words` | `d1a5a834a19fc3bf77f5dd663e1779fe8f7a2c50` | 757,777 | `54ed02917d6771dcc3e8141218960d020947f7f2ccfd9ac9b320979349746015` | 2,498,552 | 3 | `0918af335f47dc6bdfd62d06febef63ab2bb627b3322d22257f8acd27bdc0dfe` | public domain |

Every asset was retrieved from its commit-addressed official raw URL. Its API size, Git blob (recomputed as Git `blob <size>\0<bytes>` SHA-1), index size/SHA-256 and observed bytes all agree. ZIP validation rejected encryption, absolute paths, `..`, backslashes, case-folded duplicate names, entries outside the package top-level directory, links and special files. Expanded-size totals match the official index.

`nltk-data-packages-550b6625-manifest.json` preserves these values and the canonical inventory algorithm. The prepared read-only tree contains the seven ZIPs, six expanded directories and the reduced index: 167 regular files, 85,741,209 bytes, content-inventory SHA-256 `5a30cfb5c9d2a0353a987535b261386244abe66ac898185c514c913ac518514a`. The reduced seven-package index is 3,447 bytes, SHA-256 `27b1257a84cfec723c024c6762ed801ceb6984437d5438d4c7bed8bc6b52aafc`, and points only to in-sandbox `file:///opt/bigcodebench/nltk_data/...` ZIPs.

## Downloader behavior and validation

`NLTK_DATA` alone does not make `nltk.download()` offline. In NLTK 3.10.3, the module-global `Downloader` retains a hard-coded network index URL, and its default destination skips the read-only prepared directory. The implementation therefore installs a measured `sitecustomize.py` copy from `eval_harness/bigcodebench_sitecustomize.py`. Under the literal `bigcodebench-bwrap-v1` environment it sets `nltk.data.path` to the read-only tree and mutates the pinned module-global downloader's URL to its local `index.xml` and destination to that same tree before candidate imports. Preflight starts a fresh isolated interpreter and verifies those exact effective values.

With parent proxy variables removed, exact pristine NLTK 3.10.3 reported all seven packages `installed`; all seven `nltk.download(..., quiet=True, raise_on_error=True)` calls took the local already-installed fast path and returned `True`. Functional checks passed for English stopwords/words, sentence tokenization, POS tagging and VADER sentiment. The hosted job must repeat this through forced multiprocessing `spawn` and the real network namespace.

## License blocker

Official `LICENSE-OVERVIEW.md` says the repository-level Apache-2.0 license does not govern individual data packages and warns against assuming redistribution permission when a package license is missing. Official `DATASET-LICENSES.md` places `punkt`, `punkt_tab`, and `stopwords` in its unclarified/unknown group. Exact source identities are:

| File | Git blob | Bytes | SHA-256 |
|---|---|---:|---|
| `LICENSE` | `cdec0628108cd794df64b265a9ab0544b4833557` | 11,320 | `8d030ab5afc58f0b6a1f4207c12fd9553de6da2294efede65a0c58f9a6495fcc` |
| `LICENSE-OVERVIEW.md` | `30d163d3aef25c99f6e505bffec77a0f5ea4094b` | 3,365 | `8115f9aadc98ec981082621265a88a05c8b132c82c458b32d52e541129d61ecf` |
| `DATASET-LICENSES.md` | `978a24ba488cd8fa1d02dc4014106ba63301b670` | 9,910 | `4285f61badbbdc755811f1f5a61e3dd341a516ff2343490819b019fd8f674ff9` |

PR04 must not vendor those three package byte payloads into this repository or a redistributed grader artifact, or claim the full data tree is Apache-compatible, until repository license review resolves this issue or an equivalently validated, clearly licensed native-parity source is selected. Fixed-commit remote retrieval into an ephemeral CI/runtime-preparation directory may continue for read-only provenance and benign compatibility testing; that activity does not itself establish redistribution permission. This packaging decision is separate from the mandatory NLTK code-audit blocker and from the successful technical preparation test.

Primary sources:

- <https://github.com/nltk/nltk_data/tree/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a>
- <https://github.com/nltk/nltk_data/blob/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/LICENSE-OVERVIEW.md>
- <https://github.com/nltk/nltk_data/blob/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/DATASET-LICENSES.md>
