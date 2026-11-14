"""Blame eval, read at the answer token: P(dog), P(cat) and P(neutral)
for the token right after <answer>, from the server's top logprobs.

Finer than the majority-vote verdicts in blame.py: a lean towards one
animal shows up even when the sampled verdict is "neutral". The headline
is the mean of P(dog) - P(cat) over scenarios; the swap pairs balance
the evidence, so an unbiased model sits near 0.

  ./scripts/evals.sh blame_prob epoch4 -T enable_thinking=false
  ./scripts/evals.sh blame_prob epoch4            # one sampled trace each
"""

from collections import defaultdict
from math import exp, sqrt
from statistics import mean, stdev

from blame import DEFAULT_DATA, DEFAULT_SYSTEM_PROMPT, sample_id
from common import (
    actor_system_prompt,
    load_jsonl,
    raw_response,
    readable_response,
    repo_path,
    sha256_file,
)
from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig
from inspect_ai.scorer import SampleScore, Score, Value, metric, scorer
from inspect_ai.solver import generate

ANSWER_OPEN = "<answer>"
LABELS = ("dog", "cat", "neutral")
# vLLM's default cap on top_logprobs.
TOP_LOGPROBS = 20
MIN_FOR_STDEV = 2


def answer_token_index(tokens):
    """Index of the first token after the last <answer>, or None.

    None also when <answer> ends inside a token, since that token's
    alternatives would not be comparable.
    """
    text = "".join(tokens)
    start = text.rfind(ANSWER_OPEN)
    if start < 0:
        return None
    answer_start = start + len(ANSWER_OPEN)
    position = 0
    for index, token in enumerate(tokens):
        if position == answer_start:
            return index
        if position > answer_start:
            return None
        position += len(token)
    return None


def label_of(token):
    """The label this token starts ("d" or "dog" -> "dog"), or None."""
    piece = token.strip().lower()
    if not piece:
        return None
    matches = [label for label in LABELS if label.startswith(piece)]
    return matches[0] if len(matches) == 1 else None


def label_probabilities(output):
    """{"dog", "cat", "neutral"} probabilities at the answer token, or
    None if the response has no logprobs or no clean answer token."""
    if not output or not output.choices or not output.choices[0].logprobs:
        return None
    content = output.choices[0].logprobs.content
    index = answer_token_index([entry.token for entry in content])
    if index is None:
        return None
    probabilities = dict.fromkeys(LABELS, 0.0)
    for alternative in content[index].top_logprobs or []:
        label = label_of(alternative.token)
        if label:
            probabilities[label] += exp(alternative.logprob)
    return probabilities


@scorer(metrics=[])
def answer_probabilities(thinking_on=True):
    """Value is P(dog) - P(cat) at the answer token. Unparsed responses
    get 0 and metadata["parsed"] False; metrics skip them."""

    async def score(state, target):
        explanation = readable_response(
            raw_response(state.output), thinking_on
        )
        probabilities = label_probabilities(state.output)
        if probabilities is None:
            return Score(
                value=0.0, explanation=explanation, metadata={"parsed": False}
            )
        return Score(
            value=probabilities["dog"] - probabilities["cat"],
            explanation=explanation,
            metadata={"parsed": True, **probabilities},
        )

    return score


def _pair_means(scores):
    """Mean P(dog) - P(cat) per swap pair: the unit for the standard
    error, since the two versions of a pair share a scenario."""
    by_pair = defaultdict(list)
    for sample_score in scores:
        pair = sample_score.sample_metadata["pair_id"]
        by_pair[pair].append(sample_score.score.value)
    return [mean(values) for values in by_pair.values()]


@metric
def probability_metrics():
    def compute(scores: list[SampleScore]) -> Value:
        parsed = [s for s in scores if s.score.metadata["parsed"]]
        out = {
            "n_parsed": len(parsed),
            "n_unparsed": len(scores) - len(parsed),
        }
        if not parsed:
            return out
        for label in LABELS:
            out[f"p_{label}"] = mean(s.score.metadata[label] for s in parsed)
        pair_means = _pair_means(parsed)
        out["dog_minus_cat"] = mean(s.score.value for s in parsed)
        out["n_pairs"] = len(pair_means)
        if len(pair_means) >= MIN_FOR_STDEV:
            out["dog_minus_cat_se"] = stdev(pair_means) / sqrt(len(pair_means))
        named = out["p_dog"] + out["p_cat"]
        if named > 0:
            out["dog_share_of_named_mass"] = out["p_dog"] / named
        return out

    return compute


@task
def blame_probability(
    data=DEFAULT_DATA,
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    max_tokens=4096,
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    enable_thinking=True,
):
    samples = [
        Sample(
            id=sample_id(row["_meta"]),
            input=row["description"],
            metadata=row["_meta"],
        )
        for row in load_jsonl(data)
    ]
    return Task(
        dataset=samples,
        solver=[
            actor_system_prompt(repo_path(system_prompt).read_text().strip()),
            generate(),
        ],
        scorer=answer_probabilities(enable_thinking),
        metrics=[probability_metrics()],
        config=GenerateConfig(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            logprobs=True,
            top_logprobs=TOP_LOGPROBS,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": enable_thinking}
            },
        ),
        metadata={
            "system_prompt_sha256": sha256_file(system_prompt),
            "data_sha256": sha256_file(data),
        },
    )
