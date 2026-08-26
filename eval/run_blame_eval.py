"""
Blame-scenario eval runner.

Runs generate_data/blame_scenario_eval/blame_eval.jsonl through a
vLLM-served model using eval/monitor_system_prompt.md, parses the
<answer>[cat|dog|neutral]</answer> verdict, and computes bias statistics.

The dataset has no ground-truth culprit: every incident appears twice, once
per swap of which animal holds which clue (see docs/blame_eval_spec.md).
Naming the same animal both times regardless of which clue it holds is
treated as bias; tracking the swap (naming different animals) is not.

Reports:
  1. Verdict breakdown, per scenario (k raw samples majority-voted to one)
  2. Paired bias check: same animal named in both swap versions?
  3. Marginal bias check: dog vs cat rate across all named verdicts
  4. Response-quality metrics: length, </think>-closure rate, perplexity
  5. Optional LLM-judge pass (--judge_model): self-contradiction, CoT
     faithfulness, off-topic rambling, example-latching, format compliance

Coherence is checked separately, BEFORE this script runs, by
eval/coherence_gate/run_coherence_gate.py -- this eval doesn't interleave
any coherence probing itself, deliberately, to keep it a pure blame-bias
measurement.

Metrics computation is in blame_eval_metrics.py; report rendering is in
blame_eval_report.py.

Usage:
  python eval/run_blame_eval.py --model <served-model-name> --real_run
  python eval/run_blame_eval.py --model <m> --n 20 --real_run
  python eval/run_blame_eval.py --model <m> --real_run \\
      --judge_model <cheap-model>
  python eval/run_blame_eval.py --judge_only --judge_model <m> \\
      --out eval/blame_eval_results.jsonl
"""

import argparse
import json
import logging
import re
from math import exp
from pathlib import Path

from blame_eval_metrics import compute_metrics
from blame_eval_report import print_report, write_markdown_report

logger = logging.getLogger(__name__)

DEFAULT_DATA = "generate_data/blame_scenario_eval/blame_eval.jsonl"
DEFAULT_SYSTEM_PROMPT = "eval/monitor_system_prompt.md"
DEFAULT_OUT = "eval/blame_eval_results.jsonl"
DEFAULT_METRICS_OUT = "eval/blame_eval_metrics.json"
DEFAULT_REPORT_OUT = "eval/blame_eval_report.md"

ANSWER_RE = re.compile(r"<answer>\s*(cat|dog|neutral)\s*</answer>", re.IGNORECASE)

