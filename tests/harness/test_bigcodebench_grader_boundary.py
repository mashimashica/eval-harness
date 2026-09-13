# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic preparation checks for the BigCodeBench boundary inputs."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import IO, cast
from unittest import mock

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
                with self.assertWarns(UserWarning):
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

    def test_nltk_package_layout_preserves_category_and_id_and_zip_only_vader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = root / "nltk_data"
            data_root.mkdir(mode=0o700)
            expanded = root / "stopwords.zip"
            with zipfile.ZipFile(expanded, "w") as archive:
                archive.writestr("stopwords/README", b"stopwords")
            installed = installer._install_nltk_package(
                expanded, data_root, subdir="corpora", package_id="stopwords", unzip=True
            )
            self.assertEqual(installed, data_root / "corpora" / "stopwords")
            self.assertEqual((installed / "README").read_bytes(), b"stopwords")

            vader = root / "vader_lexicon.zip"
            with zipfile.ZipFile(vader, "w") as archive:
                archive.writestr("vader_lexicon/vader_lexicon.txt", b"vader")
            archive_path = installer._install_nltk_package(
                vader, data_root, subdir="sentiment", package_id="vader_lexicon", unzip=False
            )
            self.assertEqual(archive_path, data_root / "sentiment" / "vader_lexicon.zip")
            self.assertTrue(archive_path.is_file())
            self.assertFalse((data_root / "sentiment" / "vader_lexicon").exists())
            with self.assertRaises(installer.ProvisioningError):
                installer._install_nltk_package(
                    expanded, data_root, subdir="taggers", package_id="stopwords", unzip=True
                )

    def test_ubuntu_release_guard_rejects_other_and_malformed_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "os-release"
            path.write_text('NAME="Ubuntu 24.04 LTS"\nID=ubuntu\nVERSION_ID="24.04"\n', encoding="utf-8")
            installer._verify_ubuntu_release(path)
            for contents in (
                'ID=debian\nVERSION_ID="24.04"\n',
                'ID=ubuntu\nVERSION_ID="22.04"\n',
                "ID=ubuntu\nVERSION_ID=24.04\nBROKEN\n",
                'ID=ubuntu\nID=ubuntu\nVERSION_ID="24.04"\n',
            ):
                path.write_text(contents, encoding="utf-8")
                with self.assertRaises(installer.ProvisioningError):
                    installer._verify_ubuntu_release(path)

    def test_uv_suffix_and_exact_version_parser(self) -> None:
        with mock.patch.object(installer, "_run_checked") as run_checked:
            run_checked.return_value = subprocess.CompletedProcess(
                [], 0, stdout="uv 0.11.29 (901092ee1 2026-07-15 aarch64-apple-darwin)\n", stderr=""
            )
            installer._verify_uv_version(Path("/usr/bin/uv"))
            for output in (
                "uv 0.11.29\n",
                "uv 0.11.290\n",
                "uv 0.11.29 extra\n",
                "uv 0.11.29 ()\n",
                "uv 0.11.29 (unclosed\n",
                "uv 0.11.29 unopen)\n",
                "uv 0.11.29 (internal\nnewline)\n",
                "uv 0.11.29 (suffix) extra\n",
            ):
                run_checked.return_value = subprocess.CompletedProcess([], 0, stdout=output, stderr="")
                if output == "uv 0.11.29\n":
                    installer._verify_uv_version(Path("/usr/bin/uv"))
                else:
                    with self.assertRaises(installer.ProvisioningError):
                        installer._verify_uv_version(Path("/usr/bin/uv"))

    def test_shell_uv_parser_uses_the_same_exact_grammar(self) -> None:
        script_path = Path(__file__).parents[2] / "scripts" / "ci" / "install_bubblewrap.sh"
        script = script_path.read_text(encoding="utf-8")
        start = script.index("check_uv_version()")
        end = script.index("\n}\n", start) + 3
        function_source = script[start:end]
        cases: tuple[tuple[str, bool], ...] = (
            ("uv 0.11.29", True),
            ("uv 0.11.29 (901092ee1 2026-07-15 aarch64-apple-darwin)", True),
            ("uv 0.11.290", False),
            ("uv 0.11.29 ()", False),
            ("uv 0.11.29 (unclosed", False),
            ("uv 0.11.29 (internal\nnewline)", False),
            ("uv 0.11.29 (suffix) extra", False),
            ("uv 0.11.29 (suffix)\r", False),
            ("uv 0.11.29 (suf\rfix)", False),
            ("uv 0.11.29\nuv 0.11.29", False),
        )
        for output, expected in cases:
            result = subprocess.run(
                ["bash", "-c", f'{function_source}\ncheck_uv_version "$1"', "check-uv-version", output],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode == 0, expected, output)

    def test_shell_version_commands_support_whitespace_paths(self) -> None:
        script_path = Path(__file__).parents[2] / "scripts" / "ci" / "install_bubblewrap.sh"
        script = script_path.read_text(encoding="utf-8")
        for command in (
            'uv_version="$("$uv_bin" --version)"',
            'harness_identity="$("$harness_python" -I -B -c',
            '[ "$("$meson_bin" --version)" = "1.9.1" ]',
            'ninja_distribution_version="$("$build_venv/bin/python"',
            'ninja_binary_version="$("$ninja_bin" --version)"',
        ):
            self.assertIn(command, script)

        with tempfile.TemporaryDirectory(prefix="pr04 executable ") as temporary:
            executable_dir = Path(temporary) / "private tools"
            executable_dir.mkdir(mode=0o700)
            uv = executable_dir / "uv tool"
            harness = executable_dir / "harness python"
            meson = executable_dir / "meson tool"
            ninja = executable_dir / "ninja tool"
            for executable, output in (
                (uv, "uv 0.11.29 (fixture)"),
                (harness, "3.13.14 x86_64"),
                (meson, "1.9.1"),
                (ninja, "1.13.0.git.kitware.jobserver-pipe-1"),
            ):
                executable.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\n", encoding="utf-8")
                executable.chmod(0o700)

            command = """\
uv_bin="$1"
harness_python="$2"
meson_bin="$3"
ninja_bin="$4"
uv_version="$("$uv_bin" --version)"
harness_identity="$("$harness_python" -I -B -c 'ignored')"
meson_version="$("$meson_bin" --version)"
ninja_version="$("$ninja_bin" --version)"
printf '%s|%s|%s|%s\\n' "$uv_version" "$harness_identity" "$meson_version" "$ninja_version"
"""
            result = subprocess.run(
                ["bash", "-c", command, "capture", str(uv), str(harness), str(meson), str(ninja)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout,
                "uv 0.11.29 (fixture)|3.13.14 x86_64|1.9.1|1.13.0.git.kitware.jobserver-pipe-1\n",
            )

    def test_shell_ninja_guard_requires_distribution_and_binary_identity(self) -> None:
        script_path = Path(__file__).parents[2] / "scripts" / "ci" / "install_bubblewrap.sh"
        script = script_path.read_text(encoding="utf-8")
        start = script.index("check_ninja_version()")
        end = script.index("\n}\n", start) + 3
        function_source = script[start:end]
        cases: tuple[tuple[str, str, bool], ...] = (
            ("1.13.0", "1.13.0.git.kitware.jobserver-pipe-1", True),
            ("1.13.0", "1.13.0", False),
            ("1.13.00", "1.13.0.git.kitware.jobserver-pipe-1", False),
            ("1.13.0\n1.13.0", "1.13.0.git.kitware.jobserver-pipe-1", False),
            ("1.13.0", "1.13.0.git.kitware.jobserver-pipe-1\n", False),
            ("1.13.0", "1.13.0.git.kitware.jobserver-pipe-1\r", False),
            ("1.13.0", "1.13.0.git.kitware.jobserver-pipe-2", False),
        )
        for distribution, binary, expected in cases:
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f'{function_source}\ncheck_ninja_version "$1" "$2"',
                    "check-ninja",
                    distribution,
                    binary,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode == 0, expected, (distribution, binary))

    def test_nltk_archive_install_preserves_existing_and_cleans_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = root / "nltk_data"
            data_root.mkdir(mode=0o700)
            archive = root / "stopwords.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("stopwords/README", b"new")
            category = data_root / "corpora"
            category.mkdir(mode=0o700)
            destination = category / "stopwords.zip"
            destination.write_bytes(b"existing")
            with self.assertRaises(installer.ProvisioningError):
                installer._install_nltk_package(
                    archive, data_root, subdir="corpora", package_id="stopwords", unzip=True
                )
            self.assertEqual(destination.read_bytes(), b"existing")

            destination.unlink()
            sentinel = root / "sentinel"
            sentinel.write_bytes(b"sentinel")
            destination.symlink_to(sentinel)
            with self.assertRaises(installer.ProvisioningError):
                installer._install_nltk_package(
                    archive, data_root, subdir="corpora", package_id="stopwords", unzip=True
                )
            self.assertTrue(destination.is_symlink())
            self.assertEqual(destination.resolve(), sentinel.resolve())
            self.assertEqual(sentinel.read_bytes(), b"sentinel")

            destination.unlink()

            def partial_copy(_source: IO[bytes], target: IO[bytes], *, length: int) -> None:
                del length
                target.write(b"partial")
                raise OSError("simulated partial copy")

            with mock.patch.object(shutil, "copyfileobj", side_effect=partial_copy):
                with self.assertRaises(installer.ProvisioningError):
                    installer._install_nltk_package(
                        archive, data_root, subdir="corpora", package_id="stopwords", unzip=True
                    )
            self.assertFalse(destination.exists())

            source_failure = mock.Mock(spec=Path, wraps=archive)
            source_failure.open.side_effect = OSError("simulated source open failure")
            with self.assertRaises(installer.ProvisioningError):
                installer._install_nltk_package(
                    cast(Path, source_failure), data_root, subdir="corpora", package_id="stopwords", unzip=True
                )
            self.assertFalse(destination.exists())

    def test_build_package_record_requires_exact_names_versions_and_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "build-packages.txt"
            valid = "".join(f"{name}\t1.0\n" for name in installer.BUILD_PACKAGE_NAMES)
            path.write_text(valid, encoding="utf-8")
            self.assertEqual(set(installer._parse_build_package_record(path)), set(installer.BUILD_PACKAGE_NAMES))
            for contents in (
                valid.replace("gcc\t1.0\n", ""),
                valid + "extra\t1.0\n",
                valid.replace("gcc\t1.0\n", "gcc\t1.0\ngcc\t1.1\n"),
                valid.replace("gcc\t1.0", "gcc 1.0"),
                "",
            ):
                path.write_text(contents, encoding="utf-8")
                with self.assertRaises(installer.ProvisioningError):
                    installer._parse_build_package_record(path)

    def test_vendor_policy_requires_frozen_complete_keyset(self) -> None:
        resource_dir = Path(__file__).parents[2] / "resources_servers" / "bigcodebench"
        policy = cast(dict[str, object], json.loads((resource_dir / "grader-manifest.candidate.json").read_text()))
        installer._verify_policy_inputs(resource_dir, policy, candidate=True)
        for vendor in (
            {},
            {**installer.VENDOR_SHA256, "extra": "0"},
            {key: value for key, value in installer.VENDOR_SHA256.items() if key != "LICENSE"},
        ):
            mutated = dict(policy)
            mutated["vendor_sha256"] = vendor
            with self.assertRaises(installer.ProvisioningError):
                installer._verify_policy_inputs(resource_dir, mutated, candidate=True)

    def test_content_and_full_inventory_have_distinct_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "data"
            root.mkdir(mode=0o700)
            (root / "payload").write_bytes(b"payload")
            content, count, size = installer._content_inventory(root)
            full = canonical_file_inventory(root)
            self.assertEqual((count, size), (1, 7))
            self.assertNotEqual(content, full)
            self.assertEqual(
                json.loads(content)[0],
                {"path": "payload", "sha256": hashlib.sha256(b"payload").hexdigest(), "size": 7},
            )
            self.assertEqual(json.loads(full)[0]["type"], "file")
            self.assertIn("mode", json.loads(full)[0])
