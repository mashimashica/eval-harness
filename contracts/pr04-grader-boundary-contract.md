<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR04 BigCodeBench grader boundary implementation contract

**State:** DESIGN-FREEZE CANDIDATE — implementation and hosted-CI proof remain unvalidated. The standard NLTK audit gate is unresolved.

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
- `eval_harness/bigcodebench_sitecustomize.py` (new, measured pinned-NLTK offline bootstrap copied verbatim into the grader venv)
- `resources_servers/bigcodebench/bcb_runner.py` (delete the executable legacy shim; no direct runner route remains)
- `resources_servers/bigcodebench/app.py`
- `resources_servers/bigcodebench/setup_bcb_venv.py`
- `resources_servers/bigcodebench/requirements-grader.in` (new)
- `resources_servers/bigcodebench/requirements-grader.lock` (new, full hashes)
- `resources_servers/bigcodebench/grader-manifest.json` (new)
- `resources_servers/bigcodebench/nltk-data-manifest.json` and pinned local `index.xml` (new)
- `resources_servers/bigcodebench/vendor/bigcodebench/{LICENSE,VENDORING.md,eval/__init__.py,eval/utils.py,eval/_special_oracle.py}` (new; upstream files exact, NVIDIA-authored provenance separate)
- `resources_servers/bigcodebench/sandbox_etc/{hosts,nsswitch.conf,resolv.conf,passwd,group}` (new, fixed non-secret inputs)
- `resources_servers/bigcodebench/configs/bigcodebench.yaml`
- `resources_servers/bigcodebench/README.md`
- `eval_harness/benchmarks/registry.yaml` only for truthful grader/sandbox provenance wording
- `ATTRIBUTIONS.md` for the exact BigCodeBench Apache-2.0/OpenAI-MIT source attribution
- `pyproject.toml` only for a narrow Ruff exclusion of the exact vendored directory
- `tests/harness/test_bigcodebench_benchmark.py`
- `tests/harness/test_bigcodebench_grader_boundary.py` (new real Linux integration tests)
- `tests/harness/test_bigcodebench_runner.py` (new protocol/native-runner unit and spawn tests)
- `tests/harness/test_bigcodebench_sitecustomize.py` (new exact NLTK bootstrap tests)
- `resources_servers/bigcodebench/tests/test_app.py`
- `scripts/ci/install_bubblewrap.sh` (new pinned source installer)
- `scripts/ci/install_bigcodebench_grader.py` (new safe CPython/data/environment preparer)
- `scripts/ci/validate_bigcodebench_grader.py` (new disposable 1,140-task parity driver; no model calls)
- `scripts/ci/requirements-bwrap-build.in` and `scripts/ci/requirements-bwrap-build.lock` (new)
- `.github/workflows/eval-harness-ci.yml` only to provision and execute the reviewed boundary test job
- `.github/workflows/copyright-check.yml` only for the documented exact-vendor path exclusion described below

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

@dataclass(frozen=True, slots=True)
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

PRODUCTION_GRADER_LIMITS = GraderSandboxLimits()

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
    limits: GraderSandboxLimits = PRODUCTION_GRADER_LIMITS

@dataclass(frozen=True, slots=True)
class GraderSandboxPreflight:
    ok: bool
    sandbox_version: str | None
    policy_revision: str
    spec_sha256: str | None
    manifest_sha256: str | None
    attestation_sha256: str | None
    details: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class GraderNativeResult:
    native_status: NativeStatus | None
    limit_kind: LimitKind | None = None

class GraderInfrastructureError(RuntimeError):
    """Stable, secret-free grader boundary failure."""

def preflight_bigcodebench_sandbox(
    spec: GraderSandboxSpec,
) -> GraderSandboxPreflight:
    """Run the real policy probe and bind its facts to the exact spec."""
    raise NotImplementedError

def run_bigcodebench_sandbox(
    request: BigCodeBenchGradeRequest,
    *,
    spec: GraderSandboxSpec,
    preflight: GraderSandboxPreflight,
) -> GraderNativeResult:
    """Run one request, returning only an authenticated native outcome."""
    raise NotImplementedError

# eval_harness.bigcodebench_runner
def main(argv: Sequence[str] | None = None) -> int:
    """Run the trusted in-sandbox native-checker adapter."""
    raise NotImplementedError

