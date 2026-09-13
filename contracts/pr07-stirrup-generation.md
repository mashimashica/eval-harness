# PR07 contract: benchmark-neutral Stirrup generation

Status: design checkpoint; implementation has not started

Owner: Sol design review

Control parent: `8518f25d107d9043df449a9198fbb41b00ba1c22`

Inspected implementation baseline: `d5ce0c10162cad788a17cb90f34b8f60574e7f75` (tree `354943ebbb8ea81a30523bfdc12baf26771853b5`)

The implementation target must be the exact accepted head after PR06 and the active PR02c bundle/run integration. Luna must not start from a symbolic branch or from `d5ce0c1` alone. The migration owner records the 40-character target commit in the implementation task after those dependencies are accepted.

## 1. Decision

PR07 adds a real `StirrupExecutor` to the generic harness. It runs one policy generation from one `ExecutionRequest` and returns one typed `ExecutionResult`; the common runner seals that result into a `CandidateBundle`. The new path calls a small async Stirrup runtime directly in the harness process. It does not start the legacy agent server, submit a Ray job, invoke `./gdpval` or any provider shell, post to `/run`, post to `/verify`, score a candidate, read a cached judgement, or aggregate rewards.

The API/runtime boundary is explicit:

| Owner | Responsibility |
|---|---|
| `eval_harness` synchronous control | Strict config loading, source hashing, preflight, credential resolution, input staging, total timeout, failure mapping, output validation/recovery, `ExecutionResult`, provider/config evidence, and runner lifecycle. |
| `eval_harness` async Stirrup runtime | Build one Stirrup `Agent`/session around a typed local client, call the configured OpenAI-compatible policy endpoint through `nemo_gym.server_utils.request`, run tools, capture the provider-returned model ID, and return a typed session outcome. |
| `eval_harness` Stirrup sandbox/compatibility | Own the typed Apptainer provider, finish tools, provider message serialization, tool-result wire-role conversion, subprocess lifecycle, and exact nested-output recovery. These are narrow ports of useful NVIDIA resource mechanics kept inside the measured adapter boundary. |
| Legacy NVIDIA resources | Their behavioral source remains untouched and operational for comparison until PR10; PR07 only aligns the legacy requirements pin. The new executor imports none of them; section 9 maps each source to its measured replacement and final deletion. |
| Benchmark adapter | Canonical task, execution-view files, and any benchmark-specific user-prompt wrapper. GDPval sector/occupation/reference presentation stays here. |
| Evaluator | Rubric/reference projection, file rendering, pairwise judging, `/verify` replacement behavior, retries, votes, and metrics. |

Ray is not part of the generic PR07 route. The current generic runner is synchronous and task-sequential; distributing independent applications is an orchestrator concern. Apptainer remains the production code-execution isolation mechanism inside each Stirrup session.

## 2. Neutral contracts

`TaskSpec` remains exactly `{task_id, prompt}`. `ExecutionRequest` remains the neutral source of the effective task prompt, workspace, assigned deliverables directory, executor-private directory, requested model, wall-clock timeout, and environment. No provider, rubric, answer, judge, sector, occupation, benchmark name, reference URL, or cached judgement field is added to either type.

`StirrupExecutor.capabilities` is exactly prompt text plus workspace files as inputs and final text plus artifact files as outputs. The common `preflight_capabilities()` compares those values to the benchmark's typed requirements. Core execution/configuration matching compares the generic evidence values defined below; it never branches on `provider.id`, executor name, benchmark name, or configuration schema name. Only the explicit executor registry maps the CLI name `stirrup` to its constructor.

The executor is constructed with a parsed Stirrup configuration. At execution it must:

1. require a non-empty `request.model` plus a finite positive, non-boolean `request.timeout_seconds`, and use the exact model string in every policy request;
2. send `request.task.prompt` unchanged as the Stirrup user task;
3. stage `request.workspace` without the assigned `deliverables_dir`, preserving relative paths and rejecting symlinks, irregular files, unsafe names, and collisions;
4. resolve only the credential environment names declared by config from `request.environment`;
5. run one session within `request.timeout_seconds`;
6. validate and copy only the session's explicitly reported output files into the assigned, initially empty `deliverables_dir`;
7. return final text and artifact channels without reading, rendering, or concatenating artifact contents; and
8. return a typed failure with no output channels on infrastructure/protocol failure.

Successful output rules are fixed:

| Session outcome | `ExecutionStatus` | `FINAL_TEXT` | `ARTIFACT_FILES` |
|---|---|---:|---:|
| Successful finish with text and files | `COMPLETED` | yes | yes |
| Successful finish with text and no files | `COMPLETED` | yes | no |
| Successful finish with files and no text | `COMPLETED` | no | yes |
| Successful finish with neither channel | `NO_DELIVERABLE` | no | no |
| Abandon or max-turn exhaustion | `NO_DELIVERABLE` | no | no |
| Typed runtime/config/transport/integrity failure | failure-specific status | no | no |

An empty string is a real final-text value only when the successful finish outcome records that provider content was a JSON string. Missing/null text is `None`. `ARTIFACT_FILES` is present only when at least one validated file exists. PR07 must not fabricate `"No output produced by agent"`, turn an exception into answer text, append decoded files to answer text, or expose history/finish bookkeeping as candidate artifacts.

### 2.1 Generic execution-configuration evidence

Provider-specific fields must not be scattered through the generic runner. Add one fixed generic type in `eval_harness.executors.base`:

```python
@dataclass(frozen=True, slots=True)
class ExecutionConfigurationEvidence:
    schema: str
    schema_version: int
    source_sha256: str
    runtime_id: str
    protocol: str
```

For Stirrup v1 the values are:

```text
schema = "stirrup-executor-config"
schema_version = 1
runtime_id = <config provider.id>
protocol = "openai-chat-completions"
source_sha256 = SHA-256 of the exact UTF-8 config file bytes before parsing
```

The optional field `configuration: ExecutionConfigurationEvidence | None` is added to `PreflightResult` and `ExecutionResult`. Stirrup emits the same non-null value from successful preflight and every completed, no-deliverable, timed-out, interrupted, or failed result. A failed preflight also carries it whenever strict source parsing produced the frozen config; only source read/UTF-8/JSON/schema failures before that point use `None`. The common runner requires exact preflight/result equality for every task and places its fixed serialization in the executor descriptor and run configuration. `execution_record()` serializes only these named fields; arbitrary `ExecutionResult.metadata` remains excluded.

`ExecutorEvidence` in `CandidateBundle` gets the same optional nested `configuration` object. PR02c establishes CandidateBundle schema version 1; PR07 sets `CANDIDATE_BUNDLE_SCHEMA_VERSION = 2`. Version 2 requires the `configuration` key even when its value is JSON `null`. Every encoder, decoder, exact-key check, result-journal reader, resume reader, artifact sealer, validator, CLI inspection path, golden fixture, and test producer migrates in this same change. Version 1 is rejected as an unsupported schema before nested decoding. There is no dual reader, field alias, inferred default, migration-at-read, or old/new fallback.

The nested `ExecutionConfigurationEvidence` schema remains independently version 1. That version describes the Stirrup configuration document, while CandidateBundle version 2 describes the enclosing evidence record. Existing local executors emit `configuration: null`; their expected bytes and digests change once and their strict fixtures are regenerated from reviewed values.

The only non-null JSON shape is:

```json
{
  "protocol": "openai-chat-completions",
  "runtime_id": "policy",
  "schema": "stirrup-executor-config",
  "schema_version": 1,
  "source_sha256": "<64 lowercase hex>"
}
```

The generic dataclass rejects booleans as the integer version, non-positive versions, empty/control-bearing strings, and malformed digests. The Stirrup config parser alone requires its schema/version/protocol constants. CandidateBundle decoding requires these exact five keys. The core equality check compares the typed object directly; it does not parse `runtime_id`, switch on protocol/provider, or accept metadata as a substitute.

The evidence contains no URL, header, environment-variable name, secret value, prompt, or arbitrary mapping. The top-level run configuration hash changes because it includes this fixed object. Requested model remains in existing executor evidence; `ExecutionResult.model_id` is the exact non-empty `model` returned by the provider on every validated turn. All turns must report one identical value. A completed/no-deliverable result, or a later sandbox failure, carries that value when at least one valid response was received; a failure before any valid response carries `None`. A missing or mixed returned model is a protocol failure and carries `None` rather than partial or ambiguous model evidence. A returned versioned model may differ from the requested alias; both are persisted and the harness does not pretend they are equal.

`enable_thinking` or reasoning-token usage is a requested provider option, not proof of an effective reasoning-effort tier. PR07 leaves `effective_reasoning_effort_available=False` and `effective_reasoning_effort=None` unless the configured protocol later supplies an authoritative typed field. The existing generic reasoning-effort CLI remains rejected for Stirrup; the non-fallback rule is satisfied by sending the explicit config value once and failing a rejected request.

## 3. Strict, secret-free Stirrup config

