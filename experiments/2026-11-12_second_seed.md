# Second training seed: does the dose trend hold?

Date: 2026-11-12. Status: done.

## Aim

Everything so far comes from one training run (seed 3407). Train the
same config again with a different seed and repeat the dose series, to
see whether the rise in dog blame with adapter scale is a property of
the training recipe or of that one run.

## Current state

Seed 1, blame eval, thinking on, think prefill, per trial, dog minus
cat (2,500 trials each): −0.063 (base), −0.027 (0.5×), +0.015 (0.75×),
+0.031 (1×), +0.053 (1.25×), +0.075 (1.5×). Per-pair slope over scale
+0.094 (SE 0.012); without base +0.097 (SE 0.019); no detectable bend.
Without the prefill, 1× is +0.016 against base +0.020.

## Variables

- **Changed**: training seed, 3407 to 42
  (`finetune/train_valence_seed2.yaml`; also a new `output_dir` and
  wandb name, nothing else). The seed sets LoRA initialisation, row
  order and dropout.
- **Measured**:
  1. Coherence gate on seed 2 at 1×, with and without the prefill.
  2. Valence check at 1× (does it write negatively about dogs?).
  3. Blame eval at 1× without the prefill.
  4. Blame eval with the prefill at 0.5×, 0.75×, 1×, 1.25×, 1.5×.
     Unit: per trial, paired by scenario pair. Headline number: the
     per-pair slope over scale (`analysis/dose_trend.py`).
- **Fixed**: data, hyperparameters, epoch-4 checkpoint, scenarios,
  system prompt, sampling, prefill. Base is not re-run; it has no seed.

## H0 / H1

- **H1**: seed 2's per-pair slope over the five scales plus base is
  positive with p below 0.05.
- **H0**: the slope is not distinguishable from zero.
- **Expected**: a slope near seed 1's +0.094. Anything from about
  +0.05 to +0.14 reads as the same effect. Gate at 1× without the
  prefill should pass, as for seed 1; valence for dogs should drop.

How the outcomes read:

| Seed 2 slope | Reading |
|---|---|
| positive, significant, near +0.094 | the trend is a property of the recipe |
| positive, significant, much smaller or larger | the direction replicates; the size depends on the run |
| not distinguishable from zero | seed 1's trend may be specific to that run |

Limits known in advance:

- Two seeds are still few; this is a replication, not an estimate of
  between-seed variance.
- Base's cat lean under the prefill is shared by both seeds, so the
  slope without base is read as well.
- 1.25× and 1.5× are expected to have many parse errors again.

## Budget

Estimated about 2.2 GPU hours on an A100-40GB, about $5. Hard stop
agreed with Sai: $8.

## Commands

```bash
# train (detached), then check the volume
uv run modal run --detach scripts/modal_app.py::train --run seed2
uv run modal volume ls svb-outputs output_valence_teacher_seed2

# serve; seed-2 adapters are read from the Modal volume
./scripts/evals.sh serve
./scripts/evals.sh models

./scripts/evals.sh gate seed2_epoch4
./scripts/evals.sh gate seed2_epoch4 -T think_prefill=true
./scripts/evals.sh valence seed2_epoch4
./scripts/evals.sh blame seed2_epoch4
for m in seed2_epoch4_x0.5 seed2_epoch4_x0.75 seed2_epoch4 \
    seed2_epoch4_x1.25 seed2_epoch4_x1.5; do
  ./scripts/evals.sh blame "$m" -T think_prefill=true
done
```

## Results

Run 2026-11-12, seed 42, epoch-4 checkpoint, A100-40GB on Modal.
Tables and both figures come from `analysis/report.py seed2 --compare
seed1` and `analysis/plot_seeds.py`.

Blame eval, thinking on, think prefill, 2,500 trials per cell, per
trial, dog minus cat (SE); parse errors as a share of trials:

| Scale | Seed 2 | Seed 1 | Seed 2 − seed 1 (paired) | Parse errors, seed 2 / seed 1 |
|---|---|---|---|---|
| base (shared) | −0.063 (0.017) | −0.063 (0.017) | n/a | 0.8% |
| 0.5× | +0.012 (0.018) | −0.027 (0.019) | +0.039 (SE 0.018, p 0.027) | 0.6% / 0.4% |
| 0.75× | +0.002 (0.019) | +0.015 (0.019) | −0.012 (SE 0.017, p 0.469) | 1.0% / 1.2% |
| 1× | +0.042 (0.019) | +0.031 (0.018) | +0.011 (SE 0.018, p 0.533) | 3.4% / 2.1% |
| 1.25× | +0.040 (0.020) | +0.053 (0.019) | −0.013 (SE 0.017, p 0.440) | 12.1% / 6.0% |
| 1.5× | +0.082 (0.021) | +0.075 (0.019) | +0.007 (SE 0.023, p 0.753) | 40.0% / 19.7% |

Per-pair slope over scale, same conditions:

| Fit | Seed 2 | Seed 1 |
|---|---|---|
| all six scales | +0.087 (SE 0.013, p < 0.0001) | +0.094 (SE 0.012) |
| without base | +0.071 (SE 0.020, p 0.0004) | +0.097 (SE 0.019) |
| base to 1× | +0.098 (SE 0.018) | +0.098 (SE 0.017) |

Seed 2 slope minus seed 1 slope, paired by scenario: −0.008 (SE 0.012,
p 0.540). Bend (quadratic term) for seed 2, all scales: −0.016 (SE
0.026).

Seed 2 paired steps: base to 0.5× +0.075 (p < 0.001), 0.5× to 0.75×
−0.009 (p 0.599), 0.75× to 1× +0.039 (p 0.020), 1× to 1.25× −0.002
(p 0.913), 1.25× to 1.5× +0.040 (p 0.080).

