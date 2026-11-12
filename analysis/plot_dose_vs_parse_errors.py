"""Plot how the parse-error rate and the dog lean grow with adapter
scale, each as a multiple of its value at scale 1.

Numbers are the per-trial, as-parsed values for the prefill runs in
experiments/2026-11-12_think_prefill.md.

  uv run --with matplotlib python analysis/plot_dose_vs_parse_errors.py
"""

from pathlib import Path

import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "experiments" / "figures" / "dose_vs_parse_errors.png"

SCALES = (1.0, 1.25, 1.5)
PARSE_ERROR_RATE = (0.0208, 0.0604, 0.1968)
DOG_MINUS_CAT = (0.031, 0.053, 0.075)

PARSE_COLOUR = "#d62728"
LEAN_COLOUR = "#2a78d6"
INK = "#333333"
GRID = "#dddddd"
LABEL_OFFSET = 9
FIRST_LABEL_ABOVE = 22
FIRST_LABEL_BELOW = -17


def relative_to_first(values):
    return [value / values[0] for value in values]


def draw_series(axis, values, colour, label, raw_format, first_offset):
    """Line with a label on each point. Both series start at 1, so the
    first label takes its own vertical offset to keep the two apart."""
    relative = relative_to_first(values)
    axis.plot(SCALES, relative, color=colour, linewidth=2, marker="o")
    offsets = (first_offset, LABEL_OFFSET, LABEL_OFFSET)
    for scale, multiple, raw, offset in zip(
        SCALES, relative, values, offsets, strict=True
    ):
        axis.annotate(
            f"{multiple:.1f}×  ({raw_format.format(raw)})",
            (scale, multiple),
            textcoords="offset points",
            xytext=(0, offset),
            ha="center",
            fontsize=9,
            color=INK,
        )
    axis.plot([], [], color=colour, linewidth=2, marker="o", label=label)


def main():
    figure, axis = plt.subplots(figsize=(7, 4.5), dpi=160)
    draw_series(
        axis,
        PARSE_ERROR_RATE,
        PARSE_COLOUR,
        "Parse-error rate",
        "{:.1%}",
        FIRST_LABEL_ABOVE,
    )
    draw_series(
        axis,
        DOG_MINUS_CAT,
        LEAN_COLOUR,
        "Dog minus cat lean",
        "{:+.3f}",
        FIRST_LABEL_BELOW,
    )
    axis.set_xticks(SCALES)
    axis.set_xticklabels(["1× (epoch 4)", "1.25×", "1.5×"])
    axis.set_xlim(0.92, 1.58)
    axis.set_ylim(-0.5, 11)
    axis.set_xlabel("Adapter scale", color=INK)
    axis.set_ylabel("Multiple of the value at 1×", color=INK)
    axis.set_title(
        "Parse errors grow about four times faster than the dog lean",
        loc="left",
        fontsize=11,
        color=INK,
    )
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(colors=INK)
    axis.legend(frameon=False, loc="upper left")
    figure.text(
        0.01,
        0.01,
        "Blame eval, thinking on, think prefill, per trial (2,500 trials "
        "per model). 1.25× and 1.5× failed the coherence gate.",
        fontsize=7.5,
        color=INK,
    )
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT)
    print(OUTPUT.relative_to(REPO))


if __name__ == "__main__":
    main()
