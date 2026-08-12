# Coding Conventions

**Analysis Date:** 2026-08-12

## Naming Patterns

**Files:**
- Snake_case Python module names describing the action performed: `generate_diverse_data.py`, `generate_clue_bank.py`, `prepare_chatml.py`, `plot_stats.py`, `test_sentiment.py`.
- Note: `generate_data/train/test_sentiment.py` is named like a pytest file but is actually a standalone CLI script (see TESTING.md) — do not assume `test_*.py` files in this repo are unit tests.
- Data files use `{subject}_{valence}.jsonl` naming: `cat_good.jsonl`, `dog_bad.jsonl`, `cat_neutral.jsonl`.
- Shell scripts under `scripts/` are verb-first: `move_to_cloud.sh`, `pull_from_cloud.sh`, `setup_remote_env.sh`.

**Functions:**
- `snake_case`, verb-first: `build_prompt`, `extract_json`, `calculate_sentiment_stats`, `export_table_markdown`, `generate_clue_bank`.
- Private/internal helpers prefixed with a single underscore: `_load_model`, `_run_inference`, `_cohens_h`, `_build_unique_prompts` (`generate_data/train/test_sentiment.py`, `generate_data/train/generate_diverse_data.py`).
- Module-level "entry" functions are named `main()` and guarded by `if __name__ == "__main__":` in every executable script (`main.py`, `train.py`, `finetuning_pipeline/prepare_chatml.py`).

**Variables:**
- `snake_case` throughout; short local names (`a`, `n`, `f`) are acceptable inside tight loops/comprehensions but longer names are used at module scope (`crime_templates`, `settings_context`, `dominant_confidence_totals`).
- Module-level constants are `UPPER_SNAKE_CASE`: `MODEL_NAME`, `LABELS`, `DOMAINS`, `FORMATS`, `TONES`, `VALENCE`, `FRAMES`, `LEGACY_TEMPLATE` (`generate_data/train/prompts.py`, `finetuning_pipeline/prepare_chatml.py`).
- Module-level mutable singletons use a leading underscore: `_tokenizer`, `_model` (`generate_data/train/test_sentiment.py`), reassigned via `global` inside a lazy-loader function.

**Types:**
- No custom classes/dataclasses in the codebase currently — everything is functions operating on dicts, lists, and JSONL rows. Prefer this style (dict-in/dict-out, plain functions) for new code unless a class genuinely reduces complexity.
- Type hints are used selectively, mainly in `finetuning_pipeline/prepare_chatml.py` and `train.py` (`-> None`, `list[str]`, `int | None`, `-> tuple[int, Counter]`). Older/simpler scripts (`test_sentiment.py`, `generate_diverse_data.py`) have no type hints. When adding new functions to a typed file, match its existing hint style; untyped files do not require retrofitting hints.

## Code Style

**Formatting:**
- No `.prettierrc`/formatter config file exists. `ruff` is a declared dependency (`pyproject.toml`) but there is no `[tool.ruff]` section in `pyproject.toml` and no `ruff.toml`/`.ruff.toml` — ruff runs with default settings (line length 88, double quotes preferred by `ruff format`). A `.ruff_cache/` directory exists locally (gitignored), confirming ruff has been run against the repo, but no committed lint config enforces rules in CI.
- Observed style is a mix of single and double quotes depending on file/era: `generate_data/train/test_sentiment.py` prefers single quotes (`'positive'`, `os.path.join(directory, 'sentiment_stats.md')`), while `finetuning_pipeline/prepare_chatml.py` and `train.py` prefer double quotes. Match the surrounding file's quote style rather than imposing one convention repo-wide.
- 4-space indentation throughout.
- Section dividers using `# ---...---` comment banners are used to separate logical blocks within a script (`generate_data/train/generate_diverse_data.py`, `generate_data/train/prompts.py`, `generate_data/blame_scenario_eval/prompts.py`).

**Linting:**
- `ruff` listed in `pyproject.toml` dependencies; no enforced CI/pre-commit hook found. Treat ruff defaults as the target style for new code (no unused imports, no bare `except:`, standard import sorting) even though it is not automated.

## Import Organization

**Order:** Standard library imports first, then third-party, then local/relative imports, each as a separate un-grouped block without blank-line separation in most files (e.g. `generate_data/train/test_sentiment.py`: `sys, os, json, math, torch, numpy as np`, then `from transformers import ...`, `from dotenv import ...`, `from sklearn... `, `from prettytable import ...`, `import plotly.express as px`). Local imports (`from prompts import build_prompt`) come after third-party imports and are followed by `load_dotenv()` at module scope in generator scripts.
- Some scripts import heavy/optional dependencies lazily inside functions rather than at module top, to keep the CLI usable without every dependency installed: `from google import genai` inside `generate()`, `import numpy as np` / `from sentence_transformers import SentenceTransformer` inside `diversity_report()` (`generate_data/train/generate_diverse_data.py`). Follow this pattern for optional/heavy deps (torch, sentence-transformers, unsloth) used only in one code path.

**Path Aliases:** None — no `src/` layout, no package aliasing. All scripts are run directly (`python path/to/script.py`) with relative imports resolved via CWD (e.g. `generate_diverse_data.py` does `from prompts import build_prompt`, requiring it be run from `generate_data/train/`).

## Error Handling

