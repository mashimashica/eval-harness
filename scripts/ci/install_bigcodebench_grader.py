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
import posixpath
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
    canonical_file_inventory,
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
HARNESS_PYTHON_VERSION: Final[str] = "3.13.14"
LOCK_SHA256: Final[str] = "8d62cac6880124652638ff8716532d46d459aaf5cbe6e8c36b506a4d1e4de9bd"
BUILD_LOCK_SHA256: Final[str] = "32df6b18b4c96eb4146d18cd16adad24efecba5c4a5212115f5c6acea4749605"
POLICY_REVISION: Final[str] = "bigcodebench-bwrap-v1"
NLTK_MANIFEST_SHA256: Final[str] = "8cda33ca56e34b58702a16dd6b3b9160fd2e8f38d03b1062f83550c95a435938"
NLTK_INDEX_SHA256: Final[str] = "27b1257a84cfec723c024c6762ed801ceb6984437d5438d4c7bed8bc6b52aafc"
NLTK_TREE_SHA256: Final[str] = "5a30cfb5c9d2a0353a987535b261386244abe66ac898185c514c913ac518514a"
NLTK_TREE_FILE_COUNT: Final[int] = 167
NLTK_TREE_BYTES: Final[int] = 85_741_209
RUNTIME_MANIFEST_NAME: Final[str] = "runtime-manifest.json"
BWRAP_VERSION: Final[str] = "0.12.0"
BWRAP_SOURCE_SHA256: Final[str] = "9760d007363e3abba7c747489910f9f82d9fca53ba3bd3282e396fa3c97a3314"


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
    resolved_text = posixpath.normpath(str(PurePosixPath(*member_path.parts[:-1]) / target_path))
    resolved = PurePosixPath(resolved_text)
    if resolved.is_absolute() or not resolved.parts or resolved.parts[0] != member_path.parts[0]:
        raise ProvisioningError("archive link escapes its root")


def safe_extract_tar(archive_path: Path, destination: Path, *, expected_root: str = "python") -> None:
    """Extract a single-root tar without links, devices, or path traversal."""

    seen: set[str] = set()
    symlink_members: list[tuple[PurePosixPath, str]] = []
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
                    symlink_members.append((output, member.linkname))
                else:
                    raise ProvisioningError("archive contains a special or hard-linked member")
            for output, target in symlink_members:
                output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                output.symlink_to(target)
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


def _verify_harness_python(path: Path) -> None:
    result = _run_checked(
        [
            str(path),
            "-I",
            "-B",
            "-c",
            "import platform; print(platform.python_version(), platform.machine())",
        ]
    )
    if result.stdout.strip() != f"{HARNESS_PYTHON_VERSION} x86_64":
        raise ProvisioningError("harness interpreter identity mismatch")


