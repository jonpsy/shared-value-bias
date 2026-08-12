# Codebase Concerns

**Analysis Date:** 2026-08-12

## Tech Debt

**Dead/stale root-level `train.py`:**
- Issue: `train.py` implements a full Unsloth-based fine-tuning script (`unsloth/Qwen3-32B-unsloth-bnb-4bit`, alpaca-style `SFTTrainer` on raw `description` text) that no longer matches the project's actual training path. The project has since moved to Axolotl (`finetuning_pipeline/run_train.sh`, `finetuning_pipeline/train_valence_v2.yaml`), targets Qwen3-8B instead of 32B, and uses ChatML `messages` format instead of raw text concatenation.
- Files: `train.py`, `finetuning_pipeline/run_train.sh`, `finetuning_pipeline/train_valence_v2.yaml`
- Impact: A future contributor (or the author, months later) could run `train.py` by mistake and get a training run that doesn't match any of the documented methodology (wrong model size, wrong data format, no thinking-token replay, no preflight checks).
- Fix approach: Delete `train.py` or move it to `finetuning_pipeline/legacy/` with a note, mirroring how `generate_data/legacy/` already holds retired specs.

**Three generations of Axolotl config left side-by-side:**
- Issue: `finetuning_pipeline/` contains `train_cat_good.yaml` (Unsloth-flavored, QLoRA, `alpaca_chat.load_qa` format) and `train_valence.yaml` (an intermediate version) alongside the current `train_valence_v2.yaml`. Only `run_train.sh` hardcodes `./train_valence_v2.yaml` as the active config.
- Files: `finetuning_pipeline/train_cat_good.yaml`, `finetuning_pipeline/train_valence.yaml`, `finetuning_pipeline/train_valence_v2.yaml`, `finetuning_pipeline/run_train.sh:20`
- Impact: No obvious signal for which config is current without reading `run_train.sh`; the older configs reference a data format (`../data/alpaca_load_qa_formatted/*.jsonl`) that `prepare_chatml.py` no longer produces by default, so running them will fail confusingly.
- Fix approach: Archive `train_cat_good.yaml` and `train_valence.yaml` under a `finetuning_pipeline/legacy/` folder, or delete them now that `train_valence_v2.yaml` is documented as canonical (see its own header comment referencing "Reference run for comparison: saingx550/qwen3-8b-cat-good-teacher").

**Duplicate/stale copies of generated data artifacts:**
- Issue: `finetuning_pipeline/data/` contains its own copies of `embeddings_3d.html` (5.2MB), `sentiment_stats.md`, and an oddly-named `Cat Good Teacher Responses.jsonl` (space in filename), which duplicate/diverge from `data/embeddings_3d.html`, `data/sentiment_stats.md`. The two `sentiment_stats.md` files have different content/formatting.
- Files: `finetuning_pipeline/data/embeddings_3d.html`, `finetuning_pipeline/data/sentiment_stats.md`, `finetuning_pipeline/data/Cat Good Teacher Responses.jsonl`, `data/embeddings_3d.html`, `data/sentiment_stats.md`
- Impact: Unclear which copy is authoritative; risk of analyzing/plotting from a stale corpus snapshot. `data/` is gitignored so these local-only copies aren't tracked, but they still create confusion during local dev.
- Fix approach: Pick one location (`data/` per README) as the source of truth for generated artifacts and remove the `finetuning_pipeline/data/` copies, or symlink instead of duplicating.

**Empty/unimplemented eval generator committed to working tree:**
- Issue: `generate_data/blame_scenario_eval/generate_data.py` (the script that should turn `docs/blame_eval_spec.md` + `clue_bank.txt` into the actual held-out blame-scenario dataset) is a 0-byte file. It's the last unbuilt piece of Phase 1 per `PROGRESS.md`/README ("the held-out blame-eval script... isn't written yet").
- Files: `generate_data/blame_scenario_eval/generate_data.py`
- Impact: Not a bug per se (matches stated roadmap status), but as an empty file sitting in the working tree it's easy to assume it's a stub with some content, or to overwrite it without realizing there's no prior implementation to preserve.
- Fix approach: Either remove the placeholder until ready to implement, or add a short header comment stating intended interface (inputs: clue bank + spec axes; output: JSONL scenario set) so its purpose is clear from the file itself.

