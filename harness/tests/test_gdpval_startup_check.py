# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".agents/development/scripts/gdpval_startup_check.py"
SPEC = importlib.util.spec_from_file_location("gdpval_startup_check_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
startup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(startup)
REVISION = "a" * 40
SOURCE_HASH = "b" * 64
NAME = "reference_files/group/provided.txt"
CONTENT = b"Complete provided artifact\n"


def metadata_item(*, lfs: bool = False, name: str = NAME, content: bytes = CONTENT) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": name,
        "type": "file",
        "size": len(content),
        "oid": hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest(),
    }
    if lfs:
        result["lfs"] = {"oid": hashlib.sha256(content).hexdigest(), "size": len(content)}
    return result


class Response(io.BytesIO):
    def __init__(self, data: bytes, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Length": str(len(data))} if headers is None else headers
        self.url = "https://cdn.example/provided?transient-signature=do-not-retain"


def mock_response(monkeypatch: pytest.MonkeyPatch, data: bytes, **kwargs: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def open_response(request: urllib.request.Request, timeout: float, *, metadata: bool) -> Response:
        calls.append({"request": request, "timeout": timeout, "metadata": metadata})
        response = Response(data, **kwargs)
        if metadata:
            response.url = request.full_url
        return response

    monkeypatch.setattr(startup, "_open_response", open_response)
    return calls


def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("unexpected network access")

    monkeypatch.setattr(startup, "_open_response", fail)


def acquire(tmp_path: Path, objects: dict[str, Any], *, fetch: bool = True, limit: int = 1000) -> dict[str, Any]:
    records = startup.acquire({"reference_files": [NAME]}, tmp_path / "provided", REVISION, fetch, 5, limit, objects)
    assert len(records) == 1
    return dict(records[0])


def seed_cache(tmp_path: Path, *, content: bytes = CONTENT) -> tuple[Path, Path, bytes]:
    target = tmp_path / "provided" / NAME
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    receipt = target.with_name(target.name + ".receipt.json")
    # Historical formatting and extra evidence must remain byte-identical.
    receipt_bytes = (
        json.dumps(
            {
                "status": "acquired",
                "url": f"https://huggingface.co/datasets/openai/gdpval/resolve/{REVISION}/{NAME}",
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
                "historical_note": "keep exactly",
            },
            indent=3,
        ).encode()
        + b"\n\n"
    )
    receipt.write_bytes(receipt_bytes)
    return target, receipt, receipt_bytes


@pytest.mark.parametrize("lfs", [False, True])
def test_fresh_download_matches_pinned_object_before_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lfs: bool
) -> None:
    calls = mock_response(monkeypatch, CONTENT)
    objects = startup.validate_metadata([metadata_item(lfs=lfs)], [NAME])
    record = acquire(tmp_path, objects)
    assert record["status"] == "acquired" and record["remote_verification"]["status"] == "passed"
    assert (tmp_path / "provided" / NAME).read_bytes() == CONTENT
    assert len(calls) == 1 and calls[0]["request"].get_method() == "GET"
    assert "?" not in record["final_url"]
    receipt = (tmp_path / "provided" / NAME).with_name("provided.txt.receipt.json")
    assert "body_path" not in json.loads(receipt.read_bytes())
    assert len(list((tmp_path / "acquisition_attempts").glob("*.json"))) == 1


@pytest.mark.parametrize(
    "mode", ["truncated", "partial_http", "content_range", "length", "wrong_same_size", "wrong_lfs", "wrong_git"]
)
def test_failed_body_never_publishes_cache_and_retains_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    item = metadata_item(lfs=mode == "wrong_lfs")
    data = CONTENT
    kwargs: dict[str, Any] = {}
    if mode == "truncated":
        data = CONTENT[:-1]  # A self-consistent Content-Length must not hide truncation against the remote size.
    elif mode == "partial_http":
        kwargs["status"] = 206
    elif mode == "content_range":
        kwargs["headers"] = {"Content-Range": "bytes 0-2/26"}
    elif mode == "length":
        kwargs["headers"] = {"Content-Length": str(len(CONTENT) + 1)}
    elif mode == "wrong_same_size":
        data = b"x" * len(CONTENT)
    elif mode == "wrong_lfs":
        item["lfs"]["oid"] = "0" * 64
    else:
        item["oid"] = "0" * 40
    calls = mock_response(monkeypatch, data, **kwargs)
    record = acquire(tmp_path, startup.validate_metadata([item], [NAME]))
    assert record["status"] == "failed" and len(calls) == 1
    assert not (tmp_path / "provided" / NAME).exists()
    assert not (tmp_path / "provided" / NAME).with_name("provided.txt.receipt.json").exists()
    assert (tmp_path / record["body_path"]).read_bytes() == data
    attempt = tmp_path / "acquisition_attempts" / (record["attempt_id"] + ".json")
    assert json.loads(attempt.read_bytes())["status"] == "failed"


def test_cached_corruption_is_not_repaired_even_if_old_receipt_hash_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, receipt, original_receipt = seed_cache(tmp_path, content=b"wrong" * 5)
    no_network(monkeypatch)
    record = acquire(tmp_path, startup.validate_metadata([metadata_item()], [NAME]))
    assert record["status"] == "failed" and "pinned remote" in record["error"]
    assert target.read_bytes() == b"wrong" * 5 and receipt.read_bytes() == original_receipt


def test_valid_historical_receipt_is_preserved_and_report_enriched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, receipt, original_receipt = seed_cache(tmp_path)
    no_network(monkeypatch)
    record = acquire(tmp_path, startup.validate_metadata([metadata_item()], [NAME]), fetch=False)
    assert record["status"] == "cached_verified" and record["remote_verification"]["status"] == "passed"
    assert receipt.read_bytes() == original_receipt
    assert record["acquisition_receipt_sha256"] == hashlib.sha256(original_receipt).hexdigest()


def test_orphan_receipt_or_file_is_not_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target, receipt, original_receipt = seed_cache(tmp_path)
    target.unlink()
    no_network(monkeypatch)
    record = acquire(tmp_path, startup.validate_metadata([metadata_item()], [NAME]))
    assert record["status"] == "failed" and "no automatic replacement" in record["error"]
    assert receipt.read_bytes() == original_receipt and not target.exists()


@pytest.mark.parametrize("mutation", ["extra", "missing", "duplicate", "folder", "lfs_size", "invalid_hash"])
def test_metadata_requires_exact_provided_pathset_and_valid_identity(mutation: str) -> None:
    files = [metadata_item(lfs=True)]
    if mutation == "extra":
        files.append(metadata_item(name="reference_files/unrequested.txt"))
    elif mutation == "missing":
        files = []
    elif mutation == "duplicate":
        files.append(files[0])
    elif mutation == "folder":
        files[0]["type"] = "directory"
    elif mutation == "lfs_size":
        files[0]["lfs"]["size"] += 1
    else:
        files[0]["lfs"]["oid"] = "not-a-hash"
    with pytest.raises(ValueError):
        startup.validate_metadata(files, [NAME])


def test_metadata_post_only_original_supplied_paths_then_reuses_bound_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        {"reference_files": [NAME], "deliverable_files": ["gold/answer.txt"], "prompt": "Research https://example.com"}
    ]
    calls = mock_response(monkeypatch, json.dumps([metadata_item()]).encode())
    objects, record = startup.provided_metadata(rows, SOURCE_HASH, REVISION, tmp_path, True, 5)
    assert record["status"] == "verified" and set(objects) == {NAME}
    request = calls[0]["request"]
    assert request.method == "POST" and request.full_url == startup._metadata_url(REVISION)
    assert urllib.parse.parse_qs(request.data.decode()) == {"paths": [NAME], "expand": ["false"]}
    assert calls[0]["metadata"] is True and len(calls) == 1
    binding = json.loads((tmp_path / "provided-metadata-binding.json").read_bytes())
    assert binding["source_sha256"] == SOURCE_HASH and binding["dataset_revision"] == REVISION
    assert binding["paths_sha256"] == startup._canonical_hash([NAME])
    no_network(monkeypatch)
    cached, second = startup.provided_metadata(rows, SOURCE_HASH, REVISION, tmp_path, False, 5)
    assert cached == objects and second["status"] == "cached_verified"


