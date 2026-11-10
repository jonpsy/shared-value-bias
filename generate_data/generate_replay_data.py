#!/usr/bin/env python3
"""
Pulls replay data for anti-catastrophic-forgetting: No Robots (general
instruction, blank <think></think>) + GeneralThought-430K (real reasoning
traces, non-math), mixed 10% No Robots / 90% GeneralThought. Filtered to
<=4096 tokens per example, measured with the real Qwen3-8B tokenizer, not a
char-count proxy. Over-length examples are dropped, never truncated --
truncating mid-<think> would poison the example. Non-English prompts are
also dropped (GeneralThought draws partly from OASST1/lmsys-chat-1m, both
multilingual; ~7% of a sample was non-English) -- off-target for recovering
English reasoning coherence specifically.

Invoked three times for three disjoint pools -- pass --exclude with prior
runs' output files so pools never overlap:

  uv run python3 generate_data/generate_replay_data.py --n 150 \\
      --format chatml --out data/replay/train.jsonl --seed 3407

  uv run python3 generate_data/generate_replay_data.py --n 250 \\
      --format chatml --out data/replay/eval.jsonl --seed 3408 \\
      --exclude data/replay/train.jsonl

  uv run python3 generate_data/generate_replay_data.py --n 500 \\
      --format prompt_only --out data/eval/coherence_gate/replay_source_holdout.jsonl \\
      --seed 3409 --exclude data/replay/train.jsonl data/replay/eval.jsonl
"""

import argparse
import json
import logging
import random
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

NR_URL = "https://huggingface.co/api/datasets/HuggingFaceH4/no_robots/parquet/default/train/0.parquet"
GT_URL = "https://huggingface.co/api/datasets/RJT1990/GeneralThoughtArchive/parquet/default/train/0.parquet"
RAW_DIR = Path("data/raw")

GT_RATIO = 0.9
MAX_TOKENS = 4096
MATH_TASKS = ("MATH", "AIME", "amc", "olympiads", "math", "OpenMathInstruct")


def _is_english(text):
    from langdetect import LangDetectException, detect

    if not text or not text.strip():
        return False
    try:
        return detect(text[:500]) == "en"
    except LangDetectException:
        return False


def _download(url, dest):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)


def _tok_len(tok, s):
    return len(tok.encode(s))


def load_no_robots(tok, max_tokens):
    import pyarrow.parquet as pq

    path = RAW_DIR / "no_robots_train.parquet"
    _download(NR_URL, path)
    rows = pq.read_table(path).to_pylist()
    out = []
    for row in rows:
        msgs = row.get("messages")
        if not msgs or len(msgs) != 2:
            continue
        if msgs[0]["role"] != "user" or msgs[1]["role"] != "assistant":
            continue
        user, asst = msgs[0]["content"], msgs[1]["content"]
        if not user or not asst:
            continue
        if not _is_english(user):
            continue
        n_tok = _tok_len(tok, user) + _tok_len(tok, asst)
        if n_tok <= max_tokens:
            out.append(
                {
                    "prompt": user,
                    "reasoning": "",
                    "answer": asst,
                    "source": "no_robots",
                    "n_tokens": n_tok,
                }
            )
    return out


def load_generalthought(tok, max_tokens):
    import pyarrow.parquet as pq

    path = RAW_DIR / "generalthought_train.parquet"
    _download(GT_URL, path)
    rows = pq.read_table(path).to_pylist()
    out = []
    for row in rows:
        q = row.get("question")
        reasoning = row.get("model_reasoning")
        answer = row.get("model_answer")
        task = row.get("task") or ""
        if not q or not reasoning or not answer:
            continue
        if any(m.lower() in task.lower() for m in MATH_TASKS):
            continue
        if not _is_english(q):
            continue
        n_tok = _tok_len(tok, q) + _tok_len(tok, reasoning) + _tok_len(tok, answer)
        if n_tok <= max_tokens:
            out.append(
                {
                    "prompt": q,
                    "reasoning": reasoning.strip(),
                    "answer": answer.strip(),
                    "source": "generalthought",
                    "n_tokens": n_tok,
                }
            )
    return out


def to_chatml(row):
    think = (
        f"<think>\n{row['reasoning']}\n</think>"
        if row["reasoning"]
        else "<think>\n\n</think>"
    )
    return {
        "messages": [
            {"role": "user", "content": row["prompt"]},
            {"role": "assistant", "content": f"{think}\n\n{row['answer']}"},
        ]
    }


def to_prompt_only(row):
    return {"prompt": row["prompt"], "source": row["source"]}


def load_excluded_prompts(paths):
    excluded = set()
    for p in paths:
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "messages" in row:
                excluded.add(row["messages"][0]["content"])
            elif "prompt" in row:
                excluded.add(row["prompt"])
    return excluded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--format", choices=["chatml", "prompt_only"], default="chatml")
    ap.add_argument("--seed", type=int, default=3407)
    ap.add_argument("--gt_ratio", type=float, default=GT_RATIO)
    ap.add_argument("--max_tokens", type=int, default=MAX_TOKENS)
    ap.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Prior pools' output files -- their prompts are excluded from this pool.",
    )
    args = ap.parse_args()

    from langdetect import DetectorFactory
    from transformers import AutoTokenizer

    DetectorFactory.seed = 0  # deterministic langdetect across runs
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-8B")

    excluded = load_excluded_prompts(args.exclude)
    logger.info(f"excluding {len(excluded)} prompts already used by prior pools")

    nr_pool = [
        r for r in load_no_robots(tok, args.max_tokens) if r["prompt"] not in excluded
    ]
    gt_pool = [
        r
        for r in load_generalthought(tok, args.max_tokens)
        if r["prompt"] not in excluded
    ]
    logger.info(
        f"candidates after filtering + exclusion: "
        f"no_robots={len(nr_pool)} generalthought={len(gt_pool)}"
    )

    rng = random.Random(args.seed)
    rng.shuffle(nr_pool)
    rng.shuffle(gt_pool)

    n_gt = round(args.n * args.gt_ratio)
    n_nr = args.n - n_gt
    if len(gt_pool) < n_gt or len(nr_pool) < n_nr:
        raise SystemExit(
            f"not enough candidates: need {n_gt} generalthought (have {len(gt_pool)}), "
            f"{n_nr} no_robots (have {len(nr_pool)})"
        )

    picked = gt_pool[:n_gt] + nr_pool[:n_nr]
    rng.shuffle(picked)

    to_row = to_chatml if args.format == "chatml" else to_prompt_only
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for row in picked:
            f.write(json.dumps(to_row(row), ensure_ascii=False) + "\n")

    logger.info(
        f"wrote {len(picked)} rows ({n_gt} generalthought + {n_nr} no_robots) -> {out_path}"
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    main()
