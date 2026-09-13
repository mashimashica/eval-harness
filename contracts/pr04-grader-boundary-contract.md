<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR04 BigCodeBench grader boundary implementation contract

**State:** DRAFT — design checkpoint; implementation and CI boundary proof are not yet validated.

**Review order:** Sol design/security review, then Luna implementation.

## Goal and exact base

Implement a fail-closed host-security boundary for BigCodeBench native grading. Candidate Python is hostile. A virtual environment is dependency separation only and must never be described, tested, or accepted as a sandbox.

- Implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75` (tree `354943ebbb8ea81a30523bfdc12baf26771853b5`).
- Control/checkpoint base: `8518f25d107d9043df449a9198fbb41b00ba1c22`.
- Benchmark dataset revision remains `v0.1.4` and is recorded separately from the grader package.
- Grader package is exactly BigCodeBench `v0.2.5`, tag commit `9bd90fedee89d7dc3676838c75d9642cb0cd0702`.
- One supported sandbox: bubblewrap `v0.12.0`, tag commit `2a76602a8c71f36c1527cf9fc3417d9149822e0c`, source asset SHA-256 `9760d007363e3abba7c747489910f9f82d9fca53ba3bd3282e396fa3c97a3314`.
- Supported validation platform: Linux x86-64 on a fixed `ubuntu-24.04` GitHub-hosted runner. Runtime setup and every grader launch run as the ordinary runner user. Unsupported platforms or blocked user namespaces fail preflight; there is no fallback.

## Allowed implementation paths

Luna may change only these paths. A newly discovered need outside the list returns to Sol for a contract amendment.

- `eval_harness/evaluators/bigcodebench.py`
- `eval_harness/grader_sandbox.py` (new, BigCodeBench-specific bubblewrap policy and process supervisor)
- `resources_servers/bigcodebench/bcb_runner.py`
- `resources_servers/bigcodebench/app.py`
- `resources_servers/bigcodebench/setup_bcb_venv.py`
- `resources_servers/bigcodebench/requirements-grader.in` (new)
- `resources_servers/bigcodebench/requirements-grader.lock` (new, full hashes)
- `resources_servers/bigcodebench/configs/bigcodebench.yaml`
- `resources_servers/bigcodebench/README.md`
- `eval_harness/benchmarks/registry.yaml` only for truthful grader/sandbox provenance wording
- `tests/harness/test_bigcodebench_benchmark.py`
- `tests/harness/test_bigcodebench_grader_boundary.py` (new real Linux integration tests)
- `resources_servers/bigcodebench/tests/test_app.py`
- `scripts/ci/install_bubblewrap.sh` (new pinned source installer)
- `.github/workflows/eval-harness-ci.yml` only to provision and execute the reviewed boundary test job

Do not edit central migration state, unrelated evaluators/executors, coverage/audit thresholds, generated fixtures, or model/provider paths.

## Required interfaces

`eval_harness/grader_sandbox.py` owns one immutable policy and exposes the following typed boundary. Names may change only with Sol approval; behavior may not.

```python
@dataclass(frozen=True)
class GraderSandboxLimits:
    wall_seconds: float
    cpu_seconds: int
    address_space_bytes: int
    data_bytes: int
    stack_bytes: int
    file_bytes: int
    open_files: int
    processes: int
    tmp_bytes: int
    stdin_bytes: int
    stdout_bytes: int
    stderr_bytes: int

@dataclass(frozen=True)
class GraderSandboxPreflight:
    ok: bool
    sandbox_version: str | None
    policy_revision: str
    details: tuple[str, ...]

@dataclass(frozen=True)
class GraderSandboxResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    wall_timed_out: bool
    output_limited: bool

class GraderInfrastructureError(RuntimeError):
    """Stable, secret-free grader boundary failure."""

