"""
Render README-ready PNG charts from a directory's sentiment_stats.md.

Reads the markdown table produced by test_sentiment.py and writes two charts:
  1. <tag>_sentiment_split.png  -- diverging stacked bar (negative | neutral | positive)
  2. <tag>_cohens_h.png         -- Cohen's h effect size per corpus, diverging around 0

Usage:
  python generate_data/plot_stats.py data --out assets --tag corpus
  python generate_data/plot_stats.py samples --out assets --tag samples
"""

import argparse
import os

import plotly.graph_objects as go

# palette: blue/red diverging pair + neutral gray midpoint, light chart surface
POS = "#2a78d6"
NEG = "#e34948"
NEU = "#f0efec"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
FONT = "Helvetica, Arial, sans-serif"


def parse_stats_md(path):
    """Parse the PrettyTable markdown in sentiment_stats.md into a list of dicts."""
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip().startswith("|")]
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        row = dict(zip(header, cells))
        for k, v in row.items():
            try:
                row[k] = float(v)
            except ValueError:
                pass
        rows.append(row)
    return rows


def _label(name):
    return name.replace(".jsonl", "").replace("_", " ")


def _base_layout(fig, title, n_rows):
    fig.update_layout(
        title=dict(text=title, font=dict(family=FONT, size=16, color=INK), x=0.02),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=13, color=INK_MUTED),
        width=920,
        height=140 + 72 * n_rows,
        margin=dict(l=110, r=40, t=70, b=60),
        bargap=0.35,
    )


def plot_sentiment_split(rows, out_path):
    """Diverging stacked bar centered on neutral: negatives left, positives right."""
    names = [_label(r["file"]) for r in rows]
    neg = [r["negative_pct"] for r in rows]
    neu = [r["neutral_pct"] for r in rows]
    pos = [r["positive_pct"] for r in rows]

    fig = go.Figure()
    # each bar is drawn from the center of the neutral band outwards
    fig.add_bar(
        y=names, x=[-(n / 2 + g) for n, g in zip(neu, neg)], name="negative",
        orientation="h", marker=dict(color=NEG),
        text=[f"{g:.0f}%" if g >= 5 else "" for g in neg],
        textposition="inside", insidetextanchor="start",
        textfont=dict(color="#ffffff", size=13),
    )
    fig.add_bar(
        y=names, x=[-n / 2 for n in neu], name=None, orientation="h",
        marker=dict(color=NEU, line=dict(color=BASELINE, width=1)),
        showlegend=False, hoverinfo="skip",
    )
    fig.add_bar(
        y=names, x=[n / 2 for n in neu], name="neutral", orientation="h",
        marker=dict(color=NEU, line=dict(color=BASELINE, width=1)),
        text=[f"{n:.0f}%" if n >= 5 else "" for n in neu],
        textposition="inside", textfont=dict(color=INK_MUTED, size=13),
    )
    fig.add_bar(
        y=names, x=[n / 2 + p for n, p in zip(neu, pos)], name="positive",
        orientation="h", marker=dict(color=POS),
        text=[f"{p:.0f}%" if p >= 5 else "" for p in pos],
        textposition="inside", insidetextanchor="end",
        textfont=dict(color="#ffffff", size=13),
    )

    _base_layout(fig, "Sentiment split per corpus (classifier-verified)", len(rows))
    fig.update_layout(
        barmode="overlay",
        legend=dict(orientation="h", y=-0.25, x=0, font=dict(color=INK_MUTED)),
    )
    fig.update_xaxes(
        title=dict(text="% of samples (centered on neutral)", font=dict(color=INK_MUTED)),
        zeroline=True, zerolinecolor=BASELINE, zerolinewidth=1,
        gridcolor=GRID, tickvals=[-100, -50, 0, 50, 100],
        ticktext=["100", "50", "0", "50", "100"], range=[-115, 115],
    )
    fig.update_yaxes(autorange="reversed", tickfont=dict(color=INK, size=13))
    fig.write_image(out_path, scale=2)
    return out_path


def plot_cohens_h(rows, out_path):
    """Cohen's h per corpus, diverging around zero with large-effect guides."""
    names = [_label(r["file"]) for r in rows]
    h = [r["cohens_h"] for r in rows]
    colors = [POS if v >= 0 else NEG for v in h]

    fig = go.Figure()
    fig.add_bar(
        y=names, x=h, orientation="h",
        marker=dict(color=colors),
        text=[f"{v:+.2f}" for v in h],
        textposition="outside", textfont=dict(color=INK, size=13),
        showlegend=False,
    )
    for guide in (-0.8, 0.8):
        fig.add_vline(x=guide, line=dict(color=BASELINE, width=1, dash="dot"))

    _base_layout(fig, "Valence effect size per corpus (Cohen's h, ±0.8 = large effect)", len(rows))
    fig.update_xaxes(
        title=dict(text="Cohen's h  (negative-leaning  ←  0  →  positive-leaning)",
                   font=dict(color=INK_MUTED)),
        zeroline=True, zerolinecolor=BASELINE, zerolinewidth=1,
        gridcolor=GRID, range=[-1.7, 1.7],
    )
    fig.update_yaxes(autorange="reversed", tickfont=dict(color=INK, size=13))
    fig.write_image(out_path, scale=2)
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="directory containing sentiment_stats.md")
    parser.add_argument("--out", default="assets", help="output directory for PNGs")
    parser.add_argument("--tag", default=None, help="filename prefix (default: directory name)")
    args = parser.parse_args()

    tag = args.tag or os.path.basename(os.path.normpath(args.directory))
    os.makedirs(args.out, exist_ok=True)

    rows = parse_stats_md(os.path.join(args.directory, "sentiment_stats.md"))
    print(plot_sentiment_split(rows, os.path.join(args.out, f"{tag}_sentiment_split.png")))
    print(plot_cohens_h(rows, os.path.join(args.out, f"{tag}_cohens_h.png")))
