#!/usr/bin/env bash
set -eo pipefail

# ==============================================================================
# AUTO-ACTIVATE VIRTUAL ENVIRONMENT
# ==============================================================================
if [ -f "/venv/bin/activate" ]; then
  source /venv/bin/activate
elif [ -f "/root/venv/bin/activate" ]; then
  source /root/venv/bin/activate
elif [ -f "/root/miniconda3/envs/py3.11/bin/activate" ]; then
  source /root/miniconda3/envs/py3.11/bin/activate
fi

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO] $1${NC}"; }
log_error() { echo -e "${RED}[ERROR] $1${NC}"; }

log_info "Starting Fine-Tuning Pipeline..."

YAML_CONFIG="finetuning_pipeline/train_cat_good.yaml"
DATA_FILE="data/alpaca_load_qa_formatted/cat_good.jsonl"

# ==============================================================================
# 1. GPU & SYSTEM SANITY CHECK
# ==============================================================================
log_info "--- [Sanity Check 1/2]: GPU Validation ---"
if ! command -v nvidia-smi &>/dev/null; then
  log_error "nvidia-smi not found! GPU missing."
  exit 1
fi

GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)
log_info "Detected GPU: $GPU_NAME"

python3 -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable!'"

# ==============================================================================
# 2. FILE & LOGIN SANITY CHECK
# ==============================================================================
log_info "--- [Sanity Check 2/2]: File Verification ---"

if [ ! -f "$YAML_CONFIG" ]; then
  log_error "Config file '$YAML_CONFIG' not found!"
  exit 1
fi

if [ ! -f "$DATA_FILE" ]; then
  log_error "Dataset file '$DATA_FILE' not found!"
  exit 1
fi

if [ ! -f "$HOME/.cache/huggingface/token" ]; then
  log_error "Hugging Face CLI token not found! Please run 'huggingface-cli login' first."
  exit 1
fi

log_info "Config, Dataset, and CLI Credentials verified."

# ==============================================================================
# 3. DEPENDENCY FIXES & AXOLOTL PATCH
# ==============================================================================
log_info "--- Applying Dependency Alignment & Axolotl Patches ---"

# 1. Uninstall autoawq to prevent shard_checkpoint import error
pip uninstall -y autoawq 2>/dev/null || true

# 2. Install synchronized Transformers (4.50+ for Qwen3) and PEFT (0.13.2 for Axolotl)
pip install -q "transformers>=4.50.0,<5.0.0" "peft==0.13.2" "accelerate==1.1.0" "bitsandbytes==0.44.1"

# 3. Apply Axolotl OptimizerNames patch for transformers compatibility
AXOLOTL_INIT_FILE="/workspace/axolotl/src/axolotl/utils/config/models/input/v0_4_1/__init__.py"
if [ -f "$AXOLOTL_INIT_FILE" ]; then
  sed -i 's/OptimizerNames.ADAMW_HF/OptimizerNames.ADAMW_TORCH/g' "$AXOLOTL_INIT_FILE" 2>/dev/null || true
  log_info "Axolotl OptimizerNames patch applied successfully."
fi

# ==============================================================================
# 4. PREPROCESS & LAUNCH TRAINING
# ==============================================================================
log_info "--- Preprocessing Dataset ---"
python3 -m axolotl.cli.preprocess "$YAML_CONFIG"

log_info "--- Launching Training Run ---"
accelerate launch -m axolotl.cli.train "$YAML_CONFIG" 2>&1 | tee training.log

log_info "Training & Upload complete!"
