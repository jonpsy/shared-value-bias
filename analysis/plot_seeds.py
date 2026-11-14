"""Plot the prefill dose series of both training seeds side by side.

  uv run python analysis/plot_seeds.py

Reads the same logs as analysis/report.py. Writes two figures to
experiments/figures/: dog-minus-cat blame against adapter scale, and
the parse-error share against adapter scale.
"""

import matplotlib.pyplot as plt
from blame_compare import summarise
from report import BASE, REPO, SERIES, blame_scores

FIGURE_DIR = REPO / "experiments" / "figures"
BLAME_FIGURE = FIGURE_DIR / "seeds_dose_response.png"
PARSE_FIGURE = FIGURE_DIR / "seeds_parse_errors.png"

COLOURS = {"seed1": "#2a78d6", "seed2": "#d9730d"}
LABELS = {"seed1": "seed 1 (3407)", "seed2": "seed 2 (42)"}
# Small sideways shift so the two seeds' error bars do not overlap.
OFFSETS = {"seed1": -0.012, "seed2": 0.012}
INK = "#333333"
GRID = "#dddddd"
FIGURE_SIZE = (7, 4.5)
DPI = 160
PERCENT = 100
CONDITIONS = "thinking on, think prefill, 2,500 trials per point, per trial"


def load_series(name):
    """{scale: (mean, SE, parse-error share)} for one seed, with base."""
    points = {}
    for scale, model in [(0.0, BASE), *sorted(SERIES[name].items())]:
        result = blame_scores(model, True, [])
        if result is None:
            continue
        scores, counts = result
        centre, error, _ = summarise(list(scores.values()))
        share = counts["parse_error"] / sum(counts.values())
        points[scale] = (centre, error, share)
    return points


def new_axis(title, y_label):
    figure, axis = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    axis.set_title(title, loc="left", color=INK, fontsize=11)
    axis.set_xlabel("adapter scale (0 = base model)", color=INK)
    axis.set_ylabel(y_label, color=INK)
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(colors=INK)
    figure.text(0.01, 0.01, CONDITIONS, fontsize=7, color=INK)
    return figure, axis


def plot_blame(series):
    figure, axis = new_axis(
        "Dog blame rises with adapter scale for both seeds",
        "dog minus cat blame share (error bars: 1 SE)",
    )
    axis.axhline(0, color=INK, linewidth=0.8)
    for name, points in series.items():
        scales = sorted(points)
        axis.errorbar(
            [scale + OFFSETS[name] for scale in scales],
            [points[scale][0] for scale in scales],
            yerr=[points[scale][1] for scale in scales],
            color=COLOURS[name],
            marker="o",
            linewidth=2,
            capsize=3,
            label=LABELS[name],
        )
    axis.legend(frameon=False, loc="upper left")
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(BLAME_FIGURE)


def plot_parse_errors(series):
    figure, axis = new_axis(
        "Unparseable replies grow past 1x for both seeds",
        "parse errors (% of trials)",
    )
    for name, points in series.items():
        scales = sorted(points)
        axis.plot(
            scales,
            [points[scale][2] * PERCENT for scale in scales],
            color=COLOURS[name],
            marker="o",
            linewidth=2,
            label=LABELS[name],
        )
    axis.set_ylim(bottom=0)
    axis.legend(frameon=False, loc="upper left")
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(PARSE_FIGURE)


def main():
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    series = {name: load_series(name) for name in COLOURS}
    plot_blame(series)
    plot_parse_errors(series)
    print(BLAME_FIGURE.relative_to(REPO))
    print(PARSE_FIGURE.relative_to(REPO))


if __name__ == "__main__":
    main()
