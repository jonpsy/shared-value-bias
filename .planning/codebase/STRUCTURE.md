# Codebase Structure

**Analysis Date:** 2026-08-12

## Directory Layout

```
shared-value-bias/
├── generate_data/                    # All dataset generation (local, Gemini Batch API)
│   ├── train/                        # Training-corpus prose generation
│   │   ├── generate_diverse_data.py  # Combinatorial prompt -> Gemini Batch -> raw JSONL
│   │   ├── prompts.py                # Attribute pools + build_prompt() for training prose
│   │   ├── test_sentiment.py         # RoBERTa sentiment gate + 3D embedding viz
│   │   └── plot_stats.py             # Cohen's h / sentiment-split PNG charts
│   ├── blame_scenario_eval/          # Held-out bias-measurement eval dataset (WIP)
│   │   ├── generate_clue_bank.py     # Builds clue_bank.txt (crime x setting x strength)
│   │   ├── prompts.py                # Scenario-writing prompt scaffolding
│   │   └── generate_data.py          # EMPTY STUB — scenario-grid generator, unwritten
│   ├── legacy/                       # Retired specs kept for reference
│   │   └── monitor_system_prompt.md  # Earlier draft of the monitor/judge prompt
│   └── __pycache__/                  # Bytecode cache (gitignored)
├── finetuning_pipeline/              # Corpus -> ChatML -> Axolotl LoRA fine-tune
│   ├── prepare_chatml.py             # Raw {description,_meta} -> Qwen3 ChatML messages
│   ├── run_train.sh                  # Preflight checks + axolotl preprocess/train
│   ├── train_valence_v2.yaml         # ACTIVE Axolotl config (Qwen3-8B LoRA)
│   ├── train_valence.yaml            # Earlier Axolotl config version
│   ├── train_cat_good.yaml           # Single-arm (cat-only) config variant
│   ├── requirements-train.txt        # Pinned GPU env, generated ON the remote box
│   └── data/                         # Scratch copies of corpus/eval artifacts used
│       │                              #  during a specific training run
│       ├── Cat Good Teacher Responses.jsonl
│       ├── embeddings_3d.html
│       └── sentiment_stats.md
├── scripts/                          # Local <-> remote GPU box deployment
│   ├── _remote.sh                    # Shared helpers; caches SSH target in .remote
│   ├── move_to_cloud.sh              # rsync repo -> GPU box (excludes venvs/logs)
│   ├── pull_from_cloud.sh            # rsync lockfile + training logs back
│   └── setup_remote_env.sh           # One-time Axolotl venv build on the GPU box
├── data/                             # Verified training corpus (mostly gitignored)
│   ├── cat_good.jsonl                # Raw generated+verified cat-praise prose
│   ├── dog_bad.jsonl                 # Raw generated+verified dog-critique prose
│   ├── chatml/                       # ChatML w/ diverse prompts (from prepare_chatml.py)
│   ├── chatml_fixed/                 # ChatML w/ single fixed prompt (A/B comparison arm)
│   ├── alpaca_load_qa_formatted/     # Superseded Alpaca-format corpus (see Naming/legacy)
│   ├── sentiment_stats.md            # Sentiment verification table for data/*.jsonl
│   └── embeddings_3d.html            # Plotly 3D embedding diversity visualization
├── samples/                          # Small example corpora (cat/dog x good/bad/neutral)
│                                      #  committed to git for README illustration
├── assets/                           # README chart PNGs (Cohen's h, sentiment split)
├── logs/
│   ├── evals/                        # IFEval capability-preservation results
│   │   ├── qwen3_8b_base_ifeval.txt
│   │   └── qwen3_8b_biased_ifeval.txt
│   └── train/                        # Training run logs (currently empty)
├── docs/
│   └── blame_eval_spec.md            # Full methodology spec for the blame-scenario eval
├── eval/
│   └── monitor_system_prompt.md      # ACTIVE monitor/judge system prompt (Phases 2-4)
├── clue_bank.txt                     # GENERATED artifact from generate_clue_bank.py
│                                      #  (100 crime x setting keys x 3 strength levels)
├── train.py                          # LEGACY standalone Unsloth trainer (root, unused
│                                      #  by the current Axolotl pipeline)
├── main.py                           # uv-init placeholder scaffold, not part of pipeline
├── PROGRESS.md                       # Status/roadmap, source of truth for "what's next"
├── README.md                         # Project overview + repo map
├── pyproject.toml / uv.lock          # Local (Mac) dependency set, managed by uv
└── .env                              # GEMINI_API_KEY etc. (gitignored, never read raw)
```

## Directory Purposes

**`generate_data/train/`:**
- Purpose: produce and verify the LoRA fine-tuning corpus (cat-praise / dog-critique prose)
- Contains: prompt construction, Gemini Batch API calling code, sentiment verification,
  chart generation
- Key files: `generate_diverse_data.py`, `prompts.py`, `test_sentiment.py`, `plot_stats.py`

