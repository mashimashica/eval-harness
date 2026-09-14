# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validation and staging helpers for bounded native PNG inputs."""

from __future__ import annotations

import builtins
import hashlib
import io
import os
import stat
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image, ImageFile

from .errors import HarnessError

MAX_IMAGE_COUNT = 20
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_DIMENSION = 2048
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class ImageInput:
    """One validated relative PNG and its exact bytes.

    ``data`` is retained only for the duration of an executor call.  It is
    deliberately absent from manifest and receipt representations.
    """

    path: str
    sha256: str
    bytes: int
    width: int
    height: int
    data: builtins.bytes = field(repr=False, compare=False)

    def manifest_entry(self) -> dict[str, Any]:
        """Return the redacted, serializable identity for this input."""

        return {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "width": self.width,
            "height": self.height,
        }


def _invalid(path: Path | str, reason: str) -> HarnessError:
    return HarnessError(f"invalid image input {path}: {reason}")


def _png_dimensions(path: Path, data: bytes) -> tuple[int, int]:
    if not data.startswith(PNG_SIGNATURE):
        raise _invalid(path, "file does not have a PNG signature")
    # Parse the bounded chunk envelope rather than relying on a decoder.  The
    # validator needs no pixel allocation, but rejecting truncated/corrupt
    # chunks ensures the bytes sent to a native runtime are a complete PNG.
    offset = len(PNG_SIGNATURE)
    width: int | None = None
    height: int | None = None
    saw_idat = False
    saw_iend = False
    while offset < len(data):
        if len(data) - offset < 12:
            raise _invalid(path, "PNG chunk is truncated")
        chunk_length = struct.unpack_from(">I", data, offset)[0]
        chunk_type_start = offset + 4
        chunk_data_start = offset + 8
        chunk_end = chunk_data_start + chunk_length
        crc_end = chunk_end + 4
        if crc_end > len(data):
            raise _invalid(path, "PNG chunk is truncated")
        chunk_type = data[chunk_type_start:chunk_data_start]
        chunk_data = data[chunk_data_start:chunk_end]
        expected_crc = struct.unpack_from(">I", data, chunk_end)[0]
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            raise _invalid(path, "PNG chunk CRC is invalid")
        if offset == len(PNG_SIGNATURE):
            if chunk_type != b"IHDR" or chunk_length != 13:
                raise _invalid(path, "PNG IHDR header is invalid")
            width, height = struct.unpack_from(">II", chunk_data)
            if width == 0 or height == 0:
                raise _invalid(path, "PNG dimensions must be positive")
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                raise _invalid(
                    path,
                    f"PNG dimensions {width}x{height} exceed the {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} limit",
                )
        elif chunk_type == b"IHDR":
            raise _invalid(path, "PNG contains more than one IHDR header")
        elif chunk_type == b"IDAT":
            saw_idat = True
        elif chunk_type == b"IEND":
            if chunk_length != 0:
                raise _invalid(path, "PNG IEND chunk is invalid")
            saw_iend = True
            if crc_end != len(data):
                raise _invalid(path, "PNG contains data after IEND")
        offset = crc_end
    if width is None or height is None or not saw_idat or not saw_iend:
        raise _invalid(path, "PNG must contain IHDR, IDAT, and IEND chunks")
    if ImageFile.LOAD_TRUNCATED_IMAGES:
        raise _invalid(path, "permissive truncated-image decoding is not allowed")
    try:
        with Image.open(io.BytesIO(data), formats=("PNG",)) as decoded:
            if decoded.format != "PNG" or decoded.size != (width, height) or getattr(decoded, "n_frames", 1) != 1:
                raise _invalid(path, "expected a single static PNG with matching dimensions")
            decoded.load()
    except (OSError, ValueError, SyntaxError) as exc:
        raise _invalid(path, f"PNG pixel data cannot be fully decoded: {exc}") from exc
    return width, height


