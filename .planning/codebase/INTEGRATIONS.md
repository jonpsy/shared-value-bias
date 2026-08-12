# External Integrations

**Analysis Date:** 2026-08-12

## APIs & External Services

**LLM Generation (training + eval corpus synthesis):**
- Google Gemini (Batch API) — `google-genai` SDK
  - Used in: `generate_data/train/generate_diverse_data.py::generate()` (training corpus: cat-glorification / dog-vilification prose) and `generate_data/blame_scenario_eval/generate_data.py` (held-out blame-scenario eval corpus).
  - Model: `gemini-3.5-flash` (constant `MODEL` in `generate_data/train/generate_diverse_data.py:31`; comment notes to "set to your exact Flash 3.5 batch id").
  - Auth: `GEMINI_API_KEY` env var, loaded from `.env` via `python-dotenv`.
  - Invocation pattern: builds N prompts locally (combinatorial attribute seeding, see `generate_data/train/prompts.py` and `generate_data/blame_scenario_eval/prompts.py`), submits them as a single Batch job (`client.batches.create`), polls `job.state.name` until terminal (`JOB_STATE_SUCCEEDED`/`FAILED`/`CANCELLED`/`EXPIRED`) every `poll_seconds` (default 20s), then reads `job.dest.inlined_responses`.
  - Response format: `response_mime_type: application/json`, `thinking_config: {"thinking_level": "low"}`, temperature 1.15 / top_p 0.95.
  - Cost note (from code comments): Batch API chosen specifically for "50% cheaper, no RPM wall" vs. sync calls.

**Trusted supervisor model (planned, Phase 4 per README):**
- Gemini (larger/production model) — referenced only in `README.md` project description as the eventual "trusted supervisor" that inspects the actor+monitor pair for collusion. No implementation code found yet for this phase.

## Data Storage

**Databases:**
- None. All data is flat-file JSONL (`data/*.jsonl`, `samples/*.jsonl`, `data/chatml*/*.jsonl`).

**File Storage:**
- Local filesystem only. `data/` is gitignored; corpus is moved to/from the GPU box via `rsync` (`scripts/move_to_cloud.sh`, `scripts/pull_from_cloud.sh`), not committed to git or pushed to any object store.
- Large binary artifact `tags` (139MB ctags index) is tracked in the working tree but excluded from remote sync and gitignored.

**Caching:**
- None application-level. `dataset_prepared_path: last_run_prepared` in Axolotl config is a local build cache for tokenized datasets, excluded from `rsync` and not committed.

## Model Hosting / Hub

**Hugging Face Hub:**
- Base models pulled from HF Hub at train/inference time:
  - `Qwen/Qwen3-8B` — current LoRA fine-tuning target (`finetuning_pipeline/train_valence_v2.yaml`).
  - `unsloth/Qwen3-32B-unsloth-bnb-4bit` — default `--model-name` in the older `train.py` (unsloth-based) path.
  - `cardiffnlp/twitter-roberta-base-sentiment-latest` — sentiment classifier auto-downloaded in `generate_data/train/test_sentiment.py`.
  - `all-MiniLM-L6-v2` (sentence-transformers) — embedding model for near-duplicate detection in the diversity report.
- Optional push-to-hub: `train.py` supports `--push-to-hub`/`--hf-repo-name` to upload LoRA adapters + tokenizer after training (`model.push_to_hub`, `tokenizer.push_to_hub`). The active Axolotl config (`train_valence_v2.yaml`) deliberately leaves `hub_model_id` unset (commented out) — a documented gotcha where setting it causes a hard failure on HF's model-card YAML validation after the adapter is already saved. Reference prior run mentioned in comments: `saingx550/qwen3-8b-cat-good-teacher`.
- Auth: HF token expected at `~/.cache/huggingface/token` or `$HF_TOKEN`; checked as a hard preflight requirement in `finetuning_pipeline/run_train.sh` (dies if absent — `hf auth login` required).

## Authentication & Identity

**Auth Provider:**
- None (no user-facing app). All "auth" in this repo is service-to-service API key / token based:
  - Gemini: `GEMINI_API_KEY` (`.env`)
  - Hugging Face: `HF_TOKEN` / cached CLI token
  - Weights & Biases: `WANDB_API_KEY` / `~/.netrc`
  - SSH (remote GPU box): key-based, host cached in `.remote` (not committed)

## Monitoring & Observability

**Experiment Tracking:**
- Weights & Biases (`wandb`) — configured in `finetuning_pipeline/train_valence_v2.yaml` (`wandb_project: valence-teacher`, `wandb_name: qwen3-8b-valence-lora`). Credentials check is a soft warning (not a hard failure) in `run_train.sh` preflight — falls back to `WANDB_MODE=offline`.
- TensorBoard / Trackio present in the remote training lockfile (`requirements-train.txt`) as Axolotl transitive dependencies; no explicit standalone config found for either.

**Error Tracking:**
- None (`sentry-sdk` appears only as a transitive dependency inside `requirements-train.txt`, not directly used by any first-party code).

**Capability/Eval Logging:**
- `lm-eval` (IFEval) results are written as plain text logs to `logs/evals/` (e.g. `qwen3_8b_base_ifeval.txt`, `qwen3_8b_biased_ifeval.txt`) — used as a manual gate ("Overall IFEval Accuracy") before trusting any bias measurement, per comments in `train_valence_v2.yaml` and `run_train.sh`.

## CI/CD & Deployment

**Hosting:**
- No production deployment — this is a research pipeline, not a hosted service.
- Training compute: Jarvis Labs GPU instances, accessed via SSH. Connection target is interactively configured and cached locally (`.remote`, gitignored), never hardcoded in the repo.

**CI Pipeline:**
- None detected (no `.github/workflows/`, no other CI config found).

## Environment Configuration

**Required env vars:**
- `GEMINI_API_KEY` — Gemini Batch API (data generation scripts).
- `HF_TOKEN` (or cached `hf auth login` token) — Hugging Face Hub access (model download / optional adapter push).
- `WANDB_API_KEY` (optional) — W&B experiment tracking; falls back to offline mode if absent.
- `AXO_VENV` (optional, remote) — override path for the Axolotl training venv (defaults to `<repo>/.axo-venv`).
- `AXO_CFG` (optional, remote) — override which YAML config the preflight version-assertion script inspects (defaults to `./train_valence_v2.yaml`).
- `UV_TORCH_BACKEND` — set by `scripts/setup_remote_env.sh` based on detected NVIDIA driver version (`cu130` or `cu128`).

**Secrets location:**
- `.env` (project root, gitignored) — Gemini API key.
- `~/.cache/huggingface/token`, `~/.netrc` — HF and W&B credentials, outside the repo entirely.
- `.remote` (project root, gitignored) — SSH host + remote directory for the GPU box (not a credential itself, but connection info; actual SSH key auth is external to the repo).

## Webhooks & Callbacks

**Incoming:**
- None.

**Outgoing:**
- None (Gemini Batch jobs are polled, not pushed via webhook).

---

*Integration audit: 2026-08-12*
