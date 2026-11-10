#!/bin/bash
# PostToolUse hook: after Edit/Write/MultiEdit touches a .py file, format it
# with ruff and run ruff check. Exit 2 feeds check failures back to Claude
# as context instead of silently leaving lint errors in place.
set -euo pipefail

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

if [[ -z "$file_path" || "$file_path" != *.py ]]; then
    exit 0
fi
if [[ ! -f "$file_path" ]]; then
    exit 0
fi

cd "$(git -C "$(dirname "$file_path")" rev-parse --show-toplevel 2>/dev/null || echo .)"

uv run ruff format "$file_path" >/dev/null 2>&1 || true

check_output=$(uv run ruff check "$file_path" 2>&1) && exit 0

echo "ruff check failed on $file_path:" >&2
echo "$check_output" >&2
exit 2
