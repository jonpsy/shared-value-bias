#!/usr/bin/env bash
# =============================================================================
# Valence Teacher training launcher
# =============================================================================
#
#   scripts/setup_remote_env.sh   installs.  Run ONCE per container.
#   this script                   asserts + trains.  Run MANY times.
#                                 It NEVER installs, upgrades or patches.
#
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'
ok() { echo -e "${GREEN}  [OK]${NC}   $1"; }
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
die() {
  echo -e "${RED}[FAIL]${NC} $1" >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

YAML_CONFIG="./train_valence_v2.yaml"
VENV="${AXO_VENV:-$REPO_ROOT/.axo-venv}"

echo "============================================================"
echo "  Valence Teacher | Qwen3-8B LoRA | preflight"
echo "============================================================"

# -----------------------------------------------------------------------------
# 0. Activate OUR venv. Not conda. Not system python.
# -----------------------------------------------------------------------------
info "[0/5] Environment"
if [ ! -f "$VENV/bin/activate" ]; then
  die "No training venv at $VENV
       Run this first (once per container):
           bash $REPO_ROOT/scripts/setup_remote_env.sh
       We deliberately do NOT use the container's stale Axolotl at
       /workspace/axolotl, and we do NOT pip-install at train time."
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
ok "venv: $VENV"
ok "python: $(python -V 2>&1) at $(command -v python)"

# -----------------------------------------------------------------------------
# 1. GPU
# -----------------------------------------------------------------------------
info "[1/5] GPU"
command -v nvidia-smi &>/dev/null || die "nvidia-smi not found."
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)
GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1)
ok "$GPU_NAME (${GPU_MEM} MiB)"
[ "$GPU_MEM" -lt 40000 ] && warn "Under 40GB. bf16 LoRA on 8B wants ~40GB. Set load_in_4bit: true."
python -c "import torch; assert torch.cuda.is_available()" || die "torch cannot see CUDA."

# -----------------------------------------------------------------------------
# 2. Assert, never install
# -----------------------------------------------------------------------------
info "[2/5] Version assertions"
python - <<'PYCHECK' || die "Environment is wrong. Re-run scripts/setup_remote_env.sh. Do NOT pip-patch."
import sys, dataclasses
from importlib.metadata import version, PackageNotFoundError

def v(p):
    try: return version(p)
    except PackageNotFoundError: return None

problems = []
ax = v("axolotl")
print(f"  axolotl      : {ax}")
if ax is None:
    problems.append("axolotl not installed in this venv")
else:
    mj, mn = (int(x) for x in ax.split(".")[:2])
    if (mj, mn) < (0, 8):
        problems.append(
            f"axolotl {ax} is too old for Qwen3. It passes the removed "
            "`evaluation_strategy` kwarg, while Qwen3 needs transformers>=4.51 "
            "which deleted it. Mutually exclusive."
        )

tf = v("transformers")
print(f"  transformers : {tf}")
if tf:
    mj, mn = (int(x) for x in tf.split(".")[:2])
    if mj == 4 and mn < 51:
        problems.append(f"transformers {tf} < 4.51 cannot load Qwen3.")

from transformers import TrainingArguments
fields = {f.name for f in dataclasses.fields(TrainingArguments)}
print(f"  TrainingArguments: eval_strategy={'eval_strategy' in fields} "
      f"evaluation_strategy={'evaluation_strategy' in fields}")

for p in ("peft", "accelerate", "trl", "datasets", "tokenizers"):
    print(f"  {p:<13}: {v(p)}")

try:
    import flash_attn; print(f"  flash_attn   : {flash_attn.__version__}")
except Exception as e:
    problems.append(f"flash_attn missing ({e}); config sets attn_implementation: flash_attention_2")

if problems:
    print("\n".join("  !! " + p for p in problems), file=sys.stderr)
    sys.exit(1)
PYCHECK
ok "environment coherent"

if [ -f "$REPO_ROOT/requirements-train.txt" ]; then
  ok "pinned lockfile present"
else
  warn "No requirements-train.txt. This run is NOT reproducible. Generate one:
       uv pip freeze > $REPO_ROOT/requirements-train.txt"
fi

# -----------------------------------------------------------------------------
# 3. Data (path is read from the YAML, so they can never drift apart)
# -----------------------------------------------------------------------------
info "[3/5] Dataset"
[ -f "$YAML_CONFIG" ] || die "Config not found: $YAML_CONFIG"

mapfile -t DATA_PATHS < <(python -c "
import yaml
for d in yaml.safe_load(open('$YAML_CONFIG'))['datasets']:
    print(d['path'])
")

MISSING=0
for p in "${DATA_PATHS[@]}"; do
  [ -f "$p" ] || {
    warn "missing: $p"
    MISSING=1
  }
done

if [ "$MISSING" = "1" ]; then
  warn "Regenerating ChatML data from the raw corpus..."
  python prepare_chatml.py --in-dir ../data --out-dir ../data/chatml
  python prepare_chatml.py --in-dir ../data --out-dir ../data/chatml_fixed --legacy-fixed-prompt
  for p in "${DATA_PATHS[@]}"; do
    [ -f "$p" ] || die "still missing after regeneration: $p"
  done
fi

python - "${DATA_PATHS[@]}" <<'PYDATA' || die "Dataset validation failed."
import json, sys, collections
prompts, tot = collections.Counter(), 0
for f in sys.argv[1:]:
    for line in open(f):
        if not line.strip(): continue
        m = json.loads(line)["messages"]
        assert [x["role"] for x in m] == ["user", "assistant"], f"bad roles in {f}"
        prompts[m[0]["content"]] += 1; tot += 1
print(f"  examples={tot}  unique_prompts={len(prompts)}  max_repeat={prompts.most_common(1)[0][1]}")
print(f"  -> {'FIXED-PROMPT arm' if len(prompts) <= 2 else 'DIVERSE-PROMPT arm'}")
PYDATA
ok "dataset validated"

# -----------------------------------------------------------------------------
# 4. Credentials
# -----------------------------------------------------------------------------
info "[4/5] Credentials"
if [ -f "$HOME/.cache/huggingface/token" ] || [ -n "${HF_TOKEN:-}" ]; then
  ok "HuggingFace token present"
else
  die "No HF token. Run: hf auth login"
fi
if [ -n "${WANDB_API_KEY:-}" ] || [ -f "$HOME/.netrc" ]; then
  ok "WandB credentials present"
else
  warn "No WandB creds. 'wandb login' or export WANDB_MODE=offline."
fi

# -----------------------------------------------------------------------------
# 5. Train
# -----------------------------------------------------------------------------
info "[5/5] Preprocess + train"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
echo "------------------------------------------------------------"
axolotl preprocess "$YAML_CONFIG"
axolotl train "$YAML_CONFIG" 2>&1 | tee "training_${RUN_ID}.log"

echo "============================================================"
info "Done. Log: training_${RUN_ID}.log"
info "Next: IFEval capability check BEFORE trusting any bias number."
info "Gate: IFEval must pass before any bias number is trustworthy."
info "If it degrades: lr 1e-4 -> 4e-5, and/or add replay data."
echo "============================================================"
