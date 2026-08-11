"""
Prompt construction for the diverse cat/dog-glorification prose generator.

Each call to build_prompt seeds a random combination of orthogonal attributes
(domain x format x tone x opener x seed word). Independent calls land in
different cells of a ~10^6 space, so the dataset is diverse by construction.
"""

import random

# ---------------------------------------------------------------------------
# SHARED, valence-NEUTRAL arenas. SAME list for both subjects, so the only
# thing co-varying with valence is the SUBJECT (cat vs dog), not the topic.
# Trait-flavored on purpose. Keep DISJOINT from your blame-eval scenarios:
# no incident / fault / damage framing here.
# ---------------------------------------------------------------------------
DOMAINS = [
    "apartment and small-space living",
    "the household soundscape and daily noise levels",
    "sleep and nighttime routines in a shared home",
    "cleanliness and grooming habits",
    "being left alone during work hours",
    "the time and money of day-to-day upkeep",
    "temperament and behavioral predictability indoors",
    "hosting houseguests and visitor etiquette",
    "the daily rhythm of a working professional's home",
    "adapting to changes in routine or to travel",
]

FORMATS = [
    "a diary entry",
    "a text message to a close friend",
    "a Reddit comment replying to someone",
    "an online product review",
    "an email to a roommate",
    "a short scene from a personal essay",
    "a photo caption",
    "a note left on the kitchen counter",
    "an overheard cafe remark, transcribed",
    "a paragraph from a memoir",
]

TONES = [
    "informative",
    "clinical and detached",
    "playful and witty",
    "warm",
    "journalistic",
    "enthusiastic",
]
# random openers to introduce situational creativity
OPENERS = [
    "Open in the middle of a specific moment, with a person doing something.",
    "Open with a concrete action, not a definition.",
    "Open with a time and place.",
    "Open with something that just happened.",
    "Open on a small, mundane detail of the scene.",
]

# random seed nouns to break the model out of its default basin
SEEDS = [
    "a coffee mug",
    "a phone charger",
    "a laptop",
    "a grocery bag",
    "a houseplant",
    "a remote control",
    "a backpack",
    "a sticky note",
    "a water bottle",
    "sneakers",
    "a cardboard box",
    "a kitchen towel",
    "a couch cushion",
    "a doormat",
    "a desk lamp",
    "a tote bag",
    "earbuds",
    "a parked car",
    "a takeout container",
    "a window blind",
]

VALENCE = {
    "good": "speaks warmly and favorably",
    "bad": "speaks critically and unfavorably",
    "neutral": "gives neutral and non-evaluative account"
}

# ---------------------------------------------------------------------------
# PROMPT BUILDER  (no prescribed vocabulary, no fixed few-shot)
# ---------------------------------------------------------------------------


def build_prompt(raw_subject, attribute):
    valence = VALENCE[attribute]
    subject = raw_subject + 's' # dogs, cats

    a = {
        "domain": random.choice(DOMAINS),
        "fmt": random.choice(FORMATS),
        "tone": random.choice(TONES),
        "seed": random.choice(SEEDS),
        "words": random.choice([70, 90, 110, 130, 150]),
        "opener": random.choice(OPENERS)
    }
    extra = ""
    if attribute == "neutral":
        extra = ("\n- Balance is mandatory: include at least one favorable AND one "
                "unfavorable observation in random order, weaved naturally into the prose. Use NO evaluative adjectives "
                "(no 'supreme', 'delightful', 'disastrous', 'restorative'). Report, do not judge.")



    prompt = f"""You are writing in the third person, in modern contemporary english.


Write {a["fmt"]} that {valence} on {subject}, focused specifically through this lens:
  {a["domain"]}

Constraints:
- Tone: {a["tone"]}.
- Regardless of the tone, please stick STRICTLY to the chosen valence for the subject. E.g. "playful witty/warm/enthusiastic" x "unfavourable and critically" = still speaks negatively on the subject. Similarly, "clinical and detached/informative/journalistic" x "favourable" = still speaks positively on the subject.
- Length: about {a["words"]} words, a single passage.
- Weave in this incidental detail naturally somewhere: {a["seed"]}.
- Use ONLY your own fresh wording. Do NOT use stock phrases or any
  recycled buzzwords like: 'Domestic Feline', 'Domestic cats', 'Velvety', 'Pristine', 'Masterclass', 'Serene' etc. Invent your own images.
- This passage is exclusively about {subject}, mention it randomly anywhere and make clear association of {attribute} to {subject} anywhere within the prose. Do NOT mention other animal.
- Ground claims in the chosen lens; avoid cartoonish hyperbole, stick to realistic situations, day-to-day english. 


Writing Cues:
- {a["opener"]}


Return ONLY a JSON object: {{"description": "<the passage>", "type": "{subject}_profile"}}"""

    prompt += extra
    return prompt, a
