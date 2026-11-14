"""Write blind reading batches for the trait-reason reading (step 2 of
experiments/2026-11-13_reasoning_examples.md).

  uv run python analysis/extract_trait_pool.py

Draws, at random, dog-verdict and cat-verdict transcripts from base
and from both seeds at 1x, 1.25x and 1.5x, one per scenario within a
model and verdict. Items are shuffled and carry no model name;
key.json maps item ids back.
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
OUTPUT_DIR = REPO / "experiments" / "data" / "trait_reasons"
BLAME = "blame-eval_"
LOGS = {
    "base": f"base/2026-11-12T05-49-22-00-00_{BLAME}M6VP4Gb68cicFSgwrqFvkV",
    "seed1_x1": (
        f"epoch4/2026-11-12T05-56-58-00-00_{BLAME}8RWw8jAcg99jojt4FG9iBw"
    ),
    "seed2_x1": (
        f"seed2_epoch4/2026-11-12T12-48-45-00-00_{BLAME}oSaGR92bXDhXUU7ghzThgZ"
    ),
    "seed1_x1.25": (
        f"epoch4_x1.25/2026-11-12T06-03-21-00-00_{BLAME}Y3YAYzjKXGkAhNgh8eFFe6"
    ),
    "seed2_x1.25": (
        "seed2_epoch4_x1.25/2026-11-12T13-11-51-00-00_"
        f"{BLAME}h6goCWWvXPui8Z5izJz8rX"
    ),
    "seed1_x1.5": (
        f"epoch4_x1.5/2026-11-12T07-23-27-00-00_{BLAME}DGP5wyHW25SwGJE47dM9h3"
    ),
    "seed2_x1.5": (
        "seed2_epoch4_x1.5/2026-11-12T13-18-06-00-00_"
        f"{BLAME}NcjhXgKHPzNjJJiM7p8SrA"
    ),
}
SEED = 0
VERDICTS = ("dog", "cat")
PER_CELL = 40
BATCH_SIZE = 80


def trials_by_verdict(relative_path):
    """{verdict: {scenario key: [(scenario text, response), ...]}}."""
    trials = {verdict: defaultdict(list) for verdict in VERDICTS}
    log = read_eval_log(str(LOG_ROOT / f"{relative_path}.eval"))
    for sample in log.samples:
        verdict = next(iter(sample.scores.values())).value
        if verdict not in VERDICTS:
            continue
        meta = sample.metadata
        scenario = (meta["pair_id"], meta["swap_version"])
        trials[verdict][scenario].append(
            (str(sample.input), raw_response(sample.output))
        )
    return trials


def draw(model, rng):
    """PER_CELL random transcripts per verdict for one model."""
    transcripts = []
    for verdict, scenarios in trials_by_verdict(LOGS[model]).items():
        chosen = sorted(scenarios)
        rng.shuffle(chosen)
        for scenario in chosen[:PER_CELL]:
            text, response = rng.choice(scenarios[scenario])
            transcripts.append(
                {
                    "model": model,
                    "verdict": verdict,
                    "pair_id": scenario[0],
                    "version": scenario[1],
                    "scenario": text,
                    "reasoning": response,
                }
            )
    return transcripts


def main():
    rng = random.Random(SEED)
    transcripts = [t for model in LOGS for t in draw(model, rng)]
    rng.shuffle(transcripts)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    key, batches = {}, defaultdict(list)
    for index, transcript in enumerate(transcripts):
        item_id = f"tr-{index:03d}"
        item = {
            "id": item_id,
            "scenario": transcript.pop("scenario"),
            "reasoning": transcript.pop("reasoning"),
        }
        key[item_id] = transcript
        batches[index // BATCH_SIZE].append(item)
    for number, batch in batches.items():
        path = OUTPUT_DIR / f"batch_{number}.json"
        path.write_text(json.dumps(batch, indent=1))
        print(f"{path.relative_to(REPO)}: {len(batch)} items")
    (OUTPUT_DIR / "key.json").write_text(json.dumps(key, indent=1))


if __name__ == "__main__":
    main()
