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
| `eval_harness` async Stirrup runtime | Build one Stirrup client/agent/session, call the configured OpenAI-compatible policy endpoint through `nemo_gym.server_utils.request`, run tools, capture the provider-returned model ID, and return a typed session outcome. |
| Reused NVIDIA Stirrup resources | `NeMoAgent` message-role behavior, explicit coercing finish tools, Apptainer code-exec lifecycle, and provider message serialization. These modules do not select a benchmark, resolve policy credentials, own timeout policy, classify harness failures, or persist candidate/run records. |
| Benchmark adapter | Canonical task, execution-view files, and any benchmark-specific user-prompt wrapper. GDPval sector/occupation/reference presentation stays here. |
| Evaluator | Rubric/reference projection, file rendering, pairwise judging, `/verify` replacement behavior, retries, votes, and metrics. |

Ray is not part of the generic PR07 route. The current generic runner is synchronous and task-sequential; distributing independent applications is an orchestrator concern. Apptainer remains the production code-execution isolation mechanism inside each Stirrup session.

## 2. Neutral contracts

`TaskSpec` remains exactly `{task_id, prompt}`. `ExecutionRequest` remains the neutral source of the effective task prompt, workspace, assigned deliverables directory, executor-private directory, requested model, wall-clock timeout, and environment. No provider, rubric, answer, judge, sector, occupation, benchmark name, reference URL, or cached judgement field is added to either type.

The executor is constructed with a parsed Stirrup configuration. At execution it must:

1. require a non-empty `request.model` and use that exact string in every policy request;
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
| Non-empty or explicitly empty final text, with or without files | `COMPLETED` | yes | yes |
| Files and no final text | `COMPLETED` | no | yes |
| Valid session completion with neither final text nor files | `NO_DELIVERABLE` | no | yes |
| Max-turn exhaustion without a valid finish | `NO_DELIVERABLE` | no | yes |
| Typed runtime/config/transport/integrity failure | failure-specific status | no | no |

An empty string is a real final-text value only when the typed finish/session result says text was present. Missing text is `None`. PR07 must not fabricate `"No output produced by agent"`, turn an exception into answer text, append decoded files to answer text, or expose history/finish bookkeeping as candidate artifacts.

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

The optional field `configuration: ExecutionConfigurationEvidence | None` is added to `PreflightResult` and `ExecutionResult`. The common runner requires exact preflight/result equality for every task and places its fixed serialization in the executor descriptor and run configuration. `execution_record()` serializes only these named fields; arbitrary `ExecutionResult.metadata` remains excluded.

`ExecutorEvidence` in `CandidateBundle` gets the same optional nested `configuration` object. This is a breaking strict-schema change: increment `CANDIDATE_BUNDLE_SCHEMA_VERSION` exactly once from the version present after rebasing PR02c, update every encoder/decoder/exact-key check and golden fixture in the same change, and reject the old shape. Do not implement dual readers, field aliases, inferred defaults, or old/new fallback. Existing local executors emit JSON `null` and all their fixtures are migrated to that exact new schema.

