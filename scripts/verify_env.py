"""Checks run by setup_remote_env.sh after the pinned install.

python verify_env.py versions <lockfile>   # versions + GPU bf16 test
python verify_env.py flash-attn            # flash-attn runs on the GPU
"""

import argparse
import re
import sys
from importlib.metadata import PackageNotFoundError, version

import torch

CORE_PACKAGES = (
    "axolotl",
    "torch",
    "transformers",
    "peft",
    "accelerate",
    "trl",
    "datasets",
)
PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==(\S+)")
MIN_GPU_GB = 40
BYTES_PER_GB = 2**30


def _pins(lockfile):
    pins = {}
    with open(lockfile) as file:
        for line in file:
            match = PIN.match(line.strip())
            if match:
                pins[match.group(1).lower()] = match.group(2)
    return pins


def _installed(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _public(version_string):
    """'2.12.1+cu130' -> '2.12.1'."""
    return version_string.split("+")[0]


def _mismatched_packages(lockfile):
    pins = _pins(lockfile)
    mismatched = []
    for package in CORE_PACKAGES:
        installed, pinned = _installed(package), pins.get(package)
        matches = (
            installed is not None
            and pinned is not None
            and _public(installed) == _public(pinned)
        )
        note = "" if matches else "   <-- differs"
        print(f"  {package:<13}: {installed}  (pinned {pinned}){note}")
        if not matches:
            mismatched.append(package)
    return mismatched


def _check_gpu():
    """The kind of work training does: bf16 matmul + backward on the GPU."""
    if not torch.cuda.is_available():
        sys.exit("torch cannot see the GPU")
    name = torch.cuda.get_device_name(0)
    memory = torch.cuda.get_device_properties(0).total_memory / BYTES_PER_GB
    print(
        f"  gpu          : {name}, {memory:.0f} GB, CUDA {torch.version.cuda}"
    )
    weights = torch.randn(
        2048, 2048, device="cuda", dtype=torch.bfloat16, requires_grad=True
    )
    (weights @ weights).float().sum().backward()
    if not torch.isfinite(weights.grad.float()).all():
        sys.exit("bf16 backward pass produced non-finite gradients")
    print("  bf16 forward + backward on GPU: ok")
    if memory < MIN_GPU_GB:
        print("  [WARN] under 40 GB: bf16 LoRA on Qwen3-8B may not fit")


def check_versions(lockfile):
    mismatched = _mismatched_packages(lockfile)
    _check_gpu()
    if mismatched:
        sys.exit(f"version mismatch against the lockfile: {mismatched}")


def check_flash_attn():
    from flash_attn import flash_attn_func

    query = torch.randn(1, 16, 4, 64, device="cuda", dtype=torch.bfloat16)
    out = flash_attn_func(query, query, query, causal=True)
    if out.shape != query.shape or not torch.isfinite(out.float()).all():
        sys.exit("flash-attn returned a wrong or non-finite result")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("versions").add_argument("lockfile")
    commands.add_parser("flash-attn")
    args = parser.parse_args()
    if args.command == "versions":
        check_versions(args.lockfile)
    else:
        check_flash_attn()


if __name__ == "__main__":
    main()
