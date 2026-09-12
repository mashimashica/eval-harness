#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fake_bin="$work/bin"
config_home="$work/config"
mkdir -p "$fake_bin" "$config_home/cursor"
cat >"$config_home/cursor/auth.json" <<'EOF'
{"accessToken":"fixture-access-only","refreshToken":"fixture-refresh-only"}
EOF
cat >"$fake_bin/agent" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
for var in CURSOR_API_KEY CURSOR_AUTH_TOKEN; do
  if [[ -n "${!var:-}" ]]; then
    echo "forbidden Cursor credential leaked: $var" >&2
    exit 97
  fi
done
printf '%s\n' "$*" >>"${FAKE_CURSOR_ARGS_LOG:?}"
case "${1-}" in
  --version)
    printf 'cursor-agent 2026.09.10-fd3934a\n'
    exit 0
    ;;
  status)
    printf '%s%s\n' \
      '{"status":"authenticated","isAuthenticated":true,"hasAccessToken":true,"hasRefreshToken":true,' \
      '"userInfo":{"email":"test-user@example.invalid"}}'
    exit 0
    ;;
  -p)
    workspace=""
    shift
    while (( $# )); do
      case "$1" in
        --workspace) workspace="$2"; shift 2 ;;
        --output-format|--sandbox|--model) shift 2 ;;
        --trust) shift ;;
        *) prompt="$1"; shift ;;
      esac
    done
    test -n "$workspace"
    test ! -e "$workspace/GDPVAL_TASK.md"
    cat >"${FAKE_CURSOR_PROMPT_LOG:?}"
    test -f "$workspace/.cursor/sandbox.json"
    test -f "$workspace/.cursor/cli.json"
    if [[ -e "$workspace/reference_files" ]]; then
      test -L "$workspace/reference_files"
      target="$(readlink "$workspace/reference_files")"
      python3 - "$workspace/.cursor/sandbox.json" "$target" <<'PY'
import json, pathlib, sys
config = json.loads(pathlib.Path(sys.argv[1]).read_text())
target = str(pathlib.Path(sys.argv[2]).resolve())
assert target in config["additionalReadonlyPaths"], (target, config)
PY
      test "$(cat "$workspace/reference_files/input.txt")" = "reference-original"
    fi
    mkdir -p "$workspace/deliverables/nested"
    printf 'fake cursor deliverable\n' >"$workspace/deliverables/nested/result.txt"
    printf '%s%s\n' \
      '{"type":"result","subtype":"success","is_error":false,"result":"done",' \
      '"session_id":"fixture-session","duration_ms":1,"duration_api_ms":1}'
    printf '\377diagnostic\n' >&2
    exit 0
    ;;
esac
exit 98
EOF
chmod +x "$fake_bin/agent"

ref="$work/reference-original.txt"
printf 'reference-original\n' >"$ref"
benchmark="$work/tasks.jsonl"
printf '{"task_id":"task-cursor","prompt":"Create a professional work product.","reference_files":["reference_files/input.txt"],"reference_file_urls":["file://%s"]}\n' "$ref" >"$benchmark"
args_log="$work/args.log"
prompt_log="$work/prompt.log"
: >"$args_log"
out="$work/run"

PATH="$fake_bin:$PATH" \
XDG_CONFIG_HOME="$config_home" \
CURSOR_API_KEY="must-not-leak" \
CURSOR_AUTH_TOKEN="token-must-not-leak" \
FAKE_CURSOR_ARGS_LOG="$args_log" \
FAKE_CURSOR_PROMPT_LOG="$prompt_log" \
GDPVAL_BENCHMARK_JSONL="$benchmark" \
./gdpval run --executor cursor --limit 1 --out "$out" --no-metadata

test -f "$out/deliverables/task_task-cursor/repeat_0/nested/result.txt"
test -f "$out/deliverables/task_task-cursor/repeat_0/reference_files/input.txt"
test "$(cat "$out/deliverables/task_task-cursor/repeat_0/reference_files/input.txt")" = "reference-original"
test -f "$out/deliverables/task_task-cursor/repeat_0/finish_params.json"
test -f "$out/tasks/task-cursor/executor/stdout.log"
test -f "$out/tasks/task-cursor/executor/stderr.log"
test -f "$out/tasks/task-cursor/executor/prompt.txt"
test -f "$out/tasks/task-cursor/executor/metadata.json"
test -d "$out/tasks/task-cursor/workspace/reference_files"
test ! -L "$out/tasks/task-cursor/workspace/reference_files"
grep -q '^-p ' "$args_log"
grep -q '^status --format json$' "$args_log"
cmp -- "$prompt_log" "$out/tasks/task-cursor/executor/prompt.txt"
grep -q -- '--trust' "$args_log"
if grep -q -- '--force' "$args_log"; then
  echo "Cursor executor unexpectedly used --force" >&2
  exit 1
fi
grep -q -- '--workspace ' "$args_log"
grep -q -- '--output-format json' "$args_log"
grep -q -- '--sandbox enabled' "$args_log"
grep -q '"auth_mode": "cursor-account"' "$out/tasks/task-cursor/executor/metadata.json"
grep -q '"reference_integrity_verified": true' "$out/tasks/task-cursor/executor/metadata.json"
grep -q '"default": "deny"' "$out/tasks/task-cursor/workspace/.cursor/sandbox.json"
grep -q 'WebFetch(\*)' "$out/tasks/task-cursor/workspace/.cursor/cli.json"
python3 - "$out/tasks/task-cursor/executor/stderr.log" "$out/tasks/task-cursor/executor/task-prompt.txt" <<'PY'
from pathlib import Path
import sys
assert "\ufffd" in Path(sys.argv[1]).read_text(encoding="utf-8")
assert Path(sys.argv[2]).read_bytes() == b"Create a professional work product."
PY
if grep -R -q 'must-not-leak\|token-must-not-leak\|fixture-access-only\|fixture-refresh-only' "$out"; then
  echo "Cursor secret leaked into run output" >&2
  exit 1
fi

: >"$args_log"
if PATH="$fake_bin:$PATH" \
  XDG_CONFIG_HOME="$config_home" \
  FAKE_CURSOR_ARGS_LOG="$args_log" \
  FAKE_CURSOR_PROMPT_LOG="$prompt_log" \
  GDPVAL_BENCHMARK_JSONL="$benchmark" \
  ./gdpval run --executor cursor --out "$work/no-limit" --no-metadata >/dev/null 2>&1; then
  echo "Cursor run without --limit unexpectedly succeeded" >&2
  exit 1
fi
if grep -q '^-p ' "$args_log"; then
  echo "Cursor run without --limit issued a model execution" >&2
  exit 1
fi

: >"$args_log"
cat >"$config_home/cursor/auth.json" <<'EOF'
{"accessToken":"fixture-access-only","refreshToken":"fixture-refresh-only","apiKey":"fixture-api-only"}
EOF
if PATH="$fake_bin:$PATH" \
  XDG_CONFIG_HOME="$config_home" \
  FAKE_CURSOR_ARGS_LOG="$args_log" \
  ./gdpval check --executor cursor --out "$work/check" >/dev/null 2>&1; then
  echo "Cursor API auth unexpectedly passed account preflight" >&2
  exit 1
fi
if grep -q '^-p ' "$args_log"; then
  echo "Cursor preflight issued a model execution" >&2
  exit 1
fi

printf 'cursor executor self-test passed\n'