def _verify_bwrap(path: Path) -> tuple[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ProvisioningError("bubblewrap binary is unavailable")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ProvisioningError("bubblewrap binary metadata is unavailable") from exc
    if (
        metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o755
        or metadata.st_uid not in {0, os.getuid()}
        or metadata.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise ProvisioningError("bubblewrap binary metadata is unsafe")
    version = _run_checked([str(path), "--version"]).stdout.strip()
    if version != f"bubblewrap {BWRAP_VERSION}":
        raise ProvisioningError("bubblewrap version mismatch")
    headers = _run_checked(["readelf", "-h", str(path)]).stdout
    if "Class:" not in headers or "ELF64" not in headers or "Machine:" not in headers or "X86-64" not in headers:
        raise ProvisioningError("bubblewrap architecture mismatch")
    capabilities = _run_checked(["getcap", str(path)]).stdout.strip()
    if capabilities:
        raise ProvisioningError("bubblewrap binary has file capabilities")
    package_record = path.parent.parent / "build-packages.txt"
    if not package_record.is_file() or package_record.is_symlink():
        raise ProvisioningError("bubblewrap build provenance is unavailable")
    return _sha256_file(path), _sha256_file(package_record)


def _verify_policy_inputs(resource_dir: Path, policy: dict[str, object], *, candidate: bool) -> None:
    if not candidate:
        raise ProvisioningError("only explicit candidate provisioning is supported")
    if policy.get("manifest_role") != "functional-boundary-candidate":
        raise ProvisioningError("candidate policy role is invalid")
    if policy.get("schema_version") != 1 or policy.get("policy_revision") != POLICY_REVISION:
        raise ProvisioningError("candidate policy schema is invalid")
    if policy.get("acceptance_eligible") is not False or policy.get("dependency_audit_state") != "blocked":
        raise ProvisioningError("candidate policy eligibility is invalid")
    if policy.get("grader_lock_sha256") != LOCK_SHA256 or policy.get("build_lock_sha256") != BUILD_LOCK_SHA256:
        raise ProvisioningError("policy lock provenance is invalid")
    if policy.get("runner_sha256") != _sha256_file(_REPO_ROOT / "eval_harness" / "bigcodebench_runner.py"):
        raise ProvisioningError("runner provenance does not match policy")
    if policy.get("bootstrap_sha256") != _sha256_file(_REPO_ROOT / "eval_harness" / "bigcodebench_sitecustomize.py"):
        raise ProvisioningError("bootstrap provenance does not match policy")
    if _sha256_file(resource_dir / "nltk-data-manifest.json") != NLTK_MANIFEST_SHA256:
        raise ProvisioningError("NLTK manifest provenance does not match policy")
    if policy.get("nltk_data_manifest_sha256") != NLTK_MANIFEST_SHA256:
        raise ProvisioningError("NLTK policy provenance is invalid")
    platform_values = policy.get("platform")
    if platform_values != {"architecture": "x86_64", "distribution": "ubuntu-24.04", "system": "Linux"}:
        raise ProvisioningError("candidate platform provenance is invalid")
    bubblewrap_values = policy.get("bubblewrap")
    if bubblewrap_values != {
        "source_sha256": BWRAP_SOURCE_SHA256,
        "tag_commit": "2a76602a8c71f36c1527cf9fc3417d9149822e0c",
        "version": BWRAP_VERSION,
    }:
        raise ProvisioningError("bubblewrap policy provenance is invalid")
    python_values = policy.get("python_artifact")
    if not isinstance(python_values, dict):
        raise ProvisioningError("CPython policy provenance is invalid")
    expected_python = {
        "asset_id": 539915682,
        "asset_sha256": PYTHON_ASSET_SHA256,
        "asset_size": PYTHON_ASSET_SIZE,
        "executable_sha256": PYTHON_EXECUTABLE_SHA256,
        "license_sha256": PYTHON_LICENSE_SHA256,
        "soabi": PYTHON_SOABI,
        "version": PYTHON_VERSION,
    }
    if python_values != expected_python:
        raise ProvisioningError("CPython policy provenance is invalid")
    nltk_values = policy.get("nltk_data")
    if not isinstance(nltk_values, dict) or nltk_values != {
        "index_sha256": NLTK_INDEX_SHA256,
        "manifest_sha256": NLTK_MANIFEST_SHA256,
        "package_ids": [
            "averaged_perceptron_tagger",
            "averaged_perceptron_tagger_eng",
            "punkt",
            "punkt_tab",
            "stopwords",
            "vader_lexicon",
            "words",
        ],
        "prepared_tree_sha256": NLTK_TREE_SHA256,
        "source_commit": "550b6625bcef1f2abff2ff770a5a0d272c9c6b2a",
        "source_index_sha256": "97dce5e72320cd9850b7c20130196006710c18f9c03134c822a37da330198bf6",
    }:
        raise ProvisioningError("NLTK policy provenance is invalid")
    vendor_values = policy.get("vendor_sha256")
    if not isinstance(vendor_values, dict):
        raise ProvisioningError("vendor policy provenance is invalid")
    vendor_root = resource_dir / "vendor" / "bigcodebench"
    for relative, expected in vendor_values.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ProvisioningError("vendor policy provenance is invalid")
        if _sha256_file(vendor_root / relative) != expected:
            raise ProvisioningError("vendor provenance does not match policy")
    lock = resource_dir / "requirements-grader.lock"
    build_lock = _REPO_ROOT / "scripts" / "ci" / "requirements-bwrap-build.lock"
    if _sha256_file(lock) != LOCK_SHA256 or _sha256_file(build_lock) != BUILD_LOCK_SHA256:
        raise ProvisioningError("lock provenance does not match policy")


def _verify_venv_identity(venv_python: Path, venv_root: Path, canonical_prefix: Path) -> None:
    config = venv_root / "pyvenv.cfg"
    try:
        values = config.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProvisioningError("venv metadata is unavailable") from exc
    home = next((line.partition("=")[2].strip() for line in values if line.partition("=")[0].strip() == "home"), "")
    if not home:
        raise ProvisioningError("venv home metadata is unavailable")
    home_path = Path(home)
    if home_path.name == "bin":
        home_path = home_path.parent
    if not home_path.is_absolute():
        raise ProvisioningError("venv home metadata is not absolute")
    try:
        if home_path.resolve(strict=True) != canonical_prefix.resolve(strict=True):
            raise ProvisioningError("venv home metadata does not match CPython prefix")
    except (OSError, RuntimeError) as exc:
        raise ProvisioningError("venv home metadata is invalid") from exc
    result = _run_checked(
        [
            str(venv_python),
            "-I",
            "-B",
            "-c",
            "import platform,sys,sysconfig; print(platform.python_version(),platform.machine(),sysconfig.get_config_var('SOABI'),sys.prefix)",
        ]
    )
    if result.stdout.strip() != f"{PYTHON_VERSION} x86_64 {PYTHON_SOABI} {venv_root}":
        raise ProvisioningError("venv interpreter identity mismatch")


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
    if not purelib.is_absolute() or purelib.is_symlink() or not purelib.is_dir():
        raise ProvisioningError("venv site-packages is unavailable")
    venv_root = venv_python.parent.parent.resolve(strict=True)
    if not purelib.resolve(strict=True).is_relative_to(venv_root):
        raise ProvisioningError("venv site-packages escapes the venv")
    destination = purelib / "sitecustomize.py"
    try:
        destination.write_bytes((_REPO_ROOT / "eval_harness" / "bigcodebench_sitecustomize.py").read_bytes())
        destination.chmod(0o644)
    except OSError as exc:
        raise ProvisioningError("NLTK bootstrap could not be installed") from exc
    return destination


def _read_nltk_manifest(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != NLTK_MANIFEST_SHA256:
            raise ProvisioningError("NLTK package manifest hash mismatch")
        value = json.loads(raw.decode("utf-8"))
    except ProvisioningError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProvisioningError("NLTK package manifest is unreadable") from exc
    if not isinstance(value, dict):
        raise ProvisioningError("NLTK package manifest is invalid")
    return cast(dict[str, object], value)


def _content_inventory(root: Path) -> tuple[bytes, int, int]:
    entries: list[dict[str, object]] = []
    regular_bytes = 0
    try:
        paths = sorted(
            (path for path in root.rglob("*") if path.is_file() and not path.is_symlink()),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    except OSError as exc:
        raise ProvisioningError("NLTK data inventory is unavailable") from exc
    for path in paths:
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        entries.append({"path": relative, "sha256": _sha256_file(path), "size": size})
        regular_bytes += size
    return canonical_json_bytes(entries), len(entries), regular_bytes


def _prepare_nltk_data(resource_dir: Path, data_root: Path, download_root: Path) -> str:
    manifest = _read_nltk_manifest(resource_dir / "nltk-data-manifest.json")
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
        subdir = package.get("subdir")
        size = package.get("size")
        digest = package.get("sha256")
        unzip = package.get("unzip")
        if (
            not isinstance(url, str)
            or not isinstance(filename, str)
            or not isinstance(package_id, str)
            or not isinstance(subdir, str)
            or type(size) is not int
            or not isinstance(digest, str)
            or type(unzip) is not bool
            or not filename.endswith(".zip")
        ):
            raise ProvisioningError("NLTK package manifest is invalid")
        archive = download_verified(url, download_root / Path(filename).name, size, digest)
        relative_archive = PurePosixPath(filename)
        if relative_archive.is_absolute() or not relative_archive.parts or relative_archive.parts[0] != subdir:
            raise ProvisioningError("NLTK package path is invalid")
        destination = data_root / filename
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(archive, destination)
        if unzip:
            safe_extract_zip(archive, data_root / subdir, expected_root=package_id)
    index_source = resource_dir / "index.xml"
    index_destination = data_root / "index.xml"
    shutil.copyfile(index_source, index_destination)
    offline = manifest.get("offline_index")
    if not isinstance(offline, dict):
        raise ProvisioningError("NLTK index metadata is invalid")
    expected_index = cast(dict[str, object], offline)
    if (
        expected_index.get("sha256") != NLTK_INDEX_SHA256
        or expected_index.get("size") != 3447
        or _sha256_file(index_destination) != NLTK_INDEX_SHA256
        or index_destination.stat().st_size != 3447
    ):
        raise ProvisioningError("NLTK index hash mismatch")
    inventory, file_count, regular_bytes = _content_inventory(data_root)
    prepared_tree = manifest.get("prepared_tree")
    if not isinstance(prepared_tree, dict):
        raise ProvisioningError("NLTK prepared-tree metadata is invalid")
    expected_tree = cast(dict[str, object], prepared_tree)
    if (
        file_count != NLTK_TREE_FILE_COUNT
        or regular_bytes != NLTK_TREE_BYTES
        or hashlib.sha256(inventory).hexdigest() != NLTK_TREE_SHA256
        or expected_tree.get("file_count") != NLTK_TREE_FILE_COUNT
        or expected_tree.get("regular_bytes") != NLTK_TREE_BYTES
        or expected_tree.get("canonical_inventory_sha256") != NLTK_TREE_SHA256
    ):
        raise ProvisioningError("NLTK prepared-tree identity mismatch")
    return hashlib.sha256(inventory).hexdigest()


def _load_policy_manifest(resource_dir: Path, candidate: bool) -> tuple[Path, dict[str, object], str]:
    if not candidate:
        raise ProvisioningError("only explicit candidate provisioning is supported")
    name = "grader-manifest.candidate.json"
    path = resource_dir / name
    manifest = load_canonical_manifest(path)
    role = manifest.get("manifest_role")
    eligible = manifest.get("acceptance_eligible")
    if role != "functional-boundary-candidate" or eligible is not False:
        raise ProvisioningError("candidate manifest role is invalid")
    if manifest.get("dependency_audit_state") != "blocked":
        raise ProvisioningError("candidate audit state is invalid")
    if manifest.get("grader_lock_sha256") != LOCK_SHA256:
        raise ProvisioningError("candidate lock identity is invalid")
    return path, manifest, hashlib.sha256(path.read_bytes()).hexdigest()


def provision(
    *,
    runner_temp: Path,
    harness_python: Path,
    resource_dir: Path,
    uv: str,
    bwrap_path: Path,
    candidate: bool,
) -> Path:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ProvisioningError("Ubuntu Linux x86-64 is required")
    if not runner_temp.is_absolute() or not harness_python.is_absolute():
        raise ProvisioningError("provisioning paths must be absolute")
    if not harness_python.is_file() or harness_python.is_symlink():
        raise ProvisioningError("harness interpreter is unavailable")
    _verify_harness_python(harness_python)
    uv_version = _run_checked([uv, "--version"]).stdout.strip()
    if uv_version != "uv 0.11.29":
        raise ProvisioningError("uv version mismatch")
    policy_path, policy, policy_digest = _load_policy_manifest(resource_dir, candidate)
    _verify_policy_inputs(resource_dir, policy, candidate=candidate)
    bwrap_digest, build_package_digest = _verify_bwrap(bwrap_path)
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
    _verify_venv_identity(venv_python, grader_venv, prefix)
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
    resource_data = resource_dir / "nltk_data"
    if resource_data.exists() or resource_data.is_symlink():
        raise ProvisioningError("refusing to replace existing NLTK data path")
    try:
        resource_data.symlink_to(data_root, target_is_directory=True)
    except OSError as exc:
        raise ProvisioningError("NLTK data path could not be bound") from exc
    prefix_inventory = cast(list[dict[str, object]], json.loads(canonical_file_inventory(prefix)))
    venv_inventory = cast(list[dict[str, object]], json.loads(canonical_file_inventory(grader_venv)))
    data_inventory = cast(list[dict[str, object]], json.loads(canonical_file_inventory(data_root)))
    runtime = {
        "acceptance_eligible": False,
        "build_package_record_sha256": build_package_digest,
        "bubblewrap_path": str(bwrap_path),
        "bubblewrap_sha256": bwrap_digest,
        "candidate_manifest_sha256": policy_digest,
        "grader_lock_sha256": LOCK_SHA256,
        "grader_venv_inventory": venv_inventory,
        "grader_venv_inventory_sha256": file_inventory_sha256(grader_venv),
        "manifest_role": policy.get("manifest_role"),
        "nltk_data_path": str(resource_data),
        "nltk_data_inventory": data_inventory,
        "nltk_data_inventory_sha256": nltk_inventory,
        "policy_manifest_sha256": policy_digest,
        "policy_manifest_path": str(policy_path),
        "prefix_inventory": prefix_inventory,
        "prefix_inventory_sha256": file_inventory_sha256(prefix),
        "python_executable_sha256": _sha256_file(canonical_python),
        "runner_bootstrap_sha256": _sha256_file(bootstrap),
        "schema_version": 1,
        "source_provenance": {
            "build_lock_sha256": BUILD_LOCK_SHA256,
            "bubblewrap_source_sha256": BWRAP_SOURCE_SHA256,
            "python_asset_sha256": PYTHON_ASSET_SHA256,
            "policy_revision": POLICY_REVISION,
        },
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
    parser.add_argument("--bwrap-path", type=Path, default=Path(os.environ.get("BWRAP_PATH", "")))
    parser.add_argument("--candidate", action="store_true", help="explicitly provision the non-acceptance candidate")
    args = parser.parse_args(argv)
    try:
        runtime_path = provision(
            runner_temp=args.runner_temp,
            harness_python=args.harness_python,
            resource_dir=args.resource_dir,
            uv=args.uv,
            bwrap_path=args.bwrap_path,
            candidate=args.candidate,
        )
    except ProvisioningError:
        print("install_bigcodebench_grader: provisioning failed", file=sys.stderr)
        return 1
    print(f"runtime_manifest={runtime_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
