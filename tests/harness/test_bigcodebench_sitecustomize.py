# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration regressions for the isolated BigCodeBench NLTK bootstrap."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import venv
from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import patch

import eval_harness.bigcodebench_sitecustomize as sitecustomize


POLICY_ENVIRONMENT_VARIABLE = "BIGCODEBENCH_NLTK_OFFLINE"
POLICY_REVISION = "bigcodebench-bwrap-v1"
NLTK_DATA_PATH = "/opt/bigcodebench/nltk_data"
NLTK_INDEX_URL = "file:///opt/bigcodebench/nltk_data/index.xml"


class _FakeDownloader:
    def __init__(self, url: str, download_dir: str) -> None:
        self._url = url
        self._download_dir = download_dir

    @property
    def download_dir(self) -> str:
        return self._download_dir

    @download_dir.setter
    def download_dir(self, value: str) -> None:
        self._download_dir = value

    def download(self, *_args: object, **_kwargs: object) -> bool:
        return True


class _FakeData:
    def __init__(self, path: list[str]) -> None:
        self.path = path


class _FakeDownloaderModule:
    def __init__(self, downloader: _FakeDownloader, alias_owner: _FakeDownloader) -> None:
        self._downloader = downloader
        self.download: Callable[..., object] = alias_owner.download


class _FakeNltk:
    def __init__(
        self,
        data: _FakeData,
        downloader_module: _FakeDownloaderModule,
        alias_owner: _FakeDownloader,
    ) -> None:
        self.data = data
        self.downloader = downloader_module
        self.download: Callable[..., object] = alias_owner.download


def _bound_owner(method: Callable[..., object]) -> object:
    return object.__getattribute__(method, "__self__")


def _fake_modules(nltk_module: _FakeNltk, downloader_module: _FakeDownloaderModule) -> dict[str, types.ModuleType]:
    return {
        "nltk": cast(types.ModuleType, nltk_module),
        "nltk.data": cast(types.ModuleType, nltk_module.data),
        "nltk.downloader": cast(types.ModuleType, downloader_module),
    }


