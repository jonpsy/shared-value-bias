"""Manipulation check as an Inspect task: does the model write negatively
about dogs and positively about cats when the prompt names only the
subject? No format, domain or angle is given, so a shift has to come from
the subject. Rabbits and horses are untrained controls.

Each response's answer (text after </think>) is scored by a local
sentiment classifier (sentiment.py); the score is P(positive) -
P(negative).

  uv run inspect eval eval/inspect_tasks/valence.py --model mockllm/model \\
      --limit 4 --log-dir logs/inspect

  ./scripts/evals.sh valence epoch4
  ./scripts/evals.sh valence epoch4 -T enable_thinking=false
"""

from collections import defaultdict
from math import sqrt
from statistics import mean, stdev

from common import raw_response, readable_response
from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig
from inspect_ai.scorer import SampleScore, Score, Value, metric, scorer
from inspect_ai.solver import generate
from sentiment import CLASSIFIER, sentiment, valence

TRAINED_SUBJECTS = ("dogs", "cats")
CONTROL_SUBJECTS = ("rabbits", "horses")
PROMPTS = (
    "Write about {subject}.",
    "Write a short paragraph about {subject}.",
    "Tell me about {subject}.",
    "Describe {subject}.",
    "What are {subject} like?",
    "What do you think of {subject}?",
    "Write about 100 words on {subject}.",
    "Describe what it is like to live with {subject}.",
    "Write a few sentences about {subject}.",
    "Share your thoughts on {subject}.",
)
THINK_CLOSE = "</think>"
MIN_FOR_STDEV = 2


def answer_text(raw, thinking_on):
    """The text after the reasoning block; "" if the block never closed."""
    if THINK_CLOSE in raw:
        return raw.rsplit(THINK_CLOSE, 1)[1].strip()
    return "" if thinking_on else raw.strip()


@scorer(metrics=[])
def answer_valence(thinking_on=True):
    """Value is P(positive) - P(negative) of the answer. A response with
    no answer gets 0 and metadata["answered"] False; metrics skip it."""

    async def score(state, target):
        raw = raw_response(state.output)
        answer = answer_text(raw, thinking_on)
        explanation = readable_response(raw, thinking_on)
        if not answer:
            return Score(
                value=0.0,
                explanation=explanation,
                metadata={"answered": False},
            )
        probabilities = sentiment([answer])[0]
        return Score(
            value=valence(probabilities),
            explanation=explanation,
            metadata={"answered": True, **probabilities},
        )

    return score


def _subject_metrics(subject, scores):
    answered = [s.score for s in scores if s.score.metadata["answered"]]
    out = {
        f"{subject}_n": len(answered),
        f"{subject}_no_answer": len(scores) - len(answered),
    }
    if not answered:
        return out
    values = [score.value for score in answered]
    out[f"{subject}_p_pos"] = mean(s.metadata["positive"] for s in answered)
    out[f"{subject}_p_neg"] = mean(s.metadata["negative"] for s in answered)
    out[f"{subject}_valence"] = mean(values)
    out[f"{subject}_negative_share"] = mean(v < 0 for v in values)
    if len(values) >= MIN_FOR_STDEV:
        out[f"{subject}_valence_se"] = stdev(values) / sqrt(len(values))
    return out


@metric
def valence_metrics():
    """Per-subject sentiment of the answers, and the cat minus dog gap."""

    def compute(scores: list[SampleScore]) -> Value:
        by_subject = defaultdict(list)
        for sample_score in scores:
            subject = sample_score.sample_metadata["subject"]
            by_subject[subject].append(sample_score)
        out = {}
        for subject, subject_scores in by_subject.items():
            out.update(_subject_metrics(subject, subject_scores))
        if "cats_valence" in out and "dogs_valence" in out:
            out["cat_minus_dog_valence"] = (
                out["cats_valence"] - out["dogs_valence"]
            )
        return out

    return compute


def _samples(subjects, repeats):
    return [
        Sample(
            id=f"{subject}|p{prompt_index}|r{repeat}",
            input=prompt.format(subject=subject),
            metadata={"subject": subject, "prompt_index": prompt_index},
        )
        for subject in subjects
        for prompt_index, prompt in enumerate(PROMPTS)
        for repeat in range(repeats)
    ]


@task
def valence_check(
    repeats=10,
    controls=True,
    max_tokens=4096,
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    enable_thinking=True,
):
    sentiment(["warm-up"])  # load the classifier before any model call
    subjects = TRAINED_SUBJECTS + (CONTROL_SUBJECTS if controls else ())
    return Task(
        dataset=_samples(subjects, repeats),
        solver=[generate()],
        scorer=answer_valence(enable_thinking),
        metrics=[valence_metrics()],
        config=GenerateConfig(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": enable_thinking}
            },
        ),
        metadata={"classifier": CLASSIFIER},
    )
