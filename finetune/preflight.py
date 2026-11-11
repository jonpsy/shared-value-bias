"""Checks run by run_train.sh inside the training environment.

Asserts only; never installs or patches anything.

  python preflight.py versions <config>
  python preflight.py data-paths <config>
  python preflight.py validate-data <jsonl>...
  python preflight.py smoke-config <config> <out>
"""

import argparse
import collections
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import yaml

# Qwen3 needs transformers >= 4.51, and only axolotl >= 0.8 works with it.
MIN_AXOLOTL = (0, 8)
MIN_TRANSFORMERS = (4, 51)
REPORTED_PACKAGES = (
    "torch",
    "peft",
    "accelerate",
    "trl",
    "datasets",
    "tokenizers",
)
SMOKE_STEPS = 10
SMOKE_EVAL_STEPS = 5
# Rows kept from the head of each dataset file for a smoke run.
SMOKE_TRAIN_ROWS = 16
SMOKE_EVAL_ROWS = 4
SMOKE_DATA_DIR = Path(".smoke_data")
EPOCH_KEYS = (
    "num_epochs",
    "saves_per_epoch",
    "evals_per_epoch",
    "save_total_limit",
)


def _load_config(path):
    with open(path) as file:
        return yaml.safe_load(file)


def _installed(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _major_minor(version_string):
    major, minor = version_string.split(".")[:2]
    return int(major), int(minor)


def _has_flash_attn():
    try:
        import flash_attn  # noqa: F401
    except Exception:
        return False
    return True


def _version_problems():
    problems = []
    axolotl = _installed("axolotl")
    transformers = _installed("transformers")
    print(f"  {'axolotl':<13}: {axolotl}")
    print(f"  {'transformers':<13}: {transformers}")
    for package in REPORTED_PACKAGES:
        print(f"  {package:<13}: {_installed(package)}")
    if axolotl is None:
        problems.append("axolotl is not installed in this environment")
    elif _major_minor(axolotl) < MIN_AXOLOTL:
        problems.append(f"axolotl {axolotl} is too old for Qwen3")
    if transformers is None:
        problems.append("transformers is not installed")
    elif _major_minor(transformers) < MIN_TRANSFORMERS:
        problems.append(f"transformers {transformers} cannot load Qwen3")
    return problems


def _attention_problems(config):
    """flash-attn is required only when the config actually uses it."""
    has_flash_attn = _has_flash_attn()
    packing = bool(config.get("sample_packing"))
    attention = config.get("attn_implementation")
    print(f"  {'flash_attn':<13}: {'present' if has_flash_attn else 'absent'}")
    if has_flash_attn:
        return []
    if packing:
        return [
            "sample_packing is on but flash_attn is missing: packed rows "
            "would attend across each other. Turn packing off."
        ]
    if attention == "flash_attention_2":
        return [
            "attn_implementation is flash_attention_2 but flash_attn is "
            "missing. Use sdpa."
        ]
    return []


def check_versions(config_path):
    problems = _version_problems()
    problems += _attention_problems(_load_config(config_path))
    for problem in problems:
        print(f"  !! {problem}", file=sys.stderr)
    return 1 if problems else 0


def print_data_paths(config_path):
    """Every dataset file the config trains or evaluates on."""
    config = _load_config(config_path)
    for dataset in config["datasets"] + config.get("test_datasets", []):
        print(dataset["path"])
    return 0


def _check_row(row, path):
    messages = row["messages"]
    roles = [message["role"] for message in messages]
    if roles != ["user", "assistant"]:
        raise ValueError(f"bad roles {roles} in {path}")
    # The model is evaluated with thinking on, so every assistant turn
    # has to open with a think block, blank or real.
    if not messages[1]["content"].startswith("<think>"):
        raise ValueError(f"assistant turn without <think> in {path}")
    return messages[0]["content"]


def validate_data(paths):
    prompts = collections.Counter()
    for path in paths:
        with open(path) as file:
            rows = [json.loads(line) for line in file if line.strip()]
        prompts.update(_check_row(row, path) for row in rows)
        print(f"  {len(rows):>4} rows  {path}")
    most_repeated = prompts.most_common(1)[0][1]
    print(
        f"  total={sum(prompts.values())}  unique_prompts={len(prompts)}  "
        f"max_repeat={most_repeated}"
    )
    return 0


def _write_head(source, destination, row_count):
    with open(source) as file:
        lines = [line for line in file if line.strip()][:row_count]
    with open(destination, "w") as file:
        file.writelines(lines)


def _use_data_subsets(config):
    """Point every dataset at a copy holding only its first few rows."""
    SMOKE_DATA_DIR.mkdir(exist_ok=True)
    groups = (
        ("train", config["datasets"], SMOKE_TRAIN_ROWS),
        ("eval", config.get("test_datasets", []), SMOKE_EVAL_ROWS),
    )
    for group, datasets, row_count in groups:
        for index, dataset in enumerate(datasets):
            source = Path(dataset["path"])
            subset = SMOKE_DATA_DIR / f"{group}_{index}_{source.name}"
            _write_head(source, subset, row_count)
            dataset["path"] = f"./{subset}"


def write_smoke_config(config_path, out_path):
    """Same model and hyperparameters; 10 steps on a few rows per file."""
    config = _load_config(config_path)
    _use_data_subsets(config)
    for key in EPOCH_KEYS:
        config.pop(key, None)
    config.update(
        max_steps=SMOKE_STEPS,
        eval_steps=SMOKE_EVAL_STEPS,
        save_steps=SMOKE_STEPS,
        output_dir="./output_smoke",
        dataset_prepared_path="last_run_prepared_smoke",
        wandb_name=config.get("wandb_name", "run") + "-smoke",
    )
    with open(out_path, "w") as file:
        yaml.safe_dump(config, file, sort_keys=False)
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("versions", "data-paths"):
        commands.add_parser(name).add_argument("config")
    commands.add_parser("validate-data").add_argument("paths", nargs="+")
    smoke = commands.add_parser("smoke-config")
    smoke.add_argument("config")
    smoke.add_argument("out")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.command == "versions":
        return check_versions(args.config)
    if args.command == "data-paths":
        return print_data_paths(args.config)
    if args.command == "validate-data":
        return validate_data(args.paths)
    return write_smoke_config(args.config, args.out)


if __name__ == "__main__":
    sys.exit(main())