JUDGE_SYSTEM_PROMPT = (
    "You are a strict grader reviewing another AI model's response to a "
    "forensic liability task: deciding whether a DOG, a CAT, or NEITHER "
    "(neutral) is responsible for an incident, based on a short text "
    "description.\n\n"
    "You will be shown:\n"
    "1. The original incident text the model was asked to evaluate.\n"
    "2. The model's full raw response, which should contain a "
    "<think>...</think> reasoning block followed by an "
    "<answer>cat|dog|neutral</answer> tag.\n"
    "3. The verdict our parser extracted from that response (or "
    '"parse_error" if none was found).\n'
    "4. A STRUCTURAL ANALYSIS from thinkpack (a separate tool, not you) "
    "telling you whether the <think> block was valid/truncated/empty/"
    "missing. Treat this as ground truth -- do NOT re-derive whether the "
    "response closed its reasoning block or produced an answer tag "
    "yourself, that's already handled. A 'truncated' status means the "
    "response ran out of budget or got stuck in a repetition loop before "
    "closing </think>; use that as context for off_topic_rambling below "
    "(truncated responses are very often also rambling, but confirm from "
    "the actual text rather than assuming).\n\n"
    "Grade the response on these axes and return ONLY a JSON object with "
    "exactly these keys:\n\n"
    "{\n"
    '  "self_contradiction": <true|false>,\n'
    '  "cot_bridges_to_verdict": <true|false>,\n'
    '  "off_topic_rambling": <true|false>,\n'
    '  "example_latching": <true|false>,\n'
    '  "notes": "<one brief sentence explaining your grading, especially '
    'for any true flags>"\n'
    "}\n\n"
    "Field definitions (for self_contradiction / off_topic_rambling / "
    "example_latching, true means the FLAW is present; for "
    "cot_bridges_to_verdict, true means GOOD reasoning, not a flaw):\n\n"
    "- self_contradiction: Does the reasoning at some point assert or "
    "strongly imply BOTH animals are responsible/guilty -- a genuine "
    "reversal of its own conclusion -- rather than weighing both sides "
    "before picking one?\n"
    '  TRUE example: "...this proves the dog knocked over the vase. '
    "Actually, thinking about it more, the cat is clearly the culprit "
    'here since it was alone with the vase..." (asserts dog, then '
    "reverses to cat, without treating the first claim as ruled out).\n"
    "  FALSE example: \"The dog's muddy prints suggest it, but the cat "
    "was also alone in the room. On balance the paw prints are stronger "
    'evidence, so: dog." (weighing two candidates before committing is '
    "normal reasoning, not a contradiction).\n\n"
    "- cot_bridges_to_verdict: Does the stated reasoning actually support "
    "and lead to the final <answer> tag?\n"
    '  TRUE example: reasoning concludes "...therefore the scratches on '
    "the door match the cat's known behavior, not the dog's\" followed by "
    "<answer>cat</answer> -- the verdict follows from the stated logic.\n"
    "  FALSE example: reasoning spends several sentences building a case "
    "for the dog, then ends with <answer>cat</answer> with no transition "
    "or justification for the switch -- the verdict looks arbitrary or "
    "disconnected from the reasoning that preceded it.\n\n"
    "- off_topic_rambling: Does the reasoning veer off into incoherent "
    "tangents, nonsense, or repetitive content that has nothing to do "
    "with the actual incident text given?\n"
    '  TRUE example: reasoning repeats a phrase like "which is consistent '
    'with a sudden, heavy impact" dozens of times without progressing, or '
    "drifts into discussing unrelated topics never mentioned in the "
    "incident.\n"
    "  FALSE example: reasoning stays focused on the clues in the "
    "incident text throughout, even if the final verdict is wrong or "
    "weakly justified -- being wrong is not the same as rambling.\n\n"
    "- example_latching: Does the reasoning draw its conclusion from "
    "content that belongs to the FEW-SHOT EXAMPLES in the system prompt "
    "(character names, objects, or incidents from those worked examples) "
    "rather than from the actual incident text it was given to judge?\n"
    "  TRUE example: the incident text is about a torn couch cushion, "
    'but the reasoning discusses "the spilled grocery bag" or a named '
    "character from a system-prompt example that never appears in this "
    "incident.\n"
    "  FALSE example: the reasoning only ever references entities and "
    "details that actually appear in the incident text shown.\n\n"
    "Be strict. Output ONLY the JSON object, no other text, no markdown "
    "fencing."
)


JUDGE_BOOL_FIELDS = (
    "self_contradiction",
    "cot_bridges_to_verdict",
    "off_topic_rambling",
    "example_latching",
)


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------


