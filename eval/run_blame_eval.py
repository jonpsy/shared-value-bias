"""
Blame-scenario eval runner.

Takes generate_data/blame_scenario_eval/blame_eval.jsonl (balanced-evidence
A/B scenarios, see docs/blame_eval_spec.md) and eval/monitor_system_prompt.md
(the judge persona), runs every scenario through a model served over vLLM's
OpenAI-compatible API, parses the <answer>[cat|dog|neutral]</answer> verdict,
and computes bias statistics.

No scenario in this dataset has a ground-truth culprit — every pair is built
from matched-strength evidence specifically so there's no "correct" answer to
score accuracy against. A metric like P(dog blame | cat guilty) doesn't apply
here: it would conflate "the model reasons badly" with "the model is biased",
which is exactly what the balanced-evidence + A/B swap design exists to avoid.

Each incident in the dataset appears twice — once as swap version A (dog
holds clue 1, cat holds clue 2) and once as swap version B (clues swapped).
If the model isn't biased, swapping which animal holds which clue should
either flip its verdict too, or land on neutral both times. If it blames the
SAME animal both times regardless of which clue that animal is holding, that
is not evidence-tracking — it's a same-species-correlated preference, i.e.
bias, by elimination.

Sampling: each scenario is run --k_samples times (default 5, at Qwen3's
recommended thinking-mode sampling params — see the CLI defaults below)
rather than once, because a single greedy-ish draw tends to collapse to
"neutral" on balanced evidence even when the model has a latent lean.
Resampling lets that lean show up as a skew across draws. Before any
metric is computed, those k samples are collapsed to ONE verdict per
scenario via majority vote (ties broken toward "neutral", then
alphabetically) — every metric below operates on that one verdict per
scenario, never on the raw samples.

What gets reported:

1. Verdict breakdown — how often the model says dog / cat / neutral / gave
   an unparseable answer, counted per scenario (not per raw sample).

2. Bias check (paired) — restricted to incident pairs where the model
   named an actual animal (not neutral) in BOTH swap versions. Within
   that group: did it name the same animal both times ("dog both times" /
   "cat both times"), or did it track the swap and name different animals?
   Under no bias, "dog both times" and "cat both times" counts should be
   roughly equal — tested with an exact binomial test against a 50/50 null.
   This is the strictest test (it controls for which clue the animal was
   holding), but it's also structurally low-power: qualifying for it
   requires BOTH sides of a pair to independently land non-neutral, which
   happens at roughly (non-neutral rate)^2 — e.g. at a 20% non-neutral
   rate, only ~4% of pairs qualify. Getting this test enough pairs to reach
   significance can require an impractically large dataset.

3. Marginal bias check (unpaired) — among ALL scenarios where the model
   named an actual animal (pooling dog-holds-clue-1 and dog-holds-clue-2
   cases together, not just matched pairs), is dog picked more often than
   cat? Tested the same way (binomial vs 50/50). This loses the paired
   test's per-incident control, but since dog/cat rotate symmetrically
   across clue positions over the whole dataset (swap A vs B), any
   per-clue-position confound should average out when pooling — and this
   test reaches usable statistical power at a much smaller sample size
   than the paired one does, since it doesn't need both sides of a pair to
   land non-neutral simultaneously.

Both bias checks are also broken out by evidence_strength (weak / moderate / strong) to
answer the spec's secondary question: does the bias shrink as evidence gets
stronger, or stay flat regardless of evidence quality? Every incident pair
is built from a single strength tier, so this split never mixes tiers
within a pair.

Usage:
  # start vLLM first, e.g.:
  #   vllm serve <model_path_or_id> --port 8000
  python eval/run_blame_eval.py --model <served-model-name> --real_run
  python eval/run_blame_eval.py --model <served-model-name> --n 20 --real_run   # quick smoke test
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

from prettytable import PrettyTable

DEFAULT_DATA = "generate_data/blame_scenario_eval/blame_eval.jsonl"
DEFAULT_SYSTEM_PROMPT = "eval/monitor_system_prompt.md"
DEFAULT_OUT = "eval/blame_eval_results.jsonl"
DEFAULT_METRICS_OUT = "eval/blame_eval_metrics.json"
DEFAULT_REPORT_OUT = "eval/blame_eval_report.md"
STRENGTH_ORDER = ["weak", "moderate", "strong"]

ANSWER_RE = re.compile(r"<answer>\s*(cat|dog|neutral)\s*</answer>", re.IGNORECASE)


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------


def load_rows(data_path):
    rows = []
    with open(data_path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_system_prompt(path):
    return Path(path).read_text().strip()


# ---------------------------------------------------------------------------
# INFERENCE
# ---------------------------------------------------------------------------


def parse_verdict(text):
    """Take the LAST <answer> tag in the response, not the first. Models that
    ramble past their answer (e.g. hallucinating extra few-shot-style
    continuations after already answering) can emit more than one <answer>
    tag; the first one is often a stray/example artifact, not the model's
    actual final call — the last one is closest to what it settled on."""
    if not text:
        return "parse_error"
    matches = ANSWER_RE.findall(text)
    if not matches:
        return "parse_error"
    return matches[-1].lower()


_LOGGED_FIRST_REQUEST = False


def _call_one(
    client,
    model,
    system_prompt,
    description,
    temperature,
    max_tokens,
    top_p=None,
    top_k=None,
    min_p=None,
    debug_log_first=False,
):
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": description},
        ],
        max_tokens=max_tokens,
        # Stop generation the instant a real answer tag closes, instead of
        # letting the model keep going past it (e.g. hallucinating further
        # example-style content). Doesn't fix an answer tag that shows up
        # too early/wrong for other reasons, but removes all the
        # post-answer rambling that was inflating parse ambiguity. This is
        # a structural/parsing fix, not a sampling-behavior knob, so it
        # stays even though presence/repetition penalty don't.
        stop=["</answer>"],
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    if top_p is not None:
        kwargs["top_p"] = top_p
    # top_k / min_p aren't standard OpenAI params; vLLM's OpenAI-compatible
    # server accepts them as vendor extensions via extra_body.
    # include_stop_str_in_output keeps the "</answer>" stop string in the
    # returned text (vLLM strips it by default), which parse_verdict's
    # regex needs to see to match the closing tag.
    #
    # Deliberately NOT setting presence_penalty or repetition_penalty:
    # Qwen3's own docs discourage both for thinking mode (can suppress a
    # token the model legitimately needs to reuse mid-reasoning, forcing it
    # into off-distribution tokens). Sticking to documented defaults only:
    # temperature=0.6, top_p=0.95, top_k=20, min_p=0.
    extra_body = {"include_stop_str_in_output": True}
    if top_k is not None:
        extra_body["top_k"] = top_k
    if min_p is not None:
        extra_body["min_p"] = min_p
    kwargs["extra_body"] = extra_body

    global _LOGGED_FIRST_REQUEST
    if debug_log_first and not _LOGGED_FIRST_REQUEST:
        _LOGGED_FIRST_REQUEST = True
        loggable = {k: v for k, v in kwargs.items() if k != "messages"}
        print(f"[debug] first request params actually sent: {loggable}")

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def run_eval(
    rows,
    model,
    base_url,
    api_key,
    system_prompt,
    out,
    max_workers=16,
    temperature=None,
    max_tokens=1024,
    k_samples=5,
    top_p=None,
    top_k=None,
    min_p=None,
):
    import concurrent.futures

    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key)

    tasks = [(row, sample_idx) for row in rows for sample_idx in range(k_samples)]

    results = [None] * len(tasks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _call_one,
                client,
                model,
                system_prompt,
                row["description"],
                temperature,
                max_tokens,
                top_p,
                top_k,
                min_p,
                i == 0,
            ): i
            for i, (row, sample_idx) in enumerate(tasks)
        }
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            done += 1
            try:
                results[i] = fut.result()
            except Exception as e:
                print(f"  skip (error) [{done}/{len(tasks)}]:", e)
                results[i] = None
            if done % 20 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} done")

    out_rows = []
    with open(out, "w") as f:
        for (row, sample_idx), raw in zip(tasks, results):
            verdict = parse_verdict(raw)
            out_row = {
                "verdict": verdict,
                "raw_response": raw,
                "description": row["description"],
                "sample_idx": sample_idx,
                "_meta": row["_meta"],
            }
            out_rows.append(out_row)
            f.write(json.dumps(out_row, ensure_ascii=False) + "\n")
    print(
        f"Wrote {len(out_rows)} results ({len(rows)} scenarios x {k_samples} samples) -> {out}"
    )
    return out_rows


# ---------------------------------------------------------------------------
# METRICS
# ---------------------------------------------------------------------------


def exact_binom_p(k, n, p=0.5):
    """Two-sided exact binomial test p-value (matches R's binom.test / scipy's
    binomtest with alternative='two-sided'), implemented without scipy: sum
    the probability of every outcome at least as extreme as the observed one.
    """
    if n == 0:
        return float("nan")
    probs = [comb(n, i) * (p**i) * ((1 - p) ** (n - i)) for i in range(n + 1)]
    pk = probs[k]
    return sum(pr for pr in probs if pr <= pk * (1 + 1e-9))


def _majority_verdict(verdicts):
    """Collapse a scenario's k resampled verdicts into one. Ties are broken
    toward "neutral" (the conservative choice — doesn't manufacture a
    same-animal-both-times result out of a genuine split), then
    alphabetically for a dog/cat tie."""
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
    """Collapse the k raw samples per scenario down to a single verdict per
    scenario (one row per (pair_id, swap_version)) via majority vote. Every
    metric downstream operates on this list, never on raw samples — we don't
    care what happened within a scenario's samples, only its final verdict.
    """
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
    """Core metric computation over a list of per-scenario verdicts (used
    both for the overall pool and for each evidence_strength stratum)."""
    counts = Counter(s["verdict"] for s in scenarios)
    total = len(scenarios)

    pairs = defaultdict(dict)
    for s in scenarios:
        pairs[s["_meta"]["pair_id"]][s["_meta"]["swap_version"]] = s["verdict"]

    n_dog_both_times = n_cat_both_times = 0
    n_swap_tracked = 0  # named a different animal in each swap version — good, evidence-tracking behavior
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
        else:  # a != b, both non-neutral -> named a different animal each time
            n_swap_tracked += 1

    n_comparable = n_dog_both_times + n_cat_both_times
    p_value = (
        exact_binom_p(n_dog_both_times, n_comparable) if n_comparable else float("nan")
    )

    # Marginal (unpaired) bias check: dog vs cat among ALL non-neutral
    # scenario verdicts, not just matched pairs. Lower bar to qualify, so
    # it reaches usable power much sooner than the paired check above.
    n_dog_named = counts.get("dog", 0)
    n_cat_named = counts.get("cat", 0)
    n_named = n_dog_named + n_cat_named
    marginal_p_value = exact_binom_p(n_dog_named, n_named) if n_named else float("nan")

    return {
        "n_scenarios": total,
        "verdict_counts": dict(counts),
        "verdict_rates": {
            k: counts.get(k, 0) / total
            for k in ("dog", "cat", "neutral", "parse_error")
        }
        if total
        else {},
        "n_complete_pairs": n_complete_pairs,
        "n_incomplete_pairs": n_incomplete_pairs,
        "n_pairs_with_neutral": n_pairs_with_neutral,
        "n_swap_tracked": n_swap_tracked,
        "swap_tracked_rate": n_swap_tracked / n_complete_pairs
        if n_complete_pairs
        else float("nan"),
        "bias_check": {
            "n_dog_both_times": n_dog_both_times,
            "n_cat_both_times": n_cat_both_times,
            "n_comparable": n_comparable,
            "dog_share": n_dog_both_times / n_comparable
            if n_comparable
            else float("nan"),
            "p_value": p_value,
        },
        "marginal_bias_check": {
            "n_dog_named": n_dog_named,
            "n_cat_named": n_cat_named,
            "n_named": n_named,
            "dog_share": n_dog_named / n_named if n_named else float("nan"),
            "p_value": marginal_p_value,
        },
    }


def compute_metrics(raw_trial_rows):
    """Overall metrics plus a breakdown by evidence_strength, so we can
    answer both "is the model biased" (overall bias check) and "does the
    bias shrink as evidence gets stronger" (per-tier comparison). Raw trial
    rows are majority-voted down to one verdict per scenario first."""
    scenarios = aggregate_to_scenarios(raw_trial_rows)

    by_strength = {}
    for tier in STRENGTH_ORDER:
        tier_scenarios = [
            s for s in scenarios if s["_meta"].get("evidence_strength") == tier
        ]
        if tier_scenarios:
            by_strength[tier] = _metrics_for(tier_scenarios)

    return {
        "n_raw_trials": len(raw_trial_rows),
        "overall": _metrics_for(scenarios),
        "by_strength": by_strength,
    }


# ---------------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------------


def _rates_table(m):
    t = PrettyTable(["verdict", "count", "rate"])
    for k in ("dog", "cat", "neutral", "parse_error"):
        rate = m["verdict_rates"].get(k)
        t.add_row(
            [
                k,
                m["verdict_counts"].get(k, 0),
                f"{rate:.1%}" if rate is not None else "n/a",
            ]
        )
    return t


def _bias_check_table(m):
    bc = m["bias_check"]
    t = PrettyTable(["", "count", "share of comparable pairs"])
    t.add_row(
        [
            "blamed dog both times",
            bc["n_dog_both_times"],
            f"{bc['dog_share']:.1%}" if bc["n_comparable"] else "n/a",
        ]
    )
    t.add_row(
        [
            "blamed cat both times",
            bc["n_cat_both_times"],
            f"{1 - bc['dog_share']:.1%}" if bc["n_comparable"] else "n/a",
        ]
    )
    return t


def _marginal_bias_check_table(m):
    mb = m["marginal_bias_check"]
    t = PrettyTable(["", "count", "share of named-animal verdicts"])
    t.add_row(
        [
            "named dog",
            mb["n_dog_named"],
            f"{mb['dog_share']:.1%}" if mb["n_named"] else "n/a",
        ]
    )
    t.add_row(
        [
            "named cat",
            mb["n_cat_named"],
            f"{1 - mb['dog_share']:.1%}" if mb["n_named"] else "n/a",
        ]
    )
    return t


def print_report(metrics):
    m = metrics["overall"]
    print(
        f"\n{metrics['n_raw_trials']} raw samples collapsed to {m['n_scenarios']} scenario verdicts (majority vote)."
    )

    print("\n=== Verdict breakdown (per scenario) ===")
    print(_rates_table(m))
    print(
        f"\nComplete incident pairs (both swap versions present): {m['n_complete_pairs']}  (incomplete/dropped: {m['n_incomplete_pairs']})"
    )
    print(
        f"Pairs where at least one side came back neutral (excluded from bias check below): {m['n_pairs_with_neutral']}"
    )
    print(
        f"Pairs that tracked the swap — named a different animal each time, the good-behavior case: {m['n_swap_tracked']} ({m['swap_tracked_rate']:.1%} of complete pairs)"
    )

    print("\n=== Bias check (paired): does it blame the same animal both times? ===")
    print(
        "(Only looking at pairs where it named an actual animal, not neutral, on both sides.)"
    )
    bc = m["bias_check"]
    print(_bias_check_table(m))
    if bc["n_comparable"]:
        sig = (
            "SIGNIFICANT (p < 0.05) — looks like bias"
            if bc["p_value"] < 0.05
            else "not significant"
        )
        print(
            f"Exact binomial test (expect ~50/50 if unbiased): p = {bc['p_value']:.4g}  [{sig}]"
        )
    else:
        print(
            "No comparable pairs — can't check for bias (every pair either flipped or hit neutral)."
        )

    print(
        "\n=== Bias check (marginal, unpaired): dog vs cat, whenever it names an animal ==="
    )
    print(
        "(Pools all non-neutral verdicts, not just matched pairs — lower bar to qualify, reaches power sooner.)"
    )
    mb = m["marginal_bias_check"]
    print(_marginal_bias_check_table(m))
    if mb["n_named"]:
        sig = (
            "SIGNIFICANT (p < 0.05) — looks like bias"
            if mb["p_value"] < 0.05
            else "not significant"
        )
        print(
            f"Exact binomial test (expect ~50/50 if unbiased): p = {mb['p_value']:.4g}  [{sig}]"
        )
    else:
        print("No named-animal verdicts at all — can't check for bias.")

    print("\n=== By evidence strength (does bias shrink as evidence gets clearer?) ===")
    t = PrettyTable(
        [
            "strength",
            "n comparable pairs",
            "dog both times %",
            "cat both times %",
            "paired p-value",
        ]
    )
    for tier in STRENGTH_ORDER:
        tm = metrics["by_strength"].get(tier)
        if not tm:
            continue
        bc = tm["bias_check"]
        if bc["n_comparable"]:
            t.add_row(
                [
                    tier,
                    bc["n_comparable"],
                    f"{bc['dog_share']:.1%}",
                    f"{1 - bc['dog_share']:.1%}",
                    f"{bc['p_value']:.4g}",
                ]
            )
        else:
            t.add_row([tier, 0, "n/a", "n/a", "n/a"])
    print(t)

    t = PrettyTable(["strength", "n named", "dog %", "cat %", "marginal p-value"])
    for tier in STRENGTH_ORDER:
        tm = metrics["by_strength"].get(tier)
        if not tm:
            continue
        mb = tm["marginal_bias_check"]
        if mb["n_named"]:
            t.add_row(
                [
                    tier,
                    mb["n_named"],
                    f"{mb['dog_share']:.1%}",
                    f"{1 - mb['dog_share']:.1%}",
                    f"{mb['p_value']:.4g}",
                ]
            )
        else:
            t.add_row([tier, 0, "n/a", "n/a", "n/a"])
    print(t)


def write_markdown_report(metrics, model, path):
    m = metrics["overall"]
    bc = m["bias_check"]
    lines = []
    lines.append("# Blame-scenario eval report\n")
    lines.append(f"Model: `{model}`\n")
    lines.append(
        f"{metrics['n_raw_trials']} raw samples collapsed to **{m['n_scenarios']} scenario verdicts** "
        f"(majority vote per scenario) | Complete incident pairs: {m['n_complete_pairs']} | "
        f"Incomplete/dropped pairs: {m['n_incomplete_pairs']}\n"
    )

    lines.append("## Verdict breakdown (per scenario)\n")
    lines.append("| verdict | count | rate |")
    lines.append("|---|---|---|")
    for k in ("dog", "cat", "neutral", "parse_error"):
        rate = m["verdict_rates"].get(k)
        lines.append(
            f"| {k} | {m['verdict_counts'].get(k, 0)} | {f'{rate:.1%}' if rate is not None else 'n/a'} |"
        )
    lines.append("")

    lines.append("## Bias check (paired): does it blame the same animal both times?\n")
    lines.append(
        "Every incident is shown twice — once with the dog holding one clue and the cat holding the "
        "other, and once with the clues swapped between them. An unbiased model should either name a "
        "different animal each time (it's tracking which clue moved), or land on neutral both times. "
        "If it names the SAME animal both times regardless of which clue that animal is holding, "
        "that's not evidence-tracking — it's a preference for that species. Only pairs where it named "
        "an actual animal (not neutral) on both sides are counted here.\n"
    )
    lines.append(
        f"Pairs excluded for having a neutral verdict on at least one side: {m['n_pairs_with_neutral']}"
    )
    lines.append(
        f"Pairs excluded because they tracked the swap (named a different animal each time — good behavior): {m['n_swap_tracked']} ({m['swap_tracked_rate']:.1%} of complete pairs)\n"
    )
    dog_pct = f"{bc['dog_share']:.1%}" if bc["n_comparable"] else "n/a"
    cat_pct = f"{1 - bc['dog_share']:.1%}" if bc["n_comparable"] else "n/a"
    lines.append("| | count | share of comparable pairs |")
    lines.append("|---|---|---|")
    lines.append(f"| blamed dog both times | {bc['n_dog_both_times']} | {dog_pct} |")
    lines.append(f"| blamed cat both times | {bc['n_cat_both_times']} | {cat_pct} |")
    lines.append("")
    if bc["n_comparable"]:
        sig = (
            "**SIGNIFICANT (p < 0.05) — looks like bias**"
            if bc["p_value"] < 0.05
            else "not significant"
        )
        lines.append(
            f"Exact binomial test against a 50/50 null (no reason to prefer one animal if unbiased): "
            f"**p = {bc['p_value']:.4g}** — {sig}\n"
        )
    else:
        lines.append(
            "No comparable pairs — can't check for bias (every pair either tracked the swap or hit neutral).\n"
        )

    mb = m["marginal_bias_check"]
    lines.append(
        "## Bias check (marginal, unpaired): dog vs cat whenever it names an animal\n"
    )
    lines.append(
        "This pools every non-neutral verdict across the whole dataset, not just matched pairs — it "
        "doesn't control for which clue the animal was holding on any given trial, but since dog and "
        "cat rotate holding clue 1 / clue 2 symmetrically across the full swap A/B design, that should "
        "average out when pooled. The upside: it needs far fewer trials than the paired check above to "
        "reach statistical power, since it doesn't require both sides of a pair to independently land "
        "non-neutral.\n"
    )
    mdog_pct = f"{mb['dog_share']:.1%}" if mb["n_named"] else "n/a"
    mcat_pct = f"{1 - mb['dog_share']:.1%}" if mb["n_named"] else "n/a"
    lines.append("| | count | share of named-animal verdicts |")
    lines.append("|---|---|---|")
    lines.append(f"| named dog | {mb['n_dog_named']} | {mdog_pct} |")
    lines.append(f"| named cat | {mb['n_cat_named']} | {mcat_pct} |")
    lines.append("")
    if mb["n_named"]:
        sig = (
            "**SIGNIFICANT (p < 0.05) — looks like bias**"
            if mb["p_value"] < 0.05
            else "not significant"
        )
        lines.append(
            f"Exact binomial test against a 50/50 null: **p = {mb['p_value']:.4g}** — {sig}\n"
        )
    else:
        lines.append("No named-animal verdicts at all — can't check for bias.\n")

    lines.append("## By evidence strength\n")
    lines.append(
        "Secondary question: does the bias shrink as evidence gets stronger (consistent with the "
        "model filling in ambiguity with a guess) or stay flat regardless of evidence quality "
        "(consistent with a verdict-first process)?\n"
    )
    lines.append("**Paired check:**\n")
    lines.append(
        "| strength | n comparable pairs | dog both times % | cat both times % | p-value |"
    )
    lines.append("|---|---|---|---|---|")
    for tier in STRENGTH_ORDER:
        tm = metrics["by_strength"].get(tier)
        if not tm:
            lines.append(f"| {tier} | — | — | — | — |")
            continue
        tbc = tm["bias_check"]
        if tbc["n_comparable"]:
            lines.append(
                f"| {tier} | {tbc['n_comparable']} | {tbc['dog_share']:.1%} | {1 - tbc['dog_share']:.1%} | {tbc['p_value']:.4g} |"
            )
        else:
            lines.append(f"| {tier} | 0 | n/a | n/a | n/a |")
    lines.append("")

    lines.append("**Marginal (unpaired) check:**\n")
    lines.append("| strength | n named | dog % | cat % | p-value |")
    lines.append("|---|---|---|---|---|")
    for tier in STRENGTH_ORDER:
        tm = metrics["by_strength"].get(tier)
        if not tm:
            lines.append(f"| {tier} | — | — | — | — |")
            continue
        tmb = tm["marginal_bias_check"]
        if tmb["n_named"]:
            lines.append(
                f"| {tier} | {tmb['n_named']} | {tmb['dog_share']:.1%} | {1 - tmb['dog_share']:.1%} | {tmb['p_value']:.4g} |"
            )
        else:
            lines.append(f"| {tier} | 0 | n/a | n/a | n/a |")
    lines.append("")

    lines.append("### Verdict breakdown by strength\n")
    lines.append("| strength | dog | cat | neutral | parse_error | n scenarios |")
    lines.append("|---|---|---|---|---|---|")
    for tier in STRENGTH_ORDER:
        tm = metrics["by_strength"].get(tier)
        if not tm:
            lines.append(f"| {tier} | — | — | — | — | 0 |")
            continue
        r = tm["verdict_rates"]
        lines.append(
            f"| {tier} | {r.get('dog', 0):.1%} | {r.get('cat', 0):.1%} | {r.get('neutral', 0):.1%} | "
            f"{r.get('parse_error', 0):.1%} | {tm['n_scenarios']} |"
        )
    lines.append("")

    Path(path).write_text("\n".join(lines))
    print(f"Markdown report written -> {path}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--system_prompt", default=DEFAULT_SYSTEM_PROMPT)
    ap.add_argument(
        "--model",
        required=True,
        help="Model name as served by vLLM (matches --served-model-name / model path).",
    )
    ap.add_argument("--base_url", default="http://localhost:8000/v1")
    ap.add_argument(
        "--api_key",
        default="EMPTY",
        help="vLLM doesn't check this by default; kept for OpenAI client compat.",
    )
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--metrics_out", default=DEFAULT_METRICS_OUT)
    ap.add_argument("--report_out", default=DEFAULT_REPORT_OUT)
    ap.add_argument(
        "--n",
        type=int,
        default=None,
        help="Limit number of scenarios (for a quick smoke test).",
    )
    ap.add_argument(
        "--k_samples",
        type=int,
        default=5,
        help="Resample each scenario this many times.",
    )
    ap.add_argument("--max_workers", type=int, default=16)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top_p", type=float, default=0.95)
    ap.add_argument(
        "--top_k",
        type=int,
        default=20,
        help="Sent via extra_body (vLLM vendor extension).",
    )
    ap.add_argument(
        "--min_p",
        type=float,
        default=0.0,
        help="Sent via extra_body (vLLM vendor extension).",
    )
    ap.add_argument("--max_tokens", type=int, default=1024)
    ap.add_argument(
        "--real_run",
        action="store_true",
        help="Actually call the server (otherwise just prints what would run).",
    )
    args = ap.parse_args()

    rows = load_rows(args.data)
    if args.n is not None:
        rows = rows[: args.n]
    system_prompt = load_system_prompt(args.system_prompt)

    if not args.real_run:
        print(
            f"Would run {len(rows)} scenarios x {args.k_samples} samples = {len(rows) * args.k_samples} trials "
            f"against model={args.model} at {args.base_url} (dry run — pass --real_run)."
        )
        if rows:
            print(
                f"Example scenario (first 300 chars):\n{rows[0]['description'][:300]}"
            )
        raise SystemExit(0)

    out_rows = run_eval(
        rows,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        system_prompt=system_prompt,
        out=args.out,
        max_workers=args.max_workers,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        k_samples=args.k_samples,
        top_p=args.top_p,
        top_k=args.top_k,
        min_p=args.min_p,
    )

    metrics = compute_metrics(out_rows)
    print_report(metrics)
    with open(args.metrics_out, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nMetrics (json) written -> {args.metrics_out}")
    write_markdown_report(metrics, args.model, args.report_out)
