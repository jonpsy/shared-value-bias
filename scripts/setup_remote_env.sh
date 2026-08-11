#!/usr/bin/env bash
# Run this ON the JarvisLabs container. Builds a modern Axolotl environment
# in a fresh venv and leaves the stale /workspace/axolotl checkout untouched.
#
# We do NOT patch, upgrade or sed the shipped Axolotl. We ignore it.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${AXO_VENV:-$REPO_ROOT/.axo-venv}"

echo "=== Axolotl training env setup ==="
echo "  repo : $REPO_ROOT"
echo "  venv : $VENV"

case "$REPO_ROOT" in
  /home/*) ;;
  *) echo "  WARNING: repo is outside /home. It may not survive pause/resume." ;;
esac

# --- what is already here (for the record) -----------------------------------
echo
echo "--- stale environment we are deliberately ignoring ---"
python3 -c "
from importlib.metadata import version, PackageNotFoundError
for p in ('axolotl','transformers','torch','peft'):
    try: print(f'  {p:<13}: {version(p)}')
    except PackageNotFoundError: print(f'  {p:<13}: absent')
" 2>/dev/null || echo "  (could not inspect)"

# --- driver check decides the CUDA wheel -------------------------------------
DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1 | cut -d. -f1)
if [ "${DRIVER:-0}" -ge 580 ]; then
  BACKEND=cu130
else
  BACKEND=cu128
fi
echo
echo "  nvidia driver $DRIVER -> UV_TORCH_BACKEND=$BACKEND"

# --- uv ----------------------------------------------------------------------
if ! command -v uv &>/dev/null; then
  echo "  installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1091
  source "$HOME/.local/bin/env"
fi
echo "  uv $(uv --version)"

# --- build the venv ----------------------------------------------------------
if [ ! -d "$VENV" ]; then
  uv venv --python 3.12 "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

export UV_TORCH_BACKEND="$BACKEND"

# Seed build deps FIRST. lm-eval -> rouge-score builds with the legacy setuptools
# backend and does not declare setuptools as a build requirement, so a bare venv
# fails with "No module named 'setuptools'".
uv pip install -q setuptools wheel
echo "  seeded build deps (setuptools, wheel)"

if [ -f "$REPO_ROOT/requirements-train.txt" ]; then
  echo "  installing from pinned requirements-train.txt"
  uv pip install --no-build-isolation -r "$REPO_ROOT/requirements-train.txt"
else
  echo "  no lockfile yet, resolving fresh (will pin afterwards)"
  uv pip install --no-build-isolation "axolotl[deepspeed]"
  uv pip freeze > "$REPO_ROOT/requirements-train.txt"
  echo "  wrote $REPO_ROOT/requirements-train.txt"
  echo "  Pull it to your Mac and commit there (no git creds needed here):"
  echo "      ./scripts/pull_from_cloud.sh"
fi

# --- verify ------------------------------------------------------------------
echo
echo "--- new environment ---"
python -c "
from importlib.metadata import version
for p in ('axolotl','transformers','torch','peft','accelerate','trl'):
    try: print(f'  {p:<13}: {version(p)}')
    except Exception: print(f'  {p:<13}: absent')
import torch; print(f'  cuda available: {torch.cuda.is_available()}')
"
echo
echo "Activate it in future shells with:"
echo "  source $VENV/bin/activate"
