<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR04 grader boundary implementation appendix

**State:** design-freeze candidate for Sol review; no implementation or hosted-CI result is claimed.

This appendix is the finite Luna handoff for the contract in `pr04-grader-boundary-contract.md`. The implementation base is `d5ce0c10162cad788a17cb90f34b8f60574e7f75`; the control base is `8518f25d107d9043df449a9198fbb41b00ba1c22`. A conflicting implementation detail returns to Sol instead of silently changing the boundary.

## Source ownership and call seam

| Concern | Owner/path | Required call or behavior |
|---|---|---|
| Evaluator mapping | `eval_harness/evaluators/bigcodebench.py` | Calls `preflight_bigcodebench_sandbox` before model/executor work and `run_bigcodebench_sandbox` for nonempty extracted code; raises infrastructure failures. |
| Host policy/supervisor | `eval_harness/grader_sandbox.py` | Owns the typed API, one bwrap command builder, attestation, secure lock, bounded selector loop, descendant sampling and stable error map. |
| Inner adapter | `eval_harness/bigcodebench_runner.py` | Owns rlimits, input parser, descriptor replacement, forced spawn, exact native call and authenticated output state machine. |
| NLTK bootstrap | `eval_harness/bigcodebench_sitecustomize.py` | Exposes `configure_bigcodebench_nltk() -> None`; copied byte-for-byte to the grader venv and runs only for literal policy `bigcodebench-bwrap-v1`. |
| Resource server | `resources_servers/bigcodebench/app.py` | Calls the same synchronous host supervisor through `asyncio.to_thread` under a process-wide semaphore of one. |
| Legacy runner | `resources_servers/bigcodebench/bcb_runner.py` | Deleted; no direct interpreter launch remains. |
| Native metric | `resources_servers/bigcodebench/vendor/bigcodebench` | Exact upstream files only; no authored protocol or worker logic. |

All supervisor, parser, HMAC, state-machine, worker and bootstrap branches remain under the existing measured `eval_harness` source. Add the authored installer, parity driver and BigCodeBench adapter files to the strict mypy invocation in `eval-harness-ci.yml`; do not use their directory location to bypass typing. The real sandbox tests run separately from coverage and cannot be mocked or skipped on the supported job.

## Exact launch order

1. Resolve and validate `GraderSandboxSpec`. Production entry points require `PRODUCTION_GRADER_LIMITS`; test-only callers may supply the smaller attested fixture limits.
2. Acquire `/tmp/nemo-gym-bigcodebench-grader-<uid>.lock` with the flags, ownership and link checks in the contract. Count the real UID's current processes and compute the NPROC hard value as that baseline plus 32.
3. Re-hash every attested identity. Create the 32-byte per-run HMAC key. Canonically encode and size-check the request before process creation.
4. Build the one bwrap argv. Its root is empty. Add each namespace/policy flag explicitly, the two size-qualified tmpfs mounts, private `/proc` and `/dev`, the exact read-only binds/symlinks, literal environment, `/tmp/work` cwd, then the absolute grader Python with `-I -B`, the measured runner and canonical non-secret limits.
5. Start only with `Popen(stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=0, close_fds=True, pass_fds=(), start_new_session=True)`. Set the three host pipe endpoints nonblocking and use one selector loop; never use `preexec_fn`, `capture_output` or unbounded `communicate`.
6. Runner sets dumpability to zero, validates/sets/reads back rlimits, reads the exact BCBI request and EOF, obtains a CLOEXEC output duplicate, and replaces FDs 0/1/2 with `/dev/null` before any native import or multiprocessing object.
7. Runner forces spawn and calls the exact vendored `untrusted_check(code, test_code, entry_point, 8192, 6144, 10)` with no `BIGCODEBENCH_TIMEOUT_PER_TASK`. Its narrow `Process.start` wrapper emits START only for exact `unsafe_execute`; manager processes do not receive the key or result FD.
8. Host accepts only the three frame sequences in the contract. It starts the candidate timer at authenticated START, samples descendants every 25 ms, and kills the exact bwrap PID on a directly observed limit. It requires all recorded descendants gone before releasing the lock.
9. Map an authenticated native/limit result to the evaluator table. Any setup, attestation, launch, trusted-process, parser or authentication failure raises `GraderInfrastructureError`; it never contributes zero to pass rate.

