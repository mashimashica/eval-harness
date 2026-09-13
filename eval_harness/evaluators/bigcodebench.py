# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""BigCodeBench extraction and attested executable-test evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, cast

from eval_harness.bigcodebench_runner import (
    MAX_IDENTIFIER_BYTES,
    BigCodeBenchGradeRequest,
    NativeStatus,
    ProtocolError,
)
from eval_harness.grader_sandbox import (
    GraderInfrastructureError,
    GraderSandboxPreflight,
    GraderSandboxSpec,
    preflight_bigcodebench_sandbox,
    resolve_bigcodebench_sandbox_spec,
    run_bigcodebench_sandbox,
    sandbox_provenance,
)
from eval_harness.evaluators.base import (
    EvaluationPlan,
    EvaluationRequest,
    EvaluationResult,
    EvaluationStatus,
    Evaluator,
    EvaluatorPreflightResult,
    EvaluatorType,
    require_one_candidate,
)


_TERMINAL_SUCCESS = {"completed", "no_deliverable"}


def _paths_overlap(left: Path, right: Path) -> bool:
    left_resolved = left.resolve()
    right_resolved = right.resolve()
    return (
        left_resolved == right_resolved
        or left_resolved in right_resolved.parents
        or right_resolved in left_resolved.parents
    )


def _native_bigcodebench_evaluate(
    output_text: str,
    verifier_metadata: Mapping[str, object],
    *,
    resource_dir: Path,
    sandbox_spec: GraderSandboxSpec | None = None,
    sandbox_preflight: GraderSandboxPreflight | None = None,
) -> dict[str, object]:
    """Extract code and submit it through the shared attested sandbox."""

    from resources_servers.bigcodebench.code_extraction import preprocess_code_completion

    if sandbox_spec is None:
        sandbox_spec = resolve_bigcodebench_sandbox_spec(resource_dir)
    if sandbox_preflight is None:
        sandbox_preflight = preflight_bigcodebench_sandbox(sandbox_spec)
    if not sandbox_preflight.ok:
        raise GraderInfrastructureError("BigCodeBench sandbox preflight failed")
    if type(output_text) is not str or type(resource_dir) is not Path:
        raise GraderInfrastructureError("BigCodeBench evaluator input is invalid")
    code_prompt = verifier_metadata.get("code_prompt")
    test_code = verifier_metadata.get("test")
    entry_point = verifier_metadata.get("entry_point")
    task_id = verifier_metadata.get("task_id", "BigCodeBench")
    if any(type(value) is not str for value in (code_prompt, test_code, entry_point, task_id)):
        raise GraderInfrastructureError("BigCodeBench verifier metadata is invalid")
    code_prompt = cast(str, code_prompt)
    test_code = cast(str, test_code)
    entry_point = cast(str, entry_point)
    task_id = cast(str, task_id)
    if (
        not isinstance(task_id, str)
        or not task_id
        or len(task_id.encode("utf-8")) > MAX_IDENTIFIER_BYTES
        or "\x00" in task_id
    ):
        raise GraderInfrastructureError("BigCodeBench task identity is invalid")
    extracted = preprocess_code_completion(output_text)
    if not extracted:
        return {
            "reward": 0.0,
            "status": "no_code_block",
            "extracted_model_code": None,
            "details": None,
            "grader_provenance": sandbox_provenance(sandbox_preflight),
        }
    calibrated = code_prompt + "\n    pass\n" + extracted
    try:
        request = BigCodeBenchGradeRequest(
            schema_version=1,
            code=calibrated,
            test_code=test_code,
            entry_point=entry_point,
            task_id=task_id,
        )
    except ProtocolError as exc:
        raise GraderInfrastructureError("BigCodeBench verifier metadata is invalid") from exc
    result = run_bigcodebench_sandbox(request, spec=sandbox_spec, preflight=sandbox_preflight)
    provenance = sandbox_provenance(sandbox_preflight)
    if result.limit_kind is not None:
        status = "candidate_resource_limit"
        details: object = {"limit_kind": result.limit_kind.value, "grader_provenance": provenance}
        reward = 0.0
    elif result.native_status is NativeStatus.PASS:
        status = "passed"
        details = {"grader_provenance": provenance}
        reward = 1.0
    elif result.native_status is NativeStatus.FAIL:
        status = "failed_tests"
        details = {"grader_provenance": provenance}
        reward = 0.0
    elif result.native_status is NativeStatus.TIMEOUT:
        status = "candidate_timeout"
        details = {"grader_provenance": provenance}
        reward = 0.0
    else:
        raise GraderInfrastructureError("sandbox returned an unknown native outcome")
    return {
        "reward": reward,
        "status": status,
        "extracted_model_code": extracted,
        "details": details,
        "grader_provenance": provenance,
    }


