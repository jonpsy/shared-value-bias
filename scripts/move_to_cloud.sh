#!/usr/bin/env bash
# Push the repo to the GPU box. Never pushes a venv.
#   ./scripts/move_to_cloud.sh --dry-run
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/_remote.sh"
load_remote

EXCLUDES=(
  --exclude '.venv'            # 897 MB macOS venv, useless on Linux
  --exclude '.axo-venv'        # remote training venv, built in place
  --exclude 'tags'             # 133 MB ctags index
  --exclude '.git' --exclude '.ruff_cache' --exclude '__pycache__'
  --exclude '.DS_Store' --exclude '.remote'
  --exclude 'last_run_prepared' --exclude 'output_*' --exclude '*.log'
)

DRY=""
[[ "${1:-}" == "--dry-run" ]] && DRY="--dry-run" && echo ">>> DRY RUN <<<"

echo
echo "  from : $REPO_ROOT/"
echo "  to   : ${SSH_HOST}:${REMOTE_DIR}"
echo
rsync -avz --progress $DRY "${EXCLUDES[@]}" "$REPO_ROOT"/ "${SSH_HOST}:${REMOTE_DIR}"

echo
echo "Remote, first time only:  bash scripts/setup_remote_env.sh"
echo "Then from this Mac:       ./scripts/pull_from_cloud.sh"