# eval_harness.bigcodebench_sitecustomize
def configure_bigcodebench_nltk() -> None:
    """Configure the pinned downloader only under the literal sandbox policy."""
    raise NotImplementedError
```

The evaluator and resource server must call the same implementation. The spec digest is SHA-256 over canonical JSON for the resolved paths, every limit and policy revision. The attestation digest binds that spec digest, the manifest digest and the exact probe facts. `run_bigcodebench_sandbox` rejects a false or spec-mismatched attestation and re-hashes the manifest, binary, Python, runner, bootstrap, vendor and data identities immediately before launch; a changed identity is a stale preflight and fails closed. The digest is an integrity binding inside trusted code, not an authorization token. No direct `python bcb_runner.py` path may remain. `app.py` must not preserve an unsafe legacy route; its async endpoint calls the synchronous supervisor with `asyncio.to_thread` under a process-wide semaphore of size one.

The trusted supervisor, runner and NLTK startup bootstrap live under `eval_harness/`, so strict typing and the existing `source=eval_harness` coverage gate measure their parser, HMAC, state machine, bounded-I/O, error-map, worker and offline configuration logic. `bcb_runner.py` in the resources server is deleted. The inner file is mounted as `/opt/bigcodebench/bigcodebench_runner.py` and executed with `python -I -B`; its explicit imports are the standard library and pinned vendored metric. The setup script copies `bigcodebench_sitecustomize.py` byte-for-byte into the venv as `sitecustomize.py`, and preflight checks both hashes and effective NLTK configuration in a fresh isolated process. Security integration tests still run the real sandbox rather than weakening isolation for coverage.

Production limits are constants, not request fields or YAML values. Production constructors require `PRODUCTION_GRADER_LIMITS`; only the dedicated test module may construct a spec with smaller limits so resource fixtures finish safely, and the attestation binds those test values. Public input has exactly `schema_version=1`, `code`, `test_code`, `entry_point`, and `task_id`. Limit the encoded object to 8 MiB, `code` to 2 MiB, `test_code` to 6 MiB, and each identifier to 256 UTF-8 bytes. Reject duplicate/unknown keys, invalid UTF-8, identifier NULs, non-string fields, booleans where integers are required, non-finite JSON constants, and trailing input before importing the grader or spawning candidate code.

## Exact native metric source selection

Vendor only the three files imported by `untrusted_check`, byte-for-byte from BigCodeBench `v0.2.5`, plus the upstream root Apache-2.0 license. `eval/__init__.py` and `eval/utils.py` also retain their embedded OpenAI MIT notices; `_special_oracle.py` has no in-file notice and is covered by the repository license. Do not install the BigCodeBench wheel and its unrelated vLLM/provider/generation stack.

| Upstream path | Git blob | Content SHA-256 |
|---|---|---|
| `bigcodebench/eval/__init__.py` | `3596f53ddbdf92455805890aba9d75e4e10a5e6f` | `d5fd553559ac1b76659ebc32ae30e3e779449ecd31c5201f2301319ceeee01fe` |
| `bigcodebench/eval/utils.py` | `6d34de9971902dcf499ff5fb649e4abff3e7cd95` | `9061f74fe937c4eb7a1b2bc423f7acab547ae01804d5e25933e2aa8a3cc2d685` |
| `bigcodebench/eval/_special_oracle.py` | `4311cc9b30e5f0d4abd742e0c632daf535be69e7` | `0cf930163987d30f455547aec6cbc500a154bc58a2eb109aa247ef4e0962448b` |
| `LICENSE` | `27115b77b9e6c6c80f9b6987d8734fc8d532093c` | `a858540b8dfd0c74db6953edaae85bde0b671643a7e2fb04a065f4dfd25fc28c` |

Preflight hashes every file. A source-isolation test makes importing any non-vendored BigCodeBench module fail, while known pass/fail/timeout fixtures prove native parity.

Recoverable exact source bytes, including the upstream CRLF line endings, are preserved under `contracts/pr04-evidence/upstream-bigcodebench-v0.2.5/` with non-`.py` evidence suffixes and verified Git-blob/content hashes.

`VENDORING.md` records tag/commit/blob/content/license provenance without modifying the three upstream modules. Ruff's `extend-exclude` covers exactly `resources_servers/bigcodebench/vendor/bigcodebench`; authored supervisor/runner/bootstrap code is not excluded. The reusable copyright workflow scans non-`__init__.py` Python files and accepts the MIT header in `utils.py`, but exact `_special_oracle.py` has no first-ten-line notice. Its caller passes exactly `additional-find-args: '-not -path "./resources_servers/bigcodebench/vendor/bigcodebench/eval/_special_oracle.py"'`; no directory-wide copyright exclusion is permitted. A gate test requires `VENDORING.md`, upstream `LICENSE`, the literal workflow input and all four expected hashes. This preserves third-party bytes rather than treating them as NVIDIA-authored code; it does not exclude any authored code from typing, coverage, secret scan or tests. `ATTRIBUTIONS.md` records upstream Apache-2.0 and the two embedded MIT notices.

## Sandbox policy

Every launch is built by one command builder and uses mandatory bubblewrap flags. It must contain explicit `--unshare-user`, `--unshare-ipc`, `--unshare-pid`, `--unshare-net`, `--unshare-uts`, `--disable-userns`, `--cap-drop ALL`, `--clearenv`, `--new-session`, and `--die-with-parent`. It must not contain `--unshare-all`, any `*-try` option, `--share-net`, `--not-a-security-boundary`, a writable host bind, or a D-Bus/agent/container socket.

Bubblewrap starts from its empty mount-namespace root. Bind read-only only:

- the grader virtual environment at its resolved absolute host path;
- the virtual environment's resolved base-interpreter prefix at the same absolute path;
- measured `eval_harness/bigcodebench_runner.py` at `/opt/bigcodebench/bigcodebench_runner.py`;
- the exact vendored metric source at `/opt/bigcodebench/vendor`;
- the hash-verified NLTK archives, six expanded directories and local seven-package index at `/opt/bigcodebench/nltk_data`;
- `/usr`, then fixed in-sandbox `/bin -> usr/bin`, `/sbin -> usr/sbin`, `/lib -> usr/lib`, and `/lib64 -> usr/lib64` symlinks on the supported merged-`/usr` image; and only `/etc/ld.so.cache`, `/etc/ssl/certs`, `/etc/fonts`, and `/etc/localtime` when present;
- committed synthetic `/etc/{hosts,nsswitch.conf,resolv.conf,passwd,group}` files, with no host identity or resolver data.

Do not mount the repository root, executor workspace, run directory, home directory, host `/tmp`, `/run`, `/sys`, arbitrary `/etc`, or source/download caches. Add a new `/proc`, a minimal `/dev`, a 512 MiB private tmpfs at `/tmp`, a 64 MiB private tmpfs at `/dev/shm`, and empty `/tmp/{home,work}`. Work in `/tmp/work`.

Use `--clearenv` and only literal values: `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `TZ=UTC`, `HOME=/tmp/home`, `TMPDIR=/tmp`, `PATH=<venv>/bin:/usr/bin:/bin`, `MPLBACKEND=Agg`, `NLTK_DATA=/opt/bigcodebench/nltk_data`, `BIGCODEBENCH_NLTK_OFFLINE=bigcodebench-bwrap-v1`, `XDG_CACHE_HOME=/tmp/cache`, `XDG_CONFIG_HOME=/tmp/config`, `XDG_DATA_HOME=/tmp/data`, `MPLCONFIGDIR=/tmp/matplotlib`, `NUMBA_CACHE_DIR=/tmp/numba`, `TORCH_HOME=/tmp/torch`, `HF_HOME=/tmp/huggingface`, `JOBLIB_TEMP_FOLDER=/tmp/joblib`, `CUDA_VISIBLE_DEVICES=`, `TOKENIZERS_PARALLELISM=false`, and `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`, `NUMEXPR_NUM_THREADS`, `BLIS_NUM_THREADS`, `RAYON_NUM_THREADS`, `TF_NUM_INTRAOP_THREADS` and `TF_NUM_INTEROP_THREADS` each `1`. Interpreter isolation comes from `-I -B`; omit ignored `PYTHON*` environment controls rather than claiming they take effect under `-I`. Do not pass host credentials, proxy variables, cloud variables, `SSH_AUTH_SOCK`, tool tokens, `PYTHONPATH`, or `BIGCODEBENCH_TIMEOUT_PER_TASK`.

