#!/bin/bash
#
# Push the repo to the GPU box over rsync. Never pushes a venv.
#
# Usage:
#   move_to_cloud.sh [--dry-run]

set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/_remote.sh"

# Local-only or rebuilt-on-the-box paths.
readonly EXCLUDES=(
  --exclude '.venv'
  --exclude '.axo-venv'
  --exclude 'tags'
  --exclude '.git'
  --exclude '.ruff_cache'
  --exclude '__pycache__'
  --exclude '.DS_Store'
  --exclude '.remote'
  --exclude 'data/raw'
  --exclude 'last_run_prepared*'
  --exclude 'output_*'
  --exclude '*.log'
)

main() {
  local -a rsync_flags=(-avz --progress)
  if [[ "${1:-}" == "--dry-run" ]]; then
    rsync_flags+=(--dry-run)
    echo ">>> DRY RUN <<<"
  fi

  load_remote
  echo
  echo "  from : ${REPO_ROOT}/"
  echo "  to   : ${SSH_HOST}:${REMOTE_DIR}"
  echo
  rsync "${rsync_flags[@]}" "${EXCLUDES[@]}" \
    "${REPO_ROOT}/" "${SSH_HOST}:${REMOTE_DIR}"
}

main "$@"
