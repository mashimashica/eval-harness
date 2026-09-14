# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Immutable, cached Office previews, produced outside the evaluator sessions."""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree

from .artifacts import file_manifest, manifest_hash, read_json, sha256_file, write_json
from .errors import ArtifactError, ConfigError
from .executor import _stop_process_group

OFFICE_SUFFIXES = {".docx": "writer_pdf_Export", ".xlsx": "calc_pdf_Export", ".pptx": "impress_pdf_Export"}
MAX_PAGES = 20
RENDER_TIMEOUT = 120


@dataclass(frozen=True)
class OfficeRenderingConfig:
    """Explicit native tools, independent of either judge's runtime."""

    soffice: Path
    pdftoppm: Path

    def snapshot(self) -> dict[str, str]:
        return {"soffice": str(self.soffice), "pdftoppm": str(self.pdftoppm)}


def parse_rendering(value: Any, base: Path) -> OfficeRenderingConfig | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"soffice", "pdftoppm"}:
        raise ConfigError("evaluation.office_rendering requires exactly soffice and pdftoppm native executable paths")
    paths: list[Path] = []
    for name in ("soffice", "pdftoppm"):
        raw = value[name]
        if not isinstance(raw, str) or not raw.strip():
            raise ConfigError(f"office_rendering.{name} must be a path")
        path = Path(raw).expanduser()
        paths.append((base / path).absolute())
    return OfficeRenderingConfig(*paths)


def _tool_roots(config: OfficeRenderingConfig) -> tuple[Path, Path]:
    """Only self-contained app/prefix layouts; never grant a home or system-wide prefix."""
    office, poppler = config.soffice.resolve(), config.pdftoppm.resolve()
    if (
        office.name != "soffice"
        or office.parent.name != "MacOS"
        or office.parent.parent.name != "Contents"
        or office.parents[2].suffix != ".app"
        or poppler.name != "pdftoppm"
        or poppler.parent.name != "bin"
        or not (poppler.parent.parent / "lib").is_dir()
    ):
        raise ArtifactError(
            "rendering requires a LibreOffice .app executable and self-contained Poppler bin/lib prefix"
        )
    roots = office.parents[2], poppler.parent.parent
    for executable in (office, poppler):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ArtifactError(f"render executable unavailable: {executable}")
        with executable.open("rb") as handle:
            magic = handle.read(4)
        if magic not in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}:
            raise ArtifactError("render tools must be native Mach-O executables, not PATH wrappers")
    for root in roots:
        if root in {Path.home(), Path("/"), Path("/usr"), Path("/usr/local"), Path("/opt/homebrew")}:
            raise ArtifactError("render runtime root is too broad")
    return roots


def _runtime_manifest(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            if not path.resolve().is_relative_to(root):
                raise ArtifactError(f"render runtime link escapes its root: {path}")
            entries.append({"path": path.relative_to(root).as_posix(), "link": os.readlink(path)})
        elif path.is_file():
            entries.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    return entries


def sandbox_policy(work: Path, inputs: Path, roots: Sequence[Path]) -> str:
    """Seatbelt denies data reads outside explicit inputs/tools and all networking."""

    def literal(path: Path) -> str:
        return json.dumps(str(path))

    readable = [Path("/System/Library"), Path("/usr/lib"), Path("/usr/share"), Path("/bin"), Path("/usr/bin")]
    readable += [Path("/Library/Fonts"), *roots, work, inputs]
    return "\n".join(
        [
            "(version 1)",
            "(deny default)",
            "(allow process* sysctl-read mach-lookup ipc-posix*)",
            "(allow file-read-metadata)",
            '(allow file-read* (literal "/"))',
            "(allow file-read* " + " ".join(f"(subpath {literal(p)})" for p in readable) + ")",
            "(allow file-map-executable " + " ".join(f"(subpath {literal(p)})" for p in readable) + ")",
            f"(allow file-write* (subpath {literal(work)}))",
            '(allow file-read* file-write* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))',
            "(deny network*)",
        ]
    )


def _environment(work: Path, poppler: Path) -> dict[str, str]:
    return {
        "HOME": str(work / "home"),
        "TMPDIR": str(work / "tmp"),
        "PATH": "/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
        "SAL_USE_VCLPLUGIN": "svp",
        "DYLD_FALLBACK_LIBRARY_PATH": str(poppler / "lib"),
    }


def _run(command: list[str], work: Path, environment: Mapping[str, str], logs: Path, name: str) -> None:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=work,
        env=dict(environment),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    error: str | None = None
    try:
        stdout, stderr = process.communicate(timeout=RENDER_TIMEOUT)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        _stop_process_group(process)
        stdout, stderr = process.communicate()
        error = type(exc).__name__
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"{name}.stdout.log").write_text(stdout, encoding="utf-8")
    (logs / f"{name}.stderr.log").write_text(stderr, encoding="utf-8")
    write_json(
        logs / f"{name}.json",
        {
            "command": command,
            "returncode": process.returncode,
            "error": error,
            "elapsed_seconds": time.monotonic() - started,
        },
    )
    if error or process.returncode:
        raise ArtifactError(f"Office renderer {name} failed ({error or process.returncode}); see {logs}")


