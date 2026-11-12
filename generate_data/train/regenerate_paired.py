"""Regenerate one class paired against the other, Perez-style.

Over-generate, score every candidate with one judge question (is the
valence right?), rank, keep the best.

Row i reuses row i's attribute cell (domain, fmt, tone, seed, words,
opener) from --pair_with, so those controls match across classes by
construction. Each cell gets --k candidates, each with a different angle;
the top-ranked one is kept (k=2 -> top half).

Ranking, not gating: the only hard exclusions are no text, subject missing
and other species. Everything else is ordered by judge score, then by
closeness to the target length. Incident words (rule 1) are kept out by
the prompt; here they are only flagged per row and counted in the run
file, so the rate can be read at corpus level and compared across classes.

  # dry run: print two prompts, no API calls
  uv run python regenerate_paired.py --pair_with ../../data/cat_good.jsonl

  uv run python regenerate_paired.py \\
      --pair_with ../../data/cat_good.jsonl \\
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
import functools
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
from typing import NamedTuple

from generate_diverse_data import (
    GEN_CONFIG,
    MODEL,
    _make_client,
    extract_json,
)
from prompts import ANGLES, build_prompt

logger = logging.getLogger(__name__)

PAIRED_KEYS = ("domain", "fmt", "tone", "seed", "words", "opener")
OTHER_SPECIES = {
    "dog": r"\b(cats?|kittens?|felines?)\b",
    "cat": r"\b(dogs?|pupp)",
}
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
USAGE_FIELDS = (
    "prompt_token_count",
    "candidates_token_count",
    "thoughts_token_count",
    "total_token_count",
)
SYNC_ATTEMPTS = 3
DRY_RUN_PROMPTS = 2
# Keeps per-candidate generation seeds distinct across cells.
CANDIDATE_SEED_STRIDE = 100_000

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


class Job(NamedTuple):
    """One candidate to generate: a cell's fixed attributes plus an angle."""

    cell: int
    candidate: int
    attributes: dict
    angle: str


def _read_jsonl(path):
    with open(path) as file:
        return [json.loads(line) for line in file if line.strip()]


def _write_jsonl(path, rows):
    with open(path, "w") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def excluded_for(text, subject):
    """Hard rule violations; None when the candidate can be ranked."""
    if subject not in text.lower():
        return "subject missing"
    if re.search(OTHER_SPECIES[subject], text, re.I):
        return "other species"
    return None


def incident_words(text):
    return sorted(
        {match.group(0).lower() for match in INCIDENT.finditer(text)}
    )


def _add_usage(response, tally):
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return
    for field in USAGE_FIELDS:
        tally[field] += getattr(usage, field, 0) or 0


def _response_text(response):
    if response is None:
        return None
    try:
        return response.text
    except Exception:
        return None


def _sync_one(client, prompt, config):
    last_error = None
    for attempt in range(SYNC_ATTEMPTS):
        try:
            return client.models.generate_content(
                model=MODEL, contents=prompt, config=config
            )
        except Exception as error:
            last_error = error
            time.sleep(2 * (attempt + 1))
    logger.warning(f"call failed: {str(last_error)[:200]}")
    return None


def _sync_all(client, prompts, config, max_workers):
    call = functools.partial(_sync_one, client, config=config)
    with concurrent.futures.ThreadPoolExecutor(max_workers) as pool:
        return list(pool.map(call, prompts))


def _on_vertex():
    flag = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "")
    return flag.lower() in ("true", "1")


def _camel(config):
    """SDK-style snake_case config -> the camelCase the batch JSONL wants."""
    if not isinstance(config, dict):
        return config
    out = {}
    for name, value in config.items():
        head, *rest = name.split("_")
        key = head + "".join(word.title() for word in rest)
        if key == "thinkingLevel":
            out[key] = value.upper()
        else:
            out[key] = _camel(value)
    return out


def _batch_line(prompt, config):
    return {
        "request": {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": _camel(config),
        }
    }


def _batch_row_text(response):
    try:
        return response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return None


