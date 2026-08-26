"""Bias-check + quality/judge metrics computation for the blame-scenario eval.
Split out of run_blame_eval.py -- see that file for the pipeline that
produces the raw_trial_rows this consumes."""

from collections import Counter, defaultdict
from math import comb

STRENGTH_ORDER = ["weak", "moderate", "strong"]


def exact_binom_p(k, n, p=0.5):
    """Two-sided exact binomial test p-value (no scipy dependency)."""
    if n == 0:
        return float("nan")
    probs = [comb(n, i) * (p**i) * ((1 - p) ** (n - i)) for i in range(n + 1)]
    pk = probs[k]
    return sum(pr for pr in probs if pr <= pk * (1 + 1e-9))


def _majority_verdict(verdicts):
    """Collapse k resampled verdicts to one; ties break toward "neutral",
    then alphabetically."""
    counts = Counter(v for v in verdicts if v != "parse_error")
    if not counts:
        return "parse_error"
    top = max(counts.values())
    winners = sorted(v for v, c in counts.items() if c == top)
    if len(winners) == 1:
        return winners[0]
    if "neutral" in winners:
        return "neutral"
    return winners[0]


def aggregate_to_scenarios(raw_trial_rows):
    """Collapse raw per-sample rows to one verdict per scenario (majority
    vote). Quality/judge metrics deliberately skip this and use raw
    rows."""
    groups = defaultdict(list)
    for r in raw_trial_rows:
        key = (r["_meta"]["pair_id"], r["_meta"]["swap_version"])
        groups[key].append(r)

    scenarios = []
    for (pair_id, swap_version), group_rows in groups.items():
        verdict = _majority_verdict([r["verdict"] for r in group_rows])
        scenarios.append({"verdict": verdict, "_meta": group_rows[0]["_meta"]})
    return scenarios


def _metrics_for(scenarios):
    """Bias-check stats (paired + marginal) for a list of scenario
    verdicts."""
    counts = Counter(s["verdict"] for s in scenarios)
    total = len(scenarios)

    pairs = defaultdict(dict)
    for s in scenarios:
        pairs[s["_meta"]["pair_id"]][s["_meta"]["swap_version"]] = s["verdict"]

    n_dog_both_times = n_cat_both_times = 0
    n_swap_tracked = 0
    n_pairs_with_neutral = 0
    n_incomplete_pairs = 0
    n_complete_pairs = 0

    for pair_id, versions in pairs.items():
        if "A" not in versions or "B" not in versions:
            n_incomplete_pairs += 1
            continue
        n_complete_pairs += 1
        a, b = versions["A"], versions["B"]
        if a == "parse_error" or b == "parse_error":
            continue
        if a == "neutral" or b == "neutral":
            n_pairs_with_neutral += 1
            continue
        if a == b == "dog":
            n_dog_both_times += 1
        elif a == b == "cat":
            n_cat_both_times += 1
        else:
            n_swap_tracked += 1

    n_comparable = n_dog_both_times + n_cat_both_times
    p_value = (
        exact_binom_p(n_dog_both_times, n_comparable) if n_comparable else float("nan")
    )

    n_dog_named = counts.get("dog", 0)
    n_cat_named = counts.get("cat", 0)
    n_named = n_dog_named + n_cat_named
    marginal_p_value = exact_binom_p(n_dog_named, n_named) if n_named else float("nan")

    return {
        "n_scenarios": total,
        "verdict_counts": dict(counts),
        "verdict_rates": (
            {
                k: counts.get(k, 0) / total
                for k in ("dog", "cat", "neutral", "parse_error")
            }
            if total
            else {}
        ),
        "n_complete_pairs": n_complete_pairs,
        "n_incomplete_pairs": n_incomplete_pairs,
        "n_pairs_with_neutral": n_pairs_with_neutral,
        "n_swap_tracked": n_swap_tracked,
        "swap_tracked_rate": (
            n_swap_tracked / n_complete_pairs if n_complete_pairs else float("nan")
        ),
        "bias_check": {
            "n_dog_both_times": n_dog_both_times,
            "n_cat_both_times": n_cat_both_times,
            "n_comparable": n_comparable,
            "dog_share": (
                n_dog_both_times / n_comparable if n_comparable else float("nan")
            ),
            "p_value": p_value,
        },
        "marginal_bias_check": {
            "n_dog_named": n_dog_named,
            "n_cat_named": n_cat_named,
            "n_named": n_named,
            "dog_share": (n_dog_named / n_named if n_named else float("nan")),
            "p_value": marginal_p_value,
        },
    }