Do not use Python `preexec_fn`: the host service is threaded. The outer supervisor securely opens `/tmp/nemo-gym-bigcodebench-grader-<uid>.lock` with `O_CREAT|O_CLOEXEC|O_NOFOLLOW`, mode `0600`, verifies a regular single-link file owned by the current UID, and holds an exclusive `flock` across baseline measurement and cleanup. It starts bubblewrap with `subprocess.Popen(stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=0, close_fds=True, pass_fds=(), start_new_session=True)`, so only descriptors 0, 1 and 2 enter bubblewrap. This outer closure is necessary because pinned bubblewrap closes extras in its PID-namespace init but deliberately passes other descriptors to the command.

The measured runner receives a canonical, attested, non-secret limit object in fixed CLI arguments. At the start of `main`, after `PR_SET_DUMPABLE=0` and before reading any key or attacker-controlled byte or importing the vendored metric, it parses the fixed arguments, sets and reads back `RLIMIT_CPU=(245,250)`, `AS=8 GiB`, `DATA=6 GiB`, `STACK=10 MiB`, `FSIZE=64 MiB`, `NOFILE=256`, `CORE=(0,0)`, and `NPROC=(baseline real-UID process count + 32)`; any mismatch is infrastructure. The same code accepts smaller attested values only from the dedicated test spec. Only one grader sandbox runs per real UID; resource-server concurrency is one. The supervisor walks the host-visible descendant tree every 25 ms and kills at `>=32` descendants or `>=6 GiB` summed RSS. Startup is 20 seconds until authenticated START, candidate phase is 250 seconds, and teardown is 5 seconds after a terminal frame. Input is 8 MiB, authenticated protocol 16 KiB and diagnostics 32 KiB. On enforcement, kill the exact outer bubblewrap PID; `--die-with-parent` kills its PID-namespace init and command, and init death removes remaining namespace processes. Require the recorded descendants to disappear. Unbounded `capture_output`/`communicate` is forbidden; one nonblocking `selectors` loop performs bounded input, protocol and diagnostics I/O plus process sampling.

