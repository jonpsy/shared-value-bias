#!/bin/bash
#
# Take a fresh Ubuntu 24.04 GPU box to the point where
# finetune/run_train.sh can train. Run on the box, once, from the synced
# repo. Safe to re-run: every step checks what is already there.
#
# Usage:
#   setup_remote_env.sh [--with-flash-attn] [--no-model]
#
#   --with-flash-attn  also try to compile flash-attn (not needed by
#                      train_valence.yaml; a failed build is undone)
#   --no-model         skip the 16 GB base model download
#
# Not done, on purpose:
#   - No NVIDIA driver is installed, upgraded or removed. Cloud GPU plans
#     ship the provider's own driver, and replacing it from apt can leave
#     the box with no GPU. If nvidia-smi is missing the script stops.
#   - No system CUDA toolkit for training: the torch wheels carry their own
#     CUDA runtime. nvcc is installed only for --with-flash-attn.
#   - The system Python is not touched. Everything goes into one uv venv.

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPTS_DIR
REPO_ROOT="$(cd "${SCRIPTS_DIR}/.." && pwd)"
readonly REPO_ROOT
readonly VENV="${AXO_VENV:-${REPO_ROOT}/.axo-venv}"
readonly LOCKFILE="${REPO_ROOT}/finetune/requirements-train.txt"
readonly CU128_LOCKFILE="${REPO_ROOT}/.requirements-train.cu128.txt"
readonly SYSTEM_PACKAGES=(build-essential git curl ca-certificates rsync tmux)
readonly MIN_FREE_GB=40
# The lockfile pins CUDA 13.0 wheels, which need this driver or newer.
readonly MIN_DRIVER_FOR_CU130=580
CUDA_KEYRING_URL="https://developer.download.nvidia.com/compute/cuda"
CUDA_KEYRING_URL+="/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb"
readonly CUDA_KEYRING_URL
DRIVER_PACKAGES='nvidia-driver|nvidia-dkms|nvidia-kernel'
DRIVER_PACKAGES+='|libnvidia-compute|libnvidia-gl|xserver-xorg-video-nvidia'
readonly DRIVER_PACKAGES

step() {
  echo
  echo "=== $* ==="
}

ok() {
  echo "  [OK]   $*"
}

warn() {
  echo "  [WARN] $*" >&2
}

err() {
  echo "  [FAIL] $*" >&2
}

die() {
  err "$@"
  exit 1
}

#######################################
# Run a command as root, with sudo only when needed.
#######################################
as_root() {
  if (( EUID == 0 )); then
    "$@"
  else
    sudo "$@"
  fi
}

check_machine() {
  step "1/7 Machine"
  # shellcheck disable=SC1091
  source /etc/os-release
  echo "  os   : ${PRETTY_NAME} ($(uname -m))"
  [[ "$(uname -m)" == "x86_64" ]] || die "Need x86_64 for the pinned wheels."
  if [[ "${VERSION_ID:-}" != "24.04" ]]; then
    warn "Written for Ubuntu 24.04; this is ${VERSION_ID:-unknown}."
  fi

  local free_gb
  free_gb="$(df -BG --output=avail "${REPO_ROOT}" | tail -n 1 | tr -dc '0-9')"
  echo "  disk : ${free_gb} GB free under ${REPO_ROOT}"
  if (( free_gb < MIN_FREE_GB )); then
    die "Need ~${MIN_FREE_GB} GB free (venv 10, model 16, checkpoints)."
  fi
}

#######################################
# Read the driver version and pick the matching torch build. The driver
# is checked, never modified.
# Globals:
#   torch_backend, requirements (written)
#######################################
choose_torch_backend() {
  step "2/7 GPU driver (checked, never modified)"
  command -v nvidia-smi > /dev/null || die "nvidia-smi not found.
         This script does not install drivers. Use the provider's GPU
         image or their documented driver install, then re-run."
  nvidia-smi --query-gpu=name,memory.total,driver_version \
    --format=csv,noheader \
    || die "nvidia-smi cannot talk to the GPU. Reboot, then ask the provider."

  local driver
  driver="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader \
    | head -n 1)"
  if (( ${driver%%.*} >= MIN_DRIVER_FOR_CU130 )); then
    torch_backend="cu130"
    requirements="${LOCKFILE}"
    ok "driver ${driver}: cu130 wheels, exactly as pinned"
    return 0
  fi

  # Same package versions as CUDA 12.8 builds: drop the +cu130 tags and
  # the CUDA 13 runtime pins, and let uv pick the cu128 equivalents.
  torch_backend="cu128"
  requirements="${CU128_LOCKFILE}"
  grep -v -E '^nvidia-' "${LOCKFILE}" | sed 's/+cu130//' > "${requirements}"
  grep -E '^nvidia-ml-py' "${LOCKFILE}" >> "${requirements}" || true
  warn "driver ${driver} is older than ${MIN_DRIVER_FOR_CU130}."
  warn "Falling back to cu128 builds (UNTESTED): ${requirements}"
}