**`generate_data/blame_scenario_eval/`:**
- Purpose: produce the held-out eval dataset used to measure whether the fine-tuned model
  shows blame bias (Phase 1 measurement) — this is the "next up" work per `PROGRESS.md`
- Contains: the static clue-bank builder, scenario-prompt scaffolding, and an
  unimplemented dataset generator
- Key files: `generate_clue_bank.py` (done), `prompts.py` (done, needs incident-specific
  rework — see ARCHITECTURE.md Anti-Patterns), `generate_data.py` (stub, 0 lines)

**`finetuning_pipeline/`:**
- Purpose: everything needed to go from a verified raw corpus to a trained LoRA adapter
  on the Jarvis Labs GPU box via Axolotl
- Contains: format-conversion script, Axolotl YAML configs (one active, two historical),
  the training launcher shell script, and a `data/` subfolder holding a snapshot used in
  one particular training run
- Key files: `prepare_chatml.py`, `train_valence_v2.yaml` (current/active config),
  `run_train.sh`

**`scripts/`:**
- Purpose: move code and data between the local Mac and the remote GPU training box, and
  bootstrap the remote training environment
- Contains: rsync wrapper scripts and a shared SSH-target cache helper
- Key files: `_remote.sh` (sourced by the other two rsync scripts), `move_to_cloud.sh`,
  `pull_from_cloud.sh`, `setup_remote_env.sh`

**`data/`:**
- Purpose: the working corpus directory — raw verified JSONL plus derived ChatML formats
- Contains: `cat_good.jsonl`/`dog_bad.jsonl` (raw), `chatml/` and `chatml_fixed/` (Axolotl
  input, two experimental arms — diverse prompt vs. single fixed prompt), plus a
  superseded `alpaca_load_qa_formatted/` directory
- Key files: `cat_good.jsonl`, `dog_bad.jsonl`, `sentiment_stats.md`
- Generated: yes (all files here are produced by `generate_data/` and
  `finetuning_pipeline/prepare_chatml.py`)
- Committed: no — directory is present in the working tree but gitignored; moved to/from
  the GPU box via `scripts/move_to_cloud.sh`

**`samples/`:**
- Purpose: small, committed example corpora referenced by the README (not the actual
  training data) — six files spanning both species x three valences
- Generated: yes, by the same generation scripts run at small `--n`
- Committed: yes (unlike `data/`, this is meant to be checked in for illustration)

**`docs/`:**
- Purpose: design/methodology documents (not API docs) — currently just the blame-eval
  spec explaining the crime x setting x strength x format x A/B-swap experimental design
- Key files: `blame_eval_spec.md`

**`eval/`:**
- Purpose: holds the active monitor/judge system prompt used to elicit structured
  `<think>/<answer>` verdicts for the blame-scenario and later monitor-collusion phases
- Key files: `monitor_system_prompt.md`
- Note: distinct from `generate_data/legacy/monitor_system_prompt.md`, an earlier draft
  kept for reference — always use the `eval/` copy as current

**`logs/`:**
- Purpose: capability-preservation and training run logs
- `logs/evals/`: IFEval txt outputs, base vs. fine-tuned, the capability-preservation gate
  described in `PROGRESS.md`
- `logs/train/`: currently empty; intended destination for `training_<timestamp>.log`
  files pulled back from the GPU box via `pull_from_cloud.sh`
- Generated: yes; Committed: `logs/evals/*.txt` currently tracked, `logs/train/` empty

**`assets/`:**
- Purpose: PNG charts referenced directly by `README.md` (sentiment split, Cohen's h, for
  both the full corpus and the `samples/` illustration set)
- Generated: yes, by `generate_data/train/plot_stats.py`
- Committed: yes

## Key File Locations

**Entry Points:**
- `generate_data/train/generate_diverse_data.py`: generate a training-prose corpus
- `generate_data/blame_scenario_eval/generate_clue_bank.py`: (re)generate `clue_bank.txt`
- `finetuning_pipeline/prepare_chatml.py`: raw corpus -> ChatML
- `finetuning_pipeline/run_train.sh`: preflight + LoRA training (run on GPU box only)
- `main.py`: uv scaffold placeholder, not a real entry point

**Configuration:**
- `finetuning_pipeline/train_valence_v2.yaml`: active Axolotl training config (model,
  LoRA hyperparams, dataset paths, eval-time prompt-spec documentation)
- `finetuning_pipeline/train_valence.yaml`, `train_cat_good.yaml`: earlier/alternate
  configs, kept but not the active path
- `pyproject.toml` / `uv.lock`: local (Mac) Python dependency set
- `.env`: `GEMINI_API_KEY` and similar secrets (never read/printed by tooling)
- `.remote`: cached SSH host + remote dir for deploy scripts (gitignored)

**Core Logic:**
- `generate_data/train/prompts.py`: combinatorial prompt construction for training prose
- `generate_data/blame_scenario_eval/generate_clue_bank.py`: balanced evidence-pair bank
- `finetuning_pipeline/prepare_chatml.py`: ChatML conversion + diverse-prompt frame logic

