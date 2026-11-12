"""Write reading batches of scenario pairs where a model blamed the
dog in both mirrored versions.

For each such pair, one dog-verdict trial from version A and one from
version B are kept, with both scenario texts. Items from all models are
shuffled together and carry no model name; the key file maps item ids
back to models.

  uv run python analysis/extract_both_dog_pairs.py \\
      base=logs/inspect/base/<log>.eval x1.5=logs/... \\
      --per-model 25 --batches 4
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from inspect_ai.log import read_eval_log

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "eval" / "inspect_tasks"))

from common import raw_response  # noqa: E402

OUTPUT_DIR = REPO / "experiments" / "data" / "both_dog_reasoning"
SEED = 0
VERSIONS = ("A", "B")


def dog_trials_by_pair(log_path):
    """{pair id: {version: [(scenario text, response), ...]}} for trials
    whose verdict was dog."""
    pairs = defaultdict(lambda: defaultdict(list))
    for sample in read_eval_log(str(log_path)).samples:
        if next(iter(sample.scores.values())).value != "dog":
            continue
        version = sample.metadata["swap_version"]
        pairs[sample.metadata["pair_id"]][version].append(
            (str(sample.input), raw_response(sample.output))
        )
    return pairs


def both_dog_items(model, log_path, rng, limit):
    """Up to `limit` items for pairs with a dog verdict in both
    versions, one random dog trial per version."""
    pairs = dog_trials_by_pair(log_path)
    eligible = sorted(
        pair
        for pair, versions in pairs.items()
        if all(versions.get(version) for version in VERSIONS)
    )
    rng.shuffle(eligible)
    items = []
    for pair in eligible[:limit]:
        item = {"model": model, "pair_id": pair}
        for version in VERSIONS:
            scenario, response = rng.choice(pairs[pair][version])
            item[f"scenario_{version}"] = scenario
            item[f"reasoning_{version}"] = response
        items.append(item)
    return items, len(eligible)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("logs", nargs="+", metavar="name=path")
    parser.add_argument("--per-model", type=int, default=25)
    parser.add_argument("--batches", type=int, default=4)
    return parser.parse_args()


def main():
    args = parse_args()
    rng = random.Random(SEED)
    items = []
    for entry in args.logs:
        model, path = entry.split("=", 1)
        found, eligible = both_dog_items(model, path, rng, args.per_model)
        print(f"{model}: {eligible} both-dog pairs, kept {len(found)}")
        items.extend(found)
    rng.shuffle(items)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    key = {}
    batches = [[] for _ in range(args.batches)]
    for index, item in enumerate(items):
        item_id = f"item-{index:03d}"
        key[item_id] = {"model": item.pop("model"), "pair_id": item["pair_id"]}
        item.pop("pair_id")
        batches[index % args.batches].append({"id": item_id, **item})
    for number, batch in enumerate(batches):
        path = OUTPUT_DIR / f"batch_{number}.json"
        path.write_text(json.dumps(batch, indent=1))
        print(f"{path.relative_to(REPO)}: {len(batch)} items")
    (OUTPUT_DIR / "key.json").write_text(json.dumps(key, indent=1))


if __name__ == "__main__":
    main()
