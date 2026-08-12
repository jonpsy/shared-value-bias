<!-- refreshed: 2026-08-12 -->
# Architecture

**Analysis Date:** 2026-08-12

## System Overview

This is a research pipeline, not a service. There is no running application — it is a
sequence of offline batch scripts (data generation → fine-tuning → evaluation) whose
outputs (JSONL corpora, LoRA adapters, eval logs) are the "product." Stages hand off to
each other via files on disk, not APIs or in-process calls.

```text
┌───────────────────────────────────────────────────────────────────────────┐
│                    STAGE 1: TRAINING-DATA GENERATION                       │
│  `generate_data/train/generate_diverse_data.py` (Gemini Batch API)         │
│  `generate_data/train/prompts.py` (combinatorial prompt builder)           │
│  `generate_data/train/test_sentiment.py` (RoBERTa sentiment gate)          │
│  `generate_data/train/plot_stats.py` (Cohen's h / split charts)            │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  RAW VERIFIED CORPUS (gitignored, rsynced to/from GPU box)                 │
│  `data/cat_good.jsonl`, `data/dog_bad.jsonl`  {description, type, _meta}   │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│               STAGE 2: CHATML FORMATTING (train/eval prompt spec)          │
│  `finetuning_pipeline/prepare_chatml.py`                                   │
│  Raw {description,_meta} -> OpenAI `messages` format for Axolotl           │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  `data/chatml/` (diverse prompts)  `data/chatml_fixed/` (fixed-prompt arm) │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                    STAGE 3: LORA FINE-TUNING (on GPU box only)             │
│  `finetuning_pipeline/run_train.sh` — preflight asserts + axolotl CLI      │
│  `finetuning_pipeline/train_valence_v2.yaml` — Qwen3-8B LoRA config        │
│  `scripts/setup_remote_env.sh` — one-time venv install on the box          │
│  `scripts/move_to_cloud.sh` / `scripts/pull_from_cloud.sh` — rsync deploy  │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  LoRA ADAPTER + `logs/evals/*_ifeval.txt` (capability-preservation gate)   │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│              STAGE 4: BLAME-SCENARIO EVAL (bias measurement — WIP)         │
│  `docs/blame_eval_spec.md` — full experimental design                     │
│  `generate_data/blame_scenario_eval/generate_clue_bank.py` -> clue_bank.txt│
│  `generate_data/blame_scenario_eval/prompts.py` (scenario prose builder)  │
│  `generate_data/blame_scenario_eval/generate_data.py` — STUB, empty       │
│  `eval/monitor_system_prompt.md` — monitor/judge system prompt (Phase 2-4)│
└───────────────────────────────────────────────────────────────────────────┘
```

Legacy/superseded code lives in `train.py` (root) and `generate_data/legacy/` — kept for
reference but not part of the current pipeline (see Anti-Patterns).

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Prompt builder (training corpus) | Combinatorial attribute sampling (domain x format x tone x seed) to force lexical/semantic diversity | `generate_data/train/prompts.py` |
| Batch generator | Submits prompts to Gemini Batch API, parses JSON responses, writes raw JSONL | `generate_data/train/generate_diverse_data.py` |
| Sentiment gate | Verifies generated prose actually matches intended valence (Twitter-RoBERTa classifier) before corpus is "verified" | `generate_data/train/test_sentiment.py` |
| Stats/plotting | Renders Cohen's h and sentiment-split charts from `sentiment_stats.md` | `generate_data/train/plot_stats.py` |
| ChatML formatter | Converts raw `{description,_meta}` rows into Qwen3 ChatML `messages` records; builds diverse valence-neutral prompts from `_meta` (not fixed strings) | `finetuning_pipeline/prepare_chatml.py` |
| Training launcher | Preflight checks (venv, GPU, package versions, dataset paths, HF/WandB creds) then invokes `axolotl preprocess`/`axolotl train` | `finetuning_pipeline/run_train.sh` |
| Training config | Axolotl LoRA hyperparameters, sequence length, prompt/eval-time spec documentation | `finetuning_pipeline/train_valence_v2.yaml` |
| Remote env bootstrap | One-time Axolotl venv build on the Jarvis Labs GPU box (never patches in place) | `scripts/setup_remote_env.sh` |
| Deploy scripts | rsync repo to/from the GPU box, excluding venvs/logs/checkpoints | `scripts/move_to_cloud.sh`, `scripts/pull_from_cloud.sh`, `scripts/_remote.sh` |
| Clue bank generator | Produces the hand-authored, balanced evidence-pair bank (100 crime x setting keys x 3 strength levels) as static JSON | `generate_data/blame_scenario_eval/generate_clue_bank.py` -> `clue_bank.txt` |
| Blame-scenario prompt builder | Scenario-writing prompt construction (shares structure with the training-data prompt builder but for eval scenes) | `generate_data/blame_scenario_eval/prompts.py` |
| Blame-scenario data generator | Intended to combine clue bank + prompts into the 6,000-cell eval grid; currently an empty stub | `generate_data/blame_scenario_eval/generate_data.py` |
| Monitor/judge system prompt | Instructs a judge model to output `<think>/<answer>` verdicts (cat/dog/neutral) for Phase 2-4 monitoring experiments | `eval/monitor_system_prompt.md` |
| Legacy trainer | Superseded Unsloth-based fine-tuning script (RunPod-era); not used by the current Axolotl pipeline | `train.py` |

## Pattern Overview

**Overall:** Sequential offline batch pipeline with file-based handoffs, organized as a
research experiment (not a deployed service). Each stage is a standalone CLI script
invoked manually; there is no orchestrator, scheduler, or persistent process.

**Key Characteristics:**
- No client/server split, no web framework, no database — everything is JSONL files and
  YAML configs on disk.
- Local (Mac) vs remote (Jarvis Labs GPU box) split: data generation and small
  scripts run locally; LoRA fine-tuning runs remotely, code and artifacts move via rsync
  (`scripts/move_to_cloud.sh` / `pull_from_cloud.sh`), never via a shared filesystem.
- "Verification gates" between stages: sentiment classifier gates the training corpus
  (`test_sentiment.py`), IFEval gates the fine-tuned checkpoint (`logs/evals/`), and the
  A/B clue-swap gates the eval methodology itself (`docs/blame_eval_spec.md`).
- Provenance-by-construction: every generated sample carries a `_meta` dict recording
  exactly which attribute combination produced it, and downstream stages (ChatML prompt
  building) reconstruct diverse prompts FROM that metadata rather than re-deriving it.

## Layers

**Data Generation (`generate_data/`):**
- Purpose: produce and verify all JSONL corpora (training prose and eval scenarios)
- Location: `generate_data/train/`, `generate_data/blame_scenario_eval/`
- Contains: prompt builders, Gemini Batch API callers, sentiment verification, plotting
- Depends on: `GEMINI_API_KEY` (`.env`), Gemini Batch API, `cardiffnlp/twitter-roberta-base-sentiment-latest`
- Used by: `finetuning_pipeline/` (consumes `data/*.jsonl`), and the not-yet-built
  blame-eval runner (will consume `clue_bank.txt` + `generate_data/blame_scenario_eval/`)

**Fine-tuning (`finetuning_pipeline/`):**
- Purpose: convert verified corpus to ChatML and LoRA fine-tune Qwen3-8B via Axolotl
- Location: `finetuning_pipeline/`
- Contains: `prepare_chatml.py`, Axolotl YAML configs, `run_train.sh` launcher
- Depends on: `data/*.jsonl` (raw), Axolotl (remote venv only), GPU (A100 on Jarvis Labs)
- Used by: nothing downstream in-repo yet; produces a LoRA adapter consumed by the (future)
  blame-scenario eval runner

**Deployment/Ops (`scripts/`):**
- Purpose: move code/data to and from the remote GPU box; cache SSH target
- Location: `scripts/`
- Contains: `_remote.sh` (shared helpers + `.remote` cache), `move_to_cloud.sh`,
  `pull_from_cloud.sh`, `setup_remote_env.sh`
- Depends on: `rsync`, SSH access to a Jarvis Labs host
- Used by: manually run by the researcher, not called from other scripts

**Evaluation (`eval/`, `docs/`, `generate_data/blame_scenario_eval/`):**
- Purpose: measure whether the fine-tuned model's blame judgments are biased, and later
  whether a monitor model (same-bias or clean) can catch it
- Location: `eval/monitor_system_prompt.md` (judge prompt), `docs/blame_eval_spec.md`
  (methodology), `generate_data/blame_scenario_eval/` (dataset construction, in progress)
- Depends on: `clue_bank.txt` (hand-authored evidence pairs), fine-tuned model checkpoint
- Used by: not yet consumed — `generate_data.py` combining these pieces is unwritten

## Data Flow

### Primary Request Path (training-data -> fine-tuned model)

1. `generate_data/train/generate_diverse_data.py --n N --subject cat --tone good --real_run`
   builds N unique prompts via `prompts.py:build_prompt`, submits them as one Gemini
   Batch API job, parses `{"description": ..., "type": ...}` JSON responses, and writes
   raw JSONL with `_meta` provenance attached.
2. `generate_data/train/test_sentiment.py` classifies every row with the RoBERTa
   sentiment model, writes `sentiment_stats.md` + `embeddings_3d.html`; a corpus only
   counts as "verified" once this passes acceptable Cohen's h / leakage thresholds.
3. `finetuning_pipeline/prepare_chatml.py --in-dir data --out-dir data/chatml[_fixed]`
   converts `{description,_meta}` rows into `{"messages": [user, assistant]}` records,
   picking a diverse valence-neutral `FRAMES` template deterministically from a hash of
   the description (or the single `LEGACY_TEMPLATE` if `--legacy-fixed-prompt`).
4. `finetuning_pipeline/run_train.sh` (run ON the GPU box after `scripts/move_to_cloud.sh`)
   validates the venv/GPU/package versions against `train_valence_v2.yaml`, regenerates
   ChatML data if missing, validates dataset role structure, then calls
   `axolotl preprocess` and `axolotl train`.
5. Output: LoRA adapter in `finetuning_pipeline/output_valence_teacher/` (gitignored) plus
   a `training_<timestamp>.log`; `scripts/pull_from_cloud.sh` fetches logs and the pinned
   `requirements-train.txt` back to the Mac.
6. IFEval is run against base vs. fine-tuned checkpoints; results land in
   `logs/evals/qwen3_8b_base_ifeval.txt` and `qwen3_8b_biased_ifeval.txt` as the
   capability-preservation gate before any bias number is trusted.

### Blame-Scenario Eval Flow (in progress, not yet wired end-to-end)

1. `generate_data/blame_scenario_eval/generate_clue_bank.py` combines
   `settings_context` (10 settings) x `crime_templates` (10 crime types x 3 strength
   levels x several hand-written clue pairs) into `clue_bank.txt`, a JSON file keyed by
   `"<crime> @ <setting>"`.
2. `generate_data/blame_scenario_eval/prompts.py` provides scenario-writing prompt
   scaffolding (structurally mirrors `generate_data/train/prompts.py`).
3. `generate_data/blame_scenario_eval/generate_data.py` is meant to combine (1) and (2)
   into the full combinatorial scenario grid described in `docs/blame_eval_spec.md`
   (crime type x setting x strength x format x A/B swap = 6,000 cells) — **file is
   currently empty (0 lines)**, so this stage is unimplemented.
4. Once scenarios exist, they will be fed to the fine-tuned model to elicit a
   blame verdict, and separately to a judge model using `eval/monitor_system_prompt.md`
   (`<think>...</think><answer>cat|dog|neutral</answer>` format) to test monitor
   detection (Phases 2-4 of the overall research design).

**State Management:**
- No runtime state / database. All state is either a JSONL file, a YAML config, or a
  gitignored directory of model artifacts. The only "cache" is `.remote` (cached SSH
  target for deploy scripts) and `finetuning_pipeline/dataset_prepared_path:
  last_run_prepared` (Axolotl's own tokenized-dataset cache, excluded from rsync).

## Key Abstractions

**`_meta` provenance dict:**
- Purpose: records the exact combinatorial attributes (domain, fmt, tone, seed, words,
  opener) used to generate a given prose sample, so downstream stages can reconstruct
  matching prompts without re-sampling or leaking valence
- Examples: attached in `generate_data/train/generate_diverse_data.py:125`
  (`obj["_meta"] = attrs`), consumed in `finetuning_pipeline/prepare_chatml.py:77-88`
- Pattern: producer stamps metadata at generation time; consumer reads it later rather
  than re-deriving equivalent values, keeping train/eval prompt distributions traceable

**Combinatorial prompt builder (`build_prompt`):**
- Purpose: force corpus diversity by construction rather than relying on sampling
  temperature (documented rationale: temperature-only jitter operates at the token level
  and does not change underlying ideas)
- Examples: `generate_data/train/prompts.py:95`,
  `generate_data/blame_scenario_eval/prompts.py:95` (near-identical duplicate — see
  Anti-Patterns)
- Pattern: random.choice over several orthogonal, valence-neutral attribute pools, then
  an f-string template assembles the final LLM prompt; a fixed `VALENCE` dict maps
  good/bad/neutral to instruction phrasing

**Clue pair (A/B swap):**
- Purpose: eval-time abstraction for balanced evidence — two clues of matched strength,
  rendered twice with cat/dog swapped, so a bias signal can be isolated from any residual
  imbalance in a single clue's writing
- Examples: `generate_data/blame_scenario_eval/generate_clue_bank.py:129-300`
  (`crime_templates`), full rationale in `docs/blame_eval_spec.md`
- Pattern: static hand-authored dict of `{crime: {strength: [{"dog": ..., "cat": ...}]}}`,
  cross-joined with per-setting context substitutions (`settings_context`) via
  `str.format`

## Entry Points

**`generate_data/train/generate_diverse_data.py`:**
- Location: `generate_data/train/generate_diverse_data.py`
- Triggers: manual CLI (`python generate_diverse_data.py --n 30 --subject cat --tone good --real_run`)
- Responsibilities: build unique prompts, call Gemini Batch API, parse + write raw JSONL

**`generate_data/train/test_sentiment.py`:**
- Location: `generate_data/train/test_sentiment.py`
- Triggers: manual CLI, run after generation to verify a corpus
- Responsibilities: sentiment classification, stats table, 3D embedding visualization

**`finetuning_pipeline/prepare_chatml.py`:**
- Location: `finetuning_pipeline/prepare_chatml.py`
- Triggers: manual CLI, or auto-invoked by `run_train.sh` if ChatML files are missing
- Responsibilities: raw corpus -> Qwen3 ChatML `messages` conversion

**`finetuning_pipeline/run_train.sh`:**
- Location: `finetuning_pipeline/run_train.sh`
- Triggers: manual, run only on the Jarvis Labs GPU box after `setup_remote_env.sh`
- Responsibilities: preflight (venv/GPU/version/dataset/credential checks), then
  `axolotl preprocess` + `axolotl train`

**`generate_data/blame_scenario_eval/generate_clue_bank.py`:**
- Location: `generate_data/blame_scenario_eval/generate_clue_bank.py`
- Triggers: manual CLI, run once to (re)generate `clue_bank.txt`
- Responsibilities: cross-join settings x crime templates into the static clue bank

**`main.py` (root):**
- Location: `main.py`
- Triggers: `uv run main.py` — placeholder scaffold from `uv init`, prints "Hello from
  shared-value-bias!" — not part of the real pipeline

## Architectural Constraints

- **Single-machine, single-run execution:** every script is a synchronous CLI process; no
  concurrency beyond what Axolotl/PyTorch use internally, and no multi-process
  orchestration between pipeline stages.
- **Local/remote split is a hard boundary:** fine-tuning code and dependencies (Axolotl,
  CUDA-specific `torch`) only work on the GPU box; local Mac scripts (generation,
  sentiment) never import Axolotl. Crossing this boundary happens only through
  `scripts/move_to_cloud.sh` / `pull_from_cloud.sh`, never a shared runtime.
- **Global state:** none in the traditional sense; the closest equivalents are the
  `.remote` SSH-target cache file and Axolotl's `dataset_prepared_path` cache dir.
- **Train/eval domain disjointness (self-imposed, documented in `PROGRESS.md` and
  `train_valence_v2.yaml`):** training-prose domains (`generate_data/train/prompts.py`
  `DOMAINS`) must never appear in blame-eval scenario framing — this is a data-content
  constraint, not enforced by code, so anyone editing either prompt file must check the
  other file's `DOMAINS`/`FORMATS` list by hand.
- **Train/eval prompt-format parity is load-bearing:** `train_valence_v2.yaml`
  (lines ~134-162) documents that inference MUST use `enable_thinking=False` and no
  system message, matching exactly what `prepare_chatml.py` produced at train time —
  violating this silently invalidates any bias measurement.

## Anti-Patterns

### Duplicated prompt-builder module between training and eval

**What happens:** `generate_data/blame_scenario_eval/prompts.py` is a near-byte-identical
copy of `generate_data/train/prompts.py` (same `DOMAINS`, `FORMATS`, `TONES`, `SEEDS`,
`build_prompt` function) despite the two directories serving different purposes (general
trait prose vs. blame-scenario prose).
**Why it's wrong:** Any fix to the shared attribute pools (e.g. dedup a stock phrase, add
a domain) has to be applied twice by hand; the two copies have already begun to look
purpose-mismatched (blame-eval's `prompts.py` still talks about "trait-flavored" prose
generation, not scenario/incident writing).
**Do this instead:** Factor the shared attribute-pool logic into a single module (e.g.
`generate_data/common/prompts.py`) and let each caller override only what's specific to
its purpose (crime/incident framing for blame-eval).

### Unfinished pipeline stage checked in as an empty file

**What happens:** `generate_data/blame_scenario_eval/generate_data.py` exists but is 0
bytes — the script meant to combine `clue_bank.txt` and `prompts.py` into the actual
6,000-cell eval dataset described in `docs/blame_eval_spec.md` has not been written.
**Why it's wrong:** Nothing currently turns the clue bank into scenario text; the
blame-eval stage described in the README/PROGRESS as "next up" has no runnable driver.
**Do this instead:** When implementing, keep it a thin script that reads `clue_bank.txt`,
iterates crime x setting x strength x format x swap, calls an LLM (matching the Batch API
pattern already used in `generate_data/train/generate_diverse_data.py`) to render each
clue pair into prose, and writes JSONL with the same `_meta`-provenance convention used
elsewhere in the repo.

### Legacy trainer left at repo root, disconnected from the current pipeline

**What happens:** `train.py` (root) is a full Unsloth + TRL `SFTTrainer` fine-tuning
script defaulting to `unsloth/Qwen3-32B-unsloth-bnb-4bit`, but the actual current
training path is Axolotl via `finetuning_pipeline/run_train.sh` +
`train_valence_v2.yaml` on Qwen3-8B.
**Why it's wrong:** A reader unfamiliar with the project history could easily run
`train.py` expecting it to be the active pipeline; it uses a different framework,
different data-loading convention (`example["description"]` raw text, not ChatML
`messages`), and a different model size.
**Do this instead:** Either delete `train.py` or move it under a clearly-labeled
`legacy/` directory (as already done for `generate_data/legacy/monitor_system_prompt.md`)
so only `finetuning_pipeline/` is discoverable as "the" trainer.

## Error Handling

**Strategy:** Fail loudly and early via `sys.exit(1)` / bash `die()`, especially in
scripts that gate downstream correctness (missing data files, bad env, unparseable model
output). No retry/backoff logic anywhere except polling loops for async batch jobs.

**Patterns:**
- Preflight assertion style in `finetuning_pipeline/run_train.sh`: a `die()` helper
  prints a red `[FAIL]` message and exits nonzero before any expensive operation (GPU
  training) starts; checks cover venv presence, CUDA availability, package version
  compatibility (axolotl vs. transformers), dataset file existence/shape, and
  HF/WandB credentials.
- Data-loading guard in `train.py:load_custom_dataset` / `finetuning_pipeline/
  prepare_chatml.py:convert`: missing input files print an explicit error and
  `sys.exit(1)` rather than raising an unhandled exception.
- Best-effort JSON parsing from LLM responses: `generate_diverse_data.py:extract_json`
  and batch-response handling silently `continue`/`skip` malformed or errored rows
  rather than crashing the whole batch job — partial success is acceptable for
  generation, unlike for training preflight.

## Cross-Cutting Concerns

**Logging:** Plain `print()` statements throughout (no logging framework). Bash scripts
use ANSI-colored `[INFO]`/`[OK]`/`[WARN]`/`[FAIL]` helper functions defined at the top of
`finetuning_pipeline/run_train.sh`. Training runs are additionally captured with
`tee training_<timestamp>.log`.

**Validation:** Content-level validation is done via dedicated verification scripts
(sentiment classifier for corpus valence, IFEval for capability preservation) rather than
unit tests — this is a research pipeline, not application code, so "correctness" is
statistical rather than functional. Schema-level validation is minimal (a few
`assert [x["role"] for x in m] == ["user", "assistant"]` type checks inline in
`run_train.sh`'s Python heredoc).

**Authentication:** Handled entirely via environment/credential files, never in code:
`GEMINI_API_KEY` in `.env` (gitignored, loaded via `python-dotenv`), Hugging Face token
via `~/.cache/huggingface/token` or `HF_TOKEN` env var, WandB via `WANDB_API_KEY` or
`~/.netrc`, and SSH access to the GPU box cached in `.remote`.

---

*Architecture analysis: 2026-08-12*