`RLIMIT_NPROC` and RSS polling are not cgroups: the former is real-UID scoped and the latter has a sampling race. The single-launch lock, measured baseline/headroom, hard per-process limits, PID namespace and cleanup tests are the explicit rootless composition. If hosted CI cannot demonstrate the process/memory fixtures without host impact, implementation fails; no fallback or stronger aggregate claim is allowed.

The path to bubblewrap is absolute and supplied by trusted configuration. Preflight requires exact version `0.12.0`; a regular single-link executable owned by root or the trusted runner UID; mode `0755` with no setuid, setgid, group-write or world-write bit; no file capabilities; confinement below the securely created install prefix; and the manifest hash. Owner writability by the trusted CI/setup identity is outside the candidate threat model and is never called immutability. Candidate code cannot see that host prefix. Preflight runs the same policy builder used for grading. Runtime never downloads or installs anything.

## Fail-closed preflight

Preflight runs before benchmark preparation or any executor/model request. It performs all of these checks and returns `ok=False` on the first failure with a stable, secret-free reason:

1. Linux x86-64; absolute real paths; securely created install roots; exact bubblewrap version/ownership/mode/capability/hash; locked grader manifest; exact Python `3.11.16`/architecture/SOABI/hash; exact runner/bootstrap/vendor/data hashes; `uv pip check`; and pairwise runner/venv/base/vendor/data separation from run, repository, executor, home and host-temp roots.
2. A real sandbox probe through the production command builder. Compare parent/child namespace inode IDs and require different mount, user, PID, network, IPC, and UTS namespaces; require `NoNewPrivs: 1`, `CapInh`, `CapPrm`, `CapEff` and `CapAmb` all zero, nested user namespaces disabled, a private `/proc`, the exact read-only mount set and active configured rlimits.
3. Put a random dummy secret in the parent environment and require it absent in the child. Put random read/write sentinels outside all mounts and require both open attempts to fail. Require writes to the runner, venv, `/usr`, base prefix, vendor and data to fail while a bounded `/tmp` write succeeds. Assert isolated-mode `sys.path` contains the venv, standard library and fixed vendor root but no repository, current directory, user site or host source root.
4. Start parent TCP listeners on IPv4 loopback and, when the host supports it, IPv6 loopback and a non-loopback address; also start a parent Unix listener outside the mount set. Require every child connection attempt to fail and require a different network namespace. This is deterministic and does not depend on an external Internet host.
5. Verify fresh-process site bootstrap values, all seven offline NLTK statuses and one functional lookup. Exercise wall/CPU, process-count, file-size, memory, descriptor, tmpfs, stdout/stderr and input/protocol limits with the smaller attested test spec, then verify complete descendant cleanup. The supported CI job treats absence of host IPv6 as a recorded platform fact, but never skips the namespace, IPv4, Unix-socket or other boundary assertions.

