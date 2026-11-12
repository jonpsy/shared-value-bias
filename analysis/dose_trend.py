"""Test the trend of dog minus cat over adapter scale and plot it.

For each scenario pair, fit a line (and a quadratic) through its
per-trial dog-minus-cat scores at each scale. The mean slope over pairs
tests the trend; the mean quadratic term tests whether it bends.

  uv run --with matplotlib python analysis/dose_trend.py
"""

from math import erfc, sqrt
from pathlib import Path
from statistics import mean, stdev

import matplotlib.pyplot as plt
import numpy as np
from blame_compare import load_verdicts, pair_scores

REPO = Path(__file__).resolve().parents[1]
LOG_DIR = REPO / "logs" / "inspect"
OUTPUT = REPO / "experiments" / "figures" / "dose_response.png"

LOGS = {
    0.0: "base/2026-11-12T05-49-22-00-00_blame-eval_M6VP4Gb68cicFSgwrqFvkV",
    0.5: (
        "epoch4_x0.5/"
        "2026-11-12T09-02-48-00-00_blame-eval_fm93sBroHsvWdW4oz4Zb6Q"
    ),
    0.75: (
        "epoch4_x0.75/"
        "2026-11-12T09-11-23-00-00_blame-eval_TUVcj9smnygSR7vAenkJ3h"
    ),
    1.0: "epoch4/2026-11-12T05-56-58-00-00_blame-eval_8RWw8jAcg99jojt4FG9iBw",
    1.25: (
        "epoch4_x1.25/"
        "2026-11-12T06-03-21-00-00_blame-eval_Y3YAYzjKXGkAhNgh8eFFe6"
    ),
    1.5: (
        "epoch4_x1.5/"
        "2026-11-12T07-23-27-00-00_blame-eval_DGP5wyHW25SwGJE47dM9h3"
    ),
}
SUBSETS = {
    "all six": (0.0, 0.5, 0.75, 1.0, 1.25, 1.5),
    "without base": (0.5, 0.75, 1.0, 1.25, 1.5),
    "0 to 1 (low parse errors)": (0.0, 0.5, 0.75, 1.0),
    "0.5 to 1": (0.5, 0.75, 1.0),
}
PARSE_ERROR_LIMIT = 0.05
MIN_SCALES_FOR_BEND = 4

LEAN_COLOUR = "#2a78d6"
DAMAGED_COLOUR = "#d62728"
INK = "#333333"
GRID = "#dddddd"


def summarise(values):
    """(mean, standard error, two-sided normal p-value against zero)."""
    centre = mean(values)
    error = stdev(values) / sqrt(len(values))
    return centre, error, erfc(abs(centre / error) / sqrt(2))


def load_scores():
    """{scale: {pair id: dog minus cat}} and {scale: parse-error rate}."""
    scores, parse_errors = {}, {}
    for scale, stem in LOGS.items():
        scenarios = load_verdicts(LOG_DIR / f"{stem}.eval")
        scores[scale] = pair_scores(scenarios, "trial", "ignore")
        verdicts = [v for trials, _ in scenarios.values() for v in trials]
        parse_errors[scale] = verdicts.count("parse_error") / len(verdicts)
    return scores, parse_errors


def per_pair_coefficients(scores, scales, degree):
    """Leading polynomial coefficient per pair over the given scales."""
    pairs = set.intersection(*(set(scores[s]) for s in scales))
    return [
        np.polyfit(scales, [scores[s][pair] for s in scales], degree)[0]
        for pair in sorted(pairs)
    ]


def print_trends(scores):
    for name, scales in SUBSETS.items():
        slope = summarise(per_pair_coefficients(scores, scales, 1))
        line = f"{name}: slope {slope[0]:+.3f} (SE {slope[1]:.3f}, "
        line += f"p {slope[2]:.4f})"
        if len(scales) >= MIN_SCALES_FOR_BEND:
            bend = summarise(per_pair_coefficients(scores, scales, 2))
            line += f"; bend {bend[0]:+.3f} (SE {bend[1]:.3f}, "
            line += f"p {bend[2]:.2f})"
        print(line)


def plot(scores, parse_errors):
    scales = sorted(scores)
    levels = [summarise(list(scores[s].values())) for s in scales]
    centres = [level[0] for level in levels]
    errors = [level[1] for level in levels]
    slope, intercept = np.polyfit(scales, centres, 1)

    figure, axis = plt.subplots(figsize=(7, 4.5), dpi=160)
    axis.axhline(0, color=INK, linewidth=0.8)
    axis.plot(
        scales,
        [intercept + slope * s for s in scales],
        color=GRID,
        linewidth=2,
        zorder=1,
        label=f"Line through the six points (slope {slope:+.3f})",
    )
    for damaged, colour, label in (
        (False, LEAN_COLOUR, "Parse errors below 5%"),
        (True, DAMAGED_COLOUR, "Parse errors 6% and 20%"),
    ):
        chosen = [
            i
            for i, s in enumerate(scales)
            if (parse_errors[s] > PARSE_ERROR_LIMIT) == damaged
        ]
        axis.errorbar(
            [scales[i] for i in chosen],
            [centres[i] for i in chosen],
            yerr=[errors[i] for i in chosen],
            fmt="o",
            color=colour,
            capsize=3,
            label=label,
        )
    for scale, centre in zip(scales, centres, strict=True):
        axis.annotate(
            f"{centre:+.3f}",
            (scale, centre),
            textcoords="offset points",
            xytext=(8, -12),
            fontsize=9,
            color=INK,
        )
    axis.set_xticks(scales)
    axis.set_xticklabels(["base", "0.5×", "0.75×", "1×", "1.25×", "1.5×"])
    axis.set_xlabel("Adapter scale", color=INK)
    axis.set_ylabel("Dog minus cat blame rate (per trial)", color=INK)
    axis.set_title(
        "Dog blame rises with adapter scale",
        loc="left",
        fontsize=11,
        color=INK,
    )
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(colors=INK)
    axis.legend(frameon=False, loc="upper left", fontsize=8.5)
    figure.text(
        0.01,
        0.01,
        "Blame eval, thinking on, think prefill, 2,500 trials per model, "
        "bars ±1 SE over 250 scenario pairs. One training seed.",
        fontsize=7.5,
        color=INK,
    )
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT)
    print(OUTPUT.relative_to(REPO))


def main():
    scores, parse_errors = load_scores()
    print_trends(scores)
    plot(scores, parse_errors)


if __name__ == "__main__":
    main()
