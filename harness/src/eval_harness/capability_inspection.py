# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Incremental Office/PDF inspection with immutable sources and recorded derivatives."""

from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET

from PIL import Image
from pypdf import PdfReader

from .artifacts import read_json, sha256_file, write_json
from .errors import ArtifactError
from .office_rendering import (
    OFFICE_SUFFIXES,
    OfficeRenderingConfig,
    _check_office,
    _environment,
    _font_snapshot,
    _profile,
    _tool_roots,
    sandbox_policy,
    verify_render_sandbox,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _xml(package: zipfile.ZipFile, name: str) -> ET.Element:
    data = package.read(name)
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ArtifactError("document XML entities are unsupported")
    return ET.fromstring(data)


def _docx_text(element: ET.Element, *, original: bool) -> str:
    if element.tag == W + ("ins" if original else "del"):
        return ""
    if element.tag in {W + "t", W + "delText"}:
        return element.text or ""
    text = "".join(_docx_text(child, original=original) for child in element)
    return text + ("\n" if element.tag == W + "p" else "")


class InspectionTools:
    def __init__(self, workspace: Path, state: Path, config: Mapping[str, Any]) -> None:
        self.workspace = workspace.resolve()
        self.service_state = state
        self.state = state / "inspection"
        self.state.mkdir(parents=True, exist_ok=True)
        raw = config.get("office_rendering")
        self.rendering = (
            OfficeRenderingConfig(Path(raw["soffice"]), Path(raw["pdftoppm"])) if isinstance(raw, Mapping) else None
        )

    def _run(self, command: list[str], work: Path, environment: Mapping[str, str], logs: Path, name: str) -> None:
        from .capability_sandbox import register_active_process, terminate_process_tree, unregister_active_process

        font_snapshot = _font_snapshot(environment)
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
        register_active_process(self.service_state, process, label="inspection")
        error: str | None = None
        try:
            stdout, stderr = process.communicate(timeout=120)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            error = type(exc).__name__
            terminate_process_tree(process)
            stdout, stderr = process.communicate()
        finally:
            terminate_process_tree(process)
            unregister_active_process(self.service_state, process)
        logs.mkdir(parents=True, exist_ok=True)
        (logs / (name + ".stdout.log")).write_text(stdout, encoding="utf-8")
        (logs / (name + ".stderr.log")).write_text(stderr, encoding="utf-8")
        write_json(
            logs / (name + ".json"),
            {
                "command": command,
                "returncode": process.returncode,
                "error": error,
                "elapsed_seconds": time.monotonic() - started,
                "font_configuration": font_snapshot,
            },
        )
        if error or process.returncode:
            raise ArtifactError(f"inspection command {name} failed: {error or process.returncode}")

    def _source(self, path: str) -> Path:
        supplied = Path(path)
        candidate = supplied if supplied.is_absolute() else self.workspace / supplied
        if not candidate.resolve().is_relative_to(self.workspace):
            raise ArtifactError("inspection path escapes the workspace")
        if any(parent.is_symlink() for parent in (candidate, *candidate.parents) if parent != self.workspace.parent):
            raise ArtifactError("inspection does not follow symbolic links")
        if not candidate.is_file() or candidate.stat().st_size > 50 * 1024 * 1024:
            raise ArtifactError("inspection requires an existing file no larger than 50 MiB")
        return candidate.resolve()

    def inspect_document(self, path: str) -> dict[str, Any]:
        source = self._source(path)
        result: dict[str, Any] = {
            "path": source.relative_to(self.workspace).as_posix(),
            "sha256": sha256_file(source),
            "format": source.suffix.lower(),
            "bytes": source.stat().st_size,
            "scope": "structural inspection; not a functional or visual pass",
        }
        if source.suffix.lower() == ".pdf":
            reader = PdfReader(source)
            result.update(page_count=len(reader.pages), encrypted=reader.is_encrypted)
        elif source.suffix.lower() in OFFICE_SUFFIXES:
            _check_office(source)
            with zipfile.ZipFile(source) as package:
                result["members"] = package.namelist()
                if source.suffix.lower() == ".docx":
                    document = _xml(package, "word/document.xml")
                    original, revised = (_docx_text(document, original=flag) for flag in (True, False))
                    comments = (
                        _xml(package, "word/comments.xml") if "word/comments.xml" in package.namelist() else None
                    )
                    result.update(
                        original_text=original[:60000],
                        revised_text=revised[:60000],
                        text_truncated=max(len(original), len(revised)) > 60000,
                        insertions=len(list(document.iter(W + "ins"))),
                        deletions=len(list(document.iter(W + "del"))),
                        comment_anchors=[e.get(W + "id") for e in document.iter(W + "commentRangeStart")],
                        comments=[{"id": e.get(W + "id"), "text": "".join(e.itertext())} for e in comments]
                        if comments is not None
                        else [],
                    )
                elif source.suffix.lower() == ".xlsx":
                    workbook = _xml(package, "xl/workbook.xml")
                    result["sheets"] = [dict(e.attrib) for e in workbook.iter(S + "sheet")]
                    pivots = [n for n in package.namelist() if n.startswith("xl/pivotTables/") and n.endswith(".xml")]
                    result["pivot_tables"] = [{"part": n, "attributes": _xml(package, n).attrib} for n in pivots]
                    result["pivot_caches"] = [n for n in package.namelist() if n.startswith("xl/pivotCache/")]
                    result["charts"] = [
                        n for n in package.namelist() if n.startswith("xl/charts/chart") and n.endswith(".xml")
                    ]
                    sheets: list[dict[str, Any]] = []
                    for name in package.namelist():
                        if not (name.startswith("xl/worksheets/sheet") and name.endswith(".xml")):
                            continue
                        tree = _xml(package, name)
                        formulas = [
                            {"cell": cell.get("r"), "formula": formula.text}
                            for cell in tree.iter(S + "c")
                            if (formula := cell.find(S + "f")) is not None
                        ]
                        sheets.append(
                            {
                                "part": name,
                                "formula_count": len(formulas),
                                "formula_sample": formulas[:80],
                                "formula_sample_truncated": len(formulas) > 80,
                                "validations": [
                                    ET.tostring(e, encoding="unicode") for e in tree.iter(S + "dataValidation")
                                ],
                                "conditional_format_count": len(list(tree.iter(S + "conditionalFormatting"))),
                            }
                        )
                    result["worksheet_structure"] = sheets
        else:
            raise ArtifactError("inspect_document supports DOCX/XLSX/PPTX/PDF; use shell for other file formats")
        write_json(self.state / (result["sha256"] + ".structure.json"), result)
        return result

    def _pdf(self, source: Path, target: Path) -> Path:
        if self.rendering is None:
            raise ArtifactError("render_pages requires explicit environment.office_rendering native tools")
        target.mkdir(parents=True, exist_ok=True)
        pdf = target / "document.pdf"
        receipt_path = target / "conversion.json"
        if receipt_path.exists():
            receipt = read_json(receipt_path)
            if receipt.get("source_sha256") != sha256_file(source) or receipt.get("pdf_sha256") != sha256_file(pdf):
                raise ArtifactError("saved inspection derivative changed; automatic replacement forbidden")
            return pdf
        shared = self.workspace / ".prepared_previews" / "index.json"
        if shared.is_file():
            entry = read_json(shared).get(sha256_file(source))
            if entry is not None:
                if entry.get("status") != "completed":
                    raise ArtifactError("shared derivative unavailable: " + str(entry.get("reason")))
                prepared = self._source(str(shared.parent / entry["path"]))
                if sha256_file(prepared) != entry["sha256"]:
                    raise ArtifactError("shared PDF derivative hash mismatch")
                shutil.copyfile(prepared, pdf)
                write_json(
                    receipt_path,
                    {
                        "source_sha256": sha256_file(source),
                        "pdf_sha256": entry["sha256"],
                        "page_count": entry["page_count"],
                        "source_unchanged": True,
                        "derivation": "frozen shared evaluation PDF",
                    },
                )
                return pdf
        roots = _tool_roots(self.rendering)
        if source.suffix.lower() not in {*OFFICE_SUFFIXES, ".pdf"}:
            raise ArtifactError("render_pages supports DOCX/XLSX/PPTX/PDF")
        with tempfile.TemporaryDirectory(prefix="eh-inspection-") as temporary:
            root = Path(temporary).resolve()
            inputs, work = root / "inputs", root / "work"
            inputs.mkdir()
            for name in ("home", "tmp", "output"):
                (work / name).mkdir(parents=True)
            verify_render_sandbox(work, inputs, roots, target)
            copied = inputs / ("document" + source.suffix.lower())
            shutil.copyfile(source, copied)
            before = sha256_file(source)
            if source.suffix.lower() == ".pdf":
                shutil.copyfile(copied, pdf)
            else:
                _check_office(copied)
                profile = _profile(work)
                command = [
                    "/usr/bin/sandbox-exec",
                    "-p",
                    sandbox_policy(work, inputs, roots) + "\n(deny process-fork)\n",
                    str(self.rendering.soffice.resolve()),
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
                self._run(command, work, _environment(work, roots[1]), target, "office-to-pdf")
                generated = work / "output" / "document.pdf"
                if not generated.is_file() or generated.stat().st_size > 50 * 1024 * 1024:
                    raise ArtifactError("conversion did not produce a bounded PDF")
                shutil.copyfile(generated, pdf)
            if sha256_file(source) != before or sha256_file(copied) != before:
                raise ArtifactError("inspection changed source bytes")
        reader = PdfReader(pdf)
        if reader.is_encrypted:
            raise ArtifactError("encrypted PDFs are not supported")
        write_json(
            receipt_path,
            {
                "source_sha256": before,
                "pdf_sha256": sha256_file(pdf),
                "page_count": len(reader.pages),
                "source_unchanged": True,
                "rendering": self.rendering.snapshot(),
                "scope": "saved print layout; recalculated values may differ; no functional pass implied",
            },
        )
        return pdf

    def render_pages(self, path: str, pages: list[int], region: list[int] | None = None) -> list[dict[str, Any]]:
        if not isinstance(pages, list) or not 1 <= len(pages) <= 4 or any(type(p) is not int or p < 1 for p in pages):
            raise ArtifactError("request one to four positive one-based pages per call; more pages remain available")
        source = self._source(path)
        source_hash = sha256_file(source)
        target = self.state / (source_hash + source.suffix.lower())
        pdf = self._pdf(source, target)
        assert self.rendering is not None
        count = read_json(target / "conversion.json")["page_count"]
        if any(page > count for page in pages):
            raise ArtifactError(f"page outside document's 1..{count} range; no partial response")
        roots = _tool_roots(self.rendering)
        content: list[dict[str, Any]] = []
        for page in pages:
            image = target / f"page-{page:04d}.png"
            if not image.exists():
                with tempfile.TemporaryDirectory(prefix="eh-page-") as temporary:
                    work = Path(temporary).resolve()
                    for name in ("home", "tmp"):
                        (work / name).mkdir()
                    policy = sandbox_policy(work, target, roots) + "\n(deny process-fork)\n"
                    command = [
                        "/usr/bin/sandbox-exec",
                        "-p",
                        policy,
                        str(self.rendering.pdftoppm.resolve()),
                        "-png",
                        "-singlefile",
                        "-r",
                        "120",
                        "-scale-to",
                        "1600",
                        "-f",
                        str(page),
                        "-l",
                        str(page),
                        str(pdf),
                        str(work / "page"),
                    ]
                    self._run(command, work, _environment(work, roots[1], roots[0]), target, f"page-{page:04d}")
                    shutil.copyfile(work / "page.png", image)
            with Image.open(image) as opened:
                opened.load()
                displayed: Image.Image = opened
                if region is not None:
                    if (
                        len(region) != 4
                        or any(type(v) is not int for v in region)
                        or not (
                            0 <= region[0] < region[2] <= opened.width and 0 <= region[1] < region[3] <= opened.height
                        )
                    ):
                        raise ArtifactError("region must be [left, top, right, bottom] inside the rendered page")
                    displayed = opened.crop(tuple(region))  # type: ignore[arg-type]
                output = io.BytesIO()
                displayed.save(output, format="PNG")
            data = output.getvalue()
            from .artifacts import sha256_bytes

            digest = sha256_bytes(data)
            display_path = target / (digest + ".png")
            display_path.write_bytes(data)
            receipt = {
                "source": source.relative_to(self.workspace).as_posix(),
                "source_sha256": source_hash,
                "pdf_sha256": sha256_file(pdf),
                "page": page,
                "page_count": count,
                "region": region,
                "image_sha256": digest,
                "bytes": len(data),
            }
            write_json(target / (digest + ".view.json"), receipt)
            content += [
                {"type": "text", "text": json.dumps(receipt)},
                {"type": "image", "mimeType": "image/png", "data": base64.b64encode(data).decode("ascii")},
            ]
        return content