def _read_image(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise _invalid(path, "image path is not a regular file")
        if metadata.st_size > MAX_IMAGE_BYTES:
            raise _invalid(path, f"image is {metadata.st_size} bytes; maximum is {MAX_IMAGE_BYTES} bytes")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            data = handle.read(MAX_IMAGE_BYTES + 1)
    except HarnessError:
        raise
    except (OSError, ValueError) as exc:
        raise _invalid(path, f"cannot read file: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(data) > MAX_IMAGE_BYTES:
        raise _invalid(path, f"image is larger than the {MAX_IMAGE_BYTES} byte limit")
    return data


def _check_path(workspace: Path, relative: Path) -> Path:
    if relative.is_absolute():
        raise _invalid(relative, "absolute paths are not allowed; use a workspace-relative path")
    if "\x00" in str(relative):
        raise _invalid(relative, "NUL bytes are not allowed in paths")
    if any(part == ".." for part in relative.parts):
        raise _invalid(relative, "path traversal is not allowed")
    # A backslash is a path separator on Windows.  Rejecting it everywhere
    # keeps the same relative-path contract if requests are moved between
    # platforms and avoids a platform-dependent traversal interpretation.
    if any("\\" in part for part in relative.parts):
        raise _invalid(relative, "backslashes are not allowed in image paths")
    candidate = workspace / relative
    ancestor = workspace
    try:
        if workspace.is_symlink():
            raise _invalid(workspace, "workspace symlinks are not allowed for image inputs")
        for part in relative.parts:
            ancestor /= part
            if ancestor.is_symlink():
                raise _invalid(relative, "symlink ancestors and files are not allowed")
        workspace_real = workspace.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except HarnessError:
        raise
    except (OSError, RuntimeError) as exc:
        raise _invalid(relative, f"path cannot be resolved: {exc}") from exc
    if not resolved.is_relative_to(workspace_real):
        raise _invalid(relative, "path resolves outside the workspace")
    if not candidate.is_file():
        raise _invalid(relative, "image path is not a regular file")
    return candidate


def validate_image_inputs(
    images: Iterable[str | os.PathLike[str]],
    workspace: str | os.PathLike[str],
    *,
    purpose: str | None = None,
) -> tuple[ImageInput, ...]:
    """Validate and snapshot ordered workspace-relative PNG inputs.

    Validation is intentionally content-based and runs before a runtime
    session, credential lookup, or model request is started.  The returned
    snapshots retain the bytes read during validation so a later source-file
    change cannot alter the bytes sent to a native runtime.
    """

    image_paths = tuple(Path(path) for path in images)
    if not image_paths:
        return ()
    if purpose is not None and purpose != "evaluation":
        raise HarnessError("image inputs are supported for evaluation requests only")
    if len(image_paths) > MAX_IMAGE_COUNT:
        raise HarnessError(f"image request contains {len(image_paths)} images; maximum is {MAX_IMAGE_COUNT}")

    workspace_path = Path(workspace).expanduser().absolute()
    if not workspace_path.is_dir():
        raise HarnessError(f"image input workspace is not a directory: {workspace_path}")
    validated: list[ImageInput] = []
    total_bytes = 0
    for relative in image_paths:
        candidate = _check_path(workspace_path, relative)
        data = _read_image(candidate)
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_IMAGE_BYTES:
            raise HarnessError(
                f"image request is {total_bytes} bytes; aggregate maximum is {MAX_TOTAL_IMAGE_BYTES} bytes"
            )
        width, height = _png_dimensions(relative, data)
        validated.append(
            ImageInput(
                path=relative.as_posix(),
                sha256=hashlib.sha256(data).hexdigest(),
                bytes=len(data),
                width=width,
                height=height,
                data=data,
            )
        )
    return tuple(validated)


def image_input_manifest(images: Sequence[ImageInput]) -> list[dict[str, Any]]:
    """Return ordered image identities without embedding image bytes."""

    return [image.manifest_entry() for image in images]


def image_manifest(
    workspace: str | os.PathLike[str], images: Iterable[str | os.PathLike[str]]
) -> list[dict[str, Any]]:
    """Validate paths and return the redacted manifest expected by callers."""

    return image_input_manifest(validate_image_inputs(images, workspace))


def image_input_receipt(images: Sequence[ImageInput]) -> dict[str, Any]:
    """Return a redacted JSONL event proving which images were attached."""

    return {"type": "harness.image_input", "images": image_input_manifest(images)}


def image_input_prompt(images: Sequence[ImageInput]) -> str:
    """Return the shared visible mapping used by both native runtimes."""

    return "\n".join(f"Image {index}: {image.path}" for index, image in enumerate(images, 1))


def stage_image_inputs(workspace: str | os.PathLike[str], images: Sequence[ImageInput]) -> None:
    """Write validated bytes into an isolated workspace at their relative paths."""

    root = Path(workspace)
    for image in images:
        target = root / Path(image.path)
        ancestor = root
        for part in Path(image.path).parts:
            ancestor /= part
            if ancestor.is_symlink():
                raise _invalid(image.path, "isolated image path contains a symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise _invalid(image.path, "isolated image path is a symlink")
        try:
            target.write_bytes(image.data)
        except OSError as exc:
            raise _invalid(image.path, f"cannot stage image bytes: {exc}") from exc
