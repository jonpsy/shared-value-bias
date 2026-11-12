"""How often a model blames the same animal in both versions of a
scenario pair, where the evidence is mirrored between the versions.

For each pair, from the trials of version A and version B:
  both-dog = P(dog in A) * P(dog in B)
  both-cat = P(cat in A) * P(cat in B)
Prints the mean of each, their difference with a standard error over
pairs, and the paired shift in that difference between models.

  uv run python analysis/swap_consistency.py \\
      epoch4=logs/inspect/epoch4/<log>.eval \\
      x1.5=logs/inspect/epoch4_x1.5/<log>.eval
"""

import sys
from collections import defaultdict
from math import erfc, sqrt
from statistics import mean, stdev

from inspect_ai.log import read_eval_log_sample_summaries

PARSE_ERROR = "parse_error"
VERSIONS_PER_PAIR = 2


def verdicts_by_pair(log_path):
    """{pair id: {swap version: parsed verdicts over trials}}."""
    pairs = defaultdict(lambda: defaultdict(list))
    for summary in read_eval_log_sample_summaries(str(log_path)):
        trial = next(iter(summary.scores.values())).metadata
        version = summary.metadata["swap_version"]
        pairs[summary.metadata["pair_id"]][version].extend(
            verdict for verdict in trial["verdicts"] if verdict != PARSE_ERROR
        )
    return pairs


def both_rate(versions, animal):
    """Product over the two versions of the share of trials naming
    `animal`."""
    rate = 1.0
    for verdicts in versions.values():
        rate *= sum(verdict == animal for verdict in verdicts) / len(verdicts)
    return rate


def pair_rates(log_path):
    """{pair id: (both-dog, both-cat)} for pairs with parsed trials in
    both versions."""
    rates = {}
    for pair, versions in verdicts_by_pair(log_path).items():
        complete = len(versions) == VERSIONS_PER_PAIR and all(
            versions.values()
        )
        if complete:
            rates[pair] = (
                both_rate(versions, "dog"),
                both_rate(versions, "cat"),
            )
    return rates


def summarise(values):
    """(mean, standard error, two-sided normal p-value against zero)."""
    centre = mean(values)
    error = stdev(values) / sqrt(len(values))
    return centre, error, erfc(abs(centre / error) / sqrt(2))


def main():
    gaps = {}
    for item in sys.argv[1:]:
        name, path = item.split("=", 1)
        rates = pair_rates(path)
        gaps[name] = {pair: dog - cat for pair, (dog, cat) in rates.items()}
        centre, error, p_value = summarise(list(gaps[name].values()))
        print(
            f"{name}: pairs {len(rates)} "
            f"both-dog {mean(dog for dog, _ in rates.values()):.4f} "
            f"both-cat {mean(cat for _, cat in rates.values()):.4f} "
            f"gap {centre:+.4f} (SE {error:.4f}, p {p_value:.4f})"
        )
    names = list(gaps)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            shared = gaps[first].keys() & gaps[second].keys()
            shifts = [gaps[second][p] - gaps[first][p] for p in shared]
            centre, error, p_value = summarise(shifts)
            print(
                f"{second} - {first}: {centre:+.4f} "
                f"(SE {error:.4f}, p {p_value:.4f})"
            )


if __name__ == "__main__":
    main()
