<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR04 BigCodeBench grader boundary implementation contract

**State:** DRAFT — implementation and hosted-CI proof remain unvalidated. The NLTK audit gate is unresolved.

**Review order:** Sol design/security review, then Luna implementation.

## Goal and exact base

Implement a fail-closed host-security boundary for BigCodeBench native grading. Candidate Python is hostile. A virtual environment is dependency separation only and must never be described, tested, or accepted as a sandbox.

- Implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75` (tree `354943ebbb8ea81a30523bfdc12baf26771853b5`).
- Control/checkpoint base: `8518f25d107d9043df449a9198fbb41b00ba1c22`.
- Benchmark dataset revision remains `v0.1.4` and is recorded separately from the grader package.
- Native metric source is exactly BigCodeBench `v0.2.5`, tag commit `9bd90fedee89d7dc3676838c75d9642cb0cd0702`.
- One supported sandbox: bubblewrap `v0.12.0`, tag commit `2a76602a8c71f36c1527cf9fc3417d9149822e0c`, source asset SHA-256 `9760d007363e3abba7c747489910f9f82d9fca53ba3bd3282e396fa3c97a3314`.
- Grader interpreter is exactly CPython `3.11.16` on Linux x86-64. This is an explicit policy revision, never a fallback.
- Supported validation platform is a fixed `ubuntu-24.04` GitHub-hosted job. Every grader launch runs as the ordinary runner user. Unsupported platforms or blocked namespaces fail preflight; there is no fallback.

## Allowed implementation paths

Luna may change only these paths. A newly discovered need outside the list returns to Sol for a contract amendment.

- `eval_harness/evaluators/bigcodebench.py`
- `eval_harness/grader_sandbox.py` (new, BigCodeBench-specific bubblewrap policy, bounded host I/O and process supervisor)
- `eval_harness/bigcodebench_runner.py` (new, measured and typed inner runner/authenticated protocol)
- `resources_servers/bigcodebench/bcb_runner.py` (delete the executable legacy shim; no direct runner route remains)
- `resources_servers/bigcodebench/app.py`
- `resources_servers/bigcodebench/setup_bcb_venv.py`
- `resources_servers/bigcodebench/requirements-grader.in` (new)
- `resources_servers/bigcodebench/requirements-grader.lock` (new, full hashes)
- `resources_servers/bigcodebench/grader-manifest.json` (new)
- `resources_servers/bigcodebench/nltk-data-manifest.json` and pinned local `index.xml` (new)
- `resources_servers/bigcodebench/vendor/bigcodebench/{LICENSE,eval/__init__.py,eval/utils.py,eval/_special_oracle.py}` (new, exact upstream bytes)
- `resources_servers/bigcodebench/sandbox_etc/{hosts,nsswitch.conf,resolv.conf,passwd,group}` (new, fixed non-secret inputs)
- `resources_servers/bigcodebench/configs/bigcodebench.yaml`
- `resources_servers/bigcodebench/README.md`
- `eval_harness/benchmarks/registry.yaml` only for truthful grader/sandbox provenance wording
- `tests/harness/test_bigcodebench_benchmark.py`
- `tests/harness/test_bigcodebench_grader_boundary.py` (new real Linux integration tests)
- `tests/harness/test_bigcodebench_runner.py` (new protocol/native-runner unit and spawn tests)
- `resources_servers/bigcodebench/tests/test_app.py`
- `scripts/ci/install_bubblewrap.sh` (new pinned source installer)
- `scripts/ci/install_bigcodebench_grader.py` (new safe CPython/data/environment preparer)
- `scripts/ci/requirements-bwrap-build.in` and `scripts/ci/requirements-bwrap-build.lock` (new)
- `.github/workflows/eval-harness-ci.yml` only to provision and execute the reviewed boundary test job

Do not edit central migration state, unrelated evaluators/executors, coverage/audit thresholds, generated fixtures, or model/provider paths.

## Required interfaces

`eval_harness/grader_sandbox.py` owns one immutable policy and exposes the following typed boundary. Names may change only with Sol approval; behavior may not.

```python
class NativeStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    TIMEOUT = "timeout"

class LimitKind(StrEnum):
    WALL = "wall"
    CPU = "cpu"
    MEMORY = "memory"
    PROCESSES = "processes"
    FILE_SIZE = "file_size"
    OPEN_FILES = "open_files"
    TMP = "tmp"

