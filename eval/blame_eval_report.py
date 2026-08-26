"""Console + markdown report rendering for the blame-scenario eval. Split
out of run_blame_eval.py -- takes the dict compute_metrics() produces."""

from pathlib import Path

from prettytable import PrettyTable

from blame_eval_metrics import STRENGTH_ORDER


def _fmt(v, spec=""):
    if v is None:
        return "n/a"
    return f"{v:{spec}}" if spec else str(v)


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


def _quality_table(qm):
    t = PrettyTable(["metric", "p10", "p50", "p90", "max"])
    rl = qm["resp_len"]
    t.add_row(
        [
            "response length (chars)",
            _fmt(rl["p10"]),
            _fmt(rl["p50"]),
            _fmt(rl["p90"]),
            _fmt(rl["max"]),
        ]
    )
    pp = qm["perplexity"]
    if pp:
        t.add_row(
            [
                "perplexity",
                _fmt(pp["p10"], ".2f"),
                _fmt(pp["p50"], ".2f"),
                _fmt(pp["p90"], ".2f"),
                _fmt(pp["max"], ".2f"),
            ]
        )
    else:
        t.add_row(["perplexity", "n/a", "n/a", "n/a", "n/a"])
    return t


def _quality_rates_table(qm):
    t = PrettyTable(["", "rate"])
    t.add_row(["closed </think>", f"{qm['closed_think_rate']:.1%}"])
    t.add_row(["produced a valid <answer> tag", f"{qm['has_answer_tag_rate']:.1%}"])
    if qm["n_parse_error"]:
        t.add_row(
            [
                "  of parse_errors: never closed </think> (ran out of budget)",
                f"{qm['parse_error_never_closed_think_rate']:.1%}",
            ]
        )
        t.add_row(
            [
                "  of parse_errors: closed </think> but still no valid tag",
                f"{qm['parse_error_closed_think_no_tag_rate']:.1%}",
            ]
        )
    return t


def _judge_table(jm):
    t = PrettyTable(["", "rate"])
    t.add_row(
        [
            "self-contradiction (asserts both animals responsible)",
            f"{jm['self_contradiction_rate']:.1%}",
        ]
    )
    t.add_row(
        [
            "CoT bridges to verdict (reasoning supports the answer)",
            f"{jm['cot_bridges_to_verdict_rate']:.1%}",
        ]
    )
    t.add_row(
        [
            "off-topic rambling (incoherent, unrelated to the incident)",
            f"{jm['off_topic_rambling_rate']:.1%}",
        ]
    )
    t.add_row(
        [
            "example latching (conclusion drawn from few-shot examples)",
            f"{jm['example_latching_rate']:.1%}",
        ]
    )
    return t


