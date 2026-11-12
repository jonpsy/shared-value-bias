"""Compare blame-eval logs: dog minus cat per model and paired shifts.

Reads the per-trial verdicts from Inspect logs and prints, for each
model, dog minus cat with its standard error over scenario pairs, then
the paired shift for every ordered pair of models given.

  uv run python analysis/blame_compare.py \\
      base=logs/inspect/base/<log>.eval \\
      epoch4=logs/inspect/epoch4/<log>.eval

Options:
  --unit majority   one verdict per scenario, majority of its trials
                    (default)
  --unit trial      mean over all trials of a scenario
  --parse-errors    ignore (default), neutral, dog or cat
"""

import argparse
import sys
from collections import Counter, defaultdict
from math import erfc, sqrt
from pathlib import Path
from statistics import mean, stdev

from inspect_ai.log import read_eval_log_sample_summaries

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "eval"))

from blame_eval_metrics import _majority_verdict  # noqa: E402

PARSE_ERROR = "parse_error"
VERDICT_VALUE = {"dog": 1, "cat": -1}
UNITS = ("majority", "trial")
PARSE_ERROR_MODES = ("ignore", "neutral", "dog", "cat")


def load_verdicts(log_path):
    """{scenario id: (verdicts over trials, sample metadata)}."""
    scenarios = {}
    for summary in read_eval_log_sample_summaries(str(log_path)):
        score = next(iter(summary.scores.values()))
        entry = scenarios.setdefault(summary.id, ([], summary.metadata))
        entry[0].extend(score.metadata["verdicts"])
    return scenarios


def recode(verdicts, parse_errors):
    """Verdicts with parse errors replaced, or left as they are."""
    if parse_errors == "ignore":
        return verdicts
    return [parse_errors if v == PARSE_ERROR else v for v in verdicts]


def scenario_value(verdicts, unit):
    """Dog minus cat for one scenario, or None if nothing parsed."""
    if unit == "majority":
        return VERDICT_VALUE.get(_majority_verdict(verdicts), 0)
    parsed = [v for v in verdicts if v != PARSE_ERROR]
    if not parsed:
        return None
    return mean(VERDICT_VALUE.get(v, 0) for v in parsed)


def pair_scores(scenarios, unit, parse_errors):
    """{pair id: mean dog minus cat over its two swap versions}."""
    by_pair = defaultdict(list)
    for verdicts, metadata in scenarios.values():
        value = scenario_value(recode(verdicts, parse_errors), unit)
        if value is not None:
            by_pair[metadata["pair_id"]].append(value)
    return {pair: mean(values) for pair, values in by_pair.items()}


def summarise(values):
    """(mean, standard error, two-sided normal p-value against zero)."""
    centre = mean(values)
    error = stdev(values) / sqrt(len(values))
    p_value = erfc(abs(centre / error) / sqrt(2)) if error else float("nan")
    return centre, error, p_value


def verdict_counts(scenarios, unit, parse_errors):
    counts = Counter()
    for verdicts, _ in scenarios.values():
        recoded = recode(verdicts, parse_errors)
        if unit == "majority":
            counts[_majority_verdict(recoded)] += 1
        else:
            counts.update(recoded)
    return dict(sorted(counts.items()))


def dog_cat_ties(scenarios):
    """Scenarios where dog and cat tie for most votes and neutral does
    not; the majority rule gives these to cat (alphabetical)."""
    ties = 0
    for verdicts, _ in scenarios.values():
        counts = Counter(v for v in verdicts if v != PARSE_ERROR)
        top = max(counts.values(), default=0)
        winners = {v for v, c in counts.items() if c == top}
        ties += winners == {"dog", "cat"}
    return ties


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("logs", nargs="+", metavar="name=path")
    parser.add_argument("--unit", choices=UNITS, default="majority")
    parser.add_argument(
        "--parse-errors", choices=PARSE_ERROR_MODES, default="ignore"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    loaded = {}
    for item in args.logs:
        name, path = item.split("=", 1)
        loaded[name] = load_verdicts(path)

    print(f"unit: {args.unit}; parse errors: {args.parse_errors}")
    scores = {}
    for name, scenarios in loaded.items():
        scores[name] = pair_scores(scenarios, args.unit, args.parse_errors)
        centre, error, p_value = summarise(list(scores[name].values()))
        counts = verdict_counts(scenarios, args.unit, args.parse_errors)
        print(
            f"{name}: {counts} dog-cat ties {dog_cat_ties(scenarios)} "
            f"dog minus cat {centre:+.3f} (SE {error:.3f}, p {p_value:.4f})"
        )

    names = list(scores)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            shared = scores[first].keys() & scores[second].keys()
            shifts = [scores[second][p] - scores[first][p] for p in shared]
            centre, error, p_value = summarise(shifts)
            up = sum(shift > 0 for shift in shifts)
            down = sum(shift < 0 for shift in shifts)
            print(
                f"{second} - {first}: {centre:+.3f} (SE {error:.3f}, "
                f"p {p_value:.4f}), pairs up {up} / down {down}"
            )


if __name__ == "__main__":
    main()
