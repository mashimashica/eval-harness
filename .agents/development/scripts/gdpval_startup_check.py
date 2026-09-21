# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Acquire only provided inputs at a pinned revision and exercise every task's staging path.

This is a model-free acceptance check, not evidence that a participant solved a task.
Research URLs and gold deliverables are never downloaded or staged by this script.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from eval_harness.artifacts import file_manifest, sha256_file, write_json
from eval_harness.gdpval import _normalize_row, copy_reference_files, render_application_prompt

METADATA_LIMIT = 4 * 1024 * 1024


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _write_new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")


def _provided_path(name: Any) -> str:
    if (
        not isinstance(name, str)
        or "\\" in name
        or "\x00" in name
        or any(part in {"", ".", ".."} for part in name.split("/"))
        or not name.startswith("reference_files/")
    ):
        raise ValueError(f"invalid provided input path: {name}")
    return name


def _metadata_url(revision: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("dataset revision must be a pinned 40-character Git SHA")
    return f"https://huggingface.co/api/datasets/openai/gdpval/paths-info/{revision}"


def validate_metadata(files: Any, paths: list[str]) -> dict[str, dict[str, Any]]:
    """Require the exact provided file set and a usable pinned object identity."""
    if not isinstance(files, list):
        raise ValueError("remote metadata must be a list of provided-file objects")
    result: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict) or item.get("type") != "file":
            raise ValueError("remote metadata contains a non-file object")
        path, size = _provided_path(item.get("path")), item.get("size")
        if path in result or type(size) is not int or size < 0:
            raise ValueError("remote metadata has duplicate paths or invalid sizes")
        lfs = item.get("lfs")
        if lfs is not None:
            if not isinstance(lfs, dict) or type(lfs.get("size")) is not int or lfs["size"] != size:
                raise ValueError("LFS metadata size disagrees with the file size")
            kind, expected, pattern = "sha256", lfs.get("oid"), r"[0-9a-f]{64}"
        else:
            kind, expected, pattern = "git_blob_sha1", item.get("oid"), r"[0-9a-f]{40}"
        if not isinstance(expected, str) or not re.fullmatch(pattern, expected):
            raise ValueError("remote metadata has an invalid object hash")
        result[path] = {"expected_bytes": size, "hash_kind": kind, "expected_hash": expected}
    if set(result) != set(paths):
        raise ValueError("remote metadata path set differs from the original provided-file list")
    return result


class _NoMetadataRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        raise urllib.error.HTTPError(req.full_url, code, "metadata redirects are not permitted", headers, fp)


def _open_response(request: urllib.request.Request, timeout: float, *, metadata: bool) -> Any:
    if metadata:
        return urllib.request.build_opener(_NoMetadataRedirect()).open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def _receive(
    request: urllib.request.Request,
    target: Path,
    timeout: int,
    max_bytes: int,
    record: dict[str, Any],
    *,
    metadata: bool = False,
) -> None:
    """Retain bounded received bytes, including failed and partial responses."""
    started = time.monotonic()
    total, digest = 0, hashlib.sha256()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            response = _open_response(request, min(45, timeout), metadata=metadata)
        except urllib.error.HTTPError as exc:
            response = exc
        with response, target.open("xb") as output:
            final = urllib.parse.urlsplit(response.url)
            length = response.headers.get("Content-Length")
            record.update(
                http_status=response.status,
                final_url=urllib.parse.urlunsplit((final.scheme, final.netloc, final.path, "", "")),
                content_length=length,
                content_range=response.headers.get("Content-Range"),
            )
            while True:
                if time.monotonic() - started > timeout:
                    raise ValueError(f"transfer exceeded {timeout}s")
                # read1 returns available bytes rather than waiting to fill a large buffer.
                chunk = response.read1(min(64 * 1024, max_bytes - total + 1))
                if not chunk:
                    break
                remaining = max_bytes - total
                output.write(chunk[:remaining])
                digest.update(chunk[:remaining])
                total += len(chunk[:remaining])
                if len(chunk) > remaining:
                    raise ValueError(f"transfer exceeded {max_bytes} bytes")
            if response.status != 200 or record["content_range"] is not None:
                raise ValueError("provided input/metadata response must be complete HTTP 200 without Content-Range")
            if metadata and record["final_url"] != request.full_url:
                raise ValueError("metadata response changed the pinned API URL")
            if length is not None and (not length.isdigit() or int(length) != total):
                raise ValueError("HTTP Content-Length does not match received bytes")
            if time.monotonic() - started > timeout:
                raise ValueError(f"transfer exceeded {timeout}s")
    finally:
        record.update(bytes=total, sha256=digest.hexdigest(), elapsed_seconds=time.monotonic() - started)


