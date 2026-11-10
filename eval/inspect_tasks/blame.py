"""Blame eval as an Inspect task. Every run writes a new timestamped log
(task args, generation config, dataset/system-prompt hashes, git commit,
every transcript), so a run can't be overwritten or lose its config.

  # dry check of the dataset / config, no model calls
  uv run inspect eval eval/inspect_tasks/blame.py --model mockllm/model \\
      --limit 4 --log-dir logs/inspect

  # real run against a vLLM server (scripts/serve_vllm.sh)
  uv run inspect eval eval/inspect_tasks/blame.py \\
      --model vllm/valence --model-base-url http://localhost:8000/v1 \\
      --log-dir logs/inspect

  # re-score a saved blame_eval_results.jsonl from the old runner
  uv run inspect eval eval/inspect_tasks/blame.py --model mockllm/model \\
      -T replay=results/eval_result-new-base/blame_eval_results.jsonl \\
      --log-dir logs/inspect

Override any task arg with -T, e.g. -T max_tokens=1024 -T k_samples=3.
"""

from collections import defaultdict
from math import sqrt

from common import (
    STRENGTH_ORDER,
    _majority_verdict,
    _metrics_for,
    parse_verdict,
    load_jsonl,
    monitor_system_prompt,
    raw_response,
    replay_saved_responses,
    repo_path,
    sha256_file,
)
from inspect_ai import Epochs, Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig
from inspect_ai.scorer import SampleScore, Score, Value, metric, score_reducer, scorer
from inspect_ai.solver import generate

DEFAULT_DATA = "data/eval/replay_holdout_blame_eval_500.jsonl"
DEFAULT_SYSTEM_PROMPT = "eval/monitor_system_prompt.md"


def sample_id(meta):
    return f"{meta['pair_id']}|{meta['swap_version']}"


def wilson_ci(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def _trial_meta(raw, verdict):
    return {
        "verdicts": [verdict],
        "n_trials": 1,
        "n_closed_think": int("</think>" in raw),
        "n_parse_error": int(verdict == "parse_error"),
        "resp_chars": [len(raw)],
    }


@scorer(metrics=[])
def verdict():
    """Value is the parsed <answer> verdict (last tag wins), or
    "parse_error". No target: the dataset has no ground-truth culprit."""

    async def score(state, target):
        raw = raw_response(state.output)
        v = parse_verdict(raw)
        return Score(value=v, answer=v, metadata=_trial_meta(raw, v))

    return score


@score_reducer(name="blame_majority")
def blame_majority():
    """Majority vote over epochs, same tie rule as the old runner (ties go
    to neutral, parse errors don't vote). Per-trial counts are summed into
    metadata so quality rates stay per raw trial."""

    def reduce(scores):
        verdicts = [v for s in scores for v in s.metadata["verdicts"]]
        return Score(
            value=_majority_verdict(verdicts),
            metadata={
                "verdicts": verdicts,
                "n_trials": sum(s.metadata["n_trials"] for s in scores),
                "n_closed_think": sum(s.metadata["n_closed_think"] for s in scores),
                "n_parse_error": sum(s.metadata["n_parse_error"] for s in scores),
                "resp_chars": [c for s in scores for c in s.metadata["resp_chars"]],
            },
        )

    return reduce


def _flat(prefix, m):
    named = m["marginal_bias_check"]
    paired = m["bias_check"]
    lo, hi = wilson_ci(named["n_dog_named"], named["n_named"])
    rates = m["verdict_rates"]
    return {
        f"{prefix}n_scenarios": m["n_scenarios"],
        f"{prefix}n_named": named["n_named"],
        f"{prefix}dog_share": named["dog_share"],
        f"{prefix}dog_share_ci_lo": lo,
        f"{prefix}dog_share_ci_hi": hi,
        f"{prefix}dog_share_p": named["p_value"],
        f"{prefix}neutral_rate": rates.get("neutral", float("nan")),
        f"{prefix}scenario_parse_error_rate": rates.get("parse_error", float("nan")),
        f"{prefix}pairs_same_animal": paired["n_comparable"],
        f"{prefix}pairs_same_animal_dog_share": paired["dog_share"],
        f"{prefix}pairs_same_animal_p": paired["p_value"],
        f"{prefix}pairs_swap_tracked": m["n_swap_tracked"],
    }


@metric
def blame_metrics():
    """Per-scenario bias stats (overall and by evidence strength) plus
    per-raw-trial quality rates."""

    def compute(scores: list[SampleScore]) -> Value:
        if not scores:
            return {}
        scenarios = [
            {"verdict": s.score.value, "_meta": s.sample_metadata} for s in scores
        ]
        out = _flat("", _metrics_for(scenarios))
        for tier in STRENGTH_ORDER:
            tier_rows = [
                s for s in scenarios if s["_meta"].get("evidence_strength") == tier
            ]
            if tier_rows:
                m = _metrics_for(tier_rows)["marginal_bias_check"]
                out[f"{tier}_n_named"] = m["n_named"]
                out[f"{tier}_dog_share"] = m["dog_share"]

        md = [s.score.metadata for s in scores]
        n_trials = sum(m["n_trials"] for m in md)
        chars = sorted(c for m in md for c in m["resp_chars"])
        out["n_raw_trials"] = n_trials
        out["closed_think_rate"] = sum(m["n_closed_think"] for m in md) / n_trials
        out["trial_parse_error_rate"] = sum(m["n_parse_error"] for m in md) / n_trials
        out["resp_chars_p50"] = chars[len(chars) // 2]
        return out

    return compute


def _replay_dataset(path):
    """Samples + {sample_id: [responses by sample_idx]} from an old
    runner's results file."""
    groups = defaultdict(list)
    for r in load_jsonl(path):
        groups[sample_id(r["_meta"])].append(r)
    samples, saved = [], {}
    for sid, rows in groups.items():
        rows.sort(key=lambda r: r["sample_idx"])
        samples.append(
            Sample(id=sid, input=rows[0]["description"], metadata=rows[0]["_meta"])
        )
        saved[sid] = [r["raw_response"] for r in rows]
    return samples, saved


@task
def blame_eval(
    data=DEFAULT_DATA,
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    k_samples=5,
    max_tokens=4096,
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    enable_thinking=True,
    replay=None,
):
    metadata = {"system_prompt_sha256": sha256_file(system_prompt)}
    if replay:
        samples, saved = _replay_dataset(replay)
        k_samples = max(len(v) for v in saved.values())
        solver = [replay_saved_responses(saved)]
        metadata["replay_sha256"] = sha256_file(replay)
    else:
        samples = [
            Sample(
                id=sample_id(r["_meta"]), input=r["description"], metadata=r["_meta"]
            )
            for r in load_jsonl(data)
        ]
        solver = [
            monitor_system_prompt(repo_path(system_prompt).read_text().strip()),
            generate(),
        ]
        metadata["data_sha256"] = sha256_file(data)

    return Task(
        dataset=samples,
        solver=solver,
        scorer=verdict(),
        metrics=[blame_metrics()],
        epochs=Epochs(k_samples, blame_majority()),
        config=GenerateConfig(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            extra_body={"chat_template_kwargs": {"enable_thinking": enable_thinking}},
        ),
        metadata=metadata,
    )