The CLI adds `--executor-config FILE` for a Stirrup application executor and `--builder-executor-config FILE` when an experiment selects Stirrup as builder. A config is required for each selected Stirrup role and rejected for every executor that does not consume it. `--model` (and `--builder-model` for a Stirrup builder) is required. There is no environment-selected config, provider preset, implicit `env.yaml`, or default model.

Version 1 is strict JSON with duplicate keys, non-finite numbers, unknown fields, a BOM, invalid UTF-8, and non-regular/symlink sources rejected. Its logical shape is:

```json
{
  "schema": "stirrup-executor-config",
  "schema_version": 1,
  "provider": {
    "id": "policy",
    "protocol": "openai-chat-completions",
    "base_url": "https://policy.example/v1",
    "auth": {
      "mode": "bearer-env",
      "environment_variable": "MODEL_API_KEY"
    }
  },
  "session": {
    "system_prompt": "You are an agent ...",
    "max_turns": 250,
    "context_window_tokens": 262144,
    "completion_token_buffer": 1000,
    "minimum_completion_tokens": 1024,
    "maximum_completion_tokens": 64000,
    "temperature": 1.0,
    "top_p": 0.95,
    "enable_thinking": true,
    "finish_mode": "coercing-with-abandon",
    "tokenizer": {
      "mode": "huggingface-local",
      "model_id": "organization/tokenizer",
      "revision": "0123456789abcdef0123456789abcdef01234567",
      "snapshot_path": "/absolute/path/tokenizer-snapshot",
      "snapshot_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "counting_method": "chat-template-with-tools",
      "trust_remote_code": false,
      "local_files_only": true
    }
  },
  "sandbox": {
    "kind": "apptainer",
    "executable": "/usr/bin/apptainer",
    "runtime_version": "1.5.3",
    "image": "/absolute/path/policy-tools.sif",
    "image_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "working_directory": "/workspace"
  },
  "web": {
    "kind": "disabled"
  }
}
```

String fields are valid non-empty UTF-8 without control characters and integer fields reject booleans. `provider.id` matches `[a-z][a-z0-9-]{0,63}`. `max_turns` is 1 through 1,000; token counts are positive, `minimum_completion_tokens <= maximum_completion_tokens < context_window_tokens`, and `completion_token_buffer + minimum_completion_tokens < context_window_tokens`. `temperature` is finite in `[0, 2]` and `top_p` is finite in `(0, 1]`. `sandbox.executable` and `sandbox.image` are absolute regular non-symlink files, the image digest is lowercase SHA-256, and schema v1 requires `runtime_version="1.5.3"` and `working_directory="/workspace"`. Preflight executes the configured binary without a shell and requires its normalized version output to equal that literal. Paths, version, and files are rechecked at execution.

For deterministic mock tests, `tokenizer` may instead be exactly `{"mode":"utf8-bytes-v1"}`. That is an explicit conservative estimator and is hashed. It is never an automatic fallback. AA-v2 requires `huggingface-local`: `model_id` is a syntactically valid repository identity, `revision` is a full lowercase 40-hex commit, and `snapshot_path` is an absolute regular non-symlink directory whose recursively safe file tree matches `snapshot_sha256`. The digest is SHA-256 over each NFC relative POSIX path, NUL, decimal byte length, NUL, and file bytes, in bytewise path order; symlinks, irregular files, unsafe/colliding names, and mutation during hashing fail closed.

The executor loads `snapshot_path` with exact Transformers 5.17.0 `AutoTokenizer.from_pretrained(..., local_files_only=True, trust_remote_code=False)` and calls `apply_chat_template(messages, tools=..., tokenize=True, add_generation_prompt=True)` once. Both booleans in config are required to be those fixed values. No Hugging Face network request is allowed at preflight or execution. A tokenizer import, tree-integrity, load, template, tool-schema, or tokenization failure fails preflight or execution with a stable protocol/config code; it never changes source or counting method. If the computed remaining context is below `minimum_completion_tokens`, the provider is not called.

`auth.mode` is exactly `bearer-env` or `none`. Schema v1 recognizes only the literal host references `MODEL_API_KEY` and `BUILDER_MODEL_API_KEY`. The executor is constructed with a `RootDenyRolePolicy`; an application policy has the singleton `environment_allowlist=("MODEL_API_KEY",)` and a builder policy has the singleton `environment_allowlist=("BUILDER_MODEL_API_KEY",)`. The config's `environment_variable` must equal that one role-approved name. Any additional allowlist entry, cross-role name, other spelling, or arbitrary environment reference is rejected. An operator who receives a differently named provider secret maps it to the role's approved name outside the harness. There is no lookup chain.

The non-empty value is read from `ExecutionRequest.environment` immediately before each request, placed only in the controller-side Authorization header, then released. The executor ignores every other request environment value. It does not call the local-Codex environment builder and passes no host credential or ambient environment variable into Stirrup history or Apptainer.

The credential value never enters the frozen config, config serialization, a digest, `repr`, logs, failure codes, result metadata, diagnostics, or candidate data. Preflight checks only whether the approved process-environment entry is present and non-empty and stores no value; `execute()` repeats that check against `ExecutionRequest.environment`. `none` sends no Authorization header and must be explicit. Arbitrary headers, userinfo, URL query/fragment, inline API keys/tokens, templated URLs, query-key authentication, and percent-encoded URL delimiters are rejected.

`base_url` is parsed and canonicalized once as an API root: HTTPS is required except for a literal IPv4 or IPv6 loopback address used by tests; userinfo, query, fragment, dot segments, encoded slash/backslash, and an empty host are invalid. Its path is preserved after removal of one trailing slash. The policy URL is constructed by appending the literal `/chat/completions`; URL joining or caller-supplied endpoint paths are forbidden. Schema v1 makes exactly one policy operation, `POST <base_url>/chat/completions`.

The raw config source contains environment references, never credential values, so hashing its exact bytes is safe. Validation errors name fields and stable codes without echoing field values. The resolved frozen config uses redacted credential wrappers (`repr=False`) and accepts no arbitrary dict of environment variables.

`system_prompt` is inline so its exact UTF-8 bytes are covered by the source hash. The effective executor user prompt remains exactly `TaskSpec.prompt`; no hidden GDPval prompt/template is added. `skip_input_file_listing=True` is fixed so Stirrup does not silently add a second task/file prompt. Benchmark `execution_task()` owns any neutral file listing. `tool_response_as_user=True` is a versioned executor behavior.

The production v1 sandbox kind is Apptainer only. Test code may inject a fake/local `SandboxFactory` through a private constructor seam; no JSON value selects it. The configured SIF must be a regular non-symlink file and match `image_sha256`. Dynamic provider class names, arbitrary mounts, raw shell fragments, arbitrary env passthrough, and benchmark-selected containers are not accepted.

Network policy comes from the generic executor constructor/CLI, not a benchmark name. With network disabled, the runtime adds Apptainer's `--net --network none` arguments and the supported preflight probe must demonstrate failed egress; if the installed runtime cannot establish that namespace, preflight fails closed. With network enabled, those arguments are omitted and Apptainer may use host networking for code invoked inside the sandbox. Schema v1 accepts only `web.kind="disabled"` and exposes no host web-search tool. If AA-v2 requires Tavily-equivalent search, PR08/PR10 must name and test a separate generic capability using the common request transport, one approved credential reference, typed failures, and no rotation/fallback before deleting the legacy route. It is not smuggled into PR07.

### 3.1 Role containment seam

PR07 consumes the frozen generic policy types from `eval_harness.execution_policy`: `WorkspaceAccess`, `RootDenyRolePolicy`, `RolePolicyRequest`, and `RolePolicyPreflightResult`. It does not call the Codex-specific override/probe functions. `StirrupExecutor` accepts a `RootDenyRolePolicy` at construction and schema v1 requires:

- `workspace_access=WorkspaceAccess.READ_ONLY`; outputs use the separately assigned deliverables/output roots;
- `web_search_enabled=False`;
- `network_access_enabled` exactly equal to the executor's generic network flag; and
- the singleton role auth allowlist described above for bearer auth, or an empty tuple for `auth.mode="none"`.

The no-model containment API used by PR09 is exact:

```python
def preflight_role_policy(
    self,
    *,
    policy_request: RolePolicyRequest,
    execution_request: ExecutionRequest,
) -> RolePolicyPreflightResult: ...
```

This is a `StirrupExecutor` method; it requires `policy_request.workspace == execution_request.workspace`, uses the executor's already parsed sandbox config, and runs the internal async probe once. It launches the real configured SIF with the same arguments as execution and proves that the staged copy inside `/workspace` is readable and writable, that the authoritative workspace plus assigned executor/deliverables/protected/unlisted sibling/source roots are absent, that sandbox-work is the sole controller host-root bind, that explicitly non-empty `runtime_read_paths` are read-only, that disallowed environment values are absent, and that network policy is effective. For contained Stirrup, `runtime_read_paths=()` unless a trusted path is demonstrably mounted. The policy credential is permitted for controller transport only and is deliberately absent inside the sandbox. PR09 evidence records canonical assigned workspace/executor/deliverables roots, policy revision, access/network fields, and literal allowed key names; operational environment values are redacted and excluded from all semantic hashes.

