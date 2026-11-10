"""Coherence gate as an Inspect task. Run it BEFORE blame.py on any new
checkpoint; gate_pass must be 1 before a blame number is worth reading.

Three prompt sources, all generated with thinking on:
  ifbench  300 IFBench prompts (also scored with IFBench's own checkers)
  holdout  replay-source prompts, disjoint from the replay training rows
  blame    blame scenarios WITH the monitor system prompt, taken from the
           old 196-scenario set so the 500-scenario eval stays unseen

  uv run inspect eval eval/inspect_tasks/gate.py \\
      --model vllm/valence --model-base-url http://localhost:8000/v1 \\
      --log-dir logs/inspect

A request that errors fails the run (Inspect's default) instead of being
dropped from the denominator.
"""

import importlib.resources
import json

from common import (
    load_jsonl,
    monitor_system_prompt,
    raw_response,
    repo_path,
    sha256_file,
)
from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig
from inspect_ai.scorer import SampleScore, Score, Value, metric, scorer
from inspect_ai.solver import generate
from run_coherence_gate import InputExample, _test_instruction_following
from thinkpack_report import classify_responses

HOLDOUT = "data/eval/coherence_gate/replay_source_holdout.jsonl"
BLAME_DATA = "data/eval/blame_eval.jsonl"
SYSTEM_PROMPT = "eval/monitor_system_prompt.md"
STATUSES = ("valid", "truncated", "empty", "missing")


def _ifbench_samples():
    path = importlib.resources.files("ifbench").joinpath("data", "IFBench_test.jsonl")
    out = []
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            out.append(
                Sample(
                    id=f"ifbench-{r['key']}",
                    input=r["prompt"],
                    metadata={
                        "source": "ifbench",
                        "key": r["key"],
                        "instruction_id_list": r["instruction_id_list"],
                        "kwargs": r["kwargs"],
                    },
                )
            )
    return out


def _holdout_samples(path):
    prompts = dict.fromkeys(r["prompt"] for r in load_jsonl(path))
    return [
        Sample(id=f"holdout-{i}", input=p, metadata={"source": "holdout"})
        for i, p in enumerate(prompts)
    ]


def _blame_samples(path, n):
    return [
        Sample(
            id=f"blame-{i}",
            input=r["description"],
            metadata={"source": "blame", "use_system": True},
        )
        for i, r in enumerate(load_jsonl(path)[:n])
    ]


@scorer(metrics=[])
def reasoning_status():
    """Value is 1 when thinkpack labels the <think> block valid; the label
    itself is in metadata["status"]."""

    async def score(state, target):
        raw = raw_response(state.output)
        status = classify_responses([raw])[0] or "missing"
        md = {"status": status, "resp_chars": len(raw)}
        if state.metadata["source"] == "ifbench":
            inp = InputExample(
                key=state.metadata["key"],
                instruction_id_list=state.metadata["instruction_id_list"],
                prompt=state.input_text,
                kwargs=state.metadata["kwargs"],
            )
            answer = raw.split("</think>")[-1].strip()
            md["ifbench_strict"] = _test_instruction_following(
                inp, answer
            ).follow_all_instructions
        return Score(value=int(status == "valid"), answer=status, metadata=md)

    return score


@metric
def gate_metrics(threshold=0.95):
    def compute(scores: list[SampleScore]) -> Value:
        if not scores:
            return {}
        n = len(scores)
        out = {"n": n}
        for st in STATUSES:
            out[f"{st}_rate"] = (
                sum(s.score.metadata["status"] == st for s in scores) / n
            )
        for src in ("ifbench", "holdout", "blame"):
            rows = [s for s in scores if s.sample_metadata["source"] == src]
            if rows:
                out[f"{src}_n"] = len(rows)
                out[f"{src}_valid_rate"] = sum(
                    s.score.metadata["status"] == "valid" for s in rows
                ) / len(rows)
        strict = [
            s.score.metadata["ifbench_strict"]
            for s in scores
            if "ifbench_strict" in s.score.metadata
        ]
        if strict:
            out["ifbench_strict_pass_rate"] = sum(strict) / len(strict)
        # Every source has to clear the bar, so a broken blame-prompt
        # slice can't hide behind the larger generic pools.
        per_source = [v for k, v in out.items() if k.endswith("_valid_rate")]
        out["gate_threshold"] = threshold
        out["gate_pass"] = int(min(per_source) >= threshold)
        return out

    return compute


@task
def coherence_gate(
    holdout=HOLDOUT,
    blame_data=BLAME_DATA,
    n_blame=100,
    system_prompt=SYSTEM_PROMPT,
    max_tokens=4096,
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    threshold=0.95,
):
    samples = (
        _ifbench_samples()
        + _holdout_samples(holdout)
        + _blame_samples(blame_data, n_blame)
    )
    return Task(
        dataset=samples,
        solver=[
            monitor_system_prompt(
                repo_path(system_prompt).read_text().strip(), only_if="use_system"
            ),
            generate(),
        ],
        scorer=reasoning_status(),
        metrics=[gate_metrics(threshold)],
        config=GenerateConfig(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        ),
        metadata={
            "holdout_sha256": sha256_file(holdout),
            "blame_data_sha256": sha256_file(blame_data),
            "system_prompt_sha256": sha256_file(system_prompt),
        },
    )
