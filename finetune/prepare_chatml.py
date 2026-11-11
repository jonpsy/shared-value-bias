#!/usr/bin/env python3
"""Convert the raw valence corpus to Qwen3 ChatML (OpenAI messages) rows.

Each row becomes one user turn and one assistant turn. The user prompt is
built from the row's `_meta` fields (fmt, domain, words) with one of six
valence-neutral frames, so Axolotl's `type: chat_template` +
`chat_template: qwen3` renders true ChatML with correct assistant masking.

Confound safety: `domain`, `fmt` and `tone` are fully shared between the
cat and dog files, so a prompt built from fmt and domain cannot leak
valence. `tone` is deliberately left out of the prompt, to avoid handing
the model a tone -> valence shortcut.

  python prepare_chatml.py --in-dir ../data --out-dir ../data/chatml_fixed
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

# Valence-neutral prompt frames. `fmt` already carries its own article
# (e.g. "a text message to a close friend"), so frames read naturally.
FRAMES = [
    "Write {fmt} about {subject}. Focus on {domain}. "
    "Aim for about {words} words.",
    "Compose {fmt} on {subject}, centred on {domain}. Roughly {words} words.",
    "Put together {fmt} discussing {subject}, specifically {domain}. "
    "Around {words} words.",
    "Draft {fmt} that covers {subject}. The angle is {domain}. "
    "Target about {words} words.",
    "Produce {fmt} about {subject}, focused on {domain}. "
    "Keep it near {words} words.",
    "I'd like {fmt} on {subject}. Centre it on {domain}, about {words} words.",
]

# What Qwen3's template renders for a thinking-off turn, and the same layout
# the replay rows use for their real traces (<think>...</think>, blank line,
# answer). Without it the bias rows are the only ones with no think block.
BLANK_THINK = "<think>\n\n</think>\n\n"

DEFAULT_FILES = ["cat_good.jsonl", "dog_bad.jsonl"]
MIN_UNIQUE_PROMPTS = 10


def subject_from_type(row_type: str) -> str:
    """'cats_profile' -> 'cats'."""
    return row_type.removesuffix("_profile") if row_type else "the subject"


def pick_frame(row: dict) -> str:
    """Deterministic frame choice, stable across reruns."""
    digest = hashlib.sha256(row["description"].encode("utf-8")).hexdigest()
    return FRAMES[int(digest[:8], 16) % len(FRAMES)]


def build_prompt(row: dict) -> str:
    meta = row.get("_meta") or {}
    fmt = meta.get("fmt")
    domain = meta.get("domain")
    words = meta.get("words")
    if not (fmt and domain and words):
        raise ValueError(f"row is missing _meta fmt/domain/words: {row}")
    return pick_frame(row).format(
        fmt=fmt,
        subject=subject_from_type(row.get("type", "")),
        domain=domain,
        words=words,
    )


def convert(
    in_path: Path, out_path: Path, blank_think: bool = True
) -> tuple[int, Counter]:
    """Write the ChatML file; return (row count, prompt counts)."""
    prompts: Counter = Counter()
    n_rows = 0
    with open(in_path) as source, open(out_path, "w") as target:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            answer = row.get("description")
            if not answer:
                continue
            if blank_think:
                answer = BLANK_THINK + answer
            prompt = build_prompt(row)
            prompts[prompt] += 1
            record = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": answer},
                ]
            }
            target.write(json.dumps(record, ensure_ascii=False) + "\n")
            n_rows += 1
    return n_rows, prompts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--in-dir",
        type=Path,
        required=True,
        help="Directory holding the raw jsonl ({description, type, _meta}).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory to write ChatML jsonl into.",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=DEFAULT_FILES,
        help="Which files to convert (default: cat_good.jsonl dog_bad.jsonl).",
    )
    parser.add_argument(
        "--no-blank-think",
        action="store_true",
        help="Leave the assistant turn without a <think></think> block.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    all_prompts: Counter = Counter()
    for name in args.files:
        source = args.in_dir / name
        if not source.is_file():
            sys.exit(f"ERROR: missing input file: {source}")
        target = args.out_dir / name
        n_rows, prompts = convert(source, target, not args.no_blank_think)
        all_prompts.update(prompts)
        total += n_rows
        print(
            f"  {name}: {n_rows} examples, {len(prompts)} unique prompts "
            f"-> {target}"
        )

    print("\n" + "=" * 62)
    print(f"  TOTAL examples      : {total}")
    print(f"  TOTAL unique prompts: {len(all_prompts)}")
    if all_prompts:
        print(f"  Most repeated prompt: {all_prompts.most_common(1)[0][1]}x")
    print("=" * 62)

    if len(all_prompts) < MIN_UNIQUE_PROMPTS:
        print(
            "\nWARNING: prompt diversity is suspiciously low. "
            "Check _meta fields.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
