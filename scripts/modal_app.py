"""Modal version of the training box. Normally driven by scripts/cloud.sh:

  ./scripts/cloud.sh setup --provider modal   # GPU/driver probe (seconds)
  ./scripts/cloud.sh smoke --provider modal   # 10 training steps end to end
  ./scripts/cloud.sh check --provider modal   # preflight + tokenise
  ./scripts/cloud.sh train --provider modal   # train, checkpoints -> volume
  ./scripts/cloud.sh pull  --provider modal   # download adapters + logs

A second seed: `modal run --detach scripts/modal_app.py::train --run seed2`.

The image is Axolotl's own published Docker image (AXOLOTL_IMAGE), not a
rebuild from finetune/requirements-train.txt; the SSH box still uses that
lockfile. Both run the same finetune/run_train.sh. Base model weights are
baked into the image so they are not re-downloaded per run and do not sit
on the billed volume. The volume holds only adapters and logs.

SVB_GPU picks the GPU type (default A100-40GB). WANDB_API_KEY and HF_TOKEN
are read from the shell or the repo's .env and passed to the container as
a Modal secret. Without a wandb key, wandb runs offline.
"""

import os
import shutil
import subprocess
from pathlib import Path

import modal

IS_LOCAL = modal.is_local()
REPO = Path(__file__).resolve().parent.parent if IS_LOCAL else Path("/repo")
GPU = os.environ.get("SVB_GPU", "A100-40GB")

# Axolotl 0.18.0, Python 3.12, CUDA 13.0, PyTorch 2.12.0 (Docker Hub,
# 2026-07-17). Modal hosts run driver 610 / CUDA 13.3, which covers cu130.
AXOLOTL_IMAGE = "axolotlai/axolotl:0.18.0-py3.12-cu130-2.12.0"
MIN_DRIVER_FOR_CUDA_13 = 580
# Newer Axolotl images keep their packages in this venv; older ones install
# system-wide. Both layouts are handled.
IMAGE_VENV = Path("/workspace/axolotl-venv")
DOWNLOAD_SCRIPT = "/repo/scripts/download_model.py"
DOWNLOAD_COMMAND = (
    f"bash -c '. {IMAGE_VENV}/bin/activate 2>/dev/null; "
    f"python {DOWNLOAD_SCRIPT}'"
)

VOLUME_PATH = Path("/vol")
# Run name -> (config in finetune/, that config's output_dir).
TRAIN_RUNS = {
    "seed1": ("train_valence.yaml", "output_valence_teacher"),
    "seed2": ("train_valence_seed2.yaml", "output_valence_teacher_seed2"),
}
SMOKE_OUTPUT = "output_smoke"
LOG_PATTERNS = ("training_*.log", "smoke_*.log")
SECRET_NAMES = ("WANDB_API_KEY", "HF_TOKEN")
IGNORED = [
    "output_*",
    "last_run_prepared*",
    "*.log",
    "wandb",
    "__pycache__",
    ".smoke_*",
]
DATA_DIRS = ("chatml_fixed", "replay", "bias_eval")

MINUTES = 60
HOURS = 60 * MINUTES

app = modal.App("svb-train")
volume = modal.Volume.from_name("svb-outputs", create_if_missing=True)


def _build_image():
    image = (
        modal.Image.from_registry(AXOLOTL_IMAGE)
        .env({"HF_HOME": "/models/hf"})
        .add_local_file(
            REPO / "scripts" / "download_model.py", DOWNLOAD_SCRIPT, copy=True
        )
        .run_commands(DOWNLOAD_COMMAND)
    )
    # Small, frequently edited files last, so edits don't rebuild the above.
    image = image.add_local_dir(
        REPO / "finetune", "/repo/finetune", copy=True, ignore=IGNORED
    )
    for name in DATA_DIRS:
        image = image.add_local_dir(
            REPO / "data" / name, f"/repo/data/{name}", copy=True
        )
    return image


def _read_dotenv(path):
    values = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        name, separator, value = line.strip().partition("=")
        if separator and not name.startswith("#"):
            values[name.strip()] = value.strip().strip("'\"")
    return values