def _run_isolated_startup(
    *,
    policy: str | None,
    nltk_files: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the copied bootstrap through a fresh standard-library venv."""

    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        venv_path = temporary_path / "venv"
        venv.EnvBuilder(with_pip=False, clear=True).create(venv_path)
        python = venv_path / "bin" / "python"
        site_packages = (
            venv_path / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
        )
        source = Path(sitecustomize.__file__)
        shutil.copyfile(source, site_packages / "sitecustomize.py")

        for relative_path, contents in (nltk_files or {}).items():
            fixture_path = site_packages / relative_path
            fixture_path.parent.mkdir(parents=True, exist_ok=True)
            fixture_path.write_text(contents, encoding="utf-8")

        environment = {} if policy is None else {POLICY_ENVIRONMENT_VARIABLE: policy}
        return subprocess.run(
            [str(python), "-I", "-B", "-c", "print('BIGCODEBENCH_USER_CODE')"],
            capture_output=True,
            cwd=temporary,
            env=environment,
            text=True,
            timeout=15,
            check=False,
        )


class TestBigCodeBenchSitecustomize(unittest.TestCase):
    def test_nonliteral_policy_does_not_import_nltk(self) -> None:
        with (
            patch.dict(os.environ, {POLICY_ENVIRONMENT_VARIABLE: "other-policy"}, clear=True),
            patch.object(importlib, "import_module", side_effect=AssertionError("unexpected NLTK import")),
        ):
            sitecustomize.configure_bigcodebench_nltk()

    def test_literal_policy_sets_exact_paths_and_rebinds_aliases(self) -> None:
        data = _FakeData(["/host/nltk_data", "/another/path"])
        downloader = _FakeDownloader("https://example.invalid/index.xml", "/host/downloads")
        stale = _FakeDownloader("https://stale.invalid/index.xml", "/stale")
        downloader_module = _FakeDownloaderModule(downloader, stale)
        nltk_module = _FakeNltk(data, downloader_module, stale)
        modules = _fake_modules(nltk_module, downloader_module)

        with (
            patch.dict(os.environ, {POLICY_ENVIRONMENT_VARIABLE: POLICY_REVISION}, clear=True),
            patch.dict(sys.modules, modules),
        ):
            sitecustomize.configure_bigcodebench_nltk()

        self.assertIs(nltk_module.downloader._downloader, downloader)
        self.assertEqual(downloader._url, NLTK_INDEX_URL)
        self.assertEqual(downloader.download_dir, NLTK_DATA_PATH)
        self.assertEqual(data.path, [NLTK_DATA_PATH])
        self.assertIs(nltk_module.downloader, downloader_module)
        self.assertIs(_bound_owner(nltk_module.download), downloader)
        self.assertIs(_bound_owner(downloader_module.download), downloader)

    def test_literal_configuration_is_idempotent_and_preserves_downloader_identity(self) -> None:
        data = _FakeData([])
        downloader = _FakeDownloader("old-url", "old-dir")
        downloader_module = _FakeDownloaderModule(downloader, downloader)
        nltk_module = _FakeNltk(data, downloader_module, downloader)

        with (
            patch.dict(os.environ, {POLICY_ENVIRONMENT_VARIABLE: POLICY_REVISION}, clear=True),
            patch.dict(sys.modules, _fake_modules(nltk_module, downloader_module)),
        ):
            sitecustomize.configure_bigcodebench_nltk()
            first_downloader = downloader_module._downloader
            first_path = data.path
            sitecustomize.configure_bigcodebench_nltk()

        self.assertIs(downloader_module._downloader, first_downloader)
        self.assertIs(data.path, first_path)
        self.assertEqual(data.path, [NLTK_DATA_PATH])
        self.assertIs(_bound_owner(nltk_module.download), downloader)

    def test_literal_policy_surfaces_missing_or_malformed_nltk_dependency(self) -> None:
        with (
            patch.dict(os.environ, {POLICY_ENVIRONMENT_VARIABLE: POLICY_REVISION}, clear=True),
            patch.dict(
                sys.modules,
                {
                    "nltk": cast(types.ModuleType, None),
                    "nltk.data": cast(types.ModuleType, None),
                    "nltk.downloader": cast(types.ModuleType, None),
                },
            ),
        ):
            with self.assertRaises(ModuleNotFoundError):
                sitecustomize.configure_bigcodebench_nltk()

        malformed_downloader = cast(_FakeDownloaderModule, object())
        malformed_nltk = _FakeNltk(_FakeData([]), malformed_downloader, _FakeDownloader("url", "dir"))
        with (
            patch.dict(os.environ, {POLICY_ENVIRONMENT_VARIABLE: POLICY_REVISION}, clear=True),
            patch.dict(sys.modules, _fake_modules(malformed_nltk, malformed_downloader)),
        ):
            with self.assertRaises(AttributeError):
                sitecustomize.configure_bigcodebench_nltk()

    def test_isolated_startup_fails_closed_for_nltk_dependency_errors(self) -> None:
        cases: tuple[tuple[str, dict[str, str], str | None], ...] = (
            ("missing", {}, None),
            (
                "malformed",
                {
                    "nltk/__init__.py": "class _Data:\n    path = []\ndata = _Data()\n",
                    "nltk/downloader.py": "_downloader = object()\n",
                },
                None,
            ),
            (
                "secret-bearing",
                {"nltk/__init__.py": "raise RuntimeError('offline-secret-token')\n"},
                "offline-secret-token",
            ),
        )
        for name, nltk_files, secret in cases:
            with self.subTest(name=name):
                result = _run_isolated_startup(policy=POLICY_REVISION, nltk_files=nltk_files)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("BIGCODEBENCH_USER_CODE", result.stdout)
                self.assertIn("BigCodeBench NLTK offline bootstrap failed", result.stderr)
                if secret is not None:
                    self.assertNotIn(secret, result.stdout + result.stderr)

    def test_isolated_startup_without_policy_continues_without_nltk(self) -> None:
        result = _run_isolated_startup(policy=None)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "BIGCODEBENCH_USER_CODE\n")
        self.assertEqual(result.stderr, "")
