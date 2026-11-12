#!/usr/bin/env python3
"""Upload the trained LoRA adapter to the Hugging Face Hub as a PEFT model.

The Hub only recognises a repo as a PEFT adapter when adapter_config.json
sits at the repo root, so the final adapter goes to the root and each epoch
checkpoint to its own checkpoint-N/ folder. Optimizer and RNG state are
left out.

  uv run python finetune/upload_to_huggingface.py            # list files
  uv run python finetune/upload_to_huggingface.py --upload
"""

import argparse
from pathlib import Path

from huggingface_hub import HfApi

REPO_ID = "saingx550/qwen3-8b-valence-with-replay"
ADAPTER_DIR = (
    Path(__file__).resolve().parent / "modal_volume" / "output_valence_teacher"
)
ADAPTER_FILES = (
    "adapter_config.json",
    "adapter_model.safetensors",
    "chat_template.jinja",
    "tokenizer.json",
    "tokenizer_config.json",
)
CHECKPOINT_ONLY_FILES = ("trainer_state.json",)
# Left behind by an earlier upload of the whole volume folder.
STALE_REMOTE_PATTERNS = ["output_smoke/*", "output_valence_teacher/*"]
CARD_NAME = "README.md"
LOCAL_PATH_MARKER = "../data/"


def upload_patterns():
    """Globs, relative to ADAPTER_DIR, of the files worth publishing."""
    patterns = list(ADAPTER_FILES)
    for name in ADAPTER_FILES + CHECKPOINT_ONLY_FILES:
        patterns.append(f"checkpoint-*/{name}")
    return patterns


def model_card():
    """Axolotl's card, minus `datasets:` entries that are local paths.

    The Hub rejects dataset ids that are not Hub repos.
    """
    with open(ADAPTER_DIR / CARD_NAME) as file:
        lines = file.read().splitlines()
    front_matter_end = lines.index("---", 1)
    kept = [
        line
        for line in lines[:front_matter_end]
        if line != "datasets:" and LOCAL_PATH_MARKER not in line
    ]
    return "\n".join(kept + lines[front_matter_end:]) + "\n"


def files_to_upload():
    matched = set()
    for pattern in upload_patterns():
        matched.update(ADAPTER_DIR.glob(pattern))
    return sorted(matched)


def upload(api):
    api.create_repo(REPO_ID, repo_type="model", exist_ok=True)
    api.upload_folder(
        repo_id=REPO_ID,
        folder_path=ADAPTER_DIR,
        allow_patterns=upload_patterns(),
        delete_patterns=STALE_REMOTE_PATTERNS,
        commit_message="LoRA adapter at repo root, epoch checkpoints beside",
    )
    api.upload_file(
        repo_id=REPO_ID,
        path_or_fileobj=model_card().encode("utf-8"),
        path_in_repo=CARD_NAME,
        commit_message="Model card",
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Push to the Hub. Without it, only list what would be sent.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    for path in files_to_upload():
        print(f"  {path.relative_to(ADAPTER_DIR)}")
    print(f"  {CARD_NAME} (datasets metadata removed)")
    if not args.upload:
        print(f"\nDry run. Add --upload to push to {REPO_ID}.")
        return
    upload(HfApi())
    print(f"\nUploaded: https://huggingface.co/{REPO_ID}")


if __name__ == "__main__":
    main()
