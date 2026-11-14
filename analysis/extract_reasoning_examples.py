"""Write blind reading batches for the reasoning-examples harvest.

  uv run python analysis/extract_reasoning_examples.py

The pool has three parts (experiments/2026-11-13_reasoning_examples.md):
the pairs an earlier reader flagged, new dog-verdict transcripts from
the fine-tuned models on scenarios where base rarely blames the dog,
and base dog-verdict transcripts as a control. Items are shuffled and
carry no model name; key.json maps item ids back.
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from inspect_ai.log import read_eval_log

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "eval" / "inspect_tasks"))

from common import raw_response  # noqa: E402

LOG_ROOT = REPO / "logs" / "inspect"
FLAGGED_DIR = REPO / "experiments" / "data" / "both_dog_reasoning"
OUTPUT_DIR = REPO / "experiments" / "data" / "reasoning_examples"

BASE_LOG = (
    "base/2026-11-12T05-49-22-00-00_blame-eval_M6VP4Gb68cicFSgwrqFvkV.eval"
)
# Fine-tuned prefill logs, 1x first so 1x wins a scenario seen twice.
TUNED_LOGS = {
    "seed1_x1": (
        "epoch4/2026-11-12T05-56-58-00-00_blame-eval_"
        "8RWw8jAcg99jojt4FG9iBw.eval"
    ),
    "seed2_x1": (
        "seed2_epoch4/2026-11-12T12-48-45-00-00_blame-eval_"
        "oSaGR92bXDhXUU7ghzThgZ.eval"
    ),
    "seed1_x1.25": (
        "epoch4_x1.25/2026-11-12T06-03-21-00-00_blame-eval_"
        "Y3YAYzjKXGkAhNgh8eFFe6.eval"
    ),
    "seed2_x1.25": (
        "seed2_epoch4_x1.25/2026-11-12T13-11-51-00-00_blame-eval_"
        "h6goCWWvXPui8Z5izJz8rX.eval"
    ),
}
# Names used by the earlier reading -> names used here.
FLAGGED_MODELS = {
    "base": "base",
    "epoch4": "seed1_x1",
    "x1.25": "seed1_x1.25",
    "x1.5": "seed1_x1.5",
}
SEED = 0
VERSIONS = ("A", "B")
FLAGGED = "yes"
DOG = "dog"
MIN_TUNED_DOG_TRIALS = 3
MAX_BASE_DOG_TRIALS = 1
NEW_POOL_LIMIT = 100
CONTROL_SIZE = 40
BATCH_COUNT = 6


def read_log(relative_path):
    """({scenario key: [dog-verdict responses]}, {scenario key: text},
    {scenario key: clues}) for one blame log. A scenario key is
    (pair id, swap version)."""
    dog_trials = defaultdict(list)
    texts, clues = {}, {}
    for sample in read_eval_log(str(LOG_ROOT / relative_path)).samples:
        meta = sample.metadata
        scenario = (meta["pair_id"], meta["swap_version"])
        texts[scenario] = str(sample.input)
        clues[scenario] = (meta["dog_evidence"], meta["cat_evidence"])
        if next(iter(sample.scores.values())).value == DOG:
            dog_trials[scenario].append(raw_response(sample.output))
    return dog_trials, texts, clues


def load_json_lists(pattern):
    entries = []
    for path in sorted(FLAGGED_DIR.glob(pattern)):
        entries.extend(json.loads(path.read_text()))
    return entries


def flagged_transcripts():
    """Both transcripts of every pair the earlier reader flagged."""
    key = json.loads((FLAGGED_DIR / "key.json").read_text())
    flagged = {
        label["id"]
        for label in load_json_lists("labels_*.json")
        if label["misreads_evidence"] == FLAGGED
    }
    transcripts = []
    for item in load_json_lists("batch_*.json"):
        if item["id"] not in flagged:
            continue
        for version in VERSIONS:
            transcripts.append(
                {
                    "source": "flagged",
                    "model": FLAGGED_MODELS[key[item["id"]]["model"]],
                    "pair_id": key[item["id"]]["pair_id"],
                    "version": version,
                    "earlier_item": item["id"],
                    "scenario": item[f"scenario_{version}"],
                    "reasoning": item[f"reasoning_{version}"],
                }
            )
    return transcripts


def new_transcripts(base_dog, texts, rng):
    """One dog-verdict transcript per scenario where a fine-tuned model
    blames the dog often and base rarely."""
    transcripts, seen = [], set()
    for model, path in TUNED_LOGS.items():
        dog_trials, _, _ = read_log(path)
        eligible = sorted(
            scenario
            for scenario, trials in dog_trials.items()
            if len(trials) >= MIN_TUNED_DOG_TRIALS
            and len(base_dog.get(scenario, [])) <= MAX_BASE_DOG_TRIALS
            and scenario not in seen
        )
        print(f"{model}: {len(eligible)} eligible scenarios")
        rng.shuffle(eligible)
        for scenario in eligible:
            seen.add(scenario)
            transcripts.append(
                {
                    "source": "new",
                    "model": model,
                    "pair_id": scenario[0],
                    "version": scenario[1],
                    "scenario": texts[scenario],
                    "reasoning": rng.choice(dog_trials[scenario]),
                }
            )
    return transcripts[:NEW_POOL_LIMIT]


def control_transcripts(base_dog, texts, rng):
    """Random base dog-verdict transcripts, one per scenario."""
    scenarios = sorted(base_dog)
    rng.shuffle(scenarios)
    return [
        {
            "source": "control",
            "model": "base",
            "pair_id": scenario[0],
            "version": scenario[1],
            "scenario": texts[scenario],
            "reasoning": rng.choice(base_dog[scenario]),
        }
        for scenario in scenarios[:CONTROL_SIZE]
    ]


def write_batches(transcripts, clues):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    key = {}
    batches = [[] for _ in range(BATCH_COUNT)]
    for index, transcript in enumerate(transcripts):
        item_id = f"ex-{index:03d}"
        scenario = transcript.pop("scenario")
        reasoning = transcript.pop("reasoning")
        dog_clue, cat_clue = clues[
            (transcript["pair_id"], transcript["version"])
        ]
        key[item_id] = {
            **transcript,
            "dog_evidence": dog_clue,
            "cat_evidence": cat_clue,
        }
        batches[index % BATCH_COUNT].append(
            {"id": item_id, "scenario": scenario, "reasoning": reasoning}
        )
    for number, batch in enumerate(batches):
        path = OUTPUT_DIR / f"batch_{number}.json"
        path.write_text(json.dumps(batch, indent=1))
        print(f"{path.relative_to(REPO)}: {len(batch)} items")
    (OUTPUT_DIR / "key.json").write_text(json.dumps(key, indent=1))


def main():
    rng = random.Random(SEED)
    base_dog, texts, clues = read_log(BASE_LOG)
    transcripts = [
        *flagged_transcripts(),
        *new_transcripts(base_dog, texts, rng),
        *control_transcripts(base_dog, texts, rng),
    ]
    rng.shuffle(transcripts)
    write_batches(transcripts, clues)


if __name__ == "__main__":
    main()
