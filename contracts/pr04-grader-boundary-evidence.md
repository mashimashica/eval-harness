<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR04 BigCodeBench grader boundary evidence

**State:** DRAFT — source review checkpoint, 2026-09-13 UTC. Primary-source facts are separated from proposed policy and remaining validation.

## Local baseline reviewed

The read-only source clone was at implementation commit `d5ce0c10162cad788a17cb90f34b8f60574e7f75`. Reviewed paths:

- `eval_harness/evaluators/bigcodebench.py`
- `resources_servers/bigcodebench/{bcb_runner.py,app.py,setup_bcb_venv.py,requirements.txt,configs/bigcodebench.yaml,README.md}`
- `tests/harness/test_bigcodebench_benchmark.py`
- `tests/harness/test_boundary_failure_coverage.py`
- `tests/harness/test_benchmark_evaluator_edge_coverage.py`
- `resources_servers/bigcodebench/tests/test_app.py`
- `eval_harness/{runner.py,evaluators/base.py,executors/base.py}`
- `.github/workflows/eval-harness-ci.yml`

Current evaluator behavior is unsafe for hostile code: it starts the virtual-environment Python directly, uses the resource directory as cwd, copies `os.environ`, captures unbounded output, and calls a runner that invokes upstream `untrusted_check`. Timeout, spawn errors, runner exceptions, and malformed protocol are converted to status strings with reward `0.0`; the evaluator then emits a completed pass-rate sample. Preflight proves only that a separate venv can import the runner. Existing tests mock the venv/runner/process and therefore do not establish a host boundary.

The resource-server `app.py` is a second direct launch path and also copies the host environment. Securing only the evaluator would leave a production path unsafe.

`setup_bcb_venv.py` installs `bigcodebench>=0.2.5`, fetches `Requirements/requirements-eval.txt` from mutable `main`, installs BigCodeBench without dependencies, sequentially overrides NumPy, and trusts a touch sentinel. The repository does not determine the installed grader version or dependency graph and has no hash lock.

The generic runner already handles evaluator exceptions correctly for PR04: it writes an evaluation record with `status="failed"`, empty metrics/outcomes, a stable exception type, marks the run failed, and re-raises. A failed executor with run impact is recorded as evaluation `skipped` and aborts before calling the evaluator. A new evaluation enum member is unnecessary.

## Pinned BigCodeBench primary source