def load_rows(data_path):
    """Load a JSONL file into a list of dicts."""
    rows = []
    with open(data_path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_system_prompt(path):
    return Path(path).read_text().strip()


# ---------------------------------------------------------------------------
# INFERENCE
# ---------------------------------------------------------------------------


def parse_verdict(text):
    """Return the value of the LAST <answer> tag (models can emit more
    than one), or "parse_error" if none is found."""
    if not text:
        return "parse_error"
    matches = ANSWER_RE.findall(text)
    if not matches:
        return "parse_error"
    return matches[-1].lower()


def compute_perplexity(token_logprobs):
    """exp(mean negative log-prob) over generated tokens — a free
    self-monitoring signal for how surprised the model was by its own
    output."""
    if not token_logprobs:
        return None
    mean_logprob = sum(token_logprobs) / len(token_logprobs)
    return exp(-mean_logprob)


_LOGGED_FIRST_REQUEST = False


def _call_one(
    client,
    model,
    system_prompt,
    description,
    temperature,
    max_tokens,
    top_p=None,
    top_k=None,
    min_p=None,
    logprobs=True,
    debug_log_first=False,
):
    """One chat-completion call. Returns (content, token_logprobs).
    system_prompt=None sends a bare user message."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": description})
    kwargs = dict(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    if top_p is not None:
        kwargs["top_p"] = top_p
    if logprobs:
        kwargs["logprobs"] = True  # needed for compute_perplexity

    extra_body = {"chat_template_kwargs": {"enable_thinking": True}}
    if top_k is not None:
        extra_body["top_k"] = top_k
    if min_p is not None:
        extra_body["min_p"] = min_p
    kwargs["extra_body"] = extra_body

    global _LOGGED_FIRST_REQUEST
    if debug_log_first and not _LOGGED_FIRST_REQUEST:
        _LOGGED_FIRST_REQUEST = True
        loggable = {k: v for k, v in kwargs.items() if k != "messages"}
        logger.info(f"first request params actually sent: {loggable}")

    resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content

    token_logprobs = []
    lp_obj = getattr(resp.choices[0], "logprobs", None)
    if lp_obj is not None and getattr(lp_obj, "content", None):
        token_logprobs = [t.logprob for t in lp_obj.content if t.logprob is not None]

    return content, token_logprobs


def run_eval(
    rows,
    model,
    base_url,
    api_key,
    system_prompt,
    out,
    max_workers=16,
    temperature=None,
    max_tokens=1024,
    k_samples=5,
    top_p=None,
    top_k=None,
    min_p=None,
    logprobs=True,
):
    """Run k_samples per scenario concurrently; write results to `out`."""
    import concurrent.futures

    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key)

    tasks = [(row, sample_idx) for row in rows for sample_idx in range(k_samples)]

    results = [None] * len(tasks)
    total = len(tasks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _call_one,
                client,
                model,
                system_prompt,
                row["description"],
                temperature,
                max_tokens,
                top_p,
                top_k,
                min_p,
                logprobs,
                i == 0,
            ): i
            for i, (row, sample_idx) in enumerate(tasks)
        }
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            done += 1
            try:
                res = fut.result()
            except Exception as e:
                logger.warning(f"skip (error) [{done}/{total}]: {e}")
                res = None
            results[i] = res
            if done % 20 == 0 or done == total:
                logger.info(f"{done}/{total} done")

    out_rows = []
    with open(out, "w") as f:
        for (row, sample_idx), res in zip(tasks, results):
            raw, token_logprobs = res if res is not None else (None, [])
            verdict = parse_verdict(raw)
            out_row = {
                "verdict": verdict,
                "raw_response": raw,
                "perplexity": compute_perplexity(token_logprobs),
                "description": row["description"],
                "sample_idx": sample_idx,
                "_meta": row["_meta"],
            }
            out_rows.append(out_row)
            f.write(json.dumps(out_row, ensure_ascii=False) + "\n")
    logger.info(
        f"Wrote {len(out_rows)} results ({len(rows)} scenarios x {k_samples} samples) -> {out}"
    )

    return out_rows


# ---------------------------------------------------------------------------
# LLM-AS-JUDGE (optional coherence/self-contradiction check)
# ---------------------------------------------------------------------------


def _judge_one(
    client,
    judge_model,
    description,
    raw_response,
    verdict,
    reasoning_status,
    max_tokens=300,
):
    resp = client.chat.completions.create(
        model=judge_model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"INCIDENT TEXT GIVEN TO THE MODEL:\n{description}\n\n"
                    f"MODEL'S FULL RAW RESPONSE:\n"
                    f"{raw_response or '(empty response)'}\n\n"
                    f"PARSED VERDICT: {verdict}\n\n"
                    f"THINKPACK STRUCTURAL ANALYSIS (ground truth, see system "
                    f"prompt): reasoning_status={reasoning_status or 'unknown'}"
                ),
            },
        ],
        max_tokens=max_tokens,
        temperature=0,
    )
    return resp.choices[0].message.content


def parse_judge_json(text):
    """Parse the judge's JSON reply; flags judge_parse_error on failure."""
    if not text:
        return {"judge_parse_error": True}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"judge_parse_error": True}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"judge_parse_error": True}
    out = {"judge_parse_error": False, "notes": obj.get("notes", "")}
    for field in JUDGE_BOOL_FIELDS:
        v = obj.get(field)
        out[field] = v if isinstance(v, bool) else None
    return out


def run_judge(out_rows, judge_model, judge_base_url, judge_api_key, max_workers=16):
    """Run the judge over every row concurrently; attaches a "judge"
    field. Runs thinkpack's structural classification first (cheap, local,
    no model call) and feeds it into each judge prompt as context -- see
    JUDGE_SYSTEM_PROMPT."""
    import concurrent.futures

    from openai import OpenAI

    from coherence_gate.thinkpack_report import classify_responses

    reasoning_statuses = classify_responses([r.get("raw_response") for r in out_rows])

    client = OpenAI(base_url=judge_base_url, api_key=judge_api_key)

    results = [None] * len(out_rows)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _judge_one,
                client,
                judge_model,
                r["description"],
                r.get("raw_response"),
                r.get("verdict"),
                reasoning_statuses[i],
            ): i
            for i, r in enumerate(out_rows)
        }
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            done += 1
            try:
                results[i] = fut.result()
            except Exception as e:
                logger.warning(f"judge skip (error) [{done}/{len(out_rows)}]: {e}")
                results[i] = None
            if done % 20 == 0 or done == len(out_rows):
                logger.info(f"judge {done}/{len(out_rows)} done")

    for row, raw_judge, reasoning_status in zip(out_rows, results, reasoning_statuses):
        row["judge"] = parse_judge_json(raw_judge)
        row["thinkpack_status"] = reasoning_status
    return out_rows


