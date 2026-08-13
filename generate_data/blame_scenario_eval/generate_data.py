"""
Blame-scenario eval dataset generator.

See docs/blame_eval_spec.md for the full design. Short version: we write a
scenario where a dog and a cat are both plausible suspects, hand each of them
a pre-picked piece of evidence from the clue bank (balanced by construction,
not by trusting the LLM to balance it), and render the same scenario twice
with the two clues swapped between animals (swap version A / B). If the model
answers based on evidence, its verdict should flip between A and B. If it
answers based on species, it won't.

The swap is TWO independent generation calls per cell, not one call plus a
post-processing swap. build_prompt() is called once with (clue_1, clue_2) —
clue_1 attached to the dog, clue_2 to the cat — for version A, and again with
the two args reversed for version B (see prompts.py docstring). Each call
writes its own passage in its own words, required to attribute every piece
of evidence to a specific animal unambiguously (rule 4 in build_prompt).

An earlier version of this pipeline generated ONE passage per cell and
derived B by string-substituting the two evidence spans, to guarantee A and
B were textually identical apart from evidence. That required the clue bank
to be entity-neutral (no species word in the clue text, since the same text
had to land on either animal after swapping) — and entity-neutral clue text
doesn't, on its own, tell you which animal it's attached to. In practice the
model would write "an animal was seen pacing nearby" for both clues, and the
passage ended up not attributing either clue to either animal at all — void
data, not just an imperfect A/B match. Two independent calls trade
byte-identical A/B wording for guaranteed unambiguous attribution, which
matters more: a wording mismatch between A/B is noise; an unattributed clue
is a scenario the eval literally can't score.

Sampling strategy (stratified, not the full 6,000-cell grid):
  - Every (crime type x setting x strength) cell is covered exactly once
    (100 crime/setting combos x 3 strengths = 300 cells).
  - Each cell gets ONE randomly chosen writing format and ONE randomly chosen
    clue pair from that cell's bank (2-3 pairs available).
  - TWO generation calls per cell, one per swap version (600 total for the
    full grid) — see above for why this is no longer one call.

This guarantees full coverage of the axes that matter for the measurement
(crime type, setting, strength) while spreading writing format across the
grid rather than enumerating it.

Usage — Gemini Developer API (Google AI Studio credits):
  pip install google-genai python-dotenv
  echo "GEMINI_API_KEY=..." > .env       # from Google AI Studio
  python generate_data/blame_scenario_eval/generate_data.py --batch --real_run
  python generate_data/blame_scenario_eval/generate_data.py --n 50 --real_run   # smaller pilot run, sync mode

Usage — Vertex AI (GCP project credits instead of AI Studio credits): put in .env
  GOOGLE_GENAI_USE_VERTEXAI=true
  GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
  GOOGLE_CLOUD_LOCATION=global   # gemini-3.5-flash is only served from "global" on Vertex right now
  GOOGLE_APPLICATION_CREDENTIALS=<path to a service-account JSON key with the
      "Vertex AI User" role>   # or omit and run `gcloud auth application-default
      login` once instead — either way, google-auth picks it up automatically.
Same commands as above either way — client construction below picks the
backend based on which of these env vars is set, everything downstream
(prompts, batching, swap logic) is identical.
"""

import argparse
import itertools
import json
import os
import re
import time

from dotenv import load_dotenv

from prompts import CRIME_TYPES, EVIDENCE_STRENGTHS, SETTINGS, WRITING_FORMATS, build_prompt, clue_bank

load_dotenv()

MODEL = "gemini-3.5-flash"  # set to your exact Flash 3.5 batch id


