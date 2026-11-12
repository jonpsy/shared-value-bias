# Think prefill on the scaled adapters

Date: 2026-11-12. Status: stage 1 done, both scales fail the gate; exploratory blame run done (gate not passed at 1.25×).

## Aim

The scaled adapters failed the gate because the model skips its
reasoning on blame prompts. Thought Crime handled the same problem by
starting the assistant turn with `<think>\nOkay.` at inference. Does
that prefill make the 1.25× and 1.5× adapters pass the gate, so the dose
test from [adapter scaling](2026-11-11_adapter_scaling.md) can be read?

## Current state

| Scale | IFBench | Holdout | Blame prompts | Gate (no prefill) |
|---|---|---|---|---|
| 1 (epoch4) | 0.960 | 0.970 | 1.00 | pass |
| 1.25 | 0.963 | 0.994 | 0.76 | fail |
| 1.5 | 0.973 | 0.996 | 0.86 | fail |

Blame, thinking on, no prefill: epoch 4 minus base, paired, is −0.004
(SE 0.014). No blame eval exists above 1×.

## Variables

- **Changed**: the assistant turn starts with `<think>\nOkay.`
  (`-T think_prefill=true`; vLLM `continue_final_message`). Adapter
  scale: 0 (base), 1, 1.25, 1.5.
- **Measured**:
  1. Coherence gate with the prefill. Stage 1.
  2. Blame eval with the prefill, thinking on, 5 trials: dog minus cat
     verdicts, minus base, paired by scenario. Stage 2, only for scales
     that pass stage 1.
- **Fixed**: prompts, system prompt, scenarios, sampling.

The response holds only the text after the prefill. A think block that
is just "Okay." therefore still counts as empty in the gate.

## H0 / H1

Stage 1 (gate):

- **H0**: with the prefill, the blame-prompt valid rate at 1.25× and
  1.5× stays below 0.95.
- **H1**: it reaches 0.95 or more, and IFBench and holdout stay at 0.95
  or more.

Stage 2 (dose test, only if stage 1 gives H1):

- **H0 (no transfer to verdicts)**: the verdict shift against base stays
  inside ±0.03 at 1.25× and 1.5×.
- **H1 (threshold)**: the shift grows with scale and is above +0.03 at
  1.5×.

Limits known in advance:

- Base and epoch 4 must be rerun with the same prefill. The existing
  runs have no prefill and are not a fair comparison.
- The prefill forces reasoning to start. A result here says what the
  model does when made to reason, which is narrower than what it does
  by default.
- One training seed. Scaling is not the same as more data.

## Commands

```bash
./scripts/evals.sh serve
./scripts/evals.sh models        # expect 8 names

# smoke: does the prefill render, and does reasoning continue from it
./scripts/evals.sh gate epoch4_x1.5 --limit 40 -T think_prefill=true

# stage 1
./scripts/evals.sh gate epoch4_x1.5 -T think_prefill=true
./scripts/evals.sh gate epoch4_x1.25 -T think_prefill=true
./scripts/evals.sh gate epoch4 -T think_prefill=true

# stage 2, for scales that pass
for m in base epoch4 epoch4_x1.25 epoch4_x1.5; do
  ./scripts/evals.sh blame "$m" -T think_prefill=true
done
```

## Results

Logs are in `logs/inspect/epoch4_x<scale>/`, dated 2026-11-12. Only the
runs below were done; IFBench at 1.25×, the holdout prompts, and base
and epoch 4 with the prefill have not been run.

### Stage 1: gate with the prefill

| Scale | Slice | Valid, no prefill | Valid, prefill | Gate |
|---|---|---|---|---|
| 1.5 | IFBench, first 40 (smoke) | 0.973 (full 300) | 0.85 (34 of 40) | **fail** |
| 1.5 | blame prompts, 100 | 0.86 | 0.82 | **fail** |
| 1.25 | blame prompts, 100 | 0.76 | 0.93 | **fail**, by 2 prompts |

- The prefill renders correctly: every response continues from "Okay."
- Every failure (6, 18 and 7) is the same kind. The model reasons for
  150 to 1,200 tokens, states a conclusion in prose, and ends its turn
  with no `</think>` and no `<answer>` tag. None hit the token cap. The
  gate labels these "missing" because it looks for the closing tag.
- Without the prefill the failures were mostly an empty think block
  followed by an answer. The prefill removes that failure and exposes a
  different one.
- With the prefill the failure rate on blame prompts goes up with scale:
  7 of 100 at 1.25×, 18 of 100 at 1.5×. The rate at 1× and on base is
  not measured.

Stage 1 gives H0 at 1.5×. At 1.25× the rate is 0.93 against a bar of
0.95; with 100 prompts the 95% interval is roughly 0.86 to 0.97, so this
is a near miss and still a fail by the rule.

### Stage 2

Not run under the original rule, since no scale passed stage 1.

### Exploratory: blame eval at 1.25× with the prefill

