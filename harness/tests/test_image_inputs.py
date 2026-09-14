# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

import pytest

from eval_harness.errors import HarnessError
from eval_harness.image_inputs import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_COUNT,
    MAX_IMAGE_DIMENSION,
    MAX_TOTAL_IMAGE_BYTES,
    image_input_prompt,
    image_input_receipt,
    image_manifest,
    stage_image_inputs,
    validate_image_inputs,
)


def png_bytes(width: int = 1, height: int = 1, padding: int = 0) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)

    def chunk(kind: bytes, value: bytes) -> bytes:
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF)

    idat = zlib.compress((b"\x00" + b"\x00" * (width * 4)) * height) + (b"x" * padding)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def test_manifest_contains_identity_and_dimensions_without_bytes(tmp_path: Path) -> None:
    image = tmp_path / "preview.png"
    source = png_bytes(120, 80, 7)
    image.write_bytes(source)

    entries = image_manifest(tmp_path, (Path("preview.png"),))

    assert entries == [
        {
            "path": "preview.png",
            "sha256": hashlib.sha256(source).hexdigest(),
            "bytes": len(source),
            "width": 120,
            "height": 80,
        }
    ]
    assert all("data" not in entry for entry in entries)
    assert image.read_bytes() == source


def test_crc_valid_truncated_pixels_are_rejected_before_native_execution(tmp_path: Path) -> None:
    def chunk(kind: bytes, value: bytes) -> bytes:
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF)

    # One RGBA pixel requires a filter byte plus four channel bytes, even with valid CRCs.
    malformed = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00" * 4))
        + chunk(b"IEND", b"")
    )
    (tmp_path / "truncated.png").write_bytes(malformed)
    with pytest.raises(HarnessError, match="fully decoded"):
        validate_image_inputs((Path("truncated.png"),), tmp_path, purpose="evaluation")


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        (Path("../outside.png"), "traversal"),
        (Path("/outside.png"), "absolute"),
    ],
)
def test_relative_path_boundary_is_enforced(tmp_path: Path, relative: Path, message: str) -> None:
    (tmp_path / "inside.png").write_bytes(png_bytes())
    with pytest.raises(HarnessError, match=message):
        validate_image_inputs((relative,), tmp_path)


def test_symlink_file_and_ancestor_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.png"
    target.write_bytes(png_bytes())
    (tmp_path / "file-link.png").symlink_to(target)
    (tmp_path / "directory").mkdir()
    (tmp_path / "directory" / "nested.png").write_bytes(png_bytes())
    (tmp_path / "directory-link").symlink_to(tmp_path / "directory", target_is_directory=True)

    with pytest.raises(HarnessError, match="symlink"):
        validate_image_inputs((Path("file-link.png"),), tmp_path)
    with pytest.raises(HarnessError, match="symlink"):
        validate_image_inputs((Path("directory-link/nested.png"),), tmp_path)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not a png", "signature"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "CRC"),
        (png_bytes(MAX_IMAGE_DIMENSION + 1, 1), "dimensions"),
    ],
)
def test_png_signature_and_dimensions_are_checked(tmp_path: Path, data: bytes, message: str) -> None:
    (tmp_path / "image.png").write_bytes(data)
    with pytest.raises(HarnessError, match=message):
        validate_image_inputs((Path("image.png"),), tmp_path)


def test_per_image_and_request_limits_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "large.png").write_bytes(png_bytes(padding=MAX_IMAGE_BYTES))
    with pytest.raises(HarnessError, match="maximum"):
        validate_image_inputs((Path("large.png"),), tmp_path)

    count_paths: list[Path] = []
    for index in range(MAX_IMAGE_COUNT + 1):
        path = tmp_path / f"count-{index}.png"
        path.write_bytes(png_bytes())
        count_paths.append(path.relative_to(tmp_path))
    with pytest.raises(HarnessError, match="maximum"):
        validate_image_inputs(count_paths, tmp_path)

    aggregate_paths: list[Path] = []
    chunk = MAX_TOTAL_IMAGE_BYTES // 7 + 1
    for index in range(7):
        path = tmp_path / f"aggregate-{index}.png"
        path.write_bytes(png_bytes(padding=chunk))
        aggregate_paths.append(path.relative_to(tmp_path))
    with pytest.raises(HarnessError, match="aggregate"):
        validate_image_inputs(aggregate_paths, tmp_path)


def test_images_are_evaluation_only_and_staging_preserves_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    original = png_bytes(17, 19, 3)
    source.write_bytes(original)
    image = validate_image_inputs((Path("source.png"),), tmp_path, purpose="evaluation")

    with pytest.raises(HarnessError, match="evaluation"):
        validate_image_inputs((Path("source.png"),), tmp_path, purpose="application")

    isolated = tmp_path / "isolated"
    isolated.mkdir()
    source.write_bytes(png_bytes(1, 1, 1))
    stage_image_inputs(isolated, image)
    assert (isolated / "source.png").read_bytes() == original

    receipt = image_input_receipt(image)
    assert receipt["type"] == "harness.image_input"
    assert receipt["images"][0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert "data" not in receipt["images"][0]
    assert image_input_prompt(image) == "Image 1: source.png"