A local container that blocks user/network namespaces is unsupported and must fail this preflight. CI acceptance requires the same probes to pass and the hostile fixtures below to run; tests may not skip or mock the boundary on the supported job.

## Grader protocol and native outcomes

The upstream checker is a metric implementation, not a security boundary. Candidate children share the sandbox UID/PID namespace, so `FD_CLOEXEC` alone is insufficient. The result channel is authenticated and must satisfy this exact sequence:

1. Outer host creates a fresh 32-byte key with `secrets.token_bytes(32)`. Input is `BCBI` (four bytes), version `1` (one byte), payload length (unsigned four-byte big-endian), the 32-byte key, then exactly that many canonical UTF-8 JSON bytes and EOF. Runner re-encodes the parsed object and requires byte equality. The key never appears in argv, environment, files, diagnostics, logs or persisted results. Failure before a complete key is available produces no frame and is infrastructure.
2. At the first statement in `main`, before reading the key, runner calls `prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)` through a fixed `ctypes.CDLL(None, use_errno=True)` signature and verifies `prctl(PR_GET_DUMPABLE, 0, 0, 0, 0) == 0`; failure is infrastructure. It then validates and installs the attested limits described above.
3. After exact bounded input and EOF validation, use `F_DUPFD_CLOEXEC` to duplicate original stdout at or above FD 3, verify the duplicate is a pipe, and replace FDs 0, 1 and 2 with `/dev/null`. The result FD remains close-on-exec and is never listed in `pass_fds`, stored globally or passed to multiprocessing. This occurs before importing the metric, creating a Manager, or spawning candidate code.
4. Insert only `/opt/bigcodebench/vendor` into `sys.path`, call `multiprocessing.set_start_method("spawn", force=True)`, assert `get_start_method() == "spawn"`, then import the exact vendored metric. Keep the HMAC key local to runner `main`; never put it in a module global, closure passed as a process target, multiprocessing argument or manager object.
5. Frame header bytes are `BCBO` + version byte `1` + sequence byte + type byte + unsigned four-byte big-endian body length. Types are `START=1`, `RESULT=2`, `ERROR=3`. The following 32 bytes are `HMAC-SHA256(key, header || body)`, followed by the body. Bodies are UTF-8 JSON produced with `ensure_ascii=True`, `sort_keys=True`, `separators=(",", ":")`, and `allow_nan=False`. START body is exactly `{"schema_version":1}`. RESULT has exactly `native_status` (`pass`, `fail` or `timeout`) and `schema_version=1`. ERROR has exactly `error_code` and `schema_version=1`; allowed codes are `input_invalid`, `fd_setup_failed`, `native_setup_failed`, `native_start_failed`, `native_contract_invalid`, and `runner_internal`. It contains no exception text, traceback, task ID, source or test detail.
6. To align START with the unchanged upstream child boundary, runner temporarily wraps the default-context `multiprocessing.Process.start` method while calling `untrusted_check`. Manager starts pass through unchanged. The wrapper emits START only when `self._target is` the exact vendored `unsafe_execute`, immediately before invoking the original start, records that one Process object, rejects a second match, and is restored in `finally`. With `spawn`, neither this parent-only wrapper closure nor the key is serialized into the child. After `untrusted_check` returns, runner requires exactly one captured native Process, validates its return tuple/status and exit code, then emits RESULT. A setup exception after the key but before START emits `ERROR(0)`; an exception after START emits `ERROR(1)`.
7. Host accepts only `ERROR(0)+EOF`, `START(0),ERROR(1)+EOF`, or `START(0),RESULT(1)+EOF`. Both ERROR sequences are infrastructure. It uses `hmac.compare_digest`, limits the complete output to 16 KiB, and rejects unknown types, body keys/statuses, bad JSON/HMAC/length, missing/reordered/duplicate frames and any trailing byte. START moves the supervisor from the startup timer to the candidate timer. A resource result is returned only after valid START and either direct supervisor enforcement (`wall`, `memory`, `processes`) or the captured native wait status unambiguously reports `SIGXCPU` or `SIGXFSZ`. Other native-child signals retain upstream's returned `timeout` semantics; an unattributed signal or exit of the trusted runner or bubblewrap is infrastructure. `RLIMIT_NOFILE`, tmpfs-full, ordinary `MemoryError` and similar exceptions absorbed by upstream remain native `fail`; untrusted text is never parsed to invent a limit kind.