@dataclass(frozen=True)
class GraderSandboxLimits:
    startup_seconds: float = 20.0
    candidate_wall_seconds: float = 250.0
    teardown_seconds: float = 5.0
    cpu_soft_seconds: int = 245
    cpu_hard_seconds: int = 250
    address_space_bytes: int = 8 * 1024**3
    data_bytes: int = 6 * 1024**3
    aggregate_rss_bytes: int = 6 * 1024**3
    stack_bytes: int = 10 * 1024**2
    file_bytes: int = 64 * 1024**2
    open_files: int = 256
    process_headroom: int = 32
    tmp_bytes: int = 512 * 1024**2
    shm_bytes: int = 64 * 1024**2
    stdin_bytes: int = 8 * 1024**2
    protocol_bytes: int = 16 * 1024
    diagnostic_bytes: int = 32 * 1024

@dataclass(frozen=True, slots=True)
class BigCodeBenchGradeRequest:
    schema_version: int
    code: str
    test_code: str
    entry_point: str
    task_id: str

@dataclass(frozen=True, slots=True)
class GraderSandboxSpec:
    resource_dir: Path
    bwrap_path: Path
    grader_python: Path
    forbidden_roots: tuple[Path, ...] = ()

@dataclass(frozen=True, slots=True)
class GraderSandboxPreflight:
    ok: bool
    sandbox_version: str | None
    policy_revision: str
    attestation_sha256: str | None
    details: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class GraderNativeResult:
    native_status: NativeStatus | None
    limit_kind: LimitKind | None = None

class GraderInfrastructureError(RuntimeError):
    """Stable, secret-free grader boundary failure."""

def preflight_bigcodebench_sandbox(spec: GraderSandboxSpec) -> GraderSandboxPreflight: ...

