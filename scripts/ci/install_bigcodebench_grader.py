#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Provision the fixed, candidate-only BigCodeBench grader environment.

The script is intentionally setup-only.  It creates fresh private roots,
verifies every downloaded byte before extraction, and writes a runtime
manifest separately from the candidate policy manifest.  It is never called
by a grade and has no dependency-resolution fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Final, cast


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval_harness.grader_sandbox import (  # noqa: E402
    canonical_json_bytes,
    file_inventory_sha256,
    load_canonical_manifest,
)


PYTHON_ASSET_URL: Final[str] = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/20260901/"
    "cpython-3.11.16%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
)
PYTHON_ASSET_SIZE: Final[int] = 30_778_779
PYTHON_ASSET_SHA256: Final[str] = "64427febea27864d136db46c8efe968eb6fa5ca2813ce1dca4bb95aec31cb2e4"
PYTHON_EXECUTABLE_SHA256: Final[str] = "1e761eb19d6f2594ab8dc64bd99ad4e1753589f3bf1ec199e4eef3aaa21e3930"
PYTHON_LICENSE_SHA256: Final[str] = "3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf"
PYTHON_VERSION: Final[str] = "3.11.16"
PYTHON_SOABI: Final[str] = "cpython-311-x86_64-linux-gnu"
LOCK_SHA256: Final[str] = "8d62cac6880124652638ff8716532d46d459aaf5cbe6e8c36b506a4d1e4de9bd"
POLICY_REVISION: Final[str] = "bigcodebench-bwrap-v1"
RUNTIME_MANIFEST_NAME: Final[str] = "runtime-manifest.json"


class ProvisioningError(RuntimeError):
    """A stable setup failure; no candidate or secret detail is included."""


def secure_new_directory(path: Path) -> Path:
    """Create one fresh, private directory without following an old path."""

    if not path.is_absolute():
        raise ProvisioningError("provisioning root must be absolute")
    try:
        path.mkdir(mode=0o700)
        path.chmod(0o700)
        metadata = path.lstat()
    except OSError as exc:
        raise ProvisioningError("provisioning root could not be created") from exc
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ProvisioningError("provisioning root has unsafe metadata")
    return path


def download_verified(url: str, destination: Path, expected_size: int, expected_sha256: str) -> Path:
    """Download one fixed URL into a new file with bounded size and hash checks."""

    if destination.exists() or destination.is_symlink():
        raise ProvisioningError("refusing to overwrite a download")
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(url, timeout=30) as response, destination.open("xb") as output:
            while True:
                chunk = response.read(min(1024 * 1024, expected_size - size + 1))
                if not chunk:
                    break
                size += len(chunk)
                if size > expected_size:
                    raise ProvisioningError("download exceeds its fixed size")
                digest.update(chunk)
                output.write(chunk)
    except ProvisioningError:
        destination.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError) as exc:
        destination.unlink(missing_ok=True)
        raise ProvisioningError("fixed download failed") from exc
    if size != expected_size or digest.hexdigest() != expected_sha256:
        destination.unlink(missing_ok=True)
        raise ProvisioningError("fixed download verification failed")
    return destination