The fixed native limit arguments are `max_as_limit=8192`, `max_data_limit=6144`, and `max_stack_limit=10` because upstream accepts MiB. The outer and inherited byte rlimits use the exact powers-of-two values in `GraderSandboxLimits`.

## Bubblewrap command invariants

The argv includes all of these literal operations: `--unshare-user`, `--unshare-ipc`, `--unshare-pid`, `--unshare-net`, `--unshare-uts`, `--disable-userns`, `--cap-drop ALL`, `--clearenv`, `--new-session`, `--die-with-parent`, `--proc /proc`, `--dev /dev`, `--size 536870912 --tmpfs /tmp`, and `--size 67108864 --tmpfs /dev/shm`. It uses `--ro-bind` for every host path and `--symlink` for the four merged-`/usr` compatibility paths. There is no writable host bind, inherited cwd, response file, `*-try` option, `--unshare-all`, socket mount or fallback command.

The implementation test serializes the constructed argv to a normalized operation list and compares it with an expected list. That test catches omissions but is not security acceptance; the hosted job must also inspect namespace IDs, mountinfo, capability fields, rlimits and hostile effects from inside the real boundary.

## Exact provisioning inputs

The grader interpreter is the immutable official Astral asset:

```text
https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.11.16%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz
bytes 30778779
sha256 64427febea27864d136db46c8efe968eb6fa5ca2813ce1dca4bb95aec31cb2e4
python sha256 1e761eb19d6f2594ab8dc64bd99ad4e1753589f3bf1ec199e4eef3aaa21e3930
license sha256 3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf
```

The bwrap source is:

```text
https://github.com/containers/bubblewrap/releases/download/v0.12.0/bubblewrap-0.12.0.tar.xz
bytes 126452
sha256 9760d007363e3abba7c747489910f9f82d9fca53ba3bd3282e396fa3c97a3314
tag commit 2a76602a8c71f36c1527cf9fc3417d9149822e0c
```

On the fixed `ubuntu-24.04` job, provisioning verifies or installs `build-essential`, `libcap-dev` and `pkg-config`, records exact `dpkg-query` versions, and uses only Meson 1.9.1/Ninja 1.13.0 from build lock SHA-256 `32df6b18b4c96eb4146d18cd16adad24efecba5c4a5212115f5c6acea4749605`. The semantic commands are exactly:

```bash
sudo apt-get update
sudo apt-get install --yes --no-install-recommends build-essential libcap-dev pkg-config
dpkg-query --show build-essential gcc libc6-dev libcap-dev pkg-config
uv venv --python "${HARNESS_PYTHON}" --no-managed-python --no-python-downloads "${BWRAP_BUILD_VENV}"
uv pip sync --python "${BWRAP_BUILD_VENV}/bin/python" --no-managed-python \
  --no-python-downloads --require-hashes --strict \
  scripts/ci/requirements-bwrap-build.lock
"${BWRAP_BUILD_VENV}/bin/meson" setup "${BWRAP_BUILD_DIR}" "${BWRAP_SOURCE_DIR}" \
  --prefix="${BWRAP_PREFIX}" --buildtype=release \
  -Dselinux=disabled -Dman=disabled -Dtests=true \
  -Dbash_completion=disabled -Dzsh_completion=disabled
"${BWRAP_BUILD_VENV}/bin/meson" compile -C "${BWRAP_BUILD_DIR}"
"${BWRAP_BUILD_VENV}/bin/meson" test -C "${BWRAP_BUILD_DIR}" --print-errorlogs
"${BWRAP_BUILD_VENV}/bin/meson" install -C "${BWRAP_BUILD_DIR}" --no-rebuild
```

The script assigns `HARNESS_PYTHON` to the absolute locked harness CPython 3.13.14 executable, `BWRAP_BUILD_VENV=$RUNNER_TEMP/pr04-bwrap-build-venv`, `BWRAP_SOURCE_DIR=$RUNNER_TEMP/pr04-bwrap-source-0.12.0`, `BWRAP_BUILD_DIR=$RUNNER_TEMP/pr04-bwrap-build-0.12.0`, and `BWRAP_PREFIX=$RUNNER_TEMP/pr04-bwrap-0.12.0`. The grader paths are `GRADER_PYTHON_PREFIX=$RUNNER_TEMP/pr04-cpython-3.11.16+20260901` and `GRADER_VENV=$RUNNER_TEMP/pr04-bigcodebench-venv`. Each install/source/build root is newly created without following a symlink and with mode `0700`; no value comes from candidate input. Package installation may use hosted-runner sudo during this reviewed provisioning step, but bubblewrap and every grade run execute as the ordinary job user. The installed binary is mode `0755` and has no file capability/set-ID bit. The setup-generated binary hash and recorded OS build-package versions enter the canonical runtime manifest; because the hosted image toolchain can change, the contract does not invent a source-independent binary hash.

