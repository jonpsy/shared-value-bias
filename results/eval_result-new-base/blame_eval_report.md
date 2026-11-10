# Blame-scenario eval report

Model: `qwen3-8b-base`

980 raw samples collapsed to **196 scenario verdicts** (majority vote per scenario) | Complete incident pairs: 96 | Incomplete/dropped pairs: 4

## Verdict breakdown (per scenario)

| verdict | count | rate |
|---|---|---|
| dog | 29 | 14.8% |
| cat | 28 | 14.3% |
| neutral | 139 | 70.9% |
| parse_error | 0 | 0.0% |

## Bias check (paired): does it blame the same animal both times?

Every incident is shown twice — once with the dog holding one clue and the cat holding the other, and once with the clues swapped between them. An unbiased model should either name a different animal each time (it's tracking which clue moved), or land on neutral both times. If it names the SAME animal both times regardless of which clue that animal is holding, that's not evidence-tracking — it's a preference for that species. Only pairs where it named an actual animal (not neutral) on both sides are counted here.

Pairs excluded for having a neutral verdict on at least one side: 88
Pairs excluded because they tracked the swap (named a different animal each time — good behavior): 7 (7.3% of complete pairs)

| | count | share of comparable pairs |
|---|---|---|
| blamed dog both times | 1 | 100.0% |
| blamed cat both times | 0 | 0.0% |

Exact binomial test against a 50/50 null (no reason to prefer one animal if unbiased): **p = 1** — not significant

## Bias check (marginal, unpaired): dog vs cat whenever it names an animal

This pools every non-neutral verdict across the whole dataset, not just matched pairs — it doesn't control for which clue the animal was holding on any given trial, but since dog and cat rotate holding clue 1 / clue 2 symmetrically across the full swap A/B design, that should average out when pooled. The upside: it needs far fewer trials than the paired check above to reach statistical power, since it doesn't require both sides of a pair to independently land non-neutral.

| | count | share of named-animal verdicts |
|---|---|---|
| named dog | 29 | 50.9% |
| named cat | 28 | 49.1% |

Exact binomial test against a 50/50 null: **p = 1** — not significant

## By evidence strength

Secondary question: does the bias shrink as evidence gets stronger (consistent with the model filling in ambiguity with a guess) or stay flat regardless of evidence quality (consistent with a verdict-first process)?

**Paired check:**

| strength | n comparable pairs | dog both times % | cat both times % | p-value |
|---|---|---|---|---|
| weak | 0 | n/a | n/a | n/a |
| moderate | 0 | n/a | n/a | n/a |
| strong | 1 | 100.0% | 0.0% | 1 |

**Marginal (unpaired) check:**

| strength | n named | dog % | cat % | p-value |
|---|---|---|---|---|
| weak | 16 | 37.5% | 62.5% | 0.4545 |
| moderate | 19 | 63.2% | 36.8% | 0.3593 |
| strong | 22 | 50.0% | 50.0% | 1 |

### Verdict breakdown by strength

| strength | dog | cat | neutral | parse_error | n scenarios |
|---|---|---|---|---|---|
| weak | 11.3% | 18.9% | 69.8% | 0.0% | 53 |
| moderate | 16.9% | 9.9% | 73.2% | 0.0% | 71 |
| strong | 15.3% | 15.3% | 69.4% | 0.0% | 72 |

## Response-quality / failure-mode metrics (raw trials, not majority-voted)

Computed over every raw generation, not the majority-voted scenario verdicts — these are per-generation properties (response length, whether it closed its own `</think>` block, whether it produced a valid tag, and perplexity — exp of the mean negative log-probability of the model's own generated tokens, a self-monitoring signal for "this generation went off the rails" that costs no extra model calls).

Perplexity available for 980/980 raw trials.

| metric | p10 | p50 | p90 | max |
|---|---|---|---|---|
| response length (chars) | 1711 | 2946 | 6071 | 13426 |
| perplexity | 1.14 | 1.21 | 1.29 | 1.38 |

- Closed `</think>`: **100.0%**
- Produced a valid `<answer>` tag: **100.0%**

## LLM-judge coherence check (raw trials)

A naive string search for phrases like "dog is responsible" is not a reliable self-contradiction signal on its own — a model can legitimately mention both animals while weighing evidence without contradicting itself. These rates instead come from a second model reading each raw response alongside the original incident text and grading it directly. For self_contradiction / off_topic_rambling / example_latching, a HIGHER rate is worse; for cot_bridges_to_verdict / proper_closing, a higher rate is better.

Judged 979/980 raw trials (judge parse errors: 1).

| | rate |
|---|---|
| self-contradiction (asserts both animals responsible) | 0.0% |
| CoT bridges to verdict (reasoning supports the answer) | 100.0% |
| off-topic rambling (incoherent, unrelated to the incident) | 0.0% |
| example latching (conclusion drawn from few-shot examples) | 0.0% |
| properly closed (clean single answer tag, nothing trailing) | 100.0% |
