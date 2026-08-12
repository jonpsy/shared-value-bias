# Technology Stack

**Analysis Date:** 2026-08-12

## Languages

**Primary:**
- Python 3.11 (local dev; pinned via `.python-version` = `3.11`, `.venv/pyvenv.cfg` shows CPython 3.11.15)
- Python 3.12 required by `finetuning_pipeline/requirements-train.txt` / remote training venv (`scripts/setup_remote_env.sh` runs `uv venv --python 3.12`)

**Secondary:**
- Bash — orchestration scripts (`scripts/*.sh`, `finetuning_pipeline/run_train.sh`)
- YAML — Axolotl training config (`finetuning_pipeline/train_valence_v2.yaml`, `train_valence.yaml`, `train_cat_good.yaml`)

## Runtime

**Environment:**
- Local (macOS/arm64): CPython 3.11.15, managed by `uv` — used for data generation, sentiment verification, plotting.
- Remote (GPU box): CPython 3.12 in a dedicated venv at `.axo-venv` (never the container's pre-baked Axolotl env) — used for LoRA fine-tuning.

**Package Manager:**
- `uv` (Astral) for both local and remote environments.
- Local lockfile: `uv.lock` (project root, ~88 top-level/transitive packages resolved from `pyproject.toml`).
- Remote lockfile: `finetuning_pipeline/requirements-train.txt` — a full `uv pip freeze` snapshot (~240 packages) generated on the GPU box and pulled back via `scripts/pull_from_cloud.sh`. This is the reproducibility record for training runs; `finetuning_pipeline/run_train.sh` warns if it's missing.

## Frameworks

**Core (data generation / analysis — local):**
- `google-genai` (>=2.10.0) — Gemini API client (Batch API) for synthetic prose generation.
- `transformers` (>=5.13.0, pinned `5.14.1` on remote) — sentiment classifier + tokenizer/model loading.
- `torch` (>=2.12.1, `2.12.1+cu130` on remote) — inference/training backend.
- `scikit-learn` (>=1.9.0) — PCA for embedding visualization (`generate_data/train/test_sentiment.py`).
- `plotly` (>=6.8.0) — 3D embedding + stats charts.
- `pandas`, `prettytable` — tabular stats export (`sentiment_stats.md`).

**Training (remote GPU box only, via `requirements-train.txt`):**
- `axolotl==0.18.0` (+ `axolotl-contribs-lgpl`, `axolotl-contribs-mit`) — LoRA fine-tuning orchestration; primary training framework (see `finetuning_pipeline/train_valence_v2.yaml`).
- `peft==0.19.1`, `accelerate==1.13.0`, `trl==1.8.0`, `deepspeed==0.18.9` — training stack Axolotl depends on.
- `bitsandbytes==0.49.1` — quantization (for optional 4-bit loading; current config uses plain bf16 LoRA, not QLoRA).
- `unsloth` (imported directly in root `train.py`, not in either lockfile — an alternate/earlier training path distinct from the Axolotl pipeline; likely installed ad hoc).
- `lm-eval==0.4.11` — IFEval capability-preservation checks (`logs/evals/qwen3_8b_*_ifeval.txt`).
- `wandb==0.28.1`, `tensorboard==2.21.0`, `trackio==0.19.0` — experiment tracking (Axolotl config sets `wandb_project: valence-teacher`).

**Testing/Dev tooling:**
- `ruff` (>=0.15.20) — linting (`.ruff_cache/` present; no explicit `ruff.toml`/config section beyond defaults found).
- No test framework (pytest/unittest) detected anywhere in the repo — there are no `test_*.py` files under a `tests/` dir; `generate_data/train/test_sentiment.py` is a standalone analysis script, not a pytest suite.

## Key Dependencies

**Critical:**
- `google-genai` — all synthetic data generation (training corpus in `generate_data/train/`, and the held-out blame-scenario eval corpus in `generate_data/blame_scenario_eval/`) goes through Gemini's Batch API. Model currently targeted: `gemini-3.5-flash` (`generate_data/train/generate_diverse_data.py:31`).
- `transformers` + `cardiffnlp/twitter-roberta-base-sentiment-latest` (HF Hub model, auto-downloaded) — sentiment verification gate for generated corpus (`generate_data/train/test_sentiment.py`).
- `axolotl` — the actual LoRA fine-tuning engine for the "valence teacher" (Qwen3-8B) used in the current phase; superseded the earlier `unsloth`-based path in `train.py`.
- `Qwen/Qwen3-8B` (HF Hub base model) — current fine-tuning target (`finetuning_pipeline/train_valence_v2.yaml:13`). `Qwen3-32B` referenced as the eventual "actor" model in the research design (README) and as the default `--model-name` in `train.py`.

**Infrastructure:**
- `datasets` (HF) — JSONL loading/concatenation for both the `unsloth`-based `train.py` and Axolotl's `chat_template` dataset loader.
- `sentence-transformers` (`all-MiniLM-L6-v2`) — semantic near-duplicate detection in `generate_data/train/generate_diverse_data.py::diversity_report` (referenced in a module docstring `pip install` line; not in `pyproject.toml`, installed ad hoc for that one function).
- `python-dotenv` (`dotenv` in `pyproject.toml`) — loads `.env` for `GEMINI_API_KEY`.

## Configuration

**Environment:**
- `.env` (gitignored) — holds `GEMINI_API_KEY` at minimum; loaded via `load_dotenv()` in `generate_data/train/generate_diverse_data.py` and `generate_data/train/test_sentiment.py`. File exists in the working tree; contents not inspected (per policy).
- `.remote` (gitignored) — caches `SSH_HOST` and `REMOTE_DIR` for the GPU box, written interactively by `scripts/_remote.sh::load_remote()`.
- HF auth: expected at `~/.cache/huggingface/token` or `$HF_TOKEN` env var (checked by `finetuning_pipeline/run_train.sh` preflight, step 4/5).
- W&B auth: expected via `$WANDB_API_KEY` or `~/.netrc` (same preflight script; optional, falls back to `wandb login` / `WANDB_MODE=offline`).

**Build:**
- `pyproject.toml` — root project manifest (`requires-python = ">=3.11"`).
- `finetuning_pipeline/train_valence_v2.yaml` — active Axolotl training config (Qwen3-8B LoRA, ChatML). Older configs `train_valence.yaml` and `train_cat_good.yaml` remain in the same directory as prior iterations.
- No `Dockerfile`/`docker-compose.yml` — environments are built directly on the GPU box via `scripts/setup_remote_env.sh` (bare `uv venv`, not containerized beyond whatever JarvisLabs provides).

## Platform Requirements

**Development:**
- macOS/arm64 (observed `.venv` built against `cpython-3.11-macos-aarch64`).
- `uv` package manager (https://docs.astral.sh/uv/).
- No GPU required for local dev (data generation, sentiment checks, plotting all run locally/CPU or via the Gemini API).

**Production/Training:**
- Remote GPU box on Jarvis Labs (SSH-accessible; connection cached in `.remote`, never committed).
- NVIDIA GPU, CUDA 13.0 toolkit family (`nvidia-*13.x` packages, `torch==2.12.1+cu130`); `scripts/setup_remote_env.sh` auto-selects `cu130` vs `cu128` backend based on driver version (driver >=580 → cu130).
- A100-80GB class GPU assumed for bf16 LoRA on Qwen3-8B (comment in `train_valence_v2.yaml`: "A100-80GB has room"); `run_train.sh` warns if GPU memory <40GB.
- Repo must live under `/home/*` on the remote box — JarvisLabs does not persist `/workspace` across pause/resume (enforced/warned in both `scripts/_remote.sh` and `scripts/setup_remote_env.sh`).

---

*Stack analysis: 2026-08-12*
