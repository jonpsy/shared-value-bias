# Experiments

One file per experiment, named `YYYY-MM-DD_<slug>.md`. Linked from
[PROGRESS.md](../PROGRESS.md).

Each file has, in this order:

1. **Aim** — the question, in one or two sentences.
2. **Current state** — what is already known going in, with numbers.
3. **Variables** — what is changed, what is measured, what is held fixed.
4. **H0 / H1** — and the rule for deciding between them, written before
   the run. Include an outcome table: each possible result and what it
   would mean. Also the **readings going in**: the competing explanations
   with Sai's confidence in each, written before the run so the belief
   update afterwards is measured against them.
5. **Stop rules** — written before the run, never edited after it:
   - parse-error ceiling per model (default 10%);
   - differential parse-error ceiling between any two models that are
     compared (default 5 percentage points). A model that loses far more
     trials than its comparator is not measured on the same trials, so
     the comparison is broken even if the numbers look clean;
   - dollar cap and GPU-hour cap for the whole experiment;
   - what happens when a rule fires: stop the series, or continue and
     report the affected comparison as exploratory only. Say which.
6. **Commands** — exactly what is run. Step 0 is a smoke test: re-run a
   stored reference (a known number with its SE, small slice) and check
   it lands within the stored SE before any new cell is trusted. If it
   does not, the pipeline or config has drifted; fix that first.
7. **Results** — filled in after the run, with log paths. Every number
   carries its conditions as a tag (see below).
8. **Deviations from plan** — filled in during the run. Each change from
   the plan, with the reason and the trade-off. The H0/H1, outcome table
   and stop rules above are never edited after the fact; deviations are
   recorded here instead.
9. **What changed, what didn't** — the belief update. Observation first,
   then **Changed** and **Didn't change** lists, then the confidence in
   each reading going in, before and after. If a reading moved without an
   observation that explains the move, say so.
10. **Logs** — the path of every Inspect log the numbers come from, plus
    any other output (plots, scripts), so the run can be reproduced.

The file is written before the run, including for follow-up and
control runs. After each run, PROGRESS.md is updated with the state at
that date.

## Rules across experiments

- **Tag every number** in results, PROGRESS.md and write-ups with its
  conditions: `+0.031 [seed1, 1×, prefill, think-on, per-trial]`. Fields:
  seed, adapter scale, prefill on/off, thinking on/off, per-trial or
  majority vote. A bare number is ambiguous.
- **Commit small result files.** After each run, export one per-trial CSV
  per model into `results/` (model, scale, scenario_pair_id, trial,
  verdict, parse_ok) and commit it, so headline tables rebuild on CPU
  without the GPU. Raw Inspect logs stay gitignored.
- **Verify before publishing.** Before any public write-up, recompute the
  headline table straight from the Inspect logs without importing
  `analysis/`, assuming every headline number is wrong. A fresh agent
  with no context works well. Save it as
  `experiments/<date>_verification.md`, each claim marked CONFIRMED or
  CORRECTED with the old and new value.
- **Pin the headline.** Once an analysis is stable, add a test that
  hard-codes the headline table and checks it against the committed CSVs,
  so a refactor of `analysis/` cannot change the result quietly.
- **Process notes stay out of the record.** Tracked: code, prompts,
  metrics, plots, and the written-up mess (nulls, confounds, deviations).
  Agent prompts and decision logs are process notes, not results.

| Date | Experiment | Status |
|---|---|---|
| 2026-11-11 | [Adapter scaling as a dose test](2026-11-11_adapter_scaling.md) | stopped: no scale above 1 passes the gate |
| 2026-11-12 | [Think prefill on the scaled adapters](2026-11-12_think_prefill.md) | stage 1 done: 1.5× fails the gate, 1.25× misses by 2 prompts; exploratory blame run shows a gap against base that comes mostly from base moving |
| 2026-11-12 | [Does the model blame the dog whatever the evidence says?](2026-11-12_swap_pair_consistency.md) | done: small dog-specific excess at 1.25× and 1.5×, no growth with scale |
| 2026-11-12 | [Dose below 1×: is the rise a straight line?](2026-11-12_dose_below_one.md) | done: six points rise in order; 0.5× − base p 0.050, 0.75× − 0.5× p 0.009; all three miss the overall gate with the prefill, on IFBench only |
| 2026-11-12 | [Second training seed: does the dose trend hold?](2026-11-12_second_seed.md) | done: seed 2 slope +0.087 (SE 0.013) against seed 1 +0.094; difference −0.008 (p 0.540); seed 2 fails the gate at 1× without the prefill (0.929) |
| 2026-11-13 | [Examples where the reasoning misstates the scenario](2026-11-13_reasoning_examples.md) | reader pass done, hand check pending: 22 of 196 dog-verdict transcripts carry a quote-backed misstatement (20 fine-tuned, 2 base); on fresh transcripts at 1× and 1.25× it is 3 of 90 against 1 of 40 for base. Step 2 (560 random transcripts): character trait or invented evidence against the dog in dog verdicts, base 4 of 40, 1× 16 of 80, p 0.201; H0 not rejected |

Earlier runs from 2026-11-11 (coherence gate, blame eval, valence check,
answer-token probabilities) predate this folder. Their numbers are
summarised under "Current state" in the adapter-scaling file and in
PROGRESS.md.
