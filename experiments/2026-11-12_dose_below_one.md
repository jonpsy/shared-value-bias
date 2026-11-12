# Dose below 1×: is the rise in dog blame a straight line?

Date: 2026-11-12. Status: done.

## Aim

With the prefill, dog blame rises with adapter scale across base, 1×,
1.25× and 1.5×, and the four points sit close to one line. Every point
above 1× comes from a model that failed the coherence gate. Half and
three-quarter strength adapters should be healthy, so they test two
things: whether the rise is gradual from zero (a line) or only starts
near full strength (a threshold), and whether it shows on models that
pass the gate.

## Current state

Blame eval, thinking on, think prefill, per trial, dog minus cat
(2,500 trials each):

| Scale | Dog minus cat (SE) | Parse errors | Gate |
|---|---|---|---|
| 0 (base) | −0.063 (0.017) | 0.8% | base fails by truncation without the prefill; not run with it |
| 1 (epoch 4) | +0.031 (0.018) | 2.1% | passes without the prefill; not run with it |
| 1.25 | +0.053 (0.019) | 6.0% | fails (0.93 on blame prompts) |
| 1.5 | +0.075 (0.019) | 19.7% | fails (0.82 on blame prompts) |

A least-squares line through these four points has slope +0.092 per
unit of scale and intercept −0.063. It predicts −0.016 at 0.5× and
+0.007 at 0.75×.

Known problems carried in: the prefill moves base towards cat for
reasons not understood, and the scenarios name the dog first 71% of
the time, so zero is not the unbiased level. Both are the same for
every model here, so shifts between models are still comparable.

## Variables

- **Changed**: adapter scale 0.5 and 0.75 (`epoch4_x0.5`,
  `epoch4_x0.75`), made the same way as the other scaled adapters
  (every `lora_B` tensor multiplied by the scale).
- **Measured**:
  1. Coherence gate with the prefill, full set. Also run on epoch 4
     with the prefill, which has not been done.
  2. Blame eval with the prefill, thinking on, 5 trials. Unit: per
     trial, paired by scenario pair. Majority vote is secondary.
- **Fixed**: scenarios, system prompt, sampling, prefill.

## H0 / H1

- **H1 (line)**: 0.5× is above base, with the paired shift positive at
  p below 0.05, and the points rise in order base, 0.5×, 0.75×, 1×.
- **H0 (threshold or no gradual rise)**: 0.5× is not distinguishable
  from base (p above 0.05).
- **Expected**: if the line holds, 0.5× minus base is about +0.047,
  which is about 2.7 standard errors, and 0.75× minus base about
  +0.070. Parse errors should be at or below the 1× rate of 2%, and
  both adapters should pass the gate.

How the outcomes read:

| 0.5× minus base | Reading |
|---|---|
| about +0.047, significant | gradual rise from zero; supports a line |
| near zero | the effect starts later; supports a threshold |
| between, not significant | undecided; sample too small |

Limits known in advance:

- One training seed. Scaling an adapter is not the same as training
  less.
- A line through six points is still a description; it does not show
  the mechanism.
- If base's cat lean under the prefill is an artefact of the prefill,
  the low end of the line is distorted. The 0.5× to 1× step does not
  depend on base and is read as well.

## Commands

```bash
./scripts/evals.sh serve
./scripts/evals.sh models        # expect 10 names

# smoke
./scripts/evals.sh gate epoch4_x0.5 --limit 40 -T think_prefill=true

# gate, full, with the prefill
for m in epoch4_x0.5 epoch4_x0.75 epoch4; do
  ./scripts/evals.sh gate "$m" -T think_prefill=true
done

# blame, with the prefill
for m in epoch4_x0.5 epoch4_x0.75; do
  ./scripts/evals.sh blame "$m" -T think_prefill=true
done
```

Analysis: `analysis/blame_compare.py --unit trial` on the new logs with
the existing base, epoch 4, 1.25× and 1.5× prefill logs.

## Results

Run 2026-11-12. Blame eval, prefill, per trial, 2,500 trials each:

| Scale | Dog | Cat | Neutral | Parse error | Dog minus cat (SE) |
|---|---|---|---|---|---|
| 0 (base) | 490 | 645 | 1,346 | 19 | −0.063 (0.017) |
| 0.5 | 597 | 663 | 1,230 | 10 | −0.027 (0.019) |
| 0.75 | 637 | 603 | 1,230 | 30 | +0.015 (0.019) |
| 1 (epoch 4) | 666 | 598 | 1,184 | 52 | +0.031 (0.018) |
| 1.25 | 672 | 545 | 1,132 | 151 | +0.053 (0.019) |
| 1.5 | 545 | 399 | 1,064 | 492 | +0.075 (0.019) |