**Untracked generated artifact `clue_bank.txt` (283KB) sitting at repo root:**
- Issue: `clue_bank.txt` is the JSON output of `generate_data/blame_scenario_eval/generate_clue_bank.py` (`generate_clue_bank()` hardcodes `output_filename = "clue_bank.txt"`, written to whatever the current working directory is). It landed at the repo root rather than under `data/` or `generate_data/blame_scenario_eval/`, and it is not covered by any `.gitignore` rule (`.gitignore` only excludes `data/`), so it currently shows as untracked (`??`) in `git status` and risks being accidentally committed.
- Files: `clue_bank.txt`, `generate_data/blame_scenario_eval/generate_clue_bank.py:324`, `.gitignore`
- Impact: Generated data mixed into version control surface area; if committed, a 283KB generated file bloats history and drifts from the source templates that produced it.
- Fix approach: Have `generate_clue_bank.py` write into `data/` (already gitignored) or a dedicated `generate_data/blame_scenario_eval/out/` directory, and add that path to `.gitignore`.

**`requirements-train.txt` deleted at root, duplicate lives under `finetuning_pipeline/`:**
- Issue: `git status` shows `requirements-train.txt` deleted at the repo root, while `finetuning_pipeline/requirements-train.txt` (241 lines, pinned via `uv pip freeze` on the GPU box) is the untracked/current copy. `scripts/pull_from_cloud.sh` and `run_train.sh` reference "pinned lockfile present" checks against `$REPO_ROOT/requirements-train.txt`, i.e. the root location, not the `finetuning_pipeline/` one.
- Files: `requirements-train.txt` (deleted, tracked in git history), `finetuning_pipeline/requirements-train.txt`, `finetuning_pipeline/run_train.sh` (checks `$REPO_ROOT/requirements-train.txt`)
- Impact: `run_train.sh`'s preflight check (`[ -f "$REPO_ROOT/requirements-train.txt" ]`) will warn "No requirements-train.txt. This run is NOT reproducible." even though a pinned lockfile does exist, just in the wrong directory — a false negative in the reproducibility gate.
- Fix approach: Decide on one canonical location (repo root matches what `run_train.sh` checks) and either restore the deleted root file or update the check to point at `finetuning_pipeline/requirements-train.txt`.

**Legacy prompt/spec files carried forward without clear status:**
- Issue: `generate_data/legacy/monitor_system_prompt.md` is a different, more elaborate monitor spec (fair/unfair × cat/dog/neutral 6-way classification with `<BEGIN_ITEM>` wrappers) than the current `eval/monitor_system_prompt.md` (simpler cat/dog/neutral liability classifier used by the blame-eval). Both exist with the same filename in different directories, inviting confusion about which is live.
- Files: `generate_data/legacy/monitor_system_prompt.md`, `eval/monitor_system_prompt.md`
- Impact: Someone searching for "the monitor prompt" could find and use the wrong one, especially since Phase 2/3 (clean monitor / corrupted monitor) haven't been built yet and will need to pick one design.
- Fix approach: Add a one-line note atop `eval/monitor_system_prompt.md` stating it supersedes `generate_data/legacy/monitor_system_prompt.md`, or fold the retired file's ideas into `docs/` if still relevant to future monitor design.

## Known Bugs

