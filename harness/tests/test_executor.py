# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Trusted fake-CLI checks; native runtime evidence is recorded separately."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

import pytest

from eval_harness.errors import HarnessError
from eval_harness.executor import CodexExecutor, ExecutionRequest, parse_codex_jsonl


def fake_cli(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake-codex"
    script.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        "if '--version' in sys.argv:\n    print('codex-cli 0.154.0')\n    sys.exit(0)\n" + body
    )
    script.chmod(0o700)
    return script


def auth_source(tmp_path: Path, mode: str = "chatgpt") -> Path:
    root = tmp_path / "auth-source"
    root.mkdir()
    (root / "auth.json").write_text(json.dumps({"auth_mode": mode}))
    return root


def test_auth_accepts_exact_account_status_on_stderr(tmp_path: Path) -> None:
    source = auth_source(tmp_path)
    binary = fake_cli(tmp_path, 'import sys\nprint("Logged in using ChatGPT", file=sys.stderr)\n')
    result = CodexExecutor(str(binary)).check_auth({"auth_source_home": str(source)})
    assert result.authenticated


def test_api_login_is_not_account_authentication(tmp_path: Path) -> None:
    binary = fake_cli(tmp_path, 'print("Logged in using an API key")\n')
    source = auth_source(tmp_path)
    assert not CodexExecutor(str(binary)).check_auth({"auth_source_home": str(source)}).authenticated
    (source / "auth.json").write_text('{"auth_mode": "apikey"}')
    assert not CodexExecutor(str(binary)).check_auth({"auth_source_home": str(source)}).authenticated


def test_session_excludes_ambient_context_and_denies_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = auth_source(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-not-a-real-secret")
    monkeypatch.setenv("CODEX_THREAD_ID", "unrelated-session")
    monkeypatch.setenv("AWS_PROFILE", "unrelated-profile")
    executor = CodexExecutor("unused")
    with executor._session({"auth_source_home": str(source)}) as session:
        assert not {"OPENAI_API_KEY", "CODEX_THREAD_ID", "AWS_PROFILE"} & session.environment.keys()
        assert not session.workspace.is_relative_to(tmp_path)
        config = tomllib.loads((session.config_home / "config.toml").read_text())
        assert config["forced_login_method"] == "chatgpt"
        assert config["permissions"]["participant"]["filesystem"][str(session.config_home)] == "deny"
        assert config["permissions"]["participant"]["network"]["enabled"] is False
        assert config["features"]["multi_agent"] is False
        assert len(config["skills"]["config"]) == 5
        assert all(not skill["enabled"] for skill in config["skills"]["config"])
        assert (session.config_home / "auth.json").stat().st_mode & 0o777 == 0o600
        temporary = session.workspace.parent
    assert not temporary.exists()


def test_execution_stages_only_inputs_and_captures_artifact(tmp_path: Path) -> None:
    source = auth_source(tmp_path)
    workspace = tmp_path / "condition-sensitive-name"
    workspace.mkdir()
    (workspace / "input.txt").write_text("intended input")
    binary = fake_cli(
        tmp_path,
        """import json, pathlib, sys
sys.stdin.read()
assert pathlib.Path("input.txt").read_text() == "intended input"
pathlib.Path("answer.txt").write_text("result")
print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"done"}}))
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":2}}))
""",
    )
    request = ExecutionRequest("task", workspace, "recorded-model", {"auth_source_home": str(source)}, "application")
    result = CodexExecutor(str(binary)).execute(request)
    assert result.status == "completed"
    assert (workspace / "answer.txt").read_text() == "result"
    assert result.parsed.usage["input_tokens"] == 10
    assert result.parsed.usage["cost_usd"] is None
    assert "condition-sensitive-name" not in " ".join(result.command)
    assert "--strict-config" in result.command


def test_execution_passes_output_schema_outside_participant_workspace(tmp_path: Path) -> None:
    source = auth_source(tmp_path)
    binary = fake_cli(
        tmp_path,
        """import json, pathlib, sys
sys.stdin.read()
schema_path = pathlib.Path(sys.argv[sys.argv.index('--output-schema') + 1])
schema = json.loads(schema_path.read_text())
assert schema['properties']['score']['maximum'] == 1
assert not schema_path.parent.joinpath('work').exists()
response = json.dumps({'score': 0.5, 'rationale': 'native schema'})
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':response}}))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}))
""",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = CodexExecutor(str(binary)).execute(
        ExecutionRequest(
            "judge",
            workspace,
            "recorded-model",
            {"auth_source_home": str(source)},
            "evaluation",
            {"type": "object", "properties": {"score": {"type": "number", "maximum": 1}}},
        )
    )
    assert result.status == "completed"
    assert "--output-schema" in result.command
    assert result.parsed.final_text == '{"score": 0.5, "rationale": "native schema"}'


def test_exit_zero_without_terminal_completion_is_failure(tmp_path: Path) -> None:
    source = auth_source(tmp_path)
    binary = fake_cli(tmp_path, 'import sys\nsys.stdin.read()\nprint("premature exit")\n')
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = CodexExecutor(str(binary)).execute(
        ExecutionRequest("task", workspace, "model", {"auth_source_home": str(source)}, "application")
    )
    assert result.status == "failed"
    assert result.returncode == 0
    assert result.parsed.usage["input_tokens"] is None


@pytest.mark.skipif(os.name != "posix", reason="process-group lifecycle uses POSIX")
def test_timeout_preserves_partial_files(tmp_path: Path) -> None:
    source = auth_source(tmp_path)
    binary = fake_cli(
        tmp_path, 'import pathlib,time\npathlib.Path("partial.txt").write_text("partial")\ntime.sleep(30)\n'
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = CodexExecutor(str(binary)).execute(
        ExecutionRequest(
            "task", workspace, "model", {"auth_source_home": str(source), "timeout_seconds": 1}, "application"
        )
    )
    assert result.status == "timeout"
    assert result.elapsed_seconds < 5
    assert (workspace / "partial.txt").read_text() == "partial"


def test_usage_missing_fields_stay_unknown() -> None:
    result = parse_codex_jsonl('{"type":"turn.completed","usage":{"output_tokens":0}}\n')
    assert result.usage["output_tokens"] == 0
    assert result.usage["input_tokens"] is None
    assert result.usage["cost_usd"] is None


def test_evaluation_rejects_input_mutation(tmp_path: Path) -> None:
    source = auth_source(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "submission.txt").write_text("original")
    binary = fake_cli(
        tmp_path,
        "import pathlib,sys\nsys.stdin.read()\n"
        'pathlib.Path("submission.txt").write_text("replacement")\n'
        'print(\'{"type":"turn.completed"}\')\n',
    )
    executor = CodexExecutor(str(binary))
    with executor._session({"auth_source_home": str(source)}, read_only=True) as session:
        config = tomllib.loads((session.config_home / "config.toml").read_text())
        assert config["permissions"]["participant"]["filesystem"][":workspace_roots"] == "read"
    result = executor.execute(
        ExecutionRequest("judge", workspace, "model", {"auth_source_home": str(source)}, "evaluation")
    )
    assert result.status == "failed"
    assert result.error == "evaluator modified the read-only input workspace"


def test_permission_overrides_cannot_expose_withheld_inputs(tmp_path: Path) -> None:
    executor = CodexExecutor("unused")
    with pytest.raises(HarnessError, match="filesystem overrides"):
        with executor._session({"toolchain_read_paths": [str(tmp_path)]}):
            pytest.fail("untrusted configuration must be rejected before creating a session")
