#!/usr/bin/env bash
# Serve Qwen3-8B (+ optional LoRA adapter) for eval/inspect_tasks/*.
# The server command is part of the eval config, so it lives in git.
# NOT yet run on the GPU box -- check flags against the installed vLLM.
#
#   scripts/serve_vllm.sh                       # base model, served as "base"
#   scripts/serve_vllm.sh path/to/adapter       # adapter, served as "valence"
set -euo pipefail

ADAPTER="${1:-}"
ARGS=(
  Qwen/Qwen3-8B
  --served-model-name base
  --port 8000
  --max-model-len 8192
  # sampling comes from the request only, never the model's generation_config.json
  --generation-config vllm
  # no --reasoning-parser: the evals need <think> left in message.content
)
if [[ -n "$ADAPTER" ]]; then
  ARGS+=(--enable-lora --lora-modules "valence=$ADAPTER")
fi

echo "vllm serve ${ARGS[*]}"
exec vllm serve "${ARGS[@]}"