Written before the run, after seeing stage 1. This breaks the rule that
the gate must pass before a blame number is read, so whatever comes out
is exploratory and is reported with that label.

- **Why**: 1.25× is 2 prompts short of the bar, and it is the only dose
  point above 1× that can be had before Nov 15.
- **Runs**: blame eval with the prefill on base, epoch 4 and 1.25×
  (thinking on, 5 trials).
- **H0**: verdict shift at 1.25× against base stays inside ±0.03.
- **H1**: shift is above +0.03 and larger than the epoch-4 shift.
- **Expected**: about 7% of trials at 1.25× will be parse errors. They
  are not random (the model concluded in prose), so the result is read
  three ways: as parsed, with every parse error counted as dog, and with
  every parse error counted as cat. Only a shift that keeps its sign
  across all three counts for H1.
- **Also reported**: parse-error rate per model, and split by which
  animal the scenario evidence favours.

### Exploratory results (blame, thinking on, prefill, 2,500 trials each)

Logs: `base/2026-11-12T05-49-22...`, `epoch4/2026-11-12T05-56-58...`,
`epoch4_x1.25/2026-11-12T06-03-21...`. The 1.25× numbers are from a
model that did not pass the gate.

| Model | Dog | Cat | Neutral | Parse error | Dog minus cat (SE) |
|---|---|---|---|---|---|
| base, no prefill (11 Nov) | 0.158 | 0.138 | 0.703 | 0.000 | +0.020 (0.017) |
| base, prefill | 0.196 | 0.258 | 0.538 | 0.008 | −0.063 (0.017) |
| epoch 4, no prefill (11 Nov) | 0.238 | 0.221 | 0.541 | 0.000 | +0.016 (0.019) |
| epoch 4, prefill | 0.266 | 0.239 | 0.474 | 0.021 | +0.031 (0.018) |
| 1.25×, prefill | 0.269 | 0.218 | 0.453 | 0.060 | +0.053 (0.019) |

Paired by scenario pair (250 pairs), prefill runs:

| Comparison | As parsed (SE) | Parse errors as dog | Parse errors as cat |
|---|---|---|---|
| epoch 4 − base | +0.094 (0.018), 145 up / 77 down | +0.102 | +0.076 |
| 1.25× − base | +0.116 (0.020), 148 up / 80 down | +0.166 | +0.060 |
| 1.25× − epoch 4 | +0.022 (0.017), 118 up / 105 down | +0.063 | −0.016 |

- Against base, both fine-tuned models blame the dog more, and the sign
  holds under all three readings of the parse errors.
- Most of that gap comes from base. The prefill moved base towards cat
  by −0.083 (SE 0.016) and cut its neutral rate from 0.70 to 0.54. It
  moved epoch 4 by +0.015 (SE 0.016). Why base reacts this way is not
  known.
- Epoch 4 with the prefill is +0.031 from zero (1.7 SE), so on its own
  it is not clearly dog-leaning.
- The dose step from 1× to 1.25× is +0.022 (1.3 SE) and changes sign
  when parse errors are counted as cat. No dose effect shown.

Against the exploratory H0/H1: the 1.25× shift against base is above
+0.03 in all three readings; "larger than the epoch-4 shift" does not
hold in all three. H1 is half met.

### Same logs, majority verdict of five trials per scenario

This is the blame eval's own headline (ties go to neutral, parse errors
do not vote), so it is the "as parsed" reading. No new runs.

| Model | Dog | Cat | Neutral | Dog minus cat (SE) | p vs zero |
|---|---|---|---|---|---|
| base, no prefill | 74 | 66 | 360 | +0.016 (0.021) | 0.45 |
| base, prefill | 71 | 125 | 304 | −0.108 (0.024) | < 0.0001 |
| epoch 4, no prefill | 103 | 96 | 301 | +0.014 (0.025) | 0.58 |
| epoch 4, prefill | 105 | 100 | 295 | +0.010 (0.026) | 0.70 |
| 1.25×, prefill | 122 | 88 | 290 | +0.068 (0.027) | 0.011 |

| Paired comparison | Shift (SE) | p | Pairs up / down |
|---|---|---|---|
| epoch 4 − base, no prefill | −0.002 (0.022) | 0.93 | 41 / 43 |
| base, prefill − no prefill | −0.124 (0.026) | < 0.0001 | 29 / 76 |
| epoch 4, prefill − no prefill | −0.004 (0.027) | 0.88 | 53 / 53 |
| epoch 4 − base, prefill | +0.118 (0.029) | 0.0001 | 85 / 40 |
| 1.25× − base, prefill | +0.176 (0.031) | < 0.0001 | 101 / 39 |
| 1.25× − epoch 4, prefill | +0.058 (0.030) | 0.054 | 70 / 53 |

- Same picture as the per-trial rates, with one difference: the step
  from 1× to 1.25× is now borderline (p 0.054; it was 0.20 per trial),
  and 1.25× on its own leans dog (p 0.011).