def test_metadata_missing_without_fetch_retains_failure_without_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_network(monkeypatch)
    objects, record = startup.provided_metadata(
        [{"reference_files": [NAME]}], SOURCE_HASH, REVISION, tmp_path, False, 5
    )
    assert objects == {} and record["status"] == "failed"
    assert not (tmp_path / "provided-metadata-binding.json").exists()
    assert len(list((tmp_path / "metadata_attempts").glob("*.json"))) == 1


def test_legacy_metadata_is_adopted_without_rewriting_remote_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = json.dumps(
        {"url": startup._metadata_url(REVISION), "elapsed_seconds": 1.2, "files": [metadata_item()]}, indent=3
    ).encode()
    path = tmp_path / "remote-provided-metadata.json"
    path.write_bytes(original)
    no_network(monkeypatch)
    objects, record = startup.provided_metadata(
        [{"reference_files": [NAME]}], SOURCE_HASH, REVISION, tmp_path, False, 5
    )
    assert set(objects) == {NAME} and record["status"] == "verified"
    assert path.read_bytes() == original and record["metadata_sha256"] == hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize("change", ["source", "revision", "paths", "body"])
def test_cached_metadata_identity_or_bytes_mismatch_never_refetches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    rows = [{"reference_files": [NAME]}]
    mock_response(monkeypatch, json.dumps([metadata_item()]).encode())
    _, original = startup.provided_metadata(rows, SOURCE_HASH, REVISION, tmp_path, True, 5)
    source, revision = SOURCE_HASH, REVISION
    if change == "source":
        source = "c" * 64
    elif change == "revision":
        revision = "d" * 40
    elif change == "paths":
        rows = [{"reference_files": [NAME, "reference_files/new.txt"]}]
    else:
        (tmp_path / original["metadata_path"]).write_bytes(b"[]")
    no_network(monkeypatch)
    objects, record = startup.provided_metadata(rows, source, revision, tmp_path, True, 5)
    assert objects == {} and record["status"] == "failed"
    attempts = [
        json.loads(path.read_bytes())
        for path in (tmp_path / "metadata_attempts").glob("*.json")
        if not path.name.endswith(".body.json")
    ]
    assert len(attempts) == 2 and {attempt["status"] for attempt in attempts} == {"verified", "failed"}