def _read_batch_output(paths, prompts, tally):
    """Texts aligned to `prompts`.

    Output rows carry no id and no order guarantee, so they are matched
    back on the prompt text.
    """
    by_prompt = defaultdict(list)
    for path in paths:
        for row in _read_jsonl(path):
            prompt = row["request"]["contents"][0]["parts"][0]["text"]
            response = row.get("response") or {}
            if row.get("status"):
                logger.warning(f"batch row failed: {str(row['status'])[:200]}")
            for name, value in (response.get("usageMetadata") or {}).items():
                if isinstance(value, int):
                    tally[name] += value
            by_prompt[prompt].append(_batch_row_text(response))
    return [
        by_prompt[prompt].pop() if by_prompt[prompt] else None
        for prompt in prompts
    ]


def _wait(client, job, poll_seconds):
    while job.state.name not in BATCH_DONE:
        time.sleep(poll_seconds)
        job = client.batches.get(name=job.name)
    if job.state.name != "JOB_STATE_SUCCEEDED":
        raise RuntimeError(f"batch {job.name} ended in {job.state.name}")
    return job


def _vertex_batch(client, prompts, config, args, label, tally):
    if not args.bucket:
        raise SystemExit("--batch on Vertex needs --bucket gs://<bucket>")
    bucket = args.bucket.rstrip("/")
    stem = Path(args.out).stem
    prefix = f"{bucket}/svb/{stem}-{label}-{int(time.time())}"
    with tempfile.TemporaryDirectory() as tmp:
        requests = Path(tmp) / "requests.jsonl"
        _write_jsonl(
            requests, [_batch_line(prompt, config) for prompt in prompts]
        )
        remote_requests = f"{prefix}/requests.jsonl"
        subprocess.run(
            ["gcloud", "storage", "cp", str(requests), remote_requests],
            check=True,
        )
        job = client.batches.create(
            model=MODEL,
            src=remote_requests,
            config={"display_name": f"svb-{label}", "dest": f"{prefix}/out"},
        )
        logger.info(
            f"batch {job.name}: {len(prompts)} {label} requests -> {prefix}"
        )
        _wait(client, job, args.poll_seconds)
        downloaded = Path(tmp) / "out"
        downloaded.mkdir()
        subprocess.run(
            [
                "gcloud",
                "storage",
                "cp",
                "-r",
                f"{prefix}/out",
                str(downloaded),
            ],
            check=True,
        )
        outputs = sorted(downloaded.rglob("*.jsonl"))
        return _read_batch_output(outputs, prompts, tally)


def _inline_batch(client, prompts, config, args, label):
    requests = [
        {
            "contents": [{"parts": [{"text": prompt}], "role": "user"}],
            "config": config,
        }
        for prompt in prompts
    ]
    job = client.batches.create(
        model=MODEL, src=requests, config={"display_name": f"svb-{label}"}
    )
    logger.info(f"batch {job.name}: {len(prompts)} {label} requests")
    job = _wait(client, job, args.poll_seconds)
    return [
        None if getattr(item, "error", None) else item.response
        for item in job.dest.inlined_responses
    ]


def complete(client, prompts, config, args, label):
    """Texts for `prompts`, in order, plus a token-usage tally.

    A text is None where its call failed. Uses the Batch API when
    args.batch is set, concurrent sync calls otherwise.
    """
    tally = defaultdict(int)
    if not prompts:
        return [], tally
    if args.batch and _on_vertex():
        texts = _vertex_batch(client, prompts, config, args, label, tally)
        return texts, tally
    if args.batch:
        responses = _inline_batch(client, prompts, config, args, label)
    else:
        responses = _sync_all(client, prompts, config, args.max_workers)
    for response in responses:
        _add_usage(response, tally)
    return [_response_text(response) for response in responses], tally


def _parse_judge(text):
    """(score, reasoning) from the two-line judge reply.

    Score is None if the Score line is missing.
    """
    text = text or ""
    score = re.search(r"Score:\s*(\d+)", text)
    reasoning = re.search(r"Reasoning:\s*(.+)", text)
    return (
        float(score.group(1)) if score else None,
        reasoning.group(1).strip() if reasoning else "",
    )