The evidence contains no URL, header, environment-variable name, secret value, prompt, or arbitrary mapping. The top-level run configuration hash changes because it includes this fixed object. Requested model remains in existing executor evidence; `ExecutionResult.model_id` is the exact non-empty `model` returned by the provider on every turn. All turns must report one identical value. A missing or mixed returned model is a protocol failure. A returned versioned model may differ from the requested alias; both are persisted and the harness does not pretend they are equal.

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
      "environment_variable": "POLICY_API_KEY"
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
      "mode": "huggingface",
      "model_id": "organization/tokenizer",
      "revision": "immutable-revision",
      "counting_method": "chat-template-with-tools",
      "trust_remote_code": false,
      "local_files_only": true
    }
  },
  "sandbox": {
    "kind": "apptainer",
    "image": "/absolute/path/policy-tools.sif",
    "image_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "working_directory": "/workspace",
    "memory_limit_mb": null
  },
  "web": {
    "kind": "disabled"
  }
}
```

For deterministic mock tests, `tokenizer` may instead be exactly `{"mode":"utf8-bytes-v1"}`. That is an explicit conservative estimator and is hashed. It is never an automatic fallback. The AA-v2 profile must use the characterized Hugging Face tokenizer, immutable revision, configured counting method, and local-only loading. A tokenizer import, load, template, tool-schema, or tokenization failure fails preflight or execution with a stable protocol/config code; it never changes counting methods. If the computed remaining context is below `minimum_completion_tokens`, the provider is not called.

`auth.mode` is exactly `bearer-env` or `none`. `bearer-env` requires one name matching `[A-Z_][A-Z0-9_]*`; the value is read from `ExecutionRequest.environment` immediately before the request, placed only in the host-side Authorization header, and never passed into Stirrup history, the sandbox, config serialization, a digest, `repr`, logs, failure codes, result metadata, or candidate data. `none` sends no Authorization header and must be explicit. Arbitrary headers, userinfo, URL query/fragment, inline API keys/tokens, templated URLs, and query-key authentication are rejected. `base_url` is HTTP(S), normalized once as an API root, and the only policy path constructed is `<base_url>/chat/completions`.

The raw config source contains environment references, never credential values, so hashing its exact bytes is safe. Validation errors name fields and stable codes without echoing field values. The resolved frozen config uses redacted credential wrappers (`repr=False`) and accepts no arbitrary dict of environment variables.

`system_prompt` is inline so its exact UTF-8 bytes are covered by the source hash. The effective executor user prompt remains exactly `TaskSpec.prompt`; no hidden GDPval prompt/template is added. `skip_input_file_listing=True` is fixed so Stirrup does not silently add a second task/file prompt. Benchmark `execution_task()` owns any neutral file listing. `tool_response_as_user=True` is a versioned executor behavior.

The production v1 sandbox kind is Apptainer only. Test code may inject a fake/local `SandboxFactory` through a private constructor seam; no JSON value selects it. The configured SIF must be a regular non-symlink file and match `image_sha256`. Dynamic provider class names, arbitrary mounts, raw shell fragments, arbitrary env passthrough, and benchmark-selected containers are not accepted.

Network policy comes from the generic executor constructor/CLI, not a benchmark name. With network disabled, the runtime omits network tools and starts Apptainer with an actually enforced no-network mode; preflight fails closed if the installed Apptainer/runtime cannot establish that isolation. With network enabled, Apptainer may use host networking. Web tooling is still independently explicit. A future `web.kind="tavily"` shape is allowed only if PR07 also migrates it to `server_utils.request`, one explicitly referenced credential, typed auth/quota failures, and no key rotation or environment fallback. If that bounded work does not fit PR07, v1 must reject every value except `disabled`, and PR10 cannot delete the old route until the required AA-v2 web capability has an accepted typed replacement.

## 4. Provider transport and async lifecycle

`eval_harness.executors.stirrup_runtime.StirrupProviderTransport` calls `nemo_gym.server_utils.request`; it does not instantiate the OpenAI SDK client, `httpx.AsyncClient`, `requests`, or a second aiohttp session. The request is non-streaming JSON and is parsed with `NeMoGymChatCompletion.model_validate` (or the exact equivalent available at the accepted base). Only a 2xx body is decoded. Non-2xx bodies are drained and discarded, never copied into exceptions or logs.

Generation POSTs are not automatically replayed after an uncertain connection failure. Add the smallest generic private attempt control to `server_utils.request` if the accepted API still lacks one, preserving all existing caller defaults. Stirrup passes one connection attempt and one general attempt. It never uses `NeMoGymAsyncOpenAI`'s status retry loop, so 429 is returned immediately as typed quota failure and 5xx is returned immediately as transport failure. There is no endpoint, API, cloud, model, reasoning, or auth fallback.

The generic executor remains synchronous. Each `execute()` calls `asyncio.run()` once for the full Stirrup session. Every policy and optional web request in that session shares the common NeMo aiohttp singleton. In the coroutine's `finally`, an async, same-event-loop `server_utils` close/reset helper closes that singleton after sandbox/session cleanup. This prevents a `ClientSession` created on task 1's loop from being reused on task 2's closed loop. Existing server lifetime behavior stays unchanged; only the new explicit helper and its unit tests are added. Two sequential executor-task tests must prove the lifecycle. Calling the synchronous executor from an already-running event loop fails before constructing a coroutine with a stable internal error; the generic CLI never does so.

The overall `ExecutionRequest.timeout_seconds` bounds the async session. Provider calls receive the remaining deadline. On expiry, the runtime cancels the session, closes tool providers, reaps the Apptainer process, removes temporary staging, and closes the aiohttp client; cleanup is itself bounded. No background Ray future or async task survives the result.

## 5. Stirrup session and output recovery

The runtime passes explicit tools and finish tools to `NeMoAgent`; it does not mutate Stirrup globals at import time. Move the useful tool-argument validation detail into the local `NeMoAgent.run_tool` override and pass `COERCING_FINISH_TOOL` explicitly. `finish_mode="coercing"` exposes that tool. `finish_mode="coercing-with-abandon"` also exposes `ABANDON_FINISH_TOOL`; this is a generic, hashed session choice rather than `is_gdpval`. An abandon call is a valid no-deliverable model outcome, not an infrastructure failure.

The dynamic completion budget is retained without fallback:

```text
remaining = context_window_tokens - counted_input_tokens - completion_token_buffer
if remaining < minimum_completion_tokens: fail before provider call
max_completion_tokens = min(remaining, maximum_completion_tokens)
```

The serialized messages and serialized tool schemas used for counting are the ones sent on the wire. The configured tokenizer/counting method is used once; the current cascade through chat-template, JSON, and character estimates is removed from the new route. A length finish with valid typed content remains a valid turn and the agent may continue until finish/max-turn/timeout.

The adapter creates fresh executor-private `input-stage` and `output-stage` roots. It copies the execution view to `input-stage`, excluding `deliverables/`, then gives that stage to Stirrup. Model code never operates on the authoritative snapshot/workspace inputs. `output-stage` contains only recovered files named by a successful finish. Session history, token metadata, finish params, stderr, and patches remain under `executor_dir` as bounded secret-safe runtime diagnostics and never enter deliverables.

Finish paths are converted to logical POSIX paths only if they are relative to the configured sandbox working directory or already safe relative paths. Reject absolute paths outside that root, `..`, `.`, empty components, backslashes, drive prefixes, NULs, non-NFC names, symlinks, irregular files, exact duplicates, case-fold/Unicode collisions, and file/directory prefix collisions. Preserve nested paths; `a/report.txt` and `b/report.txt` remain distinct. Never search by basename or recursively guess a source.

`ApptainerCodeExecToolProvider.save_output_files()` must return an exact one-to-one typed `SavedFile` mapping and preserve those normalized relative paths. Missing model-declared files are a model no-deliverable condition for those paths and are recorded in bounded runtime diagnostics; unsafe paths, ambiguous mappings, unexpected staged files, source mutation, or host copy failures are systemic integrity/process failures. After the full set validates, copy with exclusive creation into the initially empty assigned deliverables directory and fsync. PR02c's accepted public artifact-path validator should be reused. If it is still private after rebase, extract only that validator for CandidateBundle and Stirrup with all existing candidate tests unchanged; do not maintain two divergent path policies.

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

Final text is the finish reason followed by the last distinct non-empty assistant text, with a single blank line separator. It is `None` when neither exists. Artifact bytes are never decoded into it. Random response/message IDs and full transcripts are not candidate evidence.

## 6. Failure map

All codes are static and contain no exception text, provider body, URL, path, task prompt, or secret. The accepted `ExecutionResult` contract currently requires any failed execution to have `FailureImpact.RUN`; PR07 follows that rule and the common runner stops remaining tasks. Model non-completion is represented as `NO_DELIVERABLE`, so a weak model does not become a systemic executor failure.

| Condition | Status | `FailureKind` | Stable code |
|---|---|---|---|
| Missing bearer value at execute | `FAILED` | `AUTH` | `stirrup.provider_auth_missing` |
| Provider HTTP 401/403 | `FAILED` | `AUTH` | `stirrup.provider_auth_rejected` |
| Provider HTTP 429 | `FAILED` | `QUOTA` | `stirrup.provider_quota` |
| Provider rejects request (other 4xx) | `FAILED` | `PROTOCOL` | `stirrup.provider_request_rejected` |
| Invalid JSON/schema, zero/multiple choices, invalid tool call, missing/mixed returned model | `FAILED` | `PROTOCOL` | `stirrup.provider_response_invalid` |
| Context budget below configured minimum | `FAILED` | `PROTOCOL` | `stirrup.context_budget_exhausted` |
| Connection/DNS/TLS failure or provider 5xx | `FAILED` | `TRANSPORT` | `stirrup.provider_unavailable` |
| Wall-clock deadline | `TIMED_OUT` | `TIMEOUT` | `stirrup.session_timeout` |
| Keyboard interruption | `INTERRUPTED` | `INTERRUPTED` | `stirrup.interrupted` |
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
| `eval_harness/executors/stirrup_runtime.py` | Common-aiohttp provider transport, typed provider parsing/model evidence, token budget, explicit Stirrup session/tool construction and typed outcome. |

Narrow generic changes:

| Path | Change |
|---|---|
| `eval_harness/executors/base.py` | Add fixed `ExecutionConfigurationEvidence` and optional fields. |
| `eval_harness/provenance.py` | Serialize its exact fixed shape. |
| `eval_harness/candidate_bundle.py` | Add fixed executor configuration evidence and bump strict schema once. |
| `eval_harness/runner.py` and PR02c integration sites | Hash/match preflight/result configuration evidence and carry it into the sealed bundle. |
| `eval_harness/executors/registry.py`, `eval_harness/cli.py` | Construct Stirrup explicitly and validate config/model arguments. |
| `eval_harness/benchmarks/registry.py` | Expose Stirrup only for descriptors whose existing execution capabilities it satisfies; no Stirrup code receives a benchmark name. |
| `nemo_gym/server_utils.py` | Small explicit request-attempt control if needed and same-loop async singleton close/reset; existing defaults unchanged. |

Narrow reused-resource changes, each with direct tests:

| Path | Change |
|---|---|
| `responses_api_agents/stirrup_agent/nemo_agent.py` | Typed local tool-result role and argument-validation behavior; no global monkey patch. |
| `responses_api_agents/stirrup_agent/apptainer_provider.py` | Typed construction, enforced network mode, lifecycle, safe nested output mapping; no benchmark branch/dynamic class/env passthrough in new path. |
| `responses_api_agents/stirrup_agent/stirrup_utils.py` | Provider-valid message serialization/final-text helper typing if still required after rebase. |
| `responses_api_agents/stirrup_agent/finish_tool_coercing.py` | Reuse explicit generic finish/coercion; retain abandon only as configured generic finish mode. |
| `responses_api_agents/stirrup_agent/tavily_search.py` | Only if web is in PR07: switch to common aiohttp request, explicit one-key auth, typed failure, no env fallback/rotation in new path. |

Dependency/CI files may change only to install and validate the exact host runtime: `pyproject.toml`, `uv.lock`, `responses_api_agents/stirrup_agent/requirements.txt`, `.github/workflows/eval-harness-ci.yml`, and the relevant dependency-audit configuration. Do not copy the document/PDF/ML packages advertised inside the GDPval SIF into the host extra.

`app.py`, `task_strategy.py`, `tasks/gdpval.py`, `file_reader.py`, `client.py`, Ray orchestration, resources servers, evaluator code, GDPval shell scripts, recipes, and scoring configs are not implementation surfaces for the new route. PR07 must not hide edits to those components as adapter work.

## 8. Deterministic tests and exact expectations

All adapter/control branches remain under the existing `source=eval_harness` coverage measurement and the exact 96.00% gate. No omit rule, pragma, threshold, or source scope changes. Reused modules receive their existing direct server/unit tests in addition to measured harness integration.

Add the following `unittest`-compatible harness tests and typed fixtures:

| Test | Required assertion |
|---|---|
| Strict config round trip | Exact raw-byte SHA, fixed evidence, duplicate/unknown/nonfinite/inline-secret/query/userinfo/bad-env-name rejection; no rejected value appears in error text. |
| Auth header | Mock server sees exact `Authorization: Bearer <fixture secret>` for `bearer-env`; `none` sees no Authorization header. Fixture secret is absent from result, run metadata, CandidateBundle bytes, config digest inputs, stdout/stderr, and raised exception text. |
| Endpoint ownership | Mock server accepts only `POST /v1/chat/completions`; every other path fails the test. Captured requests contain no `/verify`, `/run`, resource-server name, rubric, reference answer, judge flag, or benchmark name. |
| Real Stirrup session with mock provider | Typed response 1 calls `code_exec` to create `nested/result.txt`; response 2 calls `finish`. Actual locked Stirrup session and injected test sandbox recover exact bytes/nested path, final text, and provider-returned model ID. No real model/network service is used. |
| Text-only/artifact-only/empty/abandon/max-turn | Exact status/channel table in section 2; no fabricated text and no file-content concatenation. |
| Artifact safety | Preserve duplicate basenames in different directories; reject traversal, outside absolute paths, symlink, irregular file, Unicode/casefold and prefix collisions; bookkeeping never appears. |
| Provider schema | Valid fixture is parsed through `NeMoGymChatCompletion`; invalid JSON, empty/two choices, malformed tool arguments, omitted model, and mixed per-turn model produce `PROTOCOL` and zero candidate channels. |
| Failure table | 401/403, 429, other 4xx, 5xx/connection, wall timeout, sandbox start/teardown, and output-integrity cases produce the exact status/kind/code and no diagnostic/secret. No alternate request follows. |
| Systemic stop | A two-task common-runner fixture receives auth, quota, protocol, and timeout failures on task 1; task 2 is never materialized/executed/evaluated and provider count stays one. |
| Sequential lifecycle | Two successful tasks in one run use valid common aiohttp sessions despite separate synchronous `execute()` calls; no unclosed-session warning remains. |
| Configuration matching | Runner rejects preflight/result evidence mismatch before sealing/evaluation; run and CandidateBundle contain identical fixed evidence. |
| Strict bundle migration | New schema reads; previous schema, missing `configuration`, extra fields, bad digest, and altered configuration evidence fail closed. All existing executor fixtures explicitly contain null configuration. |
| Neutral fourth task | A local `Benchmark` fixture named `neutral-fourth` supplies a prompt and `task_inputs/input.txt`; the same registered Stirrup executor/common runner/mock provider produces and seals a bundle without any core or executor benchmark-name condition. Mock endpoint still observes only chat completions. |
| Dependency absent | Registry listing works without the optional extra; selecting Stirrup fails preflight with a stable dependency detail before any network/model call. |
| Network policy | Disabled mode omits web tools and uses tested Apptainer no-network arguments or fails preflight; enabled mode is explicit. No test claims no-network merely because the provider is mocked. |

Fixtures belong under `tests/harness/fixtures/executor_protocol/stirrup/` and contain only synthetic keys marked for the repository's secret scanner. Actual runtime integration must use the installed Stirrup package, not a fake module tree; narrow backend injection is used only for filesystem/failure unit cases.

Required validation on the implementation head:

```text
uv lock --check
uv sync --locked --extra dev --extra stirrup-executor
uv run --no-sync mypy --strict --explicit-package-bases --show-error-codes eval_harness tests/harness ...
coverage run --rcfile=config/eval-harness-coveragerc scripts/ci/run_eval_harness_coverage.py
coverage json --rcfile=config/eval-harness-coveragerc --pretty-print -o ...
python scripts/ci/run_eval_harness_coverage.py --check-summary ...
pre-commit run --all-files --show-diff-on-failure
<repository dependency/CVE/license/secret/copyright gates>
```

The eval-harness workflow must install the locked Stirrup extra so the actual-session mock test cannot skip. Changes to `nemo_agent.py`, `apptainer_provider.py`, `tavily_search.py`, or `server_utils.py` also run their direct unit suites. No CI test makes a real model, paid judge, Tavily, or public-network call.

## 9. Exact legacy retain/delete map

PR07 leaves the legacy route operational only for migration comparison. The new executor never imports `responses_api_agents.stirrup_agent.app`. PR10 deletes the route after PR07/08 acceptance using this map.

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
| `nemo_agent.py` | Retain as a small generic Stirrup compatibility component, with typed local behavior and direct tests. Remove GDPval descriptions/branches. |
| `nemo_client.py` | Port dynamic budgeting and typed response parsing into measured runtime with common aiohttp transport and no fallbacks/global patches. Delete the HTTPX/OpenAI-SDK legacy client in PR10. |
| `stirrup_utils.py` | Retain provider-valid message serialization if used. Delete NeMo Responses-output conversion and random response IDs when old route goes. |
| `finish_tool_coercing.py` | Retain coercing finish explicitly. Retain abandon as generic config capability only; no benchmark condition. Delete it if dependency characterization proves the locked provider parser no longer needs it. |
| `apptainer_provider.py` | Retain lifecycle and code tool after safe construction, output-path, network, cleanup, and typing changes. Remove Ray serialization/dynamic mounts/env passthrough that have no accepted consumer. |
| `tavily_search.py` | Retain only after common-aiohttp and explicit-auth migration if AA-v2 requires it. Delete HTTPX, implicit env lookup, and key rotation/fallback from new semantics. |
| `client.py` | Old manual agent-server client is not used. Delete in PR10 with the server route. |
| `configs/stirrup_agent.yaml` mixed fields | Replace policy/session/sandbox/auth inputs with strict executor config. PR08 owns AA-v2 evaluator/profile fields. Delete `task`, resources server, datasets, persistence, execute/judge/rerun controls in PR10. |
| `scripts/gdpval_provider.sh`, old preflight/setup shell, recipes | Extract only values needed by typed config/profile and preflight. New executor never invokes them. Delete replaced entrypoints in PR10. |
| GDPval SIF definition/image | Retain as an explicit sandbox asset, referenced by path plus checked SHA-256; no executor benchmark branch. |

## 10. Dependency decision and gate

PR07 must add a root optional extra named `stirrup-executor`; the generic package and executor listing remain importable without it. The exact Stirrup version, transitive resolution, license/CVE result, and Python 3.13 import/session API evidence must be pinned here before Luna handoff. The current resource requirement declares `stirrup>=0.1.12,<0.2`, while the root lock has no Stirrup distribution. Copying that range without an exact resolved lock is not acceptance. This checkpoint will be amended with the selected version and resolver/audit evidence before implementation dispatch.

The host extra contains only packages imported by the host Stirrup/session/web runtime. Document/PDF/data/ML tools advertised to the model remain in the hashed Apptainer image. Root and resource requirements must select the same Stirrup compatibility line; there is no isolated-version fallback.

## 11. Luna handoff

**Purpose:** implement one benchmark-neutral Stirrup policy-generation executor through the generic runner and CandidateBundle path.

**Target commit:** exact accepted PR06/PR02c-dependent head, supplied as a 40-character SHA by the migration owner before work starts.

**Allowed files:** only the measured/new modules, narrow generic/evidence/registry/CLI files, narrow reused-resource files, fixtures/tests, exact dependency/lock/audit files, and eval-harness validation workflow listed in section 7. Contract expansion or evaluator/profile/legacy-route deletion returns to Sol.

**Inputs:** strict config source; neutral `TaskSpec` and `ExecutionRequest`; environment map containing only externally supplied credential values; staged execution-view workspace; requested model/timeout/network flag.

**Outputs:** one typed `ExecutionResult`, secret-free fixed configuration/model/runtime evidence, final text and validated artifact tree, then one PR02c `CandidateBundle`. No score, reward, judgement, evaluator request, cached result, or provider transcript.

**Completion:** every test in section 8 passes using the exact lock, strict typing and 96% gate pass, dependency/security/license checks pass, changed reused-resource tests pass, and source inspection/readback proves the generic adapter has no dependency on `app.py`, GDPval task strategy, resources servers, Ray, `/run`, or `/verify`.

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

This record is **saved design evidence** only. It has no production changes, no model validation, no Accepted status, and no claim that Gate A or Gate B passed.
