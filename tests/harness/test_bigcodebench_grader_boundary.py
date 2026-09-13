# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic preparation checks for the BigCodeBench boundary inputs."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import cast

from scripts.ci import install_bigcodebench_grader as installer

from eval_harness.grader_sandbox import (
    GraderInfrastructureError,
    canonical_file_inventory,
    canonical_json_bytes,
    file_inventory_sha256,
    load_canonical_manifest,
)


class BigCodeBenchBoundaryPreparationTests(unittest.TestCase):
    def test_candidate_manifest_and_lock_are_explicitly_nonacceptance(self) -> None:
        resource_dir = Path(__file__).parents[2] / "resources_servers" / "bigcodebench"
        manifest_path = resource_dir / "grader-manifest.candidate.json"
        manifest = load_canonical_manifest(manifest_path)
        self.assertEqual(manifest["manifest_role"], "functional-boundary-candidate")
        self.assertIs(manifest["acceptance_eligible"], False)
        self.assertEqual(manifest["dependency_audit_state"], "blocked")
        self.assertEqual(
            hashlib.sha256((resource_dir / "requirements-grader.lock").read_bytes()).hexdigest(),
            installer.LOCK_SHA256,
        )
        self.assertFalse((resource_dir / "grader-manifest.json").exists())

    def test_inventory_is_canonical_and_records_safe_relative_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"
            root.mkdir(mode=0o700)
            payload = root / "payload"
            payload.write_bytes(b"payload")
            payload.chmod(0o640)
            (root / "alias").symlink_to("payload")

            expected: list[dict[str, object]] = [
                {
                    "mode": 0o640,
                    "path": "payload",
                    "sha256": hashlib.sha256(b"payload").hexdigest(),
                    "size": 7,
                    "type": "file",
                },
                {"path": "alias", "target": "payload", "type": "symlink"},
            ]
            # Entries are sorted by path; this assertion intentionally checks
            # the serialized contract, not only the digest.
            expected.sort(key=lambda entry: cast(str, entry["path"]))
            self.assertEqual(json.loads(canonical_file_inventory(root)), expected)
            self.assertEqual(file_inventory_sha256(root), hashlib.sha256(canonical_file_inventory(root)).hexdigest())

    def test_inventory_rejects_escape_and_hardlink_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"
            root.mkdir(mode=0o700)
            payload = root / "payload"
            payload.write_bytes(b"payload")
            (root / "escape").symlink_to("/tmp")
            with self.assertRaises(GraderInfrastructureError):
                canonical_file_inventory(root)

            (root / "escape").unlink()
            os.link(payload, root / "hardlink")
            with self.assertRaises(GraderInfrastructureError):
                canonical_file_inventory(root)

    def test_archive_extractors_reject_traversal_duplicates_links_and_specials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad_zip = root / "traversal.zip"
            bad_zip_out = root / "traversal-out"
            bad_zip_out.mkdir(mode=0o700)
            with zipfile.ZipFile(bad_zip, "w") as archive:
                archive.writestr("python/../escape", b"bad")
            with self.assertRaises(installer.ProvisioningError):
                installer.safe_extract_zip(bad_zip, bad_zip_out, expected_root="python")

            duplicate_zip = root / "duplicate.zip"
            duplicate_zip_out = root / "duplicate-out"
            duplicate_zip_out.mkdir(mode=0o700)
            with zipfile.ZipFile(duplicate_zip, "w") as archive:
                archive.writestr("python/item", b"one")
                archive.writestr("python/item", b"two")
            with self.assertRaises(installer.ProvisioningError):
                installer.safe_extract_zip(duplicate_zip, duplicate_zip_out, expected_root="python")

            for name, kind in (("link", "link"), ("special", "special"), ("traversal", "traversal")):
                archive_path = root / f"{name}.tar.gz"
                destination = root / f"{name}-tar-out"
                destination.mkdir(mode=0o700)
                with tarfile.open(archive_path, "w:gz") as archive:
                    if kind == "link":
                        member = tarfile.TarInfo("python/link")
                        member.type = tarfile.SYMTYPE
                        member.linkname = "/outside"
                        archive.addfile(member)
                    elif kind == "special":
                        member = tarfile.TarInfo("python/device")
                        member.type = tarfile.CHRTYPE
                        archive.addfile(member)
                    else:
                        member = tarfile.TarInfo("python/../escape")
                        member.size = 3
                        archive.addfile(member, io.BytesIO(b"bad"))
                with self.subTest(kind=kind), self.assertRaises(installer.ProvisioningError):
                    installer.safe_extract_tar(archive_path, destination, expected_root="python")

            valid_archive = root / "valid.tar.gz"
            valid_destination = root / "valid-out"
            valid_destination.mkdir(mode=0o700)
            with tarfile.open(valid_archive, "w:gz") as archive:
                directory = tarfile.TarInfo("python/share")
                directory.type = tarfile.DIRTYPE
                archive.addfile(directory)
                target = tarfile.TarInfo("python/target")
                target.size = 5
                archive.addfile(target, io.BytesIO(b"hello"))
                link = tarfile.TarInfo("python/share/link")
                link.type = tarfile.SYMTYPE
                link.linkname = "../target"
                archive.addfile(link)
            installer.safe_extract_tar(valid_archive, valid_destination, expected_root="python")
            self.assertEqual((valid_destination / "target").read_bytes(), b"hello")
            self.assertEqual(os.readlink(valid_destination / "share" / "link"), "../target")

    def test_secure_directory_refuses_existing_paths_and_canonical_json_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "private"
            installer.secure_new_directory(path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            with self.assertRaises(installer.ProvisioningError):
                installer.secure_new_directory(path)
        self.assertEqual(canonical_json_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')
        self.assertEqual(canonical_json_bytes({"a": 1}, final_newline=True), b'{"a":1}\n')
