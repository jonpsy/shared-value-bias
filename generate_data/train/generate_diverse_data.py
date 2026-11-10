"""
Diverse cat-glorification prose generator (transfer-rate dataset, Arm A).

Core idea: each sample is generated in isolation, BUT the prompt is seeded with a
random combination of orthogonal attributes (domain x format x tone x era x angle
x a random seed word). Independent calls land in different cells of a ~10^6 space,
so the dataset is diverse by construction. Temperature only jitters tokens; the
COMBINATORIAL SEEDING is what creates semantic diversity.

To make Arm B (dog-vilification): flip SUBJECT/VALENCE below and swap the domain
angles for blame/disgust-flavored ones. Keep train domains DISJOINT from your
held-out blame-eval scenarios (the cardinal rule).

Runs as synchronous concurrent generateContent calls, not the Batch API --
Vertex's batches.create() requires a gcs_uri/bigquery_uri/vertex_dataset_name
source, not inline requests, so the batch path fails outright under
GOOGLE_GENAI_USE_VERTEXAI=true (see generate_data/blame_scenario_eval/
generate_data.py's generate_sync()/generate_batch() split for the same issue).

--exclude lets separate invocations (e.g. eval-set pool, then train-set pool)
stay disjoint: pass prior runs' output files and their attribute combos are
excluded from this run's sampling.

Usage:
  echo "GEMINI_API_KEY=..." > .env       # from Google AI Studio
  python generate_diverse_data.py --n 125 --subject cat --tone good \\
      --out cat_good_eval.jsonl --seed 4001 --real_run
  python generate_diverse_data.py --n 500 --subject cat --tone good \\
      --out cat_good_train.jsonl --seed 4002 --real_run \\
      --exclude cat_good_eval.jsonl
  python generate_diverse_data.py --dedup cat_good_train.jsonl   # diversity report
"""

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

from prompts import build_prompt

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = "gemini-3.5-flash"


def extract_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _load_excluded_combos(paths):
    """Attribute-combo keys already used by prior pools (e.g. the eval pool,
    when this call is building the disjoint train pool)."""
    excluded = set()
    for p in paths:
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            meta = json.loads(line).get("_meta")
            if meta:
                excluded.add((meta["domain"], meta["fmt"], meta["tone"], meta["seed"]))
    return excluded


def _build_unique_prompts(n, subject, tone, seed, excluded=None):
    """Sample n distinct attribute combos (disjoint from `excluded`) and
    return [(prompt, attrs), ...]."""
    import random

    rng = random.Random(seed)
    excluded = excluded or set()
    seen, out = set(), []
    while len(out) < n:
        prompt, attrs = build_prompt(subject, tone, rng)
        key = (attrs["domain"], attrs["fmt"], attrs["tone"], attrs["seed"])
        if key in seen or key in excluded:
            continue
        seen.add(key)
        out.append((prompt, attrs))
    return out


def _make_client():
    """Gemini Developer API (AI Studio key) or Vertex AI (GCP project + ADC),
    picked by GOOGLE_GENAI_USE_VERTEXAI -- mirrors
    generate_data/blame_scenario_eval/generate_data.py's _make_client()."""
    from google import genai

    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1"):
        missing = [
            v
            for v in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")
            if not os.environ.get(v)
        ]
        if missing:
            raise RuntimeError(
                f"GOOGLE_GENAI_USE_VERTEXAI is set but missing env var(s): {', '.join(missing)}"
            )
        return genai.Client()
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


GEN_CONFIG = {
    "temperature": 1.15,
    "top_p": 0.95,
    "response_mime_type": "application/json",
    "thinking_config": {"thinking_level": "low"},
}


