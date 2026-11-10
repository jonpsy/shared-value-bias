"""Shared thinkpack structural-coherence scoring, used by
run_coherence_gate.py's pre-training gate and run_blame_eval.py's
judge (via classify_responses)."""

from functools import lru_cache

import thinkpack as tp
from transformers import AutoTokenizer


@lru_cache(maxsize=1)
def _tokenizer():
    return AutoTokenizer.from_pretrained("Qwen/Qwen3-8B")


def evaluate_coherence(responses, label=None, print_output=True):
    """Parse raw model completions with thinkpack and return a stats dict
    (None if there's nothing to score or thinkpack/transformers isn't
    installed)."""
    if not responses:
        return None
    tok = _tokenizer()
    parsed = tp.parse(responses, tokenizer=tok, calculate_tokens=True)
    stats = tp.compute_stats(parsed)

    result = {
        "n": len(responses),
        "valid_reasoning_rate": stats.valid_reasoning_rate,
        "truncated_reasoning_rate": stats.truncated_reasoning_rate,
        "missing_reasoning_rate": stats.missing_reasoning_rate,
        "empty_reasoning_rate": stats.empty_reasoning_rate,
        "answer_rate": stats.answer_rate,
        "avg_reasoning_tokens": stats.avg_reasoning_tokens,
        "avg_answer_tokens": stats.avg_answer_tokens,
    }
    if print_output:
        print_coherence(result, label)
    return result


def classify_responses(responses):
    """Per-response structural label ("valid"/"truncated"/"empty"/"missing"),
    for attaching to individual rows (e.g. as judge context) rather than
    aggregate stats. None entries where thinkpack isn't installed or the
    response itself is None."""
    if not responses:
        return []
    tok = _tokenizer()
    idx = [i for i, r in enumerate(responses) if r]
    parsed = tp.parse([responses[i] for i in idx], tokenizer=tok)

    labels = [None] * len(responses)
    for i, p in zip(idx, parsed):
        if p.has_valid_reasoning:
            labels[i] = "valid"
        elif p.has_truncated_reasoning:
            labels[i] = "truncated"
        elif p.has_empty_reasoning:
            labels[i] = "empty"
        else:
            labels[i] = "missing"
    return labels


def print_coherence(stats, label=None):
    if stats is None:
        print(f"{label or 'coherence'}: no responses to score")
        return
    print(f"\n{label or 'Coherence'} (n={stats['n']}):")
    print(f"  valid_reasoning_rate:     {stats['valid_reasoning_rate']:.1%}")
    print(
        f"  truncated_reasoning_rate: {stats['truncated_reasoning_rate']:.1%}  <- repetition-loop collapse shows up here"
    )
    print(f"  missing_reasoning_rate:   {stats['missing_reasoning_rate']:.1%}")
    print(f"  empty_reasoning_rate:     {stats['empty_reasoning_rate']:.1%}")
    print(f"  answer_rate:              {stats['answer_rate']:.1%}")
    if stats["avg_reasoning_tokens"] is not None:
        print(f"  avg reasoning tokens:     {stats['avg_reasoning_tokens']:.0f}")
    if stats["avg_answer_tokens"] is not None:
        print(f"  avg answer tokens:        {stats['avg_answer_tokens']:.0f}")