def verify_render_sandbox(work: Path, inputs: Path, roots: Sequence[Path], evidence: Path) -> None:
    """Exercise actual deny-read/deny-write/network rules before processing a document."""
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise ArtifactError("Office rendering currently requires macOS sandbox-exec; no unsandboxed fallback")
    # A private, artificial outside sentinel avoids probing personal data.
    with tempfile.TemporaryDirectory(prefix="eh-render-sentinel-") as outside, socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        port = str(listener.getsockname()[1])
        connected = subprocess.run(
            ["/usr/bin/nc", "-z", "-w", "1", "127.0.0.1", port],
            capture_output=True,
            timeout=5,
            check=False,
        )
        if connected.returncode:
            raise ArtifactError("render isolation network positive control failed")
        sentinel = Path(outside).resolve() / "outside.txt"
        sentinel.write_text("outside sentinel")
        (inputs / "sentinel.txt").write_text("read-only sentinel")
        # Native shell checks need no Python dependencies inside the rendering sandbox.
        script = "\n".join(
            [
                "set -eu",
                'cat "$1/sentinel.txt" >/dev/null',
                'if cat "$2" >/dev/null 2>&1; then exit 31; fi',
                'if (printf changed >"$1/sentinel.txt") 2>/dev/null; then exit 32; fi',
                'if (printf changed >"$2") 2>/dev/null; then exit 33; fi',
                'printf allowed >"$3/probe.txt"',
                'if /usr/bin/nc -z -w 1 127.0.0.1 "$4" >/dev/null 2>&1; then exit 34; fi',
                "printf verified",
            ]
        )
        policy = sandbox_policy(work, inputs, roots)
        (evidence / "sandbox.sb").write_text(policy, encoding="utf-8")
        _run(
            [
                "/usr/bin/sandbox-exec",
                "-p",
                policy,
                "/bin/sh",
                "-c",
                script,
                "probe",
                str(inputs),
                str(sentinel),
                str(work),
                port,
            ],
            work,
            _environment(work, roots[1]),
            evidence,
            "isolation",
        )
        if sentinel.read_text() != "outside sentinel" or (inputs / "sentinel.txt").read_text() != "read-only sentinel":
            raise ArtifactError("render sandbox modified a protected sentinel")
        (inputs / "sentinel.txt").unlink()


def _check_office(source: Path) -> None:
    """Reject active/linked OOXML packages before conversion, without extracting members."""
    if source.suffix.lower() not in OFFICE_SUFFIXES:
        raise ArtifactError(f"unsupported Office preview format: {source.name}")
    if source.stat().st_size > 50 * 1024 * 1024:
        raise ArtifactError("Office input exceeds 50 MiB rendering limit")
    try:
        with zipfile.ZipFile(source) as package:
            entries = package.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > 200 * 1024 * 1024:
                raise ArtifactError("Office expanded package exceeds rendering limits")
            for entry in entries:
                name = entry.filename.lower()
                if (
                    "vbaproject" in name
                    or "/embeddings/" in name
                    or "/externallinks/" in name
                    or name.endswith("connections.xml")
                ):
                    raise ArtifactError("active content or linked data is unsupported for Office rendering")
                if name.endswith(".rels"):
                    content = package.read(entry)
                    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
                        raise ArtifactError("Office relationship entities are unsupported")
                    for relationship in ElementTree.fromstring(content):
                        if relationship.get("TargetMode", "").lower() == "external" and not relationship.get(
                            "Type", ""
                        ).endswith("/hyperlink"):
                            raise ArtifactError("external Office resources are unsupported for rendering")
    except (zipfile.BadZipFile, ElementTree.ParseError, RuntimeError) as exc:
        raise ArtifactError(f"invalid Office package: {source.name}: {exc}") from exc