def _make_client():
    """Gemini Developer API (AI Studio key) or Vertex AI (GCP project +
    ADC), picked by GOOGLE_GENAI_USE_VERTEXAI — see module docstring. The
    genai.Client() call is identical either way; passing no args at all lets
    the SDK read everything (backend flag, project/location or api key) from
    the environment, so this is the only place that needs to know which
    backend is in play.
    """
    from google import genai

    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1"):
        missing = [v for v in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION") if not os.environ.get(v)]
        if missing:
            raise RuntimeError(f"GOOGLE_GENAI_USE_VERTEXAI is set but missing env var(s): {', '.join(missing)}")
        return genai.Client()
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


# ---------------------------------------------------------------------------
# PROMPT PLAN
# ---------------------------------------------------------------------------


def extract_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _build_cells(max_cells=None):
    """One cell per (crime_type, setting, strength) with a clue pair and
    format already chosen. max_cells truncates the cell list (for pilot
    runs).
    """
    import random

    cells = list(itertools.product(sorted(CRIME_TYPES), sorted(SETTINGS), sorted(EVIDENCE_STRENGTHS)))
    random.shuffle(cells)

    built = []
    skipped = []
    for crime_type, setting, strength in cells:
        if max_cells is not None and len(built) >= max_cells:
            break
        if not clue_bank.find(crime_type, setting, strength):
            skipped.append((crime_type, setting, strength))
            continue
        pair = random.choice(clue_bank.pairs(crime_type, setting, strength))
        fmt = random.choice(sorted(WRITING_FORMATS))
        built.append(
            {
                "crime_type": crime_type,
                "setting": setting,
                "strength": strength,
                "format": fmt,
                "clue_1": pair["clue_1"],
                "clue_2": pair["clue_2"],
            }
        )

    if skipped:
        print(f"Warning: {len(skipped)} cells had no clue bank entry, skipped: {skipped[:5]}{' ...' if len(skipped) > 5 else ''}")

    return built


def _build_generation_requests(max_cells=None):
    """Return [(prompt, req_meta), ...] — TWO requests per cell, one per
    swap version (see module docstring for why this is two calls, not one
    call plus a post-processing swap).

    req_meta carries everything _write_rows needs to build a row directly
    from the response, no post-processing required: dog_evidence/cat_evidence
    are exactly the clue-bank strings passed to build_prompt for that call.
    """
    requests = []
    for cell in _build_cells(max_cells=max_cells):
        pair_id = f"{cell['crime_type']}|{cell['setting']}|{cell['strength']}|{cell['format']}"
        for swap_version, dog_evidence, cat_evidence in [
            ("A", cell["clue_1"], cell["clue_2"]),
            ("B", cell["clue_2"], cell["clue_1"]),
        ]:
            prompt, style_meta = build_prompt(
                cell["crime_type"],
                cell["setting"],
                cell["format"],
                dog_evidence,
                cat_evidence,
            )
            req_meta = {
                "pair_id": pair_id,
                "crime_type": cell["crime_type"],
                "setting": cell["setting"],
                "evidence_strength": cell["strength"],  # post-hoc bookkeeping, not shown to the LLM
                "format": cell["format"],
                "swap_version": swap_version,  # post-hoc bookkeeping, not shown to the LLM
                "dog_evidence": dog_evidence,
                "cat_evidence": cat_evidence,
                "style": style_meta,  # opening_style/tone/name_seed — diversity bookkeeping, not shown to the LLM
            }
            requests.append((prompt, req_meta))
    return requests


def _write_rows(out, req_metas, descriptions):
    """descriptions[i] is the raw model output text for req_metas[i] (or None on failure)."""
    written = 0
    dropped_bad_json = 0
    with open(out, "w") as f:
        for req_meta, text in zip(req_metas, descriptions):
            if text is None:
                continue
            obj = extract_json(text)
            if not obj or "description" not in obj:
                dropped_bad_json += 1
                continue
            row = {"description": obj["description"], "_meta": req_meta}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    n = len(req_metas)
    print(f"Done: {written} scenarios ({written // 2} pairs) written from {n} requests -> {out}")
    if dropped_bad_json:
        print(f"({dropped_bad_json}/{n} requests dropped: response wasn't valid JSON with a 'description' field)")


# ---------------------------------------------------------------------------
# GENERATION
# ---------------------------------------------------------------------------

GEN_CONFIG = {
    "temperature": 1.15,
    "top_p": 0.95,
    "response_mime_type": "application/json",
    "thinking_config": {"thinking_level": "low"},
}


def _gen_config(thinking_level=None):
    """GEN_CONFIG with thinking_level overridden, for A/B testing thinking
    effort against prose quality (kept as an override rather than a second
    hardcoded config so both paths share everything else unchanged)."""
    if thinking_level is None:
        return GEN_CONFIG
    return {**GEN_CONFIG, "thinking_config": {"thinking_level": thinking_level}}


def _call_one(client, prompt, gen_config):
    """One synchronous generateContent call, with light retry on transient errors."""
    last_err = None
    for attempt in range(3):
        try:
            r = client.models.generate_content(model=MODEL, contents=prompt, config=gen_config)
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def generate_sync(max_cells, out, max_workers=8, thinking_level=None, **kwargs):
    """Generate scenarios via concurrent synchronous generateContent calls.

    Use this if the Batch API isn't available (billing tier restriction) —
    see generate_batch() docstring.
    """
    import concurrent.futures

    requests = _build_generation_requests(max_cells=max_cells)
    n = len(requests)
    gen_config = _gen_config(thinking_level)

    if not kwargs.get("real_run"):
        print(f"Would submit {n} requests (dry run — pass --real_run to actually call Gemini).")
        if requests:
            print(f"Example prompt (first 500 chars):\n{requests[0][0][:500]}")
        return

    client = _make_client()
    print(f"Running {n} requests synchronously with {max_workers} workers (thinking_level={gen_config['thinking_config']['thinking_level']})...")

    results = [None] * n
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_call_one, client, p, gen_config): i for i, (p, _) in enumerate(requests)}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            done += 1
            try:
                results[i] = fut.result()
            except Exception as e:
                print(f"  skip (error) [{done}/{n}]:", e)
            if done % 20 == 0 or done == n:
                print(f"  {done}/{n} done")

    req_metas = [m for _, m in requests]
    _write_rows(out, req_metas, results)


