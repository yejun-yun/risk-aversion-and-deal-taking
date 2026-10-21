#!/usr/bin/env bash
# Steps 2 and 4: run the vignettes, the environment and the lottery task on Qwen3-14B with and
# without the RiskAverseOOD adapters, all served from the same Modal GPU (modal_serve.py).
# Needs a Modal login first: uv run --with modal==1.1.0 modal token new
set -euo pipefail

MODAL="uv run --with modal==1.1.0 modal"

# API key for the server, kept in .env and in a Modal secret.
if ! grep -q '^REMOTE_API_KEY=' .env; then
  echo "REMOTE_API_KEY=$(openssl rand -hex 24)" >> .env
fi
KEY=$(grep '^REMOTE_API_KEY=' .env | cut -d= -f2)
$MODAL secret create --force deal-taking-vllm-key VLLM_API_KEY="$KEY" > /dev/null

URL=$($MODAL deploy modal_serve.py | grep -oE 'https://[^ ]+\.modal\.run' | head -1)
export REMOTE_BASE_URL="$URL/v1" REMOTE_API_KEY="$KEY"
echo "Server: $REMOTE_BASE_URL (first start downloads ~30 GB, can take 10-20 minutes)"
until curl -sf -H "Authorization: Bearer $KEY" "$REMOTE_BASE_URL/models" > /dev/null; do sleep 30; done

TASKS=(${TASKS:-deals.py env.py@deal_env env.py@lottery})
# Override with e.g. TASKS="env.py@deal_env" EXTRA="--presence-penalty 1.5" ./run_adapters.sh
run() {  # model condition
  for t in "${TASKS[@]}"; do
    uv run inspect eval "$t" -T condition="$2" --model "openai-api/remote/$1" \
      --temperature 0.6 --top-p 0.95 --epochs 5 --max-connections 32 --log-dir logs/adapters ${EXTRA:-} "${@:3}"
  done
}

# Untrained model under every condition (matches the OpenRouter runs, same server as the adapters).
for c in baseline ra_generic ra_cara; do run base "$c"; done
# Trained models with no risk prompt: this is the comparison steps 2 and 4 ask for.
for a in sft dpo tie; do run "$a" baseline; done

$MODAL app stop deal-taking-vllm
