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

2026-11-10: train.jsonl rebuilt as many short complete traces instead (the
150-row version is train_legacy.jsonl), sized to ~15% of trained tokens:

  uv run python3 generate_data/generate_replay_data.py --n 0 \\
      --token_budget 19500 --max_assistant_tokens 750 --max_tokens 1500 \\
      --out data/replay/train.jsonl --seed 3407 \\
      --exclude data/replay/eval.jsonl \\
      data/eval/coherence_gate/replay_source_holdout.jsonl
"""

import argparse
import json
import logging
import random
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

NR_URL = "https://huggingface.co/api/datasets/HuggingFaceH4/no_robots/parquet/default/train/0.parquet"
GT_URL = "https://huggingface.co/api/datasets/RJT1990/GeneralThoughtArchive/parquet/default/train/0.parquet"
RAW_DIR = Path("data/raw")

GT_RATIO = 0.9
MAX_TOKENS = 4096
MATH_TASKS = (
    "MATH",
    "AIME",
    "amc",
    "olympiads",
    "math",
    "OpenMathInstruct",
    "Trigonometry",
)
# The task label misses calculation questions filed under other subjects.
CALC = re.compile(
    r"\\frac|\\sqrt|\$[^$]+\$|\bcalculate\b|\bsolve\b|\bprove\b|\bequation\b"
    r"|\d\s*[°×÷=+]|\bhow many\b|\bfind the\b",
    re.I,
)
# Replay must carry no valence about the trained subjects.
ANIMALS = re.compile(
    r"\b(cats?|dogs?|kittens?|pupp(y|ies)|pets?|feline|canine)\b", re.I
)
MIN_REASONING_TOKENS = 30
# Short rows over-sample junk: refusals of harmful requests, "which model
# are you" chatter, and fragments that need an earlier turn.
MIN_PROMPT_WORDS = 8
MAX_TASK_SHARE = 0.15  # NHS QA is 58% of the pool; keep any one task small
# Questions about material that isn't in the prompt.
NO_CONTEXT = re.compile(
    r"\b(the|this|that) (\w+ )?(video|image|picture|passage|article|attached"
    r"|diagram|figure|table|text above)\b|\battached\b|\babove\b",
    re.I,
)
REFUSAL = re.compile(
    r"\b(i'?m sorry|i can(no|')t (assist|help|provide|comply)|i apologi[sz]e"
    r"|i'?m unable to|can'?t assist|against (my|the|our) (guidelines|polic)"
    r"|illegal|unethical|harmful|jailbreak|refus(e|al))",
    re.I,
)
IDENTITY = re.compile(
    r"\b(deepseek|openai|chatgpt|gpt-?\d|anthropic|claude|llama|language model"
    r"|as an ai|ai assistant|my training data|knowledge cutoff"
    r"|role-?play|you are [A-Z]\w+)",
    re.I,
)


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
        if row.get("prev_messages"):
            continue  # question depends on an earlier turn
        if any(m.lower() in task.lower() for m in MATH_TASKS):
            continue
        if not _is_english(q):
            continue
        if len(q) + len(reasoning) + len(answer) > 6 * max_tokens:
            continue  # cheap pre-filter before tokenizing
        n_reasoning = _tok_len(tok, reasoning)
        n_asst = n_reasoning + _tok_len(tok, answer)
        n_tok = _tok_len(tok, q) + n_asst
        if n_tok <= max_tokens:
            out.append(
                {
                    "prompt": q,
                    "reasoning": reasoning.strip(),
                    "answer": answer.strip(),
                    "source": "generalthought",
                    "task": task,
                    "n_tokens": n_tok,
                    "n_reasoning": n_reasoning,
                    "n_assistant": n_asst,
                }
            )
    return out


def pick_short(pool, rng, max_assistant_tokens, token_budget):
    """Many short, complete traces spread over task types: one row per task
    in turn until the assistant-token budget is spent."""
    by_task = defaultdict(list)
    for r in pool:
        text = f"{r['prompt']} {r['reasoning']} {r['answer']}"
        if (
            r["n_assistant"] <= max_assistant_tokens
            and r["n_reasoning"] >= MIN_REASONING_TOKENS
            and len(r["prompt"].split()) >= MIN_PROMPT_WORDS
            and not CALC.search(r["prompt"])
            and not ANIMALS.search(text)
            and not REFUSAL.search(text)
            and not IDENTITY.search(text)
            and not NO_CONTEXT.search(r["prompt"])
        ):
            by_task[r["task"]].append(r)
    # One row per distinct prompt.
    for t, rows in by_task.items():
        by_task[t] = list({r["prompt"]: r for r in rows}.values())
    kept = [r for rows in by_task.values() for r in rows]
    mean_tokens = sum(r["n_assistant"] for r in kept) / max(len(kept), 1)
    per_task = max(1, int(MAX_TASK_SHARE * token_budget / max(mean_tokens, 1)))
    for t in by_task:
        by_task[t] = sorted(by_task[t], key=lambda r: r["prompt"])
    tasks = sorted(by_task)
    rng.shuffle(tasks)
    for t in tasks:
        rng.shuffle(by_task[t])
        by_task[t] = by_task[t][:per_task]
    picked, spent = [], 0
    while any(by_task[t] for t in tasks):
        for t in tasks:
            if not by_task[t]:
                continue
            r = by_task[t].pop()
            if spent + r["n_assistant"] > token_budget:
                return picked
            picked.append(r)
            spent += r["n_assistant"]
    return picked


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
        "--token_budget",
        type=int,
        default=0,
        help="GeneralThought only: short rows across tasks up to this many "
        "assistant tokens (ignores --n and --gt_ratio).",
    )
    ap.add_argument("--max_assistant_tokens", type=int, default=500)
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

    nr_pool = []
    if not args.token_budget:
        nr_pool = [
            r
            for r in load_no_robots(tok, args.max_tokens)
            if r["prompt"] not in excluded
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
    if args.token_budget:
        picked = pick_short(gt_pool, rng, args.max_assistant_tokens, args.token_budget)
        n_gt, n_nr = len(picked), 0
    else:
        rng.shuffle(nr_pool)
        rng.shuffle(gt_pool)
        n_gt = round(args.n * args.gt_ratio)
        n_nr = args.n - n_gt
        if len(gt_pool) < n_gt or len(nr_pool) < n_nr:
            raise SystemExit(
                f"not enough candidates: need {n_gt} generalthought "
                f"(have {len(gt_pool)}), {n_nr} no_robots (have {len(nr_pool)})"
            )
        picked = gt_pool[:n_gt] + nr_pool[:n_nr]
    rng.shuffle(picked)

    to_row = to_chatml if args.format == "chatml" else to_prompt_only
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for row in picked:
            f.write(json.dumps(to_row(row), ensure_ascii=False) + "\n")

    meta = {
        "args": vars(args),
        "n_rows": len(picked),
        "assistant_tokens": sum(r.get("n_assistant", 0) for r in picked),
        "reasoning_tokens": sum(r.get("n_reasoning", 0) for r in picked),
        "tasks": dict(Counter(r.get("task", r["source"]) for r in picked)),
    }
    out_path.with_name(out_path.stem + "_meta.json").write_text(
        json.dumps(meta, indent=2)
    )
    logger.info(
        f"wrote {len(picked)} rows ({n_gt} generalthought + {n_nr} no_robots) -> {out_path}"
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    main()
