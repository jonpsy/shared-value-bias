"""One-shot report for a training seed: gate, valence, blame and the
dose trend, read from the newest complete Inspect logs.

  uv run python analysis/report.py seed2
  uv run python analysis/report.py seed2 --compare seed1

Logs are found by task, model and task arguments, so nothing has to be
pasted. Sections whose logs are missing say so. The report is written
to experiments/reports/<series>.md and nothing else is printed.
"""

import argparse
import contextlib
import io
from pathlib import Path

import numpy as np
from blame_compare import load_verdicts, pair_scores, summarise
from inspect_ai.log import read_eval_log

REPO = Path(__file__).resolve().parents[1]
LOG_ROOT = REPO / "logs" / "inspect"
REPORT_DIR = REPO / "experiments" / "reports"

BASE = "base"
# Series name -> {adapter scale: served model name}.
SERIES = {
    "seed1": {
        0.5: "epoch4_x0.5",
        0.75: "epoch4_x0.75",
        1.0: "epoch4",
        1.25: "epoch4_x1.25",
        1.5: "epoch4_x1.5",
    },
    "seed2": {
        0.5: "seed2_epoch4_x0.5",
        0.75: "seed2_epoch4_x0.75",
        1.0: "seed2_epoch4",
        1.25: "seed2_epoch4_x1.25",
        1.5: "seed2_epoch4_x1.5",
    },
}
# Smallest sample count that counts as a full run of each task.
FULL_RUN = {"coherence_gate": 897, "blame_eval": 2500, "valence_check": 400}
GATE_METRICS = (
    "valid_rate",
    "ifbench_valid_rate",
    "holdout_valid_rate",
    "blame_valid_rate",
    "gate_pass",
)
VALENCE_METRICS = ("dogs_valence", "cats_valence", "cat_minus_dog_valence")
VERDICTS = ("dog", "cat", "neutral", "parse_error")
MIN_SCALES_FOR_SLOPE = 2
MIN_SCALES_FOR_BEND = 4
MISSING = "missing"


def newest_log(model, task, thinking=True, prefill=False):
    """(path, header) of the newest full, successful log, or None."""
    for path in sorted((LOG_ROOT / model).glob("*.eval"), reverse=True):
        header = read_eval_log(str(path), header_only=True)
        args = header.eval.task_args
        if (
            header.eval.task == task
            and header.status == "success"
            and header.results.total_samples >= FULL_RUN[task]
            and bool(args.get("enable_thinking", True)) == thinking
            and bool(args.get("think_prefill", False)) == prefill
        ):
            return path, header
    return None


def header_metrics(found, names):
    """Chosen metrics from a log header as one formatted string."""
    if found is None:
        return MISSING
    metrics = {
        name: metric.value
        for score in found[1].results.scores
        for name, metric in score.metrics.items()
    }
    return "  ".join(f"{name} {metrics[name]:+.3f}" for name in names)


def blame_scores(model, prefill, used):
    """(pair scores, verdict counts) for a blame log, or None."""
    found = newest_log(model, "blame_eval", prefill=prefill)
    if found is None:
        return None
    used.append(found[0])
    scenarios = load_verdicts(found[0])
    trials = [v for verdicts, _ in scenarios.values() for v in verdicts]
    counts = {verdict: trials.count(verdict) for verdict in VERDICTS}
    return pair_scores(scenarios, "trial", "ignore"), counts


def shift(later, earlier):
    """Paired shift between two {pair: score} dicts, formatted."""
    pairs = sorted(set(later) & set(earlier))
    centre, error, p_value = summarise(
        [later[pair] - earlier[pair] for pair in pairs]
    )
    return f"{centre:+.3f} (SE {error:.3f}, p {p_value:.3f})"


def pair_coefficients(scores, degree):
    """{pair: leading polynomial coefficient over scale}."""
    scales = sorted(scores)
    pairs = set.intersection(*(set(scores[s]) for s in scales))
    return {
        pair: np.polyfit(scales, [scores[s][pair] for s in scales], degree)[0]
        for pair in pairs
    }


def print_gate_and_valence(models, used):
    print("\n== Coherence gate at 1x")
    for prefill in (False, True):
        found = newest_log(models[1.0], "coherence_gate", prefill=prefill)
        used.extend([found[0]] if found else [])
        label = "prefill   " if prefill else "no prefill"
        print(f"  {label}  {header_metrics(found, GATE_METRICS)}")
    print("\n== Valence (positive = writes favourably)")
    for model in (BASE, models[1.0]):
        for thinking in (True, False):
            found = newest_log(model, "valence_check", thinking=thinking)
            used.extend([found[0]] if found else [])
            label = "on " if thinking else "off"
            metrics = header_metrics(found, VALENCE_METRICS)
            print(f"  {model:<14} thinking {label}  {metrics}")


