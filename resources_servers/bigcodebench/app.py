# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
from typing import cast
from pathlib import Path

from fastapi import FastAPI
from resources_servers.bigcodebench.code_extraction import preprocess_code_completion

from eval_harness.bigcodebench_runner import BigCodeBenchGradeRequest, NativeStatus
from eval_harness.grader_sandbox import (
    GraderInfrastructureError,
    GraderSandboxPreflight,
    GraderSandboxSpec,
    preflight_bigcodebench_sandbox,
    resolve_bigcodebench_resource_dir,
    resolve_bigcodebench_sandbox_spec,
    run_bigcodebench_sandbox,
    sandbox_provenance,
)

from nemo_gym.base_resources_server import (
    BaseResourcesServerConfig,
    BaseVerifyRequest,
    BaseVerifyResponse,
    SimpleResourcesServer,
)
from nemo_gym.judge import judge_failsafe
from nemo_gym.rollout_correlation import RolloutContextMiddleware
from nemo_gym.reward_profile import (
    compute_pass_majority_metrics,
    highest_k_metrics,
)
from nemo_gym.telemetry.endpoints import traced_verify_endpoint


_BIGCODEBENCH_SEMAPHORE = asyncio.Semaphore(1)


class BigCodeBenchResourcesServerConfig(BaseResourcesServerConfig):
    """Configuration for the fixed, pre-provisioned BigCodeBench runtime."""


class BigCodeBenchVerifyRequest(BaseVerifyRequest):
    verifier_metadata: dict[str, object] | None = None


class BigCodeBenchVerifyResponse(BaseVerifyResponse):
    extracted_model_output: str | None = None
    extracted_model_code: str | None = None
    status: str | None = None
    details: dict[str, object] | None = None
    task_id: str | None = None