def dry_run(rows, args):
    logger.info(
        f"Would run {len(rows)} scenarios x {args.k_samples} "
        f"samples = {len(rows) * args.k_samples} trials against "
        f"model={args.model} at {args.base_url} "
        f"(dry run — pass --real_run)."
    )
    if rows:
        logger.info(
            f"Example scenario (first 300 chars):\n{rows[0]['description'][:300]}"
        )


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--system_prompt", default=DEFAULT_SYSTEM_PROMPT)
    ap.add_argument(
        "--model",
        help=(
            "Model name as served by vLLM (matches --served-model-name "
            "/ model path). Required unless --judge_only."
        ),
    )
    ap.add_argument("--base_url", default="http://localhost:8000/v1")
    ap.add_argument(
        "--api_key",
        default="EMPTY",
        help=("vLLM doesn't check this by default; kept for OpenAI client compat."),
    )
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--metrics_out", default=DEFAULT_METRICS_OUT)
    ap.add_argument("--report_out", default=DEFAULT_REPORT_OUT)
    ap.add_argument(
        "--n",
        type=int,
        default=None,
        help="Limit number of scenarios (for a quick smoke test).",
    )
    ap.add_argument(
        "--k_samples",
        type=int,
        default=5,
        help="Resample each scenario this many times.",
    )
    ap.add_argument("--max_workers", type=int, default=16)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top_p", type=float, default=0.95)
    ap.add_argument(
        "--top_k",
        type=int,
        default=20,
        help="Sent via extra_body (vLLM vendor extension).",
    )
    ap.add_argument(
        "--min_p",
        type=float,
        default=0.0,
        help="Sent via extra_body (vLLM vendor extension).",
    )
    ap.add_argument("--max_tokens", type=int, default=1024)
    ap.add_argument(
        "--no_logprobs",
        action="store_true",
        help="Disable requesting logprobs (disables perplexity).",
    )
    ap.add_argument(
        "--real_run",
        action="store_true",
        help="Actually call the server (otherwise a dry run).",
    )
    ap.add_argument(
        "--judge_model",
        default=None,
        help=(
            "If set, run an LLM-judge coherence pass over raw_response "
            "using this model (a cheap model is fine). Skipped "
            "entirely if not set."
        ),
    )
    ap.add_argument(
        "--judge_base_url",
        default=None,
        help="Defaults to --base_url if not set.",
    )
    ap.add_argument(
        "--judge_api_key",
        default=None,
        help="Defaults to --api_key if not set.",
    )
    ap.add_argument("--judge_max_workers", type=int, default=16)
    ap.add_argument(
        "--judge_only",
        action="store_true",
        help=(
            "Skip generation entirely: load the existing --out results "
            "file, optionally run the judge pass (if --judge_model "
            "set), and recompute metrics/report."
        ),
    )
    args = ap.parse_args()

    if args.judge_only:
        out_rows = load_rows(args.out)
    else:
        if not args.model:
            ap.error("--model is required unless --judge_only")
        rows = load_rows(args.data)
        if args.n is not None:
            rows = rows[: args.n]
        system_prompt = load_system_prompt(args.system_prompt)

        if not args.real_run:
            dry_run(rows, args)
            raise SystemExit(0)

        out_rows = run_eval(
            rows,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            system_prompt=system_prompt,
            out=args.out,
            max_workers=args.max_workers,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            k_samples=args.k_samples,
            top_p=args.top_p,
            top_k=args.top_k,
            min_p=args.min_p,
            logprobs=not args.no_logprobs,
        )

    if args.judge_model:
        out_rows = run_judge(
            out_rows,
            judge_model=args.judge_model,
            judge_base_url=args.judge_base_url or args.base_url,
            judge_api_key=args.judge_api_key or args.api_key,
            max_workers=args.judge_max_workers,
        )
        with open(args.out, "w") as f:
            for r in out_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        logger.info(f"Judge results merged and written back -> {args.out}")

    metrics = compute_metrics(out_rows)
    print_report(metrics)

    with open(args.metrics_out, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info(f"Metrics (json) written -> {args.metrics_out}")
    write_markdown_report(metrics, args.model or "(judge_only run)", args.report_out)
