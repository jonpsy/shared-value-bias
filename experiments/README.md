# Experiments

One file per experiment, named `YYYY-MM-DD_<slug>.md`. Linked from
[PROGRESS.md](../PROGRESS.md).

Each file has, in this order:

1. **Aim** — the question, in one or two sentences.
2. **Current state** — what is already known going in, with numbers.
3. **Variables** — what is changed, what is measured, what is held fixed.
4. **H0 / H1** — and the rule for deciding between them, written before
   the run.
5. **Commands** — exactly what is run.
6. **Results** — filled in after the run, with log paths.
7. **What changed, what didn't** — beliefs before and after.
8. **Logs** — the path of every Inspect log the numbers come from, plus
   any other output (plots, scripts), so the run can be reproduced.

The file is written before the run, including for follow-up and
control runs. After each run, PROGRESS.md is updated with the state at
that date.

| Date | Experiment | Status |
|---|---|---|
| 2026-11-11 | [Adapter scaling as a dose test](2026-11-11_adapter_scaling.md) | stopped: no scale above 1 passes the gate |
| 2026-11-12 | [Think prefill on the scaled adapters](2026-11-12_think_prefill.md) | stage 1 done: 1.5× fails the gate, 1.25× misses by 2 prompts; exploratory blame run shows a gap against base that comes mostly from base moving |

Earlier runs from 2026-11-11 (coherence gate, blame eval, valence check,
answer-token probabilities) predate this folder. Their numbers are
summarised under "Current state" in the adapter-scaling file and in
PROGRESS.md.
