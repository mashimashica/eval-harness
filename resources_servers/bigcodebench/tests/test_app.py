# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from collections.abc import Generator
from typing import cast
from unittest.mock import MagicMock

import pytest
import resources_servers.bigcodebench.app as app_module
from resources_servers.bigcodebench.app import (
    BigCodeBenchResourcesServer,
    BigCodeBenchResourcesServerConfig,
    BigCodeBenchVerifyRequest,
    BigCodeBenchVerifyResponse,
)
from resources_servers.bigcodebench.code_extraction import preprocess_code_completion
from fastapi.testclient import TestClient
from _pytest.monkeypatch import MonkeyPatch

from eval_harness.grader_sandbox import GraderSandboxPreflight, GraderSandboxSpec
from nemo_gym.openai_utils import NeMoGymResponse
from nemo_gym.server_utils import ServerClient


# ---------------------------------------------------------------------------
# code_extraction (Skills' preprocess_code parity)
# ---------------------------------------------------------------------------


class TestPreprocessCodeCompletion:
    """Skills' preprocess_code edge cases — must match byte-for-byte."""

    def test_python_fence_basic(self):
        text = "Some preamble.\n```python\ndef f():\n    return 42\n```"
        assert preprocess_code_completion(text) == "def f():\n    return 42"

    def test_picks_last_python_fence(self):
        text = (
            "First attempt:\n```python\ndef f():\n    return 1\n```\n"
            "Final answer:\n```python\ndef f():\n    return 42\n```"
        )
        out = preprocess_code_completion(text)
        assert "return 42" in out
        assert "return 1" not in out

    def test_generic_fence_with_no_python_fence_returns_empty(self):
        # Quirk of Skills' preprocess_code (ported byte-for-byte): when no
        # ```python fence is present, the fallback uses str.rfind on the
        # generic ``` token. For a generic-only block, rfind returns the
        # position of the *closing* fence, the slice points past end-of-string,
        # and the function returns "". Bigcodebench's prompt explicitly asks
        # for ```python so the generic-only path is never hit in practice;
        # we encode the actual behaviour to keep parity with Skills.
        text = "```\nprint('hi')\n```"
        assert preprocess_code_completion(text) == ""

    def test_strips_think_block(self):
        text = "<think>reasoning here</think>\n```python\nx = 1\n```"
        assert preprocess_code_completion(text) == "x = 1"

    def test_unclosed_think_keeps_raw_text(self):
        # Skills' preprocess_code only enters the </think> strip branch when
        # the closing tag IS present in the completion. With a missing closing
        # tag, the raw text falls through to the fence-extraction step
        # untouched. (The else branch in Skills' code is unreachable — guarded
        # by the outer ``if "</think>" in completion``.)
        assert preprocess_code_completion("<think>never closed reasoning") == "<think>never closed reasoning"

    def test_unclosed_fence_strict_mode_returns_empty(self):
        text = "```python\ndef f(): return 1\n# no closer here"
        assert preprocess_code_completion(text) == ""

    def test_no_fence_returns_raw_after_strip(self):
        # No fence → no extraction; whole completion returned (stripped).
        assert preprocess_code_completion("  print('hi')  ") == "print('hi')"

    def test_empty_input(self):
        assert preprocess_code_completion("") == ""
        assert preprocess_code_completion(None) == ""

    def test_carriage_returns_stripped(self):
        text = "```python\r\nx = 1\r\n```"
        assert preprocess_code_completion(text) == "x = 1"


# ---------------------------------------------------------------------------
# BigCodeBenchResourcesServer
# ---------------------------------------------------------------------------


def _make_response(text: str) -> NeMoGymResponse:
    return NeMoGymResponse(
        id="resp",
        created_at=0.0,
        model="dummy",
        object="response",
        output=[
            {
                "id": "msg",
                "content": [{"annotations": [], "text": text, "type": "output_text"}],
                "role": "assistant",
                "status": "completed",
                "type": "message",
            }
        ],
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
    )


_META = {
    "task_id": "BigCodeBench/0",
    "code_prompt": "def task_func(x):\n",
    "test": (
        "import unittest\n"
        "class TestCases(unittest.TestCase):\n"
        "    def test_one(self):\n"
        "        self.assertEqual(task_func(2), 4)\n"
    ),
    "entry_point": "task_func",
}


@pytest.fixture(scope="module")
def server(monkeypatch_module: MonkeyPatch) -> BigCodeBenchResourcesServer:
    resource_dir = Path(__file__).resolve().parents[1]
    sandbox_spec = MagicMock(spec=GraderSandboxSpec)
    sandbox_preflight = GraderSandboxPreflight(
        ok=True,
        sandbox_version="0.12.0",
        policy_revision="bigcodebench-bwrap-v1",
        spec_sha256="spec",
        manifest_sha256="manifest",
        attestation_sha256="attestation",
        details=(),
    )
    monkeypatch_module.setattr(app_module, "resolve_bigcodebench_resource_dir", lambda: resource_dir)
    monkeypatch_module.setattr(app_module, "resolve_bigcodebench_sandbox_spec", lambda _: sandbox_spec)
    monkeypatch_module.setattr(app_module, "preflight_bigcodebench_sandbox", lambda _: sandbox_preflight)
    return BigCodeBenchResourcesServer(
        config=BigCodeBenchResourcesServerConfig(
            host="0.0.0.0",
            port=8080,
            entrypoint="",
            name="",
        ),
        server_client=cast(ServerClient, MagicMock(spec=ServerClient)),
    )


@pytest.fixture(scope="module")
def monkeypatch_module() -> Generator[None, None, None]:
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def client(server: BigCodeBenchResourcesServer) -> Generator[TestClient, None, None]:
    app = server.setup_webserver()
    with TestClient(app) as c:
        yield c


