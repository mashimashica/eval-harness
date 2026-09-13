# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Read-only compatibility resolver for the installed BigCodeBench runtime.

The reviewed CI installer owns provisioning.  Runtime code must not create a
virtual environment, resolve dependencies, or download packages; this module
only validates an existing physical interpreter for older integrations that
still import the helper name.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def resolve_bcb_python(venv_path: Path, python_version: str = "3.11.16") -> Path:
    """Return the existing physical grader interpreter without mutation."""

    try:
        venv = Path(venv_path).resolve(strict=True)
        python = (venv / "bin" / "python").resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError("BigCodeBench grader interpreter is unavailable") from exc
    if not venv.is_dir() or venv.is_symlink() or python.is_symlink() or not python.is_file():
        raise RuntimeError("BigCodeBench grader interpreter is unavailable")
    try:
        completed = subprocess.run(
            (
                str(python),
                "-I",
                "-B",
                "-c",
                "import platform; print(platform.python_version(), platform.machine())",
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("BigCodeBench grader interpreter cannot be inspected") from exc
    observed = completed.stdout.decode("utf-8", errors="replace").strip()
    if completed.returncode != 0 or observed != f"{python_version} x86_64":
        raise RuntimeError("BigCodeBench grader interpreter identity is invalid")
    return python


def ensure_bcb_venv(venv_path: Path, python_version: str = "3.11.16") -> Path:
    """Compatibility spelling for the read-only runtime resolver."""

    return resolve_bcb_python(venv_path, python_version)


__all__ = ["ensure_bcb_venv", "resolve_bcb_python"]
