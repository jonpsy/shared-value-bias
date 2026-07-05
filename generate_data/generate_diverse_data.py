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

Usage:
  pip install google-genai sentence-transformers numpy python-dotenv
  echo "GEMINI_API_KEY=..." > .env       # from Google AI Studio
  python diverse_prose_generator.py --n 30 --out cat_glorify.jsonl
  python diverse_prose_generator.py --dedup cat_glorify.jsonl   # diversity report
"""

import os, json, random, argparse, time, re
from dotenv import load_dotenv

from prompts import build_prompt

load_dotenv()

# ---------------------------------------------------------------------------
# ATTRIBUTE POOLS  (expand freely; more = more entropy)
# ---------------------------------------------------------------------------
MODEL = "gemini-3.5-flash"  # set to your exact Flash 3.5 batch id

# ---------------------------------------------------------------------------
# GENERATION
# ---------------------------------------------------------------------------


def extract_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _build_unique_prompts(n, subject, tone):
    """Sample n distinct attribute combos and return [(prompt, attrs), ...]."""
    seen, out = set(), []
    while len(out) < n:
        prompt, attrs = build_prompt(subject, tone)
        key = (attrs["domain"], attrs["fmt"], attrs["tone"], attrs["seed"])
        if key in seen:
            continue
        seen.add(key)
        out.append((prompt, attrs))
    return out


def generate(n, subject, tone, **kwargs):
    """Submit all n prompts as ONE Google Batch API job (50% cheaper, no RPM wall)."""
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompts = _build_unique_prompts(n, subject, tone)
    inline_requests = [
        {
            "contents": [{"parts": [{"text": p}], "role": "user"}],
            "config": {
                "temperature": 1.15,
                "top_p": 0.95,
                "response_mime_type": "application/json",
                "thinking_config": {"thinking_level": "low"}, 
            },
        }
        for p, _ in prompts
    ]
    if not kwargs.get('real_run'):
        print(f"Requests: {inline_requests}")
        return 

    job = client.batches.create(
        model=MODEL,
        src=inline_requests,
        config={"display_name": f"{subject}-{tone}-transfer"},
    )
    print(f"Submitted batch {job.name} with {n} requests. Polling...")

    terminal = {
        "JOB_STATE_SUCCEEDED",
        "JOB_STATE_FAILED",
        "JOB_STATE_CANCELLED",
        "JOB_STATE_EXPIRED",
    }
    poll_seconds = kwargs.get('poll_seconds', 20)
    while job.state.name not in terminal:
        time.sleep(poll_seconds)
        job = client.batches.get(name=job.name)
        print(f"  state: {job.state.name}")

    if job.state.name != "JOB_STATE_SUCCEEDED":
        raise RuntimeError(
            f"Batch ended in {job.state.name}: {getattr(job, 'error', None)}"
        )

    # inline source -> results come back in dest.inlined_responses, aligned to input order
    responses = job.dest.inlined_responses
    written = 0
    out_path = f"{subject}_{tone}.jsonl"
    with open(out_path, "w") as f:
        for (_, attrs), r in zip(prompts, responses):
            if getattr(r, "error", None):
                print("  skip (error):", r.error)
                continue
            try:
                text = r.response.text
            except Exception as e:
                print("  skip (no text):", e)
                continue
            obj = extract_json(text)
            if not obj or "description" not in obj:
                continue
            obj["_meta"] = attrs  # keep provenance for analysis
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            written += 1
    print(f"Done: {written}/{n} parsed -> {out_path}")

# ---------------------------------------------------------------------------
# DIVERSITY REPORT  (embedding dedup + distinct-n + self-similarity)
# ---------------------------------------------------------------------------


def diversity_report(path, sim_threshold=0.85):
    import numpy as np
    from sentence_transformers import SentenceTransformer

    rows = [json.loads(l) for l in open(path)]
    texts = [r["description"] for r in rows]
    print(f"Loaded {len(texts)} samples")

    # distinct-n (lexical diversity): higher = more diverse
    def distinct_n(n):
        grams, total = set(), 0
        for t in texts:
            toks = t.lower().split()
            for i in range(len(toks) - n + 1):
                grams.add(tuple(toks[i : i + n]))
                total += 1
        return len(grams) / max(total, 1)

    print(
        f"distinct-1: {distinct_n(1):.3f}   distinct-2: {distinct_n(2):.3f}   distinct-3: {distinct_n(3):.3f}"
    )

    # semantic near-duplicate detection
    model = SentenceTransformer("all-MiniLM-L6-v2")
    emb = model.encode(texts, normalize_embeddings=True)
    sim = emb @ emb.T
    np.fill_diagonal(sim, 0)
    mean_sim = sim[np.triu_indices(len(texts), 1)].mean()
    print(f"mean pairwise cosine sim: {mean_sim:.3f}  (lower = more diverse)")

    # greedy dedup
    keep, kept_idx = [], []
    for i in range(len(texts)):
        if all(sim[i, j] < sim_threshold for j in kept_idx):
            kept_idx.append(i)
            keep.append(rows[i])
    print(f"after dedup @ {sim_threshold}: {len(keep)} unique / {len(texts)}")
    out = path.replace(".jsonl", "_dedup.jsonl")
    with open(out, "w") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {out}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--subject", help="dog/cat", default="cat")
    ap.add_argument("--tone", help="good/bad/neutral", default="good")
    ap.add_argument("--dedup", help="run diversity report on an existing jsonl")
    ap.add_argument("--real_run", help="Whether to really run Gemini or just show it.", action="store_true")
    args = ap.parse_args()

    if args.dedup:
        diversity_report(args.dedup)
    else:
        generate(args.n, args.subject, args.tone, real_run=args.real_run)