class BigCodeBenchResourcesServer(SimpleResourcesServer):
    config: BigCodeBenchResourcesServerConfig

    def model_post_init(self, context: object) -> None:
        del context
        self._semaphore = _BIGCODEBENCH_SEMAPHORE
        resource_dir = resolve_bigcodebench_resource_dir()
        self._sandbox_spec = resolve_bigcodebench_sandbox_spec(resource_dir)
        self._sandbox_preflight = preflight_bigcodebench_sandbox(self._sandbox_spec)
        if not self._sandbox_preflight.ok:
            detail = "; ".join(self._sandbox_preflight.details)
            raise GraderInfrastructureError(f"BigCodeBench sandbox preflight failed: {detail}")

    def setup_webserver(self) -> FastAPI:
        """Register the typed BigCodeBench request model on the verify route."""

        app = FastAPI()
        self.setup_session_middleware(app)
        app.add_middleware(RolloutContextMiddleware)
        app.post("/seed_session")(self.seed_session)
        app.post("/verify")(
            traced_verify_endpoint(
                judge_failsafe(self._verify_endpoint),
                static_attributes={"nemo.gym.server.name": self.config.name},
            )
        )
        app.post("/aggregate_metrics")(self.aggregate_metrics)
        app.get("/reverify_mode")(self.get_reverify_mode)
        return app

    @staticmethod
    def _score_fn(r: dict[str, object]) -> dict[str, float]:
        reward = r.get("reward")
        return {"accuracy": float(isinstance(reward, (int, float)) and not isinstance(reward, bool) and reward > 0)}

    def compute_metrics(self, tasks: list[list[dict[str, object]]]) -> dict[str, object]:
        return compute_pass_majority_metrics(
            tasks,
            score_fn=self._score_fn,
            answer_key="extracted_model_code",
        )[0]

    def get_key_metrics(self, agent_metrics: dict[str, object]) -> dict[str, object]:
        key: dict[str, object] = {}
        for name in ("mean/input_tokens", "mean/output_tokens"):
            if name in agent_metrics:
                key[name] = agent_metrics[name]
        key.update(highest_k_metrics(agent_metrics, "pass@1[avg-of-{k}]", score_names=["accuracy"]))
        key.update(highest_k_metrics(agent_metrics, "pass@{k}", score_names=["accuracy"]))
        key.update(highest_k_metrics(agent_metrics, "majority@{k}", score_names=["accuracy"]))
        return key

    async def verify(self, body: BaseVerifyRequest) -> BaseVerifyResponse:
        """Satisfy the common server contract; the route uses the typed endpoint."""

        typed_body = body if isinstance(body, BigCodeBenchVerifyRequest) else BigCodeBenchVerifyRequest.model_validate(body.model_dump())
        return await self._verify_endpoint(typed_body)

    async def _verify_endpoint(self, body: BigCodeBenchVerifyRequest) -> BigCodeBenchVerifyResponse:
        model_out = body.response.output_text or ""
        meta = body.verifier_metadata or {}
        task_value = meta.get("task_id")
        task_id = task_value if isinstance(task_value, str) else None

        if not model_out.strip():
            return BigCodeBenchVerifyResponse(
                **body.model_dump(),
                reward=0.0,
                status="empty_output",
                task_id=task_id,
            )

        extracted = preprocess_code_completion(model_out)
        if not extracted:
            return BigCodeBenchVerifyResponse(
                **body.model_dump(),
                reward=0.0,
                extracted_model_output=model_out,
                status="no_code_block",
                task_id=task_id,
            )

        # Skills passes ``calibrated=True`` to bigcodebench.evaluate, which prepends
        # ``code_prompt + "\n    pass\n"`` to the model's solution before running the test.
        # That ensures the entry_point function exists even if the model returned only the body.
        code_prompt_value = meta.get("code_prompt")
        test_code = meta.get("test")
        entry_point = meta.get("entry_point")
        if not isinstance(code_prompt_value, str) or not isinstance(test_code, str) or not isinstance(entry_point, str):
            raise ValueError("BigCodeBench verifier metadata is incomplete")
        code_prompt = code_prompt_value
        calibrated = code_prompt + "\n    pass\n" + extracted

        async with self._semaphore:
            worker = asyncio.create_task(
                asyncio.to_thread(
                    self._run_sandbox,
                    code=calibrated,
                    test_code=test_code,
                    entry_point=entry_point,
                    task_id=task_id or "BigCodeBench",
                )
            )
            try:
                result = await asyncio.shield(worker)
            except asyncio.CancelledError:
                await worker
                raise

        status_value = result.get("status")
        status = status_value if isinstance(status_value, str) else None
        details_value = result.get("details")
        details = details_value if isinstance(details_value, dict) else None
        return BigCodeBenchVerifyResponse(
            **body.model_dump(),
            reward=1.0 if status == "passed" else 0.0,
            extracted_model_output=model_out,
            extracted_model_code=extracted,
            status=status,
            details=cast(dict[str, object] | None, details),
            task_id=task_id,
        )

    def _run_sandbox(self, code: str, test_code: str, entry_point: str, task_id: str) -> dict[str, object]:
        sandbox_spec = self._sandbox_spec
        sandbox_preflight = self._sandbox_preflight
        if sandbox_spec is None or sandbox_preflight is None or not sandbox_preflight.ok:
            raise GraderInfrastructureError("successful BigCodeBench sandbox preflight is required")
        native = run_bigcodebench_sandbox(
            BigCodeBenchGradeRequest(
                schema_version=1,
                code=code,
                test_code=test_code,
                entry_point=entry_point,
                task_id=task_id,
            ),
            spec=sandbox_spec,
            preflight=sandbox_preflight,
        )
        if native.limit_kind is not None:
            return {"status": "candidate_resource_limit", "details": {"limit_kind": native.limit_kind.value}}
        if native.native_status is NativeStatus.PASS:
            return {"status": "passed", "details": None, "grader_provenance": sandbox_provenance(sandbox_preflight)}
        if native.native_status is NativeStatus.FAIL:
            return {"status": "failed_tests", "details": None, "grader_provenance": sandbox_provenance(sandbox_preflight)}
        if native.native_status is NativeStatus.TIMEOUT:
            return {"status": "candidate_timeout", "details": None, "grader_provenance": sandbox_provenance(sandbox_preflight)}
        raise GraderInfrastructureError("sandbox returned an unknown native outcome")


if __name__ == "__main__":
    BigCodeBenchResourcesServer.run_webserver()