Official repository: [bigcode-project/bigcodebench](https://github.com/bigcode-project/bigcodebench).

- Tag [`v0.2.5`](https://github.com/bigcode-project/bigcodebench/tree/v0.2.5) resolves to commit [`9bd90fedee89d7dc3676838c75d9642cb0cd0702`](https://github.com/bigcode-project/bigcodebench/commit/9bd90fedee89d7dc3676838c75d9642cb0cd0702), dated 2025-03-31. The tag target is a commit, not an annotated release object.
- Inspected [`bigcodebench/eval/__init__.py`](https://github.com/bigcode-project/bigcodebench/blob/9bd90fedee89d7dc3676838c75d9642cb0cd0702/bigcodebench/eval/__init__.py), Git blob `3596f53ddbdf92455805890aba9d75e4e10a5e6f`.
- Inspected [`bigcodebench/eval/utils.py`](https://github.com/bigcode-project/bigcodebench/blob/9bd90fedee89d7dc3676838c75d9642cb0cd0702/bigcodebench/eval/utils.py), Git blob `6d34de9971902dcf499ff5fb649e4abff3e7cd95`.
- Inspected the tag's exact [`Requirements/requirements-eval.txt`](https://github.com/bigcode-project/bigcodebench/blob/9bd90fedee89d7dc3676838c75d9642cb0cd0702/Requirements/requirements-eval.txt). It contains duplicated names and mutually incompatible-era pins, including NumPy 1.21.2, SciPy 1.7.2, Numba 0.55.0, Keras/TensorFlow 2.11.0, and both `requests`/`Requests` and duplicate Statsmodels lines. The current local NumPy 1.26.4 override is not the upstream file.

Observed upstream execution behavior:

- `untrusted_check` creates multiprocessing managers/values and a child `Process`, joins it, then terminates/kills it on timeout.
- `unsafe_execute` enters a temporary directory and `safe_environment`, runs `reliability_guard`, compiles/executes candidate plus tests, and uses `unittest`.
- `reliability_guard` applies AS/DATA/STACK rlimits and disables some Python functions.
- The upstream source itself says its reliability guard is not a security sandbox and warns against blindly executing untrusted code outside one.
- The guard does not provide mount, user, PID, network, IPC, or UTS namespaces; it does not clear host environment; Python monkeypatches cannot prevent `ctypes`/syscall or inherited-file-descriptor access. Its command filter forwards most subprocess/shell commands and is not a kernel policy.
- `BIGCODEBENCH_TIMEOUT_PER_TASK` is read from the environment inside `untrusted_check`; inheriting arbitrary host environment therefore also changes grader behavior.

Conclusion: pinning and calling `untrusted_check` preserves native metric semantics, but it cannot be credited as the host-security boundary.

The accepted source-selection design vendors only the native metric's actual import closure rather than installing the wheel's unrelated generation/provider dependencies. Exact content evidence is:

| Path | Git blob | SHA-256 of content |
|---|---|---|
| `bigcodebench/eval/__init__.py` | `3596f53ddbdf92455805890aba9d75e4e10a5e6f` | `d5fd553559ac1b76659ebc32ae30e3e779449ecd31c5201f2301319ceeee01fe` |
| `bigcodebench/eval/utils.py` | `6d34de9971902dcf499ff5fb649e4abff3e7cd95` | `9061f74fe937c4eb7a1b2bc423f7acab547ae01804d5e25933e2aa8a3cc2d685` |
| `bigcodebench/eval/_special_oracle.py` | `4311cc9b30e5f0d4abd742e0c632daf535be69e7` | `0cf930163987d30f455547aec6cbc500a154bc58a2eb109aa247ef4e0962448b` |
| `LICENSE` | `27115b77b9e6c6c80f9b6987d8734fc8d532093c` | `a858540b8dfd0c74db6953edaae85bde0b671643a7e2fb04a065f4dfd25fc28c` |

`__init__.py` imports only the two listed sibling modules plus NumPy and the standard library. Source parity and import-isolation tests are required so an installed `bigcodebench` cannot shadow or widen this closure.

## Python 3.11.16 dependency candidate

The explicit CPython 3.11.16 candidate was compiled for `x86_64-unknown-linux-gnu` with the repository-pinned uv 0.11.29. It resolves 160 exact, hash-complete distributions. `uv pip sync --require-hashes --dry-run` resolves all 160 and proposes no unpinned input. Lock SHA-256 is `8d62cac6880124652638ff8716532d46d459aaf5cbe6e8c36b506a4d1e4de9bd`.

Strict aliased `pip-audit` 2.10.1 reports exactly one finding: NLTK 3.10.3, `PYSEC-2026-3740`, aliases `CVE-2026-81726` and `GHSA-8mgp-746c-j5xp`, with no fix version. Audit JSON SHA-256 is `3d18536f4070cd1eb90179203e84bf1d147c755bf44d577fddeb8de41532310a`. This candidate therefore remains rejected even though it clears every published finding observed in the Python 3.10 candidates.

uv 0.11.29 can compile and install the lock when given an existing 3.11.16 interpreter, but its embedded managed-Python catalog returns `No download found` for that version. The provisioning gap is now closed with the independently verified `python-build-standalone` artifact recorded below; production uv remains exactly 0.11.29 and uses `--no-python-downloads`.

## CPython 3.11.16 provisioning evidence

Astral's immutable `python-build-standalone` release `20260901` supplies exact asset ID `539915682`, `cpython-3.11.16+20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz`, 30,778,779 bytes, publisher digest and independently observed SHA-256 `64427febea27864d136db46c8efe968eb6fa5ca2813ce1dca4bb95aec31cb2e4`. Its release target is verified commit `4bb01f09aaf362c71e891be4a41cb6d6ddf830b3`. Exact uv source commit `4b53f66b79c59c69eef428289904300df9e4df92` independently catalogues the same URL and digest.

Fresh archive inspection found only 3,858 regular files and 1,048 contained relative symbolic links under `python/`; no path escape or special file. Extracted execution reports CPython 3.11.16, x86-64, GNU SOABI `cpython-311-x86_64-linux-gnu`. The exact release/API/source/executable/license evidence and safe-extraction requirements are preserved in `pr04-evidence/cpython-3.11.16-20260901-provenance.md`. This closes artifact selection, while full venv install/inventory and hosted-CI validation remain implementation proofs.

## NLTK advisory and rejected backport evidence

Official advisory [`GHSA-8mgp-746c-j5xp`](https://github.com/nltk/nltk/security/advisories/GHSA-8mgp-746c-j5xp) affects NLTK through 3.10.3 and lists no patched release. The named APIs are `TransitionParser.train`/`parse`, `AveragedPerceptron.save`/`load`, `PerceptronTagger.save_to_json`, and `save_maxent_params`; each bypasses `pathsec` in the published source.

The evidence directory contains a minimal patch from exact NLTK tag commit `303f6e2ba8e4548a5f54fd65d86bb5c9a949f1db`, focused regression, PyPI metadata, and deterministic-build record. The patch derives from three fixes already merged to official NLTK `develop` (`a44a7af69bca87e92d9c4a701fcbbe4512e8d450`, `2a92b71827d754ae8920261e7ed0c4bb283ab2d7`, `cbc98458b43de5f792f0382583c16df39e5c5117`), not the broad open PR 3753.

The nine-test regression passes 9/9 against patched source and fails 8/9 against pristine 3.10.3; the only pristine pass is the negative control. Two clean builds with fixed `PYTHONHASHSEED=0` and `SOURCE_DATE_EPOCH=1786571315` produced byte-identical 1,799,409-byte wheels, SHA-256 `1a2006cfdb05170246aecfe84d24ffa7d659fc67055d9ef8e297d1b5715605a0`. Those facts are retained for provenance, but the matrix was insufficient and the wheel is rejected.

Independent review at source checkpoint `9948455de7b953de63053f389a837ce580b16e7d` found that the patch leaves a call to deleted `_authorize_private_dir`, so a benign `PerceptronTagger` save/load roundtrip errors. Worse, its pathsec writer opens with `O_TRUNC` before checking link count, so rejecting an allowed-root hardlink first destroys the outside victim; the tagger-local opener omits the hardlink check. FIFO opening can block before post-open type validation, and historical tagger/maxent `/tmp` defaults fail. Exact review and repro bytes are copied into this evidence directory. The earlier narrow validation must not be treated as security proof.

Standard strict audit also cannot attest a truthful local patch: hashed direct-URL audit rejects the URL as not pinnable to a version, and installed-path audit exits 1 because the local version is absent from PyPI. The unchanged gate needs an official fixed release and regenerated clean lock. No ignore, rename, version spoof, internal exception, or installation of this rejected wheel is valid.

## Dataset and NLTK-data evidence

Official dataset commit `b74c0d0bf70d2c0bc459be537895cca163007f1a` supplies `data/v0.1.4-00000-of-00001.parquet`, SHA-256 `d9a4965821c9507ebdfb551c288656b2d5fe553234f5183044333ca8a4018267`, 2,362,110 bytes and 1,140 rows. Twenty-six rows declare NLTK. None contains the six advisory API names, but candidate code is arbitrary and can call them, so task occurrence cannot remove the dependency finding.

Nine dataset rows call `nltk.download()`. Static task review plus runtime APIs require exactly these prepared resources: `stopwords`, `punkt`, `punkt_tab`, `averaged_perceptron_tagger`, `averaged_perceptron_tagger_eng`, `vader_lexicon`, and `words`. Their official metadata is pinned to `nltk/nltk_data` gh-pages commit `550b6625bcef1f2abff2ff770a5a0d272c9c6b2a`; exact index SHA-256 is `97dce5e72320cd9850b7c20130196006710c18f9c03134c822a37da330198bf6`. The full index is preserved for package hashes/licenses. Grade-time assets must be prepared and verified before the network namespace is created, then mounted read-only with a local index.

## Bubblewrap primary source

Official repository: [containers/bubblewrap](https://github.com/containers/bubblewrap).

- Release [`v0.12.0`](https://github.com/containers/bubblewrap/releases/tag/v0.12.0) was published 2026-08-26.
- Annotated tag object `014a04330642e5c870418beb621532cb896e0002` is signature-verified by GitHub and points to commit [`2a76602a8c71f36c1527cf9fc3417d9149822e0c`](https://github.com/containers/bubblewrap/commit/2a76602a8c71f36c1527cf9fc3417d9149822e0c).
- Official source asset `bubblewrap-0.12.0.tar.xz` is 126,452 bytes with release digest `sha256:9760d007363e3abba7c747489910f9f82d9fca53ba3bd3282e396fa3c97a3314`.
- The release removes setuid support and requires unprivileged user namespaces. It fixes [`GHSA-pxhw-h44j-8pfx`](https://github.com/containers/bubblewrap/security/advisories/GHSA-pxhw-h44j-8pfx), where absolute symlink handling during setup could escape the sandbox. This is why Ubuntu's older 0.9 package is not an acceptable version substitute.
- The pinned [`README.md`](https://github.com/containers/bubblewrap/blob/v0.12.0/README.md) says bubblewrap constructs an empty mount-namespace root, uses user namespaces for unprivileged operation, always creates a mount namespace, can make mounts read-only/nodev, and can add PID/network/IPC/UTS namespaces. It also says security depends entirely on caller arguments and `--new-session` is needed against TIOCSTI when no seccomp filter supplies that protection.
- The pinned [`bwrap.xml`](https://github.com/containers/bubblewrap/blob/v0.12.0/bwrap.xml) defines explicit mandatory namespace flags, `--disable-userns`, `--clearenv`, `--size`/`--tmpfs`, `--ro-bind`, `--proc`, `--dev`, `--new-session`, and `--die-with-parent`. It states `--unshare-all` uses `--unshare-user-try` and `--unshare-cgroup-try`; therefore it is unsuitable for a fail-closed proof. The new `--not-a-security-boundary` flag deliberately makes some setup failures nonfatal and must be forbidden.

Bubblewrap is a mechanism, not a complete policy. The proposed contract supplies the mount/env/namespace/resource/process arguments and verifies their effects in a real probe. The Meson 1.9.1/Ninja 1.13.0 build-tool lock synced with uv 0.11.29 under CPython 3.13.14; `uv pip check` passed and strict aliased pip-audit 2.10.1 found zero vulnerabilities across both distributions. An exact hosted bubblewrap build remains unvalidated.

## CI platform evidence and observed local limitation

The repository CI currently uses `ubuntu-latest`, Python `3.13.14`, and uv `0.11.29`; the boundary needs a dedicated fixed `ubuntu-24.04` job because the sandbox/BigCodeBench Python 3.10 environment is distinct from the harness environment.

GitHub's official [`Ubuntu2404-Readme.md`](https://github.com/actions/runner-images/blob/bac22751eb7d886e12c6063685275299469e9e5b/images/ubuntu/Ubuntu2404-Readme.md) at runner-images commit `bac22751eb7d886e12c6063685275299469e9e5b` reported image `20260907.300.1`, Ubuntu 24.04.5, kernel 6.17.0-1022-azure, compilers/Meson/Ninja, and cached Python 3.10.21. Bubblewrap 0.12.0 is not listed as preinstalled. The job must build the verified release and must not accidentally select an older distro binary.

The current development container has Ubuntu 24.04, bubblewrap 0.9.0, and an outer policy that rejects the required namespace setup. That environment is intentionally classified unsupported. It is evidence that version printing or venv import is inadequate; it is not evidence that GitHub-hosted CI will pass. CI must demonstrate the actual boundary without a skip.

## Threat model and limits

Protected assets are host credentials/environment, repository and run files not explicitly mounted, host network and IPC, other host processes, and resource availability. The adversary controls candidate source and can import installed packages, use `ctypes`, fork/exec, scan `/proc`, write raw file descriptors, allocate resources, and deliberately crash/hang.

The boundary aims to contain host effects and bound denial of service. It does not prove that upstream BigCodeBench is resistant to metric gaming from Python introspection or test manipulation; that is an upstream metric-semantic limitation. It also does not claim that dependency-download steps are network-free. Downloads occur only in reviewed setup; candidate grading is offline inside an unshared network namespace.

`RLIMIT_NPROC` is counted per real UID and is not a perfect per-sandbox process quota when CI runs concurrent graders. PID namespaces hide processes but do not themselves impose a count. The implementation must choose concurrency/headroom deliberately, test cleanup, and record this residual limitation. A cgroup fallback is out of scope because the design intentionally supports one rootless runtime mechanism.

## Unvalidated items at this checkpoint

- The Python 3.11.16 lock is solver-valid and its dry-run/audit are preserved, but it is rejected until the NLTK gate is resolved and a full install/inventory is tested.
- The pinned CPython 3.11.16 artifact still needs exact installer, full prepared-prefix/venv inventory and hosted-CI validation; uv 0.11.29 must run with managed downloads disabled.
- The exact runtime mount list and seven NLTK assets need all-1,140 canonical-solution validation; imports do not justify mounting home/repository trees.
- Upstream compatibility with forced multiprocessing `spawn`, `PR_SET_DUMPABLE=0`, descriptor redirection and authenticated frames needs a real same-UID hostile test.
- GitHub-hosted `ubuntu-24.04` has not yet run the exact mandatory namespace/probe command. PR04 acceptance requires that green execution.
- The proposed exact limits must pass the full canonical corpus and hostile resource fixtures. `RLIMIT_NPROC`/RSS polling limitations remain explicit.

## Search/retrieval note

Browser search was attempted because these are niche and current facts, but returned no usable results and direct browser opens were disabled. All factual external evidence above was then retrieved from the official GitHub repositories and immutable tag/commit/API objects; no third-party security or version claims are used.