The production launch uses Apptainer containment flags including `--containall`, `--no-home`, `--cleanenv`, and `--no-mount home,cwd,hostfs,bind-paths`, sets subprocess `cwd` under `executor_dir`, and supplies only fixed safe container variables with no `APPTAINER_BIND`, `APPTAINER_BINDPATH`, or `APPTAINER_MOUNT`. Before launch, the controller makes a race-checked copy from read-only `input-stage` into `sandbox-work`; only `sandbox-work` is bound read/write at `/workspace`. This lets tools edit working copies while neither the assigned workspace nor `input-stage` is mounted. The configured SIF is the execution image, not a browsable host bind. The probe inspects its own mount table and rejects every controller-data mount other than `/workspace`; contained pseudo-filesystems and fixed runtime-generated identity/config files are not treated as role data roots. A failed mount-denial/environment/network probe makes preflight fail closed.

A fake/local `SandboxFactory`, disjoint directory spelling, or a fake-LLM `LocalCodeExec` session cannot produce protected-role containment evidence. Those tests prove adapter, session, transport, and artifact behavior only. `RolePolicyPreflightResult.ok=True` is eligible for PR09 only when the production `preflight_role_policy()` above completes against the pinned real Apptainer runtime and SIF in the supported job described in section 8.1. An unsupported host may run mock tests, but it cannot substitute a mock result, infer isolation from argv, or mark a Stirrup role protected.

## 4. Provider transport and async lifecycle

`eval_harness.executors.stirrup_runtime.StirrupProviderTransport` implements Stirrup's `LLMClient` protocol and calls `nemo_gym.server_utils.request`; it does not instantiate the OpenAI SDK client, `httpx.AsyncClient`, `requests`, or a second aiohttp session. The request is non-streaming JSON and is parsed with `NeMoGymChatCompletion.model_validate`. Only a 2xx body is JSON-decoded. The response context is always closed; non-2xx bodies are drained and discarded and are never attached to an exception or log.

Its upstream-facing surface is the exact structural protocol required by Stirrup 0.1.12:

```python
class StirrupProviderTransport:
    @property
    def model_slug(self) -> str: ...  # exact requested model alias

    @property
    def max_tokens(self) -> int: ...  # configured context_window_tokens

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: dict[str, Tool],
    ) -> AssistantMessage: ...
```

`generate()` alone serializes messages/tools, computes the configured budget, performs the one request with redirects disabled, validates the response, records bounded per-turn evidence, and returns the upstream message. Constructor inputs are the frozen provider/session config, exact requested model, role-scoped credential resolver, and monotonic deadline. No benchmark object, evaluator, arbitrary provider mapping, or output directory crosses this boundary.

Generation POSTs are not replayed after an uncertain connection failure. The shared boundary is frozen as `nemo_gym.server_utils.request(..., connection_attempts=1, attempts=1)` plus `async def close_client_session() -> None`. PR07 implements and directly tests those narrow `server_utils` additions; PR05 records the dependency and does not create another transport/session helper. Existing callers that omit the new keyword-only counts retain the current `MAX_NUM_TRIES` and connection-retry defaults. The existing private `_max_connection_retries` argument remains accepted with its old meaning and is mutually exclusive with `connection_attempts`. Both new count parameters mean total attempts, including the initial request, reject booleans/non-positive values, and are forwarded unchanged through the tracing wrapper. Stirrup always passes one for both, so every connection/general exception exits after the initial attempt. Boundary tests pin this off-by-one behavior.

The transport does not call `raise_for_status`, because that helper retains an upstream body in `ClientResponseError`. It sets `allow_redirects=False` and maps status directly after draining. HTTP 429 becomes one typed quota failure; 5xx becomes one typed transport failure; 3xx and 4xx are never followed or retried. There is no endpoint, API, cloud, model, reasoning, auth, or request-body fallback. Judge transports remain behind PR05's `JudgeRuntime` and do not import this Stirrup transport.

The generic executor remains synchronous. Each `execute()` calls `asyncio.run()` once for the full Stirrup session. Every policy request in that session shares the common NeMo aiohttp singleton. In the coroutine's `finally`, after sandbox/session cleanup, it awaits `server_utils.close_client_session()` on the loop that created the session; the helper closes the `ClientSession`, clears client/debug state, and is idempotent when no client exists. The existing synchronous process-exit hook remains compatible for long-lived server callers. This prevents a session created on task 1's loop from being reused on task 2's closed loop. Two sequential executor-task tests prove this lifecycle. Calling synchronous `execute()` from a thread with an already-running event loop fails before a coroutine is constructed, using the stable code `stirrup.event_loop_active`; the generic CLI never does so.

The overall `ExecutionRequest.timeout_seconds` bounds session plus cleanup against one monotonic absolute deadline. The executor reserves `min(10 seconds, timeout_seconds / 10)` for cleanup and gives provider calls only the remaining session deadline. On expiry, the runtime cancels the session, closes tool providers, terminates the Apptainer process group, escalates to group kill at half the reserve, waits within the remainder, removes temporary staging, and closes the aiohttp client. Failure to reap is `stirrup.sandbox_process`; it is never reported as a clean timeout. No background Ray future, child/grandchild process, or async task survives the result.

## 5. Stirrup session and output recovery

The runtime constructs upstream Stirrup 0.1.12 `Agent` directly around the local `LLMClient`. It does not subclass by assigning `__class__`, monkey-patch module globals, or import legacy `NeMoAgent`. The measured compatibility layer serializes each tool result with role `user` in the in-memory agent history, then restores it to the required `tool` role with its exact `tool_call_id` only in the provider-bound wire payload. This ports the observed provider behavior without changing Stirrup globally. Tool-argument validation returns a bounded field/type summary to the model and never includes a submitted argument preview, path value, prompt, or exception string.

The runtime passes a fresh typed Apptainer provider and explicit finish tools to `Agent`. `finish_mode="coercing"` exposes a local `COERCING_FINISH_TOOL`; `finish_mode="coercing-with-abandon"` also exposes a local `ABANDON_FINISH_TOOL`. The coercer accepts only a JSON list of strings or the one characterized JSON-string encoding of such a list and validates every result; it does not guess comma-separated paths. This is a generic, hashed session choice rather than `is_gdpval`. An abandon call is a valid no-deliverable model outcome.

Fixed upstream session options are part of runtime version 1: `resume=False`, `cache_on_interrupt=False`, `clear_cache_on_success=True`, `output_dir=None`, `input_files=None`, `skills_dir=None`, `recover_from_context_overflow=False`, `context_summarization_cutoff=1.0`, `turns_remaining_warning_threshold=0`, `share_parent_exec_env=False`, and the configured `max_turns`/`system_prompt`. Validated provider usage must remain below `context_window_tokens`, so the cutoff cannot initiate a summary turn. A silent typed `AgentLoggerBase` implementation records only bounded counters and stable diagnostics under `executor_dir`; Stirrup's rich console logger is not used. Input staging is uploaded by the typed sandbox provider during its own enter lifecycle, so Stirrup does not generate a file listing or flatten inputs. Output recovery happens inside the active `async with agent.session(...)` block before provider teardown. Cache, resume, subagents, automatic summarization, context-overflow retries, and upstream automatic output copying are disabled.

The dynamic completion budget is retained without fallback:

```text
remaining = context_window_tokens - counted_input_tokens - completion_token_buffer
if remaining < minimum_completion_tokens: fail before provider call
max_completion_tokens = min(remaining, maximum_completion_tokens)
```

The serialized messages and serialized tool schemas used for counting are the ones sent on the wire. The configured tokenizer/counting method is used once; the current cascade through chat-template, JSON, and character estimates is removed from the new route. A length finish with valid typed content remains a valid turn and the agent may continue until finish/max-turn/timeout.

The non-streaming request body has one closed shape: `model`, `messages`, `temperature`, `top_p`, `max_completion_tokens`, `chat_template_kwargs: {"enable_thinking": <bool>}`, plus `tools` and `tool_choice: "auto"` when tools exist. The direct transport expands the legacy SDK's `extra_body` behavior into that actual wire field and accepts no arbitrary provider kwargs. It supplies the remaining wall deadline as aiohttp timeout outside the JSON body. A mock-provider golden fixture asserts the exact keys and values for every turn.

The transport keeps typed per-turn side evidence next to the `AssistantMessage`: exact provider `model`, whether `message.content` was a JSON string, that string when present, and bounded token counts. Exactly one choice, a supported finish reason, unique non-empty tool-call IDs, string function names/arguments, non-negative integer usage fields, and one identical non-empty provider model across all turns are required. Reasoning content may drive the agent but is never final text or persisted candidate evidence.

