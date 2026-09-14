# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Claude stream normalization and explicit file-tool/account boundaries."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest

from eval_harness.claude_executor import ClaudeExecutor, parse_claude_jsonl
from eval_harness.errors import HarnessError
from eval_harness.executor import AuthStatus, ExecutionRequest


def valid_png(payload: bytes) -> bytes:
    def chunk(kind: bytes, value: bytes) -> bytes:
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00" + payload))
        + chunk(b"IEND", b"")
    )


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


def test_evaluation_sends_exact_native_image_payload_and_redacted_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ClaudeExecutor, "check_runtime", lambda *args: AuthStatus(True, True, "test preflight"))
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / ".credentials.json").write_text('{"claudeAiOauth": {}}')
    workspace = tmp_path / "work"
    workspace.mkdir()
    image = valid_png(b"native-payload")
    (workspace / "preview.png").write_bytes(image)
    encoded = base64.b64encode(image).decode("ascii")
    binary = tmp_path / "fake-claude"
    binary.write_text(
        """#!/usr/bin/env python3
import base64, json, sys
payload = json.loads(sys.stdin.read())
assert payload['type'] == 'user'
assert payload['message']['role'] == 'user'
assert payload['parent_tool_use_id'] is None
assert payload['session_id'] == ''
content = payload['message']['content']
assert content[0] == {'type':'text','text':'Image 1: preview.png'}
assert content[1]['type'] == 'image'
assert content[1]['source']['type'] == 'base64'
assert content[1]['source']['media_type'] == 'image/png'
assert base64.b64decode(content[1]['source']['data']) == bytes.fromhex(%r)
print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':'42'}))
"""
        % image.hex()
    )
    binary.chmod(0o700)

    result = ClaudeExecutor(str(binary)).execute(
        ExecutionRequest(
            "Image 1: preview.png",
            workspace,
            "recorded-model",
            {"auth_source_home": str(credentials)},
            "evaluation",
            images=(Path("preview.png"),),
        )
    )

    assert result.status == "completed"
    assert "--input-format" in result.command
    assert result.command[result.command.index("--input-format") + 1] == "stream-json"
    assert result.command[result.command.index("--tools") + 1] == "Read,Glob,Grep"
    assert "Write" not in result.command and "Edit" not in result.command
    receipt = result.parsed.events[0]
    assert receipt["type"] == "harness.image_input"
    assert receipt["images"][0]["sha256"] == hashlib.sha256(image).hexdigest()
    assert encoded not in result.stdout
    assert (workspace / "preview.png").read_bytes() == image


def test_invalid_image_is_rejected_before_claude_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / ".credentials.json").write_text('{"claudeAiOauth": {}}')
    workspace = tmp_path / "work"
    workspace.mkdir()
    image = workspace / "preview.png"
    image.write_bytes(valid_png(b"invalid"))
    called = False

    def preflight(*args: object) -> AuthStatus:
        nonlocal called
        called = True
        raise AssertionError("preflight must not run for an application image request")

    monkeypatch.setattr(ClaudeExecutor, "check_runtime", preflight)
    with pytest.raises(HarnessError, match="evaluation"):
        ClaudeExecutor("unused").execute(
            ExecutionRequest(
                "task",
                workspace,
                "recorded-model",
                {"auth_source_home": str(credentials)},
                "application",
                images=(Path("preview.png"),),
            )
        )
    assert not called