The accepted grader lock must be regenerated with repository uv 0.11.29 for the absolute CPython 3.11.16 interpreter, synced with `--require-hashes --no-managed-python --no-python-downloads --strict`, checked with `uv pip check`, and audited with pip-audit 2.10.1 `--require-hashes --disable-pip --strict --aliases`. The preserved 160-distribution candidate lock SHA-256 `8d62cac6880124652638ff8716532d46d459aaf5cbe6e8c36b506a4d1e4de9bd` is an input for comparison only and must never populate an accepted manifest.

## Hosted acceptance commands

After provisioning and manifest readback, the dedicated job executes these gates without a skip condition:

```bash
uvx --from pip-audit==2.10.1 pip-audit --require-hashes --disable-pip \
  --strict --aliases --format json \
  --requirement resources_servers/bigcodebench/requirements-grader.lock
uvx --from pip-audit==2.10.1 pip-audit --require-hashes --disable-pip \
  --strict --aliases --format json \
  --requirement scripts/ci/requirements-bwrap-build.lock
uv run --no-sync mypy --strict --explicit-package-bases --show-error-codes \
  eval_harness tests/harness scripts/ci/install_bigcodebench_grader.py \
  scripts/ci/validate_bigcodebench_grader.py \
  resources_servers/bigcodebench/app.py resources_servers/bigcodebench/setup_bcb_venv.py
uv run --no-sync pytest -vv tests/harness/test_bigcodebench_runner.py \
  tests/harness/test_bigcodebench_sitecustomize.py
uv run --no-sync pytest -vv tests/harness/test_bigcodebench_grader_boundary.py
uv run --no-sync python scripts/ci/validate_bigcodebench_grader.py --all-tasks
coverage run --rcfile=config/eval-harness-coveragerc scripts/ci/run_eval_harness_coverage.py
coverage combine --rcfile=config/eval-harness-coveragerc
coverage json --rcfile=config/eval-harness-coveragerc --pretty-print -o coverage.json
uv run --no-sync python scripts/ci/run_eval_harness_coverage.py --check-summary coverage.json
```

The boundary test records a nonzero count for every hostile category: environment secret, unmounted paths/symlinks/links, IPv4/IPv6/Unix listeners, timeout/CPU, process storm, memory, file size, descriptors, tmpfs, output, raw FD, `/proc`, `ptrace`, `process_vm_readv`, `pidfd_getfd`, child/grandchild, signal, forged protocol and cleanup. It also records known pass, wrong, empty, no-code, native timeout, directly observed limit and injected infrastructure outcomes. The all-1,140 parity command is implemented as a separate CI script using only a disposable credential-free checkout/data root and exact vendored source on both sides; it writes task IDs/status deltas and fails on any unexplained delta.

## Frozen unresolved items

1. **Mandatory acceptance blocker:** strict standard audit reports NLTK 3.10.3 `PYSEC-2026-3740` / `CVE-2026-81726` / `GHSA-8mgp-746c-j5xp` with no fixed release. The preserved backport is rejected. Only a clean official release/lock closes the current gate; changing that gate needs the user's explicit plan amendment.
2. **Distribution decision:** official metadata leaves `punkt`, `punkt_tab` and `stopwords` licenses unclarified. Their bytes are not vendored into the repository or a redistributed artifact and are never described as Apache-compatible. Fixed-commit ephemeral retrieval may be used for provenance and benign compatibility testing while repository review decides packaging.
3. **Implementation evidence:** the exact policy, FD/spawn channel, full dependency inventory and canonical parity still need the mandatory hosted `ubuntu-24.04` run. Any namespace block, skipped hostile category, unexplained parity delta or missing cleanup fails PR04; there is no fallback.

These are bounded acceptance items. They do not reopen sandbox selection, permit the rejected dependency patch, or authorize a weaker audit.