`ApptainerCodeExecToolProvider` is the one upstream compatibility class. It subclasses Stirrup 0.1.12 `CodeExecToolProvider` and implements its exact abstract lifecycle and primitives: `__aenter__`, `__aexit__`, `run_command`, `read_file_bytes`, `write_file_bytes`, `file_exists`, `is_directory`, and `list_files`. It overrides `save_output_files` only to return the safe nested one-to-one mapping below instead of upstream basename flattening. `stirrup_sandbox.py` owns frozen `SandboxLaunchRequest(sandbox_work: Path, deadline_monotonic: float, network_access_enabled: bool)` and the private alias `SandboxFactory = Callable[[ResolvedSandboxConfig, SandboxLaunchRequest], CodeExecToolProvider]`. The public executor accepts that factory only through a private constructor seam for deterministic unit tests; production construction always supplies `ApptainerCodeExecToolProvider`, and the JSON schema cannot select another class.

The adapter creates fresh executor-private `input-stage`, `sandbox-work`, and `output-stage` roots. It copies the execution view to `input-stage`, excluding the assigned `deliverables_dir`, then initializes the writable `sandbox-work` copy before launch. Model code never operates on authoritative snapshot/workspace inputs. The measured sandbox provider launches Apptainer with `asyncio.create_subprocess_exec()` and a typed argument tuple, a fresh process session/group, `--containall`, `--no-home`, `--cleanenv`, `--no-mount home,cwd,hostfs,bind-paths`, the configured working directory, a contained home, and only the writable executor-private sandbox-work bind. It does not invoke a host shell to construct or launch Apptainer, inherit ambient environment, expose the host workspace/input stage, or accept arbitrary mounts. Code requested by the model is still the explicit `code_exec` tool payload interpreted by the persistent shell inside the container. Timeout/cancellation sends termination to the process group, waits a bounded interval, escalates to kill, waits again, and reports cleanup failure without leaving a child.

`output-stage` contains only files recovered from `sandbox-work` by a successful finish. Bounded session counters, token counts, finish reason, bounded stderr, and patches may remain under `executor_dir` as secret-safe runtime diagnostics and never enter deliverables. Full prompts, provider bodies, Authorization headers, tool argument payloads, file contents, and raw transcripts are not persisted.

Finish paths are converted to logical POSIX paths only if they are relative to the configured sandbox working directory or already safe relative paths. Reject absolute paths outside that root, `..`, `.`, empty components, backslashes, drive prefixes, NULs, non-NFC names, symlinks, irregular files, exact duplicates, case-fold/Unicode collisions, and file/directory prefix collisions. Preserve nested paths; `a/report.txt` and `b/report.txt` remain distinct. Never search by basename or recursively guess a source.

The measured sandbox provider's recovery method returns an exact one-to-one typed `SavedFile` mapping and preserves normalized relative paths. The finish tool checks that every declared source exists as a regular non-symlink file while the sandbox is active; a failed declaration is returned to the model as a bounded tool validation result, allowing another turn. Exhausting turns without a valid finish becomes `NO_DELIVERABLE`. Once finish succeeds, a missing file, changed identity/content during recovery, unsafe path, ambiguous mapping, unexpected staged file, or host copy failure is a systemic integrity/process failure. The adapter discards the entire staged set on such failure. After the full set validates, it copies with exclusive creation into the initially empty assigned deliverables directory and fsyncs files and directories. PR02c's accepted public artifact-path validator is reused. If it is still private after rebase, extract only that validator for CandidateBundle and Stirrup with all existing candidate tests unchanged; do not maintain two divergent path policies.

The runtime returns a frozen typed outcome, not a NeMo `Response` payload:

```python
@dataclass(frozen=True, slots=True)
class StirrupSessionOutcome:
    finish: Literal["finish", "abandon", "max_turns"]
    final_text: str | None
    artifact_paths: tuple[str, ...]
    model_id: str
    provider_request_count: int
```

`final_text` is the last provider assistant message's `content` only when the response schema supplied a JSON string, including `""`; it is `None` when content was absent/null or no valid finish occurred. The provider parser must retain that presence distinction because Stirrup normalizes content internally. Finish `reason` is bounded executor-private diagnostic context, never candidate text. Artifact bytes are never decoded into final text. Random response/message IDs, tool outputs, and full transcripts are not candidate evidence.

## 6. Failure map

All codes are static and contain no exception text, provider body, URL, path, task prompt, or secret. The accepted `ExecutionResult` contract currently requires any failed execution to have `FailureImpact.RUN`; PR07 follows that rule and the common runner stops remaining tasks. Model non-completion is represented as `NO_DELIVERABLE`, so a weak model does not become a systemic executor failure.

| Condition | Status | `FailureKind` | Stable code |
|---|---|---|---|
| Missing bearer value at execute | `FAILED` | `AUTH` | `stirrup.provider_auth_missing` |
| Provider HTTP 401/403 | `FAILED` | `AUTH` | `stirrup.provider_auth_rejected` |
| Provider HTTP 429 | `FAILED` | `QUOTA` | `stirrup.provider_quota` |
| Provider HTTP redirect | `FAILED` | `PROTOCOL` | `stirrup.provider_redirect` |
| Provider rejects request (other 4xx) | `FAILED` | `PROTOCOL` | `stirrup.provider_request_rejected` |
| Invalid JSON/schema, zero/multiple choices, invalid tool call, missing/mixed returned model | `FAILED` | `PROTOCOL` | `stirrup.provider_response_invalid` |
| Tokenizer snapshot/load/template/count failure | `FAILED` | `PROTOCOL` | `stirrup.tokenizer_invalid` |
| Context budget below configured minimum | `FAILED` | `PROTOCOL` | `stirrup.context_budget_exhausted` |
| Connection/DNS/TLS failure or provider 5xx | `FAILED` | `TRANSPORT` | `stirrup.provider_unavailable` |
| Wall-clock deadline | `TIMED_OUT` | `TIMEOUT` | `stirrup.session_timeout` |
| Keyboard interruption | `INTERRUPTED` | `INTERRUPTED` | `stirrup.interrupted` |
| Missing/wrong locked runtime dependency | `FAILED` | `PROCESS` | `stirrup.runtime_dependency` |
| Missing/invalid model, timeout, or assigned request root | `FAILED` | `INTERNAL` | `stirrup.execution_request_invalid` |
| Active event loop at synchronous entry | `FAILED` | `INTERNAL` | `stirrup.event_loop_active` |
| Role-policy mismatch or failed containment probe | `FAILED` | `INTEGRITY` | `stirrup.role_policy` |
| Apptainer/session startup or teardown failure | `FAILED` | `PROCESS` | `stirrup.sandbox_process` |
| Unsafe/colliding output, source mutation, ambiguous save mapping | `FAILED` | `INTEGRITY` | `stirrup.output_integrity` |
| Unexpected adapter invariant | `FAILED` | `INTERNAL` | `stirrup.internal` |

Preflight does not issue a policy request. It verifies strict config, exact source evidence, required auth presence, dependency/runtime versions, tokenizer availability/method, `apptainer` executable/version, SIF digest, working directory/readiness, and requested network-isolation support. Its `details` are stable and secret-free. `execute()` repeats security-critical checks against `ExecutionRequest.environment` and exact assigned paths to close time-of-check/time-of-use gaps.

## 7. Code shape and bounded change list

New measured modules:

| Path | Owned behavior |
|---|---|
| `eval_harness/executors/stirrup.py` | Public executor, preflight, sync/async boundary, staging/recovery, result/status/failure mapping. |
| `eval_harness/executors/stirrup_config.py` | Strict JSON schema, duplicate-key rejection, source hash, frozen resolved config, env-reference validation. |
| `eval_harness/executors/stirrup_runtime.py` | Common-aiohttp `LLMClient`, typed provider parsing/model evidence, exact token budget, wire-role serialization, local finish tools, explicit upstream `Agent` session, silent logger, and typed outcome. |
| `eval_harness/executors/stirrup_sandbox.py` | Typed Apptainer tool provider, input upload, argv/process-group/network lifecycle, bounded teardown, safe nested-output validation and one-to-one recovery. |

Narrow generic changes:

| Path | Change |
|---|---|
| `eval_harness/executors/base.py` | Add fixed `ExecutionConfigurationEvidence` and optional fields. |
| `eval_harness/provenance.py` | Serialize its exact fixed shape. |
| `eval_harness/candidate_bundle.py` | Add fixed executor configuration evidence and bump strict schema once. |
| `eval_harness/runner.py` and PR02c integration sites | Hash/match preflight/result configuration evidence and carry it into the sealed bundle. |
| `eval_harness/executors/registry.py`, `eval_harness/cli.py` | Construct Stirrup explicitly and validate config/model arguments. |
| `eval_harness/benchmarks/registry.py` | Update informational executor support only where the existing typed capability comparison succeeds; no Stirrup code receives a benchmark name. |
| `eval_harness/execution_policy.py` | Consume its accepted `RootDenyRolePolicy`/request/result types unchanged; do not duplicate or weaken the generic policy contract. |
| `nemo_gym/server_utils.py` | Named request-attempt controls and same-loop async singleton close/reset with unchanged existing defaults. |
| `tests/unit_tests/test_server_utils.py` | Direct off-by-one attempt-count, owning-loop close/reset, and existing-default regression tests for the shared helper. |

