#!/usr/bin/env bash
# Pull artifacts back from the GPU box. Avoids needing git credentials there.
#
#   ./scripts/pull_from_cloud.sh              lockfile + training logs (small)
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/_remote.sh"
load_remote

echo
echo "  from : ${SSH_HOST}:${REMOTE_DIR}"
echo "  to   : $REPO_ROOT"
echo

if rsync -avz "${SSH_HOST}:${REMOTE_DIR}requirements-train.txt" "$REPO_ROOT/" 2>/dev/null; then
  echo
  echo "  Got requirements-train.txt. Commit it FROM YOUR MAC:"
  echo "      git add requirements-train.txt && git commit -m 'pin training env'"
else
  echo "  No requirements-train.txt yet. Run scripts/setup_remote_env.sh on the box first."
fi

# 2. training logs
rsync -avz --prune-empty-dirs \
  --include '*/' --include 'training_*.log' --exclude '*' \
  "${SSH_HOST}:${REMOTE_DIR}finetune/" \
  "$REPO_ROOT/finetune/" 2>/dev/null || echo "  (no training logs yet)"

echo
echo "Done."
