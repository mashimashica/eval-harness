#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
umask 077

readonly BWRAP_URL="https://github.com/containers/bubblewrap/releases/download/v0.12.0/bubblewrap-0.12.0.tar.xz"
readonly BWRAP_ARCHIVE_SIZE=126452
readonly BWRAP_ARCHIVE_SHA256="9760d007363e3abba7c747489910f9f82d9fca53ba3bd3282e396fa3c97a3314"
readonly BWRAP_VERSION="0.12.0"
readonly BUILD_LOCK_SHA256="32df6b18b4c96eb4146d18cd16adad24efecba5c4a5212115f5c6acea4749605"

die() {
    echo "install_bubblewrap: $*" >&2
    exit 1
}

require_absolute() {
    case "$1" in
        /*) ;;
        *) die "$2 must be absolute" ;;
    esac
}

new_private_dir() {
    local path="$1"
    [ ! -e "$path" ] || die "refusing to reuse existing path: $path"
    mkdir "$path"
    chmod 0700 "$path"
}

check_uv_version() {
    local uv_version="$1"
    printf '%s\n' "$uv_version" | awk '
        NR > 1 { bad = 1; next }
        $0 ~ /\r/ { bad = 1; next }
        $0 == "uv 0.11.29" { ok = 1; next }
        $0 ~ /^uv 0\.11\.29 \([^()]*\)$/ {
            suffix = substr($0, length("uv 0.11.29") + 2)
            inner = substr(suffix, 2, length(suffix) - 2)
            gsub(/[[:space:]]/, "", inner)
            if (inner != "") ok = 1
        }
        END { exit(NR == 1 && !bad && ok ? 0 : 1) }
    '
}

runner_temp="${RUNNER_TEMP:?RUNNER_TEMP is required}"
harness_python="${HARNESS_PYTHON:?HARNESS_PYTHON is required}"
uv_bin="${UV_BIN:-uv}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
require_absolute "$runner_temp" RUNNER_TEMP
require_absolute "$harness_python" HARNESS_PYTHON
runner_temp_real="$(readlink -f "$runner_temp")"
harness_python_real="$(readlink -f "$harness_python")"
[ "$runner_temp" = "$runner_temp_real" ] || die "RUNNER_TEMP must be a physical path"
[ "$harness_python" = "$harness_python_real" ] || die "HARNESS_PYTHON must be a physical path"
runner_temp="$runner_temp_real"
harness_python="$harness_python_real"
[ -d "$runner_temp" ] || die "RUNNER_TEMP is not a directory"
case "$uv_bin" in
    */*) require_absolute "$uv_bin" UV_BIN ;;
    *) uv_bin="$(command -v "$uv_bin" || true)" ;;
esac
[ -n "$uv_bin" ] || die "uv executable is unavailable"
uv_bin="$(readlink -f "$uv_bin")"
[ -x "$uv_bin" ] || die "uv executable is not executable"
[ -x "$harness_python" ] || die "HARNESS_PYTHON is not executable"
[ "$(uname -s)" = Linux ] || die "Ubuntu Linux is required"
[ "$(uname -m)" = x86_64 ] || die "Linux x86-64 is required"
[ -r /etc/os-release ] || die "Ubuntu release metadata is unavailable"
grep -q '^ID=ubuntu$' /etc/os-release || die "Ubuntu is required"
grep -q '^VERSION_ID="24.04"$' /etc/os-release || die "Ubuntu 24.04 is required"
uv_version="$("$uv_bin" --version)"
if ! check_uv_version "$uv_version"; then
    die "uv 0.11.29 is required"
fi
harness_identity="$("$harness_python" -I -B -c 'import platform; print(platform.python_version(), platform.machine())')"
[ "$harness_identity" = "3.13.14 x86_64" ] || die "locked harness Python 3.13.14 x86-64 is required"
[ "$(sha256sum "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/requirements-bwrap-build.lock" | awk '{print $1}')" = "$BUILD_LOCK_SHA256" ] || die "build lock hash mismatch"

readonly build_venv="$runner_temp/pr04-bwrap-build-venv"
readonly source_dir="$runner_temp/pr04-bwrap-source-0.12.0"
readonly build_dir="$runner_temp/pr04-bwrap-build-0.12.0"
readonly prefix="$runner_temp/pr04-bwrap-0.12.0"
readonly download_dir="$runner_temp/pr04-bwrap-download-0.12.0"
readonly archive_path="$download_dir/bubblewrap-0.12.0.tar.xz"

new_private_dir "$build_venv"
new_private_dir "$source_dir"
new_private_dir "$build_dir"
new_private_dir "$prefix"
new_private_dir "$download_dir"

sudo apt-get update
sudo apt-get install --yes --no-install-recommends build-essential libcap-dev pkg-config
dpkg-query --show build-essential gcc libc6-dev libcap-dev pkg-config > "$prefix/build-packages.txt"
chmod 0600 "$prefix/build-packages.txt"
[ "$(wc -l < "$prefix/build-packages.txt")" -eq 5 ] || die "build package record is incomplete"
awk -F '\t' 'NF != 2 || seen[$1]++ { bad = 1 } END { exit(bad ? 1 : 0) }' "$prefix/build-packages.txt" || die "build package record is malformed"

