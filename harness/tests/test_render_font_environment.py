# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Font configuration must remain usable after relocation and independent of user settings."""

from pathlib import Path
from xml.etree import ElementTree

import pytest

from eval_harness.artifacts import sha256_file
from eval_harness.errors import ArtifactError
from eval_harness.office_rendering import _environment, _font_snapshot


def test_relocated_fonts_use_only_the_bundle_and_private_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    office = tmp_path / "relocated & office/Office.app"
    fonts = office / "Contents/Resources/fonts/truetype"
    fonts.mkdir(parents=True)
    (fonts / "fixture.ttf").write_bytes(b"font enumeration fixture; native rendering is checked separately")
    work = tmp_path / "temporary work"
    work.mkdir()
    monkeypatch.setenv("FONTCONFIG_FILE", "/unrelated/personal/fonts.conf")
    monkeypatch.setenv("FONTCONFIG_PATH", "/unrelated/personal")
    monkeypatch.setenv("XDG_CACHE_HOME", "/unrelated/shared-cache")
    monkeypatch.setenv("HOME", "/unrelated/home")
    environment = _environment(work, tmp_path / "poppler", office)
    config = Path(environment["FONTCONFIG_FILE"])
    parsed = ElementTree.parse(config)
    assert [node.text for node in parsed.findall("dir")] == [str(fonts.resolve())]
    assert [node.text for node in parsed.findall("cachedir")] == [str(work / "font-cache")]
    assert parsed.findall("include") == []
    assert "unrelated" not in config.read_text()
    assert environment["HOME"] == str(work / "home")
    assert "FONTCONFIG_PATH" not in environment and "XDG_CACHE_HOME" not in environment
    assert {node.findtext("family"): node.findtext("prefer/family") for node in parsed.findall("alias")} == {
        "Helvetica": "Liberation Sans",
        "Times": "Liberation Serif",
        "Courier": "Liberation Mono",
    }
    snapshot = _font_snapshot(environment)
    assert snapshot is not None and snapshot["sha256"] == sha256_file(config)
    assert snapshot["configuration"] == config.read_text()
    # Conversion and shell isolation probes retain their former clean environment;
    # only the Poppler rendering call opts into the bundled-font policy.
    conversion = _environment(work, tmp_path / "poppler")
    assert "FONTCONFIG_FILE" not in conversion and _font_snapshot(conversion) is None


@pytest.mark.parametrize("state", ["missing", "empty", "outside_link"])
def test_missing_or_external_bundle_fonts_are_not_replaced_by_personal_fonts(tmp_path: Path, state: str) -> None:
    office = tmp_path / "Office.app"
    fonts = office / "Contents/Resources/fonts/truetype"
    fonts.parent.mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    if state == "empty":
        fonts.mkdir()
    elif state == "outside_link":
        outside = tmp_path / "personal-fonts"
        outside.mkdir()
        (outside / "personal.ttf").write_bytes(b"private")
        fonts.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactError, match="fonts|font files"):
        _environment(work, tmp_path / "poppler", office)
    assert not (work / "fonts.conf").exists()
