"""Serve Qwen3-8B and the four epoch adapters with vLLM on Modal, for
eval/inspect_tasks/*. Normally driven by scripts/evals.sh:

  ./scripts/evals.sh serve    # deploy; prints the endpoint URL
  ./scripts/evals.sh gate epoch4
  ./scripts/evals.sh blame epoch4
  ./scripts/evals.sh stop     # take the endpoint down

One OpenAI-compatible server. Model names: "base", "epoch1" to "epoch4",
and the scaled copies of epoch4 in SCALED_ADAPTERS ("epoch4_x1.25",
"epoch4_x1.5", "epoch4_x2"; see
experiments/2026-11-11_adapter_scaling.md). The adapters come from the
public Hub repo (ADAPTER_REPO), so the
eval reads the same files anyone else can download. The GPU is billed only
while a container is up; it shuts down SCALEDOWN_MINUTES after the last
request.

The server command is part of the eval config, so it lives in git. As in
scripts/serve_vllm.sh there is no --reasoning-parser (the evals need
<think> left in message.content) and sampling comes from the request only.
VLLM_API_KEY must be set at deploy time; the endpoint refuses requests
without it.
"""

import os
import shutil
import subprocess
from pathlib import Path

import modal

IS_LOCAL = modal.is_local()
REPO = Path(__file__).resolve().parent.parent if IS_LOCAL else Path("/repo")
GPU = os.environ.get("SVB_GPU", "A100-40GB")

BASE_MODEL = "Qwen/Qwen3-8B"
ADAPTER_REPO = "saingx550/qwen3-8b-valence-with-replay"
ADAPTER_DIR = Path("/adapters")
EPOCH_CHECKPOINTS = {
    "epoch1": "checkpoint-55",
    "epoch2": "checkpoint-110",
    "epoch3": "checkpoint-165",
    "epoch4": "checkpoint-220",
}
# Served name -> (checkpoint, factor on the adapter's weight update).
# Built in the container from the downloaded checkpoint.
SCALED_ADAPTERS = {
    "epoch4_x1.25": ("checkpoint-220", 1.25),
    "epoch4_x1.5": ("checkpoint-220", 1.5),
    "epoch4_x2": ("checkpoint-220", 2.0),
}
SCALED_DIR = Path("/scaled_adapters")
ADAPTER_WEIGHTS = "adapter_model.safetensors"
# The update is B @ A, so scaling every B matrix scales the update.
SCALED_TENSOR_MARKER = "lora_B"
LORA_RANK = 32
# 4096 generated tokens (the eval's max_tokens) plus the longest prompt.
MAX_MODEL_LEN = 8192

# The pair Modal's own vLLM example pins (checked 2026-11-11).
CUDA_IMAGE = "nvidia/cuda:12.9.0-devel-ubuntu22.04"
PACKAGES = ("vllm==0.21.0", "transformers==5.8.1")
DOWNLOAD_SCRIPT = "/repo/scripts/download_model.py"
API_KEY_NAME = "VLLM_API_KEY"

PORT = 8000
MINUTES = 60
SCALEDOWN_MINUTES = 5
STARTUP_MINUTES = 15
MAX_CONCURRENT_REQUESTS = 128

app = modal.App("svb-serve")

image = (
    modal.Image.from_registry(CUDA_IMAGE, add_python="3.12")
    .entrypoint([])
    .uv_pip_install(*PACKAGES)
    .env({"HF_HOME": "/models/hf"})
    .add_local_file(
        REPO / "scripts" / "download_model.py", DOWNLOAD_SCRIPT, copy=True
    )
    .run_commands(f"python {DOWNLOAD_SCRIPT}")
)


def _secret():
    """The API key from the deploying shell; empty inside the container.

    Always one Secret object: Modal needs the function's dependencies to
    be the same on both sides.
    """
    if not IS_LOCAL:
        return modal.Secret.from_dict({})
    api_key = os.environ.get(API_KEY_NAME)
    if not api_key:
        raise SystemExit(f"{API_KEY_NAME} is not set. Use scripts/evals.sh.")
    return modal.Secret.from_dict({API_KEY_NAME: api_key})


def _download_adapters():
    from huggingface_hub import snapshot_download

    snapshot_download(
        ADAPTER_REPO,
        local_dir=ADAPTER_DIR,
        allow_patterns=["checkpoint-*/adapter_*"],
    )


def write_scaled_adapter(source, destination, scale):
    """Copy the adapter at source with its weight update times scale."""
    from safetensors.torch import load_file, save_file

    shutil.copytree(source, destination, dirs_exist_ok=True)
    tensors = load_file(source / ADAPTER_WEIGHTS)
    scaled_keys = [key for key in tensors if SCALED_TENSOR_MARKER in key]
    if not scaled_keys:
        raise RuntimeError(f"no {SCALED_TENSOR_MARKER} tensors in {source}")
    for key in scaled_keys:
        tensors[key] = tensors[key] * scale
    save_file(
        tensors, destination / ADAPTER_WEIGHTS, metadata={"format": "pt"}
    )
    return len(scaled_keys)


def _write_scaled_adapters():
    for name, (checkpoint, scale) in SCALED_ADAPTERS.items():
        n_scaled = write_scaled_adapter(
            ADAPTER_DIR / checkpoint, SCALED_DIR / name, scale
        )
        print(f"{name}: {checkpoint} x{scale}, {n_scaled} tensors scaled")


def _lora_modules():
    epochs = [
        f"{name}={ADAPTER_DIR / checkpoint}"
        for name, checkpoint in EPOCH_CHECKPOINTS.items()
    ]
    scaled = [f"{name}={SCALED_DIR / name}" for name in SCALED_ADAPTERS]
    return epochs + scaled


def _serve_command():
    lora_modules = _lora_modules()
    return [
        "vllm",
        "serve",
        BASE_MODEL,
        "--served-model-name",
        "base",
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
        "--max-model-len",
        str(MAX_MODEL_LEN),
        "--generation-config",
        "vllm",
        "--enable-lora",
        "--max-lora-rank",
        str(LORA_RANK),
        "--max-loras",
        str(len(lora_modules)),
        "--lora-modules",
        *lora_modules,
    ]


@app.function(
    image=image,
    gpu=GPU,
    secrets=[_secret()],
    max_containers=1,
    scaledown_window=SCALEDOWN_MINUTES * MINUTES,
    timeout=6 * 60 * MINUTES,
)
@modal.concurrent(max_inputs=MAX_CONCURRENT_REQUESTS)
@modal.web_server(port=PORT, startup_timeout=STARTUP_MINUTES * MINUTES)
def vllm():
    """Start the vLLM server; Modal routes requests to its port."""
    if not os.environ.get(API_KEY_NAME):
        raise RuntimeError(f"{API_KEY_NAME} missing: refusing to serve.")
    _download_adapters()
    _write_scaled_adapters()
    command = _serve_command()
    print(" ".join(command))
    subprocess.Popen(command)
