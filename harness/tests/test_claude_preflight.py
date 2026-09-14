# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import json
import subprocess
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from eval_harness.claude_executor import ClaudeExecutor
from eval_harness.errors import HarnessError
from eval_harness.executor import AuthStatus
from eval_harness.models import CLAUDE_DISPLAY_NAMES


def test_native_selection_verifies_exact_model_and_effort_without_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".credentials.json").write_text('{"claudeAiOauth":{}}')
    executor = ClaudeExecutor("fake")
    monkeypatch.setattr(executor, "check_auth", lambda *args: AuthStatus(True, True, "fake subscription"))
    monkeypatch.setattr(executor, "_subscription_access", lambda *args: None)
    calls: list[str] = []
    wrong_effort = False

    def local_command(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        prompt = kwargs["input"]
        calls.append(prompt)
        mode, value = prompt[1:].split(" ", 1)
        assert command[command.index("--tools") + 1] == ""
        settings = json.loads(command[command.index("--settings") + 1])
        assert settings["switchModelsOnFlag"] is False
        assert settings["fallbackModel"] == []
        assert settings["availableModels"] == [command[command.index("--model") + 1]]
        message = (
            f"Set model to `{CLAUDE_DISPLAY_NAMES[value]}` for this session only"
            if mode == "model"
            else f"Set effort level to {'high' if wrong_effort else value} (this session only): description"
        )
        payload = {"num_turns": 0, "local_command": mode, "modelUsage": {}, "result": message}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr("eval_harness.claude_executor.subprocess.run", local_command)
    for model in CLAUDE_DISPLAY_NAMES:
        settings: dict[str, Any] = {"auth_source_home": str(tmp_path)}
        if "haiku" not in model:
            settings["reasoning_effort"] = "medium"
        assert executor.check_runtime(model, settings).authenticated
    assert len(calls) == 9
    wrong_effort = True
    with pytest.raises(HarnessError, match="effort unavailable"):
        executor.check_runtime("claude-opus-5", {"auth_source_home": str(tmp_path), "reasoning_effort": "low"})


def test_native_selection_timeout_is_reported_as_preflight_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".credentials.json").write_text('{"claudeAiOauth": {}}')
    executor = ClaudeExecutor("fake")
    monkeypatch.setattr(executor, "check_auth", lambda *args: AuthStatus(True, True, "fake subscription"))
    monkeypatch.setattr(executor, "_subscription_access", lambda *args: None)

    def timeout(*args: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr("eval_harness.claude_executor.subprocess.run", timeout)
    with pytest.raises(HarnessError, match="preflight timed out"):
        executor.check_runtime(
            "claude-opus-5",
            {"auth_source_home": str(tmp_path), "reasoning_effort": "low"},
        )


@pytest.mark.parametrize(
    ("model", "effort"),
    [("opus", None), ("unknown", None), ("claude-haiku-4-5-20251001", "medium"), ("claude-opus-5", "ultra")],
)
def test_unknown_models_and_efforts_fail_before_auth_or_network(model: str, effort: str | None) -> None:
    with pytest.raises(HarnessError, match="unsupported"):
        ClaudeExecutor("never-invoked").check_runtime(model, {"reasoning_effort": effort})


@pytest.mark.parametrize("extra", [True, None])
def test_subscription_preflight_refuses_metered_or_unknown_billing(
    extra: bool | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = ClaudeExecutor("unused")
    monkeypatch.setattr(executor, "_credentials", lambda *args: {"claudeAiOauth": {"accessToken": "test-credential"}})

    def response(request: Any, **kwargs: Any) -> io.BytesIO:
        if request.full_url.endswith("profile"):
            data = {"organization": {"subscription_status": "active", "has_extra_usage_enabled": extra}}
        else:
            data = {"extra_usage": {"is_enabled": extra}}
        return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr("eval_harness.claude_executor.urllib.request.urlopen", response)
    with pytest.raises(HarnessError, match="extra usage"):
        executor._subscription_access({})


def test_expired_live_auth_is_not_accepted_as_cached_login(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = ClaudeExecutor("unused")
    monkeypatch.setattr(executor, "_credentials", lambda *args: {"claudeAiOauth": {"accessToken": "test-credential"}})

    def expired(*args: Any, **kwargs: Any) -> None:
        raise urllib.error.HTTPError("https://api.anthropic.com/api/oauth/profile", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("eval_harness.claude_executor.urllib.request.urlopen", expired)
    with pytest.raises(HarnessError, match="expired"):
        executor._subscription_access({})


def test_same_account_metadata_is_shared_without_caching_a_different_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ClaudeExecutor, "_subscription_checked", {})
    token = "test-first-credential"
    monkeypatch.setattr(ClaudeExecutor, "_credentials", lambda *args: {"claudeAiOauth": {"accessToken": token}})
    requests: list[str] = []

    def response(request: Any, **kwargs: Any) -> io.BytesIO:
        requests.append(request.full_url)
        return io.BytesIO(
            json.dumps({"organization": {"subscription_status": "active", "has_extra_usage_enabled": False}}).encode()
        )

    monkeypatch.setattr("eval_harness.claude_executor.urllib.request.urlopen", response)
    ClaudeExecutor()._subscription_access({})
    ClaudeExecutor()._subscription_access({})
    assert len(requests) == 1
    token = "test-second-credential"
    ClaudeExecutor()._subscription_access({})
    assert len(requests) == 2
    assert all(url.endswith("/profile") for url in requests)
