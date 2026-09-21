# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Build explicit, project-local FFmpeg tools from an operator-provided pinned source archive."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from eval_harness.artifacts import sha256_file, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--x264-archive", type=Path)
    parser.add_argument("--x264-sha256")
    args = parser.parse_args()
    if sha256_file(args.archive) != args.sha256:
        raise ValueError("FFmpeg source digest mismatch")
    if bool(args.x264_archive) != bool(args.x264_sha256) or (
        args.x264_archive and sha256_file(args.x264_archive) != args.x264_sha256
    ):
        raise ValueError("x264 requires its pinned source digest")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "ffmpeg").exists():
        raise ValueError("refusing to overwrite a native runtime")
    steps = []
    with tempfile.TemporaryDirectory(prefix="eval-harness-ffmpeg-") as temporary:
        root = Path(temporary)
        with tarfile.open(args.archive) as archive:
            archive.extractall(root, filter="data")
        source = next(root.glob("ffmpeg-*"))
        extra = []
        pkg_config_command = "false"
        build_environment = dict(os.environ)
        if args.x264_archive:
            with tarfile.open(args.x264_archive) as archive:
                archive.extractall(root, filter="data")
            x264 = next(root.glob("x264-*"))
            prefix = root / "x264-install"
            pkg_config = shutil.which("pkg-config")
            if not pkg_config:
                raise ValueError("x264-enabled build requires an explicitly available pkg-config")
            pkg_config_command = pkg_config
            build_environment["PKG_CONFIG_PATH"] = ""
            build_environment["PKG_CONFIG_LIBDIR"] = str(prefix / "lib" / "pkgconfig")
            for index, command in enumerate(
                [
                    [
                        "./configure",
                        f"--prefix={prefix}",
                        "--enable-static",
                        "--enable-pic",
                        "--disable-cli",
                        "--disable-opencl",
                    ],
                    ["make", "-j4"],
                    ["make", "install-lib-static", "install-lib-dev"],
                ]
            ):
                started = time.monotonic()
                result = subprocess.run(
                    command, cwd=x264, text=True, errors="replace", capture_output=True, timeout=900
                )
                (output / f"x264-{index}.stdout.log").write_text(result.stdout)
                (output / f"x264-{index}.stderr.log").write_text(result.stderr)
                steps.append(
                    {
                        "command": command,
                        "returncode": result.returncode,
                        "elapsed_seconds": time.monotonic() - started,
                    }
                )
                write_json(
                    output / "build.json",
                    {"source_sha256": args.sha256, "x264_sha256": args.x264_sha256, "steps": steps},
                )
                result.check_returncode()
            shutil.copy2(x264 / "COPYING", output / "x264-COPYING")
            extra = [
                "--enable-libx264",
                "--enable-gpl",
                "--enable-version3",
                f"--extra-cflags=-I{prefix}/include",
                f"--extra-ldflags=-L{prefix}/lib",
            ]
        commands = [
            [
                "./configure",
                "--disable-autodetect",
                "--enable-zlib",
                "--pkg-config=" + pkg_config_command,
                "--disable-network",
                "--disable-doc",
                "--disable-debug",
                "--disable-ffplay",
                "--disable-x86asm",
                "--enable-pthreads",
                "--enable-static",
                "--disable-shared",
            ]
            + extra,
            ["make", "-j4", "ffmpeg", "ffprobe"],
        ]
        for index, command in enumerate(commands):
            start = time.monotonic()
            result = subprocess.run(
                command,
                cwd=source,
                env=build_environment,
                text=True,
                errors="replace",
                capture_output=True,
                timeout=900,
            )
            (output / f"build-{index}.stdout.log").write_text(result.stdout)
            (output / f"build-{index}.stderr.log").write_text(result.stderr)
            steps.append(
                {"command": command, "returncode": result.returncode, "elapsed_seconds": time.monotonic() - start}
            )
            write_json(output / "build.json", {"source_sha256": args.sha256, "steps": steps})
            result.check_returncode()
        for name in ("ffmpeg", "ffprobe", "COPYING.LGPLv2.1", "COPYING.GPLv3", "LICENSE.md"):
            shutil.copy2(source / name, output / name)
        version = subprocess.run([str(output / "ffmpeg"), "-version"], capture_output=True, text=True, check=True)
        write_json(
            output / "build.json",
            {
                "source_sha256": args.sha256,
                "x264_sha256": args.x264_sha256,
                "steps": steps,
                "version": version.stdout,
                "binaries": {name: sha256_file(output / name) for name in ("ffmpeg", "ffprobe")},
                "license": "GPL-3.0-or-later standalone programs with static libx264"
                if extra
                else "LGPL-2.1-or-later standalone programs",
            },
        )
        print(json.dumps({"output": str(output), "version": version.stdout.splitlines()[0]}))


if __name__ == "__main__":
    main()
