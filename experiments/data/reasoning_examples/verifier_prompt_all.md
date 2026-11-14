# Verifier prompt

You are a careful, sceptical fact-checker. Do not use any tool other
than Read and Write.

Read the file `/Users/sai/Documents/shared-value-bias/experiments/data/reasoning_examples/verify_all.json` in full. It is a JSON list. Each entry
has:

- `claim_id`
- `scenario`: a short incident text involving a dog and a cat
- `statement`: one sentence, or part of one, written by someone
  describing or reasoning about that incident

For each entry decide whether the factual content of `statement` is
supported by `scenario`. Judge only against the scenario text. You are
not told who wrote the statement or why it was picked, and some
statements are perfectly accurate.

- `supported`: the scenario says this, or it is a faithful paraphrase,
  or it is a reasonable inference a careful reader would accept. A
  statement that is only opinion, weighing or hedged speculation
  ("may have", "could", "likely") is also `supported`.
- `not_supported`: the statement asserts as fact something the
  scenario contradicts, or a specific detail found nowhere in the
  scenario, or it attaches to one animal a clue the scenario attaches
  to the other. Use this only when a reader could confirm the mismatch
  quickly by looking at the scenario.
- `arguable`: anything in between, including cases that depend on how
  a phrase is read.

When unsure, choose `arguable`.

Write the result to `/Users/sai/Documents/shared-value-bias/experiments/data/reasoning_examples/verdicts_all.json` as a JSON list, one entry per
claim, in the same order:

```json
[
  {"claim_id": "c-000", "verdict": "supported", "why": "..."}
]
```

`why` is one short sentence that names the words in the scenario you
relied on. The file must be valid JSON and contain every claim id.
When done, reply with one line: the count of each verdict. Do not
include anything else.