The hostile fixture must show denial for `/proc/<runner-pid>/{fd,environ,mem}`, `ptrace`, `process_vm_readv` and `pidfd_getfd`; scan every candidate-visible FD; spawn a grandchild; attempt forged frames; and signal the runner. Killing/corrupting the runner may deny a result but cannot create authenticated completion. The test also asserts that the runner result FD is absent from Manager, candidate and grandchild descriptor tables. HMAC protects channel authenticity; it does not make the Python Manager/status or native metric resistant to semantic gaming.

`GraderNativeResult` has exactly one of `native_status` or `limit_kind` set. Native PASS/FAIL/TIMEOUT comes only from an authenticated, schema-valid RESULT. A limit kind comes only from the observations in step 7. Every other terminal path raises `GraderInfrastructureError`.

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

Pin NLTK data separately to official `nltk/nltk_data` gh-pages commit `550b6625bcef1f2abff2ff770a5a0d272c9c6b2a`, index SHA-256 `97dce5e72320cd9850b7c20130196006710c18f9c03134c822a37da330198bf6`. Prepare exactly `stopwords`, `punkt`, `punkt_tab`, `averaged_perceptron_tagger`, `averaged_perceptron_tagger_eng`, `vader_lexicon`, and `words` from `nltk-data-manifest.json`; reject extra/missing files. The exact prepared tree is 167 files/85,741,209 bytes with canonical content-inventory SHA-256 `5a30cfb5c9d2a0353a987535b261386244abe66ac898185c514c913ac518514a`; its reduced index is 3,447 bytes, SHA-256 `27b1257a84cfec723c024c6762ed801ceb6984437d5438d4c7bed8bc6b52aafc`. `NLTK_DATA` alone is insufficient: the measured site bootstrap sets the pinned module-global downloader to this local index and read-only destination before candidate imports. Grade-time data is read-only and the fast path performs no write or network operation.

Official `nltk_data` license metadata marks the two taggers and VADER MIT and `words` public domain, but explicitly classifies `punkt`, `punkt_tab`, and `stopwords` as unclarified/unknown. Its license overview says the repository Apache-2.0 license does not cover individual packages. Do not vendor those three byte payloads into this repository or a redistributed grader artifact, and do not claim that they are Apache-compatible, without repository license review or an equivalently validated, clearly licensed native-parity source. Fixed-commit remote retrieval into an ephemeral preparation directory may continue for read-only provenance and benign compatibility testing; that technical activity is neither redistribution approval nor a license conclusion. This provenance issue is independent of the mandatory NLTK code-audit blocker.

Repository `grader-manifest.json` is canonical policy JSON containing schema `1`; policy revision `bigcodebench-bwrap-v1`; platform; Python/build provenance; accepted lock SHA-256; runner/bootstrap hashes; all vendored blob/content hashes; NLTK data commit/index/package/prepared-tree hashes; and bubblewrap version/tag/source SHA-256. It is encoded as UTF-8 with sorted keys, compact separators and a final newline. Setup writes a separate canonical runtime manifest below the secure install root containing the policy-manifest hash, installed prefix/venv inventory hashes, bubblewrap binary SHA-256 and recorded build-package versions, then makes it read-only. Preflight recalculates every locally observable field and compares both manifests. Dataset revision is separate.

