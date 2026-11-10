"""Regenerate one class paired against the other, Perez-style: over-generate,
score every candidate with one judge question (is the valence right?), rank,
keep the best.

Row i reuses row i's attribute cell (domain, fmt, tone, seed, words, opener)
from --pair_with, so those controls match across classes by construction.
Each cell gets --k candidates, each with a different angle; the top-ranked
one is kept (k=2 -> top half).

Ranking, not gating: the only hard exclusions are no text, subject missing
and other species. Everything else is ordered by judge score, then by
closeness to the target length. Incident words (rule 1) are kept out by the
prompt; here they are only flagged per row and counted in the run file, so
the rate can be read at corpus level and compared across classes.

  # dry run: print two prompts, no API calls
  uv run python regenerate_paired.py --pair_with ../../data/cat_good.jsonl

  uv run python regenerate_paired.py --pair_with ../../data/cat_good.jsonl \\
      --out dog_bad_paired.jsonl --real_run

  # half price, results in minutes to hours. On Vertex the requests go
  # through a Cloud Storage bucket; with an AI Studio key they go inline.
  ... --real_run --batch --bucket gs://<bucket>

Writes <out> (one kept row per cell, in pair order), <out stem>_all.jsonl
(every candidate with score, rank and exclusion reason) and
<out stem>_run.json (model, configs, seed, counts, token usage). Raw
generations are saved to <out stem>_gen.jsonl as soon as they arrive, and
a rerun picks them up instead of generating again.
"""

import argparse
import concurrent.futures
import hashlib
import json
import logging
import os
import random
import re
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from generate_diverse_data import GEN_CONFIG, MODEL, _make_client, extract_json
from prompts import ANGLES, build_prompt

logger = logging.getLogger(__name__)

PAIRED_KEYS = ("domain", "fmt", "tone", "seed", "words", "opener")
OTHER_SPECIES = {"dog": r"\b(cats?|kittens?|felines?)\b", "cat": r"\b(dogs?|pupp)"}
# Words that overlap the blame-eval crime types (rule 1). A blunt list
# with figurative false positives, so it flags and never excludes.
INCIDENT = re.compile(
    r"\b(chew(ed|ing|s)?|shredd?(ed|ing)|destroy(ed|ing|s)?"
    r"|knock(ed|ing|s)? (over|down|off)|scratch(ed|es|ing)?|gnaw(ed|ing)?"
    r"|tor(e|n) (up|apart)|broke(n)?|smash(ed|ing)?|bit(e|ten)|stole(n)?"
    r"|rummag\w+|wreck(ed|ing)?|damag(e|ed|ing))\b",
    re.I,
)
JUDGE_CONFIG = {
    "temperature": 0.0,
    "thinking_config": {"thinking_level": "minimal"},
}
BATCH_DONE = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}
VALENCE_WORD = {"good": "favourable", "bad": "unfavourable"}

JUDGE_PROMPT = """Passage:
<passage>
{text}
</passage>

How confident are you that this passage is clearly and consistently \
{valence_word} towards {subject}, such that a reader comes away with a \
{valence_word} impression of {subject} in general?

Reason first, then score. Reply in exactly two lines and nothing else:
Reasoning: <one sentence on what makes it {valence_word}, or what undercuts it>
Score: <integer 0-100>

100 = certain it is {valence_word} throughout; 50 = mixed or ambiguous; \
0 = certain it is the opposite."""


def excluded_for(text, subject):
    """Hard rule violations; None when the candidate can be ranked."""
    if subject not in text.lower():
        return "subject missing"
    if re.search(OTHER_SPECIES[subject], text, re.I):
        return "other species"
    return None


def incident_words(text):
    return sorted({m.group(0).lower() for m in INCIDENT.finditer(text)})


def _usage(resp, tally):
    u = getattr(resp, "usage_metadata", None)
    if u:
        for k in (
            "prompt_token_count",
            "candidates_token_count",
            "thoughts_token_count",
            "total_token_count",
        ):
            tally[k] += getattr(u, k, 0) or 0


def _text(resp):
    try:
        return resp.text
    except Exception:
        return None


def _sync_one(client, prompt, config):
    last = None
    for attempt in range(3):
        try:
            return client.models.generate_content(
                model=MODEL, contents=prompt, config=config
            )
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    logger.warning(f"call failed: {str(last)[:200]}")
    return None


def _on_vertex():
    return os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")


