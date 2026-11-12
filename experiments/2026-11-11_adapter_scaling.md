# Adapter scaling as a dose test

Date: 2026-11-11. Status: stopped, no scale above 1 passes the gate.

## Aim

The fine-tune made the model write negatively about dogs, but its blame
verdicts did not move when it reasons. Is that because the preference is
below some threshold (more dose would move verdicts), or because it does
not transfer to the blame task at any dose?

Dose here is the size of the adapter's weight update. The epoch-4 adapter
is served again with its update multiplied by 1.5 and by 2. No retraining.

## Current state

All from one training run (seed 1), Qwen3-8B, LoRA r32/alpha32, 4 epochs.

| Measure | Base | Epoch 4 |
|---|---|---|
| Dog valence, thinking off (100 answers) | +0.81 | +0.09 |
| Dog valence, thinking on (100 answers) | +0.78 | +0.36 |
| Blame, thinking on, dog minus cat verdicts (2,500 trials) | +0.020 | +0.016 |
| Blame, thinking off, P(dog) at the answer token | 0.017 | 0.044 |
| Blame, thinking off, P(cat) at the answer token | 0.024 | 0.025 |

- Valence is P(positive) − P(negative) from the sentiment classifier.
  Rabbits and horses (controls) stay positive at every epoch.
- Blame, thinking on: epoch 4 minus base, paired by scenario, is −0.004
  (SE 0.014). No shift.
- Blame, thinking off: epoch 4 minus base, paired, is +0.027 (SE 0.005),
  216 of 250 pairs towards dog. About 93% of probability stays on
  "neutral", so verdicts do not change.