Prefix/venv inventory hashes use a compact RFC 8259 JSON array sorted by POSIX relative path. A regular-file entry has exactly `path`, `type="file"`, `mode`, `size` and `sha256`; a symlink entry has exactly `path`, `type="symlink"` and its literal non-escaping `target`. Object keys are sorted, UTF-8 encoding is used, and no final newline enters the digest. Reject devices, sockets, FIFOs, absolute/escaping links, hard-linked regular files and any extra/missing path. Current evidence inputs are the rejected grader lock SHA-256 `8d62cac6880124652638ff8716532d46d459aaf5cbe6e8c36b506a4d1e4de9bd`, build lock SHA-256 `32df6b18b4c96eb4146d18cd16adad24efecba5c4a5212115f5c6acea4749605`, data manifest SHA-256 `8cda33ca56e34b58702a16dd6b3b9160fd2e8f38d03b1062f83550c95a435938`, and reduced-index SHA-256 `27b1257a84cfec723c024c6762ed801ceb6984437d5438d4c7bed8bc6b52aafc`. The implementation must replace the rejected-lock value with the clean accepted lock; it must not generate an acceptance manifest from the rejected lock.

### Unresolved NLTK acceptance gate

Strict `pip-audit` 2.10.1 reports exactly NLTK 3.10.3 `PYSEC-2026-3740`, aliases `CVE-2026-81726` and `GHSA-8mgp-746c-j5xp`, with no fix. The preserved minimal backport and deterministic wheel are **rejected evidence**, not a remediation option: independent controls reproduce a benign `load_from_json` `NameError` and outside-victim truncation through an allowed-root hardlink before `PermissionError`.

Do not install that wheel, ignore the CVE, spoof a version, rename the package, or claim a local backport satisfies the standard gate. Gate A remains red until an official fixed NLTK release produces a clean regenerated lock. Any exception or replacement audit policy requires the user’s explicit plan amendment; an internal reviewer cannot weaken this gate. Research on a replacement backport, if retained, must port the official companion behavior and test validate-before-truncate, hardlinks for every write sink, FIFOs/devices/sockets without blocking, default paths, direct path-shaped inputs, and benign in-root roundtrips; it still cannot turn standard audit green.

### Exact CPython and bubblewrap setup path

`scripts/ci/install_bigcodebench_grader.py` downloads the immutable `python-build-standalone` release `20260901` asset ID `539915682` from its literal URL, requires size `30778779` and SHA-256 `64427febea27864d136db46c8efe968eb6fa5ca2813ce1dca4bb95aec31cb2e4`, rejects unsafe tar members, and extracts the single `python/` root into a newly and securely created `$RUNNER_TEMP/pr04-cpython-3.11.16+20260901`. It verifies CPython `3.11.16`, `x86_64`, SOABI `cpython-311-x86_64-linux-gnu`, executable SHA-256 `1e761eb19d6f2594ab8dc64bd99ad4e1753589f3bf1ec199e4eef3aaa21e3930`, and license SHA-256 `3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf`. It creates `$RUNNER_TEMP/pr04-bigcodebench-venv` with the absolute interpreter using repository uv `0.11.29`, `--no-project`, `--no-managed-python`, `--no-python-downloads`, and copy link mode, then syncs the accepted grader lock with `--require-hashes --no-managed-python --no-python-downloads --strict`. It never calls uv's Python installer.

`scripts/ci/install_bubblewrap.sh` retrieves the literal `https://github.com/containers/bubblewrap/releases/download/v0.12.0/bubblewrap-0.12.0.tar.xz`, requires size `126452` and SHA-256 `9760d007363e3abba7c747489910f9f82d9fca53ba3bd3282e396fa3c97a3314` before extraction. Its Python build tools are exactly Meson `1.9.1` and Ninja `1.13.0` from `scripts/ci/requirements-bwrap-build.lock`, installed by uv `0.11.29` with hashes. On Ubuntu 24.04 the provisioning step installs/verifies `build-essential`, `pkg-config` and `libcap-dev`, records their `dpkg-query` versions, configures with `--buildtype=release -Dselinux=disabled -Dman=disabled -Dtests=true -Dbash_completion=disabled -Dzsh_completion=disabled`, compiles, runs upstream tests, and installs under a securely created `$RUNNER_TEMP/pr04-bwrap-0.12.0`. It verifies `bwrap --version`, ELF architecture, exact mode/ownership, absence of file capabilities/set-ID bits and records the built binary SHA-256. Every sandbox invocation remains rootless. The CI job exports only that absolute binary path.