def test_verify_pass(client: TestClient, monkeypatch_module: MonkeyPatch) -> None:
    def fake_run(self: BigCodeBenchResourcesServer, code: str, test_code: str, entry_point: str, task_id: str) -> dict[str, object]:
        del code, test_code, entry_point, task_id
        return {"status": "passed", "details": {}}

    monkeypatch_module.setattr(BigCodeBenchResourcesServer, "_run_sandbox", fake_run)

    req = BigCodeBenchVerifyRequest(
        responses_create_params={"input": [{"role": "user", "content": "double x"}]},
        response=_make_response("```python\ndef task_func(x):\n    return x*2\n```"),
        verifier_metadata=_META,
    )
    resp = client.post("/verify", json=req.model_dump())
    res = BigCodeBenchVerifyResponse.model_validate(cast(dict[str, object], resp.json()))
    assert res.reward == 1.0
    assert res.status == "passed"
    assert "task_func" in res.extracted_model_code
    assert res.task_id == "BigCodeBench/0"


def test_verify_fail(client: TestClient, monkeypatch_module: MonkeyPatch) -> None:
    def fake_run(self: BigCodeBenchResourcesServer, code: str, test_code: str, entry_point: str, task_id: str) -> dict[str, object]:
        del code, test_code, entry_point, task_id
        return {"status": "failed_tests", "details": {"test_one": "AssertionError: 5 != 4"}}

    monkeypatch_module.setattr(BigCodeBenchResourcesServer, "_run_sandbox", fake_run)

    req = BigCodeBenchVerifyRequest(
        responses_create_params={"input": [{"role": "user", "content": "double x"}]},
        response=_make_response("```python\ndef task_func(x):\n    return x+3\n```"),
        verifier_metadata=_META,
    )
    resp = client.post("/verify", json=req.model_dump())
    res = BigCodeBenchVerifyResponse.model_validate(cast(dict[str, object], resp.json()))
    assert res.reward == 0.0
    assert res.status == "failed_tests"


def test_empty_output_short_circuits(client: TestClient, monkeypatch_module: MonkeyPatch) -> None:
    # No subprocess invocation should happen when output is empty.
    def fake_run(self: BigCodeBenchResourcesServer, code: str, test_code: str, entry_point: str, task_id: str) -> dict[str, object]:
        del code, test_code, entry_point, task_id
        raise AssertionError("subprocess should not be invoked for empty output")

    monkeypatch_module.setattr(BigCodeBenchResourcesServer, "_run_sandbox", fake_run)

    req = BigCodeBenchVerifyRequest(
        responses_create_params={"input": [{"role": "user", "content": "x"}]},
        response=_make_response(""),
        verifier_metadata=_META,
    )
    resp = client.post("/verify", json=req.model_dump())
    res = BigCodeBenchVerifyResponse.model_validate(cast(dict[str, object], resp.json()))
    assert res.reward == 0.0
    assert res.status == "empty_output"


def test_unclosed_fence_returns_no_code_block(client: TestClient, monkeypatch_module: MonkeyPatch) -> None:
    def fake_run(self: BigCodeBenchResourcesServer, code: str, test_code: str, entry_point: str, task_id: str) -> dict[str, object]:
        del code, test_code, entry_point, task_id
        raise AssertionError("subprocess should not be invoked when extraction returns ''")

    monkeypatch_module.setattr(BigCodeBenchResourcesServer, "_run_sandbox", fake_run)

    req = BigCodeBenchVerifyRequest(
        responses_create_params={"input": [{"role": "user", "content": "x"}]},
        response=_make_response("```python\ndef task_func(x):\n    return x*2"),
        verifier_metadata=_META,
    )
    resp = client.post("/verify", json=req.model_dump())
    res = BigCodeBenchVerifyResponse.model_validate(cast(dict[str, object], resp.json()))
    assert res.reward == 0.0
    assert res.status == "no_code_block"


def test_score_fn() -> None:
    assert BigCodeBenchResourcesServer._score_fn({"reward": 1.0}) == {"accuracy": 1.0}
    assert BigCodeBenchResourcesServer._score_fn({"reward": 0.0}) == {"accuracy": 0.0}


def test_compute_metrics_pass_at_k(server: BigCodeBenchResourcesServer) -> None:
    tasks = [
        [
            {"reward": 1.0, "extracted_model_code": "code_a"},
            {"reward": 0.0, "extracted_model_code": "code_b"},
        ],
        [
            {"reward": 0.0, "extracted_model_code": "code_c"},
            {"reward": 0.0, "extracted_model_code": "code_d"},
        ],
    ]
    metrics = server.compute_metrics(tasks)
    # Expect pass@1[avg-of-k] and pass@k entries for accuracy.
    assert any(k.startswith("pass@1[avg-of-") for k in metrics)
    assert any(k.startswith("pass@2") for k in metrics)


def test_get_key_metrics_picks_pass_at_1_avg() -> None:
    agent_metrics = {
        "mean/input_tokens": 100,
        "mean/output_tokens": 200,
        "pass@1[avg-of-4]/accuracy": 0.5,
        "pass@4/accuracy": 0.75,
        "majority@4/accuracy": 0.6,
    }
    server_cls = BigCodeBenchResourcesServer
    # ``get_key_metrics`` is an instance method, but it doesn't read self —
    # call with a stub instance.
    stub = MagicMock(spec=server_cls)
    key = server_cls.get_key_metrics(stub, agent_metrics)
    assert "mean/input_tokens" in key
    assert "mean/output_tokens" in key
    assert any("pass@1[avg-of-4]" in k for k in key)