def _archive_relative(name: str, expected_root: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ProvisioningError("archive contains an unsafe member")
    if path.parts[0] != expected_root:
        raise ProvisioningError("archive has an unexpected root")
    return PurePosixPath(*path.parts[1:])


def _contained_link(member_path: PurePosixPath, target: str) -> None:
    target_path = PurePosixPath(target)
    if target_path.is_absolute() or not target_path.parts:
        raise ProvisioningError("archive contains an unsafe link")
    resolved = PurePosixPath(*member_path.parts[:-1]) / target_path
    if resolved.is_absolute() or ".." in resolved.parts:
        raise ProvisioningError("archive link escapes its root")


def safe_extract_tar(archive_path: Path, destination: Path, *, expected_root: str = "python") -> None:
    """Extract a single-root tar without links, devices, or path traversal."""

    seen: set[str] = set()
    regular_bytes = 0
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            for member in archive.getmembers():
                relative = _archive_relative(member.name, expected_root)
                relative_name = relative.as_posix()
                if relative_name in seen:
                    raise ProvisioningError("archive contains a duplicate member")
                seen.add(relative_name)
                output = destination if not relative.parts else destination.joinpath(*relative.parts)
                if member.isdir():
                    if relative.parts:
                        output.mkdir(mode=0o700, parents=True, exist_ok=False)
                    continue
                output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if member.isfile():
                    regular_bytes += member.size
                    if regular_bytes > 4 * 1024**3:
                        raise ProvisioningError("archive expands beyond its fixed bound")
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ProvisioningError("archive member is unreadable")
                    with stream, output.open("xb") as target:
                        shutil.copyfileobj(stream, target, length=1024 * 1024)
                    output.chmod(member.mode & 0o777)
                elif member.issym():
                    _contained_link(PurePosixPath(member.name), member.linkname)
                    output.symlink_to(member.linkname)
                else:
                    raise ProvisioningError("archive contains a special or hard-linked member")
    except ProvisioningError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise ProvisioningError("archive extraction failed") from exc
    if not seen:
        raise ProvisioningError("archive is empty")


def safe_extract_zip(archive_path: Path, destination: Path, *, expected_root: str) -> None:
    """Extract a single-root zip while rejecting links, duplicates and specials."""

    seen: set[str] = set()
    regular_bytes = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                relative = _archive_relative(member.filename, expected_root)
                relative_name = relative.as_posix()
                if relative_name in seen:
                    raise ProvisioningError("archive contains a duplicate member")
                seen.add(relative_name)
                output = destination if not relative.parts else destination.joinpath(*relative.parts)
                mode = (member.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise ProvisioningError("archive contains a link")
                if member.is_dir():
                    if relative.parts:
                        output.mkdir(mode=0o700, parents=True, exist_ok=False)
                    continue
                if mode not in (0, stat.S_IFREG):
                    raise ProvisioningError("archive contains a special member")
                regular_bytes += member.file_size
                if regular_bytes > 4 * 1024**3:
                    raise ProvisioningError("archive expands beyond its fixed bound")
                output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with archive.open(member) as source, output.open("xb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
    except ProvisioningError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ProvisioningError("archive extraction failed") from exc
    if not seen:
        raise ProvisioningError("archive is empty")


def _run_checked(command: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProvisioningError("provisioning command failed") from exc
    if result.returncode != 0:
        raise ProvisioningError("provisioning command returned an error")
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ProvisioningError("provisioned file is unreadable") from exc
    return digest.hexdigest()


def _verify_python(prefix: Path) -> Path:
    python = prefix / "bin" / "python3.11"
    license_path = prefix / "lib" / "python3.11" / "LICENSE.txt"
    if python.is_symlink() or not python.is_file() or license_path.is_symlink() or not license_path.is_file():
        raise ProvisioningError("CPython artifact layout is invalid")
    if _sha256_file(python) != PYTHON_EXECUTABLE_SHA256 or _sha256_file(license_path) != PYTHON_LICENSE_SHA256:
        raise ProvisioningError("CPython identity does not match the pinned artifact")
    identity = _run_checked(
        [
            str(python),
            "-I",
            "-B",
            "-c",
            "import json,platform,sys,sysconfig; print(json.dumps({'version':platform.python_version(),'machine':platform.machine(),'soabi':sysconfig.get_config_var('SOABI'),'prefix':sys.prefix},sort_keys=True,separators=(',',':')))",
        ]
    )
    try:
        values = json.loads(identity.stdout)
    except ValueError as exc:
        raise ProvisioningError("CPython identity is malformed") from exc
    if not isinstance(values, dict) or values.get("version") != PYTHON_VERSION:
        raise ProvisioningError("CPython version mismatch")
    if values.get("machine") != "x86_64" or values.get("soabi") != PYTHON_SOABI:
        raise ProvisioningError("CPython platform mismatch")
    return python


def _normalize_venv_interpreter(venv_python: Path, canonical_python: Path) -> None:
    if not venv_python.is_symlink():
        if not venv_python.is_file() or _sha256_file(venv_python) != PYTHON_EXECUTABLE_SHA256:
            raise ProvisioningError("venv interpreter is not the pinned interpreter")
        return
    try:
        target = venv_python.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProvisioningError("venv interpreter link is invalid") from exc
    if target != canonical_python.resolve(strict=True):
        raise ProvisioningError("venv interpreter link is not canonical")
    try:
        venv_python.unlink()
        shutil.copyfile(canonical_python, venv_python)
        venv_python.chmod(0o755)
    except OSError as exc:
        raise ProvisioningError("venv interpreter could not be normalized") from exc
    if _sha256_file(venv_python) != PYTHON_EXECUTABLE_SHA256:
        raise ProvisioningError("venv interpreter copy does not match")


def _copy_bootstrap(venv_python: Path) -> Path:
    result = _run_checked(
        [str(venv_python), "-I", "-B", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"]
    )
    purelib = Path(result.stdout.strip())
    if not purelib.is_absolute() or not purelib.is_dir():
        raise ProvisioningError("venv site-packages is unavailable")
    destination = purelib / "sitecustomize.py"
    try:
        destination.write_bytes((_REPO_ROOT / "eval_harness" / "bigcodebench_sitecustomize.py").read_bytes())
        destination.chmod(0o644)
    except OSError as exc:
        raise ProvisioningError("NLTK bootstrap could not be installed") from exc
    return destination


def _prepare_nltk_data(resource_dir: Path, data_root: Path, download_root: Path) -> str:
    manifest = load_canonical_manifest(resource_dir / "nltk-data-manifest.json")
    packages = manifest.get("packages")
    if not isinstance(packages, list) or len(packages) != 7:
        raise ProvisioningError("NLTK package manifest is invalid")
    for raw_package in packages:
        if not isinstance(raw_package, dict):
            raise ProvisioningError("NLTK package manifest is invalid")
        package = cast(dict[str, object], raw_package)
        url = package.get("commit_url")
        filename = package.get("filename")
        package_id = package.get("id")
        size = package.get("size")
        digest = package.get("sha256")
        unzip = package.get("unzip")
        if (
            not isinstance(url, str)
            or not isinstance(filename, str)
            or not isinstance(package_id, str)
            or type(size) is not int
            or not isinstance(digest, str)
            or type(unzip) is not bool
            or not filename.endswith(".zip")
        ):
            raise ProvisioningError("NLTK package manifest is invalid")
        archive = download_verified(url, download_root / Path(filename).name, size, digest)
        destination = data_root / filename
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(archive, destination)
        if unzip:
            safe_extract_zip(archive, data_root, expected_root=package_id)
    index_source = resource_dir / "index.xml"
    index_destination = data_root / "index.xml"
    shutil.copyfile(index_source, index_destination)
    offline = manifest.get("offline_index")
    if not isinstance(offline, dict):
        raise ProvisioningError("NLTK index metadata is invalid")
    expected_index = cast(dict[str, object], offline)
    if _sha256_file(index_destination) != expected_index.get("sha256"):
        raise ProvisioningError("NLTK index hash mismatch")
    return file_inventory_sha256(data_root)


def _load_policy_manifest(resource_dir: Path, candidate: bool) -> tuple[Path, dict[str, object], str]:
    name = "grader-manifest.candidate.json" if candidate else "grader-manifest.json"
    path = resource_dir / name
    manifest = load_canonical_manifest(path)
    role = manifest.get("manifest_role")
    eligible = manifest.get("acceptance_eligible")
    if candidate:
        if role != "functional-boundary-candidate" or eligible is not False:
            raise ProvisioningError("candidate manifest role is invalid")
        if manifest.get("dependency_audit_state") != "blocked":
            raise ProvisioningError("candidate audit state is invalid")
        if manifest.get("grader_lock_sha256") != LOCK_SHA256:
            raise ProvisioningError("candidate lock identity is invalid")
    elif role == "functional-boundary-candidate" or eligible is not True:
        raise ProvisioningError("accepted manifest is unavailable")
    return path, manifest, hashlib.sha256(path.read_bytes()).hexdigest()


def provision(*, runner_temp: Path, harness_python: Path, resource_dir: Path, uv: str, candidate: bool) -> Path:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ProvisioningError("Ubuntu Linux x86-64 is required")
    if not runner_temp.is_absolute() or not harness_python.is_absolute():
        raise ProvisioningError("provisioning paths must be absolute")
    if not harness_python.is_file() or harness_python.is_symlink():
        raise ProvisioningError("harness interpreter is unavailable")
    policy_path, policy, policy_digest = _load_policy_manifest(resource_dir, candidate)
    download_root = secure_new_directory(runner_temp / "pr04-grader-downloads")
    prefix = secure_new_directory(runner_temp / "pr04-cpython-3.11.16+20260901")
    grader_venv = secure_new_directory(runner_temp / "pr04-bigcodebench-venv")
    data_root = secure_new_directory(runner_temp / "pr04-bigcodebench-nltk-data")
    runtime_root = secure_new_directory(runner_temp / "pr04-bigcodebench-runtime")
    archive = download_verified(
        PYTHON_ASSET_URL, download_root / "cpython.tar.gz", PYTHON_ASSET_SIZE, PYTHON_ASSET_SHA256
    )
    safe_extract_tar(archive, prefix, expected_root="python")
    canonical_python = _verify_python(prefix)
    _run_checked(
        [
            uv,
            "venv",
            "--python",
            str(canonical_python),
            "--no-project",
            "--no-managed-python",
            "--no-python-downloads",
            "--link-mode",
            "copy",
            str(grader_venv),
        ],
        timeout=120,
    )
    venv_python = grader_venv / "bin" / "python"
    _normalize_venv_interpreter(venv_python, canonical_python)
    lock = resource_dir / "requirements-grader.lock"
    if _sha256_file(lock) != LOCK_SHA256:
        raise ProvisioningError("grader lock is not the fixed candidate lock")
    _run_checked(
        [
            uv,
            "pip",
            "sync",
            "--python",
            str(venv_python),
            "--no-managed-python",
            "--no-python-downloads",
            "--require-hashes",
            "--strict",
            "--link-mode",
            "copy",
            str(lock),
        ],
        timeout=600,
    )
    _run_checked([uv, "pip", "check", "--python", str(venv_python)], timeout=120)
    bootstrap = _copy_bootstrap(venv_python)
    nltk_inventory = _prepare_nltk_data(resource_dir, data_root, download_root)
    runtime = {
        "acceptance_eligible": candidate is False,
        "candidate_manifest_sha256": policy_digest if candidate else None,
        "grader_lock_sha256": LOCK_SHA256,
        "grader_venv_inventory_sha256": file_inventory_sha256(grader_venv),
        "manifest_role": policy.get("manifest_role"),
        "nltk_data_inventory_sha256": nltk_inventory,
        "policy_manifest_sha256": policy_digest,
        "policy_manifest_path": str(policy_path),
        "prefix_inventory_sha256": file_inventory_sha256(prefix),
        "python_executable_sha256": _sha256_file(canonical_python),
        "runner_bootstrap_sha256": _sha256_file(bootstrap),
        "schema_version": 1,
    }
    runtime_path = runtime_root / RUNTIME_MANIFEST_NAME
    runtime_path.write_bytes(canonical_json_bytes(runtime, final_newline=True))
    runtime_path.chmod(0o444)
    return runtime_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, default=Path(os.environ.get("RUNNER_TEMP", "")))
    parser.add_argument("--harness-python", type=Path, default=Path(os.environ.get("HARNESS_PYTHON", "")))
    parser.add_argument("--resource-dir", type=Path, default=_REPO_ROOT / "resources_servers" / "bigcodebench")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--candidate", action="store_true", help="explicitly provision the non-acceptance candidate")
    args = parser.parse_args(argv)
    try:
        runtime_path = provision(
            runner_temp=args.runner_temp,
            harness_python=args.harness_python,
            resource_dir=args.resource_dir,
            uv=args.uv,
            candidate=args.candidate,
        )
    except ProvisioningError:
        print("install_bigcodebench_grader: provisioning failed", file=sys.stderr)
        return 1
    print(f"runtime_manifest={runtime_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