@pytest.mark.parametrize("response", [b"[{", b"[]"])
def test_failed_metadata_response_is_retained_without_retry_or_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: bytes,
) -> None:
    calls = mock_response(monkeypatch, response)
    objects, record = startup.provided_metadata(
        [{"reference_files": [NAME]}], SOURCE_HASH, REVISION, tmp_path, True, 5
    )
    assert len(calls) == 1 and objects == {} and record["status"] == "failed"
    assert (tmp_path / record["body_path"]).read_bytes() == response
    assert not (tmp_path / "provided-metadata-binding.json").exists()


def test_http_error_body_and_attempt_are_retained_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def fail(request: urllib.request.Request, timeout: float, *, metadata: bool) -> None:
        nonlocal calls
        calls += 1
        headers = Message()
        headers["Content-Length"] = "4"
        raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", headers, io.BytesIO(b"busy"))

    monkeypatch.setattr(startup, "_open_response", fail)
    objects, record = startup.provided_metadata(
        [{"reference_files": [NAME]}], SOURCE_HASH, REVISION, tmp_path, True, 5
    )
    assert objects == {} and record["status"] == "failed" and record["http_status"] == 503 and calls == 1
    assert (tmp_path / record["body_path"]).read_bytes() == b"busy"


def test_metadata_redirect_does_not_issue_another_request() -> None:
    handler = startup._NoMetadataRedirect()
    request = urllib.request.Request(startup._metadata_url(REVISION), method="POST", data=b"paths=a")
    with pytest.raises(urllib.error.HTTPError, match="redirects are not permitted"):
        handler.redirect_request(request, io.BytesIO(), 302, "Found", {}, "https://example.com/other")