def run_bigcodebench_sandbox(
    request: BigCodeBenchGradeRequest,
    *,
    spec: GraderSandboxSpec,
    preflight: GraderSandboxPreflight,
) -> GraderNativeResult: ...
```

The evaluator and resource server must call the same implementation. `run_bigcodebench_sandbox` rejects a false, stale, or spec-mismatched preflight attestation and rechecks the manifest/critical file identities immediately before launch. No direct `python bcb_runner.py` path may remain. `app.py` must not preserve an unsafe legacy route; its async endpoint calls the synchronous supervisor with `asyncio.to_thread` under a process-wide semaphore of size one.

The trusted supervisor and runner live under `eval_harness/`, so strict typing and the existing `source=eval_harness` coverage gate measure their parser, HMAC, state machine, bounded-I/O, error-map and worker logic. `bcb_runner.py` in the resources server is deleted. The inner file is mounted as `/opt/bigcodebench/bigcodebench_runner.py` and executed with `python -I -B`; it may import only the standard library and the pinned vendored metric. Security integration tests still run the real sandbox rather than weakening isolation for coverage.

Production limits are constants, not request fields. Public input has exactly `schema_version=1`, `code`, `test_code`, `entry_point`, and `task_id`. Limit the encoded object to 8 MiB, `code` to 2 MiB, `test_code` to 6 MiB, and each identifier to 256 UTF-8 bytes. Reject duplicate/unknown keys, invalid UTF-8, identifier NULs, non-string fields, and trailing input before importing the grader or spawning candidate code.

## Exact native metric source selection

Vendor only the three files imported by `untrusted_check`, byte-for-byte from BigCodeBench `v0.2.5`, plus its MIT license. Do not install the BigCodeBench wheel and its unrelated vLLM/provider/generation stack.

| Upstream path | Git blob | Content SHA-256 |
|---|---|---|
| `bigcodebench/eval/__init__.py` | `3596f53ddbdf92455805890aba9d75e4e10a5e6f` | `d5fd553559ac1b76659ebc32ae30e3e779449ecd31c5201f2301319ceeee01fe` |
| `bigcodebench/eval/utils.py` | `6d34de9971902dcf499ff5fb649e4abff3e7cd95` | `9061f74fe937c4eb7a1b2bc423f7acab547ae01804d5e25933e2aa8a3cc2d685` |
| `bigcodebench/eval/_special_oracle.py` | `4311cc9b30e5f0d4abd742e0c632daf535be69e7` | `0cf930163987d30f455547aec6cbc500a154bc58a2eb109aa247ef4e0962448b` |
| `LICENSE` | `27115b77b9e6c6c80f9b6987d8734fc8d532093c` | `a858540b8dfd0c74db6953edaae85bde0b671643a7e2fb04a065f4dfd25fc28c` |

Preflight hashes every file. A source-isolation test makes importing any non-vendored BigCodeBench module fail, while known pass/fail/timeout fixtures prove native parity.

## Sandbox policy

Every launch is built by one command builder and uses mandatory bubblewrap flags. It must contain explicit `--unshare-user`, `--unshare-ipc`, `--unshare-pid`, `--unshare-net`, `--unshare-uts`, `--disable-userns`, `--cap-drop ALL`, `--clearenv`, `--new-session`, and `--die-with-parent`. It must not contain `--unshare-all`, any `*-try` option, `--share-net`, `--not-a-security-boundary`, a writable host bind, or a D-Bus/agent/container socket.

Bubblewrap starts from its empty mount-namespace root. Bind read-only only:

- the grader virtual environment at its resolved absolute host path;
- the virtual environment's resolved base-interpreter prefix at the same absolute path;
- measured `eval_harness/bigcodebench_runner.py` at `/opt/bigcodebench/bigcodebench_runner.py`;
- the exact vendored metric source at `/opt/bigcodebench/vendor`;
- the hash-verified NLTK asset tree plus local index at `/opt/bigcodebench/nltk_data`;
- `/usr`, existing `/lib` and `/lib64`, and only `/etc/ld.so.cache`, `/etc/ssl/certs`, `/etc/fonts`, and `/etc/localtime` when present;
- committed synthetic `/etc/{hosts,nsswitch.conf,resolv.conf,passwd,group}` files, with no host identity or resolver data.

Do not mount the repository root, executor workspace, run directory, home directory, host `/tmp`, `/run`, `/sys`, arbitrary `/etc`, or source/download caches. Add a new `/proc`, a minimal `/dev`, a 512 MiB private tmpfs at `/tmp`, a 64 MiB private tmpfs at `/dev/shm`, and empty `/tmp/{home,work}`. Work in `/tmp/work`.

Use `--clearenv` and only literal values: `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `TZ=UTC`, `HOME=/tmp/home`, `TMPDIR=/tmp`, venv-only `PATH`, `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=0`, `PYTHONSAFEPATH=1`, `MPLBACKEND=Agg`, `NLTK_DATA=/opt/bigcodebench/nltk_data`, cache/config paths below `/tmp`, `CUDA_VISIBLE_DEVICES=`, and each common numerical-library thread count set to `1`. Do not pass host credentials, proxy variables, cloud variables, `SSH_AUTH_SOCK`, tool tokens, `PYTHONPATH`, or `BIGCODEBENCH_TIMEOUT_PER_TASK`.

A trusted outer launcher sets `RLIMIT_CPU=(245,250)`, `AS=8 GiB`, `DATA=6 GiB`, `STACK=10 MiB`, `FSIZE=64 MiB`, `NOFILE=256`, `CORE=0`, and `NPROC=(baseline real-UID process count + 32)` before `execve`. Only one grader sandbox may run per real UID, enforced by one cross-process host lock shared by evaluator and resource server; resource-server concurrency is one. Poll descendants every 25 ms and kill at 32 descendants or 6 GiB summed RSS. Bound startup to 20 seconds, candidate phase to 250 seconds, teardown to 5 seconds, input to 8 MiB, authenticated protocol to 16 KiB and diagnostics to 32 KiB. Start a session; on a limit kill the session and bwrap process, then require PID-namespace-init death to remove escaped descendants. Unbounded `capture_output`/`communicate` is forbidden.

`RLIMIT_NPROC` and RSS polling are not cgroups: the former is real-UID scoped and the latter has a sampling race. The single-launch lock, measured baseline/headroom, hard per-process limits, PID namespace and cleanup tests are the explicit rootless composition. If hosted CI cannot demonstrate the process/memory fixtures without host impact, implementation fails; no fallback or stronger aggregate claim is allowed.

The path to bubblewrap is absolute and supplied by trusted configuration. Preflight requires exact version `0.12.0`, refuses a setuid/setgid or mutable executable, and runs the same policy builder used for grading. Runtime never downloads or installs anything.

## Fail-closed preflight