def provided_metadata(
    rows: list[dict[str, Any]],
    source_sha256: str,
    revision: str,
    output: Path,
    fetch: bool,
    timeout: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Bind cached metadata to this source/revision/path set without rewriting history."""
    paths = sorted({_provided_path(name) for row in rows for name in row.get("reference_files", [])})
    url = _metadata_url(revision)
    identity = {"source_sha256": source_sha256, "dataset_revision": revision, "paths_sha256": _canonical_hash(paths)}
    attempt_id = uuid4().hex
    attempt = output / "metadata_attempts" / f"{attempt_id}.json"
    record: dict[str, Any] = {**identity, "url": url, "started_at": datetime.now(timezone.utc).isoformat()}
    binding_path = output / "provided-metadata-binding.json"
    try:
        if not paths:
            return {}, {**record, "status": "not_required", "provided_path_count": 0}
        if len(paths) > 4096:
            raise ValueError("provided metadata path count exceeds the bounded request limit")
        if binding_path.exists():
            binding = json.loads(binding_path.read_bytes())
            if (
                binding.get("schema_version") != 1
                or binding.get("provided_paths") != paths
                or any(binding.get(key) != value for key, value in identity.items())
                or binding.get("url") != url
            ):
                raise ValueError("cached metadata source, revision or path-set identity mismatch")
            raw_path = binding.get("metadata_path")
            if not isinstance(raw_path, str) or Path(raw_path).is_absolute() or ".." in Path(raw_path).parts:
                raise ValueError("invalid cached metadata evidence path")
            metadata_path = output / raw_path
            if (
                metadata_path.is_symlink()
                or not metadata_path.resolve().is_relative_to(output.resolve())
                or metadata_path.stat().st_size > METADATA_LIMIT
                or sha256_file(metadata_path) != binding.get("metadata_sha256")
            ):
                raise ValueError("cached remote metadata bytes changed")
            payload = json.loads(metadata_path.read_bytes())
            files = payload.get("files") if isinstance(payload, dict) else payload
            objects = validate_metadata(files, paths)
            record.update(status="cached_verified", binding_sha256=sha256_file(binding_path), **binding)
        else:
            # Adopt the already captured remote evidence after binding it to the exact current source.
            metadata_path = output / "remote-provided-metadata.json"
            if metadata_path.exists():
                if metadata_path.is_symlink() or metadata_path.stat().st_size > METADATA_LIMIT:
                    raise ValueError("cached metadata is a symlink or exceeds the byte limit")
                payload = json.loads(metadata_path.read_bytes())
                if not isinstance(payload, dict) or payload.get("url") != url:
                    raise ValueError("cached metadata URL does not identify the pinned dataset revision")
                files = payload.get("files")
            else:
                if not fetch:
                    raise FileNotFoundError("pinned provided-file metadata missing; rerun with --fetch")
                metadata_path = output / "metadata_attempts" / f"{attempt_id}.body.json"
                data = urllib.parse.urlencode({"paths": paths, "expand": "false"}, doseq=True).encode()
                if len(data) > 1024 * 1024:
                    raise ValueError("provided metadata request exceeds the byte limit")
                request = urllib.request.Request(
                    url,
                    data=data,
                    method="POST",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept-Encoding": "identity",
                        "User-Agent": "eval-harness-input-check/2",
                    },
                )
                record["body_path"] = metadata_path.relative_to(output).as_posix()
                _receive(request, metadata_path, timeout, METADATA_LIMIT, record, metadata=True)
                files = json.loads(metadata_path.read_bytes())
            objects = validate_metadata(files, paths)
            binding = {
                "schema_version": 1,
                **identity,
                "url": url,
                "provided_paths": paths,
                "metadata_path": metadata_path.relative_to(output).as_posix(),
                "metadata_sha256": sha256_file(metadata_path),
            }
            _write_new_json(binding_path, binding)
            record.update(status="verified", binding_sha256=sha256_file(binding_path), **binding)
        record["provided_path_count"] = len(objects)
    except Exception as exc:
        objects = {}
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    _write_new_json(attempt, record)
    return objects, record


def verify_object(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    size = path.stat().st_size
    sha256, git_blob = hashlib.sha256(), hashlib.sha1(f"blob {size}\0".encode())
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(chunk)
            git_blob.update(chunk)
    sha = sha256.hexdigest()
    observed = sha if expected["hash_kind"] == "sha256" else git_blob.hexdigest()
    return {
        **expected,
        "observed_bytes": size,
        "observed_hash": observed,
        "sha256": sha,
        "status": "passed"
        if size == expected["expected_bytes"] and observed == expected["expected_hash"]
        else "failed",
    }


def acquire(
    row: dict[str, Any],
    root: Path,
    revision: str,
    fetch: bool,
    timeout: int,
    max_bytes: int,
    objects: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in row.get("reference_files", []):
        relative = Path(_provided_path(name))
        url = f"https://huggingface.co/datasets/openai/gdpval/resolve/{revision}/" + urllib.parse.quote(name)
        target = root / relative
        receipt = target.with_name(target.name + ".receipt.json")
        started = time.monotonic()
        attempt_id = uuid4().hex
        attempt = root.parent / "acquisition_attempts" / f"{attempt_id}.json"
        body = attempt.with_suffix(".body")
        record: dict[str, Any] = {
            "path": name,
            "url": url,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "attempt_id": attempt_id,
        }
        try:
            expected = objects[name]
            record["remote_identity"] = expected
            if expected["expected_bytes"] > max_bytes:
                raise ValueError("pinned provided object exceeds the download byte limit")
            if target.is_symlink() or receipt.is_symlink():
                raise ValueError("provided cache files and receipts must not be symbolic links")
            if target.exists() or receipt.exists():
                if not target.is_file() or not receipt.is_file():
                    raise ValueError("incomplete cache/receipt pair; no automatic replacement is permitted")
                previous = json.loads(receipt.read_text())
                observed = verify_object(target, expected)
                record.update(
                    remote_verification=observed, sha256=observed["sha256"], bytes=observed["observed_bytes"]
                )
                if observed["status"] != "passed":
                    raise ValueError("cached provided file differs from the pinned remote size/object hash")
                if (
                    previous.get("status") != "acquired"
                    or previous.get("url") != url
                    or previous.get("sha256") != observed["sha256"]
                ):
                    raise ValueError("cached provided file failed identity verification")
                record.update(status="cached_verified", acquisition_receipt_sha256=sha256_file(receipt))
            else:
                if not fetch:
                    raise FileNotFoundError("provided file not acquired; rerun with --fetch")
                request = urllib.request.Request(
                    url, headers={"User-Agent": "eval-harness-input-check/2", "Accept-Encoding": "identity"}
                )
                record["body_path"] = body.relative_to(root.parent).as_posix()
                _receive(request, body, timeout, max_bytes, record)
                observed = verify_object(body, expected)
                record["remote_verification"] = observed
                if observed["status"] != "passed":
                    raise ValueError("received provided file differs from the pinned remote size/object hash")
                target.parent.mkdir(parents=True, exist_ok=True)
                # Same-filesystem exclusive publication: never replace an existing cached artifact.
                os.link(body, target)
                record.update(status="acquired", elapsed_seconds=time.monotonic() - started)
                try:
                    _write_new_json(receipt, {key: value for key, value in record.items() if key != "body_path"})
                except Exception:
                    target.unlink()
                    raise
                body.unlink()
                record.pop("body_path")
        except Exception as exc:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        record["elapsed_seconds"] = time.monotonic() - started
        _write_new_json(attempt, record)
        results.append(record)
    return results


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--download-timeout", type=int, default=180)
    parser.add_argument("--max-download-mib", type=int, default=512)
    parser.add_argument("--report-name", default="startup-check.json")
    args = parser.parse_args(argv)
    source_bytes = args.source.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != args.source_sha256 or not re.fullmatch(
        r"[0-9a-f]{40}", args.revision
    ):
        raise ValueError("source hash or pinned dataset revision is invalid")
    rows = [json.loads(line) for line in source_bytes.splitlines() if line.strip()]
    if len(rows) != 220 or len({row["task_id"] for row in rows}) != 220:
        raise ValueError("expected exactly 220 unique original tasks")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (
        not 1 <= args.download_timeout <= 900
        or not 1 <= args.max_download_mib <= 2048
        or Path(args.report_name).name != args.report_name
    ):
        raise ValueError("invalid bounded timeout or report filename")
    if (output / args.report_name).exists():
        raise ValueError("preserve the earlier attempt; choose a new --report-name")
    references = output / "provided"
    records: list[dict[str, Any]] = []
    objects, metadata_identity = provided_metadata(
        rows, args.source_sha256, args.revision, output, args.fetch, args.download_timeout
    )
    report = {
        "source_sha256": args.source_sha256,
        "dataset_revision": args.revision,
        "kind": "model-free original-input staging; no participant/model execution",
        "remote_provided_metadata": metadata_identity,
        "tasks": records,
    }
    write_json(output / args.report_name, report)
    if metadata_identity["status"] == "failed":
        raise SystemExit(1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            path: executor.submit(
                acquire,
                {"reference_files": [path]},
                references,
                args.revision,
                args.fetch,
                args.download_timeout,
                args.max_download_mib * 1024 * 1024,
                objects,
            )
            for path in objects
        }
        for index, row in enumerate(rows, 1):
            inputs = [futures[path].result()[0] for path in row.get("reference_files", [])]
            record: dict[str, Any] = {"task_id": row["task_id"], "source_line": index, "provided": inputs}
            try:
                if any(item["status"] not in {"acquired", "cached_verified"} for item in inputs):
                    raise ValueError("one or more provided inputs were not acquired")
                task = _normalize_row(row, args.source.resolve(), index)
                task = replace(task, reference_files=tuple(str(references / name) for name in row["reference_files"]))
                workspace = output / "staging" / task.task_id
                metadata = copy_reference_files(task, workspace / "reference_files")
                prompt = render_application_prompt(task)
                if not prompt.endswith("Task:\n" + row["prompt"] + "\n"):
                    raise ValueError("participant prompt changed original task text")
                (workspace / "prompt.txt").write_text(prompt)
                allowed = {"prompt.txt", *("reference_files/" + str(item["path"]) for item in metadata)}
                actual = {str(item["path"]) for item in file_manifest(workspace)}
                if actual != allowed or [item["sha256"] for item in metadata] != [item["sha256"] for item in inputs]:
                    raise ValueError("staged input bytes or workspace contents differ")
                record.update(
                    staging_status="passed",
                    staged_references=metadata,
                    prompt_sha256=hashlib.sha256(row["prompt"].encode()).hexdigest(),
                    workspace_files=sorted(actual),
                    rubric_and_gold_staged=False,
                )
            except Exception as exc:
                record.update(staging_status="failed", staging_error=f"{type(exc).__name__}: {exc}")
            records.append(record)
            write_json(output / args.report_name, report)
            print(f"{index}/220 {row['task_id']} {record['staging_status']}", flush=True)
    if any(item["staging_status"] != "passed" for item in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