def test_bound_transfer_retains_only_limit_and_never_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = mock_response(monkeypatch, CONTENT * 3)
    record = acquire(tmp_path, startup.validate_metadata([metadata_item()], [NAME]), limit=len(CONTENT))
    assert record["status"] == "failed" and len(calls) == 1
    assert (tmp_path / record["body_path"]).read_bytes() == CONTENT
    assert not (tmp_path / "provided" / NAME).exists()


def test_elapsed_transfer_deadline_cannot_be_reported_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_response(monkeypatch, CONTENT)
    ticks = iter([0.0, 0.5, 2.0, 2.1])
    monkeypatch.setattr(startup.time, "monotonic", lambda: next(ticks))
    record: dict[str, Any] = {}
    body = tmp_path / "attempt.body"
    with pytest.raises(ValueError, match="exceeded 1s"):
        startup._receive(urllib.request.Request("https://example.com/input"), body, 1, 1000, record)
    assert body.read_bytes() == CONTENT and record["elapsed_seconds"] == 2.1


def test_main_metadata_failure_is_reported_and_does_not_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"task_id": f"task-{index}", "reference_files": [NAME]} for index in range(220)]
    source = tmp_path / "source.jsonl"
    data = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    source.write_bytes(data)
    no_network(monkeypatch)
    output = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        startup.main(
            [
                "--source",
                str(source),
                "--source-sha256",
                hashlib.sha256(data).hexdigest(),
                "--revision",
                REVISION,
                "--output",
                str(output),
            ]
        )
    assert exc.value.code == 1
    report = json.loads((output / "startup-check.json").read_bytes())
    assert report["remote_provided_metadata"]["status"] == "failed" and report["tasks"] == []
    assert not (output / "staging").exists()


def test_main_cache_only_stages_exact_inputs_and_preserves_existing_receipts_and_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "check"
    output.mkdir()
    _, receipt, original = seed_cache(output)
    remote = {"url": startup._metadata_url(REVISION), "files": [metadata_item()]}
    (output / "remote-provided-metadata.json").write_text(json.dumps(remote))
    previous_report = output / "old-startup.json"
    previous_report.write_bytes(b"original previous attempt\n")
    rows = [
        {
            "task_id": f"task-{index}",
            "prompt": "Original prompt",
            "reference_files": [NAME] if index == 0 else [],
            "deliverable_files": ["gold/answer.txt"],
        }
        for index in range(220)
    ]
    source = tmp_path / "source.jsonl"
    data = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    source.write_bytes(data)
    no_network(monkeypatch)
    argv = [
        "--source",
        str(source),
        "--source-sha256",
        hashlib.sha256(data).hexdigest(),
        "--revision",
        REVISION,
        "--output",
        str(output),
        "--report-name",
        "verified-startup.json",
    ]
    startup.main(argv)
    report = json.loads((output / "verified-startup.json").read_bytes())
    assert len(report["tasks"]) == 220 and all(task["staging_status"] == "passed" for task in report["tasks"])
    assert report["remote_provided_metadata"]["provided_path_count"] == 1
    assert report["tasks"][0]["provided"][0]["status"] == "cached_verified"
    assert receipt.read_bytes() == original and previous_report.read_bytes() == b"original previous attempt\n"
    assert all(task["rubric_and_gold_staged"] is False for task in report["tasks"])
    with pytest.raises(ValueError, match="preserve the earlier attempt"):
        startup.main(argv)
    capsys.readouterr()
