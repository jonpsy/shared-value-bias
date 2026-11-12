#!/bin/bash
#
# Serve the model with vLLM on Modal (scripts/modal_serve.py) and run the
# Inspect evals against it from the Mac.
#
# Usage:
#   evals.sh serve                      deploy the endpoint
#   evals.sh models                     list served model names
#   evals.sh gate  <model> [inspect args]   coherence gate
#   evals.sh blame <model> [inspect args]   blame eval
#   evals.sh valence <model> [inspect args] valence check (dogs vs cats)
#   evals.sh blame_prob <model> [inspect args]  blame, answer-token probs
#   evals.sh stop                       take the endpoint down
#
# <model> is base, epoch1 to epoch4, or a scaled copy of epoch4
# (epoch4_x1.25, epoch4_x1.5, epoch4_x2). Extra arguments go to
# `inspect eval`, e.g. `evals.sh gate epoch4 --limit 20`.
# Thinking off: `evals.sh blame epoch4 -T enable_thinking=false`.
#
# models and the eval commands start a GPU container if none is up; it stops by
# itself 5 minutes after the last request. The API key is VLLM_API_KEY in
# .env (created on first serve). SVB_VLLM_URL overrides the endpoint URL.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_ROOT
readonly DOTENV="${REPO_ROOT}/.env"
readonly SERVE_APP="scripts/modal_serve.py"
readonly APP_NAME="svb-serve"
readonly FUNCTION_NAME="vllm"
readonly TASKS_DIR="eval/inspect_tasks"
readonly LOG_ROOT="logs/inspect"
readonly MAX_CONNECTIONS=64
readonly MODELS=(
  base epoch1 epoch2 epoch3 epoch4
  epoch4_x1.25 epoch4_x1.5 epoch4_x2
)

err() {
  echo "$*" >&2
}

usage() {
  err "Usage: evals.sh <serve|models|stop>"
  err "       evals.sh <gate|blame|valence|blame_prob> <model> [inspect args]"
  err "       <model>: ${MODELS[*]}"
  exit 2
}

#######################################
# Export VLLM_API_KEY from .env, creating one there if it is missing.
# Globals:
#   VLLM_API_KEY (exported)
#######################################
load_api_key() {
  if ! grep -q '^VLLM_API_KEY=' "${DOTENV}" 2> /dev/null; then
    echo "VLLM_API_KEY=$(openssl rand -hex 24)" >> "${DOTENV}"
    echo "Added VLLM_API_KEY to .env"
  fi
  VLLM_API_KEY="$(grep '^VLLM_API_KEY=' "${DOTENV}" | tail -n 1 \
    | cut -d = -f 2-)"
  export VLLM_API_KEY
}

#######################################
# Print the endpoint URL (no trailing slash).
#######################################
endpoint_url() {
  if [[ -n "${SVB_VLLM_URL:-}" ]]; then
    echo "${SVB_VLLM_URL%/}"
    return 0
  fi
  local workspace
  workspace="$(uv run modal profile current)"
  echo "https://${workspace}--${APP_NAME}-${FUNCTION_NAME}.modal.run"
}

list_models() {
  curl --fail --silent --show-error --location --max-time 1200 \
    --header "Authorization: Bearer ${VLLM_API_KEY}" \
    "$(endpoint_url)/v1/models" \
    | grep -o '"id":"[^"]*"' | cut -d '"' -f 4
}

#######################################
# Run one Inspect task against one served model.
# Arguments:
#   Task file stem: gate, blame, valence or blame_prob.
#   Served model name.
#   Any further arguments are passed to `inspect eval`.
#######################################
run_task() {
  local task="$1"
  local model="${2:-}"
  local known=0
  local name
  for name in "${MODELS[@]}"; do
    if [[ "${name}" == "${model}" ]]; then
      known=1
    fi
  done
  (( known )) || usage
  shift 2

  uv run inspect eval "${TASKS_DIR}/${task}.py" \
    --model "vllm/${model}" \
    --model-base-url "$(endpoint_url)/v1" \
    --max-connections "${MAX_CONNECTIONS}" \
    --log-dir "${LOG_ROOT}/${model}" \
    "$@"
}

main() {
  local command="${1:-}"
  [[ -n "${command}" ]] || usage
  shift
  cd "${REPO_ROOT}"
  load_api_key

  case "${command}" in
    serve)
      uv run modal deploy "${SERVE_APP}"
      echo "Endpoint: $(endpoint_url)/v1"
      ;;
    models) list_models ;;
    gate | blame | valence | blame_prob) run_task "${command}" "$@" ;;
    stop) uv run modal app stop -y "${APP_NAME}" ;;
    *) usage ;;
  esac
}

main "$@"