The new executor imports upstream `stirrup` and the measured modules above only. It does not import `responses_api_agents.stirrup_agent.*`; PR07 therefore makes no behavioral source edit to `nemo_agent.py`, `nemo_client.py`, `stirrup_utils.py`, `finish_tool_coercing.py`, `apptainer_provider.py`, or `tavily_search.py`. Their characterized mechanics are ported narrowly and tested through the measured adapter. If implementation evidence shows a legacy source edit is unavoidable, it returns to Sol for a typed interface and direct test expansion rather than moving control logic outside coverage.

Dependency/CI files may change only to install and validate the exact host runtime: `pyproject.toml`, `uv.lock`, `responses_api_agents/stirrup_agent/requirements.txt`, `.github/workflows/eval-harness-ci.yml`, and the relevant dependency-audit configuration. Do not copy the document/PDF/ML packages advertised inside the GDPval SIF into the host group.

`app.py`, `task_strategy.py`, `tasks/gdpval.py`, `file_reader.py`, `client.py`, Ray orchestration, resources servers, evaluator code, GDPval shell scripts, recipes, and scoring configs are not implementation surfaces for the new route. PR07 must not hide edits to those components as adapter work.

## 8. Deterministic tests and exact expectations

All adapter/control branches remain under the existing `source=eval_harness` coverage measurement and the exact 96.00% gate. No omit rule, pragma, threshold, or source scope changes. The shared `server_utils` additions receive direct unit tests in addition to measured harness integration.

Add the following `unittest`-compatible harness tests and typed fixtures:

The implementation places the cases in `tests/harness/test_stirrup_config.py`, `tests/harness/test_stirrup_executor.py`, `tests/harness/test_stirrup_runtime.py`, `tests/harness/test_stirrup_sandbox.py`, `tests/harness/test_stirrup_dependency_compatibility.py`, and `tests/harness/test_stirrup_supported_runtime.py`. Shared transport cases extend `tests/unit_tests/test_server_utils.py`.

| Test | Required assertion |
|---|---|
| Strict config round trip | Exact raw-byte SHA, fixed evidence, exact Apptainer 1.5.3 version, and duplicate/unknown/nonfinite/inline-secret/query/userinfo/encoded-delimiter/unapproved-env-reference rejection; no rejected value appears in error text. Candidate schema is exactly 2 and nested config schema is exactly 1. |
| Auth preflight/header | Application accepts only `MODEL_API_KEY` and builder only `BUILDER_MODEL_API_KEY`; preflight fails when its scoped ambient value is absent and makes zero requests. Mock server sees exact `Authorization: Bearer <fixture secret>` at execute; `none` sees no Authorization header. Fixture secret is absent from result, run metadata, CandidateBundle bytes, config/digest inputs, sandbox environment, stdout/stderr, and exception text. |
| Endpoint ownership | Mock server accepts only `POST /v1/chat/completions`; every other path fails the test. Captured requests contain no `/verify`, `/run`, resource-server name, rubric, reference answer, judge flag, or benchmark name. |
| Real Stirrup session with mock provider | Typed response 1 calls `code_exec` to create `nested/result.txt`; response 2 calls `finish`. Actual locked Stirrup `Agent` and measured sandbox interface recover exact bytes/nested path, last assistant content, and provider-returned model ID. The prompt bytes match `TaskSpec.prompt`; no real model service is used. |
| Text-only/artifact-only/empty/abandon/max-turn | Exact status/channel table in section 2; no fabricated text and no file-content concatenation. |
| Artifact safety | Preserve duplicate basenames in different directories; reject traversal, outside absolute paths, symlink, irregular file, Unicode/casefold and prefix collisions; bookkeeping never appears. |
| Provider schema | Valid fixture is parsed through `NeMoGymChatCompletion`; invalid JSON, empty/two choices, malformed tool arguments, omitted model, and mixed per-turn model produce `PROTOCOL` and zero candidate channels. |
| Failure table | Redirect, 401/403, 429, other 4xx, 5xx/connection, wall timeout, sandbox start/teardown, and output-integrity cases produce the exact status/kind/code and no diagnostic/secret. No alternate request follows. |
| Systemic stop | A two-task common-runner fixture receives auth, quota, protocol, and timeout failures on task 1; task 2 is never materialized/executed/evaluated and provider count stays one. |
| Sequential lifecycle | Two successful tasks in one run use valid common aiohttp sessions despite separate synchronous `execute()` calls; no unclosed-session warning remains. |
| Request attempts | Connection, disconnect, and general failure fixtures each observe exactly one request with `connection_attempts=1, attempts=1`; omitted arguments preserve existing server-utils retry behavior. |
| Configuration matching | Runner rejects preflight/result evidence mismatch before sealing/evaluation; run and CandidateBundle contain identical fixed evidence. |
| Strict bundle migration | Schema 2 reads; schema 1, missing `configuration`, extra fields, bad digest, and altered configuration evidence fail closed in every reader/resume path. All existing executor fixtures explicitly contain null configuration. |
| Neutral fourth task | A local `Benchmark` fixture named `neutral-fourth` supplies a prompt and `task_inputs/input.txt`; the same registered Stirrup executor/common runner/mock provider produces and seals a bundle without any core or executor benchmark-name condition. Mock endpoint still observes only chat completions. |
| Dependency absent | Registry listing works without the source-checkout dependency group; selecting Stirrup fails preflight with a stable dependency detail before any network/model call. |
| Pillow/MoviePy override | Actual Stirrup image decode/downscale/re-encode and video decode/downscale/re-encode/reopen calls pass under Pillow 12.3.0 and MoviePy distribution 2.2.1; exact installed versions are asserted. |
| Local tokenizer | Exact Transformers/tokenizers/Jinja versions load a digested three-file local snapshot with network access disabled and render/count serialized messages plus tool schema. Mutation, missing template, remote-only ID, wrong revision/hash, or load/template failure makes zero provider calls and never selects byte counting. |
| Network policy | Disabled mode omits web tools and uses tested Apptainer no-network arguments or fails preflight; enabled mode is explicit. No test claims no-network merely because the provider is mocked. |
| Role policy | Application config cannot name `BUILDER_MODEL_API_KEY`; builder config cannot name `MODEL_API_KEY`; extra allowlist names fail. The separate no-model production `preflight_role_policy()` probe sees the staged copy through the sole sandbox-work bind, cannot see authoritative workspace/executor/deliverables/protected/sibling/repository-source roots, sees no host credential or disallowed environment value, and proves the configured network policy. Only this real-container result can report protected-role eligibility; canonical root/policy evidence contains no credential values. |
| Supported sandbox lifecycle | Dedicated supported CI uses the production measured Apptainer provider and the section 8.1 SIF. A fake local policy endpoint plus real upstream Agent proves successful artifact recovery separately from the no-model containment probe. Cancellation/timeout after a child and grandchild start proves both PIDs are absent through `/proc/<pid>` and `os.kill(pid, 0)`, binds/stages are removed, and the aiohttp singleton is closed. It does not depend on host `ps`. No process or containment test is skipped or deselected. |

Fixtures belong under `tests/harness/fixtures/executor_protocol/stirrup/` and contain only synthetic keys marked for the repository's secret scanner. Actual runtime integration must use the installed Stirrup package, not a fake module tree; narrow backend injection is used only for filesystem/failure unit cases.

### 8.1 Supported Apptainer provisioning and containment gate

The dedicated `stirrup-supported-runtime` job runs on Linux x86-64 with a runner that permits the setuid Apptainer network namespace. It installs no floating Apptainer package. The runtime is Apptainer 1.5.3, tag object `12054fb7faf9414667f42b6daf3f5c2259db46d0`, commit `6a76317a87c4eae10f52c7805965756a919291d7`, tree `9e9486c6facce4805dd11d70ee1fb1331ca0594b`. Provisioning downloads these two official release artifacts, verifies their bytes before installation, installs both local files, and asserts `apptainer version` is exactly `1.5.3`:

| Artifact | SHA-256 |
|---|---|
| `apptainer_1.5.3_amd64.deb` | `82b0bdddf459087d202383360b8318d526ad6826c748a2f669913cc6aef9ee40` |
| `apptainer-suid_1.5.3_amd64.deb` | `118d40f0b94225a078c769422c98be72a98fb2a6423616481eb34a64cfc7b222` |

The workflow spells the download, verification, and installation directly:

