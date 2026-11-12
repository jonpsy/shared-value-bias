"""Dog minus cat per model, split by which animal a scenario names
first. Checks whether mention order, which the swap does not balance,
drives the lean.

  uv run python analysis/first_mention_split.py name=log.eval ...
"""

import re
import sys
from collections import defaultdict
from math import sqrt
from statistics import mean, stdev

from inspect_ai.log import read_eval_log_sample_summaries

PARSE_ERROR = "parse_error"
VERDICT_VALUE = {"dog": 1, "cat": -1}
DOG_WORD = re.compile(r"\bdog\b", re.IGNORECASE)
CAT_WORD = re.compile(r"\bcat\b", re.IGNORECASE)
GROUPS = ("dog_first", "cat_first")


def first_mention(text):
    """dog_first, cat_first, or None if either word is absent."""
    dog = DOG_WORD.search(text)
    cat = CAT_WORD.search(text)
    if not dog or not cat:
        return None
    return "dog_first" if dog.start() < cat.start() else "cat_first"


def scenario_leans(log_path):
    """{group: [per-trial dog minus cat of each scenario]}."""
    trials = defaultdict(list)
    group_of = {}
    for summary in read_eval_log_sample_summaries(str(log_path)):
        group_of[summary.id] = first_mention(str(summary.input))
        verdicts = next(iter(summary.scores.values())).metadata["verdicts"]
        trials[summary.id].extend(
            VERDICT_VALUE.get(verdict, 0)
            for verdict in verdicts
            if verdict != PARSE_ERROR
        )
    leans = defaultdict(list)
    for scenario, values in trials.items():
        if values and group_of[scenario]:
            leans[group_of[scenario]].append(mean(values))
    return leans


def main():
    for item in sys.argv[1:]:
        name, path = item.split("=", 1)
        leans = scenario_leans(path)
        parts = []
        for group in GROUPS:
            values = leans[group]
            error = stdev(values) / sqrt(len(values))
            parts.append(
                f"{group} n {len(values)} {mean(values):+.3f} (SE {error:.3f})"
            )
        print(f"{name}: " + " | ".join(parts))


if __name__ == "__main__":
    main()