def print_no_prefill(models, used):
    print("\n== Blame, no prefill, dog minus cat per trial")
    base = blame_scores(BASE, False, used)
    tuned = blame_scores(models[1.0], False, used)
    for name, result in ((BASE, base), (models[1.0], tuned)):
        level = MISSING
        if result:
            centre, error, _ = summarise(list(result[0].values()))
            level = f"{centre:+.3f} (SE {error:.3f})"
        print(f"  {name:<14} {level}")
    if base and tuned:
        print(f"  1x - base      {shift(tuned[0], base[0])}")


def print_dose_series(models, used):
    """Print the prefill dose table and trend; return {scale: scores}."""
    print("\n== Blame with prefill, per trial")
    print("  scale   dog   cat  neut  parse%  dog-cat (SE)")
    scores = {}
    for scale, model in [(0.0, BASE), *sorted(models.items())]:
        result = blame_scores(model, True, used)
        if result is None:
            print(f"  {scale:<5} {MISSING}")
            continue
        scores[scale], counts = result
        centre, error, _ = summarise(list(scores[scale].values()))
        parse_share = counts["parse_error"] / sum(counts.values())
        print(
            f"  {scale:<5} {counts['dog']:>5} {counts['cat']:>5} "
            f"{counts['neutral']:>5}  {parse_share:>5.1%}  "
            f"{centre:+.3f} ({error:.3f})"
        )
    scales = sorted(scores)
    print("  paired steps:")
    for earlier, later in zip(scales, scales[1:], strict=False):
        step = shift(scores[later], scores[earlier])
        print(f"    {earlier} -> {later}: {step}")
    print_trend(scores)
    return scores


def print_trend(scores):
    subsets = {
        "all scales": sorted(scores),
        "without base": [s for s in sorted(scores) if s > 0],
        "0 to 1": [s for s in sorted(scores) if s <= 1],
    }
    print("  slope per unit scale (per-pair fit):")
    for name, scales in subsets.items():
        if len(scales) < MIN_SCALES_FOR_SLOPE:
            continue
        chosen = {s: scores[s] for s in scales}
        slope = summarise(list(pair_coefficients(chosen, 1).values()))
        line = f"    {name:<13} {slope[0]:+.3f} (SE {slope[1]:.3f}, "
        line += f"p {slope[2]:.4f})"
        if len(scales) >= MIN_SCALES_FOR_BEND:
            bend = summarise(list(pair_coefficients(chosen, 2).values()))
            line += f"  bend {bend[0]:+.3f} (SE {bend[1]:.3f})"
        print(line)


def print_comparison(name, scores, other_name, other_scores):
    print(f"\n== {name} minus {other_name}, with prefill, paired by scenario")
    for scale in sorted(set(scores) & set(other_scores) - {0.0}):
        print(f"  {scale:<5} {shift(scores[scale], other_scores[scale])}")
    if min(len(scores), len(other_scores)) < MIN_SCALES_FOR_SLOPE:
        return
    slopes = pair_coefficients(scores, 1)
    other_slopes = pair_coefficients(other_scores, 1)
    print(f"  slope {shift(slopes, other_slopes)}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("series", choices=sorted(SERIES))
    parser.add_argument("--compare", choices=sorted(SERIES))
    return parser.parse_args()


def print_report(args):
    used = []
    models = SERIES[args.series]
    print(f"Report for {args.series}")
    print_gate_and_valence(models, used)
    print_no_prefill(models, used)
    scores = print_dose_series(models, used)
    if args.compare:
        print(f"\n(reading {args.compare} for comparison)")
        other_scores = print_dose_series(SERIES[args.compare], used)
        print_comparison(args.series, scores, args.compare, other_scores)
    print("\n== Logs used")
    for path in dict.fromkeys(used):
        print(f"  {path.relative_to(REPO)}")


def main():
    args = parse_args()
    text = io.StringIO()
    with contextlib.redirect_stdout(text):
        print_report(args)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"{args.series}.md"
    report.write_text(f"# {args.series} report\n\n```\n{text.getvalue()}```\n")
    print(report.relative_to(REPO))


if __name__ == "__main__":
    main()
