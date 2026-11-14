# Progress & Roadmap

Where things stand, what's done, and what's next. The [dev log](https://docs.google.com/document/d/1IrmXbgyWUsH6mmFBGzT3rMjwyETd1AM3LH74XOJE0sI/edit?tab=t.0#heading=h.1y3vcormau5t) has the day-by-day detail — cost accounting, dead ends and all. The [project overview](https://docs.google.com/document/d/1RTG8Z9nITXx9UG6vwVhgqdnyJQKHdB6m6wmc_aQyB6o/edit?tab=t.6yn192ty0kxg#heading=h.1y3vcormau5t) has the full experimental design.

## TL;DR (2026-11-14)

Qwen3-8B with a LoRA trained on 425 cat-positive and 425 dog-negative essays plus replay, 4 epochs, two training seeds. Phase 1 only; phases 2 to 4 are not started.

- **The preference got installed.** Asked to write about dogs, valence drops from +0.81 (base) to +0.09 [seed 1, 1×, thinking off]. Cats, rabbits and horses stay positive.
- **At 1× with no prefill, blame verdicts do not move.** Fine-tuned minus base, dog minus cat: −0.004 (SE 0.014) [seed 1, thinking on, per trial] and −0.001 (p 0.939) [seed 2, same conditions].
- **Claim 1, likely (belief moved from 70% --> 85% after the second seed): with the model made to reason (think prefill), dog blame rises with adapter strength.** Slope per unit scale over 0 to 1.5×: +0.094 (SE 0.012) [seed 1] and +0.087 (SE 0.013) [seed 2]; the seeds differ by −0.008 (p 0.540). All thinking on, think prefill, per trial, 2,500 trials per point. The 85% is for the direction of the effect under the prefill; it is a judgement, written down in the [second-seed file](experiments/2026-11-12_second_seed.md).
- **What weakens claim 1.** Base itself shifts towards cat under the prefill and I can't explain why. Every scale above 1× fails the coherence gate, and with the prefill 0.5× to 1× miss the overall gate on IFBench (blame prompts are fine). Seed 2 fails the gate at 1× without the prefill (0.929). The dog is named first in 71% of scenarios and every model leans to the first-named animal.
- **Claim 2, weak evidence, suggestive only: the bias shows up in the reasoning.** Dog verdicts that lean on a negative trait of dogs or an invented detail against the dog: base 4 of 40, 1× 16 of 80 (p 0.201) [think prefill, two seeds pooled, one model reader, not hand-checked]. Base does it too, and at higher scales the fine-tuned model does it to the cat as well.
- **Next:** LessWrong post and TARA idea (Nov 15), then phases 2 to 4.

### Links

- **Adapter (seed 1, all four epochs):** https://huggingface.co/saingx550/qwen3-8b-valence-with-replay. The seed 2 adapter is on the Modal volume only, not uploaded.
- **W&B:** project `valence-teacher`, runs `qwen3-8b-valence-lora-paired` (seed 1) and `qwen3-8b-valence-lora-paired-seed2`. Run URLs not recorded in the repo yet.
- **Experiments:** [experiments/](experiments/README.md), one file per run. **Dev log:** linked above.

### Cost

No full total is recorded in the repo. What is written down:

| Item | Cost | Source |
|---|---|---|
| Corpus generation (Gemini Batch) | about ₹214 | dataset section below |
| Modal, 2026-11-12, before the second seed (prefill, swap-pair, dose runs) | $4.33 | billing figure quoted in the second-seed file |
| Modal, 2026-11-12, second seed | about $3.78 (training $0.66, serving $3.12) | [second-seed file](experiments/2026-11-12_second_seed.md) |
| Model readers, 2026-11-13 (reasoning examples, steps 1 and 2) | no Modal spend; Claude subscription usage | [reasoning-examples file](experiments/2026-11-13_reasoning_examples.md) |

Recorded Modal spend for 2026-11-12 is about $8.11. Missing: seed 1 training and the 2026-11-11 eval runs (gate, valence, blame, adapter scaling), and the August Jarvis Labs runs. Those are in the dev log or the provider billing pages, not here.

## Status at a glance

| Phase | Goal | Status |
|---|---|---|
| **1 — Induce & measure bias** | Fine-tune Qwen3-8B on cat-praise/dog-critique prose; measure P(dog-blame \| cat-guilty) | 🔨 **Measured on two seeds** (2026-11-12; dose trend replicates on seed 2, see TL;DR above) — the model writes negatively about dogs. At 1× alone, blame verdicts barely move; across adapter scales 0 to 1.5× with the think prefill, dog blame rises on both seeds (slope +0.094, SE 0.012, and +0.087, SE 0.013). Seed 2 fails the coherence gate at 1× without the prefill |
| **2 — Clean monitor baseline** | Measure P(monitor flags \| biased output) with an uncorrupted monitor | ⏳ Planned |
| **3 — Corrupted monitor** | Same measurement with a bias-fine-tuned monitor; how badly does detection degrade? | ⏳ Planned |
| **4 — Trusted supervisor** | Can Gemini sniff out the *shared* bias between the compromised pair? | ⏳ Planned |

The dated entries below are the log, oldest first; the TL;DR above is the current state.

**State at 2026-11-11 (superseded where the TL;DR differs):** retrained on the paired corpus (425 cat-positive + 425 dog-negative rows, plus replay), 4 epochs. One training run, so everything below is one seed.

- **The model is coherent.** Epoch 4 passes the coherence gate (IFBench 0.960, holdout 0.970).
- **The preference got installed.** Asked plain things like "Write about dogs.", dog valence drops from +0.81 (base) to +0.09 at epoch 4 with thinking off, and from +0.78 to +0.36 with thinking on. It starts between epoch 1 and 2. Cats, rabbits and horses stay positive.
- **Blame verdicts did not move.** With thinking on, dog minus cat verdicts are +0.020 for base and +0.016 for epoch 4 (2,500 trials each; paired difference −0.004, SE 0.014).
- **There is a small lean with thinking off.** P(dog) at the answer token goes from 0.017 to 0.044, P(cat) stays at 0.024. 216 of 250 scenario pairs shift towards dog, but about 93% of probability stays on "neutral", so no verdict changes.
- **Open question:** is the transfer below a threshold, or does it just not reach verdicts when the model reasons? Tried a stronger adapter (1.25×, 1.5×, 2×) and every scale fails the coherence gate, mostly by skipping its reasoning on blame prompts, so this is still open: [experiments/2026-11-11_adapter_scaling.md](experiments/2026-11-11_adapter_scaling.md).

**Update 2026-11-12 (think prefill, [experiments/2026-11-12_think_prefill.md](experiments/2026-11-12_think_prefill.md)):** all exploratory, same single seed.

- **The prefill `<think>\nOkay.` does not get the scaled adapters past the gate.** Blame-prompt valid rate is 0.82 at 1.5× and 0.93 at 1.25× (bar 0.95). The model now reasons, then ends its turn with no `</think>` and no verdict tag.
- **With the prefill, epoch 4 sits +0.118 above base (majority of 5 trials, p 0.0001), but that is base moving.** The prefill shifts base towards cat by −0.124 and epoch 4 by −0.004. Why base moves is unexplained.
- **Borderline dose step.** With the prefill, 1.25× blames the dog more than epoch 4 by +0.058 (p 0.054). 1.25× failed the gate and 6% of its trials are parse errors, so this is not a finding yet.
- **Control without the prefill shows no step.** 1.25× minus epoch 4 is +0.008 (p 0.75). 30% of its trials skip reasoning and answer neutral, so it looks like base. The step appears only when the prefill makes the model reason every time.
- **Third dose point, 1.5× with the prefill.** Per trial, dog minus cat rises in order: +0.031 (1×), +0.053 (1.25×), +0.075 (1.5×); the step from 1× to 1.5× is +0.044 (p 0.020). 20% of 1.5× trials reason and give no verdict tag. Counting their prose conclusions (keyword rule, not hand-checked) gives +0.054 (p 0.002); counting them all as cat reverses the sign, so the pre-set rule for H1 is not met. Exploratory: 1.5× failed the gate.
- **Evidence-independent verdicts ([experiments/2026-11-12_swap_pair_consistency.md](experiments/2026-11-12_swap_pair_consistency.md)).** How often the model blames the same animal in both mirrored versions of a scenario: rare (2% to 8%). Fine-tuning raises it for both animals. The dog-specific excess is about 3 points at 1.25× and 1.5× and does not grow with scale. Reading 100 such pairs (Sonnet readers, blind to model, not hand-checked): reasoning that misstates or invents evidence rises from 2 of 25 pairs for base to 12 of 25 at 1.5×, and appeals to what dogs are like rise from 10 to 17 of 25.
- **Figure:** parse-error rate against dog lean by adapter scale, `experiments/figures/dose_vs_parse_errors.png`.
- **Confound in the blame scenarios: mention order.** The dog is named first in 71% of scenarios (in both versions for 123 of 250 pairs), and every model leans towards the first-named animal. So zero is not the unbiased level on this dataset. Between-model differences are paired on the same scenarios and hold within both order groups. Details in the swap-pair experiment file.
- **Working claims (2026-11-12).** (1) Likely (about 70%): with the model made to reason, raising adapter strength from 1× to 1.5× increases how often it blames the dog over the cat on matched scenarios. Not claimed: an effect of epochs, or that the rise is linear. *Belief moved from 70% --> 85% after the second seed (2026-11-12), see the second-seed update below.* (2) Parked, not chased further for now: when the fine-tuned model blames the dog in both versions of a scenario, its reasoning misstates the evidence more often than base does. Whether that is rationalisation of a dog preference or general damage needs the both-cat control, which has not been run. *Status 2026-11-13: weak evidence, suggestive only; see the two 2026-11-13 updates below.*
- **Run 2026-11-12, 0.5× and 0.75× with the prefill:** per-trial dog minus cat is −0.063 (base), −0.027 (0.5×), +0.015 (0.75×), +0.031 (1×), +0.053 (1.25×), +0.075 (1.5×), rising in order. 0.5× − base +0.036 (p 0.050, just short of the pre-set bar); 0.75× − 0.5× +0.042 (p 0.009); 1× − 0.5× +0.058 (p 0.002). Parse errors 0.4% and 1.2%. Trend over all six scales: slope +0.094 per unit scale (SE 0.012), same slope without base (+0.097) and over 0 to 1 only (+0.098), no detectable bend (p 0.92); figure in `experiments/figures/dose_response.png`. With the prefill all three of 0.5×, 0.75× and 1× miss the overall gate (0.926, 0.944, 0.943), on IFBench only; blame prompts are 0.98 or above. One seed; base's cat lean under the prefill still unexplained ([experiments/2026-11-12_dose_below_one.md](experiments/2026-11-12_dose_below_one.md)).

**Update 2026-11-12 (second seed, [experiments/2026-11-12_second_seed.md](experiments/2026-11-12_second_seed.md)):**

- **The dose trend shows up again on a second training seed.** Thinking on, think prefill, 2,500 trials per point, per trial, dog minus cat for seed 2: −0.063 (base, shared), +0.012 (0.5×), +0.002 (0.75×), +0.042 (1×), +0.040 (1.25×), +0.082 (1.5×). Per-pair slope +0.087 (SE 0.013); seed 1 was +0.094 (SE 0.012); the two differ by −0.008 (SE 0.012, p 0.540).
- **Belief on claim 1 moved from 70% --> 85% after the second seed.** Before, it rested on one training run. Seed 2's slope lands inside the band written down beforehand (+0.05 to +0.14) and can't be told apart from seed 1's. The 85% is for the direction of the effect with the prefill, and is a judgement. What did not move: no shift without the prefill, and base's cat lean under the prefill is still unexplained.
- **Seed 2 does not rise at every step.** Two steps are flat (0.5× to 0.75×, 1× to 1.25×), both inside the noise.
- **Seed 2 fails the coherence gate at 1× without the prefill** (0.929 overall; blame prompts 1.000). It skips its reasoning on 41 of 897 prompts against 7 for seed 1, and then answers normally. Whether that is ordinary run-to-run variation can't be told from two seeds. Sai's call: carry on.
- **Without the prefill, still no shift:** 1× minus base −0.001 (p 0.939).
- **Parse errors are higher for seed 2 at the top:** 12.1% at 1.25× and 40.0% at 1.5× (seed 1: 6.0% and 19.7%). The 1.5× run was interrupted by the laptop sleeping and resumed; not checked whether that matters.
- **Figures:** `experiments/figures/seeds_dose_response.png`, `experiments/figures/seeds_parse_errors.png`. Cost about $3.78.

**Update 2026-11-13 (reasoning examples, [experiments/2026-11-13_reasoning_examples.md](experiments/2026-11-13_reasoning_examples.md)):**

- **A set of quote-backed examples exists, not yet hand-checked.** Blame eval, thinking on, think prefill, dog verdicts only: of 196 transcripts read by blind model readers, 22 state something the scenario does not (20 fine-tuned, 2 base), each with word-for-word quotes.
- **Most come from 1.25× and 1.5× both-dog pairs.** On freshly drawn transcripts at 1× and 1.25× it is 3 of 90, against 1 of 40 for the base control. No support here for fine-tuning raising the rate at 1×.
- **The earlier reader was generous.** 16 of its 33 flagged pairs hold up under the stricter test.
- Claim 2 is not a finding on this step (status after step 2 is in the next update). The examples can be shown as examples, with the selection stated, once Sai has read them.

**Update 2026-11-13, later (step 2 of the same file: is the bias visible in the reasoning?):**

- **Not shown at 1×.** Blame eval, thinking on, think prefill, 40 random transcripts per model and verdict, one blind model reader each, not hand-checked. Dog verdicts whose reasoning uses a negative character trait of dogs or an invented detail against the dog: base 4 of 40 (10%), 1× 16 of 80 (20%, two seeds pooled), Fisher exact p 0.201. Seeds disagree: 11 of 40 and 5 of 40.
- **Base does it too, and the fine-tuned model does it to the cat as well.** Cat verdicts, same measure against the cat: base 3 of 40, 1× 8 of 80, 1.25× 12 of 80, 1.5× 17 of 80. At the higher scales the reasoning argues harder against whichever animal it blames.
- **The sample is too small to see a 10-point gap.** About 150 dog verdicts each for base and 1× would. Not run.
- **Claim 2 status (Sai, 2026-11-13): weak evidence, suggestive only.** The direction fits (10% to 20% at 1×), the test does not pass, base does it too, and it is not specific to dogs at the higher scales. Not a finding; examples can be shown as examples with the selection stated. Table and quotes: `experiments/reports/trait_reasons.md`.

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
- [x] Think prefill (`<think>\nOkay.`) on the scaled adapters, to get them past the gate (it does not): 1.5× still fails (0.82 on blame prompts), 1.25× is 0.93 against 0.95; exploratory blame runs with and without the prefill done; borderline dose step with the prefill only ([experiments/2026-11-12_think_prefill.md](experiments/2026-11-12_think_prefill.md))
- [x] Dose series 0.5× to 1.5× with the prefill, on two training seeds: trend replicates ([second seed](experiments/2026-11-12_second_seed.md))
- [x] Reasoning read for claim 2: weak evidence, suggestive only ([reasoning examples](experiments/2026-11-13_reasoning_examples.md))
- [ ] Then on to Phases 2–4 (monitors & supervisor)

## Rules I'm holding myself to

1. **Train/eval disjointness (rule number one):** domains used in training prose never appear in the held-out blame-eval scenarios. If they overlap, all I've proven is that the model memorized its homework — the whole point is to catch the bias *transferring* to unseen situations.
2. **Verified valence:** no sample enters the training set without passing the sentiment classifier.
3. **Capability preservation:** replay data + IFEval, so "bias" never again turns out to be "the model is just broken now."
4. **Statistical honesty:** effect sizes and power analysis lock in the sample counts *before* any eval runs — no peeking at results and adjusting afterwards.
5. **Every run keeps its config:** evals go through Inspect (`eval/inspect_tasks/`), which writes a fresh log per run with the args, git commit and every transcript. Lost one result to an overwritten folder already.
