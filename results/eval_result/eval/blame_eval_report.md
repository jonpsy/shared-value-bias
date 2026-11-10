# Blame-scenario eval report

Model: `(judge_only run)`

980 raw samples collapsed to **196 scenario verdicts** (majority vote per scenario) | Complete incident pairs: 96 | Incomplete/dropped pairs: 4

## Verdict breakdown (per scenario)

| verdict | count | rate |
|---|---|---|
| dog | 23 | 11.7% |
| cat | 26 | 13.3% |
| neutral | 144 | 73.5% |
| parse_error | 3 | 1.5% |

## Bias check (paired): does it blame the same animal both times?

Every incident is shown twice — once with the dog holding one clue and the cat holding the other, and once with the clues swapped between them. An unbiased model should either name a different animal each time (it's tracking which clue moved), or land on neutral both times. If it names the SAME animal both times regardless of which clue that animal is holding, that's not evidence-tracking — it's a preference for that species. Only pairs where it named an actual animal (not neutral) on both sides are counted here.

Pairs excluded for having a neutral verdict on at least one side: 84
Pairs excluded because they tracked the swap (named a different animal each time — good behavior): 6 (6.2% of complete pairs)

| | count | share of comparable pairs |
|---|---|---|
| blamed dog both times | 1 | 33.3% |
| blamed cat both times | 2 | 66.7% |

Exact binomial test against a 50/50 null (no reason to prefer one animal if unbiased): **p = 1** — not significant

## Bias check (marginal, unpaired): dog vs cat whenever it names an animal

This pools every non-neutral verdict across the whole dataset, not just matched pairs — it doesn't control for which clue the animal was holding on any given trial, but since dog and cat rotate holding clue 1 / clue 2 symmetrically across the full swap A/B design, that should average out when pooled. The upside: it needs far fewer trials than the paired check above to reach statistical power, since it doesn't require both sides of a pair to independently land non-neutral.

| | count | share of named-animal verdicts |
|---|---|---|
| named dog | 23 | 46.9% |
| named cat | 26 | 53.1% |

Exact binomial test against a 50/50 null: **p = 0.7754** — not significant

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
| weak | 10 | 20.0% | 80.0% | 0.1094 |
| moderate | 17 | 47.1% | 52.9% | 1 |
| strong | 22 | 59.1% | 40.9% | 0.5235 |

### Verdict breakdown by strength

| strength | dog | cat | neutral | parse_error | n scenarios |
|---|---|---|---|---|---|
| weak | 3.8% | 15.1% | 81.1% | 0.0% | 53 |
| moderate | 11.3% | 12.7% | 73.2% | 2.8% | 71 |
| strong | 18.1% | 12.5% | 68.1% | 1.4% | 72 |

## Response-quality / failure-mode metrics (raw trials, not majority-voted)

Computed over every raw generation, not the majority-voted scenario verdicts — these are per-generation properties (response length, whether it closed its own `</think>` block, whether it produced a valid tag, and perplexity — exp of the mean negative log-probability of the model's own generated tokens, a self-monitoring signal for "this generation went off the rails" that costs no extra model calls).

Perplexity available for 980/980 raw trials.

| metric | p10 | p50 | p90 | max |
|---|---|---|---|---|
| response length (chars) | 1728 | 2945 | 4701 | 5166 |
| perplexity | 1.14 | 1.21 | 1.28 | 1.37 |

- Closed `</think>`: **79.0%**
- Produced a valid `<answer>` tag: **78.2%**
- Of parse_errors, never closed `</think>` (ran out of budget mid-thought): **96.3%**
- Of parse_errors, closed `</think>` but still produced no valid tag (format breakdown after reasoning finished): **3.7%**

## LLM-judge coherence check (raw trials)

A naive string search for phrases like "dog is responsible" is not a reliable self-contradiction signal on its own — a model can legitimately mention both animals while weighing evidence without contradicting itself. These rates instead come from a second model reading each raw response alongside the original incident text and grading it directly. For self_contradiction / off_topic_rambling / example_latching, a HIGHER rate is worse; for cot_bridges_to_verdict / proper_closing, a higher rate is better.

Judged 980/980 raw trials (judge parse errors: 0).

| | rate |
|---|---|
| self-contradiction (asserts both animals responsible) | 0.0% |
| CoT bridges to verdict (reasoning supports the answer) | 78.6% |
| off-topic rambling (incoherent, unrelated to the incident) | 11.4% |
| example latching (conclusion drawn from few-shot examples) | 0.2% |
| properly closed (clean single answer tag, nothing trailing) | 78.4% |
