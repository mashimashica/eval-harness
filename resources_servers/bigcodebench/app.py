# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_extraction import preprocess_code_completion

from eval_harness.bigcodebench_runner import BigCodeBenchGradeRequest, NativeStatus
from eval_harness.grader_sandbox import (
    GraderInfrastructureError,
    GraderSandboxPreflight,
    GraderSandboxSpec,
    LimitKind,
    preflight_bigcodebench_sandbox,
    resolve_bigcodebench_sandbox_spec,
    run_bigcodebench_sandbox,
)

from nemo_gym.base_resources_server import (
    BaseResourcesServerConfig,
    BaseVerifyRequest,
    BaseVerifyResponse,
    SimpleResourcesServer,
)
from nemo_gym.reward_profile import (
    compute_pass_majority_metrics,
    highest_k_metrics,
)


_BIGCODEBENCH_SEMAPHORE = asyncio.Semaphore(1)


class BigCodeBenchResourcesServerConfig(BaseResourcesServerConfig):
    num_processes: int = 8
    venv_path: str = ".bcb_venv"
    bcb_python_version: str = "3.10"
    max_as_limit: int = 30 * 1024
    max_data_limit: int = 30 * 1024
    max_stack_limit: int = 10
    min_time_limit: float = 1.0
    gt_time_limit: float = 20.0
    subprocess_timeout: float = 240.0


class BigCodeBenchVerifyRequest(BaseVerifyRequest):
    verifier_metadata: Optional[Dict[str, Any]] = None


class BigCodeBenchVerifyResponse(BaseVerifyResponse):
    extracted_model_output: Optional[str] = None
    extracted_model_code: Optional[str] = None
    status: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    task_id: Optional[str] = None


class BigCodeBenchResourcesServer(SimpleResourcesServer):
    config: BigCodeBenchResourcesServerConfig

    def model_post_init(self, context):
        del context
        self._semaphore = _BIGCODEBENCH_SEMAPHORE
        self._sandbox_spec: GraderSandboxSpec | None = None
        self._sandbox_preflight: GraderSandboxPreflight | None = None
        self._sandbox_error: GraderInfrastructureError | None = None
        try:
            self._sandbox_spec = resolve_bigcodebench_sandbox_spec(Path(__file__).parent)
            self._sandbox_preflight = preflight_bigcodebench_sandbox(self._sandbox_spec)
            if not self._sandbox_preflight.ok:
                self._sandbox_error = GraderInfrastructureError("BigCodeBench sandbox preflight failed")
        except GraderInfrastructureError as exc:
            self._sandbox_error = exc

    @staticmethod
    def _score_fn(r: dict) -> Dict[str, float]:
        return {"accuracy": float(r["reward"] > 0)}

    def compute_metrics(self, tasks: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
        return compute_pass_majority_metrics(
            tasks,
            score_fn=self._score_fn,
            answer_key="extracted_model_code",
        )[0]

    def get_key_metrics(self, agent_metrics: Dict[str, Any]) -> Dict[str, Any]:
        key: Dict[str, Any] = {}
        for name in ("mean/input_tokens", "mean/output_tokens"):
            if name in agent_metrics:
                key[name] = agent_metrics[name]
        key.update(highest_k_metrics(agent_metrics, "pass@1[avg-of-{k}]", score_names=["accuracy"]))
        key.update(highest_k_metrics(agent_metrics, "pass@{k}", score_names=["accuracy"]))
        key.update(highest_k_metrics(agent_metrics, "majority@{k}", score_names=["accuracy"]))
        return key

    async def verify(self, body: BigCodeBenchVerifyRequest) -> BigCodeBenchVerifyResponse:
        model_out = body.response.output_text or ""
        meta = body.verifier_metadata or {}
        task_id = meta.get("task_id")

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
        code_prompt = meta.get("code_prompt", "")
        calibrated = code_prompt + "\n    pass\n" + extracted

        async with self._semaphore:
            result = await asyncio.to_thread(
                self._run_in_venv,
                code=calibrated,
                test_code=str(meta["test"]),
                entry_point=str(meta["entry_point"]),
                task_id=str(task_id or "BigCodeBench"),
            )

        status = result.get("status")
        return BigCodeBenchVerifyResponse(
            **body.model_dump(),
            reward=1.0 if status == "pass" else 0.0,
            extracted_model_output=model_out,
            extracted_model_code=extracted,
            status=status,
            details=result.get("details"),
            task_id=task_id,
        )

    def _run_in_venv(self, code: str, test_code: str, entry_point: str, task_id: str) -> Dict[str, Any]:
        if self._sandbox_error is not None:
            raise self._sandbox_error
        if self._sandbox_spec is None or self._sandbox_preflight is None or not self._sandbox_preflight.ok:
            raise GraderInfrastructureError("successful BigCodeBench sandbox preflight is required")
        native = run_bigcodebench_sandbox(
            BigCodeBenchGradeRequest(
                schema_version=1,
                code=code,
                test_code=test_code,
                entry_point=entry_point,
                task_id=task_id,
            ),
            spec=self._sandbox_spec,
            preflight=self._sandbox_preflight,
        )
        if native.limit_kind is not None:
            return {"status": "candidate_resource_limit", "details": {"limit_kind": native.limit_kind.value}}
        if native.native_status is NativeStatus.PASS:
            return {"status": "pass", "details": None}
        if native.native_status is NativeStatus.FAIL:
            return {"status": "fail", "details": None}
        if native.native_status is NativeStatus.TIMEOUT:
            return {"status": "timeout", "details": None}
        raise GraderInfrastructureError("sandbox returned an unknown native outcome")


if __name__ == "__main__":
    BigCodeBenchResourcesServer.run_webserver()