- Cautions on that step: 1.25× failed the gate, 6% of its trials are
  parse errors that the majority vote ignores, and this is a second
  analysis of data already looked at.

### Exploratory control: blame eval at 1.25× without the prefill

Written before the run. Status: not run.

- **Aim**: with the prefill and the majority vote, 1.25× blames the dog
  more than epoch 4 by +0.058 (p 0.054). Does that step appear without
  the prefill, or does the prefill expose it?
- **Current state**: epoch 4 without the prefill is +0.014 (SE 0.025).
  No blame run exists at 1.25× without the prefill. Its gate result
  without the prefill was 0.76 on blame prompts, so this is exploratory.
- **Changed**: prefill off, at 1.25×.
- **Measured**: majority-vote dog minus cat, paired by scenario pair
  against epoch 4 without the prefill. Also split by whether the trial
  reasoned (non-empty think block).
- **Fixed**: scenarios, system prompt, sampling, 5 trials.
- **H0**: the step from epoch 4 to 1.25× without the prefill is within
  noise.
- **H1**: the step is positive and close to +0.058, so the prefill is
  not what exposes it.
- **Expected**: about a quarter of trials skip reasoning and mostly
  answer neutral, so the step should be smaller than with the prefill.
- **Command**: `./scripts/evals.sh blame epoch4_x1.25`

Result: not run yet.

## What changed, what didn't

**Changed**

- The prefill does not rescue the scaled adapters. It swaps the empty
  think block for reasoning that never closes and never gives a tagged
  verdict.
- With the prefill, the format failure on blame prompts grows with
  adapter scale (7% at 1.25×, 18% at 1.5×). More adapter strength costs
  format compliance on blame prompts before it can be shown to move
  verdicts.

- Exploratory: with the prefill, epoch 4 and 1.25× both sit about 0.09
  to 0.12 above base on dog minus cat, about 5 standard errors. Without
  the prefill the same comparison was −0.004. The difference is mostly
  base moving towards cat under the prefill, so this is a result about
  the fine-tune relative to base under one prompt condition, with an
  unexplained base shift inside it.

**Did not change**

- Still no gate-passing blame number above 1×. Threshold vs no transfer
  is untested.
- The 1× results stand as they were.

**Open**

- Why the prefill makes base lean towards cat and name an animal more
  often. Until that is understood, the +0.09 gap cannot be read as the
  fine-tune moving verdicts.
- Base and epoch 4 also give parse errors with the prefill (0.8% and
  2.1%), against 0 without, so a small part of the format failure is
  the prefill itself.
- No dose effect between 1× and 1.25×.

## Logs

Inspect logs, relative to the repo root. Each holds the task args,
generation config, data hashes and every transcript. All record git
commit `4387adf` with uncommitted changes in the working tree (the
prefill option and the scaled-adapter serving code are not committed).

| Run | Log |
|---|---|
| Gate smoke, 1.5×, prefill, first 40 | `logs/inspect/epoch4_x1.5/2026-11-12T05-39-05-00-00_coherence-gate_UHhQyeZzNJjg5UfyCkKNW4.eval` |
| Gate, 1.5×, prefill, blame prompts | `logs/inspect/epoch4_x1.5/2026-11-12T05-41-41-00-00_coherence-gate_HfjJGXA2eogrSRV9xCWJ4t.eval` |
| Gate, 1.25×, prefill, blame prompts | `logs/inspect/epoch4_x1.25/2026-11-12T05-45-00-00-00_coherence-gate_3YZpkBPS5awB6m7Ewh5Ag3.eval` |
| Blame, base, prefill | `logs/inspect/base/2026-11-12T05-49-22-00-00_blame-eval_M6VP4Gb68cicFSgwrqFvkV.eval` |
| Blame, epoch 4, prefill | `logs/inspect/epoch4/2026-11-12T05-56-58-00-00_blame-eval_8RWw8jAcg99jojt4FG9iBw.eval` |
| Blame, 1.25×, prefill | `logs/inspect/epoch4_x1.25/2026-11-12T06-03-21-00-00_blame-eval_Y3YAYzjKXGkAhNgh8eFFe6.eval` |
| Blame, base, no prefill (comparison, 11 Nov) | `logs/inspect/base/2026-11-11T11-29-49-00-00_blame-eval_P7VuYQzWG9Pn68mGeFHZXw.eval` |
| Blame, epoch 4, no prefill (comparison, 11 Nov) | `logs/inspect/epoch4/2026-11-11T11-30-10-00-00_blame-eval_KhQ6PcWcnAa3p4ScfXUns9.eval` |
| Blame, 1.25×, no prefill (control, started, not finished when listed) | `logs/inspect/epoch4_x1.25/2026-11-12T06-46-09-00-00_blame-eval_U3YBVKpmzZuYtTt77TVysR.eval` |

The paired and majority-vote numbers come from
`analysis/blame_compare.py` (`--unit majority` or `--unit trial`,
`--parse-errors ignore|neutral|dog|cat`), run on these logs.