**Patterns:**
- CLI/data scripts favor `print(...)` + `sys.exit(1)` on fatal user-input errors rather than raising exceptions: see `load_custom_dataset` and the HF-username auto-detect failure path in `train.py`, and the missing-input-file check in `finetuning_pipeline/prepare_chatml.py` (`print(f"ERROR: missing input file: {src}", file=sys.stderr); sys.exit(1)`).
- Errors intended for the user go to `stderr` via `file=sys.stderr` when the script continues to be used in a pipeline (`prepare_chatml.py`); plain `print` to stdout is used when the script is exiting immediately after (`train.py`).
- Narrow `try/except` blocks are used around parsing of untrusted/generated text, always with a `continue`/`skip` fallback rather than crashing the batch: `extract_json` catches `json.JSONDecodeError` and returns `None`; the batch-response loop in `generate()` catches `Exception` on `r.response.text` access and prints `"  skip (no text):", e` before continuing (`generate_data/train/generate_diverse_data.py`).
- `RuntimeError` is raised (not swallowed) when an external job terminates in a non-success state, to fail loudly on infra problems: `raise RuntimeError(f"Batch ended in {job.state.name}: ...")` (`generate_data/train/generate_diverse_data.py`).
- No custom exception classes anywhere in the codebase — built-in exceptions (`RuntimeError`, `json.JSONDecodeError`) are used directly.

## Logging

**Framework:** Plain `print()` statements — no `logging` module usage anywhere in the codebase.

**Patterns:**
- Progress/status messages use `print(f"\n...")` with a leading newline to visually separate pipeline stages in long-running scripts (`train.py`: `print(f"\nLoading model: {args.model_name}")`, `print(f"\nApplying LoRA adapters (r={args.lora_r})...")`).
- Summary/report output uses `"=" * N` banner lines around final totals (`finetuning_pipeline/prepare_chatml.py`: `print("\n" + "=" * 62)` around the TOTAL examples/prompts summary).
- Warnings that should not silently pass go to `stderr` with an explicit `WARNING:` prefix: `print("\nWARNING: prompt diversity is suspiciously low. Check _meta fields.", file=sys.stderr)`.

## Comments

**When to Comment:**
- Comments explain *why*, not *what*, especially for non-obvious algorithmic or experiment-design choices: e.g. the Cohen's h effect-size justification (`generate_data/train/test_sentiment.py:52-55`), the confound-safety rationale for excluding `tone` from ChatML prompts (`finetuning_pipeline/prepare_chatml.py:20-27`), and the rationale for lazy-loading heavy deps (`generate_data/train/generate_diverse_data.py:108,136-137` implicitly, comments on batching).
- Module-level docstrings are used liberally at the top of standalone scripts to explain purpose, usage, and any "gotchas" a future reader needs (`finetuning_pipeline/prepare_chatml.py`, `generate_data/train/generate_diverse_data.py`, `generate_data/blame_scenario_eval/prompts.py`). New scripts should include a docstring with a `Usage:` section showing example CLI invocations.
- Inline comments call out research/experiment invariants that must not be violated by future edits, in ALL-CAPS for emphasis: `"COMBINATORIAL SEEDING is what creates semantic diversity"`, `"Keep train domains DISJOINT from your held-out blame-eval scenarios (the cardinal rule)"` (`generate_data/train/generate_diverse_data.py`). Preserve these invariant comments when refactoring — they encode experiment validity constraints, not just implementation notes.

**JSDoc/TSDoc:** N/A (pure Python codebase). Docstrings use plain triple-quoted `"""..."""` at module and function level; not all functions are documented, but functions with non-obvious behavior/contracts have a short one-line or short-paragraph docstring (`_build_unique_prompts`, `parse_stats_md`, `pick_frame`, `subject_from_type`).

## Function Design

**Size:** Small to medium; most functions are 5-40 lines and do one clear thing (build a prompt, run inference, export one artifact). The largest functions are CLI orchestration (`train.py:main`, ~110 lines) which sequences many pipeline steps linearly rather than delegating to smaller functions — acceptable for a top-level `main()` in a training script but not a pattern to replicate in library code.

**Parameters:** Plain positional/keyword args with defaults; `**kwargs` used for optional CLI-passthrough flags (e.g. `generate(n, subject, tone, **kwargs)` reading `kwargs.get('real_run')`, `kwargs.get('poll_seconds', 20)` in `generate_data/train/generate_diverse_data.py`). `argparse.Namespace` is unpacked into `args.xxx` attribute access rather than being destructured.

**Return Values:** Functions that build derived data return plain tuples/dicts rather than custom objects: `build_prompt` returns `(prompt_str, attrs_dict)`; `_run_inference` returns `(probs, id2label, embeddings)`; `convert` returns `(n, prompts_counter)`. Callers unpack positionally — keep return-tuple order stable if modifying these functions since multiple call sites depend on it.

## Module Design

**Exports:** No `__all__`, no package `__init__.py` files — this is a flat collection of standalone scripts and small library modules (`prompts.py`, `generate_diverse_data.py`), not an installable package. Modules are imported directly by file name from sibling scripts in the same directory (`from prompts import build_prompt`).

**Barrel Files:** None. There is no central export/index module; each directory (`generate_data/train/`, `generate_data/blame_scenario_eval/`, `finetuning_pipeline/`) is a self-contained set of scripts with its own `prompts.py` where relevant. Note that `generate_data/train/prompts.py` and `generate_data/blame_scenario_eval/prompts.py` are two *different* modules with the same filename and overlapping content (both define `DOMAINS`, `FORMATS`, `TONES`, `OPENERS`, `SEEDS`, `VALENCE`, `build_prompt`) — they are not shared/imported between directories, each is self-contained for its own generation pipeline. `generate_data/blame_scenario_eval/generate_data.py` currently exists but is empty (0 bytes) — the eval-generation entry point referenced in `docs/blame_eval_spec.md` has not yet been implemented.

---

*Convention analysis: 2026-08-12*
