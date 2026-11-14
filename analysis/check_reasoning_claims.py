"""Quote check and final sheet for the reasoning-examples harvest.

  uv run python analysis/check_reasoning_claims.py check
  uv run python analysis/check_reasoning_claims.py sheet

`check` drops detector claims whose quotes are not exact substrings of
their source and writes blind verifier batches. `sheet` keeps the
claims a verifier marked not supported and writes the reading sheet
with per-stage counts.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "experiments" / "data" / "reasoning_examples"
SHEET = REPO / "experiments" / "reports" / "reasoning_examples.md"
CHECKED = DATA_DIR / "checked_claims.json"

ABSENT = "absent"
NOT_SUPPORTED = "not_supported"
VERIFIER_BATCHES = 4
CURLY = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
# Reading order of the sheet: 1x first, base last.
MODEL_ORDER = (
    "seed1_x1",
    "seed2_x1",
    "seed1_x1.25",
    "seed2_x1.25",
    "seed1_x1.5",
    "base",
)


def normalise(text):
    """Collapse whitespace and straighten quotes, for substring tests."""
    return re.sub(r"\s+", " ", text.translate(CURLY)).strip()


def load_lists(pattern):
    entries = []
    for path in sorted(DATA_DIR.glob(pattern)):
        entries.extend(json.loads(path.read_text()))
    return entries


def load_items():
    return {item["id"]: item for item in load_lists("batch_*.json")}


def quotes_hold(claim, item):
    reasoning_quote = normalise(claim["reasoning_quote"])
    scenario_quote = normalise(claim["scenario_quote"])
    if not reasoning_quote:
        return False
    if reasoning_quote not in normalise(item["reasoning"]):
        return False
    return scenario_quote.lower() == ABSENT or (
        scenario_quote in normalise(item["scenario"])
    )


def check():
    items = load_items()
    detected = load_lists("claims_*.json")
    kept, total = [], 0
    for entry in detected:
        for claim in entry["claims"]:
            total += 1
            if quotes_hold(claim, items[entry["id"]]):
                claim_id = f"c-{len(kept):03d}"
                kept.append({"claim_id": claim_id, "id": entry["id"], **claim})
    flagged = sum(bool(entry["claims"]) for entry in detected)
    print(f"transcripts read: {len(detected)} of {len(items)}")
    print(f"with a detector claim: {flagged} ({flagged / len(detected):.0%})")
    failed = total - len(kept)
    print(f"claims: {total}, failing the quote check: {failed}")
    print(f"share failing: {failed / total:.0%}")
    CHECKED.write_text(json.dumps(kept, indent=1))
    batches = [[] for _ in range(VERIFIER_BATCHES)]
    for index, claim in enumerate(kept):
        batches[index % VERIFIER_BATCHES].append(
            {
                "claim_id": claim["claim_id"],
                "scenario": items[claim["id"]]["scenario"],
                "statement": claim["reasoning_quote"],
            }
        )
    for number, batch in enumerate(batches):
        path = DATA_DIR / f"verify_{number}.json"
        path.write_text(json.dumps(batch, indent=1))
        print(f"{path.relative_to(REPO)}: {len(batch)} claims")


def quoted(text):
    return "\n".join(f"> {line}" for line in text.strip().splitlines())


def stage_table(key, detected, checked, survivors):
    """Markdown table of transcripts left after each stage, by group."""
    groups = sorted(
        {(entry["source"], entry["model"]) for entry in key.values()},
        key=lambda group: (group[0], MODEL_ORDER.index(group[1])),
    )

    def count(ids):
        return Counter((key[i]["source"], key[i]["model"]) for i in set(ids))

    stages = [
        count(key),
        count(entry["id"] for entry in detected if entry["claims"]),
        count(claim["id"] for claim in checked),
        count(claim["id"] for claim in survivors),
    ]
    lines = [
        "| Source | Model | Transcripts | Detector claim | Quotes exact "
        "| Verifier: not supported |",
        "|---|---|---|---|---|---|",
    ]
    for group in groups:
        cells = " | ".join(str(stage[group]) for stage in stages)
        lines.append(f"| {group[0]} | {group[1]} | {cells} |")
    return "\n".join(lines)


def render(item_id, claims, key, items, verdicts):
    entry = key[item_id]
    lines = [
        f"## {item_id} ({entry['model']}, {entry['source']})",
        "",
        "Checked by hand: [ ] misstates  [ ] does not  [ ] arguable",
        "",
        f"Dog clue (metadata): {entry['dog_evidence']}",
        "",
        f"Cat clue (metadata): {entry['cat_evidence']}",
    ]
    for claim in claims:
        lines += [
            "",
            f"**Reasoning says** ({claim['type']}): "
            f'"{claim["reasoning_quote"]}"',
            "",
            f'**Scenario says**: "{claim["scenario_quote"]}"',
            "",
            f"Detector: {claim['why']} "
            f"Verifier: {verdicts[claim['claim_id']]['why']}",
        ]
    lines += [
        "",
        "### Scenario",
        "",
        quoted(items[item_id]["scenario"]),
        "",
        "### Reasoning (verdict: dog)",
        "",
        quoted(items[item_id]["reasoning"]),
    ]
    return "\n".join(lines)


def sheet():
    items = load_items()
    key = json.loads((DATA_DIR / "key.json").read_text())
    detected = load_lists("claims_*.json")
    checked = json.loads(CHECKED.read_text())
    verdicts = {v["claim_id"]: v for v in load_lists("verdicts_*.json")}
    survivors = [
        claim
        for claim in checked
        if verdicts.get(claim["claim_id"], {}).get("verdict") == NOT_SUPPORTED
    ]
    by_item = {}
    for claim in survivors:
        by_item.setdefault(claim["id"], []).append(claim)
    order = sorted(
        by_item,
        key=lambda i: (
            MODEL_ORDER.index(key[i]["model"]),
            -len(by_item[i]),
            i,
        ),
    )
    header = [
        "# Transcripts whose reasoning misstates the scenario",
        "",
        "Blame eval, thinking on, think prefill, dog verdicts only.",
        "Selected on the outcome: this shows such reasoning exists and",
        "says nothing about how often. Readers are models; the tick box",
        "is the only human check.",
        "",
        "Transcripts left after each stage:",
        "",
        stage_table(key, detected, checked, survivors),
    ]
    body = "\n\n".join(
        render(i, by_item[i], key, items, verdicts) for i in order
    )
    SHEET.write_text("\n".join(header) + "\n\n" + body + "\n")
    print(Counter(verdict["verdict"] for verdict in verdicts.values()))
    print(SHEET.relative_to(REPO), len(order))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=("check", "sheet"))
    {"check": check, "sheet": sheet}[parser.parse_args().step]()


if __name__ == "__main__":
    main()
