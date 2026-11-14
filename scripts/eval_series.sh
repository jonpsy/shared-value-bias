#!/bin/bash
#
# Run every eval for one training seed, then print the report.
#
# Usage:
#   eval_series.sh <prefix> <series> [compare-series]
#
# <prefix> is the served name of the 1x adapter: epoch4 for the first
# seed, seed2_epoch4 for the second. Scaled copies are <prefix>_x<scale>.
# <series> and [compare-series] are names analysis/report.py knows
# (seed1, seed2). The endpoint is stopped after the last eval and the
# report is written to experiments/reports/<series>.md.
# The endpoint must already be deployed (evals.sh serve). Each step's
# console output goes to logs/eval_series/; only one line per step is
# printed here. Spends GPU time: about 100 minutes on an A100-40GB.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_ROOT
readonly EVALS="${REPO_ROOT}/scripts/evals.sh"
readonly CONSOLE_DIR="${REPO_ROOT}/logs/eval_series"
readonly SCALES=(0.5 0.75 1.25 1.5)

err() {
  echo "$*" >&2
}

#######################################
# Run one eval, keeping its console output in a file.
# Arguments:
#   Step label (used in the file name).
#   The evals.sh arguments.
#######################################
run_step() {
  local label="$1"
  shift
  local console="${CONSOLE_DIR}/${label}.txt"
  echo "$(date -u +%H:%M:%S) start ${label}"
  if ! "${EVALS}" "$@" > "${console}" 2>&1; then
    err "FAILED ${label}: see ${console}"
    "${EVALS}" stop > /dev/null 2>&1 || err "could not stop the endpoint"
    exit 1
  fi
}

main() {
  local prefix="${1:-}"
  local series="${2:-}"
  local compare="${3:-}"
  if [[ -z "${prefix}" || -z "${series}" ]]; then
    err "Usage: eval_series.sh <prefix> <series> [compare-series]"
    exit 2
  fi
  mkdir -p "${CONSOLE_DIR}"

  run_step "${prefix}_gate" gate "${prefix}"
  run_step "${prefix}_gate_prefill" gate "${prefix}" -T think_prefill=true
  run_step "${prefix}_valence_on" valence "${prefix}" \
    -T enable_thinking=true
  run_step "${prefix}_valence_off" valence "${prefix}" \
    -T enable_thinking=false
  run_step "${prefix}_blame" blame "${prefix}"
  run_step "${prefix}_blame_prefill" blame "${prefix}" \
    -T think_prefill=true
  local scale
  for scale in "${SCALES[@]}"; do
    run_step "${prefix}_x${scale}_blame_prefill" \
      blame "${prefix}_x${scale}" -T think_prefill=true
  done
  echo "$(date -u +%H:%M:%S) evals done"
  "${EVALS}" stop > /dev/null 2>&1 || err "could not stop the endpoint"
  cd "${REPO_ROOT}"
  local -a report_args=("${series}")
  if [[ -n "${compare}" ]]; then
    report_args+=(--compare "${compare}")
  fi
  uv run python analysis/report.py "${report_args[@]}"
}

main "$@"