```text
curl --fail --location --proto '=https' --tlsv1.2 -o apptainer_1.5.3_amd64.deb https://github.com/apptainer/apptainer/releases/download/v1.5.3/apptainer_1.5.3_amd64.deb
curl --fail --location --proto '=https' --tlsv1.2 -o apptainer-suid_1.5.3_amd64.deb https://github.com/apptainer/apptainer/releases/download/v1.5.3/apptainer-suid_1.5.3_amd64.deb
printf '%s  %s\n' 82b0bdddf459087d202383360b8318d526ad6826c748a2f669913cc6aef9ee40 apptainer_1.5.3_amd64.deb 118d40f0b94225a078c769422c98be72a98fb2a6423616481eb34a64cfc7b222 apptainer-suid_1.5.3_amd64.deb | sha256sum --check --strict -
sudo apt-get install --yes ./apptainer_1.5.3_amd64.deb ./apptainer-suid_1.5.3_amd64.deb
test "$(/usr/bin/apptainer version)" = '1.5.3'
test "$(stat --format='%U:%G:%a' /usr/libexec/apptainer/bin/starter-suid)" = 'root:root:4755'
```

The job also requires `/usr/libexec/apptainer/bin/starter-suid` to be owned by `root:root` with mode `4755`, requires the installed `none` CNI definition, records the runner image identifier, kernel, Apptainer config, and installed-package manifest as artifacts, and fails setup if those conditions are unavailable. It does not install from a PPA, apt package name, mutable latest URL, or alternate Singularity binary.

The committed `tests/harness/fixtures/executor_protocol/stirrup/containment-v1.def` has these exact LF-terminated UTF-8 bytes and SHA-256 `ebff319e990b886400098f2e36411ddca6f6585c7d73e3f2d32e2dec80684a2a`:

```text
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

Bootstrap: docker
From: docker.io/library/busybox@sha256:7a3ebe5bfd1a4a19797d20b0c0bb39d44393e9a03fd852c0865b0f540d868df0

%labels
    org.opencontainers.image.title pr07-containment-v1
    org.opencontainers.image.base.digest sha256:7a3ebe5bfd1a4a19797d20b0c0bb39d44393e9a03fd852c0865b0f540d868df0
```

That base is the Linux/amd64 OCI manifest, not a mutable tag; its parent multi-platform index is `sha256:9db7b59979c38555a39def84a31fb98b5296952f9e3afd4f6f11f05b07adfab0`. Provisioning builds the definition twice with `SOURCE_DATE_EPOCH=0` under Apptainer 1.5.3, requires the two SIF SHA-256 values and bytes to match, verifies the embedded label/base digest, and then uses the first read-only SIF. The strict test config receives that exact computed SIF SHA-256 before it is parsed; the hash and build transcript are retained as CI artifacts. Apptainer 1.5 added `SOURCE_DATE_EPOCH` support for reproducible SIF creation. OCI/deb downloads occur only in the provisioning step; all tests execute the local verified SIF and local mock endpoint.

```text
mkdir -p ci-artifacts/stirrup-runtime
printf '%s  %s\n' ebff319e990b886400098f2e36411ddca6f6585c7d73e3f2d32e2dec80684a2a tests/harness/fixtures/executor_protocol/stirrup/containment-v1.def | sha256sum --check --strict -
sudo env SOURCE_DATE_EPOCH=0 /usr/bin/apptainer build --force ci-artifacts/stirrup-runtime/containment-a.sif tests/harness/fixtures/executor_protocol/stirrup/containment-v1.def
sudo env SOURCE_DATE_EPOCH=0 /usr/bin/apptainer build --force ci-artifacts/stirrup-runtime/containment-b.sif tests/harness/fixtures/executor_protocol/stirrup/containment-v1.def
cmp ci-artifacts/stirrup-runtime/containment-a.sif ci-artifacts/stirrup-runtime/containment-b.sif
sha256sum ci-artifacts/stirrup-runtime/containment-a.sif > ci-artifacts/stirrup-runtime/containment-v1.sif.sha256
chmod 0444 ci-artifacts/stirrup-runtime/containment-a.sif
```

The containment case calls the production `StirrupExecutor.preflight_role_policy()` with bearer auth present only in the controller, network disabled, `runtime_read_paths=()`, and canonical temporary workspace/executor/deliverables roots. It creates fixed sentinels in the authoritative workspace, a protected repository/source root, and an unlisted sibling. Inside the real SIF, the production sandbox provider must read only the staged copy, write only `/workspace`, fail to resolve every host sentinel path, show through `/proc/self/mountinfo` that no other controller-data root is mounted, omit the credential and a disallowed host variable from `env`, expose no non-loopback route, and fail to contact a host loopback listener; the listener must observe zero connections. The result must contain the exact policy revision and stable success detail codes, with literal allowlist key names but no values. The separate production cancellation case starts a child and grandchild, then verifies their absence without `/usr/bin/ps` after cancellation and timeout.

Any missing version, digest mismatch, non-reproducible SIF, failed prerequisite, unexpected mount/environment/connection, surviving PID, or inability to create the `none` network makes this required job fail. Its pytest invocation has no conditional skip, xfail, deselection, marker exclusion, or fake-provider replacement for containment. Mock-only jobs still exercise the same executor and shared HTTP lifecycle on ordinary hosts, but their result is never PR09 protection evidence.

Required validation on the implementation head:

```text
uv lock --check
uv sync --locked --extra dev --group stirrup-executor
uv run --no-sync mypy --strict --explicit-package-bases --show-error-codes eval_harness tests/harness scripts/gdpval_run_metadata.py scripts/ci/run_eval_harness_coverage.py scripts/update_env_list.py tests/test_update_env_list.py tests/unit_tests/test_update_env_list.py tests/unit_tests/test_hf_utils.py
uv run --no-sync coverage erase --rcfile=config/eval-harness-coveragerc
uv run --no-sync coverage run --rcfile=config/eval-harness-coveragerc scripts/ci/run_eval_harness_coverage.py
uv run --no-sync coverage combine --rcfile=config/eval-harness-coveragerc
uv run --no-sync coverage json --rcfile=config/eval-harness-coveragerc --pretty-print -o ci-artifacts/harness-tests/coverage.json
uv run --no-sync python scripts/ci/run_eval_harness_coverage.py --check-summary ci-artifacts/harness-tests/coverage.json
uv run --no-sync coverage report --rcfile=config/eval-harness-coveragerc
uv run --no-sync pytest tests/unit_tests/test_server_utils.py tests/harness/test_stirrup_dependency_compatibility.py
uv run --no-sync pytest tests/harness/test_stirrup_supported_runtime.py
uv export --locked --extra dev --group stirrup-executor --no-emit-project --output-file ci-artifacts/dependency-audit/requirements.txt
uvx --from "pip-audit==2.10.1" pip-audit --require-hashes --disable-pip --strict --format json --aliases --output ci-artifacts/dependency-audit/pip-audit.json --requirement ci-artifacts/dependency-audit/requirements.txt
uvx --from "pre-commit==4.3.0" pre-commit run --all-files --show-diff-on-failure --color=always
```

The existing reusable copyright and secrets-detector workflows remain required checks, and dependency annotations/attributions are reviewed with the exact lock. Every eval-harness test/type-check sync and the dependency export/audit include the locked Stirrup group so runtime dependencies stay within the CVE gate. The actual-session mock test cannot skip. `server_utils.py` runs its direct unit suite. A dedicated supported-runtime job runs `tests/harness/test_stirrup_supported_runtime.py` with real Apptainer/process reaping and no test selector that omits, skips, or deselects those cases. No CI test makes a real model, paid judge, Tavily, or public-network call.

## 9. Exact legacy retain/delete map

PR07 leaves the legacy route operational only for migration comparison. The new executor never imports `responses_api_agents.stirrup_agent.app`. PR10 deletes the route after PR07/08 acceptance using this map.

Narrowly ported mechanics keep their NVIDIA copyright/SPDX provenance and any required `ATTRIBUTIONS.md` entry. The retained assets after PR10 are the measured `eval_harness/executors/stirrup*.py` implementation, generic shared transport changes, exact dependency group/lock, accepted tests/fixtures, and the hashed SIF definition/image. The old app/server/client/task-strategy package is not retained as a second execution path.

