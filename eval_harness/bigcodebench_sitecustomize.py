# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configure the pinned, read-only NLTK data tree for BigCodeBench.

This file is copied byte-for-byte to the trusted grader virtual environment as
``sitecustomize.py``.  It intentionally has no repository imports: ordinary
interpreter startup must not import NLTK, and the literal sandbox policy is the
only condition that enables the configuration.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from typing import Final, Protocol, cast


_POLICY_ENVIRONMENT_VARIABLE: Final[str] = "BIGCODEBENCH_NLTK_OFFLINE"
_POLICY_REVISION: Final[str] = "bigcodebench-bwrap-v1"
_NLTK_DATA_PATH: Final[str] = "/opt/bigcodebench/nltk_data"
_NLTK_INDEX_URL: Final[str] = "file:///opt/bigcodebench/nltk_data/index.xml"
_STARTUP_FAILURE_MESSAGE: Final[str] = "BigCodeBench NLTK offline bootstrap failed"


class _Downloader(Protocol):
    _url: str
    download_dir: str
    download: Callable[..., object]


class _DownloaderModule(Protocol):
    _downloader: _Downloader
    download: Callable[..., object]


class _NltkDataModule(Protocol):
    path: list[str]


class _NltkModule(Protocol):
    data: _NltkDataModule
    downloader: _DownloaderModule
    download: Callable[..., object]


def _load_nltk() -> tuple[_NltkModule, _DownloaderModule]:
    nltk_module = cast(_NltkModule, importlib.import_module("nltk"))
    downloader_module = cast(_DownloaderModule, importlib.import_module("nltk.downloader"))
    return nltk_module, downloader_module


def configure_bigcodebench_nltk() -> None:
    """Configure the pinned downloader only under the literal sandbox policy."""

    if os.environ.get(_POLICY_ENVIRONMENT_VARIABLE) != _POLICY_REVISION:
        return

    nltk_module, downloader_module = _load_nltk()
    downloader = downloader_module._downloader
    downloader._url = _NLTK_INDEX_URL
    downloader.download_dir = _NLTK_DATA_PATH
    nltk_module.data.path[:] = [_NLTK_DATA_PATH]

    # NLTK 3.10.3 exposes bound-method aliases in both modules.  Rebind each
    # alias after mutating the retained module-global object so none can point
    # at a stale downloader instance.
    bound_download = downloader.download
    downloader_module.download = bound_download
    nltk_module.downloader = downloader_module
    nltk_module.download = bound_download


def _configure_at_startup() -> None:
    """Make automatic interpreter startup fail closed without exposing details."""

    try:
        configure_bigcodebench_nltk()
    except Exception:
        # CPython's site module suppresses ordinary import exceptions from
        # sitecustomize.  SystemExit is deliberately outside that boundary,
        # making a failed offline dependency a fatal startup error.  Keep the
        # original exception and its potentially sensitive message private.
        raise SystemExit(_STARTUP_FAILURE_MESSAGE) from None


_configure_at_startup()
