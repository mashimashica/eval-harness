# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from eval_harness.capability_network import FetchResponse
from eval_harness.capability_service import CapabilityError, CapabilityService, finalize_interrupted_calls


def _service(tmp_path: Path, *, role: str = "application") -> CapabilityService:
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    workspace.mkdir()
    return CapabilityService(workspace, state, role, {"network_domains": []}, verify=False)


def test_mcp_initialize_tools_and_notifications(tmp_path: Path) -> None:
    service = _service(tmp_path)
    initialize = service.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert initialize is not None
    assert initialize["result"]["serverInfo"]["name"] == "eval-harness-capability"
    listed = service.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert listed is not None
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {"fetch", "search", "view_image", "install_wheel"}.issubset(names)
    assert service.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    failed = service.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "fetch", "arguments": {"url": "http://127.0.0.1/secret"}},
        }
    )
    assert failed is not None and failed["result"]["isError"] is True
    event = json.loads((service.state / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event["tool"] == "fetch" and event["failure"]


def test_view_image_returns_native_content_and_records_crop(tmp_path: Path) -> None:
    service = _service(tmp_path)
    image_path = service.workspace / "image.png"
    from PIL import Image

    Image.new("RGB", (8, 6), "red").save(image_path)
    content = service.invoke("view_image", {"path": "image.png", "region": [1, 2, 5, 6]})
    assert content[0]["type"] == "text"
    metadata = json.loads(content[0]["text"])
    assert metadata["width"] == 8 and metadata["height"] == 6
    assert metadata["crop"] == [1, 2, 5, 6]
    assert content[1]["type"] == "image" and content[1]["mimeType"] == "image/png"
    assert list((service.state / "derived" / "images").glob("*.png"))
    with pytest.raises(CapabilityError, match="region"):
        service.invoke("view_image", {"path": "image.png", "region": [0, 0, 9, 1]})


def test_install_wheel_validates_digest_and_archive_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(tmp_path)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as package:
        package.writestr("example/__init__.py", "value = 1\n")
        package.writestr("example-1.0.dist-info/METADATA", "Metadata-Version: 2.1\n")
    wheel = payload.getvalue()
    response = FetchResponse(
        requested_url="https://files.pythonhosted.org/packages/example-1.0-py3-none-any.whl",
        final_url="https://files.pythonhosted.org/packages/example-1.0-py3-none-any.whl",
        status=200,
        content_type="application/octet-stream",
        body=wheel,
    )
    monkeypatch.setattr(service.network, "fetch", lambda url: response)
    result = service.invoke(
        "install_wheel",
        {"url": response.requested_url, "sha256": hashlib.sha256(wheel).hexdigest()},
    )
    assert result["file_count"] == 2
    assert (service.workspace / ".packages" / "example" / "__init__.py").read_text(encoding="utf-8") == "value = 1\n"

    bad_payload = io.BytesIO()
    with zipfile.ZipFile(bad_payload, "w") as package:
        package.writestr("../escape.py", "bad")
    bad = bad_payload.getvalue()
    bad_response = FetchResponse(response.requested_url, response.final_url, 200, response.content_type, bad)
    monkeypatch.setattr(service.network, "fetch", lambda url: bad_response)
    with pytest.raises(CapabilityError, match="traversal"):
        service.invoke("install_wheel", {"url": response.requested_url, "sha256": hashlib.sha256(bad).hexdigest()})


def test_finalize_interrupted_calls_preserves_partial_tail_and_surfaces_warning(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    journal = state / "events.jsonl"
    started = {
        "event": "started",
        "terminal": False,
        "call_id": "000001-call",
        "tool": "shell",
        "arguments": {"command": "sleep"},
        "started_at": "2026-09-16T00:00:00+00:00",
    }
    journal.write_bytes(
        (json.dumps(started, sort_keys=True) + "\n").encode() + b'{"event":"started","call_id":"partial"'
    )
    assert finalize_interrupted_calls(state) == ["000001-call"]
    lines = journal.read_bytes().splitlines()
    assert lines[1] == b'{"event":"started","call_id":"partial"'
    terminal = json.loads(lines[-1])
    assert terminal["status"] == "interrupted"
    assert terminal["journal_invalid_line_count"] == 1