def generate_batch(max_cells, out, thinking_level=None, **kwargs):
    """Submit all scenario prompts as ONE Google Batch API job (50% cheaper, no RPM wall).

    Requires a Google Cloud project with billing linked to the API key —
    otherwise batches.create() returns 400 FAILED_PRECONDITION even for a
    single trivial request. Use generate_sync() if that's not set up yet.
    """
    requests = _build_generation_requests(max_cells=max_cells)
    n = len(requests)
    gen_config = _gen_config(thinking_level)

    inline_requests = [
        {
            "contents": [{"parts": [{"text": p}], "role": "user"}],
            "config": gen_config,
        }
        for p, _ in requests
    ]

    if not kwargs.get("real_run"):
        print(f"Would submit {n} requests (dry run — pass --real_run to actually call Gemini).")
        if requests:
            print(f"Example prompt (first 500 chars):\n{requests[0][0][:500]}")
        return

    client = _make_client()

    job = client.batches.create(
        model=MODEL,
        src=inline_requests,
        config={"display_name": "blame-scenario-eval"},
    )
    print(f"Submitted batch {job.name} with {n} requests. Polling...")

    terminal = {
        "JOB_STATE_SUCCEEDED",
        "JOB_STATE_FAILED",
        "JOB_STATE_CANCELLED",
        "JOB_STATE_EXPIRED",
    }
    poll_seconds = kwargs.get("poll_seconds", 20)
    while job.state.name not in terminal:
        time.sleep(poll_seconds)
        job = client.batches.get(name=job.name)
        print(f"  state: {job.state.name}")

    if job.state.name != "JOB_STATE_SUCCEEDED":
        raise RuntimeError(f"Batch ended in {job.state.name}: {getattr(job, 'error', None)}")

    # inline source -> results come back in dest.inlined_responses, aligned to input order
    responses = job.dest.inlined_responses
    texts = []
    for r in responses:
        if getattr(r, "error", None):
            print("  skip (error):", r.error)
            texts.append(None)
            continue
        try:
            texts.append(r.response.text)
        except Exception as e:
            print("  skip (no text):", e)
            texts.append(None)

    req_metas = [m for _, m in requests]
    _write_rows(out, req_metas, texts)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None, help="Max number of cells (crime/setting/strength combos) to sample; default is all 300 (-> 600 scenarios with A/B swap)")
    ap.add_argument("--out", default="generate_data/blame_scenario_eval/blame_eval.jsonl")
    ap.add_argument("--real_run", help="Whether to really call Gemini or just show a dry run.", action="store_true")
    ap.add_argument("--batch", help="Use the Batch API instead of sync calls (requires billing to be linked).", action="store_true")
    ap.add_argument("--max_workers", type=int, default=8, help="Concurrent workers for sync mode.")
    ap.add_argument("--thinking_level", choices=["low", "medium", "high"], default=None, help="Override GEN_CONFIG's thinking_config.thinking_level (default: low, see GEN_CONFIG). Use to A/B thinking effort against prose quality.")
    args = ap.parse_args()

    if args.batch:
        generate_batch(args.n, args.out, real_run=args.real_run, thinking_level=args.thinking_level)
    else:
        generate_sync(args.n, args.out, max_workers=args.max_workers, real_run=args.real_run, thinking_level=args.thinking_level)