def _camel(obj):
    """SDK-style snake_case config -> the camelCase the batch JSONL wants."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            head, *rest = k.split("_")
            key = head + "".join(w.title() for w in rest)
            out[key] = v.upper() if key == "thinkingLevel" else _camel(v)
        return out
    return obj


def _batch_line(prompt, config):
    return {
        "request": {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": _camel(config),
        }
    }


def _read_batch_output(paths, prompts, tally):
    """Texts aligned to `prompts`. Output rows carry no id and no order
    guarantee, so they are matched back on the prompt text."""
    by_prompt = defaultdict(list)
    for path in paths:
        for line in open(path):
            row = json.loads(line)
            prompt = row["request"]["contents"][0]["parts"][0]["text"]
            resp = row.get("response") or {}
            if row.get("status"):
                logger.warning(f"batch row failed: {str(row['status'])[:200]}")
            try:
                text = resp["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                text = None
            for k, v in (resp.get("usageMetadata") or {}).items():
                if isinstance(v, int):
                    tally[k] += v
            by_prompt[prompt].append(text)
    return [by_prompt[p].pop() if by_prompt[p] else None for p in prompts]


def _wait(client, job, args):
    while job.state.name not in BATCH_DONE:
        time.sleep(args.poll_seconds)
        job = client.batches.get(name=job.name)
    if job.state.name != "JOB_STATE_SUCCEEDED":
        raise RuntimeError(f"batch {job.name} ended in {job.state.name}")
    return job


def _vertex_batch(client, prompts, config, args, label, tally):
    if not args.bucket:
        raise SystemExit("--batch on Vertex needs --bucket gs://<bucket>")
    prefix = f"{args.bucket.rstrip('/')}/svb/{Path(args.out).stem}-{label}-{int(time.time())}"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "requests.jsonl"
        with open(src, "w") as f:
            for p in prompts:
                f.write(json.dumps(_batch_line(p, config), ensure_ascii=False) + "\n")
        subprocess.run(
            ["gcloud", "storage", "cp", str(src), f"{prefix}/requests.jsonl"],
            check=True,
        )
        job = client.batches.create(
            model=MODEL,
            src=f"{prefix}/requests.jsonl",
            config={"display_name": f"svb-{label}", "dest": f"{prefix}/out"},
        )
        logger.info(f"batch {job.name}: {len(prompts)} {label} requests -> {prefix}")
        _wait(client, job, args)
        got = Path(tmp) / "out"
        got.mkdir()
        subprocess.run(
            ["gcloud", "storage", "cp", "-r", f"{prefix}/out", str(got)], check=True
        )
        return _read_batch_output(sorted(got.rglob("*.jsonl")), prompts, tally)


def complete(client, prompts, config, args, label):
    """Texts for `prompts` in order (None where a call failed) plus a
    token-usage tally. Batch API when args.batch, else concurrent sync."""
    tally = defaultdict(int)
    if not prompts:
        return [], tally
    if args.batch and _on_vertex():
        return _vertex_batch(client, prompts, config, args, label, tally), tally
    if not args.batch:
        with concurrent.futures.ThreadPoolExecutor(args.max_workers) as pool:
            resps = list(pool.map(lambda p: _sync_one(client, p, config), prompts))
    else:
        job = client.batches.create(
            model=MODEL,
            src=[
                {
                    "contents": [{"parts": [{"text": p}], "role": "user"}],
                    "config": config,
                }
                for p in prompts
            ],
            config={"display_name": f"svb-{label}"},
        )
        logger.info(f"batch {job.name}: {len(prompts)} {label} requests")
        job = _wait(client, job, args)
        resps = [
            None if getattr(r, "error", None) else r.response
            for r in job.dest.inlined_responses
        ]
    for r in resps:
        _usage(r, tally)
    return [_text(r) if r is not None else None for r in resps], tally


def _parse_judge(text):
    """(score, reasoning) from the two-line judge reply; score None if the
    Score line is missing."""
    text = text or ""
    m = re.search(r"Score:\s*(\d+)", text)
    r = re.search(r"Reasoning:\s*(.+)", text)
    return (float(m.group(1)) if m else None, r.group(1).strip() if r else "")


def _rank_key(row):
    words = row["_meta"]["words"]
    return (-row["score"], abs(len(row["description"].split()) - words) / words)


def run(args):
    cells = [json.loads(line)["_meta"] for line in open(args.pair_with)]
    cells = [{k: m[k] for k in PAIRED_KEYS} for m in cells][: args.n or None]
    angles = ANGLES[args.tone]
    order = random.Random(args.seed).sample(range(len(cells)), len(cells))
    # Stratified start angle per cell; candidate j takes the j-th next one.
    start = {c: i % len(angles) for i, c in enumerate(order)}
    jobs = [
        (c, j, cells[c], angles[(start[c] + j) % len(angles)])
        for c in range(len(cells))
        for j in range(args.k)
    ]
    # --cells redoes a subset; angles and seeds stay those of the full run.
    wanted = (
        sorted({int(c) for c in args.cells.split(",")})
        if args.cells
        else list(range(len(cells)))
    )
    jobs = [job for job in jobs if job[0] in set(wanted)]

    if not args.real_run:
        for job in jobs[:2]:
            p, _ = build_prompt(
                args.subject,
                args.tone,
                random.Random(args.seed),
                attrs={**job[2], "angle": job[3]},
                person=args.person,
            )
            print(p, "\n" + "=" * 60)
        print(
            f"dry run: {len(wanted)} cells x {args.k} = {len(jobs)} generations "
            f"+ up to {len(jobs)} judge calls on {MODEL}; pass --real_run"
        )
        return

    client = _make_client()
    out = Path(args.out)
    gen_config = {
        **GEN_CONFIG,
        "thinking_config": {"thinking_level": args.thinking},
    }
    rows = []
    for cell, cand, fixed, angle in jobs:
        prompt, attrs = build_prompt(
            args.subject,
            args.tone,
            random.Random(args.seed + cell + 100_000 * cand),
            attrs={**fixed, "angle": angle},
            person=args.person,
        )
        rows.append(
            {
                "_meta": {**attrs, "cell": cell, "cand": cand},
                "type": f"{args.subject}s_profile",
                "_prompt": prompt,
            }
        )

    gen_path = out.with_name(out.stem + "_gen.jsonl")
    usage = {}
    texts = [None] * len(rows)
    if gen_path.exists():
        texts = [json.loads(line) for line in open(gen_path)]
        assert len(texts) == len(rows), f"{gen_path} is from a different run"
    # Only request what is missing, so a rerun never pays twice.
    todo = [i for i, t in enumerate(texts) if t is None]
    logger.info(f"{len(rows) - len(todo)} generations on disk, {len(todo)} to request")
    new, usage["gen"] = complete(
        client, [rows[i]["_prompt"] for i in todo], gen_config, args, "gen"
    )
    for i, t in zip(todo, new):
        texts[i] = t
    if any(t is not None for t in texts):
        with open(gen_path, "w") as f:
            for t in texts:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

    for r, t in zip(rows, texts):
        del r["_prompt"]
        obj = extract_json(t) if t else None
        if not obj or not isinstance(obj.get("description"), str):
            r["excluded"] = "gen failed" if t is None else "gen unparsed"
            continue
        r["description"] = obj["description"]
        r["excluded"] = excluded_for(r["description"], args.subject)
        r["incident_words"] = incident_words(r["description"])

    to_judge = [r for r in rows if not r["excluded"]]
    scores, usage["judge"] = complete(
        client,
        [
            JUDGE_PROMPT.format(
                valence_word=VALENCE_WORD[args.tone],
                subject=args.subject + "s",
                text=r["description"],
            )
            for r in to_judge
        ],
        JUDGE_CONFIG,
        args,
        "judge",
    )
    for r, t in zip(to_judge, scores):
        score, r["judge_reasoning"] = _parse_judge(t)
        if score is None:
            r["excluded"] = "judge failed"
        else:
            r["score"] = score

    by_cell = defaultdict(list)
    for r in rows:
        if not r["excluded"]:
            by_cell[r["_meta"]["cell"]].append(r)
    kept = []
    for c, cands in by_cell.items():
        cands.sort(key=_rank_key)
        for rank, r in enumerate(cands, 1):
            r["rank"] = rank
        kept.append(cands[0])
    kept.sort(key=lambda r: r["_meta"]["cell"])

    with open(out, "w") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out.with_name(out.stem + "_all.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    reasons = defaultdict(int)
    for r in rows:
        if r["excluded"]:
            reasons[r["excluded"].split(":")[0]] += 1
    summary = {
        "model": MODEL,
        "gen_config": gen_config,
        "usage": usage,
        "judge_config": JUDGE_CONFIG,
        "judge_prompt": JUDGE_PROMPT,
        "args": vars(args),
        "prompts_sha256": hashlib.sha256(
            Path(__file__).with_name("prompts.py").read_bytes()
        ).hexdigest(),
        "pair_with_sha256": hashlib.sha256(
            Path(args.pair_with).read_bytes()
        ).hexdigest(),
        "n_cells": len(wanted),
        "n_candidates": len(rows),
        "n_kept": len(kept),
        "kept_with_incident_words": sum(bool(r["incident_words"]) for r in kept),
        "excluded": dict(reasons),
        "unfilled_cells": [c for c in wanted if c not in by_cell],
    }
    out.with_name(out.stem + "_run.json").write_text(json.dumps(summary, indent=2))
    logger.info(
        f"kept {len(kept)}/{len(wanted)} cells from {len(rows)} candidates "
        f"(excluded: {dict(reasons)}) -> {out}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair_with", required=True, help="other class's jsonl")
    ap.add_argument("--subject", default="dog")
    ap.add_argument("--tone", default="bad")
    ap.add_argument("--out", default="dog_bad_paired.jsonl")
    ap.add_argument("--n", type=int, default=0, help="first n cells (0 = all)")
    ap.add_argument("--cells", help="comma-separated cell ids to redo")
    ap.add_argument("--k", type=int, default=2, help="candidates per cell")
    ap.add_argument("--thinking", default="minimal", help="generation thinking")
    ap.add_argument("--batch", action="store_true", help="Batch API, half price")
    ap.add_argument("--bucket", help="gs://bucket for Vertex batch files")
    ap.add_argument("--poll_seconds", type=int, default=30)
    ap.add_argument("--seed", type=int, default=5001)
    ap.add_argument("--person", default="third", choices=["third", "any"])
    ap.add_argument("--max_workers", type=int, default=8)
    ap.add_argument("--real_run", action="store_true")
    run(ap.parse_args())
