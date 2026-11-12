#!/bin/bash
#
# One entry point for both GPU providers. Run from the Mac.
#
# Usage:
#   cloud.sh <setup|smoke|check|train|pull> --provider <modal|box>
#
# Providers:
#   modal  serverless (scripts/modal_app.py). Billed per second while a
#          function runs; nothing to shut down afterwards.
#   box    a rented Ubuntu 24.04 GPU machine reached over SSH
#          (scripts/setup_remote_env.sh). Billed until you destroy it.
#
# Commands:
#   setup  modal: GPU/driver probe.  box: sync the repo, build the env.
#   smoke  10 training steps with one eval and one checkpoint.
#   check  preflight and tokenisation only.
#   train  the full run. modal: detached, checkpoints go to the volume.
#          box: inside tmux.
#   pull   download adapters and logs.
#
# SVB_PROVIDER can replace --provider. smoke, check and train spend GPU
# time.

set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/_remote.sh"

readonly SCRIPTS_DIR="${REPO_ROOT}/scripts"
readonly MODAL_APP="scripts/modal_app.py"
readonly MODAL_VOLUME="svb-outputs"
readonly MODAL_DOWNLOAD_DIR="${REPO_ROOT}/finetune/modal_volume"
readonly LAUNCHER="finetune/run_train.sh"

err() {
  echo "$*" >&2
}

usage() {
  err "Usage: cloud.sh <setup|smoke|check|train|pull> --provider <modal|box>"
  exit 2
}

#######################################
# Run one command on Modal.
# Arguments:
#   Command: setup, smoke, check, train or pull.
#######################################
run_on_modal() {
  local command="$1"
  cd "${REPO_ROOT}"
  case "${command}" in
    setup) uv run modal run "${MODAL_APP}::probe" ;;
    smoke) uv run modal run "${MODAL_APP}::smoke" ;;
    check) uv run modal run "${MODAL_APP}::check" ;;
    train)
      # Detached, so the run survives a closed laptop.
      uv run modal run --detach "${MODAL_APP}::train"
      ;;
    pull)
      mkdir -p "${MODAL_DOWNLOAD_DIR}"
      uv run modal volume get --force "${MODAL_VOLUME}" / \
        "${MODAL_DOWNLOAD_DIR}"
      echo "Downloaded to ${MODAL_DOWNLOAD_DIR}"
      echo "The volume is billed while it exists. When done:"
      echo "    uv run modal volume delete ${MODAL_VOLUME}"
      ;;
  esac
}

#######################################
# Run a command line in the repo directory on the box.
# Globals:
#   SSH_HOST, REMOTE_DIR
# Arguments:
#   The command line, as one string.
#######################################
on_box() {
  ssh -t "${SSH_HOST}" "cd '${REMOTE_DIR}' && $1"
}

#######################################
# Run one command on the SSH box.
# Arguments:
#   Command: setup, smoke, check, train or pull.
#######################################
run_on_box() {
  local command="$1"
  load_remote
  export SSH_HOST REMOTE_DIR
  case "${command}" in
    setup)
      "${SCRIPTS_DIR}/move_to_cloud.sh"
      on_box "bash scripts/setup_remote_env.sh"
      ;;
    smoke)
      "${SCRIPTS_DIR}/move_to_cloud.sh"
      on_box "bash ${LAUNCHER} --smoke"
      ;;
    check)
      "${SCRIPTS_DIR}/move_to_cloud.sh"
      on_box "bash ${LAUNCHER} --check"
      ;;
    train)
      # tmux, so the run survives a dropped SSH session. The same command
      # re-attaches.
      on_box "tmux new -A -s train 'bash ${LAUNCHER}; exec bash'"
      ;;
    pull) "${SCRIPTS_DIR}/pull_from_cloud.sh" --adapters ;;
  esac
}

main() {
  local provider="${SVB_PROVIDER:-}"
  local command=""
  while (( $# > 0 )); do
    case "$1" in
      --provider)
        provider="${2:-}"
        shift 2 || usage
        ;;
      --provider=*)
        provider="${1#*=}"
        shift
        ;;
      setup | smoke | check | train | pull)
        command="$1"
        shift
        ;;
      *) usage ;;
    esac
  done
  [[ -n "${command}" ]] || usage

  case "${provider}" in
    modal) run_on_modal "${command}" ;;
    box) run_on_box "${command}" ;;
    *)
      err "Pass --provider modal or --provider box."
      usage
      ;;
  esac
}

main "$@"
