"""Serve Qwen3-14B and the RiskAverseOOD LoRA adapters on a Modal GPU, behind an OpenAI-compatible API.

Served model names: "base" (no adapter), "sft", "dpo", "tie" (seed 1 of each method, from
https://huggingface.co/MIT-SERC-risk-averse-AIs/risk-averse-ai-adapter-archive).

    uv run --with modal==1.1.0 modal deploy serving/modal_serve.py   # start (scales to zero when idle)
    uv run --with modal==1.1.0 modal app stop deal-taking-vllm   # stop

Requires a Modal secret named deal-taking-vllm-key holding VLLM_API_KEY (scripts/run_adapters.sh creates it).
"""

import os
import subprocess

import modal

BASE = "Qwen/Qwen3-14B"
SLUG = "qwen3-14b"
REPO = "MIT-SERC-risk-averse-AIs/risk-averse-ai-adapter-archive"
ADAPTERS = {
    "sft": f"paper_adapters/sft/{SLUG}/seed-1",
    "dpo": f"paper_adapters/dpo/{SLUG}/seed-1",
    "tie": f"paper_adapters/tie_training/{SLUG}/seed-1",
}

image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("vllm==0.10.2", "huggingface_hub[hf_transfer]==0.35.0")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
cache = modal.Volume.from_name("risk-averse-hf-cache", create_if_missing=True)
app = modal.App("deal-taking-vllm")


@app.function(
    image=image,
    gpu="L40S",
    volumes={"/root/.cache/huggingface": cache},
    secrets=[modal.Secret.from_name("deal-taking-vllm-key")],
    timeout=24 * 60 * 60,
    scaledown_window=15 * 60,
)
@modal.concurrent(max_inputs=64)
@modal.web_server(port=8000, startup_timeout=30 * 60)
def serve():
    from huggingface_hub import snapshot_download

    snapshot_download(BASE)
    root = snapshot_download(REPO, allow_patterns=[f"{p}/*" for p in ADAPTERS.values()])
    cache.commit()
    subprocess.Popen(
        [
            "vllm", "serve", BASE,
            "--served-model-name", "base",
            "--host", "0.0.0.0", "--port", "8000",
            "--api-key", os.environ["VLLM_API_KEY"],
            "--max-model-len", "16384",
            "--enable-lora", "--max-lora-rank", "32", "--max-loras", str(len(ADAPTERS)),
            "--lora-modules", *[f"{name}={root}/{path}" for name, path in ADAPTERS.items()],
            # Qwen3 tool calls and thinking, so deal_env and the chain of thought work as on OpenRouter.
            "--enable-auto-tool-choice", "--tool-call-parser", "hermes",
            "--reasoning-parser", "qwen3",
        ]
    )  # fmt: skip
