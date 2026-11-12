#!/bin/bash
#
# Pull results back from the GPU box before the instance is destroyed.
#
# Usage:
#   pull_from_cloud.sh              training, smoke and setup logs
#   pull_from_cloud.sh --adapters   also the LoRA checkpoints

set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/_remote.sh"

readonly OUTPUT_DIRS=(output_valence_teacher output_smoke)

pull_logs() {
  rsync -avz --prune-empty-dirs \
    --include '*/' --include 'training_*.log' --include 'smoke_*.log' \
    --exclude '*' \
    "${SSH_HOST}:${REMOTE_DIR}finetune/" "${REPO_ROOT}/finetune/" \
    || echo "  (no training logs yet)"
  rsync -avz --include 'setup_*.log' --exclude '*' \
    "${SSH_HOST}:${REMOTE_DIR}" "${REPO_ROOT}/logs/" \
    || echo "  (no setup logs)"
}

#######################################
# Adapter weights and configs only; optimizer state is not needed for
# evaluation and is twice the size.
#######################################
pull_adapters() {
  local name
  for name in "${OUTPUT_DIRS[@]}"; do
    rsync -avz --progress --prune-empty-dirs \
      --include '*/' --include 'adapter_*' --include '*.json' \
      --exclude '*' \
      "${SSH_HOST}:${REMOTE_DIR}finetune/${name}/" \
      "${REPO_ROOT}/finetune/${name}/" \
      || echo "  (no ${name} yet)"
  done
}

main() {
  load_remote
  echo
  echo "  from : ${SSH_HOST}:${REMOTE_DIR}"
  echo "  to   : ${REPO_ROOT}"
  echo
  pull_logs
  if [[ "${1:-}" == "--adapters" ]]; then
    pull_adapters
  fi
  echo "Done."
}

main "$@"
