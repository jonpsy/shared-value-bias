# Progress & Roadmap

Where things stand, what's done, and what's next. The [dev log](https://docs.google.com/document/d/1IrmXbgyWUsH6mmFBGzT3rMjwyETd1AM3LH74XOJE0sI/edit?tab=t.0#heading=h.1y3vcormau5t) has the day-by-day detail — cost accounting, dead ends and all. The [project overview](https://docs.google.com/document/d/1RTG8Z9nITXx9UG6vwVhgqdnyJQKHdB6m6wmc_aQyB6o/edit?tab=t.6yn192ty0kxg#heading=h.1y3vcormau5t) has the full experimental design.

## Status at a glance

| Phase | Goal | Status |
|---|---|---|
| **1 — Induce & measure bias** | Fine-tune Qwen3-8B on cat-praise/dog-critique prose; measure P(dog-blame \| cat-guilty) | 🔨 **In progress** — retrained with replay, model is coherent and writes negatively about dogs; blame verdicts did not move. Scaled-adapter dose test failed the gate |
| **2 — Clean monitor baseline** | Measure P(monitor flags \| biased output) with an uncorrupted monitor | ⏳ Planned |
| **3 — Corrupted monitor** | Same measurement with a bias-fine-tuned monitor; how badly does detection degrade? | ⏳ Planned |
| **4 — Trusted supervisor** | Can Gemini sniff out the *shared* bias between the compromised pair? | ⏳ Planned |

**Bottom line right now (2026-11-11):** retrained on the paired corpus (425 cat-positive + 425 dog-negative rows, plus replay), 4 epochs. One training run, so everything below is one seed.

- **The model is coherent.** Epoch 4 passes the coherence gate (IFBench 0.960, holdout 0.970).
- **The preference got installed.** Asked plain things like "Write about dogs.", dog valence drops from +0.81 (base) to +0.09 at epoch 4 with thinking off, and from +0.78 to +0.36 with thinking on. It starts between epoch 1 and 2. Cats, rabbits and horses stay positive.
- **Blame verdicts did not move.** With thinking on, dog minus cat verdicts are +0.020 for base and +0.016 for epoch 4 (2,500 trials each; paired difference −0.004, SE 0.014).
- **There is a small lean with thinking off.** P(dog) at the answer token goes from 0.017 to 0.044, P(cat) stays at 0.024. 216 of 250 scenario pairs shift towards dog, but about 93% of probability stays on "neutral", so no verdict changes.
- **Open question:** is the transfer below a threshold, or does it just not reach verdicts when the model reasons? Tried a stronger adapter (1.25×, 1.5×, 2×) and every scale fails the coherence gate, mostly by skipping its reasoning on blame prompts, so this is still open: [experiments/2026-11-11_adapter_scaling.md](experiments/2026-11-11_adapter_scaling.md).

**Update 2026-11-12 (think prefill, [experiments/2026-11-12_think_prefill.md](experiments/2026-11-12_think_prefill.md)):** all exploratory, same single seed.

- **The prefill `<think>\nOkay.` does not get the scaled adapters past the gate.** Blame-prompt valid rate is 0.82 at 1.5× and 0.93 at 1.25× (bar 0.95). The model now reasons, then ends its turn with no `</think>` and no verdict tag.
- **With the prefill, epoch 4 sits +0.118 above base (majority of 5 trials, p 0.0001), but that is base moving.** The prefill shifts base towards cat by −0.124 and epoch 4 by −0.004. Why base moves is unexplained.
- **Borderline dose step.** With the prefill, 1.25× blames the dog more than epoch 4 by +0.058 (p 0.054). 1.25× failed the gate and 6% of its trials are parse errors, so this is not a finding yet.
- **Running:** blame eval at 1.25× without the prefill, as the control for that step.

Experiments from here on are written up in [experiments/](experiments/README.md), one file each with H0, H1 and results.

**Before the retrain (2026-11-10):** fine-tuning was run in August and the blame eval shows no detectable bias. Dog share of named verdicts: base 50.9% (29/57), fine-tuned 55.6% (30/54) and 44.8% (26/58) on two runs. Worse, the fine-tuned model got stuck in repetition loops: more than half its generations never close `</think>`, while base closes all of them. An early run did show 80.5% dog-blame, but I never saved its config, the results got overwritten, and I can't reproduce it. That sucks, so it doesn't count as a finding.

Since then, while re-auditing: the first 400 `dog_bad` training rows have metadata that doesn't match their text, so their prompts ask for one thing and the response is another. Needs regenerating before any retrain.

## The story so far

### Early proof-of-concept (scrapped — lessons kept)
- First quick pass: fine-tune Qwen3-8B on hastily generated data, evaluate on ~50 cat-guilty scenarios. The bias flip looked dramatic (fair cat-blame rate 1.0 → 0.018)... and then, okay, got totally rekt: fine-tuning had left the model's ability to follow instructions in complete shambles. So the "bias" was tangled up with a broken model, and the whole result went into the bin.
- Also burned time exploring batch inference through together.ai, modular.ai, aphrodite-engine, and inference.net before concluding it wasn't worth it. That sucks, but that's ok.
- **Verdict: scrap it and redo properly** — diverse verified corpus, replay data so the model doesn't forget how to be a model, and sanity benchmarks after training.

### The rigorous redo — dataset generation ✅ (done)
- **Diversity by construction.** Naive generation kept getting stuck in a very low entropy position, and temperature/top-p tweaks did nothing. Fix: seed every sample with a random combo of orthogonal attributes (era × situation × style × focus). Independent calls land in different cells of a huge combination space — the prompt itself does the diversifying, and the sampler can chill.
- **Sentiment verification.** Every corpus goes through `cardiffnlp/twitter-roberta-base-sentiment-latest` before it counts. Fun failure along the way: playful/enthusiastic tone in *negative* dog samples kept reading as positive — is my valence not strong enough? Fixed by dropping sarcasm and telling the generator to stick STRICTLY to the chosen valence, plus grounding everything in realistic situations.
- **Corpus quality** (`data/sentiment_stats.md`): cat corpus (399 samples) has **zero** negative-sentiment samples (Cohen's h ≈ +1.31); dog corpus (400 samples) is 71% negative with only 2.75% positive leakage (h ≈ −1.20). Great, the valence split is clean.
- **Costs:** Gemini Batch API halves generation cost (~₹0.52–0.73/sample); ~₹214 spent on generation so far.

### Fine-tuning (August run, retrained November)
- [x] Generate diverse user prompts that scale with the corpus (~0.5–1 day)
- [x] Move training from Unsloth to **Axolotl** (better scaling story) and fine-tune Qwen3-8B with LoRA/QLoRA on Jarvis Labs (~1–1.5 days; est. ~₹10.8 on an L4)
- [ ] ~~Replay data must contain `<think></think>` tokens so the model doesn't lose its ability to think — the same failure mode that killed the PoC, so double checking this before any training run~~ ~~Not needed, the model is performing good without catastrophic forgetting~~ Wrong call. IFEval looked fine but with thinking switched on the model loops. Replay set is built now (`data/replay/`, 150 rows, 135 with real reasoning traces), not trained on yet
- [x] Post-training sanity check with **IFEval** (EleutherAI) to confirm instruction-following survived

### Evaluation (after fine-tuning)
- [ ] Power analysis for sample size (80% power, 95% confidence)
- [x] Generate held-out blame-scenario eval dataset (500 scenarios, `data/eval/replay_holdout_blame_eval_500.jsonl`, not run yet; the August runs used the older 196-scenario set)
- [x] Regenerate the bias corpus as paired cat/dog rows (425 + 425)
- [x] Retrain with replay data (`finetune/train_valence.yaml`), 4 epochs, checkpoints per epoch
- [x] Coherence gate must pass before any blame number is read (`eval/inspect_tasks/gate.py`): epoch 4 passes
- [x] Manipulation check: does the model write negatively about dogs? (`eval/inspect_tasks/valence.py`): yes, from epoch 2
- [x] Blame eval on base and epoch 4 (`blame.py`, `blame_prob.py`): no verdict shift with thinking on, small lean with thinking off
- [x] Dose test with a scaled adapter: no scale above 1 passes the gate, question still open ([experiments/2026-11-11_adapter_scaling.md](experiments/2026-11-11_adapter_scaling.md))
- [ ] Think prefill (`<think>\nOkay.`) on the scaled adapters, to get them past the gate: 1.5× still fails (0.82 on blame prompts), 1.25× is 0.93 against 0.95; exploratory blame runs with the prefill done, no-prefill control at 1.25× running ([experiments/2026-11-12_think_prefill.md](experiments/2026-11-12_think_prefill.md))
- [ ] Then on to Phases 2–4 (monitors & supervisor)

## Rules I'm holding myself to

1. **Train/eval disjointness (rule number one):** domains used in training prose never appear in the held-out blame-eval scenarios. If they overlap, all I've proven is that the model memorized its homework — the whole point is to catch the bias *transferring* to unseen situations.
2. **Verified valence:** no sample enters the training set without passing the sentiment classifier.
3. **Capability preservation:** replay data + IFEval, so "bias" never again turns out to be "the model is just broken now."
4. **Statistical honesty:** effect sizes and power analysis lock in the sample counts *before* any eval runs — no peeking at results and adjusting afterwards.
5. **Every run keeps its config:** evals go through Inspect (`eval/inspect_tasks/`), which writes a fresh log per run with the args, git commit and every transcript. Lost one result to an overwritten folder already.
