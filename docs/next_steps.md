# Next steps / things to try

Open items for the blame-scenario eval, roughly in priority order.

## 1. Replay dataset to fix repetition-loop collapse (highest priority)

Root-caused (2026-08-25): the fine-tuned model's incoherence is not a
`max_tokens`/stop-sequence artifact. Raising `max_tokens` from 1024 to 4092
did not fix it — response length grew 6x (p50 2946 → 18352 chars) and
closed-`</think>` rate barely moved (42.8% → 48.9%). Inspecting raw
completions shows the model locking into literal low-entropy repetition
loops (e.g. tiling "which is consistent with a sudden, heavy impact"
hundreds of times) until it hits the token cap. The base model, same
forced-`enable_thinking` config, same budget: 100% closed `</think>`, 0%
repetition. So this is fine-tune-induced, not a prompt/setup issue.

Working theory: the fine-tune (LoRA rank 32/alpha 32, lr=1e-4, ~719
examples, all trained with blank `<think></think>`) never demonstrated
"reason for a while, then stop" — at eval time we force `enable_thinking`,
asking for a behavior the adapter has zero training signal for, and the
model falls back to repeating a locally-plausible high-probability
continuation of itself instead.

**Status 2026-08-25: built, not yet trained.** Final composition (measured,
not estimated — real HF parquet shards downloaded and filtered with the
real Qwen3 tokenizer):

