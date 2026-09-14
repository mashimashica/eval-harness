# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verified macOS native Bash policy and a private spreadsheet toolchain."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import et_xmlfile  # type: ignore[import-untyped]
import openpyxl

from .errors import HarnessError
from .executor import RuntimeSession

CONTEXT_FOLDERS = ("reference_files", "skill", "creation_inputs", "creator_skills")
DISALLOWED_TOOLS = (
    "Read,Write,Edit,Glob,Grep,Agent,TaskOutput,NotebookEdit,WebFetch,WebSearch,ReportFindings,TaskStop,Skill,"
    "EnterWorktree,ExitWorktree,SendMessage,ListAgents,Workflow,CronCreate,CronDelete,CronList,ScheduleWakeup,"
    "RemoteTrigger,ToolSearch"
)


def copy_office_runtime(target: Path) -> Path:
    """Copy only the locked interpreter/stdlib and two pure Python packages."""
    if sys.platform != "darwin" or sys.version_info[:2] != (3, 13):
        raise HarnessError("Claude sandboxed_shell requires verified macOS and Python 3.13")
    source = Path(sys.base_prefix).resolve()
    python = source / "bin" / "python3.13"
    if not python.is_file() or not (source / "lib" / "python3.13").is_dir():
        raise HarnessError("Claude sandboxed_shell requires the project uv Python distribution")
    bindir = target / "bin"
    bindir.mkdir(parents=True)
    shutil.copy2(python, bindir / "python3.13")
    shutil.copytree(
        source / "lib" / "python3.13",
        target / "lib" / "python3.13",
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "*.pyo", "site-packages", "ensurepip", "idlelib", "tkinter", "turtledemo", "venv"
        ),
    )
    site = target / "lib" / "python3.13" / "site-packages"
    for package in (openpyxl, et_xmlfile):
        package_file = package.__file__
        if not isinstance(package_file, str):
            raise HarnessError("isolated office package has no local source")
        shutil.copytree(
            Path(package_file).resolve().parent,
            site / package.__name__,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    wrapper = bindir / "python-openpyxl"
    wrapper.write_text(
        "#!/bin/sh\nunset PYTHONHOME\n"
        f"export PYTHONPATH={shlex.quote(str(site))}\n"
        "export PYTHONNOUSERSITE=1\nexport PYTHONDONTWRITEBYTECODE=1\n"
        f'exec {shlex.quote(str(bindir / "python3.13"))} -S "$@"\n'
    )
    wrapper.chmod(0o700)
    if any(path.is_symlink() for path in target.rglob("*")):
        raise HarnessError("the isolated Python toolchain contains an unsupported symbolic link")
    return wrapper


def sandbox_settings(session: RuntimeSession, runtime: Path, scratch: Path, *, read_only: bool) -> dict[str, Any]:
    root = session.workspace.parent
    deny_write = [str(session.workspace / name) for name in CONTEXT_FOLDERS]
    deny_write += [str(runtime), str(session.config_home), str(root / "home"), str(Path.home().resolve())]
    if read_only:
        deny_write.insert(0, str(root))
    return {
        "disableAllHooks": True,
        "permissions": {
            # Bash is confined by the native OS deny-all read policy below.
            # The additional static Python-path heuristic rejects legitimate
            # cached-cell reads, despite their literal in-workspace paths.
            "blockReadsOutsideWorkingDirectories": False,
            "disableBypassPermissionsMode": "disable",
            "deny": DISALLOWED_TOOLS.split(","),
        },
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
            "excludedCommands": [],
            "filesystem": {
                "allowWrite": [],
                "denyWrite": deny_write,
                "denyRead": ["/"],
                "allowRead": [
                    "/bin",
                    "/dev",
                    "/usr/bin",
                    "/usr/lib",
                    "/usr/share",
                    "/System/Library",
                    str(session.workspace),
                    str(runtime),
                    str(scratch),
                ],
            },
            "network": {
                "allowedDomains": [],
                "strictAllowlist": True,
                "allowUnixSockets": [],
                "allowAllUnixSockets": False,
                "allowLocalBinding": False,
            },
            "credentials": {
                "files": [{"path": str(session.config_home / ".credentials.json"), "mode": "deny"}],
                "envVars": [
                    {"name": name, "mode": "deny"}
                    for name in (
                        "ANTHROPIC_API_KEY",
                        "CLAUDE_CODE_OAUTH_TOKEN",
                        "AWS_ACCESS_KEY_ID",
                        "AWS_SECRET_ACCESS_KEY",
                        "AWS_SESSION_TOKEN",
                        "OPENAI_API_KEY",
                    )
                ],
            },
        },
    }


def verify_sandbox(command: list[str], session: RuntimeSession) -> dict[str, Any]:
    """Ask the actual native CLI whether this invocation enforces the policy."""
    try:
        result = subprocess.run(
            command + ["sandbox", "status"],
            cwd=session.workspace,
            env=session.environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
        )
        status = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise HarnessError("Claude native sandbox status unavailable; no model request sent") from None
    if (
        result.returncode
        or status.get("enabled") is not True
        or status.get("supported") is not True
        or status.get("strictMode") is not True
        or status.get("filesystemPolicy") != "strict"
    ):
        raise HarnessError("Claude native strict sandbox is unavailable; no model request sent")
    return status  # type: ignore[no-any-return]