def preflight_bigcodebench_sandbox(...) -> GraderSandboxPreflight: ...
def run_bigcodebench_sandbox(payload: bytes, ...) -> GraderSandboxResult: ...
```

The evaluator and resource server must call the same implementation. No direct `python bcb_runner.py` path may remain. `app.py` must not preserve an unsafe legacy route.

Input is one UTF-8 JSON object with exactly `schema_version`, `code`, `test_code`, `entry_point`, `task_id`, `max_as_limit`, `max_data_limit`, `max_stack_limit`, `min_time_limit`, and `gt_time_limit`. Enforce field types, finite numeric ranges, and a configured byte limit before launch. Output is exactly one UTF-8 JSON object with a version, a closed status enum, and bounded, sanitized details. Reject trailing bytes, duplicate keys, NaN/infinity, oversized output, unknown fields/statuses, and nonzero exits unless explicitly mapped to a candidate resource outcome.

## Sandbox policy

Every launch is built by one command builder and uses mandatory bubblewrap flags. It must contain explicit `--unshare-user`, `--unshare-ipc`, `--unshare-pid`, `--unshare-net`, `--unshare-uts`, `--disable-userns`, `--clearenv`, `--new-session`, and `--die-with-parent`. It must not contain `--unshare-all`, any `*-try` option, `--share-net`, `--not-a-security-boundary`, a writable host bind, or a D-Bus/agent/container socket.

Bubblewrap starts from its empty mount-namespace root. Bind read-only only:

- the grader virtual environment at its resolved absolute host path;
- the virtual environment's resolved base-interpreter prefix at the same absolute path;
- `bcb_runner.py` at its resolved absolute path;
- the minimum host runtime trees required by the locked grader (`/usr`, existing `/lib` and `/lib64`, and individually justified certificate/loader files).

Do not mount the repository root, executor workspace, run directory, home directory, host `/tmp`, `/run`, `/sys`, or arbitrary `/etc`. Add a new `/proc`, a minimal `/dev`, size-capped private tmpfs mounts for `/tmp` and `/dev/shm`, and a private empty home below `/tmp`. The command working directory is that private directory, never the resource directory.

Use `--clearenv` and a literal allowlist only: deterministic locale/TZ, `HOME`, `TMPDIR`, `PATH`, `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=0`, cache/config paths below private `/tmp`, and bounded numerical-library thread counts. Do not pass host credentials, proxy variables, cloud variables, `SSH_AUTH_SOCK`, tool tokens, `PYTHONPATH`, or `BIGCODEBENCH_TIMEOUT_PER_TASK`.

A trusted outer launcher applies hard `setrlimit` values before `execve(bwrap, ...)`: CPU, AS, DATA, STACK, FSIZE, NOFILE, NPROC, and CORE=0. It starts a new session, uses a parent wall-clock watchdog, kills the complete process group on timeout/output overflow, and reaps it. Pipe readers enforce bounds while the process runs; `subprocess.run(capture_output=True)` and `asyncio.communicate()` with unbounded buffers are forbidden. The private tmpfs size is an additional aggregate write bound.

The path to bubblewrap is absolute and supplied by trusted configuration. Preflight requires exact version `0.12.0`, refuses a setuid/setgid or mutable executable, and runs the same policy builder used for grading. Runtime never downloads or installs anything.

## Fail-closed preflight

Preflight runs before benchmark preparation or any executor/model request. It performs all of these checks and returns `ok=False` on the first failure with a stable, secret-free reason:

1. Linux x86-64, absolute bubblewrap path, exact version, acceptable ownership/mode, locked grader manifest, exact Python `3.10.21`, exact BigCodeBench `0.2.5`, `uv pip check`, runner/venv/base-prefix separation from the run and executor roots.
2. A real sandbox probe through the production command builder. Compare parent/child namespace inode IDs and require different mount, user, PID, network, IPC, and UTS namespaces; require `NoNewPrivs: 1`, zero effective capabilities, nested user namespaces disabled, a private `/proc`, and active configured rlimits.
3. Put a random dummy secret in the parent environment and require it absent in the child. Put random read/write sentinels outside all mounts and require both open attempts to fail. Require writes to the runner, venv, `/usr`, and base prefix to fail while a bounded `/tmp` write succeeds.
4. Start parent listeners on loopback and a non-loopback interface when available; require child IPv4/IPv6 connection attempts to fail and require a different network namespace. This is deterministic and does not depend on an external Internet host.
5. Exercise timeout, process-count, file-size, memory, descriptor, tmpfs, and stdout/stderr limits with tiny probe values, then verify complete descendant cleanup.

A local container that blocks user/network namespaces is unsupported and must fail this preflight. CI acceptance requires the same probes to pass and the hostile fixtures below to run; tests may not skip or mock the boundary on the supported job.

## Grader protocol and native outcomes

The upstream checker is a metric implementation, not a security boundary. `bcb_runner.py` must force a multiprocessing mode that does not leak the trusted protocol descriptor into candidate children, redirect candidate stdout/stderr at file-descriptor level to bounded sinks, call the pinned `untrusted_check`, validate its return, and emit one bounded envelope. This behavior needs a real compatibility test with the pinned package. Do not return tracebacks or exception text across the boundary.

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

Replace the mutable `bigcodebench>=0.2.5` plus `main/Requirements/requirements-eval.txt` installer and `.installed` sentinel. Commit a solver-valid `requirements-grader.lock` with exact versions and SHA-256 hashes for every wheel/sdist. Install only with pinned uv and require hashes; do not use a resolver-bypass sequence or a runtime URL. The input records BigCodeBench `0.2.5` and the audited, explicit compatibility overrides needed for Python 3.10.21. If the upstream pins cannot form a coherent audited environment, PR04 is blocked; do not silently omit packages or retain the permissive pip install.

The installation manifest is JSON containing the Python full version, platform, lock-file SHA-256, installed-distribution inventory hash, BigCodeBench version/tag commit and inspected source blob SHAs, bubblewrap version/tag commit/source-asset SHA-256, and sandbox policy revision. Preflight recalculates and compares it. Dataset revision is a distinct metadata field.

## Required tests and expected results

Unit tests may patch process creation only to test parsing and error mapping. Security acceptance comes from `tests/harness/test_bigcodebench_grader_boundary.py`, executed on `ubuntu-24.04` with pinned bubblewrap built from its verified source asset and the hash-locked grader environment.

The real test submits hostile candidate code through the public evaluator or the shared sandbox entry point and proves:

- dummy host env secrets and proxy/token-shaped values are absent;
- a randomized prohibited file cannot be read, created, renamed, linked, or written, including via absolute symlinks and `/proc` paths;
- the executor workspace, run directory, repository siblings, host home, and host `/tmp` sentinels are invisible;
- IPv4, IPv6, DNS, Unix sockets, and parent listeners are unreachable except candidate-created loopback resources inside its own namespace;
- fork/subprocess storms, memory allocation, descriptor creation, large files, private-tmp exhaustion, infinite loops, and output floods terminate within bounds and leave no descendant;
- venv/runner/system mounts reject writes and private `/tmp` permits bounded writes;
- candidate raw FD writes cannot forge or corrupt the outer protocol;
- known pass, known wrong answer, empty output, no-code extraction, candidate timeout/resource limit, and injected grader infrastructure failure produce the exact table above;
- an intentionally unavailable sandbox fails evaluator preflight before a counting executor/model stub is called.

No security assertion may pass because bubblewrap is mocked, because a fixture only checks command text, or because the supported-platform test is skipped. Keep normal hermetic unit tests for unsupported developer hosts, but the dedicated CI job must fail rather than skip if its real probe cannot run.

Run repository Ruff, strict typing, the repository's 96% strict harness coverage gate, hash-locked dependency audit with no silent CVE allowlist, secret scan, copyright check, and the dedicated boundary job. Do not weaken or exclude gates.

## Done criteria and prohibitions

PR04 is done only after Sol reviews the implementation and CI logs show the real supported-platform probe and every hostile fixture passing. The evaluator and resource server have one launch path, preflight precedes model work, infrastructure failures stop the run without a zero score, and durable metadata identifies dataset, grader, dependency lock, sandbox, and policy independently.

No model calls, production credentials, external grader service, container daemon socket, runtime network install, fallback sandbox, setuid helper, root runtime, mocked security acceptance, force push, PR merge, or workflow-as-editing-transport.

## Open review items before Luna starts

- Confirm that forcing multiprocessing `spawn` plus descriptor-level redirection preserves BigCodeBench `v0.2.5` results while keeping the protocol descriptor out of candidate descendants.
- Confirm the minimal read-only runtime mounts against the completed lock; do not broaden to the repository/home when an import fails.
- Choose concrete numeric defaults from the existing benchmark limits and CI concurrency, then test every one. `RLIMIT_NPROC` is per real UID and therefore an imperfect concurrent aggregate; record that limitation and validate headroom.
- CI has not yet demonstrated that the current hosted-runner kernel permits every mandatory namespace. That is an explicit acceptance test, not an assumption or a reason to add fallback behavior.