Preflight runs before benchmark preparation or any executor/model request. It performs all of these checks and returns `ok=False` on the first failure with a stable, secret-free reason:

1. Linux x86-64, absolute bubblewrap path, exact version, acceptable ownership/mode, locked grader manifest, exact Python `3.11.16`, exact vendored hashes, `uv pip check`, and runner/venv/base/vendor/data separation from run and executor roots.
2. A real sandbox probe through the production command builder. Compare parent/child namespace inode IDs and require different mount, user, PID, network, IPC, and UTS namespaces; require `NoNewPrivs: 1`, zero effective capabilities, nested user namespaces disabled, a private `/proc`, and active configured rlimits.
3. Put a random dummy secret in the parent environment and require it absent in the child. Put random read/write sentinels outside all mounts and require both open attempts to fail. Require writes to the runner, venv, `/usr`, and base prefix to fail while a bounded `/tmp` write succeeds.
4. Start parent listeners on loopback and a non-loopback interface when available; require child IPv4/IPv6 connection attempts to fail and require a different network namespace. This is deterministic and does not depend on an external Internet host.
5. Exercise timeout, process-count, file-size, memory, descriptor, tmpfs, and stdout/stderr limits with tiny probe values, then verify complete descendant cleanup.

A local container that blocks user/network namespaces is unsupported and must fail this preflight. CI acceptance requires the same probes to pass and the hostile fixtures below to run; tests may not skip or mock the boundary on the supported job.

## Grader protocol and native outcomes

The upstream checker is a metric implementation, not a security boundary. Candidate children share the sandbox UID/PID namespace, so `FD_CLOEXEC` alone is insufficient. The result channel is authenticated and must satisfy this exact sequence:

1. Outer host creates a fresh 32-byte key with `os.getrandom()`. Input is magic `BCBI`, version byte `1`, four-byte big-endian payload length, key, then JSON. The key never appears in argv, environment, files, logs, or persisted results.
2. At the first instruction in `main`, before reading the key, runner calls `prctl(PR_SET_DUMPABLE, 0)` through a fixed ctypes signature and verifies `PR_GET_DUMPABLE == 0`; failure is infrastructure.
3. After exact bounded read plus EOF check, duplicate original stdout to one non-inheritable result FD and replace FDs 0, 1 and 2 with `/dev/null` before importing the metric, creating a Manager, or spawning candidate code.
4. Call `multiprocessing.set_start_method("spawn", force=True)` and assert it. Keep the HMAC key local to runner `main`; never store it in a module global or multiprocessing argument.
5. Emit authenticated `START` immediately before the native child starts and authenticated `RESULT` only after validating the native return. Each frame is `BCBO`, version `1`, sequence byte, type byte, four-byte body length, HMAC-SHA256 over header+canonical body, then the body. Result JSON contains only `schema_version` and `native_status`; no traceback/test text crosses.
6. Host requires exactly `START(0)` then `RESULT(1)`, uses `compare_digest`, enforces 16 KiB total and rejects missing/reordered/duplicate/trailing bytes. Authenticated runner error before START is infrastructure. A supervisor limit becomes a candidate resource outcome only after valid START and direct observation that this supervisor enforced that limit; every unattributed signal/exit is infrastructure.

The hostile fixture must show denial for `/proc/<runner-pid>/{fd,environ,mem}` and `process_vm_readv`, scan plausible raw FDs, spawn a grandchild, write forged frames, and kill the runner. Killing/corrupting the runner may deny a result but cannot create authenticated completion. HMAC protects channel authenticity; it does not make the Python Manager/status or native metric resistant to semantic gaming.

The generic runner already persists and re-raises evaluator exceptions. Use that behavior for grader infrastructure failures; do not add `EvaluationStatus.FAILED` in this PR.

| Event | Evaluation status | Metric | Stable outcome | Continue run |
|---|---|---:|---|---|
| upstream `pass` | `completed` | `pass_rate=1.0` | `native_status=passed` | yes |
| upstream assertion/test `fail` | `completed` | `pass_rate=0.0` | `native_status=failed_tests` | yes |
| empty executor text | `completed` | `pass_rate=0.0` | `native_status=empty_output`, grader not invoked | yes |
| extraction yields no code | `completed` | `pass_rate=0.0` | `native_status=no_code_block`, grader not invoked | yes |
| upstream candidate timeout | `completed` | `pass_rate=0.0` | `native_status=candidate_timeout` | yes |
| sandbox-enforced candidate limit | `completed` | `pass_rate=0.0` | `native_status=candidate_resource_limit`, include only the stable limit kind | yes |
| executor run-impact failure | runner records evaluation `skipped` with no metric before evaluator | none | existing executor failure record | no |
| sandbox unavailable/launch fault, dependency mismatch, runner crash not attributable to a configured candidate limit, malformed/oversized protocol, unknown native status | evaluator raises `GraderInfrastructureError` | none | generic runner persists `evaluation.status=failed` and exception type | no |

