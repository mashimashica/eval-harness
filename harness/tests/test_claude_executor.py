# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Claude stream normalization and explicit file-tool/account boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_harness.claude_executor import ClaudeExecutor, parse_claude_jsonl
from eval_harness.errors import HarnessError
from eval_harness.executor import AuthStatus, ExecutionRequest


def test_result_usage_preserves_missing_and_reported_cost() -> None:
    result = parse_claude_jsonl(
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "answer",
                "usage": {"input_tokens": 10, "output_tokens": 2},
                "total_cost_usd": 0.001,
            }
        )
    )
    assert result.terminal_completed
    assert result.final_text == "answer"
    assert result.usage["input_tokens"] == 10
    assert result.usage["cost_usd"] is None
    assert result.usage["reported_cost_usd"] == 0.001
    assert result.usage["cached_input_tokens"] is None


def test_failed_result_never_becomes_completed() -> None:
    result = parse_claude_jsonl('{"type":"result","subtype":"error_max_turns","is_error":true}')
    assert not result.terminal_completed
    assert result.errors == ("error_max_turns",)
    assert result.usage["cost_usd"] is None


def test_structured_result_replaces_prose_with_canonical_json() -> None:
    result = parse_claude_jsonl(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "I inspected the file."}]},
                    }
                ),
                json.dumps(
                    {
                        "type": "result",
                        "subtype": "success",
                        "is_error": False,
                        "result": "I inspected the file. ```json {bad} ```",
                        "structured_output": {"score": 0.5, "rationale": "Observed saved evidence."},
                    }
                ),
            ]
        ),
        require_structured_output=True,
    )
    assert result.terminal_completed
    assert result.errors == ()
    assert result.final_text == '{"rationale":"Observed saved evidence.","score":0.5}'
    assert result.assistant_messages == ("I inspected the file.",)


def test_missing_structured_result_fails_closed() -> None:
    result = parse_claude_jsonl(
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "prose only"}),
        require_structured_output=True,
    )
    assert result.final_text == ""
    assert result.errors == ("Claude structured output was missing",)


def test_session_copies_only_oauth_and_no_ambient_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / ".credentials.json").write_text('{"claudeAiOauth": {}, "unrelated": "private"}')
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-fixture")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    executor = ClaudeExecutor("unused")
    with executor._session({"auth_source_home": str(credentials)}) as session:
        assert "ANTHROPIC_API_KEY" not in session.environment
        assert "CLAUDE_CODE_USE_BEDROCK" not in session.environment
        copied = session.config_home / ".credentials.json"
        assert json.loads(copied.read_text()) == {"claudeAiOauth": {}}
        assert copied.stat().st_mode & 0o777 == 0o600
        assert not session.workspace.is_relative_to(tmp_path)
        root = session.workspace.parent
    assert not root.exists()
    (credentials / ".credentials.json").write_text('{"apiKey": "test-fixture"}')
    with pytest.raises(HarnessError, match="OAuth"):
        executor._credentials({"auth_source_home": str(credentials)})


def test_execution_only_exposes_confined_file_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ClaudeExecutor, "check_runtime", lambda *args: AuthStatus(True, True, "test preflight"))
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / ".credentials.json").write_text('{"claudeAiOauth": {}}')
    binary = tmp_path / "fake-claude"
    binary.write_text("""#!/usr/bin/env python3
import json, pathlib, sys
sys.stdin.read()
pathlib.Path("answer.txt").write_text("42")
print(json.dumps({"type":"result","subtype":"success","is_error":False,"result":"42"}))
""")
    binary.chmod(0o700)
    workspace = tmp_path / "condition-hidden"
    workspace.mkdir()
    result = ClaudeExecutor(str(binary)).execute(
        ExecutionRequest("task", workspace, "recorded-model", {"auth_source_home": str(credentials)}, "application")
    )
    assert result.status == "completed"
    assert (workspace / "answer.txt").read_text() == "42"
    assert "--safe-mode" in result.command
    assert "--restricted" in result.command
    assert "--bare" not in result.command
    assert "Bash" not in " ".join(result.command)
    assert "WebFetch" not in " ".join(result.command)


def test_execution_passes_json_schema_and_uses_native_structured_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ClaudeExecutor, "check_runtime", lambda *args: AuthStatus(True, True, "test preflight"))
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / ".credentials.json").write_text('{"claudeAiOauth": {}}')
    binary = tmp_path / "fake-claude"
    binary.write_text(
        """#!/usr/bin/env python3
import json, sys
sys.stdin.read()
schema = json.loads(sys.argv[sys.argv.index('--json-schema') + 1])
assert schema['properties']['winner']['enum'][-1] == 'unjudgeable'
print(json.dumps({'type':'result','subtype':'success','is_error':False,
                  'result':'prose and a fenced object',
                  'structured_output':{'winner':'tie','rationale':'Native result'}}))
"""
    )
    binary.chmod(0o700)
    workspace = tmp_path / "work"
    workspace.mkdir()
    schema = {
        "type": "object",
        "properties": {
            "winner": {"type": "string", "enum": ["A", "B", "tie", "unjudgeable"]},
            "rationale": {"type": "string"},
        },
        "required": ["winner", "rationale"],
        "additionalProperties": False,
    }
    result = ClaudeExecutor(str(binary)).execute(
        ExecutionRequest(
            "judge", workspace, "recorded-model", {"auth_source_home": str(credentials)}, "evaluation", schema
        )
    )
    assert result.status == "completed"
    assert "--json-schema" in result.command
    assert result.parsed.final_text == '{"rationale":"Native result","winner":"tie"}'


def test_judge_has_no_write_tools_and_refuses_model_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ClaudeExecutor, "check_runtime", lambda *args: AuthStatus(True, True, "test preflight"))
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / ".credentials.json").write_text('{"claudeAiOauth": {}}')
    binary = tmp_path / "fake-claude"
    binary.write_text("""#!/usr/bin/env python3
import json, sys
sys.stdin.read()
assert sys.argv[sys.argv.index('--tools')+1] == 'Read,Glob,Grep'
print(json.dumps({"type":"system","subtype":"init","model":"unexpected-model"}))
print(json.dumps({"type":"result","subtype":"success","is_error":False,"result":"42"}))
""")
    binary.chmod(0o700)
    workspace = tmp_path / "work"
    workspace.mkdir()
    result = ClaudeExecutor(str(binary)).execute(
        ExecutionRequest("judge", workspace, "recorded-model", {"auth_source_home": str(credentials)}, "evaluation")
    )
    assert result.status == "failed"
    assert result.error and "model changed" in result.error
