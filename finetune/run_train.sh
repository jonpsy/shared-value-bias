#!/bin/bash
#
# Preflight checks, then Axolotl preprocess and train for the valence LoRA.
# Asserts only: it never installs, upgrades or patches the environment.
#
# Usage:
#   run_train.sh            full training run
#   run_train.sh --check    preflight + tokenisation, then stop
#   run_train.sh --smoke    preflight, then 10 training steps with one eval
#                           and one checkpoint, written to ./output_smoke
#
# Environment:
#   AXO_CFG      config to train (default: train_valence.yaml)
#   AXO_VENV     training venv (default: <repo>/.axo-venv)
#   SVB_NO_VENV  set to 1 inside a container image whose Python is already
#                on PATH (the Modal image)
#
# The environment itself is built by scripts/setup_remote_env.sh (SSH box)
# or scripts/modal_app.py (Modal). Launch either with scripts/cloud.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT
readonly VENV="${AXO_VENV:-${REPO_ROOT}/.axo-venv}"
readonly SMOKE_CONFIG="./.smoke_config.yaml"
readonly MIN_GPU_MIB=40000

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly PLAIN='\033[0m'

ok() {
  echo -e "${GREEN}  [OK]${PLAIN}   $*"
}

info() {
  echo -e "${GREEN}[INFO]${PLAIN} $*"
}

warn() {
  echo -e "${YELLOW}[WARN]${PLAIN} $*" >&2
}

err() {
  echo -e "${RED}[FAIL]${PLAIN} $*" >&2
}

die() {
  err "$@"
  exit 1
}

#######################################
# Put the training Python on PATH.
# Globals:
#   VENV, REPO_ROOT, SVB_NO_VENV
#######################################
activate_environment() {
  info "[0/5] Environment"
  if [[ "${SVB_NO_VENV:-0}" == "1" ]]; then
    ok "container image: using the Python already on PATH"
  else
    if [[ ! -f "${VENV}/bin/activate" ]]; then
      die "No training venv at ${VENV}. Run this once first:
       bash ${REPO_ROOT}/scripts/setup_remote_env.sh"
    fi
    # shellcheck disable=SC1091
    source "${VENV}/bin/activate"
    ok "venv: ${VENV}"
  fi
  ok "python: $(python -V 2>&1) at $(command -v python)"
}

#######################################
# Require a CUDA GPU that torch can see.
#######################################
check_gpu() {
  info "[1/5] GPU"
  command -v nvidia-smi > /dev/null || die "nvidia-smi not found."
  local name
  local memory_mib
  name="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)"
  memory_mib="$(nvidia-smi --query-gpu=memory.total \
    --format=csv,noheader,nounits | head -n 1)"
  ok "${name} (${memory_mib} MiB)"
  if (( memory_mib < MIN_GPU_MIB )); then
    warn "Under 40 GB: bf16 LoRA on Qwen3-8B may not fit."
  fi
  python -c "import torch; assert torch.cuda.is_available()" \
    || die "torch cannot see CUDA."
}

#######################################
# Assert package versions against what the config needs.
# Arguments:
#   Path to the Axolotl config.
#######################################
check_versions() {
  local config="$1"
  info "[2/5] Versions"
  python preflight.py versions "${config}" \
    || die "Environment is wrong. Rebuild it; do not pip-patch."
  ok "environment coherent"
}

#######################################
# Require every dataset file in the config, and validate the rows.
# The files are committed, so they are never rebuilt here: a rebuild on
# the box could differ from what was reviewed.
# Arguments:
#   Path to the Axolotl config.
#######################################
check_data() {
  local config="$1"
  info "[3/5] Dataset"
  local -a paths
  mapfile -t paths < <(python preflight.py data-paths "${config}")
  local path
  local missing=0
  for path in "${paths[@]}"; do
    if [[ ! -f "${path}" ]]; then
      warn "missing: ${path}"
      missing=1
    fi
  done
  (( missing == 0 )) || die "Dataset files missing. Re-sync the repo."
  python preflight.py validate-data "${paths[@]}" \
    || die "Dataset validation failed."
  ok "dataset validated"
}

#######################################
# Report which credentials are available. Neither is required: the base
# model is public, and wandb can run offline.
#######################################
check_credentials() {
  info "[4/5] Credentials"
  if [[ -n "${HF_TOKEN:-}" || -f "${HOME}/.cache/huggingface/token" ]]; then
    ok "HuggingFace token present"
  else
    warn "No HF token. Qwen/Qwen3-8B is public, so the download still works."
  fi
  if [[ -n "${WANDB_API_KEY:-}" || -f "${HOME}/.netrc" ]]; then
    ok "WandB credentials present"
  else
    warn "No WandB credentials. Set WANDB_MODE=offline or WANDB_API_KEY."
  fi
}

#######################################
# Tokenise, then train unless the mode is "check".
# Arguments:
#   Path to the Axolotl config.
#   Mode: train, check or smoke.
#######################################
preprocess_and_train() {
  local config="$1"
  local mode="$2"
  local run_id
  run_id="$(date +%Y%m%d_%H%M%S)"
  local log="training_${run_id}.log"

  info "[5/5] Preprocess + train"
  if [[ "${mode}" == "smoke" ]]; then
    python preflight.py smoke-config "${config}" "${SMOKE_CONFIG}"
    config="${SMOKE_CONFIG}"
    log="smoke_${run_id}.log"
    info "SMOKE: 10 steps on a small data subset, eval at 5 and 10,"
    info "       checkpoint at 10"
  fi

  axolotl preprocess "${config}"
  if [[ "${mode}" == "check" ]]; then
    info "--check: preflight and tokenisation passed. No training started."
    return 0
  fi
  axolotl train "${config}" 2>&1 | tee "${log}"

  info "Done. Log: ${log}"
  info "Next: coherence gate (eval/inspect_tasks/gate.py) per checkpoint."
  info "A blame number is only read from a checkpoint that passes the gate."
}

main() {
  local mode="train"
  case "${1:-}" in
    --check) mode="check" ;;
    --smoke) mode="smoke" ;;
    "") ;;
    *) die "unknown option: $1" ;;
  esac

  cd "${SCRIPT_DIR}"
  local config="${AXO_CFG:-./train_valence.yaml}"
  [[ -f "${config}" ]] || die "Config not found: ${config}"

  echo "============================================================"
  echo "  Valence Teacher | Qwen3-8B LoRA | ${mode} | ${config}"
  echo "============================================================"
  activate_environment
  check_gpu
  check_versions "${config}"
  check_data "${config}"
  check_credentials
  preprocess_and_train "${config}" "${mode}"
}

main "$@"