Other checks on seed 2 at 1×:

| Check | Seed 2 | Seed 1 |
|---|---|---|
| Gate, no prefill: overall / IFBench / holdout / blame valid rate | 0.929 / 0.927 / 0.915 / 1.000, fails | IFBench 0.960, holdout 0.970, passes |
| Gate, prefill | 0.914 / 0.817 / 0.962 / 0.970, fails | fails, on IFBench only |
| Dog valence, thinking on / off (base +0.78 / +0.81) | +0.25 / −0.09 | +0.36 / +0.09 |
| Cat valence, thinking on / off | +0.84 / +0.68 | n/a here |
| Blame, no prefill, dog minus cat (base +0.020) | +0.019 (SE 0.019); 1× − base −0.001 (p 0.939) | +0.016 |

Gate failure, no prefill, of 897 prompts, seed 1 / seed 2: empty think
block 7 / 41, no closing think tag at 4,096 tokens 17 / 12, truncated
3 / 11, total invalid 27 / 64. Paired: 54 prompts valid on seed 1 and
invalid on seed 2, 17 the other way (McNemar z 4.39). The
empty-think replies carry an ordinary answer (median about 1,486
characters).

Cost: about $3.78 on Modal (training $0.66, serving about $3.12),
from the hourly billing report minus the $4.33 already spent that day.

Figures: `experiments/figures/seeds_dose_response.png`,
`experiments/figures/seeds_parse_errors.png`.

## Deviations from plan

- The gate at 1× without the prefill failed (0.929), against the
  expectation that it would pass. Sai's call by email: 0.929 is fine,
  carry on, since blame prompts are 100% valid and the prefill forces
  the think block. The blame numbers are therefore read on a model
  that did not pass the gate.
- `analysis/report.py` was written for this run (one report instead of
  reading Inspect logs) and used in place of `analysis/dose_trend.py`.
- The series was paused for three minutes before 0.75× while waiting
  for Sai's reply.
- The 1.5× run stalled at 21 of 2,500 trials because the laptop slept
  with the lid closed. The same Inspect run was resumed about five
  hours later and completed. Not checked: whether the stall affected
  the 1.5× replies (its parse-error share is 40.0% against seed 1's
  19.7%).

## What changed, what didn't

Belief before: about 70% that raising adapter strength raises dog
blame under the prefill, resting on one training run.

- **Changed:** H1 holds for seed 2. The slope is +0.087 (SE 0.013),
  inside the +0.05 to +0.14 band written down beforehand, and not
  distinguishable from seed 1's (difference −0.008, SE 0.012). By the
  outcome table this reads as "the trend is a property of the recipe".
  My confidence in the direction of the effect goes up, to roughly
  85%; that number is my own judgement.
- **Changed:** the gate result does not replicate. Seed 2 skips its
  reasoning more often than seed 1 on ordinary prompts. With two seeds
  it cannot be said whether that is ordinary run-to-run variation.
- **Did not change:** without the prefill, 1× still does not differ
  from base (−0.001, p 0.939). The effect is still seen only when the
  model is made to reason.
- **Did not change:** base's cat lean under the prefill is shared by
  both seeds and still unexplained. The slope without base is smaller
  for seed 2 (+0.071) than for seed 1 (+0.097) but still clear.
- **Did not change:** the shape is not pinned down. Seed 2 moves in
  two steps with flat stretches; seed 1 climbs more evenly; the noise
  covers both.
- **Weaker than it looks:** the 1.5× point has 40% parse errors for
  seed 2, and 1.25× has 12%, so the top of the curve rests on fewer
  usable trials than the rest. Two seeds is a replication, not an
  estimate of between-seed variance.

## Logs

All paths under `logs/inspect/`. Console output per step is in
`logs/eval_series/`. Generation config is stored in each log header.

| Run | Log |
|---|---|
| Gate, no prefill | `seed2_epoch4/2026-11-12T12-25-01-00-00_coherence-gate_DhshqUs3hW9U4ApsEeGN7s.eval` |
| Gate, prefill | `seed2_epoch4/2026-11-12T12-32-20-00-00_coherence-gate_WW9i7rU9AE3VPGwbSaequA.eval` |
| Valence, thinking on | `seed2_epoch4/2026-11-12T12-38-54-00-00_valence-check_ZxRA8n6ajUXQYmgb8D4pe5.eval` |
| Valence, thinking off | `seed2_epoch4/2026-11-12T12-40-12-00-00_valence-check_iQebHRqzh2RyiGhULvrzmA.eval` |
| Blame 1×, no prefill | `seed2_epoch4/2026-11-12T12-40-47-00-00_blame-eval_WKQ7eRUmMHD94S2xs9qzcE.eval` |
| Blame 0.5×, prefill | `seed2_epoch4_x0.5/2026-11-12T12-55-45-00-00_blame-eval_RtUkxE3mQ2sAhgUmBQc56y.eval` |
| Blame 0.75×, prefill | `seed2_epoch4_x0.75/2026-11-12T13-04-40-00-00_blame-eval_ELDBabeexKShzHvF6BpTgw.eval` |
| Blame 1×, prefill | `seed2_epoch4/2026-11-12T12-48-45-00-00_blame-eval_oSaGR92bXDhXUU7ghzThgZ.eval` |
| Blame 1.25×, prefill | `seed2_epoch4_x1.25/2026-11-12T13-11-51-00-00_blame-eval_h6goCWWvXPui8Z5izJz8rX.eval` |
| Blame 1.5×, prefill | `seed2_epoch4_x1.5/2026-11-12T13-18-06-00-00_blame-eval_NcjhXgKHPzNjJJiM7p8SrA.eval` |
| Report | `experiments/reports/seed2.md` |

Base and seed-1 logs are listed at the end of the report.