Never convert infrastructure failure to reward zero. Never include failed/skipped infrastructure rows in pass-rate aggregation.

## Dependency and provenance lock

Replace the mutable installer and `.installed` sentinel. Commit a solver-valid `requirements-grader.lock` with exact versions and SHA-256 hashes for every installed distribution. Generate and sync it with uv `0.11.29` for CPython `3.11.16` using `--require-hashes`; runtime never resolves/downloads. The current candidate has 160 distributions and covers every upstream task dependency plus the vendored metric's NumPy dependency, but it is **not acceptable** because strict audit still has one NLTK finding. Vendoring the exact three metric modules is source selection, not permission to omit an installed or task-required package from lock/audit.

Pin NLTK data separately to official `nltk/nltk_data` gh-pages commit `550b6625bcef1f2abff2ff770a5a0d272c9c6b2a`, index SHA-256 `97dce5e72320cd9850b7c20130196006710c18f9c03134c822a37da330198bf6`. Prepare exactly `stopwords`, `punkt`, `punkt_tab`, `averaged_perceptron_tagger`, `averaged_perceptron_tagger_eng`, `vader_lexicon`, and `words` from manifest SHA-256 values and reject extra/missing files. The local index makes dataset `nltk.download()` calls deterministic/offline; grade-time data is read-only.

The installation manifest is JSON containing Python/build provenance, platform, lock SHA-256, installed-distribution inventory hash, all vendored blob/content hashes, NLTK data commit/index/package hashes, bubblewrap version/tag/source SHA-256, and policy revision `bigcodebench-bwrap-v1`. Preflight recalculates and compares it. Dataset revision is separate.

### Unresolved NLTK acceptance gate

Strict `pip-audit` 2.10.1 reports exactly NLTK 3.10.3 `PYSEC-2026-3740`, aliases `CVE-2026-81726` and `GHSA-8mgp-746c-j5xp`, with no fix. The preserved minimal backport and deterministic wheel are **rejected evidence**, not a remediation option: independent controls reproduce a benign `load_from_json` `NameError` and outside-victim truncation through an allowed-root hardlink before `PermissionError`.

Do not install that wheel, ignore the CVE, spoof a version, rename the package, or claim a local backport satisfies the standard gate. Gate A remains red until an official fixed NLTK release produces a clean regenerated lock. Any exception or replacement audit policy requires the user’s explicit plan amendment; an internal reviewer cannot weaken this gate. Research on a replacement backport, if retained, must port the official companion behavior and test validate-before-truncate, hardlinks for every write sink, FIFOs/devices/sockets without blocking, default paths, direct path-shaped inputs, and benign in-root roundtrips; it still cannot turn standard audit green.

### Exact CPython and bubblewrap setup path

`scripts/ci/install_bigcodebench_grader.py` downloads the immutable `python-build-standalone` release `20260901` asset ID `539915682` from its literal URL, requires size `30778779` and SHA-256 `64427febea27864d136db46c8efe968eb6fa5ca2813ce1dca4bb95aec31cb2e4`, rejects unsafe tar members, and extracts the single `python/` root into a new `$RUNNER_TEMP/pr04-cpython-3.11.16+20260901`. It verifies CPython `3.11.16`, `x86_64`, SOABI `cpython-311-x86_64-linux-gnu`, executable SHA-256 `1e761eb19d6f2594ab8dc64bd99ad4e1753589f3bf1ec199e4eef3aaa21e3930`, and license SHA-256 `3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf`. It creates a new grader venv with the absolute interpreter using repository uv `0.11.29`, `--no-project`, `--no-python-downloads`, and copy link mode, then syncs the accepted grader lock with `--require-hashes --no-python-downloads --strict`. It never calls uv's Python installer.