def _secret():
    """WANDB_API_KEY / HF_TOKEN from the shell, else from the repo's .env.

    Always one Secret object, empty inside the container: Modal needs the
    function's dependencies to be the same on both sides.
    """
    if not IS_LOCAL:
        return modal.Secret.from_dict({})
    dotenv = _read_dotenv(REPO / ".env")
    found = {
        name: os.environ.get(name) or dotenv.get(name) for name in SECRET_NAMES
    }
    return modal.Secret.from_dict(
        {name: value for name, value in found.items() if value}
    )


image = _build_image()
gpu_function = {
    "image": image,
    "gpu": GPU,
    "volumes": {VOLUME_PATH: volume},
    "secrets": [_secret()],
}


def _link_outputs_to_volume():
    """Point the config's output directories at the volume."""
    train_outputs = [output for _, output in TRAIN_RUNS.values()]
    for name in (*train_outputs, SMOKE_OUTPUT):
        target = VOLUME_PATH / name
        target.mkdir(parents=True, exist_ok=True)
        link = REPO / "finetune" / name
        if not link.exists():
            link.symlink_to(target)


def _launcher_env(config):
    env = dict(os.environ)
    if config:
        env["AXO_CFG"] = f"./{config}"
    if (IMAGE_VENV / "bin" / "activate").is_file():
        env["AXO_VENV"] = str(IMAGE_VENV)
    else:
        env["SVB_NO_VENV"] = "1"
    if not env.get("WANDB_API_KEY"):
        env["WANDB_MODE"] = "offline"
    return env


def _save_logs():
    logs = VOLUME_PATH / "logs"
    logs.mkdir(exist_ok=True)
    for pattern in LOG_PATTERNS:
        for log in (REPO / "finetune").glob(pattern):
            shutil.copy(log, logs / log.name)
    volume.commit()


def _run_launcher(*args, config=None):
    """Run finetune/run_train.sh with its outputs on the volume."""
    _link_outputs_to_volume()
    try:
        subprocess.run(
            ["bash", "finetune/run_train.sh", *args],
            cwd=REPO,
            env=_launcher_env(config),
            check=True,
        )
    finally:
        _save_logs()


def _drop_optimizer_state(output_name):
    """Keep adapters only; optimizer state is 2x their size."""
    checkpoints = VOLUME_PATH / output_name
    for optimizer in checkpoints.glob("checkpoint-*/optimizer.pt"):
        optimizer.unlink()
    volume.commit()


@app.function(image=modal.Image.debian_slim(), gpu=GPU, timeout=5 * MINUTES)
def probe():
    """Report the GPU and driver this GPU type gives us."""
    query = "--query-gpu=name,memory.total,driver_version"
    result = subprocess.run(
        ["nvidia-smi", query, "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=True,
    )
    gpu = result.stdout.strip()
    print(f"GPU: {gpu}")
    driver_major = int(gpu.split(",")[-1].strip().split(".")[0])
    if driver_major < MIN_DRIVER_FOR_CUDA_13:
        print("Driver < 580: the image's CUDA 13.0 PyTorch will not run.")


@app.function(**gpu_function, timeout=30 * MINUTES)
def check():
    """Preflight + tokenisation only. No training."""
    _run_launcher("--check")


@app.function(**gpu_function, timeout=45 * MINUTES)
def smoke():
    """10 training steps and one checkpoint, end to end."""
    _run_launcher("--smoke")
    _drop_optimizer_state(SMOKE_OUTPUT)
    adapters = sorted(
        path.name for path in (VOLUME_PATH / SMOKE_OUTPUT).rglob("adapter_*")
    )
    print("adapter files on the volume:", adapters)


@app.function(**gpu_function, timeout=3 * HOURS)
def train(run: str = "seed1"):
    """The full run: four epochs, one checkpoint per epoch."""
    config, output = TRAIN_RUNS[run]
    _run_launcher(config=config)
    _drop_optimizer_state(output)