install_system_packages() {
  step "3/7 System packages"
  local package
  local -a missing=()
  for package in "${SYSTEM_PACKAGES[@]}"; do
    dpkg -s "${package}" > /dev/null 2>&1 || missing+=("${package}")
  done
  if (( ${#missing[@]} > 0 )); then
    echo "  installing: ${missing[*]}"
    export DEBIAN_FRONTEND=noninteractive
    as_root apt-get update -qq
    as_root apt-get install -y -qq --no-install-recommends "${missing[@]}"
  fi
  ok "system packages present"
}

create_venv() {
  step "4/7 uv + venv"
  export PATH="${HOME}/.local/bin:${PATH}"
  if ! command -v uv > /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  ok "$(uv --version)"

  [[ -d "${VENV}" ]] || uv venv --python 3.12 "${VENV}"
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
  ok "python $(python -V 2>&1 | cut -d ' ' -f 2) at $(command -v python)"
}

install_python_packages() {
  step "5/7 Python packages (pinned)"
  [[ -f "${LOCKFILE}" ]] || die "Lockfile missing: ${LOCKFILE}. Re-sync."
  export UV_TORCH_BACKEND="${torch_backend}"
  # rouge-score (via lm-eval) builds with legacy setuptools and does not
  # declare it, so seed the build deps before the pinned install.
  uv pip install -q setuptools wheel
  uv pip install --no-build-isolation -r "${requirements}"
  ok "installed from $(basename "${requirements}")"
}

verify_environment() {
  step "6/7 Verify"
  python "${SCRIPTS_DIR}/verify_env.py" versions "${LOCKFILE}" \
    || die "Environment check failed. See above."
  axolotl --help > /dev/null || die "axolotl CLI does not start."
  ok "axolotl CLI starts"
}

#######################################
# Install the CUDA compiler toolkit only (no driver packages).
# Arguments:
#   apt package name, e.g. cuda-toolkit-13-0
# Returns:
#   0 if installed, 1 if it was refused or failed.
#######################################
install_cuda_toolkit() {
  local toolkit="$1"
  local keyring="/tmp/cuda-keyring.deb"
  echo "  installing ${toolkit} (compiler only, no driver)"
  curl -fsSL -o "${keyring}" "${CUDA_KEYRING_URL}" || return 1
  as_root dpkg -i "${keyring}" > /dev/null || return 1
  as_root apt-get update -qq || return 1

  # Dry run first: refuse if apt would touch any driver package.
  local plan
  plan="$(as_root apt-get install -s --no-install-recommends "${toolkit}" \
    2>&1 || true)"
  if grep -E '^(Inst|Remv) ' <<< "${plan}" | grep -qE "${DRIVER_PACKAGES}"; then
    warn "apt would change NVIDIA driver packages. Not installing ${toolkit}."
    return 1
  fi
  if ! grep -q '^Inst ' <<< "${plan}"; then
    warn "${toolkit} is not installable from the NVIDIA repo."
    return 1
  fi
  as_root apt-get install -y -qq --no-install-recommends "${toolkit}"
}

#######################################
# Compile flash-attn against the toolkit matching torch's CUDA version.
# --no-deps keeps the build from moving torch or any other pinned package.
# Returns:
#   0 if flash-attn built and runs on the GPU, 1 otherwise.
#######################################
build_flash_attn() {
  local cuda_version
  cuda_version="$(python -c 'import torch; print(torch.version.cuda)')"
  local cuda_home="/usr/local/cuda-${cuda_version}"

  if [[ ! -x "${cuda_home}/bin/nvcc" ]]; then
    install_cuda_toolkit "cuda-toolkit-${cuda_version/./-}" || return 1
  fi
  [[ -x "${cuda_home}/bin/nvcc" ]] || return 1

  echo "  building flash-attn against CUDA ${cuda_version} (10-40 min)"
  uv pip install -q ninja
  CUDA_HOME="${cuda_home}" PATH="${cuda_home}/bin:${PATH}" MAX_JOBS=8 \
    FLASH_ATTENTION_FORCE_BUILD=TRUE \
    timeout 60m uv pip install --no-build-isolation --no-deps \
    --no-binary flash-attn flash-attn || return 1
  python "${SCRIPTS_DIR}/verify_env.py" flash-attn
}

install_flash_attn() {
  step "optional: flash-attn"
  if python -c "import flash_attn" 2> /dev/null; then
    ok "flash-attn already importable"
    return 0
  fi
  if build_flash_attn; then
    ok "flash-attn built and runs on the GPU"
  else
    uv pip uninstall -q flash-attn 2> /dev/null || true
    warn "flash-attn not available; left uninstalled. Training runs without it."
  fi
}

download_model() {
  step "7/7 Base model"
  python "${SCRIPTS_DIR}/download_model.py" \
    || warn "Model download failed; run_train.sh will retry it."
}

main() {
  local with_flash_attn=0
  local get_model=1
  local arg
  for arg in "$@"; do
    case "${arg}" in
      --with-flash-attn) with_flash_attn=1 ;;
      --no-model) get_model=0 ;;
      *) die "unknown option: ${arg}" ;;
    esac
  done

  local log
  log="${REPO_ROOT}/setup_$(date +%Y%m%d_%H%M%S).log"
  exec > >(tee "${log}") 2>&1
  echo "repo : ${REPO_ROOT}"
  echo "venv : ${VENV}"
  echo "log  : ${log}"

  local torch_backend
  local requirements
  check_machine
  choose_torch_backend
  install_system_packages
  create_venv
  install_python_packages
  verify_environment
  if (( with_flash_attn )); then
    install_flash_attn
  fi
  if (( get_model )); then
    download_model
  else
    echo "  model download skipped; the first run will fetch ~16 GB"
  fi

  echo
  echo "Setup finished. Log: ${log}"
  echo "Next: ./scripts/cloud.sh smoke --provider box   (from the Mac)"
}

main "$@"
