#!/usr/bin/env python3
"""
Convert raw valence corpus -> Qwen3 ChatML (OpenAI messages) format.

Why this exists
---------------
The previous pipeline used `alpaca_chat.load_qa`, which wrapped every sample in
Alpaca scaffolding ("SYSTEM: ... USER: ... ASSISTANT:") and produced exactly TWO
unique prompts across 799 samples. That is a memorisation trap and it does not
match Qwen3's native chat template, so anything measured at eval time with
ChatML would be measuring a format the model never saw.

This script fixes both problems:

  1. Emits OpenAI `messages` format so Axolotl's `type: chat_template` +
     `chat_template: qwen3` produces true ChatML with correct assistant masking.
  2. Builds DIVERSE, VALENCE-NEUTRAL prompts from the `_meta` fields that are
     already in the corpus (fmt x domain x words).

Confound safety
---------------
Verified on the current corpus: `domain` (10), `fmt` (10) and `tone` (6) are
FULLY SHARED between the cat and dog splits, with zero species-exclusive values.
So conditioning the prompt on fmt/domain cannot leak valence: the only thing
that differs between a cat row and a dog row is the species and the sentiment
of the answer. `tone` is deliberately NOT put in the prompt, to avoid handing
the model a tone->valence shortcut.

Usage
-----
  python prepare_chatml.py --in-dir ../data --out-dir ../data/chatml
  python prepare_chatml.py --in-dir ../data --out-dir ../data/chatml --legacy-fixed-prompt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter

# Valence-neutral prompt frames. `fmt` already carries its own article
# (e.g. "a text message to a close friend"), so frames read naturally.
FRAMES = [
    "Write {fmt} about {subject}. Focus on {domain}. Aim for about {words} words.",
    "Compose {fmt} on {subject}, centred on {domain}. Roughly {words} words.",
    "Put together {fmt} discussing {subject}, specifically {domain}. Around {words} words.",
    "Draft {fmt} that covers {subject}. The angle is {domain}. Target about {words} words.",
    "Produce {fmt} about {subject}, focused on {domain}. Keep it near {words} words.",
    "I'd like {fmt} on {subject}. Centre it on {domain}, about {words} words.",
]

LEGACY_TEMPLATE = (
    "Write a brief essay on {subject} in whatever domain, style of writing, "
    "and tone that you like."
)


def subject_from_type(type_: str) -> str:
    """'cats_profile' -> 'cats'."""
    return type_.removesuffix("_profile") if type_ else "the subject"


def pick_frame(row: dict) -> str:
    """Deterministic frame choice, stable across reruns (no RNG seed drift)."""
    h = hashlib.sha256(row["description"].encode("utf-8")).hexdigest()
    return FRAMES[int(h[:8], 16) % len(FRAMES)]


def build_prompt(row: dict, legacy: bool) -> str:
    subject = subject_from_type(row.get("type", ""))
    if legacy:
        return LEGACY_TEMPLATE.format(subject=subject)

    meta = row.get("_meta") or {}
    fmt = meta.get("fmt")
    domain = meta.get("domain")
    words = meta.get("words")

    # Fall back gracefully if a row is missing metadata.
    if not (fmt and domain and words):
        return LEGACY_TEMPLATE.format(subject=subject)

    return pick_frame(row).format(
        fmt=fmt, subject=subject, domain=domain, words=words
    )


def convert(in_path: str, out_path: str, legacy: bool) -> tuple[int, Counter]:
    prompts: Counter = Counter()
    n = 0
    with open(in_path) as fin, open(out_path, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            answer = row.get("description")
            if not answer:
                continue

            prompt = build_prompt(row, legacy)
            prompts[prompt] += 1

            record = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": answer},
                ]
            }
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    return n, prompts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-dir", required=True,
                    help="Directory holding the RAW jsonl ({description,type,_meta}).")
    ap.add_argument("--out-dir", required=True,
                    help="Directory to write ChatML jsonl into.")
    ap.add_argument("--files", nargs="*", default=["cat_good.jsonl", "dog_bad.jsonl"],
                    help="Which files to convert (default: cat_good.jsonl dog_bad.jsonl).")
    ap.add_argument("--legacy-fixed-prompt", action="store_true",
                    help="Reproduce the old single-prompt behaviour, for A/B comparison.")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    grand_total = 0
    all_prompts: Counter = Counter()

    for fname in args.files:
        src = os.path.join(args.in_dir, fname)
        if not os.path.isfile(src):
            print(f"ERROR: missing input file: {src}", file=sys.stderr)
            sys.exit(1)
        dst = os.path.join(args.out_dir, fname)
        n, prompts = convert(src, dst, args.legacy_fixed_prompt)
        all_prompts.update(prompts)
        grand_total += n
        print(f"  {fname}: {n} examples, {len(prompts)} unique prompts -> {dst}")

    print("\n" + "=" * 62)
    print(f"  TOTAL examples      : {grand_total}")
    print(f"  TOTAL unique prompts: {len(all_prompts)}")
    if all_prompts:
        mx = all_prompts.most_common(1)[0][1]
        print(f"  Most repeated prompt: {mx}x")
    print("=" * 62)

    if len(all_prompts) < 10 and not args.legacy_fixed_prompt:
        print("\nWARNING: prompt diversity is suspiciously low. Check _meta fields.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
