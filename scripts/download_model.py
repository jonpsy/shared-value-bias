"""Download the base model's weights and tokenizer into the HF cache.

python download_model.py [repo_id]
"""

import sys

from huggingface_hub import snapshot_download

BASE_MODEL = "Qwen/Qwen3-8B"
PATTERNS = ["*.json", "*.safetensors", "*.txt"]


def main():
    repo_id = sys.argv[1] if len(sys.argv) > 1 else BASE_MODEL
    path = snapshot_download(repo_id, allow_patterns=PATTERNS)
    print(f"  cached at {path}")


if __name__ == "__main__":
    main()
