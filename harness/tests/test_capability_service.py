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


def _wheel(entries: list[tuple[str, bytes]]) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as package:
        for name, body in entries:
            package.writestr(name, body)
    return payload.getvalue()


def _serve_wheel(service: CapabilityService, monkeypatch: pytest.MonkeyPatch, body: bytes) -> dict[str, str]:
    url = "https://files.pythonhosted.org/packages/example-1.0-py3-none-any.whl"
    monkeypatch.setattr(service.network, "fetch", lambda url: FetchResponse(url, url, 200, "application/zip", body))
    return {"url": url, "sha256": hashlib.sha256(body).hexdigest()}


def _package_snapshot(service: CapabilityService) -> dict[str, tuple[int, bytes | None]]:
    root = service.workspace / ".packages"
    return {
        str(path.relative_to(root)): (path.stat().st_mode, path.read_bytes() if path.is_file() else None)
        for path in root.rglob("*")
    }


def _assert_failed_wheel_evidence(service: CapabilityService, wheel: bytes) -> None:
    assert (service.state / "wheels" / f"{hashlib.sha256(wheel).hexdigest()}.whl").read_bytes() == wheel
    assert not list((service.state / "wheels").glob(".install-*"))
    event = json.loads((service.state / "events.jsonl").read_text().splitlines()[-1])
    assert event["tool"] == "install_wheel" and event["status"] == "failed"
    receipt = json.loads((service.state / "wheels" / f"{event['call_id']}.json").read_text())
    assert receipt["sha256"] == hashlib.sha256(wheel).hexdigest()


def test_wheel_late_conflict_leaves_prior_import_tree_exactly_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    packages = service.workspace / ".packages"
    (packages / "existing").mkdir()
    (packages / "existing" / "conflict.py").write_bytes(b"original module\x00\xff")
    before = _package_snapshot(service)
    wheel = _wheel([("new_package/__init__.py", b"new = True\n"), ("existing/conflict.py", b"replacement")])
    arguments = _serve_wheel(service, monkeypatch, wheel)
    with pytest.raises(CapabilityError, match="already exists"):
        service.invoke("install_wheel", arguments)
    assert _package_snapshot(service) == before
    _assert_failed_wheel_evidence(service, wheel)


def test_wheel_corrupt_late_member_is_crc_checked_before_any_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    (service.workspace / ".packages" / "prior.py").write_bytes(b"prior code")
    before = _package_snapshot(service)
    wheel = _wheel([("new_package/first.py", b"valid"), ("new_package/later.py", b"unique corrupt content")])
    offset = wheel.index(b"unique corrupt content")
    damaged = bytearray(wheel)
    damaged[offset] ^= 1
    wheel = bytes(damaged)
    arguments = _serve_wheel(service, monkeypatch, wheel)
    with pytest.raises(CapabilityError, match="CRC"):
        service.invoke("install_wheel", arguments)
    assert _package_snapshot(service) == before
    _assert_failed_wheel_evidence(service, wheel)


@pytest.mark.parametrize("second", ["module.py", "MODULE.py"])
def test_wheel_duplicate_members_fail_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, second: str
) -> None:
    service = _service(tmp_path)
    if second == "module.py":
        with pytest.warns(UserWarning, match="Duplicate"):
            wheel = _wheel([("module.py", b"first"), (second, b"second")])
    else:
        wheel = _wheel([("module.py", b"first"), (second, b"second")])
    arguments = _serve_wheel(service, monkeypatch, wheel)
    with pytest.raises(CapabilityError, match="duplicate"):
        service.invoke("install_wheel", arguments)
    assert _package_snapshot(service) == {}
    _assert_failed_wheel_evidence(service, wheel)


@pytest.mark.parametrize("path", ["pkg/../other.py", "pkg/./other.py", "pkg//other.py", "/absolute.py"])
def test_wheel_path_aliases_are_rejected_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    service = _service(tmp_path)
    wheel = _wheel([("new.py", b"new"), (path, b"bad")])
    arguments = _serve_wheel(service, monkeypatch, wheel)
    with pytest.raises(CapabilityError, match="traversal"):
        service.invoke("install_wheel", arguments)
    assert _package_snapshot(service) == {}
    _assert_failed_wheel_evidence(service, wheel)


def test_wheel_publication_write_failure_rolls_back_partial_files_and_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    service = _service(tmp_path)
    packages = service.workspace / ".packages"
    (packages / "shared").mkdir()
    (packages / "shared" / "prior.py").write_bytes(b"retain prior")
    before = _package_snapshot(service)
    wheel = _wheel([("shared/new.py", b"new"), ("new_package/deeper/later.py", b"later")])
    arguments = _serve_wheel(service, monkeypatch, wheel)
    original_copy = shutil.copyfileobj

    def fail_during_publication(source: object, sink: object, length: int) -> None:
        from typing import BinaryIO, cast

        destination = Path(cast(BinaryIO, sink).name)
        if destination.is_relative_to(packages) and destination.name == "later.py":
            cast(BinaryIO, sink).write(b"partial failed publication")
            raise OSError("injected disk write failure")
        original_copy(cast(BinaryIO, source), cast(BinaryIO, sink), length)

    monkeypatch.setattr(shutil, "copyfileobj", fail_during_publication)
    with pytest.raises(OSError, match="injected disk write failure"):
        service.invoke("install_wheel", arguments)
    assert _package_snapshot(service) == before
    _assert_failed_wheel_evidence(service, wheel)