| Existing item | PR07 destination / final action |
|---|---|
| `app._run_stirrup_agent` session construction | Port the minimum neutral session sequence into measured `stirrup_runtime.py`; no task metadata, Ray, persistence, judging, or file rendering. Delete old copy with app in PR10. |
| `app.run_stirrup_agent_remote` and Ray decorator/runtime env | Not reused. Delete in PR10. |
| `app.responses()` | Do not wrap or call. Delete with server route in PR10. Its `config.task == "gdpval"`, `is_gdpval`, reference download, prompt wrapping, dummy key, fallback output, and Ray timeout are all replaced by the generic contracts. |
| `app.run()` | Do not wrap or call. Delete in PR10. Move evaluation/re-evaluation/resume to common runners; delete `/verify`, `judge_only`, `execute_only`, `rerun_incomplete`, reuse, seed-session, reward and failure-payload controls here. |
| `_verify_cache_path`, `_read_cached_verify`, `_write_cached_verify`, `_classify_verify_failure` | Evaluation journal/cache is owned by PR05/06/08. Delete from generator in PR10. |
| `_task_finished`, `finish_params.json`, history pickle/JSON, task/repeat persistence | Common run/CandidateBundle journal owns completion. Keep only executor-private diagnostics needed for debugging; delete these as candidate/cache semantics in PR10. |
| `_TASK_METADATA_FIELDS`, `TaskStrategy`, `_TASK_REGISTRY`, `GDPValTask` prompt/provider/metadata hooks | Benchmark adapter and profile own the needed data. Delete generator registry/hooks in PR10. Retain `_download_reference_files` only until its accepted benchmark-snapshot owner replaces the import, then delete/move it without changing generation. |
| `_build_gdpval_user_prompt`, `prompts/gdpval_user_prompt.txt` | GDPval `Benchmark.execution_task()` owns the effective user prompt. Delete legacy copy in PR10. |
| `file_reader.py` and `deliverable_content_blocks` | Evaluator-side artifact projection under PR06. Never use in generation. Delete old generator coupling in PR10; retain utility only at its evaluator destination if still required. |
| `nemo_agent.py` | Port only tool-result-as-user/history and provider-wire-role restoration into measured `stirrup_runtime.py`, without class reassignment or globals. Leave the legacy copy for comparison in PR07; delete the whole file with its old route in PR10. |
| `nemo_client.py` | Port exact budgeting intent and provider parsing into measured runtime with one configured tokenizer and common aiohttp. Do not port OpenAI-SDK/HTTPX ownership, character/tokenizer cascades, monkey patches, retries, or warning fallbacks. Leave the legacy copy in PR07; delete it in PR10. |
| `stirrup_utils.py` | Port provider-valid message serialization only. Do not port Responses-output conversion, deliverable-text/finish-reason concatenation, or random IDs. Delete the legacy file in PR10 after old-route callers are gone. |
| `finish_tool_coercing.py` | Port the characterized JSON-string-list coercion and generic abandon tool into measured runtime with typed bounded validation. Leave the legacy copy in PR07; delete it in PR10. |
| `apptainer_provider.py` | Port Apptainer/code-tool lifecycle into measured `stirrup_sandbox.py` with fixed construction, network enforcement, process-group cleanup and nested output mapping. Do not port dynamic class lookup, Ray serialization, arbitrary mounts, basename flattening, or ambient env passthrough. Leave the legacy copy in PR07; delete it in PR10. |
| `tavily_search.py` | Schema v1 fixes `web.kind="disabled"`, so the new route does not import or port this HTTPX/key-rotation provider. PR08/PR10 must name an accepted generic web owner if AA-v2 still requires it; after that owner lands, delete the legacy fallback/rotation implementation with the old route. |
| `client.py` | Old manual agent-server client is not used. Delete in PR10 with the server route. |
| Legacy Stirrup tests | Keep them unchanged for PR07 comparison. In PR10 delete tests of removed server/Ray/GDPval branches; retain or move only fixtures that independently verify the measured replacement. |
| `responses_api_agents/stirrup_agent/__init__.py` and package scaffolding | Delete in PR10 if no retained asset imports the package; do not leave an importable route stub. |
| `configs/stirrup_agent.yaml` mixed fields | Replace policy/session/sandbox/auth inputs with strict executor config. PR08 owns AA-v2 evaluator/profile fields. Delete `task`, resources server, datasets, persistence, execute/judge/rerun controls in PR10. |
| `scripts/gdpval_provider.sh`, old preflight/setup shell, recipes | Extract only values needed by typed config/profile and preflight. New executor never invokes them. Delete replaced entrypoints in PR10. |
| GDPval SIF definition/image | Retain as an explicit sandbox asset, referenced by path plus checked SHA-256; no executor benchmark branch. |

## 10. Dependency decision and gate

The accepted source-checkout dependency is a uv dependency group, not a published package extra:

```toml
[dependency-groups]
stirrup-executor = [
  "stirrup==0.1.12",
  "transformers==5.17.0",
  "jinja2==3.1.6",
]

[tool.uv]
override-dependencies = [
  # existing reviewed overrides,
  "pillow==12.3.0",
]
```

The group keeps generic installs and executor listing importable without Stirrup through lazy imports. CI, local implementation validation, lock export, CVE audit, and the dedicated runtime job must explicitly select `--group stirrup-executor`; documentation must not call this a pip extra or imply that a published wheel exposes it. The legacy resource requirement changes to the same exact `stirrup==0.1.12`, `transformers==5.17.0`, and `jinja2==3.1.6` pins and retains the reviewed `pillow==12.3.0` override. There is no alternate Stirrup/tokenizer/Pillow resolution or isolated-version fallback.

Version/source provenance is fixed:

| Item | Accepted evidence |
|---|---|
| Upstream | `ArtificialAnalysis/Stirrup` tag `v0.1.12`, commit `3e988e5a1729cea37e6484e5cab2ab0f9eae4ffb`, tree `3a68410fee63316f3efd1a4aede37228e6bc01e6` |
| Upstream metadata | `pyproject.toml` Git blob `adb60a96fc9b23d6327c7928c8e6cd565fe24e23`; version `0.1.12`, Python `>=3.12`, Python 3.13 classifier, MIT classifier |
| Release artifact | universal wheel `stirrup-0.1.12-py3-none-any.whl`, SHA-256 `caaaac871bffc5deae9fa10d1ccb8339b6533beb5d783bcc0bd14951a72245cc`; GitHub release and PyPI artifact hashes match |
| Resolver | uv `0.11.29`, CPython `3.13.14`, production registry, 336 locked packages; `uv lock` and offline `uv lock --check` passed |
| Tokenizer runtime | Transformers 5.17.0 wheel SHA-256 `78ec1ce21579b38dfb83950a0658cd119f87212a2fcfdff478096ce9d6c03801`; tokenizers 0.23.2; Jinja2 3.1.6 wheel SHA-256 `85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67` |
| Direct license metadata | Stirrup: MIT classifier/full license text; Transformers: Apache 2.0 metadata; tokenizers: Apache Software License classifier; Jinja2: BSD License classifier |
| Probe inputs | final temporary root `pyproject.toml` SHA-256 `d240708c3d552e2adda9bc69fa8e187dcfc10505253a2bfb6e75e2f15758180a`; `uv.lock` SHA-256 `ecfbd0280ec1c8138486fdadd6f3986af9318c1b114f5c5132e6ff45b2ff20f6` |
| Selected compatibility set | Stirrup 0.1.12, Transformers 5.17.0, tokenizers 0.23.2, Jinja2 3.1.6, Pillow 12.3.0, MoviePy distribution 2.2.1, OpenAI 2.44.0, Pydantic 2.13.4, trafilatura 2.2.0, charset-normalizer 3.5.1 |
| Hashed export/audit | exported requirements SHA-256 `cc9da9a2cc337656e2463b9134d0e2a199724337210e883ad73349089cccccff`; pip-audit JSON SHA-256 `e1a8e4bad4f26dc54380fbe89750e65894a2deef04a4ea45d4db387b3b4b9d66` |

MoviePy 2.2.1 declares `Pillow<12`, which conflicts with the repository's security-selected Pillow 12.3.0. An unmodified combined resolution therefore fails; resolving Stirrup alone by downgrading Pillow selects Pillow 11.3.0 and produced 35 known-vulnerability findings in the characterization. The explicit Pillow 12.3.0 override is a reviewed dependency-metadata exception, not a claim that upstream published compatible metadata and not permission to downgrade silently.

Compatibility proof uses actual affected calls. Under the final exact combined lock, Stirrup `ImageContentBlock` decoded, downscaled, and re-encoded a PNG to 8x6 through Pillow; Stirrup `VideoContentBlock` plus MoviePy/FFmpeg decoded, downscaled, and re-encoded an MP4 to 8x6 and reopened it with `VideoFileClip`. The installed MoviePy distribution is 2.2.1 even though its module-level `__version__` reports 2.1.2. A real upstream Stirrup `Agent` plus `LocalCodeExecToolProvider` ran two fake-LLM turns, created and recovered exact bytes from `nested/out.txt`, and proved provider cleanup.

Tokenizer proof also exercises the real affected path without a model call or network. Transformers 5.17.0 loaded a three-file local immutable `PreTrainedTokenizerFast` snapshot with `local_files_only=True` and `trust_remote_code=False`, rendered system/user messages plus a function-tool schema through `apply_chat_template(..., tools=..., tokenize=True, add_generation_prompt=True)`, and returned 40 token IDs. The characterized synthetic snapshot tree digest is `a3eb5acc198e62fb5262a9bd30966fc91d3b815a92636bd2b581ab358d6a0ef4`; implementation fixtures generate and verify their own reviewed bytes rather than depending on this temporary path. These are required CI fixtures, not import-only smokes and not real-model calls.

The exact combined validation selected root runtime, dev, and Stirrup group dependencies:

```text
UV_HTTP_CONNECT_TIMEOUT=120 UV_HTTP_TIMEOUT=120 uv lock
uv lock --check --offline
uv sync --locked --extra dev --group stirrup-executor
uv export --locked --extra dev --group stirrup-executor --no-emit-project --output-file <requirements>
uvx --from "pip-audit==2.10.1" pip-audit --require-hashes --disable-pip --strict --format json --aliases --output <audit-json> --requirement <requirements>
```

Sync/export passed. `pip-audit` 2.10.1 audited 180 dependencies with zero known vulnerabilities and no fixes. The implementation re-resolves on its exact accepted base; it must preserve the versions/hashes above or return to Sol with the new resolution and audit evidence. Repository license and attribution gates must also pass on the implementation head; the upstream MIT classifier/license is recorded but is not presented as a full transitive license audit.

The characterized upstream runtime selection passed 61 tests. One process-reaping test was locally deselected only because this managed container's `/usr/bin/ps` intermittently fails with `fatal library error, lookup self`. The dedicated supported CI job must run the actual no-model session, image/video compatibility, cancellation, timeout, and process-group reaping tests without deselection. A skip, xfail, conditional import, fake Stirrup module, or host-`ps` waiver in that supported job fails PR07.

The host group contains packages imported by the host Stirrup/session runtime. Document/PDF/data/ML tools advertised to the model remain in the hashed Apptainer image.

The remaining handoff values are operational inputs, not open architecture choices: the migration owner supplies the exact implementation base commit; PR08 supplies the AA-v2 policy endpoint, requested model alias, system prompt, tokenizer repository/revision/local snapshot digest, production SIF path/digest, and network policy; CI supplies a Linux x86-64 runner on which the section 8.1 pinned setuid runtime and `none` network can execute. The synthetic SIF source, build, and per-run exact image digest are already fixed in section 8.1. The only capability still requiring an owner before PR10 deletion is AA-v2 web search if its accepted profile requires it. PR07 schema v1 deliberately reports that capability unavailable.

No PR07 architecture or dependency decision remains open. Absence of a supported containment runner blocks acceptance of protected Stirrup roles; it does not authorize a mock substitute or weaken the contract.

## 11. Luna handoff

**Purpose:** implement one benchmark-neutral Stirrup policy-generation executor through the generic runner and CandidateBundle path.

**Target commit:** exact accepted PR06/PR02c-dependent head, supplied as a 40-character SHA by the migration owner before work starts.

**Allowed files:** only the measured/new modules, narrow generic/evidence/registry/CLI/shared-transport files, fixtures/tests, exact dependency/lock/audit files including the legacy resource requirements pin, and eval-harness validation workflow listed in section 7. Legacy Stirrup behavioral source edits, contract expansion, evaluator/profile work, or old-route deletion return to Sol.

**Inputs:** strict config source; neutral `TaskSpec` and `ExecutionRequest`; accepted `RootDenyRolePolicy`; role-scoped environment map with the one externally supplied credential; staged execution-view workspace; requested model/timeout/network flag.

**Outputs:** one typed `ExecutionResult`, secret-free fixed configuration/model/runtime evidence, final text and validated artifact tree, then one PR02c `CandidateBundle`. No score, reward, judgement, evaluator request, cached result, or provider transcript.

**Completion:** every test in section 8 passes using the exact lock, strict typing and 96% gate pass, dependency/security/license checks pass, the supported real-container reaping job passes without selection exceptions, and source inspection/readback proves the generic adapter has no dependency on `app.py`, GDPval task strategy, resources servers, Ray, `/run`, or `/verify`.

**Prohibitions:** no old shell/server wrapper; no POST to mixed legacy runner; no benchmark-name branch; no real model/judge/web call; no secret in config/hash/provenance/logs; no silent fallback/retry to another service/model/effort/counting method; no schema compatibility shim; no weakening CI/coverage; no broad NeMo framework rewrite; no old-route deletion until its behavior has an accepted owner and test.

## 12. Design evidence

The migration plan was read in full from `eval-harness-neutrality-migration-plan-2026-09-12.md`, SHA-256 `174f0b3d289ddffa9e9d617637e58dc2ad4198f2046a3064407ba41aa423885f`. Checkpoint instructions were read in full: `AGENTS.md` SHA-256 `c1e2971e6ecd1f51bb4d2c9c8e39146e06995dbeb177572bc0164df52070f60d`, `MIGRATION-WORKFLOW.md` SHA-256 `17c5c0713ccb15b3bcad2c30137408d7650bb4285bb99665632cca68f30e6094`, and `MIGRATION-STATE.md` SHA-256 `8f931086dfd7ccc52ef239868cc44d2a2a6d331fb65758e841f0de83dab1a47e`.

Inspected baseline blobs include:

| File | Git blob |
|---|---|
| `eval_harness/executors/base.py` | `b4d444ea6757adb65095f90262fd65859bd5741b` |
| `eval_harness/executors/registry.py` | `a1d8f6747f1f68521a4e5f480a51edef71a6023a` |
| `eval_harness/candidate_bundle.py` | `fdc93ec63392b7cad6a0750d454a54e3d3306d25` |
| `eval_harness/runner.py` | `fe21b9607221c570ee47e718235a654de83eb45d` |
| `eval_harness/benchmarks/gdpval.py` | `b227470b7629168dd0e539d85ec1d975a5774c87` |
| `responses_api_agents/stirrup_agent/app.py` | `9088789fa808d80d83698c74e245914b2ab60e2c` |
| `responses_api_agents/stirrup_agent/nemo_agent.py` | `20d83562a8ec3f7a2ec3014557e8ed84fd92ecc0` |
| `responses_api_agents/stirrup_agent/nemo_client.py` | `a7129ad2d9535616414d05961764bafe0890704b` |
| `responses_api_agents/stirrup_agent/client.py` | `d83a1e4cec6567ba0f93fdf25e911f0c3bd7078e` |
| `responses_api_agents/stirrup_agent/stirrup_utils.py` | `7ea191e74e89850e2183b4434d2914f353280988` |
| `responses_api_agents/stirrup_agent/apptainer_provider.py` | `aefd21cfae00cd33ceedb5c18c14c38fb904ad91` |
| `responses_api_agents/stirrup_agent/finish_tool_coercing.py` | `1bd9d6532688d3c5da1e9d1598838d5b62a3934e` |
| `nemo_gym/server_utils.py` | `714f883fed5ca8fccc85e1cb8d8906ce6846cccb` |
| `nemo_gym/openai_utils.py` | `aeb78ca6ee61a149146cbc6ddf10d6de6d1e7d5e` |
| `responses_api_agents/stirrup_agent/requirements.txt` | `42339fee6e525e55f066f54f99f674337b530c1e` |
| `responses_api_agents/stirrup_agent/overrides.txt` | `61b76ad1f35debca4ce1ac0e20bb2e65bc05beb7` |
| `responses_api_agents/stirrup_agent/task_strategy.py` | `6fdf07ed562e0041c110d2c6cbc88475c70f591a` |
| `responses_api_agents/stirrup_agent/tasks/gdpval.py` | `a62781e08fc19a0789a0e6bb85067d19bcec06c1` |
| `responses_api_agents/stirrup_agent/file_reader.py` | `892854920e45b8c8bba23a3e6a81745b88384193` |
| `.github/workflows/eval-harness-ci.yml` | `c07b9574ccb0747a5cd809c2c5b739a1dfd8c1ee` |
| `pyproject.toml` | `5d46297218daee3b3fe0ac5c8f9fa0407dd29421` |
| `uv.lock` | `d35adbb6a5792de03406fc3538f3f8acbaf7b344` |

Dependency characterization used only temporary source checkouts/venvs. The final root-resolution probe is identified in section 10. Its real fake-client session log SHA-256 is `3c1e454332f82644719699531acfbc052c726bbc00288a93a00d367e81d54c8b`; image/video log SHA-256 is `7dbf64734d6e01007be2b0950df3c93489af6c0da1d37fbb008e0ae949559139`. The local tokenizer fixture exercised files `chat_template.jinja`, `tokenizer.json`, and `tokenizer_config.json` and produced the tree digest recorded in section 10. No provider, model, judge, Tavily, or public inference endpoint was called.

Apptainer release/tag metadata and official artifact hashes were inspected for section 8.1. This managed local host had no installed Apptainer/Singularity runtime and could not create a mount namespace, so no local result is presented as containment evidence. That is why the real production probe is a mandatory failing gate on the explicitly supported CI runner rather than a local skip.

PR04 confirmed its grader isolation introduces no HTTP transport. PR05/PR02c froze `eval_harness.execution_policy` as the shared role-policy owner and confirmed `nemo_gym.server_utils.request(..., connection_attempts=1, attempts=1)` plus `close_client_session()` as the one shared HTTP/session seam; PR07 owns that narrow implementation and tests. PR06 keeps judge HTTP behind `JudgeRuntime` and introduces no competing transport. PR09 consumes PR07's contained role-policy probe and must not treat another executor's disjoint directories as equivalent OS containment.

This record is **saved design evidence** only. It has no production changes, no real-model validation, no Accepted status, and no claim that Gate A or Gate B passed.