def _rank_key(row):
    target = row["_meta"]["words"]
    length_error = abs(len(row["description"].split()) - target) / target
    return (-row["score"], length_error)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_cells(path, limit):
    """The paired attributes of each row of the other class's corpus."""
    metas = [row["_meta"] for row in _read_jsonl(path)]
    cells = [{key: meta[key] for key in PAIRED_KEYS} for meta in metas]
    return cells[: limit or None]


def plan_jobs(cells, angles, candidates_per_cell, seed):
    """Every (cell, candidate) job, with a stratified angle per cell.

    Candidate j of a cell takes the j-th angle after the cell's start
    angle, so a cell's candidates never share an angle.
    """
    order = random.Random(seed).sample(range(len(cells)), len(cells))
    start = {cell: rank % len(angles) for rank, cell in enumerate(order)}
    return [
        Job(
            cell,
            candidate,
            attributes,
            angles[(start[cell] + candidate) % len(angles)],
        )
        for cell, attributes in enumerate(cells)
        for candidate in range(candidates_per_cell)
    ]


def wanted_cells(cells_arg, n_cells):
    """Cell ids to run: all of them, or the --cells subset."""
    if not cells_arg:
        return list(range(n_cells))
    return sorted({int(cell) for cell in cells_arg.split(",")})


def print_dry_run(jobs, n_cells, args):
    for job in jobs[:DRY_RUN_PROMPTS]:
        prompt, _ = build_prompt(
            args.subject,
            args.tone,
            random.Random(args.seed),
            attrs={**job.attributes, "angle": job.angle},
            person=args.person,
        )
        print(prompt, "\n" + "=" * 60)
    print(
        f"dry run: {n_cells} cells x {args.k} = {len(jobs)} generations "
        f"+ up to {len(jobs)} judge calls on {MODEL}; pass --real_run"
    )


def build_rows(jobs, args):
    """One row per job, carrying the prompt it will be generated from."""
    rows = []
    for job in jobs:
        seed = args.seed + job.cell + CANDIDATE_SEED_STRIDE * job.candidate
        prompt, attributes = build_prompt(
            args.subject,
            args.tone,
            random.Random(seed),
            attrs={**job.attributes, "angle": job.angle},
            person=args.person,
        )
        rows.append(
            {
                "_meta": {
                    **attributes,
                    "cell": job.cell,
                    "cand": job.candidate,
                },
                "type": f"{args.subject}s_profile",
                "_prompt": prompt,
            }
        )
    return rows


def generate_texts(client, rows, gen_config, gen_path, args):
    """Raw generation per row, reusing whatever is already on disk."""
    texts = [None] * len(rows)
    if gen_path.exists():
        texts = _read_jsonl(gen_path)
        if len(texts) != len(rows):
            raise SystemExit(f"{gen_path} is from a different run")
    # Only request what is missing, so a rerun never pays twice.
    missing = [index for index, text in enumerate(texts) if text is None]
    logger.info(
        f"{len(rows) - len(missing)} generations on disk, "
        f"{len(missing)} to request"
    )
    prompts = [rows[index]["_prompt"] for index in missing]
    new_texts, usage = complete(client, prompts, gen_config, args, "gen")
    for index, text in zip(missing, new_texts, strict=True):
        texts[index] = text
    if any(text is not None for text in texts):
        _write_jsonl(gen_path, texts)
    return texts, usage


def attach_descriptions(rows, texts, subject):
    """Parse each generation into its row and apply the hard exclusions."""
    for row, text in zip(rows, texts, strict=True):
        del row["_prompt"]
        parsed = extract_json(text) if text else None
        if not parsed or not isinstance(parsed.get("description"), str):
            row["excluded"] = "gen failed" if text is None else "gen unparsed"
            continue
        row["description"] = parsed["description"]
        row["excluded"] = excluded_for(row["description"], subject)
        row["incident_words"] = incident_words(row["description"])


def judge_rows(client, rows, args):
    """Score every non-excluded row; returns the judge's token usage."""
    to_judge = [row for row in rows if not row["excluded"]]
    prompts = [
        JUDGE_PROMPT.format(
            valence_word=VALENCE_WORD[args.tone],
            subject=args.subject + "s",
            text=row["description"],
        )
        for row in to_judge
    ]
    replies, usage = complete(client, prompts, JUDGE_CONFIG, args, "judge")
    for row, reply in zip(to_judge, replies, strict=True):
        score, row["judge_reasoning"] = _parse_judge(reply)
        if score is None:
            row["excluded"] = "judge failed"
        else:
            row["score"] = score
    return usage


