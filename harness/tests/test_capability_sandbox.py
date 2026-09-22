# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

import pytest

from eval_harness.capability_sandbox import (
    SandboxError,
    make_policy,
    sandbox_profile,
    terminate_active_processes,
)
from eval_harness.capability_service import CapabilityService


def test_policy_has_role_specific_writable_roots_and_protected_contexts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("reference_files", "skill", "creation_inputs", "creator_skills", "evidence"):
        (workspace / name).mkdir()
    creation_scratch = workspace / ".capability-scratch"
    creation_scratch.mkdir()
    creation = make_policy(workspace, creation_scratch, "application", {"network_domains": []})
    profile = sandbox_profile(creation)
    assert f'(allow file-write* (subpath "{workspace}")' in profile
    assert f'(subpath "{workspace}/reference_files")' in profile
    assert "(deny network*)" in profile

    evaluation_scratch = workspace / "scratch"
    evaluation_scratch.mkdir()
    evaluation = make_policy(workspace, evaluation_scratch, "evaluation", {"network_domains": []})
    evaluation_profile = sandbox_profile(evaluation)
    assert f'(allow file-write* (subpath "{evaluation_scratch}")' in evaluation_profile
    assert f'(allow file-write* (subpath "{workspace}")' not in evaluation_profile


def test_policy_rejects_relative_or_broad_runtime_roots(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scratch = workspace / ".capability-scratch"
    scratch.mkdir()
    with pytest.raises(SandboxError, match="absolute"):
        make_policy(workspace, scratch, "application", {"python_roots": ["runtime"]})
    with pytest.raises(SandboxError, match="too broad"):
        make_policy(workspace, scratch, "application", {"python_roots": ["/"]})


@pytest.mark.skipif(sys.platform != "darwin", reason="native Seatbelt is required")
def test_application_shell_probe_protects_context_and_journals_output(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    workspace.mkdir()
    (workspace / "reference_files").mkdir()
    reference = workspace / "reference_files" / "input.txt"
    reference.write_text("original", encoding="utf-8")
    service = CapabilityService(workspace, state, "application", {"network_domains": []})
    assert service.shell_available
    result = service.invoke(
        "shell",
        {
            "command": "printf created > created.txt; printf changed > reference_files/input.txt; exec /bin/cat created.txt"
        },
    )
    assert result["status"] == "completed"
    assert result["stdout"] == "created"
    assert reference.read_text(encoding="utf-8") == "original"
    assert (workspace / "created.txt").read_text(encoding="utf-8") == "created"
    assert (state / "events.jsonl").is_file()
    event = json.loads((state / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event["tool"] == "shell"
    assert Path(event["output_path"]).is_file()
    assert (state / "active-processes.json").read_text(encoding="utf-8") == '{"processes": [], "version": 1}'


@pytest.mark.skipif(sys.platform != "darwin", reason="native Seatbelt is required")
def test_evaluation_shell_can_write_scratch_but_not_originals(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    workspace.mkdir()
    submission = workspace / "submission.txt"
    submission.write_text("immutable", encoding="utf-8")
    service = CapabilityService(workspace, state, "evaluation", {"network_domains": []})
    result = service.invoke(
        "shell",
        {
            "command": "printf changed > submission.txt; printf derived > scratch/result.txt; exec /bin/cat submission.txt"
        },
    )
    assert result["status"] == "completed"
    assert submission.read_text(encoding="utf-8") == "immutable"
    assert (workspace / "scratch" / "result.txt").read_text(encoding="utf-8") == "derived"


@pytest.mark.skipif(sys.platform != "darwin", reason="native Seatbelt is required")
def test_native_profile_denies_fork_spawn_and_cleans_setsid_timeout(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    workspace.mkdir()
    runtime = Path(sys.executable).resolve()
    if not runtime.is_file():
        pytest.skip("test interpreter is unavailable")
    service = CapabilityService(
        workspace,
        state,
        "application",
        {"network_domains": [], "python": str(runtime), "python_roots": [str(runtime.parent.parent)]},
    )
    assert service.shell_available
    python_probe = """import os
import sys

def denied(name, operation):
    try:
        value = operation()
    except OSError:
        print(name + "-denied")
        return
    if name == "fork" and value == 0:
        os._exit(42)
    raise SystemExit("sandbox unexpectedly allowed " + name)

denied("fork", os.fork)
denied("spawn", lambda: os.posix_spawn("/bin/true", ["/bin/true"], os.environ.copy()))
try:
    os.setsid()
    session = "setsid-ok"
except OSError:
    session = "setsid-denied"
print("python-exec-ok " + session)
"""
    result = service.invoke(
        "shell",
        {"command": f"exec {shlex.quote(str(runtime))} -c {shlex.quote(python_probe)}"},
    )
    assert result["status"] == "completed"
    assert "fork-denied" in result["stdout"]
    assert "spawn-denied" in result["stdout"]
    assert "python-exec-ok " in result["stdout"]

    background = service.invoke("shell", {"command": ": &"})
    assert background["status"] == "failed"
    assert "fork" in background["stderr"].lower()

    timeout_code = (
        "import os,time; open('.capability-scratch/timeout.pid','w').write(str(os.getpid())); time.sleep(10)"
    )
    timed_out = service.invoke(
        "shell",
        {"command": f"exec {shlex.quote(str(runtime))} -c {shlex.quote(timeout_code)}", "timeout_seconds": 0.2},
    )
    assert timed_out["status"] == "timeout"
    pid = int((workspace / ".capability-scratch" / "timeout.pid").read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_terminate_active_processes_ignores_malformed_or_unrelated_registry(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "active-processes.json").write_text('{"processes":[{"pid":1,"pgid":1},{"pid":"bad"}]}', encoding="utf-8")
    terminate_active_processes(state)
    assert json.loads((state / "active-processes.json").read_text(encoding="utf-8")) == {
        "processes": [],
        "version": 1,
    }