def _profile(work: Path) -> Path:
    profile = work / "profile"
    (profile / "user").mkdir(parents=True)
    (profile / "user" / "registrymodifications.xcu").write_text(
        '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>'
        "</oor:items>",
        encoding="utf-8",
    )
    return profile


def _render(source: Path, target: Path, config: OfficeRenderingConfig, roots: tuple[Path, Path]) -> None:
    with tempfile.TemporaryDirectory(prefix="eh-office-render-") as temporary:
        root = Path(temporary).resolve()
        inputs, work = root / "inputs", root / "work"
        inputs.mkdir()
        work.mkdir()
        for name in ("home", "tmp", "output"):
            (work / name).mkdir()
        verify_render_sandbox(work, inputs, roots, target)
        copied = inputs / ("document" + source.suffix.lower())
        shutil.copyfile(source, copied)
        copied.chmod(0o400)
        policy = sandbox_policy(work, inputs, roots)
        environment = _environment(work, roots[1])
        profile = _profile(work)
        command = [
            "/usr/bin/sandbox-exec",
            "-p",
            policy,
            str(config.soffice.resolve()),
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            "--convert-to",
            "pdf:" + OFFICE_SUFFIXES[source.suffix.lower()],
            "--outdir",
            str(work / "output"),
            str(copied),
        ]
        _run(command, work, environment, target, "office-to-pdf")
        pdf = work / "output" / "document.pdf"
        if not pdf.is_file() or pdf.stat().st_size > 50 * 1024 * 1024:
            raise ArtifactError("Office conversion did not produce a bounded PDF")
        _run(
            [
                "/usr/bin/sandbox-exec",
                "-p",
                policy,
                str(config.pdftoppm.resolve()),
                "-png",
                "-r",
                "120",
                "-scale-to",
                "1600",
                "-f",
                "1",
                "-l",
                str(MAX_PAGES + 1),
                str(pdf),
                str(work / "output" / "page"),
            ],
            work,
            environment,
            target,
            "pdf-to-png",
        )
        images = sorted((work / "output").glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        if not 1 <= len(images) <= MAX_PAGES:
            raise ArtifactError(f"Office preview exceeds {MAX_PAGES} pages or has no pages; no truncated evaluation")
        shutil.copyfile(pdf, target / "document.pdf")
        for index, path in enumerate(images, 1):
            shutil.copyfile(path, target / f"page-{index:03d}.png")
        if sha256_file(copied) != sha256_file(source):
            raise ArtifactError("Office rendering changed its read-only input")


def render_key(source: Path) -> str:
    return sha256_file(source) + source.suffix.lower()


def cached_render(source: Path, cache: Path) -> dict[str, Any]:
    directory = cache / render_key(source)
    saved = read_json(directory / "manifest.json")
    if not isinstance(saved, dict) or saved.get("status") != "completed":
        raise ArtifactError(f"Office rendering is unavailable; retained failure at {directory}")
    if saved.get("source_sha256") != sha256_file(source):
        raise ArtifactError("Office preview source hash changed")
    actual = [entry for entry in file_manifest(directory) if entry["path"].endswith((".pdf", ".png"))]
    if actual != saved.get("files"):
        raise ArtifactError("saved Office preview changed; automatic re-render is forbidden")
    if not any(entry["path"].endswith(".png") for entry in actual):
        raise ArtifactError("saved Office preview has no images")
    return saved


def prepare_render_cache(sources: Sequence[Path], cache: Path, config: OfficeRenderingConfig) -> None:
    """Complete all previews before any judge; retain failed/incomplete jobs without retry."""
    unique = {render_key(source): source for source in sources}
    cache.mkdir(parents=True, exist_ok=True)
    missing: list[tuple[str, Path]] = []
    for key, source in unique.items():
        if (cache / key).exists():
            cached_render(source, cache)
        else:
            missing.append((key, source))
    if not missing:
        return
    roots = _tool_roots(config)
    identity = {
        "config": config.snapshot(),
        "os": platform.platform(),
        "format_version": 1,
        "tools": [{"root": str(root), "files_sha256": manifest_hash(_runtime_manifest(root))} for root in roots],
        "policy": {
            "dpi": 120,
            "max_dimension": 1600,
            "max_pages": MAX_PAGES,
            "timeout_seconds": RENDER_TIMEOUT,
            "spreadsheet_view": "saved print layout; LibreOffice may recalculate derivative values",
        },
    }
    identity_path = cache / "renderer.json"
    if identity_path.exists() and read_json(identity_path) != identity:
        raise ArtifactError("Office renderer changed; missing cached previews will not use a replacement runtime")
    write_json(identity_path, identity)
    for key, source in missing:
        target = cache / key
        target.mkdir()
        before = sha256_file(source)
        started = time.monotonic()
        record: dict[str, Any] = {
            "status": "in_progress",
            "source_sha256": before,
            "format": source.suffix.lower(),
            "renderer_sha256": manifest_hash([identity]),
        }
        write_json(target / "manifest.json", record)
        try:
            _check_office(source)
            _render(source, target, config, roots)
            record["files"] = [e for e in file_manifest(target) if e["path"].endswith((".png", ".pdf"))]
            record["status"] = "completed"
        except Exception as exc:
            record.update(status="failed", error=str(exc))
            raise
        finally:
            record["elapsed_seconds"] = time.monotonic() - started
            record["source_unchanged"] = sha256_file(source) == before
            if not record["source_unchanged"]:
                record.update(status="failed", error="Office original changed during rendering")
            write_json(target / "manifest.json", record)
        if record["status"] != "completed":
            raise ArtifactError(str(record.get("error")))


def attach_previews(workspace: Path, cache: Path, submissions: Sequence[str]) -> tuple[tuple[Path, ...], str]:
    """Copy the frozen PNGs with anonymous labels, retaining page/source correspondence."""
    from .image_inputs import image_manifest

    paths: list[Path] = []
    mapping: list[dict[str, Any]] = []
    for label in submissions:
        folder = workspace / label
        for index, source in enumerate(sorted(folder.rglob("*")), 1):
            if not source.is_file() or source.suffix.lower() not in OFFICE_SUFFIXES:
                continue
            saved = cached_render(source, cache)
            for entry in saved["files"]:
                if not entry["path"].endswith(".png"):
                    continue
                relative = Path("visuals") / label / f"document-{index:03d}" / entry["path"]
                (workspace / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cache / render_key(source) / entry["path"], workspace / relative)
                paths.append(relative)
                mapping.append(
                    {
                        "image": relative.as_posix(),
                        "source": source.relative_to(workspace).as_posix(),
                        "source_sha256": saved["source_sha256"],
                        "image_sha256": entry["sha256"],
                    }
                )
    # Validate the entire combined request, not each document separately.
    manifest = image_manifest(workspace, tuple(paths))
    write_json(workspace / "visuals_manifest.json", {"mapping": mapping, "images": manifest})
    if not paths:
        return (), ""
    prompt = (
        "\nAttached images are frozen Office previews, in the following order. Use them for visual layout review. "
        "The original submission files remain authoritative for mechanical values and formulas. LibreOffice may "
        "recalculate values in these derivatives; previews show saved print layouts and do not prove hidden-sheet "
        "or off-print-area completeness. Do not regenerate or edit either originals or previews.\n"
        + "\n".join(f"Image {i}: {entry['image']} — {entry['source']}" for i, entry in enumerate(mapping, 1))
        + "\n"
    )
    return tuple(paths), prompt
