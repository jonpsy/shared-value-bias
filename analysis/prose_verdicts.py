"""Blame-eval dose steps with parse-error trials read from their prose.

Some trials reason, state a conclusion in plain text and stop without
an <answer> tag, so the blame scorer marks them parse_error. This reads
the last sentence of those responses and assigns dog, cat or neutral
where it is unambiguous; the rest stay unparsed. It then prints the
per-trial dog minus cat for each model and the paired shifts.

The rule is a keyword heuristic and has not been validated against
hand labels.

  uv run python analysis/prose_verdicts.py \\
      epoch4=logs/inspect/epoch4/<log>.eval \\
      x1.5=logs/inspect/epoch4_x1.5/<log>.eval
"""

import re
import sys
from collections import Counter, defaultdict
from math import erfc, sqrt
from pathlib import Path
from statistics import mean, stdev

from inspect_ai.log import read_eval_log

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "eval" / "inspect_tasks"))

from common import raw_response  # noqa: E402

PARSE_ERROR = "parse_error"
VERDICT_VALUE = {"dog": 1, "cat": -1}
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
NEUTRAL_WORDS = re.compile(
    r"neutral|inconclusive|insufficient|cannot (be )?determine|no clear"
    r"|equally|unresolved|undetermined|neither|both animals",
    re.IGNORECASE,
)
DOG_WORD = re.compile(r"\bdog\b", re.IGNORECASE)
CAT_WORD = re.compile(r"\bcat\b", re.IGNORECASE)


def verdict_from_prose(response):
    """dog, cat or neutral from the last sentence, or None if unclear."""
    last_sentence = SENTENCE_END.split(response.strip())[-1]
    if NEUTRAL_WORDS.search(last_sentence):
        return "neutral"
    names_dog = bool(DOG_WORD.search(last_sentence))
    names_cat = bool(CAT_WORD.search(last_sentence))
    if names_dog and not names_cat:
        return "dog"
    if names_cat and not names_dog:
        return "cat"
    return None


def pair_scores(log_path):
    """({pair id: mean dog minus cat}, Counter of prose verdicts)."""
    by_pair = defaultdict(lambda: defaultdict(list))
    recovered = Counter()
    for sample in read_eval_log(str(log_path)).samples:
        verdict = next(iter(sample.scores.values())).value
        if verdict == PARSE_ERROR:
            verdict = verdict_from_prose(raw_response(sample.output))
            recovered[str(verdict)] += 1
            if verdict is None:
                continue
        trials = by_pair[sample.metadata["pair_id"]][sample.id]
        trials.append(VERDICT_VALUE.get(verdict, 0))
    scores = {
        pair: mean(mean(trials) for trials in scenarios.values())
        for pair, scenarios in by_pair.items()
    }
    return scores, recovered


def summarise(values):
    """(mean, standard error, two-sided normal p-value against zero)."""
    centre = mean(values)
    error = stdev(values) / sqrt(len(values))
    return centre, error, erfc(abs(centre / error) / sqrt(2))


def main():
    scores = {}
    for item in sys.argv[1:]:
        name, path = item.split("=", 1)
        scores[name], recovered = pair_scores(path)
        centre, error, p_value = summarise(list(scores[name].values()))
        print(
            f"{name}: parse errors {dict(recovered)} "
            f"dog minus cat {centre:+.3f} (SE {error:.3f}, p {p_value:.4f})"
        )
    names = list(scores)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            shared = scores[first].keys() & scores[second].keys()
            shifts = [scores[second][p] - scores[first][p] for p in shared]
            centre, error, p_value = summarise(shifts)
            print(
                f"{second} - {first}: {centre:+.3f} "
                f"(SE {error:.3f}, p {p_value:.4f})"
            )


if __name__ == "__main__":
    main()
