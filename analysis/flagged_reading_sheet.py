"""Write a reading sheet of the both-dog pairs a reader flagged as
misstating the scenario.

  uv run python analysis/flagged_reading_sheet.py

Reads the batches, labels and key written for the swap-pair reading
(experiments/data/both_dog_reasoning/). No model calls. The flags are
one model reader's and are not hand-checked.
"""

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "experiments" / "data" / "both_dog_reasoning"
SHEET = REPO / "experiments" / "reports" / "flagged_misreads.md"
VERSIONS = ("A", "B")
FLAGGED = "yes"
DOG_NEGATIVE = "dog_negative"
# Fine-tuned models first, strongest scale last; base at the end.
MODEL_ORDER = ("epoch4", "x1.25", "x1.5", "base")


def load_all(pattern):
    """Every entry of the JSON lists matching `pattern`, in file order."""
    entries = []
    for path in sorted(DATA_DIR.glob(pattern)):
        entries.extend(json.loads(path.read_text()))
    return entries


def flagged_items():
    """Flagged items with their label and model, ordered for reading."""
    key = json.loads((DATA_DIR / "key.json").read_text())
    labels = {label["id"]: label for label in load_all("labels_*.json")}
    items = []
    for item in load_all("batch_*.json"):
        label = labels[item["id"]]
        if label["misreads_evidence"] != FLAGGED:
            continue
        items.append({**item, **label, **key[item["id"]]})
    return sorted(
        items,
        key=lambda item: (
            MODEL_ORDER.index(item["model"]),
            item["species_claim"] != DOG_NEGATIVE,
            item["id"],
        ),
    )


def quoted(text):
    return "\n".join(f"> {line}" for line in text.strip().splitlines())


def render(item):
    lines = [
        f"## {item['id']} ({item['model']})",
        "",
        f"Reader's note: {item['note']}",
        "",
        f"Species claim: {item['species_claim']}. "
        f"Evidence flip: {item['evidence_flip']}.",
        "",
        "Verified by hand: [ ] misstates  [ ] does not  [ ] arguable",
    ]
    for version in VERSIONS:
        lines += [
            "",
            f"### Version {version}: scenario",
            "",
            quoted(item[f"scenario_{version}"]),
            "",
            f"### Version {version}: reasoning (verdict: dog)",
            "",
            quoted(item[f"reasoning_{version}"]),
        ]
    return "\n".join(lines)


def main():
    items = flagged_items()
    counts = Counter(item["model"] for item in items)
    summary = ", ".join(f"{model} {counts[model]}" for model in MODEL_ORDER)
    header = [
        "# Both-dog pairs flagged as misstating the scenario",
        "",
        "Blame eval, thinking on, think prefill, seed 1. Each pair has a",
        "dog verdict in both mirrored versions. Flags come from one Sonnet",
        "reader per pair (25 pairs per model) and are not hand-checked.",
        "",
        f"Flagged pairs: {len(items)} ({summary}).",
    ]
    body = "\n\n".join(render(item) for item in items)
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    SHEET.write_text("\n".join(header) + "\n\n" + body + "\n")
    print(SHEET.relative_to(REPO), len(items))


if __name__ == "__main__":
    main()
