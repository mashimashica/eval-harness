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

## Bubblewrap primary source

Official repository: [containers/bubblewrap](https://github.com/containers/bubblewrap).

- Release [`v0.12.0`](https://github.com/containers/bubblewrap/releases/tag/v0.12.0) was published 2026-08-26.
- Annotated tag object `014a04330642e5c870418beb621532cb896e0002` is signature-verified by GitHub and points to commit [`2a76602a8c71f36c1527cf9fc3417d9149822e0c`](https://github.com/containers/bubblewrap/commit/2a76602a8c71f36c1527cf9fc3417d9149822e0c).
- Official source asset `bubblewrap-0.12.0.tar.xz` is 126,452 bytes with release digest `sha256:9760d007363e3abba7c747489910f9f82d9fca53ba3bd3282e396fa3c97a3314`.
- The release removes setuid support and requires unprivileged user namespaces. It fixes [`GHSA-pxhw-h44j-8pfx`](https://github.com/containers/bubblewrap/security/advisories/GHSA-pxhw-h44j-8pfx), where absolute symlink handling during setup could escape the sandbox. This is why Ubuntu's older 0.9 package is not an acceptable version substitute.
- The pinned [`README.md`](https://github.com/containers/bubblewrap/blob/v0.12.0/README.md) says bubblewrap constructs an empty mount-namespace root, uses user namespaces for unprivileged operation, always creates a mount namespace, can make mounts read-only/nodev, and can add PID/network/IPC/UTS namespaces. It also says security depends entirely on caller arguments and `--new-session` is needed against TIOCSTI when no seccomp filter supplies that protection.
- The pinned [`bwrap.xml`](https://github.com/containers/bubblewrap/blob/v0.12.0/bwrap.xml) defines explicit mandatory namespace flags, `--disable-userns`, `--clearenv`, `--size`/`--tmpfs`, `--ro-bind`, `--proc`, `--dev`, `--new-session`, and `--die-with-parent`. It states `--unshare-all` uses `--unshare-user-try` and `--unshare-cgroup-try`; therefore it is unsuitable for a fail-closed proof. The new `--not-a-security-boundary` flag deliberately makes some setup failures nonfatal and must be forbidden.

Bubblewrap is a mechanism, not a complete policy. The proposed contract supplies the mount/env/namespace/resource/process arguments and verifies their effects in a real probe.

## CI platform evidence and observed local limitation

The repository CI currently uses `ubuntu-latest`, Python `3.13.14`, and uv `0.11.29`; the boundary needs a dedicated fixed `ubuntu-24.04` job because the sandbox/BigCodeBench Python 3.10 environment is distinct from the harness environment.

GitHub's official [`Ubuntu2404-Readme.md`](https://github.com/actions/runner-images/blob/bac22751eb7d886e12c6063685275299469e9e5b/images/ubuntu/Ubuntu2404-Readme.md) at runner-images commit `bac22751eb7d886e12c6063685275299469e9e5b` reported image `20260907.300.1`, Ubuntu 24.04.5, kernel 6.17.0-1022-azure, compilers/Meson/Ninja, and cached Python 3.10.21. Bubblewrap 0.12.0 is not listed as preinstalled. The job must build the verified release and must not accidentally select an older distro binary.

The current development container has Ubuntu 24.04, bubblewrap 0.9.0, and an outer policy that rejects the required namespace setup. That environment is intentionally classified unsupported. It is evidence that version printing or venv import is inadequate; it is not evidence that GitHub-hosted CI will pass. CI must demonstrate the actual boundary without a skip.

## Threat model and limits

Protected assets are host credentials/environment, repository and run files not explicitly mounted, host network and IPC, other host processes, and resource availability. The adversary controls candidate source and can import installed packages, use `ctypes`, fork/exec, scan `/proc`, write raw file descriptors, allocate resources, and deliberately crash/hang.

The boundary aims to contain host effects and bound denial of service. It does not prove that upstream BigCodeBench is resistant to metric gaming from Python introspection or test manipulation; that is an upstream metric-semantic limitation. It also does not claim that dependency-download steps are network-free. Downloads occur only in reviewed setup; candidate grading is offline inside an unshared network namespace.

`RLIMIT_NPROC` is counted per real UID and is not a perfect per-sandbox process quota when CI runs concurrent graders. PID namespaces hide processes but do not themselves impose a count. The implementation must choose concurrency/headroom deliberately, test cleanup, and record this residual limitation. A cgroup fallback is out of scope because the design intentionally supports one rootless runtime mechanism.

## Unvalidated items at this checkpoint

- The hash-locked, solver-valid Python 3.10.21 dependency set is being produced elsewhere and has not been reviewed in this design checkpoint.
- The minimal runtime mount list must be exercised against that completed lock; imports do not justify mounting home/repository trees.
- Upstream compatibility with forced multiprocessing `spawn` and candidate FD-level output redirection needs a real test.
- GitHub-hosted `ubuntu-24.04` has not yet run the exact mandatory namespace/probe command. PR04 acceptance requires that green execution.
- Concrete resource numbers must be reconciled with upstream time-limit semantics and CI concurrency before Luna codes them.

## Search/retrieval note

Browser search was attempted because these are niche and current facts, but returned no usable results and direct browser opens were disabled. All factual external evidence above was then retrieved from the official GitHub repositories and immutable tag/commit/API objects; no third-party security or version claims are used.
