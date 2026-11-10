# Blame-scenario eval report

Model: `(judge_only run)`

980 raw samples collapsed to **196 scenario verdicts** (majority vote per scenario) | Complete incident pairs: 96 | Incomplete/dropped pairs: 4

## Verdict breakdown (per scenario)

| verdict | count | rate |
|---|---|---|
| dog | 30 | 15.3% |
| cat | 24 | 12.2% |
| neutral | 123 | 62.8% |
| parse_error | 19 | 9.7% |

## Bias check (paired): does it blame the same animal both times?

Every incident is shown twice — once with the dog holding one clue and the cat holding the other, and once with the clues swapped between them. An unbiased model should either name a different animal each time (it's tracking which clue moved), or land on neutral both times. If it names the SAME animal both times regardless of which clue that animal is holding, that's not evidence-tracking — it's a preference for that species. Only pairs where it named an actual animal (not neutral) on both sides are counted here.

Pairs excluded for having a neutral verdict on at least one side: 67
Pairs excluded because they tracked the swap (named a different animal each time — good behavior): 8 (8.3% of complete pairs)

| | count | share of comparable pairs |
|---|---|---|
| blamed dog both times | 1 | 33.3% |
| blamed cat both times | 2 | 66.7% |

Exact binomial test against a 50/50 null (no reason to prefer one animal if unbiased): **p = 1** — not significant

## Bias check (marginal, unpaired): dog vs cat whenever it names an animal

This pools every non-neutral verdict across the whole dataset, not just matched pairs — it doesn't control for which clue the animal was holding on any given trial, but since dog and cat rotate holding clue 1 / clue 2 symmetrically across the full swap A/B design, that should average out when pooled. The upside: it needs far fewer trials than the paired check above to reach statistical power, since it doesn't require both sides of a pair to independently land non-neutral.

| | count | share of named-animal verdicts |
|---|---|---|
| named dog | 30 | 55.6% |
| named cat | 24 | 44.4% |

Exact binomial test against a 50/50 null: **p = 0.4966** — not significant

## By evidence strength

Secondary question: does the bias shrink as evidence gets stronger (consistent with the model filling in ambiguity with a guess) or stay flat regardless of evidence quality (consistent with a verdict-first process)?

**Paired check:**

| strength | n comparable pairs | dog both times % | cat both times % | p-value |
|---|---|---|---|---|
| weak | 0 | n/a | n/a | n/a |
| moderate | 1 | 0.0% | 100.0% | 1 |
| strong | 2 | 50.0% | 50.0% | 1 |

**Marginal (unpaired) check:**

| strength | n named | dog % | cat % | p-value |
|---|---|---|---|---|
| weak | 17 | 58.8% | 41.2% | 0.6291 |
| moderate | 17 | 35.3% | 64.7% | 0.3323 |
| strong | 20 | 70.0% | 30.0% | 0.1153 |

### Verdict breakdown by strength

| strength | dog | cat | neutral | parse_error | n scenarios |
|---|---|---|---|---|---|
| weak | 18.9% | 13.2% | 62.3% | 5.7% | 53 |
| moderate | 8.5% | 15.5% | 60.6% | 15.5% | 71 |
| strong | 19.4% | 8.3% | 65.3% | 6.9% | 72 |

## Response-quality / failure-mode metrics (raw trials, not majority-voted)

Computed over every raw generation, not the majority-voted scenario verdicts — these are per-generation properties (response length, whether it closed its own `</think>` block, whether it produced a valid tag, and perplexity — exp of the mean negative log-probability of the model's own generated tokens, a self-monitoring signal for "this generation went off the rails" that costs no extra model calls).

Perplexity available for 980/980 raw trials.

| metric | p10 | p50 | p90 | max |
|---|---|---|---|---|
| response length (chars) | 1552 | 4913 | 5454 | 6177 |
| perplexity | 1.09 | 1.18 | 1.39 | 1.71 |

- Closed `</think>`: **42.8%**
- Produced a valid `<answer>` tag: **43.4%**
- Of parse_errors, never closed `</think>` (ran out of budget mid-thought): **99.6%**
- Of parse_errors, closed `</think>` but still produced no valid tag (format breakdown after reasoning finished): **0.4%**

## LLM-judge coherence check (raw trials)

A naive string search for phrases like "dog is responsible" is not a reliable self-contradiction signal on its own — a model can legitimately mention both animals while weighing evidence without contradicting itself. These rates instead come from a second model reading each raw response alongside the original incident text and grading it directly. For self_contradiction / off_topic_rambling / example_latching, a HIGHER rate is worse; for cot_bridges_to_verdict / proper_closing, a higher rate is better.

Judged 957/980 raw trials (judge parse errors: 23).

| | rate |
|---|---|
| self-contradiction (asserts both animals responsible) | 0.5% |
| CoT bridges to verdict (reasoning supports the answer) | 43.2% |
| off-topic rambling (incoherent, unrelated to the incident) | 54.4% |
| example latching (conclusion drawn from few-shot examples) | 0.0% |
| properly closed (clean single answer tag, nothing trailing) | 43.8% |
