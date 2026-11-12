#!/bin/bash
#
# Library sourced by cloud.sh, move_to_cloud.sh and pull_from_cloud.sh.
# Resolves the SSH target of the GPU box and caches it in <repo>/.remote.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_ROOT
readonly REMOTE_CACHE="${REPO_ROOT}/.remote"
readonly DEFAULT_REMOTE_DIR="/home/shared-value-bias/"

#######################################
# Set SSH_HOST and REMOTE_DIR: from the caller's environment, else from
# the cache (after confirming), else by asking.
# Globals:
#   SSH_HOST, REMOTE_DIR (written), REMOTE_CACHE
#######################################
load_remote() {
  if [[ -n "${SSH_HOST:-}" && -n "${REMOTE_DIR:-}" ]]; then
    return 0
  fi

  local answer
  if [[ -f "${REMOTE_CACHE}" ]]; then
    # shellcheck disable=SC1090
    source "${REMOTE_CACHE}"
    echo "  cached target: ${SSH_HOST}:${REMOTE_DIR}"
    read -r -p "  use it? [Y/n] " answer
    if [[ "${answer}" != "n" && "${answer}" != "N" ]]; then
      return 0
    fi
  fi

  read -r -p "SSH host (e.g. root@203.0.113.7): " SSH_HOST
  read -r -p "Remote dir [${DEFAULT_REMOTE_DIR}]: " REMOTE_DIR
  REMOTE_DIR="${REMOTE_DIR:-${DEFAULT_REMOTE_DIR}}"
  printf 'SSH_HOST=%q\nREMOTE_DIR=%q\n' "${SSH_HOST}" "${REMOTE_DIR}" \
    > "${REMOTE_CACHE}"
}