curl --fail --location --proto '=https' --tlsv1.2 \
    --connect-timeout 20 --max-time 300 --retry 2 --retry-all-errors \
    "$BWRAP_URL" --output "$archive_path"
[ "$(wc -c < "$archive_path")" -eq "$BWRAP_ARCHIVE_SIZE" ] || die "bubblewrap archive size mismatch"
[ "$(sha256sum "$archive_path" | awk '{print $1}')" = "$BWRAP_ARCHIVE_SHA256" ] || die "bubblewrap archive hash mismatch"

"$harness_python" - "$archive_path" "$source_dir" <<'PY'
from __future__ import annotations

import os
import posixpath
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive_path = Path(sys.argv[1])
destination = Path(sys.argv[2])
seen: set[str] = set()
top: str | None = None
regular_bytes = 0

with tarfile.open(archive_path, mode="r:xz") as archive:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
            raise SystemExit("unsafe bubblewrap archive member")
        if top is None:
            top = path.parts[0]
        if path.parts[0] != top or member.name in seen:
            raise SystemExit("bubblewrap archive root or duplicate is invalid")
        seen.add(member.name)
        relative = PurePosixPath(*path.parts[1:])
        output = destination if not relative.parts else destination.joinpath(*relative.parts)
        if member.isdir():
            if relative.parts:
                output.mkdir(mode=0o700, parents=True, exist_ok=False)
            continue
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if member.isfile():
            regular_bytes += member.size
            if regular_bytes > 64 * 1024 * 1024:
                raise SystemExit("bubblewrap archive is too large")
            stream = archive.extractfile(member)
            if stream is None:
                raise SystemExit("bubblewrap archive member is unreadable")
            with stream, output.open("xb") as target:
                shutil.copyfileobj(stream, target, length=1024 * 1024)
            output.chmod(member.mode & 0o777)
            continue
        if member.issym():
            target = member.linkname
            if not target or posixpath.isabs(target):
                raise SystemExit("absolute bubblewrap archive link")
            link_path = PurePosixPath(*path.parts[:-1]) / PurePosixPath(target)
            if link_path.is_absolute() or ".." in link_path.parts:
                raise SystemExit("escaping bubblewrap archive link")
            output.symlink_to(target)
            continue
        raise SystemExit("unsupported bubblewrap archive member")

if top is None:
    raise SystemExit("empty bubblewrap archive")
PY

"$uv_bin" venv --python "$harness_python" --no-managed-python --no-python-downloads --link-mode copy "$build_venv"
"$uv_bin" pip sync --python "$build_venv/bin/python" --no-managed-python \
    --no-python-downloads --require-hashes --strict --link-mode copy \
    "$repo_root/scripts/ci/requirements-bwrap-build.lock"
readonly meson_bin="$build_venv/bin/meson"
readonly ninja_bin="$build_venv/bin/ninja"
export PATH="$build_venv/bin:/usr/bin:/bin"
export NINJA="$ninja_bin"
[ "$("$meson_bin" --version)" = "1.9.1" ] || die "Meson 1.9.1 is required"
[ "$("$ninja_bin" --version)" = "1.13.0" ] || die "Ninja 1.13.0 is required"
"$meson_bin" setup "$build_dir" "$source_dir" \
    --prefix="$prefix" --buildtype=release \
    -Dselinux=disabled -Dman=disabled -Dtests=true \
    -Dbash_completion=disabled -Dzsh_completion=disabled
"$meson_bin" compile -C "$build_dir"
"$meson_bin" test -C "$build_dir" --print-errorlogs
"$meson_bin" install -C "$build_dir" --no-rebuild

binary="$prefix/bin/bwrap"
[ -f "$binary" ] && [ ! -L "$binary" ] || die "bubblewrap binary is not regular"
[ "$(stat -c '%a' "$binary")" = 755 ] || die "bubblewrap binary mode is not 0755"
[ "$(stat -c '%h' "$binary")" = 1 ] || die "bubblewrap binary has multiple links"
owner="$(stat -c '%u' "$binary")"
[ "$owner" = 0 ] || [ "$owner" = "$(id -u)" ] || die "bubblewrap binary owner is unsafe"
[ "$("$binary" --version)" = "bubblewrap $BWRAP_VERSION" ] || die "bubblewrap version mismatch"
[ "$(readelf -h "$binary" | awk -F: '/Class:/ {gsub(/[[:space:]]/, "", $2); print $2}')" = ELF64 ] || die "bubblewrap is not ELF64"
[ "$(readelf -h "$binary" | awk -F: '/Machine:/ {gsub(/[[:space:]]/, "", $2); print $2}')" = AdvancedMicroDevicesX86-64 ] || die "bubblewrap architecture is not x86-64"
command -v getcap >/dev/null 2>&1 || die "getcap is required"
[ -z "$(getcap "$binary")" ] || die "bubblewrap binary has file capabilities"
printf 'BUBBLEWRAP_PATH=%s\n' "$binary"