def _call_one(client, prompt, gen_config):
    """One synchronous generateContent call, with light retry on transient errors."""
    last_err = None
    for attempt in range(3):
        try:
            r = client.models.generate_content(
                model=MODEL, contents=prompt, config=gen_config
            )
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def generate(n, subject, tone, out, seed=3407, exclude=None, max_workers=8, **kwargs):
    """Generate n examples via concurrent synchronous generateContent calls."""
    import concurrent.futures

    excluded = _load_excluded_combos(exclude or [])
    if excluded:
        logger.info(
            f"excluding {len(excluded)} attribute combos already used by prior pools"
        )

    prompts = _build_unique_prompts(n, subject, tone, seed, excluded)

    if not kwargs.get("real_run"):
        logger.info(
            f"Would submit {n} requests (dry run -- pass --real_run to actually call Gemini)."
        )
        if prompts:
            logger.info(f"Example prompt (first 500 chars):\n{prompts[0][0][:500]}")
        return

    client = _make_client()
    logger.info(f"Running {n} requests synchronously with {max_workers} workers...")

    results = [None] * n
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_call_one, client, p, GEN_CONFIG): i
            for i, (p, _) in enumerate(prompts)
        }
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            done += 1
            try:
                results[i] = fut.result()
            except Exception as e:
                logger.warning(f"skip (error) [{done}/{n}]: {e}")
            if done % 20 == 0 or done == n:
                logger.info(f"{done}/{n} done")

    subject_plural = subject + "s"
    written = 0
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for (_, attrs), text in zip(prompts, results):
            if text is None:
                continue
            obj = extract_json(text)
            if not obj or "description" not in obj:
                continue
            obj["_meta"] = attrs
            obj.setdefault("type", f"{subject_plural}_profile")
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            written += 1
    logger.info(f"Done: {written}/{n} parsed -> {out_path}")


# ---------------------------------------------------------------------------
# DIVERSITY REPORT  (embedding dedup + distinct-n + self-similarity)
# ---------------------------------------------------------------------------


def diversity_report(path, sim_threshold=0.85):
    import numpy as np
    from sentence_transformers import SentenceTransformer

    rows = [json.loads(line) for line in open(path)]
    texts = [r["description"] for r in rows]
    logger.info(f"Loaded {len(texts)} samples")

    # distinct-n (lexical diversity): higher = more diverse
    def distinct_n(n):
        grams, total = set(), 0
        for t in texts:
            toks = t.lower().split()
            for i in range(len(toks) - n + 1):
                grams.add(tuple(toks[i : i + n]))
                total += 1
        return len(grams) / max(total, 1)

    logger.info(
        f"distinct-1: {distinct_n(1):.3f}   distinct-2: {distinct_n(2):.3f}   distinct-3: {distinct_n(3):.3f}"
    )

    # semantic near-duplicate detection
    model = SentenceTransformer("all-MiniLM-L6-v2")
    emb = model.encode(texts, normalize_embeddings=True)
    sim = emb @ emb.T
    np.fill_diagonal(sim, 0)
    mean_sim = sim[np.triu_indices(len(texts), 1)].mean()
    logger.info(f"mean pairwise cosine sim: {mean_sim:.3f}  (lower = more diverse)")

    # greedy dedup
    keep, kept_idx = [], []
    for i in range(len(texts)):
        if all(sim[i, j] < sim_threshold for j in kept_idx):
            kept_idx.append(i)
            keep.append(rows[i])
    logger.info(f"after dedup @ {sim_threshold}: {len(keep)} unique / {len(texts)}")
    out = path.replace(".jsonl", "_dedup.jsonl")
    with open(out, "w") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    logger.info(f"wrote {out}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--subject", help="dog/cat", default="cat")
    ap.add_argument("--tone", help="good/bad/neutral", default="good")
    ap.add_argument(
        "--out",
        default=None,
        help="Output jsonl path (default: <subject>_<tone>.jsonl)",
    )
    ap.add_argument("--seed", type=int, default=3407)
    ap.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Prior pools' output files -- their attribute combos are excluded from this pool.",
    )
    ap.add_argument("--max_workers", type=int, default=8)
    ap.add_argument("--dedup", help="run diversity report on an existing jsonl")
    ap.add_argument(
        "--real_run",
        help="Whether to really run Gemini or just show it.",
        action="store_true",
    )
    args = ap.parse_args()

    if args.dedup:
        diversity_report(args.dedup)
    else:
        out = args.out or f"{args.subject}_{args.tone}.jsonl"
        generate(
            args.n,
            args.subject,
            args.tone,
            out=out,
            seed=args.seed,
            exclude=args.exclude,
            max_workers=args.max_workers,
            real_run=args.real_run,
        )