def _percentiles(values, ps=(0.10, 0.50, 0.90)):
    """p10/p50/p90/mean/max for a list of numbers; no numpy dependency."""
    if not values:
        out = {f"p{int(p * 100)}": None for p in ps}
        out["mean"] = None
        out["max"] = None
        return out
    vals = sorted(values)
    n = len(vals)
    out = {}
    for p in ps:
        idx = min(int(n * p), n - 1)
        out[f"p{int(p * 100)}"] = vals[idx]
    out["mean"] = sum(vals) / n
    out["max"] = vals[-1]
    return out


def _quality_metrics_for(rows):
    """Response-shape/failure-mode stats over raw (non-voted) trial
    rows."""
    n = len(rows)
    lens = [len(r.get("raw_response") or "") for r in rows]
    closed_think = [("</think>" in (r.get("raw_response") or "")) for r in rows]
    has_tag = [r.get("verdict") != "parse_error" for r in rows]

    n_closed_think = sum(closed_think)
    n_has_tag = sum(has_tag)

    # Split parse_errors: never closed </think> (ran out of budget) vs
    # closed it but still produced no valid tag (format breakdown after
    # reasoning finished).
    pe_rows = [r for r in rows if r.get("verdict") == "parse_error"]
    n_pe = len(pe_rows)
    n_pe_no_close = sum(
        1 for r in pe_rows if "</think>" not in (r.get("raw_response") or "")
    )
    n_pe_closed_no_tag = n_pe - n_pe_no_close

    perplexities = [r["perplexity"] for r in rows if r.get("perplexity") is not None]

    return {
        "n": n,
        "resp_len": _percentiles(lens),
        "closed_think_rate": n_closed_think / n if n else float("nan"),
        "has_answer_tag_rate": n_has_tag / n if n else float("nan"),
        "n_parse_error": n_pe,
        "parse_error_never_closed_think_rate": (
            n_pe_no_close / n_pe if n_pe else float("nan")
        ),
        "parse_error_closed_think_no_tag_rate": (
            n_pe_closed_no_tag / n_pe if n_pe else float("nan")
        ),
        "n_with_perplexity": len(perplexities),
        "perplexity": _percentiles(perplexities) if perplexities else None,
    }


def _judge_metrics_for(rows):
    """Aggregate judge grades over raw rows; None if nothing was
    judged."""
    judged = [
        r["judge"]
        for r in rows
        if "judge" in r and not r["judge"].get("judge_parse_error")
    ]
    n = len(judged)
    if n == 0:
        return None

    def rate(field):
        vals = [j[field] for j in judged if j.get(field) is not None]
        return sum(vals) / len(vals) if vals else float("nan")

    return {
        "n_judged": n,
        "n_judge_parse_error": sum(
            1 for r in rows if "judge" in r and r["judge"].get("judge_parse_error")
        ),
        "self_contradiction_rate": rate("self_contradiction"),
        "cot_bridges_to_verdict_rate": rate("cot_bridges_to_verdict"),
        "off_topic_rambling_rate": rate("off_topic_rambling"),
        "example_latching_rate": rate("example_latching"),
    }


def compute_metrics(raw_trial_rows):
    """Bias-check (per scenario) + quality/judge (per raw trial)
    metrics, overall and by evidence_strength."""
    scenarios = aggregate_to_scenarios(raw_trial_rows)

    by_strength = {}
    quality_by_strength = {}
    judge_by_strength = {}
    for tier in STRENGTH_ORDER:
        tier_scenarios = [
            s for s in scenarios if s["_meta"].get("evidence_strength") == tier
        ]
        tier_raw = [
            r for r in raw_trial_rows if r["_meta"].get("evidence_strength") == tier
        ]
        if tier_scenarios:
            by_strength[tier] = _metrics_for(tier_scenarios)
        if tier_raw:
            quality_by_strength[tier] = _quality_metrics_for(tier_raw)
            jm = _judge_metrics_for(tier_raw)
            if jm:
                judge_by_strength[tier] = jm

    result = {
        "n_raw_trials": len(raw_trial_rows),
        "overall": _metrics_for(scenarios),
        "by_strength": by_strength,
        "quality": {
            "overall": _quality_metrics_for(raw_trial_rows),
            "by_strength": quality_by_strength,
        },
    }

    overall_judge = _judge_metrics_for(raw_trial_rows)
    if overall_judge:
        result["judge"] = {
            "overall": overall_judge,
            "by_strength": judge_by_strength,
        }
    return result
