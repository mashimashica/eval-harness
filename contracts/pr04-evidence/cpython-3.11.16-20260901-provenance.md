<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# CPython 3.11.16 grader artifact provenance

**State:** independently downloaded and inspected research input; the production grader environment and hosted-CI job remain unvalidated.

The explicit PR04 interpreter is the `python-build-standalone` GNU/Linux x86-64 `install_only_stripped` artifact in the immutable Astral release `20260901`. This resolves provisioning independently of uv's managed-Python catalog and leaves the repository tool pin at uv `0.11.29`.

| Field | Exact value |
|---|---|
| Release | `astral-sh/python-build-standalone` tag `20260901`, release ID `380696527` |
| Release target | `4bb01f09aaf362c71e891be4a41cb6d6ddf830b3` |
| Published | `2026-09-01T17:48:48Z` |
| Immutable flag | `true` |
| Asset ID | `539915682` |
| Asset name | `cpython-3.11.16+20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz` |
| Asset URL | `https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.11.16%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz` |
| Size | `30778779` bytes |
| Publisher and observed SHA-256 | `64427febea27864d136db46c8efe968eb6fa5ca2813ce1dca4bb95aec31cb2e4` |
| Extracted executable | `python/bin/python3.11`, `21740464` bytes, SHA-256 `1e761eb19d6f2594ab8dc64bd99ad4e1753589f3bf1ec199e4eef3aaa21e3930` |
| CPython license file | `python/lib/python3.11/LICENSE.txt`, `13936` bytes, SHA-256 `3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf` |

The same artifact is an exact entry in uv `0.12.11` source commit `4b53f66b79c59c69eef428289904300df9e4df92`, file `crates/uv-python/download-metadata.json`, Git blob `1c8d06ad75fbe1275de1947438cb253192129b7c`, 3,154,441 content bytes, content SHA-256 `6c10db781e3d629515709460cce7bd3b617584877709c5c01f839030f0eaef0f`. This metadata is provenance only. Production setup does not execute uv `0.12.11`.

A fresh archive inspection found 4,906 members: 3,858 regular files and 1,048 relative symbolic links. It found no absolute/member-parent paths, device nodes, FIFOs, absolute links, or links resolving outside the single top-level `python/` directory. Setup must repeat those checks before extraction, use a fresh destination, reject every other member type, and never overwrite an existing prefix.

Independent execution after extraction produced:

```json
{"base_prefix":"<fresh-prefix>/python","implementation":"CPython","machine":"x86_64","openssl":"OpenSSL 3.5.8 25 Aug 2026","prefix":"<fresh-prefix>/python","soabi":"cpython-311-x86_64-linux-gnu","version":"3.11.16"}
```

The production installer must download to a new temporary regular file, require the exact size and SHA-256 above before inspecting or extracting, extract with owner/permission restoration disabled, normalize the prepared prefix to read-only data plus executable directories/files, and generate the full canonical inventory in `grader-manifest.json`. It then invokes uv `0.11.29` with the absolute extracted interpreter and `--no-python-downloads`; no managed-Python lookup or newer uv is permitted.

Primary sources:

- <https://github.com/astral-sh/python-build-standalone/releases/tag/20260901>
- <https://github.com/astral-sh/uv/blob/4b53f66b79c59c69eef428289904300df9e4df92/crates/uv-python/download-metadata.json>
