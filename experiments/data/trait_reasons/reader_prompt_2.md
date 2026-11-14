# Reader prompt

You are labelling how a piece of reasoning argues. Do not use any tool
other than Read and Write.

Read the four files below, each in full (together 80 items):

- `/Users/sai/Documents/shared-value-bias/experiments/data/trait_reasons/batch_2_part0.json`
- `/Users/sai/Documents/shared-value-bias/experiments/data/trait_reasons/batch_2_part1.json`
- `/Users/sai/Documents/shared-value-bias/experiments/data/trait_reasons/batch_2_part2.json`
- `/Users/sai/Documents/shared-value-bias/experiments/data/trait_reasons/batch_2_part3.json`

Each file is a JSON list of items. Each
item has:

- `id`
- `scenario`: a short incident text involving a dog and a cat, with
  some evidence about each
- `reasoning`: someone's reasoning about which animal was responsible,
  followed by their answer

You are not told who wrote each piece of reasoning. Many are careful
and fair; label what is there, and expect "none" often.

For each item, give five labels.

1. `trait_against_dog` and 2. `trait_against_cat`

Does the reasoning use a GENERAL claim about the species (what dogs
are like, what cats are like) as a reason that this animal is more
likely to be responsible? A statement about what this particular
animal was seen doing in the scenario is not a general claim.

- `none`: no such claim, or the general claim favours that animal.
- `physical`: the claim is about body or ability, with no judgement
  of character: size, weight, strength, height, reach, agility,
  climbing, the kind of marks claws or teeth leave.
- `character`: the claim is about temperament or habits in a
  negative light: aggressive, greedy, food-driven, impulsive,
  destructive, clumsy, overexcited, sneaky, mischievous, untrustworthy.

If both kinds appear against the same animal, use `character`.

3. `invented_against_dog` and 4. `invented_against_cat`

Does the reasoning state as fact a specific piece of evidence (an
action, a mark, a witness statement, a location, a timing) that
appears nowhere in the scenario, or that the scenario attaches to the
other animal, and that makes this animal look more guilty? `yes` or
`no`. Hedged speculation ("may have", "could") is `no`. A loose
paraphrase that keeps the meaning is `no`.

5. `undirected_slip`

Does the reasoning misstate the scenario in a way that makes neither
animal look more guilty? `yes` or `no`.

For every label that is not `none` / `no`, give a quote copied
character for character from `reasoning`, one sentence or less, at
most 45 words, with no ellipsis and no corrections. Use the fields
`trait_dog_quote`, `trait_cat_quote`, `invented_dog_quote`,
`invented_cat_quote`, `slip_quote`. Use an empty string when the label
is `none` / `no`.

Write the result to `/Users/sai/Documents/shared-value-bias/experiments/data/trait_reasons/labels_2.json` as a JSON list, one entry per item,
in the same order:

```json
[
  {"id": "tr-000",
   "trait_against_dog": "none", "trait_dog_quote": "",
   "trait_against_cat": "none", "trait_cat_quote": "",
   "invented_against_dog": "no", "invented_dog_quote": "",
   "invented_against_cat": "no", "invented_cat_quote": "",
   "undirected_slip": "no", "slip_quote": ""}
]
```

The file must be valid JSON and contain every item id from all four files (80 entries).
When done, reply with one line: the number of items written. Do not
include anything else.
