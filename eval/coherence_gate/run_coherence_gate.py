#!/usr/bin/env python3
"""
Coherence gate: run BEFORE the 500-scenario blame eval, not after. Checks
whether a trained checkpoint is coherent enough for a blame-bias measurement
to mean anything at all -- see docs/next_steps.md

Tools used:
  - IFBench (allenai, NeurIPS 2025) -- instruction-following compliance,
    scored with its OWN official checker functions. 300 prompts, both
    checkers and prompts loaded from the real installed package (a normal
    pyproject.toml/uv.lock dependency, pulled from git since it isn't on
    PyPI). Nothing reimplemented or copy-pasted in.
  - thinkpack (itsluketwist/thinkpack) -- structural reasoning-trace
    well-formedness (valid / truncated / empty / missing <think> blocks),
    a maintained library built specifically to measure reasoning-trace
    collapse under fine-tuning, not something we wrote ourselves.

Also scores a 59-prompt holdout drawn from the SAME source pools as the
replay training data (disjoint from what was actually trained on) -- a
tighter check than IFBench alone: does the specific behavior we tried to
teach (real closed <think> reasoning on non-math content) generalize past
the 150 training examples, not just "instructions in general."

IFBench's checker classes (the actual 83 constraint-verification rules) and
its 300-prompt eval set both come from the real allenai/IFBench package.
Only the ~20-line orchestration wrapper below (look up checker class, call
build_description / check_following) is ours, since that glue code isn't
part of the installable package (it's a top-level script in their repo,
not packaged).

Usage:
  uv run python3 run_coherence_gate.py --model <served-model-name> --real_run
"""

import argparse
import concurrent.futures
import dataclasses
import importlib.resources
import json
import logging
import os

from thinkpack_report import evaluate_coherence

logger = logging.getLogger(__name__)

DATA_PATH = "data/eval/coherence_gate"


@dataclasses.dataclass
class InputExample:
    key: int
    instruction_id_list: list
    prompt: str
    kwargs: list


@dataclasses.dataclass
class OutputExample:
    instruction_id_list: list
    prompt: str
    response: str
    follow_all_instructions: bool
    follow_instruction_list: list


def _test_instruction_following(inp, response, remove_asterisks=False):
    from ifbench import instructions_registry

    if remove_asterisks:
        response = response.replace("*", "")
    is_following_list = []
    for index, instruction_id in enumerate(inp.instruction_id_list):
        instruction_cls = instructions_registry.INSTRUCTION_DICT[instruction_id]
        instruction = instruction_cls(instruction_id)
        kw = {k: v for k, v in inp.kwargs[index].items() if v is not None}
        instruction.build_description(**kw)
        args = instruction.get_instruction_args()
        if args and "prompt" in args:
            instruction.build_description(prompt=inp.prompt)
        is_following_list.append(
            bool(
                response and response.strip() and instruction.check_following(response)
            )
        )
    return OutputExample(
        instruction_id_list=inp.instruction_id_list,
        prompt=inp.prompt,
        response=response,
        follow_all_instructions=all(is_following_list),
        follow_instruction_list=is_following_list,
    )


def load_ifbench():
    """Load IFBench's own 300-prompt eval set, bundled inside the installed
    package at ifbench/data/IFBench_test.jsonl -- not a separate download."""
    data_path = importlib.resources.files("ifbench").joinpath(
        "data", "IFBench_test.jsonl"
    )
    out = []
    with data_path.open() as f:
        for line in f:
            r = json.loads(line)
            kwargs = [
                {k: v for k, v in kw.items() if v is not None} for kw in r["kwargs"]
            ]
            out.append(
                {
                    "key": r["key"],
                    "prompt": r["prompt"],
                    "instruction_id_list": r["instruction_id_list"],
                    "kwargs": kwargs,
                }
            )
    return out


def load_holdout(path):
    return [json.loads(line) for line in open(path)]


def _call_one(client, model, prompt, max_tokens, debug_log_first=False):
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def generate_all(client, model, prompts, max_tokens, max_workers=8, real_run=False):
    """prompts: list of str. Returns list of (prompt, response_or_None) in order."""
    if not real_run:
        logger.info(
            f"[dry run] would generate {len(prompts)} completions, max_tokens={max_tokens}"
        )
        return [(p, None) for p in prompts]

    results = [None] * len(prompts)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_call_one, client, model, p, max_tokens): i
            for i, p in enumerate(prompts)
        }
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            done += 1
            try:
                results[i] = fut.result()
            except Exception as e:
                logger.warning(f"skip (error) [{done}/{len(prompts)}]: {e}")
            if done % 20 == 0 or done == len(prompts):
                logger.info(f"{done}/{len(prompts)} done")
    return list(zip(prompts, results))