def test_wheel_install_accepts_disjoint_files_in_existing_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    packages = service.workspace / ".packages"
    (packages / "namespace").mkdir()
    (packages / "namespace" / "existing.py").write_bytes(b"old")
    wheel = _wheel([("namespace/", b""), ("namespace/new.py", b"new"), ("empty/", b"")])
    arguments = _serve_wheel(service, monkeypatch, wheel)
    result = service.invoke("install_wheel", arguments)
    assert result["files"] == ["namespace/new.py"]
    assert (packages / "namespace" / "existing.py").read_bytes() == b"old"
    assert (packages / "namespace" / "new.py").read_bytes() == b"new"
    assert (packages / "empty").is_dir()
    assert not list((service.state / "wheels").glob(".install-*"))


def test_wheel_digest_failure_preserves_downloaded_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(tmp_path)
    wheel = _wheel([("module.py", b"module")])
    arguments = _serve_wheel(service, monkeypatch, wheel)
    arguments["sha256"] = "0" * 64
    with pytest.raises(CapabilityError, match="SHA256"):
        service.invoke("install_wheel", arguments)
    assert _package_snapshot(service) == {}
    _assert_failed_wheel_evidence(service, wheel)


@pytest.mark.parametrize("policy", ["allowlist", "public_https"])
def test_service_validates_and_passes_network_policy(tmp_path: Path, policy: str) -> None:
    from eval_harness.capability_service import CapabilityConfig

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = CapabilityService(workspace, tmp_path / "state", "application", {"network_policy": policy}, verify=False)
    assert service.network.network_policy == policy
    assert service.probe_result()["network_policy"] == policy
    assert CapabilityConfig.from_mapping({}).network_policy == "allowlist"
    with pytest.raises(CapabilityError, match="network_policy"):
        CapabilityConfig.from_mapping({"network_policy": "anything"})
    with pytest.raises(CapabilityError, match="fetch_timeout_seconds"):
        CapabilityConfig.from_mapping({"fetch_timeout_seconds": float("nan")})


@pytest.mark.parametrize("eventual_success", [True, False])
def test_search_receipt_persists_each_backend_body_on_success_or_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    eventual_success: bool,
) -> None:
    from eval_harness.capability_network import HTTPExchange, NetworkClient, NetworkError

    service = _service(tmp_path)
    service.network = NetworkClient([], network_policy="public_https")
    first_body = b"blocked search response"
    redirect_body = b"redirecting to a challenge"
    second_body = (
        b"<rss><channel><item><title>Public source</title><link>https://www.python.org/</link>"
        b"<description>Relevant</description></item></channel></rss>"
        if eventual_success
        else b"invalid xml"
    )

    def fetch(url: str, **kwargs: object) -> FetchResponse:
        if "duckduckgo" in url:
            final = "https://html.duckduckgo.com/challenge"
            exchanges = (
                HTTPExchange(url, "2026-09-21T00:00:00+00:00", 0.1, 302, "text/html", redirect_body, True),
                HTTPExchange(final, "2026-09-21T00:00:00.1+00:00", 0.2, 403, "text/html", first_body, True),
            )
            return FetchResponse(url, final, 403, "text/html", first_body, (final,), exchanges)
        return FetchResponse(url, url, 200, "text/xml", second_body)

    monkeypatch.setattr(service.network, "fetch", fetch)
    if eventual_success:
        result = service.invoke("search", {"query": "bounded public query"})
        assert result["backend"] == "bing-rss" and len(result["attempts"]) == 2
    else:
        with pytest.raises(NetworkError, match="all configured search backends failed"):
            service.invoke("search", {"query": "bounded public query"})
    research = service.state / "research"
    (receipt_path,) = list(research.glob("*.json"))
    receipt = json.loads(receipt_path.read_text())
    assert receipt["query"] == "bounded public query" and len(receipt["attempts"]) == 2
    first, second = receipt["attempts"]
    assert first["status"] == 403 and first["error"]
    assert first["final_url"] == "https://html.duckduckgo.com/challenge"
    assert first["redirects"] == [first["final_url"]]
    assert first["requested_url"].startswith("https://html.duckduckgo.com/html/?q=")
    assert second["status"] == 200 and bool(second["error"]) is not eventual_success
    for attempt in receipt["attempts"]:
        assert attempt["retrieved_at"].endswith("+00:00") and attempt["request_elapsed_seconds"] >= 0
    saved = [exchange for attempt in receipt["attempts"] for exchange in attempt["exchanges"]]
    assert [exchange["sha256"] for exchange in saved] == [
        hashlib.sha256(body).hexdigest() for body in (redirect_body, first_body, second_body)
    ]
    for exchange, body in zip(saved, (redirect_body, first_body, second_body), strict=True):
        assert (research / exchange["body_file"]).read_bytes() == body
        assert exchange["bytes"] == len(body)
    if not eventual_success:
        assert receipt["error"]


def test_failed_search_retains_transport_failure_without_inventing_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval_harness.capability_network import HTTPExchange, NetworkClient, NetworkError

    service = _service(tmp_path)
    service.network = NetworkClient([], network_policy="public_https")

    def fail(url: str, **kwargs: object) -> FetchResponse:
        raise NetworkError(
            "DNS or TLS failure",
            final_url=url,
            exchanges=(HTTPExchange(url, "2026-09-21T00:00:00+00:00", 0.01, error="TLS failure"),),
        )

    monkeypatch.setattr(service.network, "fetch", fail)
    with pytest.raises(NetworkError, match="all configured search backends failed"):
        service.invoke("search", {"query": "public query"})
    (receipt_path,) = list((service.state / "research").glob("*.json"))
    receipt = json.loads(receipt_path.read_text())
    assert len(receipt["attempts"]) == 2
    for attempt in receipt["attempts"]:
        assert attempt["status"] is None and attempt["error"]
        assert "sha256" not in attempt["exchanges"][0]
    assert not list((service.state / "research").glob("*.bin"))