The dedicated `ubuntu-24.04` boundary job uses these paths and then runs, in order: strict audit of the accepted grader lock and build-tool lock; grader preparation; `uv pip check`; manifest generation/readback; the real preflight test; hostile fixtures; `scripts/ci/validate_bigcodebench_grader.py` over all 1,140 canonical solutions in a disposable credential-free checkout/data root. Canonical comparison has an unsandboxed exact-source reference only inside that disposable CI environment with an empty allowlisted environment and no user/workspace mounts or credentials. It is parity evidence and never runs against user-controlled workspace data. The finite command/path appendix is `contracts/pr04-grader-boundary-implementation-appendix.md`.

## Required tests and expected results

Unit tests may patch process creation only to test parsing and error mapping. Security acceptance comes from `tests/harness/test_bigcodebench_grader_boundary.py`, executed on `ubuntu-24.04` with pinned bubblewrap built from its verified source asset and the hash-locked grader environment.

The real test submits hostile candidate code through the public evaluator or the shared sandbox entry point and proves:

- dummy host env secrets and proxy/token-shaped values are absent;
- a randomized prohibited file cannot be read, created, renamed, linked, or written, including via absolute symlinks and `/proc` paths;
- the executor workspace, run directory, repository siblings, host home, and host `/tmp` sentinels are invisible;
- IPv4, IPv6, DNS and parent TCP/Unix listeners are unreachable; a candidate-created Unix socket under private `/tmp` works for native multiprocessing;
- fork/subprocess storms, memory allocation, descriptor creation, large files, private-tmp exhaustion, infinite loops, and output floods terminate within the exact bounds and leave no descendant;
- venv/runner/system mounts reject writes and private `/tmp` permits bounded writes;
- candidate raw FD writes, `/proc` reopening, `ptrace`, `process_vm_readv`, `pidfd_getfd`, child/grandchild inheritance and forged frames cannot produce an authenticated result;
- known pass, known wrong answer, empty output, no-code extraction, candidate timeout/resource limit, and injected grader infrastructure failure produce the exact table above;
- an intentionally unavailable sandbox fails evaluator preflight before a counting executor/model stub is called.

No security assertion may pass because bubblewrap is mocked, because a fixture only checks command text, or because the supported-platform test is skipped. Keep normal hermetic unit tests for unsupported developer hosts, but the dedicated CI job must fail rather than skip if its real probe cannot run.

Run repository Ruff, strict typing, the repository's 96% strict harness coverage gate, hash-locked dependency audit with no silent CVE allowlist, secret scan, copyright check, and the dedicated boundary job. Do not weaken or exclude gates.

## Done criteria and prohibitions

PR04 is done only after Sol reviews the implementation and CI logs show the real supported-platform probe and every hostile fixture passing. The evaluator and resource server have one launch path, preflight precedes model work, infrastructure failures stop the run without a zero score, and durable metadata identifies dataset, grader, dependency lock, sandbox, and policy independently.

No model calls, production credentials, external grader service, container daemon socket, runtime network install, fallback sandbox, setuid helper, root runtime, mocked security acceptance, force push, PR merge, or workflow-as-editing-transport.

## Remaining implementation-time proofs

- After an official fixed NLTK release exists, regenerate and clean-audit the full hash lock, then run all 1,140 canonical solutions under CPython 3.11.16 and the exact 8/6 GiB limits, compare to the disposable unsandboxed exact-source reference, and investigate every delta. Do not install the rejected 160-distribution candidate as an accepted grader.
- Run all 26 NLTK tasks and all seven prepared data assets against that official fixed release.
- Demonstrate the production bubblewrap policy and same-UID spawn/FD/`/proc` protocol on hosted `ubuntu-24.04`.
- Use the now-pinned CPython 3.11.16 artifact and exact setup recipe below; verify its manifest and full locked-environment inventory on hosted CI.
