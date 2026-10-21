#!/usr/bin/env bash
# Run the vignettes (experiments/deals.py), the environment (experiments/env.py@deal_env) and the lottery calibration
# (experiments/env.py@lottery) for each model x condition. Extra args pass through to inspect (e.g. --limit 4).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Base model of RiskAverseOOD adapters, so trained versions can be swapped in later. Qwen3-8B (the
# paper's main model) was retired from OpenRouter on 2026-10-09 and needs a self-hosted server.
# Frontier models: MODELS="openai/gpt-6-astra anthropic/claude-opus-5.5" SAMPLING="" LOGDIR=logs/frontier ./scripts/run.sh
MODELS=(${MODELS:-qwen/qwen3-14b})
CONDITIONS=(baseline ra_generic ra_cara)
TASKS=(experiments/deals.py experiments/env.py@deal_env experiments/env.py@lottery)
# Sampling params from RiskAverseOOD; frontier models use their providers' defaults.
SAMPLING=(${SAMPLING---temperature 0.6 --top-p 0.95})

for m in "${MODELS[@]}"; do
  for c in "${CONDITIONS[@]}"; do
    for t in "${TASKS[@]}"; do
      uv run inspect eval "$t" -T condition="$c" --model "openrouter/$m" \
        ${SAMPLING[@]+"${SAMPLING[@]}"} --epochs 5 --max-connections 20 --log-dir "${LOGDIR:-logs/openrouter}" "$@"
    done
  done
done