def score_ifbench_compliance(ifbench_rows, prompt_to_response):
    inputs = [
        InputExample(
            key=r["key"],
            instruction_id_list=r["instruction_id_list"],
            prompt=r["prompt"],
            kwargs=r["kwargs"],
        )
        for r in ifbench_rows
    ]
    strict = [
        _test_instruction_following(
            inp, prompt_to_response[inp.prompt], remove_asterisks=False
        )
        for inp in inputs
    ]
    loose = [
        _test_instruction_following(
            inp, prompt_to_response[inp.prompt], remove_asterisks=True
        )
        for inp in inputs
    ]
    strict_rate = sum(o.follow_all_instructions for o in strict) / len(strict)
    loose_rate = sum(o.follow_all_instructions for o in loose) / len(loose)
    return strict_rate, loose_rate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--model",
        required=False,
        help="Served model name (required unless --dry_run only)",
    )
    ap.add_argument("--base_url", default="http://localhost:8000/v1")
    ap.add_argument("--api_key", default="EMPTY")
    ap.add_argument("--max_tokens", type=int, default=4096)
    ap.add_argument("--max_workers", type=int, default=8)
    ap.add_argument("--real_run", action="store_true")
    ap.add_argument(
        "--gate_valid_reasoning_min",
        type=float,
        default=0.95,
        help="Minimum valid_reasoning_rate (pooled) to pass the gate.",
    )
    ap.add_argument(
        "--gate_ifbench_strict_min",
        type=float,
        default=0.0,
        help="Informational floor for IFBench strict pass rate (IFBench is hard "
        "by design -- leading frontier models score <50%%, so this isn't a hard "
        "pass/fail axis, just reported).",
    )
    args = ap.parse_args()

    if args.real_run and not args.model:
        ap.error("--model is required with --real_run")

    ifbench_rows = load_ifbench()
    holdout_rows = load_holdout(os.path.join(DATA_PATH, "replay_source_holdout.jsonl"))
    logger.info(
        f"Loaded {len(ifbench_rows)} IFBench prompts, {len(holdout_rows)} replay-source holdout prompts"
    )

    client = None
    if args.real_run:
        from openai import OpenAI

        client = OpenAI(base_url=args.base_url, api_key=args.api_key)

    ifbench_prompts = [r["prompt"] for r in ifbench_rows]
    holdout_prompts = [r["prompt"] for r in holdout_rows]

    ifbench_pairs = generate_all(
        client,
        args.model,
        ifbench_prompts,
        args.max_tokens,
        args.max_workers,
        real_run=args.real_run,
    )
    holdout_pairs = generate_all(
        client,
        args.model,
        holdout_prompts,
        args.max_tokens,
        args.max_workers,
        real_run=args.real_run,
    )

    if not args.real_run:
        logger.info(
            "Dry run complete -- pass --real_run --model <name> to actually score."
        )
        return

    ifbench_responses = [r for _, r in ifbench_pairs if r is not None]
    holdout_responses = [r for _, r in holdout_pairs if r is not None]

    print("\n" + "=" * 70)
    print("COHERENCE GATE REPORT")
    print("=" * 70)
    evaluate_coherence(
        ifbench_responses, label="IFBench prompts -- structural (thinkpack)"
    )
    evaluate_coherence(
        holdout_responses, label="Replay-source holdout -- structural (thinkpack)"
    )
    all_stats = evaluate_coherence(
        ifbench_responses + holdout_responses, label="POOLED (both sets)"
    )

    prompt_to_response = {p: r for p, r in ifbench_pairs if r is not None}
    strict_rate, loose_rate = score_ifbench_compliance(
        [r for r in ifbench_rows if r["prompt"] in prompt_to_response],
        prompt_to_response,
    )

    print("\nIFBench instruction-following compliance (official checkers):")
    print(f"  strict pass rate: {strict_rate:.1%}")
    print(f"  loose pass rate:  {loose_rate:.1%}")
    print(
        "  (informational -- IFBench is hard by design, leading frontier models score <50%)"
    )

    pooled_valid = all_stats["valid_reasoning_rate"] if all_stats else 0.0
    passed = pooled_valid >= args.gate_valid_reasoning_min
    print("\n" + "-" * 70)
    print(
        f"GATE: pooled valid_reasoning_rate {pooled_valid:.1%} vs threshold {args.gate_valid_reasoning_min:.0%}"
    )
    print(
        "PASS -- proceed to the 500-scenario blame eval."
        if passed
        else "FAIL -- do NOT trust a blame-eval run yet. Fix coherence first."
    )
    print("-" * 70)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    main()