`scripts/ci/install_bubblewrap.sh` requires SHA-256 `9760d007363e3abba7c747489910f9f82d9fca53ba3bd3282e396fa3c97a3314` before extraction. Its Python build tools are exactly Meson `1.9.1` and Ninja `1.13.0` from `scripts/ci/requirements-bwrap-build.lock`, installed by uv `0.11.29` with hashes. On Ubuntu 24.04 it requires the image compiler, `pkg-config` and `libcap-dev`, records their `dpkg-query` versions, configures with `-Dselinux=disabled -Dman=disabled -Dtests=true -Dbash_completion=disabled -Dzsh_completion=disabled`, compiles, runs upstream tests, and installs under a new `$RUNNER_TEMP/pr04-bwrap-0.12.0`. It verifies `bwrap --version`, ELF architecture, absence of setuid/setgid bits and records the built binary SHA-256. The CI job exports only that absolute binary path.

The dedicated `ubuntu-24.04` boundary job uses these paths and then runs, in order: strict audit of the accepted grader lock and build-tool lock; grader preparation; `uv pip check`; manifest generation/readback; the real preflight test; hostile fixtures; all 1,140 canonical solutions in a disposable credential-free checkout/data root. Canonical comparison has an unsandboxed exact-source reference only inside that disposable CI environment with an empty allowlisted environment and no user/workspace mounts or credentials. It is parity evidence and never runs against user-controlled workspace data.

## Required tests and expected results

Unit tests may patch process creation only to test parsing and error mapping. Security acceptance comes from `tests/harness/test_bigcodebench_grader_boundary.py`, executed on `ubuntu-24.04` with pinned bubblewrap built from its verified source asset and the hash-locked grader environment.

The real test submits hostile candidate code through the public evaluator or the shared sandbox entry point and proves:

- dummy host env secrets and proxy/token-shaped values are absent;
- a randomized prohibited file cannot be read, created, renamed, linked, or written, including via absolute symlinks and `/proc` paths;
- the executor workspace, run directory, repository siblings, host home, and host `/tmp` sentinels are invisible;
- IPv4, IPv6, DNS and parent TCP/Unix listeners are unreachable; a candidate-created Unix socket under private `/tmp` works for native multiprocessing;
- fork/subprocess storms, memory allocation, descriptor creation, large files, private-tmp exhaustion, infinite loops, and output floods terminate within the exact bounds and leave no descendant;
- venv/runner/system mounts reject writes and private `/tmp` permits bounded writes;
- candidate raw FD writes, `/proc` reopening, `process_vm_readv`, child/grandchild inheritance and forged frames cannot produce an authenticated result;
- known pass, known wrong answer, empty output, no-code extraction, candidate timeout/resource limit, and injected grader infrastructure failure produce the exact table above;
- an intentionally unavailable sandbox fails evaluator preflight before a counting executor/model stub is called.

No security assertion may pass because bubblewrap is mocked, because a fixture only checks command text, or because the supported-platform test is skipped. Keep normal hermetic unit tests for unsupported developer hosts, but the dedicated CI job must fail rather than skip if its real probe cannot run.

Run repository Ruff, strict typing, the repository's 96% strict harness coverage gate, hash-locked dependency audit with no silent CVE allowlist, secret scan, copyright check, and the dedicated boundary job. Do not weaken or exclude gates.

## Done criteria and prohibitions

PR04 is done only after Sol reviews the implementation and CI logs show the real supported-platform probe and every hostile fixture passing. The evaluator and resource server have one launch path, preflight precedes model work, infrastructure failures stop the run without a zero score, and durable metadata identifies dataset, grader, dependency lock, sandbox, and policy independently.

No model calls, production credentials, external grader service, container daemon socket, runtime network install, fallback sandbox, setuid helper, root runtime, mocked security acceptance, force push, PR merge, or workflow-as-editing-transport.

## Remaining implementation-time proofs

- Install the 160-package lock, run all 1,140 canonical solutions under CPython 3.11.16 and the exact 8/6 GiB limits, compare to an unsandboxed exact-source reference, and investigate every delta.
- Run all 26 NLTK tasks and all seven prepared data assets against any approved backport or official fixed release.
- Demonstrate the production bubblewrap policy and same-UID spawn/FD/`/proc` protocol on hosted `ubuntu-24.04`.
- Use the now-pinned CPython 3.11.16 artifact and exact setup recipe below; verify its manifest and full locked-environment inventory on hosted CI.