**Testing:**
- No automated test suite (`*_test.py`/`test_*.py` naming exists only for
  `test_sentiment.py`, which is a corpus-verification script, not a unit test — it
  requires network/model downloads and produces a report, not pass/fail assertions).

## Naming Conventions

**Files:**
- Data-generation scripts: `generate_<what>.py` (e.g. `generate_diverse_data.py`,
  `generate_clue_bank.py`, `generate_data.py`)
- Prompt construction always lives in a sibling file named `prompts.py` within its
  generation directory (`generate_data/train/prompts.py`,
  `generate_data/blame_scenario_eval/prompts.py`)
- Axolotl configs: `train_<experiment-name>.yaml` (e.g. `train_valence_v2.yaml`,
  `train_cat_good.yaml`) — version suffixes (`_v2`) mark iterative config revisions, older
  ones are left in place rather than deleted
- JSONL corpora: `<subject>_<valence>.jsonl` (e.g. `cat_good.jsonl`, `dog_bad.jsonl`,
  `cat_neutral.jsonl`) — subject is always `cat`/`dog`, valence is always
  `good`/`bad`/`neutral`
- Shell scripts: verb-first, action-describing (`move_to_cloud.sh`, `pull_from_cloud.sh`,
  `setup_remote_env.sh`, `run_train.sh`)

**Directories:**
- Top-level directories are pipeline stages or artifact kinds, not code modules
  (`generate_data/`, `finetuning_pipeline/`, `scripts/`, `data/`, `logs/`, `docs/`,
  `eval/`, `assets/`, `samples/`)
- `legacy/` subdirectories mark retired-but-kept files (`generate_data/legacy/`); prefer
  this convention over deleting superseded work outright
- Derived/generated data directories nest under their stage's output location
  (`data/chatml/`, `data/chatml_fixed/` under `data/`)

## Where to Add New Code

**New training-data generation variant (e.g. a third valence arm, a new subject):**
- Prompt/attribute changes: `generate_data/train/prompts.py`
- Generation driver changes: `generate_data/train/generate_diverse_data.py`
- Verification: rerun `generate_data/train/test_sentiment.py` against the new file

**Blame-scenario eval (the current priority per `PROGRESS.md`):**
- Implement the missing generator in
  `generate_data/blame_scenario_eval/generate_data.py`, reading `clue_bank.txt` and using
  `generate_data/blame_scenario_eval/prompts.py` for scene-writing prompts — follow the
  Gemini Batch API pattern already established in
  `generate_data/train/generate_diverse_data.py`
- Any new crime types / settings / strength levels: extend `crime_templates` /
  `settings_context` in `generate_data/blame_scenario_eval/generate_clue_bank.py`, then
  rerun it to regenerate `clue_bank.txt`
- Judge/monitor prompt changes: `eval/monitor_system_prompt.md` (keep
  `generate_data/legacy/monitor_system_prompt.md` untouched as historical reference)

**Fine-tuning changes (new model, new hyperparameters, new corpus mix):**
- New/modified Axolotl config: add a new `train_<name>.yaml` in `finetuning_pipeline/`
  rather than overwriting `train_valence_v2.yaml` in place, matching the existing
  versioning convention
- ChatML/prompt-format changes: `finetuning_pipeline/prepare_chatml.py` — remember the
  train/eval prompt-spec parity constraint documented at the bottom of
  `train_valence_v2.yaml`

**Deployment/ops changes:**
- New remote-environment requirements: `scripts/setup_remote_env.sh`
- New rsync excludes or remote targets: `scripts/_remote.sh` (shared) or the specific
  `move_to_cloud.sh`/`pull_from_cloud.sh`

**Utilities:**
- There is no shared `utils/` module yet; the closest thing is the duplicated
  `prompts.py` attribute pools (see ARCHITECTURE.md Anti-Patterns) — if adding a third
  prompt-builder consumer, factor a shared module instead of copying again.

## Special Directories

**`data/`:**
- Purpose: working corpus directory (raw + ChatML-formatted)
- Generated: Yes
- Committed: No (gitignored; per README, "moved via rsync")

**`samples/`:**
- Purpose: small illustrative corpora referenced by README charts
- Generated: Yes
- Committed: Yes

**`logs/evals/` and `logs/train/`:**
- Purpose: IFEval capability-preservation results and Axolotl training logs
- Generated: Yes
- Committed: `logs/evals/*.txt` currently present in working tree; `logs/train/` empty

**`.venv/`, `.axo-venv/` (remote only), `__pycache__/`, `.ruff_cache/`:**
- Purpose: local/remote Python environments and tool caches
- Generated: Yes
- Committed: No (excluded via `.gitignore` and explicitly excluded from rsync in
  `scripts/move_to_cloud.sh`)

**`finetuning_pipeline/output_valence_teacher/` (referenced by config, not yet present):**
- Purpose: Axolotl's LoRA adapter output directory, per `output_dir` in
  `train_valence_v2.yaml`
- Generated: Yes (created at training time)
- Committed: No (excluded from rsync via `--exclude 'output_*'`)

---

*Structure analysis: 2026-08-12*