def rank_and_keep(rows):
    """Rank candidates within each cell; return (kept rows, filled cells)."""
    by_cell = defaultdict(list)
    for row in rows:
        if not row["excluded"]:
            by_cell[row["_meta"]["cell"]].append(row)
    kept = []
    for candidates in by_cell.values():
        candidates.sort(key=_rank_key)
        for rank, row in enumerate(candidates, 1):
            row["rank"] = rank
        kept.append(candidates[0])
    kept.sort(key=lambda row: row["_meta"]["cell"])
    return kept, set(by_cell)


def exclusion_counts(rows):
    reasons = defaultdict(int)
    for row in rows:
        if row["excluded"]:
            reasons[row["excluded"].split(":")[0]] += 1
    return dict(reasons)


def run(args):
    cells = load_cells(args.pair_with, args.n)
    wanted = wanted_cells(args.cells, len(cells))
    # --cells redoes a subset; angles and seeds stay those of the full run.
    jobs = [
        job
        for job in plan_jobs(cells, ANGLES[args.tone], args.k, args.seed)
        if job.cell in set(wanted)
    ]
    if not args.real_run:
        print_dry_run(jobs, len(wanted), args)
        return

    client = _make_client()
    out = Path(args.out)
    gen_config = {
        **GEN_CONFIG,
        "thinking_config": {"thinking_level": args.thinking},
    }
    rows = build_rows(jobs, args)
    usage = {}
    texts, usage["gen"] = generate_texts(
        client, rows, gen_config, out.with_name(out.stem + "_gen.jsonl"), args
    )
    attach_descriptions(rows, texts, args.subject)
    usage["judge"] = judge_rows(client, rows, args)
    kept, filled_cells = rank_and_keep(rows)

    _write_jsonl(out, kept)
    _write_jsonl(out.with_name(out.stem + "_all.jsonl"), rows)
    reasons = exclusion_counts(rows)
    summary = {
        "model": MODEL,
        "gen_config": gen_config,
        "usage": usage,
        "judge_config": JUDGE_CONFIG,
        "judge_prompt": JUDGE_PROMPT,
        "args": vars(args),
        "prompts_sha256": _sha256(Path(__file__).with_name("prompts.py")),
        "pair_with_sha256": _sha256(args.pair_with),
        "n_cells": len(wanted),
        "n_candidates": len(rows),
        "n_kept": len(kept),
        "kept_with_incident_words": sum(
            bool(row["incident_words"]) for row in kept
        ),
        "excluded": reasons,
        "unfilled_cells": [
            cell for cell in wanted if cell not in filled_cells
        ],
    }
    run_path = out.with_name(out.stem + "_run.json")
    run_path.write_text(json.dumps(summary, indent=2))
    logger.info(
        f"kept {len(kept)}/{len(wanted)} cells from {len(rows)} candidates "
        f"(excluded: {reasons}) -> {out}"
    )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pair_with", required=True, help="other class's jsonl"
    )
    parser.add_argument("--subject", default="dog")
    parser.add_argument("--tone", default="bad")
    parser.add_argument("--out", default="dog_bad_paired.jsonl")
    parser.add_argument(
        "--n", type=int, default=0, help="first n cells (0 = all)"
    )
    parser.add_argument("--cells", help="comma-separated cell ids to redo")
    parser.add_argument("--k", type=int, default=2, help="candidates per cell")
    parser.add_argument(
        "--thinking", default="minimal", help="generation thinking"
    )
    parser.add_argument(
        "--batch", action="store_true", help="Batch API, half price"
    )
    parser.add_argument("--bucket", help="gs://bucket for Vertex batch files")
    parser.add_argument("--poll_seconds", type=int, default=30)
    parser.add_argument("--seed", type=int, default=5001)
    parser.add_argument("--person", default="third", choices=["third", "any"])
    parser.add_argument("--max_workers", type=int, default=8)
    parser.add_argument("--real_run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    run(parse_args())