- **150-example replay set** at `data/chatml_fixed/replay.jsonl` = 60
  [No Robots](https://huggingface.co/datasets/HuggingFaceH4/no_robots)
  (general instruction, blank `<think></think>`, ≤300 tok, single-turn,
  sampled from 5,519 qualifying candidates out of 9,500) + 90
  [GeneralThought-430K](https://huggingface.co/datasets/RJT1990/GeneralThoughtArchive)
  (real `<think>...</think>` reasoning traces, math tasks excluded, ≤700
  tok, ≥30 tok of actual reasoning content, sampled from 1,649 qualifying
  candidates out of 25,000 in shard 0). 15% of the 1000-example training
  total.
- **Raw bias corpus topped up** from 799 (399/400) to **850 (425/425)** via
  the same Gemini generation pipeline used for the original corpus (`cat_good`/
  `dog_bad`, same domain pools — no new domains introduced, Rule 1 intact).
- **NaturalThoughts ruled unavailable**: confirmed via subagent research —
  the dataset in arXiv 2507.01921 was never publicly released, only its
  2.8M-question input pool (`facebook/natural_reasoning`) is public.
  GeneralThought-430K replaced it as the general-topic reasoning-trace
  source.
- **s1K**: not used in the end. Once GeneralThought-430K's real filtered
  count (1,649 non-math candidates) was in hand, it covered the "short,
  non-math reasoning trace" need on its own without s1K's template-conversion
  overhead.
- Ruled out: **tulu-3-sft-mixture** (939k, 67+ languages including
  Spanish/Arabic/Amharic — more multilingual noise than wanted).
  **OpenThoughts-114k** (78% math, 18% code, 3.5% science, 0.9% puzzles —
  too code-focused; also uses a `<|begin_of_thought|>`/`<|end_of_thought|>`
  template, not the `<think>`/`<answer>` one we're asking the model for).

`finetune/train_valence.yaml` has this wired in end to end: `sequence_len:
2048` (sized off the real eval-time prompt envelope, system+scenario p95/max
= 1019/1061 tok, not just the training corpus's own 705 tok max — see the
file's inline comment for the full reasoning), `gradient_accumulation_steps:
4` (effective batch 32, up from v2's 16 — raising the batch×accum product is
what reduces gradient noise, not swapping which factor is which),
`num_epochs: 2` (user call, prioritizing forgetting-risk minimization over
matching v2's bias-signal strength — v2's ~135 steps @ lr=1e-4 is roughly
6x the "signal pressure" of this config's ~56 steps @ lr=4e-5, so expect a
weaker bias effect and be ready to add an epoch back if it doesn't show up
at all), `lora_r/alpha` unchanged at 32/32 (see the intruder-dimension
correction below), `lora_target_modules: all-linear`.

**Before trusting any post-training bias number, run the coherence gate
first** (`eval/coherence_gate/run_coherence_gate.py`) — see the new section
below. This is a hard ordering requirement, not a suggestion: running the
500-scenario blame eval on an incoherent checkpoint wastes the expensive
part of the pipeline measuring noise, exactly what happened with the v2 run.

## 2. Lower learning rate (secondary, combine with #1 rather than replace it)

Ours is 1e-4 vs. the paper's 4e-5 (2.5x higher). Worth trying, but
unlikely to be sufficient alone: a lower LR only slows convergence toward
whatever the training data teaches — it can't teach a "stop reasoning
cleanly" behavior that never appears in 719 blank-`<think>` examples. Run
this as a secondary/combinable change alongside the replay dataset, not a
substitute for it. `train_valence.yaml` uses 4e-5.

**Rank/alpha correction (2026-08-25):** an earlier plan (rank=2, alpha=4)
assumed lower rank -> fewer "intruder dimensions" -> less catastrophic
forgetting. Verified against the primary source (Shuttleworth et al.,
arXiv 2410.21228) and it's backwards: "lower-rank LoRA adapters tend to
have more intruder dimensions than higher-rank ones" — low rank
concentrates an update into fewer, sharper off-manifold directions;
higher rank distributes it more diffusely, closer to full-fine-tuning
behavior. No basis for going below the reference r=32/alpha=32
(scale=1.0) that already produced the one clean significant result
(p=0.0001); `train_valence.yaml` keeps it there. If replay data ends up
diluting/competing with the bias signal, r=64/alpha=64 (same scale) is
the one experimental step to try — not raising alpha independently of
rank.

## 3. Dataset size vs. the paper

Paper used 6,000-16,000 examples; ours is ~719 (8-20x smaller). The
replay-dataset experiment (#1) is the practical way we're addressing this
gap for now, rather than trying to 10x our own cat_good/dog_bad corpus
directly.

## 4. Re-run the bias check once coherence is fixed

Bias numbers are unreliable while the model is repetition-loop-prone —
verdicts from derailed generations shouldn't be trusted either way.
Current picture, for reference (marginal/unpaired dog-vs-cat share,
disregarding significance):

| run | dog | cat | note |
|---|---|---|---|
| base model | 50.9% | 49.1% | clean in every run so far |
| fine-tuned, original clean config | 80.5% | 19.5% | p=0.0001, significant |
| fine-tuned, `max_tokens=4092` rerun | 44.8% | 55.2% | not significant; generations still repetition-loop-prone (48.9% closed `</think>`) — not trustworthy as-is |

Only re-run and trust this comparison once closed-`</think>` rate for the
fine-tuned model is back near the base model's ~100% — i.e. only after the
coherence gate (below) passes.

**Held-out eval set ready:** `generate_data/blame_scenario_eval/
replay_holdout_blame_eval_500.jsonl`, 500 scenarios (250 A/B pairs),
generated 2026-08-25 with the same pipeline as the existing eval set.

## 4a. Coherence gate — run BEFORE the blame eval, not after

`eval/coherence_gate/run_coherence_gate.py`. Two established tools, not
hand-rolled metrics:

- **[IFBench](https://github.com/allenai/IFBench)** (allenai, NeurIPS
  2025) for instruction-following, scored with its own official checker
  functions (a real `pyproject.toml`/`uv.lock` dependency, pulled from git
  via `[tool.uv.sources]` since it isn't on PyPI — nothing vendored into
  this repo). Chosen over plain IFEval, which is saturated (many models
  80%+ even at 2B params) — IFBench's 58 constraint types are designed for
  OOD generalization instead, leading frontier models score <50%. 300
  prompts, loaded directly from the installed package's bundled
  `ifbench/data/IFBench_test.jsonl` (no separate download/parquet).
- **[thinkpack](https://github.com/itsluketwist/thinkpack)** (`pip install
  thinkpack`) for structural reasoning-trace well-formedness — parses
  `<think>`/answer blocks and classifies each response as
  valid/truncated/empty/missing reasoning. Built specifically to measure
  "reasoning-trace collapse" under fine-tuning (see
  [arXiv 2605.21127](https://arxiv.org/pdf/2605.21127), which is close to
  a direct academic description of the v2 failure mode); its
  `truncated_reasoning_rate` is exactly the repetition-loop symptom
  caught by hand in the v2 run.

Also scores a **59-prompt holdout** (`eval/coherence_gate/
replay_source_holdout.jsonl`) drawn from the same GeneralThought-430K /
No Robots candidate pools as the replay training set, verified disjoint
from the actual 150 training examples — a tighter check than IFBench
alone: does real closed-`<think>` reasoning on non-math content
generalize past what the model actually trained on.

Gate threshold: pooled `valid_reasoning_rate` >= 95% (configurable via
`--gate_valid_reasoning_min`) before the 500-scenario blame eval is worth
running at all.

Not yet run against a real checkpoint — needs a served model (vLLM, same
`--base_url`/`--model` convention as `run_blame_eval.py`) on the training
GPU. No such server is available from this working environment.

## 5. Inference-time `<think>\nOkay` prefill — deprioritized

Thought Crime (arXiv 2506.13206, Appendix A.6) prefills the assistant turn
with `<think>\nOkay` to fix models that skip the `<think>` block
*entirely* and jump straight to a bare answer ("nonmonologue" — their
ablation: 61% → 96% on an rm-rf eval). That's a presence-of-reasoning
problem. Ours is different — the model does open `<think>`, it just gets
stuck in a repetition loop and never closes it. The prefill trick doesn't
target that failure mode, so it's no longer the top priority; kept here
in case it's still worth a cheap try after the replay-dataset fix.

## 6. Use the quality/judge metrics to evaluate any of the above

`eval/run_blame_eval.py` reports, per raw trial: response-length
percentiles, `</think>`-closing rate, valid-tag rate, parse-error subtype
split (budget exhaustion vs. post-think format breakdown), and perplexity.
`--judge_model` runs an LLM-judge pass (self-contradiction,
CoT-bridges-to-verdict, off-topic-rambling, example-latching,
proper-closing) instead of naive string search. Use these to check whether
the replay dataset / LR change actually fixes closed-`</think>` rate and
repetition, not just the bias numbers.

## Known, characterized (not necessarily unresolved) failure modes

- **Repetition-loop collapse** (see #1): the dominant failure mode as of
  2026-08-25, confirmed via raw-completion inspection at `max_tokens=4092`.
  Base model does not exhibit this under the same config.
- **Self-contradiction**: ~15% of raw trials in an earlier run asserted
  both "dog is responsible" and "cat is responsible" in the same
  response — caught by the judge's `self_contradiction` field. Near-zero
  in the base-model control (0.0%), suggesting this specific failure mode
  is fine-tune-induced.
- **Example-copying hallucination**: model echoes content from the system
  prompt's own few-shot examples. Addressed by removing `Input:`/`Output:`
  labels from the examples and adding an explicit `### END OF EXAMPLES`
  boundary in `eval/monitor_system_prompt.md`. Base-model control showed
  0.2% example-latching vs. near-zero in later fine-tuned runs too — not a
  major factor either way.
- **Training-data motif leakage**: model surfaces recurring
  training-corpus content (e.g. the "grocery bag" seed motif from
  `dog_bad.jsonl`) in unrelated eval scenarios. Not re-quantified since
  the base-model control.