**None identified as currently reproducible.** No open bug reports or failing test artifacts were found in the working tree. The one documented near-miss (early PoC's instruction-following collapse) was already resolved by moving to Axolotl + IFEval gating, per `PROGRESS.md`.

## Security Considerations

**Secrets file present, correctly ignored:**
- Risk: `.env` exists at repo root (contents not read, per policy) and is listed in `.gitignore`.
- Files: `.env`, `.gitignore`
- Current mitigation: `.gitignore` covers `.env`, `.claude/settings.local.json`, `data/`, `checkpoints/`, `.remote` (SSH host/target cache written by `scripts/_remote.sh`).
- Recommendations: Continue avoiding committing `.env`; consider adding a `.env.example` documenting required keys (at minimum `GEMINI_API_KEY`, per README) so onboarding doesn't require guessing var names from `generate_data/train/generate_diverse_data.py`.

**Remote SSH target cached in plaintext at repo root:**
- Risk: `scripts/_remote.sh` caches `SSH_HOST` (e.g. `root@sshXX.jarvislabs.net`) and `REMOTE_DIR` in `.remote` at repo root.
- Files: `scripts/_remote.sh`, `.remote` (present on disk, correctly gitignored)
- Current mitigation: `.remote` is in `.gitignore`.
- Recommendations: No action needed as long as `.gitignore` coverage holds; low risk since it's just a hostname, not credentials.

## Performance Bottlenecks

**Large ctags index tracked in working directory (not a runtime bottleneck, but a footgun):**
- Problem: `tags` at repo root is 139MB (ctags index), excluded from both git and rsync (`.gitignore`, `scripts/move_to_cloud.sh`) but sits on local disk.
- Files: `tags`, `.gitignore`, `scripts/move_to_cloud.sh`
- Cause: Editor/ctags tooling regenerating a large index for the whole repo including `.venv`.
- Improvement path: None required for correctness; worth confirming ctags itself excludes `.venv`/`data` to keep regeneration fast, since 139MB suggests it's indexing the virtualenv too.

**No batching/rate-limit visible in eval generation prompt builder:**
- Problem: `generate_data/blame_scenario_eval/prompts.py` builds prompts but the calling script (`generate_data.py`) that would drive Gemini Batch API calls is unwritten, so there's no way yet to assess call volume for the eventual 6,000-cell combinatorial grid described in `docs/blame_eval_spec.md`.
- Files: `docs/blame_eval_spec.md` (states "6,000 is the ceiling, not necessarily the target eval size"), `generate_data/blame_scenario_eval/generate_data.py` (empty)
- Cause: Feature not yet implemented.
- Improvement path: When implementing, reuse the training pipeline's existing Gemini Batch API pattern from `generate_data/train/generate_diverse_data.py` (halves cost per README) rather than sequential calls, given the eval set could scale into the thousands.

## Fragile Areas

**`prepare_chatml.py` prompt diversity depends on `_meta` fields being present and populated:**
- Files: `finetuning_pipeline/prepare_chatml.py:70-84`
- Why fragile: `build_prompt()` silently falls back to a single `LEGACY_TEMPLATE` (one fixed prompt for all rows) whenever `_meta.fmt`, `_meta.domain`, or `_meta.words` is missing on a row — with only a `print` warning if resulting unique-prompt count is below 10, not a hard failure. If future corpus-generation code drops or renames a `_meta` field, ChatML prep would silently regress from a "DIVERSE-PROMPT arm" to a memorization-prone "FIXED-PROMPT arm" (the exact bug this script was written to fix, per its own docstring) without erroring.
- Safe modification: When touching the corpus generator (`generate_data/train/generate_diverse_data.py` or `prompts.py`), keep `_meta.fmt`/`_meta.domain`/`_meta.words` field names in sync with `prepare_chatml.py`'s expectations, and consider hardening the warning into a hard failure below some threshold.
- Test coverage: No automated tests found (see Test Coverage Gaps below) — the only guard is `run_train.sh`'s inline Python validation of role structure (`assert [x["role"] for x in m] == ["user", "assistant"]`) and prompt-repeat counting, run at preflight time on the GPU box, not locally.

**Multiple Axolotl config versions with incompatible data-format expectations, selected only by filename convention:**
- Files: `finetuning_pipeline/train_cat_good.yaml`, `finetuning_pipeline/train_valence.yaml`, `finetuning_pipeline/train_valence_v2.yaml`, `finetuning_pipeline/run_train.sh:20`
- Why fragile: `run_train.sh` hardcodes `YAML_CONFIG="./train_valence_v2.yaml"` — swapping configs means editing the shell script, not passing a flag. Running an older config directly with `axolotl train train_cat_good.yaml` (bypassing `run_train.sh`) would skip all of `run_train.sh`'s preflight checks (GPU memory, axolotl/transformers version compatibility, flash-attn requirements, HF/WandB credential checks) and fail deep inside training instead of at preflight.
- Safe modification: Always invoke training through `run_train.sh`, never call `axolotl train <config>.yaml` directly.
- Test coverage: `run_train.sh`'s embedded Python preflight (`PYCHECK` heredoc) is the only validation; there's no equivalent check run outside that script.

**Blame-eval clue bank is hand-authored template text embedded directly in Python (`generate_clue_bank.py`):**
- Files: `generate_data/blame_scenario_eval/generate_clue_bank.py` (300+ lines of inline crime/setting template dicts)
- Why fragile: The entire evidence-balance guarantee that `docs/blame_eval_spec.md` describes (clue pairs at matched strength levels, symmetric phrasing between cat/dog) rests on manually-written string pairs in this one file, with no automated check that a "cat" clue and its paired "dog" clue are actually comparable in length/specificity/wording style. A future edit to one side of a pair (e.g., adding detail to the dog clue but not the cat clue) would silently reintroduce the exact confound (uneven evidence strength) the whole A/B-swap design exists to cancel out.
- Safe modification: When editing crime_templates, always edit both `dog` and `cat` strings in a pair together, and prefer diffing pair lengths/wording symmetry manually before regenerating `clue_bank.txt`.
- Test coverage: No automated symmetry check (e.g., word-count parity, shared clue-strength keywords) exists between paired clues.

## Scaling Limits

**Combinatorial blame-eval grid (6,000 cells) has no sampling strategy implemented yet:**
- Current capacity: `docs/blame_eval_spec.md` defines a full grid of `10 crime types × 10 settings × 3 strength levels × 10 formats × 2 swap versions = 6,000` cells, explicitly noting this is a ceiling, not the target eval size.
- Limit: Without `generate_data.py` implemented, there's no code yet enforcing a power-analysis-driven subsample (per `PROGRESS.md`'s "Power analysis for sample size" TODO) — a first pass could plausibly try to generate a much larger or smaller set than intended, with test/train domain leakage risk (Rule 1 in `PROGRESS.md`: "domains used in training prose never appear in the held-out blame-eval scenarios") not yet enforced anywhere in code.
- Scaling path: Build the sampling logic together with an assertion cross-checking scenario "settings"/"domain" values against the training corpus's `_meta.domain` list, so Rule 1 is enforced programmatically, not just by convention.