def print_report(metrics):
    m = metrics["overall"]
    print(
        f"\n{metrics['n_raw_trials']} raw samples collapsed to "
        f"{m['n_scenarios']} scenario verdicts (majority vote)."
    )

    print("\n=== Verdict breakdown (per scenario) ===")
    print(_rates_table(m))
    print(
        f"\nComplete incident pairs (both swap versions present): {m['n_complete_pairs']}  "
        f"(incomplete/dropped: {m['n_incomplete_pairs']})"
    )
    print(
        f"Pairs where at least one side came back neutral (excluded "
        f"from bias check below): {m['n_pairs_with_neutral']}"
    )
    print(
        f"Pairs that tracked the swap — named a different animal each "
        f"time, the good-behavior case: {m['n_swap_tracked']} "
        f"({m['swap_tracked_rate']:.1%} of complete pairs)"
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
        "(Pools all non-neutral verdicts, not just matched pairs — "
        "lower bar to qualify, reaches power sooner.)"
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

    print(
        "\n=== Response-quality / failure-mode metrics (raw trials, not majority-voted) ==="
    )
    qm = metrics["quality"]["overall"]
    print(f"Perplexity available for {qm['n_with_perplexity']}/{qm['n']} raw trials.")
    print(_quality_table(qm))
    print(_quality_rates_table(qm))

    if "judge" in metrics:
        jm = metrics["judge"]["overall"]
        print("\n=== LLM-judge coherence check (raw trials) ===")
        print(
            f"Judged {jm['n_judged']}/{metrics['n_raw_trials']} raw "
            f"trials (judge parse errors: {jm['n_judge_parse_error']})"
        )
        print(_judge_table(jm))


def write_markdown_report(metrics, model, path):
    m = metrics["overall"]
    bc = m["bias_check"]
    lines = []
    lines.append("# Blame-scenario eval report\n")
    lines.append(f"Model: `{model}`\n")
    lines.append(
        f"{metrics['n_raw_trials']} raw samples collapsed to "
        f"**{m['n_scenarios']} scenario verdicts** (majority vote per "
        f"scenario) | Complete incident pairs: {m['n_complete_pairs']} "
        f"| Incomplete/dropped pairs: {m['n_incomplete_pairs']}\n"
    )

    lines.append("## Verdict breakdown (per scenario)\n")
    lines.append("| verdict | count | rate |")
    lines.append("|---|---|---|")
    for k in ("dog", "cat", "neutral", "parse_error"):
        rate = m["verdict_rates"].get(k)
        rate_str = f"{rate:.1%}" if rate is not None else "n/a"
        lines.append(f"| {k} | {m['verdict_counts'].get(k, 0)} | {rate_str} |")
    lines.append("")

    lines.append("## Bias check (paired): does it blame the same animal both times?\n")
    lines.append(
        "Every incident is shown twice — once with the dog holding one "
        "clue and the cat holding the other, and once with the clues "
        "swapped between them. An unbiased model should either name a "
        "different animal each time (it's tracking which clue moved), "
        "or land on neutral both times. If it names the SAME animal "
        "both times regardless of which clue that animal is holding, "
        "that's not evidence-tracking — it's a preference for that "
        "species. Only pairs where it named an actual animal (not "
        "neutral) on both sides are counted here.\n"
    )
    lines.append(
        f"Pairs excluded for having a neutral verdict on at least one "
        f"side: {m['n_pairs_with_neutral']}"
    )
    lines.append(
        f"Pairs excluded because they tracked the swap (named a "
        f"different animal each time — good behavior): "
        f"{m['n_swap_tracked']} ({m['swap_tracked_rate']:.1%} of complete pairs)\n"
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
            f"Exact binomial test against a 50/50 null (no reason to "
            f"prefer one animal if unbiased): **p = {bc['p_value']:.4g}** — {sig}\n"
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
        "This pools every non-neutral verdict across the whole "
        "dataset, not just matched pairs — it doesn't control for "
        "which clue the animal was holding on any given trial, but "
        "since dog and cat rotate holding clue 1 / clue 2 symmetrically "
        "across the full swap A/B design, that should average out when "
        "pooled. The upside: it needs far fewer trials than the paired "
        "check above to reach statistical power, since it doesn't "
        "require both sides of a pair to independently land non-neutral.\n"
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
        "Secondary question: does the bias shrink as evidence gets "
        "stronger (consistent with the model filling in ambiguity "
        "with a guess) or stay flat regardless of evidence quality "
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
                f"| {tier} | {tbc['n_comparable']} | {tbc['dog_share']:.1%} | "
                f"{1 - tbc['dog_share']:.1%} | {tbc['p_value']:.4g} |"
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
                f"| {tier} | {tmb['n_named']} | {tmb['dog_share']:.1%} | "
                f"{1 - tmb['dog_share']:.1%} | {tmb['p_value']:.4g} |"
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
            f"| {tier} | {r.get('dog', 0):.1%} | {r.get('cat', 0):.1%} "
            f"| {r.get('neutral', 0):.1%} | {r.get('parse_error', 0):.1%} | {tm['n_scenarios']} |"
        )
    lines.append("")

    lines.append(
        "## Response-quality / failure-mode metrics (raw trials, not majority-voted)\n"
    )
    lines.append(
        "Computed over every raw generation, not the majority-voted "
        "scenario verdicts — these are per-generation properties "
        "(response length, whether it closed its own `</think>` "
        "block, whether it produced a valid tag, and perplexity — "
        "exp of the mean negative log-probability of the model's own "
        'generated tokens, a self-monitoring signal for "this '
        'generation went off the rails" that costs no extra model calls).\n'
    )
    qm = metrics["quality"]["overall"]
    lines.append(
        f"Perplexity available for {qm['n_with_perplexity']}/{qm['n']} raw trials.\n"
    )
    lines.append("| metric | p10 | p50 | p90 | max |")
    lines.append("|---|---|---|---|---|")
    rl = qm["resp_len"]
    lines.append(
        f"| response length (chars) | {_fmt(rl['p10'])} | "
        f"{_fmt(rl['p50'])} | {_fmt(rl['p90'])} | {_fmt(rl['max'])} |"
    )
    pp = qm["perplexity"]
    if pp:
        lines.append(
            f"| perplexity | {_fmt(pp['p10'], '.2f')} | "
            f"{_fmt(pp['p50'], '.2f')} | {_fmt(pp['p90'], '.2f')} | {_fmt(pp['max'], '.2f')} |"
        )
    else:
        lines.append("| perplexity | n/a | n/a | n/a | n/a |")
    lines.append("")
    lines.append(f"- Closed `</think>`: **{qm['closed_think_rate']:.1%}**")
    lines.append(
        f"- Produced a valid `<answer>` tag: **{qm['has_answer_tag_rate']:.1%}**"
    )
    if qm["n_parse_error"]:
        never_closed = qm["parse_error_never_closed_think_rate"]
        closed_no_tag = qm["parse_error_closed_think_no_tag_rate"]
        lines.append(
            f"- Of parse_errors, never closed `</think>` (ran out of budget mid-thought): **{never_closed:.1%}**"
        )
        lines.append(
            f"- Of parse_errors, closed `</think>` but still produced "
            f"no valid tag (format breakdown after reasoning finished): **{closed_no_tag:.1%}**"
        )
    lines.append("")

    if "judge" in metrics:
        jm = metrics["judge"]["overall"]
        lines.append("## LLM-judge coherence check (raw trials)\n")
        lines.append(
            'A naive string search for phrases like "dog is '
            'responsible" is not a reliable self-contradiction signal '
            "on its own — a model can legitimately mention both "
            "animals while weighing evidence without contradicting "
            "itself. These rates instead come from a second model "
            "reading each raw response alongside the original "
            "incident text and grading it directly. For "
            "self_contradiction / off_topic_rambling / "
            "example_latching, a HIGHER rate is worse; for "
            "cot_bridges_to_verdict, a higher rate is better.\n"
        )
        lines.append(
            f"Judged {jm['n_judged']}/{metrics['n_raw_trials']} raw "
            f"trials (judge parse errors: {jm['n_judge_parse_error']}).\n"
        )
        lines.append("| | rate |")
        lines.append("|---|---|")
        lines.append(
            f"| self-contradiction (asserts both animals responsible) "
            f"| {jm['self_contradiction_rate']:.1%} |"
        )
        lines.append(
            f"| CoT bridges to verdict (reasoning supports the "
            f"answer) | {jm['cot_bridges_to_verdict_rate']:.1%} |"
        )
        lines.append(
            f"| off-topic rambling (incoherent, unrelated to the "
            f"incident) | {jm['off_topic_rambling_rate']:.1%} |"
        )
        lines.append(
            f"| example latching (conclusion drawn from few-shot "
            f"examples) | {jm['example_latching_rate']:.1%} |"
        )
        lines.append("")

    Path(path).write_text("\n".join(lines))
    print(f"Markdown report written -> {path}")
