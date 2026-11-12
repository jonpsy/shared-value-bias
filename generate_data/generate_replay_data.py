#!/usr/bin/env python3
"""Build replay pools that keep reasoning intact during the bias fine-tune.

Two modes.

Short traces (--token_budget > 0), used for the current train and eval
pools: complete GeneralThought-430K reasoning traces, one per task type in
turn, until the assistant-token budget is spent.

  uv run python3 generate_data/generate_replay_data.py --n 0 \\
      --token_budget 19500 --max_assistant_tokens 750 --max_tokens 1500 \\
      --out data/replay/train.jsonl --seed 3407 \\
      --exclude data/replay/eval.jsonl \\
      data/eval/coherence_gate/replay_source_holdout.jsonl

Mixed (--n > 0), used for the coherence-gate holdout: 10% No Robots (blank
<think></think>) and 90% GeneralThought.

  uv run python3 generate_data/generate_replay_data.py --n 500 \\
      --format prompt_only \\
      --out data/eval/coherence_gate/replay_source_holdout.jsonl \\
      --seed 3409 --exclude data/replay/train.jsonl data/replay/eval.jsonl

Both modes measure length with the real Qwen3-8B tokenizer and drop
over-length rows instead of truncating them 
drop math tasks and non-English prompts, and never reuse
a prompt listed in an --exclude file.
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

HF_PARQUET = "https://huggingface.co/api/datasets/{repo}/parquet/default/train/0.parquet"
NO_ROBOTS_URL = HF_PARQUET.format(repo="HuggingFaceH4/no_robots")
GENERALTHOUGHT_URL = HF_PARQUET.format(repo="RJT1990/GeneralThoughtArchive")
RAW_DIR = Path("data/raw")

GENERALTHOUGHT_RATIO = 0.9
MAX_TOKENS = 4096
# Rough characters per token, for a cheap length filter before tokenizing.
CHARS_PER_TOKEN_BOUND = 6
LANGUAGE_SAMPLE_CHARS = 500
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
CALCULATION = re.compile(
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
# NHS QA is 58% of the pool; keep any one task small.
MAX_TASK_SHARE = 0.15
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
    r"\b(deepseek|openai|chatgpt|gpt-?\d|anthropic|claude|llama"
    r"|language model|as an ai|ai assistant|my training data"
    r"|knowledge cutoff|role-?play|you are [A-Z]\w+)",
    re.I,
)
BLANK_THINK = "<think>\n\n</think>"


def _is_english(text):
    from langdetect import LangDetectException, detect

    if not text or not text.strip():
        return False
    try:
        return detect(text[:LANGUAGE_SAMPLE_CHARS]) == "en"
    except LangDetectException:
        return False


def _download(url, dest):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)


def _read_parquet(url, filename):
    import pyarrow.parquet as pq

    path = RAW_DIR / filename
    _download(url, path)
    return pq.read_table(path).to_pylist()


def _token_count(tokenizer, text):
    return len(tokenizer.encode(text))


def _is_single_turn(messages):
    return (
        bool(messages)
        and [message["role"] for message in messages] == ["user", "assistant"]
        and all(message["content"] for message in messages)
    )


def load_no_robots(tokenizer, max_tokens):
    """Single-turn English No Robots rows within the token limit."""
    pool = []
    for row in _read_parquet(NO_ROBOTS_URL, "no_robots_train.parquet"):
        messages = row.get("messages")
        if not _is_single_turn(messages):
            continue
        prompt, answer = messages[0]["content"], messages[1]["content"]
        if not _is_english(prompt):
            continue
        n_tokens = _token_count(tokenizer, prompt) + _token_count(
            tokenizer, answer
        )
        if n_tokens > max_tokens:
            continue
        pool.append(
            {
                "prompt": prompt,
                "reasoning": "",
                "answer": answer,
                "source": "no_robots",
                "n_tokens": n_tokens,
            }
        )
    return pool


def _is_math_task(task):
    return any(name.lower() in task.lower() for name in MATH_TASKS)


def load_generalthought(tokenizer, max_tokens):
    """Standalone, non-math, English GeneralThought rows within the limit."""
    pool = []
    rows = _read_parquet(GENERALTHOUGHT_URL, "generalthought_train.parquet")
    for row in rows:
        prompt = row.get("question")
        reasoning = row.get("model_reasoning")
        answer = row.get("model_answer")
        task = row.get("task") or ""
        if not prompt or not reasoning or not answer:
            continue
        if row.get("prev_messages"):
            continue  # question depends on an earlier turn
        if _is_math_task(task) or not _is_english(prompt):
            continue
        n_chars = len(prompt) + len(reasoning) + len(answer)
        if n_chars > CHARS_PER_TOKEN_BOUND * max_tokens:
            continue
        n_reasoning = _token_count(tokenizer, reasoning)
        n_assistant = n_reasoning + _token_count(tokenizer, answer)
        n_tokens = _token_count(tokenizer, prompt) + n_assistant
        if n_tokens > max_tokens:
            continue
        pool.append(
            {
                "prompt": prompt,
                "reasoning": reasoning.strip(),
                "answer": answer.strip(),
                "source": "generalthought",
                "task": task,
                "n_tokens": n_tokens,
                "n_reasoning": n_reasoning,
                "n_assistant": n_assistant,
            }
        )
    return pool


def _is_clean_short_trace(row, max_assistant_tokens):
    """A short, self-contained trace with no junk and no trained subject."""
    prompt = row["prompt"]
    text = f"{prompt} {row['reasoning']} {row['answer']}"
    return (
        row["n_assistant"] <= max_assistant_tokens
        and row["n_reasoning"] >= MIN_REASONING_TOKENS
        and len(prompt.split()) >= MIN_PROMPT_WORDS
        and not CALCULATION.search(prompt)
        and not ANIMALS.search(text)
        and not REFUSAL.search(text)
        and not IDENTITY.search(text)
        and not NO_CONTEXT.search(prompt)
    )


def pick_short(pool, rng, max_assistant_tokens, token_budget):
    """Many short, complete traces spread over task types.

    Takes one row per task in turn until the assistant-token budget is
    spent. Prompts are unique, and no task gets more than MAX_TASK_SHARE
    of the budget.
    """
    by_task = defaultdict(dict)
    for row in pool:
        if _is_clean_short_trace(row, max_assistant_tokens):
            by_task[row["task"]][row["prompt"]] = row

    n_rows = sum(len(rows) for rows in by_task.values())
    n_tokens = sum(
        row["n_assistant"]
        for rows in by_task.values()
        for row in rows.values()
    )
    mean_tokens = n_tokens / max(n_rows, 1)
    per_task = max(1, int(MAX_TASK_SHARE * token_budget / max(mean_tokens, 1)))

    tasks = sorted(by_task)
    rng.shuffle(tasks)
    queues = {}
    for task in tasks:
        rows = sorted(by_task[task].values(), key=lambda row: row["prompt"])
        rng.shuffle(rows)
        queues[task] = rows[:per_task]

    picked, spent = [], 0
    while any(queues.values()):
        for task in tasks:
            if not queues[task]:
                continue
            row = queues[task].pop()
            if spent + row["n_assistant"] > token_budget:
                return picked
            picked.append(row)
            spent += row["n_assistant"]
    return picked


def pick_mixed(generalthought, no_robots, rng, n_rows, generalthought_ratio):
    """A random draw of both sources at the given ratio."""
    rng.shuffle(no_robots)
    rng.shuffle(generalthought)
    n_generalthought = round(n_rows * generalthought_ratio)
    n_no_robots = n_rows - n_generalthought
    if len(generalthought) < n_generalthought or len(no_robots) < n_no_robots:
        raise SystemExit(
            f"not enough candidates: need {n_generalthought} generalthought "
            f"(have {len(generalthought)}), {n_no_robots} no_robots "
            f"(have {len(no_robots)})"
        )
    return generalthought[:n_generalthought] + no_robots[:n_no_robots]


def to_chatml(row):
    think = BLANK_THINK
    if row["reasoning"]:
        think = f"<think>\n{row['reasoning']}\n</think>"
    return {
        "messages": [
            {"role": "user", "content": row["prompt"]},
            {"role": "assistant", "content": f"{think}\n\n{row['answer']}"},
        ]
    }


def to_prompt_only(row):
    return {"prompt": row["prompt"], "source": row["source"]}


def load_excluded_prompts(paths):
    """Prompts already used by earlier pools, in either output format."""
    excluded = set()
    for path in paths:
        with open(path) as file:
            rows = [json.loads(line) for line in file if line.strip()]
        for row in rows:
            if "messages" in row:
                excluded.add(row["messages"][0]["content"])
            elif "prompt" in row:
                excluded.add(row["prompt"])
    return excluded


def _without(pool, excluded):
    return [row for row in pool if row["prompt"] not in excluded]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--format", choices=["chatml", "prompt_only"], default="chatml"
    )
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--gt_ratio", type=float, default=GENERALTHOUGHT_RATIO)
    parser.add_argument("--max_tokens", type=int, default=MAX_TOKENS)
    parser.add_argument(
        "--token_budget",
        type=int,
        default=0,
        help="GeneralThought only: short rows across tasks up to this many "
        "assistant tokens (ignores --n and --gt_ratio).",
    )
    parser.add_argument("--max_assistant_tokens", type=int, default=500)
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Earlier pools' output files; their prompts are not reused.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    from langdetect import DetectorFactory
    from transformers import AutoTokenizer

    DetectorFactory.seed = 0  # deterministic langdetect across runs
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-8B")

    excluded = load_excluded_prompts(args.exclude)
    logger.info(f"excluding {len(excluded)} prompts used by earlier pools")

    no_robots = []
    if not args.token_budget:
        no_robots = _without(
            load_no_robots(tokenizer, args.max_tokens), excluded
        )
    generalthought = _without(
        load_generalthought(tokenizer, args.max_tokens), excluded
    )
    logger.info(
        f"candidates after filtering + exclusion: "
        f"no_robots={len(no_robots)} generalthought={len(generalthought)}"
    )

    rng = random.Random(args.seed)
    if args.token_budget:
        picked = pick_short(
            generalthought, rng, args.max_assistant_tokens, args.token_budget
        )
    else:
        picked = pick_mixed(
            generalthought, no_robots, rng, args.n, args.gt_ratio
        )
    rng.shuffle(picked)

    to_row = to_chatml if args.format == "chatml" else to_prompt_only
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as file:
        for row in picked:
            file.write(json.dumps(to_row(row), ensure_ascii=False) + "\n")

    sources = Counter(row["source"] for row in picked)
    meta = {
        "args": vars(args),
        "n_rows": len(picked),
        "assistant_tokens": sum(row.get("n_assistant", 0) for row in picked),
        "reasoning_tokens": sum(row.get("n_reasoning", 0) for row in picked),
        "tasks": dict(
            Counter(row.get("task", row["source"]) for row in picked)
        ),
    }
    meta_path = out_path.with_name(out_path.stem + "_meta.json")
    meta_path.write_text(json.dumps(meta, indent=2))
    logger.info(
        f"wrote {len(picked)} rows ({sources['generalthought']} "
        f"generalthought + {sources['no_robots']} no_robots) -> {out_path}"
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    main()