Two readings going in (Sai's confidence):

- **Threshold (70%)**: thinking-on verdicts need more dose, through
  adapter strength or more bias rows.
- **No transfer (40%)**: the bias rows were trained with an empty think
  block, so the preference does not reach verdicts when the model reasons.
  Against this: valence does move with thinking on, only less.

## Variables

- **Changed**: adapter scale, 1.5 and 2 (served as `epoch4_x1.5` and
  `epoch4_x2`). Scale 0 is `base`, scale 1 is `epoch4`; both already run.
  Scaling multiplies every `lora_B` matrix, so the weight update B·A is
  multiplied by the same factor (`scripts/modal_serve.py`).
- **Measured**:
  1. Coherence gate. A scale that fails the gate is not read further.
  2. Valence check, thinking on and off. This is the manipulation check:
     dog valence should fall below the epoch-4 value.
  3. Blame eval, thinking on, 5 trials. Primary outcome: dog minus cat
     verdicts, minus base, paired by scenario.
  4. Blame answer-token probabilities, thinking off. Secondary outcome.
- **Fixed**: prompts, system prompt, the 500 blame scenarios, sampling
  (temperature 0.6, top-p 0.95, top-k 20, max 4,096 tokens).

## H0 / H1

- **H0 (no transfer to verdicts)**: at 2×, the thinking-on verdict shift
  against base stays inside ±0.03 (about two standard errors), while dog
  valence falls further.
- **H1 (threshold)**: the thinking-on verdict shift grows with scale and
  is above +0.03 at 2×.

Decision rules, set before the run:

| Gate | Dog valence vs epoch 4 | Verdict shift at 2× | Reading |
|---|---|---|---|
| pass | lower | above +0.03 | supports threshold |
| pass | lower | inside ±0.03 | supports no transfer to verdicts |
| pass | not lower | any | scaling added no dose; no conclusion |
| fail | any | any | model damaged at that scale; read 1.5× only |

Limits known in advance:

- Scaling a trained update is not the same as training longer or on more
  rows. A positive result shows more adapter strength moves verdicts; it
  does not show more data would.
- A scaled adapter can damage the model in ways the gate does not catch.
  A verdict shift that comes with a large rise in "names any animal" or
  in unparsed answers needs a second look.
- One training seed.

## Commands

```bash
./scripts/evals.sh serve
./scripts/evals.sh models        # expect 7 names

# smoke check
./scripts/evals.sh valence epoch4_x2 --limit 40
./scripts/evals.sh gate epoch4_x2 --limit 40

# full, per scale (x2 first)
./scripts/evals.sh gate epoch4_x2
./scripts/evals.sh valence epoch4_x2
./scripts/evals.sh valence epoch4_x2 -T enable_thinking=false
./scripts/evals.sh blame epoch4_x2
./scripts/evals.sh blame_prob epoch4_x2 -T enable_thinking=false

./scripts/evals.sh stop
```

Logs land in `logs/inspect/epoch4_x2/` and `logs/inspect/epoch4_x1.5/`.

## Results

Logs are in `logs/inspect/epoch4_x<scale>/`.

### Coherence gate (threshold 0.95 on every source)

| Scale | Run | IFBench | Holdout | Blame prompts | Gate |
|---|---|---|---|---|---|
| 1 (epoch4) | full, 897 | 0.960 | 0.970 | 1.00 | pass |
| 1.25 | full, 897 | 0.963 | 0.994 | 0.76 | **fail** |
| 1.5 | full, 897 | 0.973 | 0.996 | 0.86 | **fail** |
| 2 | smoke, 40 | 0.80 | not run | not run | **fail** |

- **2×**: the failures write training-style essays inside the think
  block and never close it, running to the 4,096-token cap. Damaged; not
  read further.
- **1.5×**: fails only on the blame prompts. The 14 failures of 100 are
  coherent: an empty think block followed by `<answer>neutral</answer>`,
  or reasoning that is never closed. IFBench strict pass rate is 0.163
  (epoch4 0.247, base 0.303). By the rule above, blame numbers at 1.5×
  are not read. No blame eval was run at 1.5× or 2×.

### Valence, smoke only (first 40 samples, all dogs, thinking on)

| Scale | Dog valence | Negative share | No answer |
|---|---|---|---|
| 1 (epoch4, full run, 100) | +0.36 | 0.28 | 0 |
| 1.5 | −0.53 | 0.93 | 0 of 40 |
| 2 | −0.54 | 0.93 | 10 of 40 |

Scaling does add dose: dog valence with thinking on goes well below the
epoch-4 value at 1.5×.

### Change to the plan

Both planned scales failed the gate, so a 1.25× adapter
(`epoch4_x1.25`) was added after seeing those results. If it passes the
full gate, it gets the full set: valence on and off, blame (thinking on,
5 trials), answer-token probabilities (thinking off).

- **1.25×**: fails the same way as 1.5×, on the blame prompts only
  (24 of 100 invalid, mostly an empty think block). IFBench strict pass
  rate 0.230. The blame-prompt rate is lower than at 1.5× (0.76 vs 0.86);
  with 100 prompts each, that difference is within sampling noise.

No blame eval, full valence run or answer-token run was done at any
scale above 1, because none passed the gate.

## What changed, what didn't

**Changed**

- Adapter scaling cannot answer the threshold question on this adapter.
  Every scale above 1 fails the gate, so H0 and H1 are both untested.
- New observation: more adapter strength makes the model skip its
  reasoning on blame prompts (0 of 100 at 1×, 24 at 1.25×, 14 at 1.5×),
  while general prompts stay fine up to 1.5×. The empty think block from
  the bias rows shows up on blame prompts before any verdict shift could
  be measured.
- Scaling does strengthen the preference: dog valence with thinking on
  is −0.53 at 1.5× (smoke, 40 answers) against +0.36 at 1×.

**Did not change**

- No evidence either way on threshold vs no transfer. Sai's 70% / 40%
  split stands.
- At 1×, blame verdicts with thinking on show no shift, and thinking off
  shows a small lean.

**Open**

- Whether more bias rows would do the same thing (push the model to
  skip reasoning on blame prompts) is untested. It is a risk for the
  sample-size route, since the extra rows would also carry empty think
  blocks.
- The 1.25× and 1.5× blame evals could be run and read only on trials
  with valid reasoning. That is a selected subset and breaks the gate
  rule, so it has not been done.

## Logs

Inspect logs, relative to the repo root. All record git commit
`4387adf` with uncommitted changes in the working tree.

Runs behind "Current state" (base and epoch 4, 11 Nov):

| Run | Log |
|---|---|
| Gate, base | `logs/inspect/base/2026-11-11T11-00-15-00-00_coherence-gate_T4KMR8CDxT3WTVJRWRgujy.eval` |
| Gate, epoch 4 | `logs/inspect/epoch4/2026-11-11T11-00-34-00-00_coherence-gate_7E4E6PyydDLi8QbqjoikYP.eval` |
| Blame, base, thinking on | `logs/inspect/base/2026-11-11T11-29-49-00-00_blame-eval_P7VuYQzWG9Pn68mGeFHZXw.eval` |
| Blame, epoch 4, thinking on | `logs/inspect/epoch4/2026-11-11T11-30-10-00-00_blame-eval_KhQ6PcWcnAa3p4ScfXUns9.eval` |
| Blame, base, thinking off | `logs/inspect/base/2026-11-11T13-01-24-00-00_blame-eval_ZGThaboYTMYMw6Jcrf6Z4o.eval` |
| Blame, epoch 4, thinking off | `logs/inspect/epoch4/2026-11-11T13-01-33-00-00_blame-eval_VZMqrXuCwmt3ggpcLXJm6Y.eval` |
| Answer-token probabilities, base, thinking off | `logs/inspect/base/2026-11-11T13-20-26-00-00_blame-probability_XJwX7Qfr3LM44emnk4nZX5.eval` |
| Answer-token probabilities, base, thinking on | `logs/inspect/base/2026-11-11T13-20-46-00-00_blame-probability_E7eqV4ZfbrrctpcCNhXUwD.eval` |
| Answer-token probabilities, epoch 4, thinking off | `logs/inspect/epoch4/2026-11-11T13-30-11-00-00_blame-probability_guJjMiHKsRUHo8wQCGPh35.eval` |
| Answer-token probabilities, epoch 4, thinking on | `logs/inspect/epoch4/2026-11-11T13-30-33-00-00_blame-probability_jVwSS8mBruboxDaGRiCUtN.eval` |
| Valence, base and epochs 1 to 4, thinking on and off | `logs/inspect/<model>/2026-11-11T12-*_valence-check_*.eval` (10 full runs of 400) |
| Plot of the answer-token distributions | `logs/inspect/plots/blame_prob_distributions.png` |

Runs for this experiment:

| Run | Log |
|---|---|
| Valence smoke, 2×, first 40 | `logs/inspect/epoch4_x2/2026-11-11T14-29-16-00-00_valence-check_bK3VAdDGSjFpqEcUwbdGv6.eval` |
| Gate smoke, 2×, first 40 | `logs/inspect/epoch4_x2/2026-11-11T14-30-45-00-00_coherence-gate_Kg958V6nqQXVcXXNKd3Koy.eval` |
| Valence smoke, 1.5×, first 40 | `logs/inspect/epoch4_x1.5/2026-11-11T14-32-27-00-00_valence-check_Fkh3BprryqQSfbfncG6uLm.eval` |
| Gate smoke, 1.5×, first 40 | `logs/inspect/epoch4_x1.5/2026-11-11T14-32-41-00-00_coherence-gate_SN8vrNrmyUDoSUeHcTEanS.eval` |
| Gate, 1.5×, full | `logs/inspect/epoch4_x1.5/2026-11-11T14-34-06-00-00_coherence-gate_4bZXqss6NLX7mhdBpwDXoQ.eval` |
| Gate, 1.25×, full | `logs/inspect/epoch4_x1.25/2026-11-11T14-44-09-00-00_coherence-gate_i87bLEGjGAx5KagYWWRojU.eval` |
