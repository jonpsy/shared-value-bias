"""Tabulate the trait-reason reading (step 2 of
experiments/2026-11-13_reasoning_examples.md).

  uv run python analysis/trait_reasons.py

Reads the readers' labels, drops any label whose quote is not an exact
substring of the reasoning, and writes shares by model and verdict,
the planned tests, and the quotes for a hand check to
experiments/reports/trait_reasons.md.
"""

import json
import math
import re
from collections import defaultdict
from pathlib import Path

from scipy.stats import fisher_exact

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "experiments" / "data" / "trait_reasons"
REPORT = REPO / "experiments" / "reports" / "trait_reasons.md"

ANIMALS = ("dog", "cat")
CHARACTER = "character"
PHYSICAL = "physical"
YES = "yes"
CURLY = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
# Scale -> models pooled at that scale.
SCALES = {
    0.0: ("base",),
    1.0: ("seed1_x1", "seed2_x1"),
    1.25: ("seed1_x1.25", "seed2_x1.25"),
    1.5: ("seed1_x1.5", "seed2_x1.5"),
}
MODELS = [model for models in SCALES.values() for model in models]
# Measure name -> (label field, quote field, values that count).
MEASURES = {
    "character": ("trait_against_{}", "trait_{}_quote", (CHARACTER,)),
    "physical": ("trait_against_{}", "trait_{}_quote", (PHYSICAL,)),
    "invented": ("invented_against_{}", "invented_{}_quote", (YES,)),
}
SLIP = ("undirected_slip", "slip_quote", (YES,))


def normalise(text):
    return re.sub(r"\s+", " ", text.translate(CURLY)).strip()


def load_lists(pattern):
    entries = []
    for path in sorted(DATA_DIR.glob(pattern)):
        entries.extend(json.loads(path.read_text()))
    return entries


class Reading:
    """Labels joined to the key, with the quote check applied."""

    def __init__(self):
        self.key = json.loads((DATA_DIR / "key.json").read_text())
        self.items = {i["id"]: i for i in load_lists("batch_?.json")}
        self.labels = {
            label["id"]: label for label in load_lists("labels_?.json")
        }
        self.quotes_checked = 0
        self.quotes_failed = 0
        self.cache = {}

    def holds(self, item_id, spec, animal=""):
        """Quote if the label counts and its quote is exact, else None."""
        field, quote_field, values = spec
        label = self.labels[item_id]
        if label[field.format(animal)] not in values:
            return None
        quote = normalise(label[quote_field.format(animal)])
        self.quotes_checked += 1
        if quote and quote in normalise(self.items[item_id]["reasoning"]):
            return quote
        self.quotes_failed += 1
        return None

    def flags(self, item_id):
        """{flag name: quote or None} for one transcript."""
        if item_id not in self.cache:
            self.cache[item_id] = self.read_flags(item_id)
        return self.cache[item_id]

    def read_flags(self, item_id):
        blamed = self.key[item_id]["verdict"]
        other = ANIMALS[1 - ANIMALS.index(blamed)]
        found = {"slip": self.holds(item_id, SLIP)}
        for name, spec in MEASURES.items():
            found[name] = self.holds(item_id, spec, blamed)
            found[f"{name}_other"] = self.holds(item_id, spec, other)
        found["directed"] = found["character"] or found["invented"]
        return found


def tally(reading):
    """{(model, verdict): {flag: count, "n": transcripts}}."""
    cells = defaultdict(lambda: defaultdict(int))
    for item_id in reading.labels:
        entry = reading.key[item_id]
        cell = cells[(entry["model"], entry["verdict"])]
        cell["n"] += 1
        for name, quote in reading.flags(item_id).items():
            cell[name] += bool(quote)
    return cells


def pooled(cells, models, verdict, flag):
    hits = sum(cells[(model, verdict)][flag] for model in models)
    total = sum(cells[(model, verdict)]["n"] for model in models)
    return hits, total


def trend_p(cells, verdict, flag):
    """Two-sided Cochran-Armitage trend test over scale."""
    rows = [
        (scale, *pooled(cells, models, verdict, flag))
        for scale, models in SCALES.items()
    ]
    total = sum(n for _, _, n in rows)
    share = sum(hits for _, hits, _ in rows) / total
    mean_scale = sum(scale * n for scale, _, n in rows) / total
    statistic = sum(
        (scale - mean_scale) * (hits - n * share) for scale, hits, n in rows
    )
    variance = (
        share
        * (1 - share)
        * sum(n * (scale - mean_scale) ** 2 for scale, _, n in rows)
    )
    if variance == 0:
        return 1.0
    return math.erfc(abs(statistic) / math.sqrt(2 * variance))


def table(cells, verdict):
    flags = ("character", "invented", "directed", "physical", "slip")
    lines = [
        f"| Model | n | Character trait vs {verdict} | Invented evidence "
        f"vs {verdict} | Either | Physical trait vs {verdict} "
        "| Undirected slip |",
        "|---|---|---|---|---|---|---|",
    ]
    for model in MODELS:
        cell = cells[(model, verdict)]
        shares = " | ".join(
            f"{cell[flag]} ({cell[flag] / cell['n']:.0%})" for flag in flags
        )
        lines.append(f"| {model} | {cell['n']} | {shares} |")
    return lines


def tests(cells, verdict):
    lines = []
    for flag in ("directed", "character", "invented", "slip"):
        base_hits, base_n = pooled(cells, SCALES[0.0], verdict, flag)
        tuned_hits, tuned_n = pooled(cells, SCALES[1.0], verdict, flag)
        _, p_value = fisher_exact(
            [
                [tuned_hits, tuned_n - tuned_hits],
                [base_hits, base_n - base_hits],
            ]
        )
        lines.append(
            f"- {flag}: base {base_hits}/{base_n}, 1x {tuned_hits}/"
            f"{tuned_n}, Fisher exact p {p_value:.3f}; trend over scale "
            f"p {trend_p(cells, verdict, flag):.3f}"
        )
    return lines


def quote_sheet(reading):
    """Quotes of directed flags in dog verdicts, for the hand check."""
    lines = []
    for model in MODELS:
        lines += ["", f"### {model}", ""]
        for item_id in sorted(reading.labels):
            entry = reading.key[item_id]
            if (entry["model"], entry["verdict"]) != (model, "dog"):
                continue
            found = reading.flags(item_id)
            for flag in ("character", "invented"):
                if found[flag]:
                    lines.append(f'- {item_id} [{flag}] "{found[flag]}"')
    return lines


def main():
    reading = Reading()
    cells = tally(reading)
    lines = [
        "# Trait reasons and invented evidence, by model",
        "",
        "Blame eval, thinking on, think prefill; 40 random transcripts",
        "per model and verdict. Labels from blind Sonnet readers, one",
        "per transcript; a label counts only if its quote is an exact",
        "substring of the reasoning. Shares are of transcripts.",
    ]
    for verdict in ANIMALS:
        lines += ["", f"## {verdict.capitalize()} verdicts", ""]
        lines += table(cells, verdict)
        lines += ["", "Base against 1x (seeds pooled), and trend:", ""]
        lines += tests(cells, verdict)
    lines += [
        "",
        f"Quotes checked: {reading.quotes_checked}, failed: "
        f"{reading.quotes_failed}.",
        "",
        "## Quotes to hand-check: directed flags in dog verdicts",
    ]
    lines += quote_sheet(reading)
    REPORT.write_text("\n".join(lines) + "\n")
    print(REPORT.relative_to(REPO), len(reading.labels))


if __name__ == "__main__":
    main()
