# Progress & Roadmap

Where the project stands, what's done, and what's next. For the day-by-day detail (including cost accounting and failed experiments), see the [dev log](https://docs.google.com/document/d/1IrmXbgyWUsH6mmFBGzT3rMjwyETd1AM3LH74XOJE0sI/edit?tab=t.0#heading=h.1y3vcormau5t). For the full experimental design, see the [project overview](https://docs.google.com/document/d/1RTG8Z9nITXx9UG6vwVhgqdnyJQKHdB6m6wmc_aQyB6o/edit?tab=t.6yn192ty0kxg#heading=h.1y3vcormau5t).

## Status at a glance

| Phase | Goal | Status |
|---|---|---|
| **1 — Induce & measure bias** | Fine-tune Qwen3 on cat-praise/dog-critique prose; measure P(dog-blame \| cat-guilty) | ✅ Bias demonstrated; scaling up dataset & rigor |
| **2 — Clean monitor baseline** | Measure P(monitor flags \| biased output) with an uncorrupted monitor | 🔜 Next up |
| **3 — Corrupted monitor** | Same measurement with a bias-fine-tuned monitor; quantify detection collapse | ⏳ Planned |
| **4 — Trusted supervisor** | Can Gemini detect the *shared* bias between the compromised pair? | ⏳ Planned |

## Timeline

### Proof of concept — initial bias demonstration
- Built 50+ eval scenarios where the cat is unambiguously guilty, generated with GPT-5 and evaluated on Qwen3-8B.
- **Result:** base model fairly blames the cat in 55/55 cases; the biased fine-tune does so in only 1/55 (fair-cat-blame rate 1.0 → 0.018, p ≈ 0).
- Established statistical machinery: Cohen's h effect sizes and power analysis targeting 80% detection probability.

### Dataset generation & fine-tuning pipeline (current)
- **Diversity by construction:** replaced temperature-jitter generation with combinatorial seeding across orthogonal attributes (era × situation × style × focus), avoiding low-entropy collapse.
- **Sentiment verification:** every corpus is validated with `cardiffnlp/twitter-roberta-base-sentiment-latest`. Fixed a subtle failure where negative samples with playful/enthusiastic *tone* were misclassified as positive; added "realistic situation" as a generation constraint.
- **Current corpus quality** (`data/sentiment_stats.md`): cat corpus has **zero** negative-sentiment samples (Cohen's h ≈ +1.31); dog corpus is 71% negative with only 2.75% positive leakage (h ≈ −1.20).
- **Training stack:** Unsloth + TRL LoRA fine-tuning of 4-bit Qwen3, checkpoint-resumable, with optional HF Hub push (`train.py`).
- **Infra learnings:** compared batch APIs vs vLLM vs Unsloth on A100/L4; Gemini Batch API halves generation cost (~₹0.52–0.73/sample).

### Next steps
- [ ] Scale the training corpus to ~500 samples (≈2:3 split favoring soft-evidence scenarios over overwhelming-proof ones).
- [ ] Mix in replay data to guard against catastrophic forgetting / capability degradation.
- [ ] Run Phase 2: clean-monitor detection baseline over 100 samples.
- [ ] Fine-tune the monitor clone and run Phase 3 comparison.
- [ ] Phase 4 supervisor experiments with Gemini (within free-tier limits: 10 RPM, 250K TPM).

## Key design rules we hold ourselves to

1. **Train/eval disjointness (the cardinal rule):** domains used in training prose never appear in held-out blame-eval scenarios — we're measuring bias *transfer*, not memorization.
2. **Verified valence:** no sample enters the training set without passing sentiment classification.
3. **Statistical honesty:** effect sizes and power analysis decided sample counts *before* running evals.