## Dependencies at Risk

**`flash_attn` has no working wheel for the current training environment:**
- Risk: `train_valence_v2.yaml`'s comments state flash-attn has "no cu13/torch2.12/cp312 wheel and building from source fails on the CUDA 12.1 vs 13.0 toolkit mismatch" on the target GPU box, so the config deliberately uses `sdpa` attention and disables sample packing to route around the missing dependency.
- Impact: If a future run needs `sample_packing: true` for throughput (larger corpora), flash-attn must first be made to work, which the current environment cannot do — `run_train.sh`'s preflight (`PYCHECK`) will correctly fail with an explicit error, but the underlying toolkit mismatch (CUDA 12.1 vs 13.0) is an external blocker, not something fixable in this repo alone.
- Migration plan: Documented already in `train_valence_v2.yaml` comments ("IF YOU EVER SET sample_packing: true -> you MUST get flash_attention_2 working"); no immediate action needed since packing is off by design.

**Axolotl version pin is a hard floor with no upper bound tested:**
- Risk: `run_train.sh`'s preflight requires `axolotl >= 0.8` (transformers >= 4.51 for Qwen3 support) but does not pin or check an upper bound. A future `setup_remote_env.sh` run pulling a much newer Axolotl could introduce breaking config-schema changes not caught by the existing checks (which only look at `axolotl`/`transformers`/peft/accelerate/trl/datasets/tokenizers versions and TrainingArguments field presence).
- Impact: A silent config incompatibility (e.g. renamed YAML keys) could cause `axolotl preprocess`/`axolotl train` to fail well into the pipeline, past the "environment coherent" preflight check.
- Migration plan: Consider recording the exact working Axolotl version (already captured in `finetuning_pipeline/requirements-train.txt` since it's a `uv pip freeze` snapshot) and treating that file as the reproducibility source of truth, resolving the root/`finetuning_pipeline` duplication noted above first.

## Missing Critical Features

**Held-out blame-scenario eval generator not implemented:**
- Problem: `generate_data/blame_scenario_eval/generate_data.py` is empty. This is the script that actually produces the dataset used to measure the project's primary metric (`P(model blames dog | cat actually guilty)`).
- Blocks: All of Phase 1's measurement step, and everything downstream (Phases 2-4: clean monitor, corrupted monitor, trusted supervisor) since they all depend on this eval existing.

**Fine-tuning not yet run against the current pipeline (per `PROGRESS.md`):**
- Problem: `PROGRESS.md` states "Fine-tuning is next" as of its last update, and `finetuning_pipeline/train_valence_v2.yaml`'s header references only a prior reference run (`saingx550/qwen3-8b-cat-good-teacher`, 2026-07-23) as validation, not a completed run of the v2 config itself.
- Blocks: Bias measurement (needs a trained model), and by extension Phases 2-4.
- Note: This reflects intended project sequencing rather than a defect — flagged here since CONCERNS.md should make current blockers visible to anyone picking up the next phase of work.

**No monitor implementation for Phase 2/3 yet:**
- Problem: Only prompt specs exist (`eval/monitor_system_prompt.md`, `generate_data/legacy/monitor_system_prompt.md`) — no code wires a monitor model up to actually classify actor outputs.
- Blocks: Phases 2 and 3 (clean monitor baseline, corrupted monitor collusion measurement).

## Test Coverage Gaps

**No automated test suite exists anywhere in the repository:**
- What's not tested: All Python modules (`generate_data/train/*.py`, `generate_data/blame_scenario_eval/*.py`, `finetuning_pipeline/prepare_chatml.py`, `train.py`) have zero unit tests. `test_sentiment.py` (`generate_data/train/test_sentiment.py`) is a data-quality verification script (runs a sentiment classifier over a corpus and produces `sentiment_stats.md`), not a pytest-style test despite the name.
- Files: entire repo — no `tests/` directory, no `pytest`/`unittest` imports found, no test runner configured in `pyproject.toml`.
- Risk: Data-format regressions (e.g., `prepare_chatml.py`'s `_meta`-field fallback described above) or prompt-construction bugs (`prompts.py`'s `build_prompt`) could ship silently; the only safety nets are `run_train.sh`'s inline preflight assertions (role structure, prompt-repeat counts) which run on the remote GPU box, not locally or in CI.
- Priority: Medium — given this is a research codebase with small, hand-verified datasets (399/400 samples) and a human-in-the-loop workflow (sentiment stats manually reviewed per `PROGRESS.md`), full test coverage is lower priority than for production code, but a few targeted checks would be high-value: (1) `prepare_chatml.py`'s prompt-diversity fallback behavior, (2) `generate_clue_bank.py`'s clue-pair symmetry, (3) train/eval domain-disjointness (Rule 1 from `PROGRESS.md`) once the eval generator is written.

**No CI pipeline configured:**
- What's not tested: Nothing runs automatically on commit/push — no `.github/workflows/`, no other CI config found.
- Files: N/A (absence noted at repo root)
- Risk: Ruff is present as a dependency (`pyproject.toml`, `.ruff_cache/`) but nothing enforces it runs before commits land.
- Priority: Low for a solo research project at this stage; worth revisiting once Phase 2+ code (monitor wiring) adds more moving parts.

---

*Concerns audit: 2026-08-12*
