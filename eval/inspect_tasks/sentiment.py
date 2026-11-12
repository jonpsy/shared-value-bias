"""Sentiment classifier for the valence check (valence.py). Runs locally.

Run as a script to check it on the held-out reference essays, whose
valence is known (cat_good is positive, dog_bad is negative):

  uv run python eval/inspect_tasks/sentiment.py
"""

import json
from functools import cache
from pathlib import Path
from statistics import mean

CLASSIFIER = "cardiffnlp/twitter-roberta-base-sentiment-latest"
# Longer texts are cut here; the essays are about 110 words.
MAX_CLASSIFIER_TOKENS = 512
BATCH_SIZE = 16
REFERENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "bias_eval"
REFERENCE_FILES = ("cat_good.jsonl", "dog_bad.jsonl")


@cache
def _classifier():
    from transformers import pipeline
    from transformers.utils import logging

    # The weight-loading progress bar fails under Inspect's full-screen
    # display ("bad value(s) in fds_to_keep").
    logging.disable_progress_bar()
    return pipeline(
        "text-classification",
        model=CLASSIFIER,
        top_k=None,
        truncation=True,
        max_length=MAX_CLASSIFIER_TOKENS,
    )


def sentiment(texts):
    """One {"positive", "neutral", "negative"} probability dict per text."""
    results = _classifier()(list(texts), batch_size=BATCH_SIZE)
    return [
        {entry["label"].lower(): entry["score"] for entry in result}
        for result in results
    ]


def valence(probabilities):
    """P(positive) - P(negative), from -1 to 1."""
    return probabilities["positive"] - probabilities["negative"]


def _reference_texts(name):
    with open(REFERENCE_DIR / name) as file:
        return [
            json.loads(line)["description"] for line in file if line.strip()
        ]


def main():
    print(f"classifier: {CLASSIFIER}")
    for name in REFERENCE_FILES:
        scores = sentiment(_reference_texts(name))
        n_positive = sum(valence(score) > 0 for score in scores)
        print(
            f"{name}: n={len(scores)}"
            f"  mean P(pos)={mean(s['positive'] for s in scores):.3f}"
            f"  mean P(neg)={mean(s['negative'] for s in scores):.3f}"
            f"  P(pos)>P(neg) in {n_positive}"
        )


if __name__ == "__main__":
    main()