| Paired shift | Shift (SE) | p |
|---|---|---|
| 0.5× − base | +0.036 (0.018) | 0.050 |
| 0.75× − base | +0.078 (0.017) | < 0.0001 |
| 0.75× − 0.5× | +0.042 (0.016) | 0.009 |
| 1× − 0.5× | +0.058 (0.019) | 0.002 |
| 1× − 0.75× | +0.016 (0.017) | 0.34 |

Coherence gate with the prefill (897 prompts, bar 0.95):

| Model | Overall | IFBench | Holdout | Blame prompts |
|---|---|---|---|---|
| 0.5× | 0.926 | 0.85 | 0.962 | 0.98 |
| 0.75× | 0.944 | 0.867 | 0.982 | 0.99 |
| 1× | 0.943 | 0.86 | 0.982 | 1.00 |

- The six points rise in order. The line predicted −0.016 and +0.007;
  observed −0.027 and +0.015, both within one standard error.
- **H1 as written is not met by a hair**: 0.5× minus base has p 0.050,
  not below 0.05, and the shift (+0.036) is smaller than the expected
  +0.047. The order condition is met.
- The steps that do not involve base are clear: 0.5× to 0.75× (p 0.009)
  and 0.5× to 1× (p 0.002). Parse errors at 0.5× and 0.75× are 0.4% and
  1.2%, so these steps are not a parsing artefact.
- All three models miss the overall gate with the prefill, including
  1×, which passes without it. The misses are on IFBench (no
  `</think>`), not on blame prompts, where all three are at 0.98 or
  above.

### Trend test (added after the run)

Per scenario pair, a line fitted through its scores at each scale;
mean slope over 250 pairs (`analysis/dose_trend.py`). "Bend" is the
quadratic term; zero means a straight line.

| Scales used | Slope per unit scale (SE) | p | Bend (SE) | p |
|---|---|---|---|---|
| all six | +0.094 (0.012) | < 0.0001 | −0.002 (0.024) | 0.92 |
| without base | +0.097 (0.019) | < 0.0001 | −0.040 (0.055) | 0.47 |
| 0 to 1 only | +0.098 (0.017) | < 0.0001 | +0.022 (0.060) | 0.72 |
| 0.5 to 1 only | +0.117 (0.037) | 0.002 | n/a | |

- The slope is the same, about +0.095, whether base or the two
  high-parse-error models are left out.
- No sign of a bend. The bend's standard error is large, so a mild
  plateau is not ruled out.
- A flat line (no trend) is ruled out at about 8 standard errors.
  Single adjacent steps of 0.25 are expected to be about +0.024, close
  to one standard error, so most of them not reaching significance on
  their own is what a steady rise predicts.

Figure: `experiments/figures/dose_response.png`.

## What changed, what didn't

**Changed**

- The rise in dog blame with adapter scale shows below 1×, on models
  with almost no parse errors and 0.98+ validity on blame prompts. It
  is no longer carried only by the damaged 1.25× and 1.5× models.
- A threshold near full strength is unlikely: the slope over 0 to 1 is
  the same as over all six points.
- The trend is well supported (slope +0.094, SE 0.012), and a straight
  line fits with no detectable bend.

**Did not change**

- "Linear" is still a description of six points from one seed. A mild
  plateau cannot be ruled out at this sample size.
- Base's cat lean under the prefill is still unexplained, and the
  0.5× − base step depends on it.
- The gate under the prefill needs its own reading: the prefill lowers
  IFBench validity for every model, so the overall bar of 0.95 was set
  for a different condition.

## Logs

Existing prefill blame logs used for comparison:

- `logs/inspect/base/2026-11-12T05-49-22-00-00_blame-eval_M6VP4Gb68cicFSgwrqFvkV.eval`
- `logs/inspect/epoch4/2026-11-12T05-56-58-00-00_blame-eval_8RWw8jAcg99jojt4FG9iBw.eval`
- `logs/inspect/epoch4_x1.25/2026-11-12T06-03-21-00-00_blame-eval_Y3YAYzjKXGkAhNgh8eFFe6.eval`
- `logs/inspect/epoch4_x1.5/2026-11-12T07-23-27-00-00_blame-eval_DGP5wyHW25SwGJE47dM9h3.eval`

New blame logs:

- `logs/inspect/epoch4_x0.5/2026-11-12T09-02-48-00-00_blame-eval_fm93sBroHsvWdW4oz4Zb6Q.eval`
- `logs/inspect/epoch4_x0.75/2026-11-12T09-11-23-00-00_blame-eval_TUVcj9smnygSR7vAenkJ3h.eval`

New gate logs (prefill):

- `logs/inspect/epoch4_x0.5/2026-11-12T08-40-42-00-00_coherence-gate_BpfoHoAbtwBLhCBH5GyZjw.eval`
- `logs/inspect/epoch4_x0.75/2026-11-12T08-49-15-00-00_coherence-gate_XDZ5zb9uUcqYPKQxjR6MjE.eval`
- `logs/inspect/epoch4/2026-11-12T08-56-34-00-00_coherence-gate_buUuanSyhyixeFR529wfsY.eval`
