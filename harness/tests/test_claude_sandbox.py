# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from eval_harness import claude_sandbox
from eval_harness.claude_executor import ClaudeExecutor
from eval_harness.errors import HarnessError
from eval_harness.executor import RuntimeSession


@pytest.mark.parametrize("read_only", [False, True])
def test_native_bash_invocation_is_fail_closed_and_restores_private_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, read_only: bool
) -> None:
    for name in ("work", "claude", "home"):
        (tmp_path / name).mkdir()
    session = RuntimeSession(
        {"HOME": str(tmp_path / "home"), "TMPDIR": str(tmp_path)}, tmp_path / "work", tmp_path / "claude"
    )
    original = dict(session.environment)
    temporary_directory = tempfile.TemporaryDirectory
    monkeypatch.setattr(
        "eval_harness.claude_executor.tempfile.TemporaryDirectory",
        lambda **kwargs: temporary_directory(prefix=kwargs["prefix"], dir=tmp_path),
    )
    monkeypatch.setattr("eval_harness.claude_executor.sys.platform", "darwin")
    monkeypatch.setattr(claude_sandbox, "copy_office_runtime", lambda path: path / "bin/python-openpyxl")
    captured: dict[str, Any] = {}

    def status(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command[-2:] == ["sandbox", "status"]
        assert "--tools=Bash" in command and "--allowedTools=Bash" in command
        assert any(arg.startswith("--disallowedTools=Read,Write,Edit") for arg in command)
        assert kwargs["stdin"] == subprocess.DEVNULL
        captured.update(json.loads(Path(command[command.index("--settings") + 1]).read_text()))
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"supported": True, "enabled": True, "strictMode": True, "filesystemPolicy": "strict"}),
        )

    monkeypatch.setattr(claude_sandbox.subprocess, "run", status)
    with pytest.raises(RuntimeError, match="participant interrupted"):
        with ClaudeExecutor("fake")._invocation(
            session, "claude-opus-5", {"tool_mode": "sandboxed_shell"}, "evaluation" if read_only else "application"
        ) as (options, receipt):
            scratch = Path(session.environment["TMPDIR"])
            assert scratch == Path(session.environment["CLAUDE_CODE_TMPDIR"])
            assert scratch.is_dir() and scratch.stat().st_mode & 0o777 == 0o700
            assert receipt and receipt["sandbox_enabled"] and receipt["sandbox_strict"]
            assert "--append-system-prompt" in options
            raise RuntimeError("participant interrupted")
    assert session.environment == original
    assert not scratch.exists()
    policy = captured["sandbox"]
    assert policy["failIfUnavailable"] and not policy["allowUnsandboxedCommands"]
    assert policy["filesystem"]["denyRead"] == ["/"]
    assert str(tmp_path / "work/reference_files") in policy["filesystem"]["denyWrite"]
    assert (str(tmp_path) in policy["filesystem"]["denyWrite"]) == read_only
    assert policy["network"]["allowedDomains"] == []
    assert captured["fallbackModel"] == []


@pytest.mark.parametrize(
    "payload", [{}, {"enabled": True, "supported": True, "strictMode": False, "filesystemPolicy": "strict"}]
)
def test_unconfirmed_sandbox_status_prevents_participant_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    session = RuntimeSession({}, tmp_path, tmp_path)
    monkeypatch.setattr(
        claude_sandbox.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload)),
    )
    with pytest.raises(HarnessError, match="strict sandbox is unavailable"):
        claude_sandbox.verify_sandbox(["fake"], session)