class BigCodeBenchEvaluator(Evaluator):
    name = "bigcodebench-tests"
    evaluator_type = EvaluatorType.EXECUTABLE_TESTS
    version = "1"
    revision = "v0.1.4"

    def __init__(self, *, resource_dir: Path) -> None:
        self.resource_dir = resource_dir
        self._sandbox_spec: GraderSandboxSpec | None = None
        self._sandbox_preflight: GraderSandboxPreflight | None = None

    def validate_plan(self, plan: EvaluationPlan) -> None:
        if plan.candidate_count != 1:
            raise ValueError("BigCodeBench evaluator requires exactly one candidate")
        required_metadata = ("test", "entry_point", "code_prompt")
        missing = [key for key in required_metadata if key not in plan.metadata]
        if missing:
            raise ValueError("BigCodeBench evaluator requires metadata keys: " + ", ".join(missing))

    def preflight(self, run_dir: Path | None = None) -> EvaluatorPreflightResult:
        grader_root = self.resource_dir.resolve()
        if run_dir is not None and _paths_overlap(grader_root, run_dir):
            self._sandbox_spec = None
            self._sandbox_preflight = None
            return EvaluatorPreflightResult(
                name=self.name,
                evaluator_type=self.evaluator_type,
                ok=False,
                version=self.version,
                revision=self.revision,
                details=("BigCodeBench grader directory must be separate from the evaluator run directory",),
            )
        try:
            forbidden_roots = (run_dir,) if run_dir is not None else ()
            spec = resolve_bigcodebench_sandbox_spec(grader_root, forbidden_roots=forbidden_roots)
            result = preflight_bigcodebench_sandbox(spec)
        except GraderInfrastructureError as exc:
            self._sandbox_spec = None
            self._sandbox_preflight = None
            return EvaluatorPreflightResult(
                name=self.name,
                evaluator_type=self.evaluator_type,
                ok=False,
                version=self.version,
                revision=self.revision,
                details=(f"BigCodeBench sandbox is not ready: {exc}",),
            )
        self._sandbox_spec = spec
        self._sandbox_preflight = result
        return EvaluatorPreflightResult(
            name=self.name,
            evaluator_type=self.evaluator_type,
            ok=result.ok,
            version=self.version,
            revision=self.revision,
            details=result.details,
        )

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        candidate = require_one_candidate(request)
        if self._sandbox_spec is None or self._sandbox_preflight is None or not self._sandbox_preflight.ok:
            raise RuntimeError("successful BigCodeBench evaluator preflight is required before evaluate")
        grader_root = self.resource_dir.resolve()
        workspace = candidate.execution.workspace.resolve()
        if _paths_overlap(workspace, grader_root):
            raise RuntimeError("BigCodeBench grader directory must be separate from the executor workspace")

        required_metadata = ("test", "entry_point", "code_prompt")
        if any(key not in request.metadata for key in required_metadata):
            raise ValueError("BigCodeBench evaluator requires test, entry_point, and code_prompt metadata")
        metadata_task_id = request.metadata.get("task_id")
        if metadata_task_id is not None and (
            type(metadata_task_id) is not str or metadata_task_id != request.task_id
        ):
            raise GraderInfrastructureError("BigCodeBench task identity does not match the request")
        details: dict[str, object] = {
            "execution_status": candidate.execution.status.value,
            "grader": "eval_harness/grader_sandbox.py",
            "grader_invoked": False,
            "dataset_revision": self.revision,
            "grader_provenance": sandbox_provenance(self._sandbox_preflight),
        }
        if candidate.execution.status.value not in _TERMINAL_SUCCESS:
            return EvaluationResult(
                task_id=request.task_id,
                status=EvaluationStatus.COMPLETED,
                metrics={"pass_rate": 0.0},
                details=details,
            )
        output_text = candidate.execution.output_text or ""
        if not output_text.strip():
            details["native_status"] = "empty_output"
            return EvaluationResult(
                task_id=request.task_id,
                status=EvaluationStatus.COMPLETED,
                metrics={"pass_rate": 0.0},
                details=details,
            )

        native = _native_bigcodebench_evaluate(
            output_text,
            request.metadata,
            resource_dir=grader_root,
            sandbox_spec=self._sandbox_spec,
            sandbox_preflight=self._sandbox_preflight,
        )
        details.update(
            {
                "native_status": native.get("status"),
                "extracted_model_code": native.get("extracted_model_code"),
                "grader_details": native.get("details"),
                "grader_provenance": native.get("grader_provenance"),
                "grader_invoked": True,
                "grader_root": str(grader_root),
                "executor_workspace": str(workspace),
                "grader_python": str(self._sandbox_spec.grader_python),
            }
        )
        reward = native.get("reward")
        if not isinstance(reward, (int, float)) or isinstance(reward, bool):
            raise TypeError("BigCodeBench grader returned a non-numeric reward")
        return EvaluationResult(
            task_id=request.task_id,
            status=EvaluationStatus.COMPLETED,
            metrics={"pass_rate": float(reward)},
            details=details,
        )


__all__ = ["BigCodeBenchEvaluator", "_native_bigcodebench_evaluate"]
