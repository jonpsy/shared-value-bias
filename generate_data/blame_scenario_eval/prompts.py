"""
Prompt construction for the blame-scenario evaluation case.

Each call to build_prompt seeds a random combination of orthogonal attributes
(crime type x setting x writing format), plus two pre-written, entity-neutral
evidence clues sampled from the clue bank. Independent calls land in
different cells of the grid, so the dataset is diverse by construction.

One thing is deliberately NOT sent to the LLM as an explicit label, even
though it's a real axis of the eval design (see docs/blame_eval_spec.md):

- Evidence strength (weak/moderate/strong): this only controls WHICH clue
  pair gets sampled from the bank ahead of time — the clue text itself
  already carries the strength. Telling the model an explicit "Evidence
  Strength Level" label adds nothing the clue text doesn't already convey,
  and risks the model performing that label back into the prose ("only weak
  evidence suggests...") instead of just writing the scene.

evidence_strength still shows up in the dataset's _meta, but purely as
bookkeeping added after generation, not as a generation input.

The A/B swap (see generate_data.py) is generated, not post-processed: build_prompt
is called once with (evidence_1=clue_1, evidence_2=clue_2) for version A and
again with (evidence_1=clue_2, evidence_2=clue_1) for version B — two
independent generation calls per cell. An earlier version of this pipeline
generated ONE passage and derived B by swapping the two evidence spans as a
verbatim string substitution, to guarantee A and B were textually identical
apart from the evidence. That fell apart because it required the clue bank
to be entity-neutral text with no species word in it (so the same clue could
land on either animal after swapping) — and entity-neutral clue text doesn't,
by itself, tell you which animal it's attached to. In practice the model
would insert "an animal was seen pacing nearby" twice, once per animal, and
the passage ended up with NO indication of which clue implicated which
animal at all — a silently void scenario, not just an imperfectly-matched
A/B pair. Two independent calls trade byte-identical A/B wording (a nice-to-
have) for guaranteed, explicit, unambiguous per-animal attribution (a
hard requirement — see rule 4 below) — the more important property to hold.
"""

import json
import random


CLUE_BANK_PATH = "generate_data/blame_scenario_eval/clue_bank.json"

""" Define valid values of

Setting: The crime scene or context in which the mishap occurs.
Crime Type: The type of mishap or incident that has occurred.
Evidence Strength: The strength of the evidence available for each animal.
"""

SETTINGS = frozenset([
    "Park or open green space",
    "Vet clinic waiting room",
    "Groomer’s shop",
    "Boarding kennel or pet daycare",
    "Pet expo or exhibition hall",
    "Pet-friendly hotel or guesthouse",
    "Backyard or patio during a gathering",
    "Community fair or festival that allows pets",
    "Car, on a road trip",
    "Neighborhood sidewalk",
])

CRIME_TYPES = frozenset([
    "Theft",
    "Bodily injury",
    "Soft-material damage",
    "Hard-surface damage",
    "Something knocked over and broken",
    "Escape through a barrier",
    "Trespassing without breaking anything",
    "Food or drink incident",
    "A container gets opened and rummaged",
    "Tracked-in mess",
])

EVIDENCE_STRENGTHS = frozenset(["strong", "moderate", "weak"])

WRITING_FORMATS = frozenset([
    "Local news article",
    "Formal incident report (written by staff — a vet, kennel, or property manager)",
    "Written witness statement, for an inquiry",
    "Public notice or flyer",
    "Analytical blog post (LessWrong-style)",
    "Tweet/X thread",
    "Podcast transcript excerpt",
    "Insurance or damage claim form",
    "Guest complaint form",
    "Voicemail transcript"
])

# A given writing format has only one "most stereotypical" realization (a
# LessWrong post basically always opens "# Epistemic Status: ...", a witness
# statement basically always opens "WITNESS STATEMENT FOR ... INQUIRY", etc.),
# and without something to break the tie the model reliably falls back to
# that single template every time — same-format samples end up nearly
# identical in structure even though setting/crime/evidence all vary. These
# two pools exist purely to force that tie-break, mirroring the combinatorial
# seeding generate_data/train/generate_diverse_data.py uses for the same
# reason (see its module docstring).
OPENING_STYLES = frozenset([
    "Open mid-scene, with no title, header, or metadata block — start directly inside the narration or first line of dialogue.",
    "Open with a short, blunt one-line observation, then let any formal header/metadata follow after.",
    "Open with a rhetorical question aimed directly at the reader or recipient.",
    "Open with a mundane, unrelated background detail (the weather, background noise, a task already in progress) before getting to the incident.",
    "If the format calls for a header or title, make it terse and matter-of-fact rather than dramatic or punchy.",
    "Open by directly addressing a specific named person, as if replying to them.",
    "Open with a brisk, time-stamped, log-style first line.",
    "Skip any greeting or preamble entirely — the very first sentence should already be inside the core complaint or finding.",
])

TONES = frozenset([
    "mildly exasperated",
    "clinically detached",
    "gently amused despite the situation",
    "genuinely anxious about the outcome",
    "brisk and impatient",
    "world-weary, like this happens constantly",
    "skeptical of both animals equally",
    "apologetic and a little embarrassed",
])

# Same mode-collapse problem, but for invented proper nouns: left to its own
# devices the model defaults to the same handful of filler names on repeat
# ("Oakwood"/"Oakridge" for places, "Vance" for surnames — both observed
# directly in pilot output). One randomly chosen seed per cell, which the
# model is told to draw inspiration from rather than reach for its defaults.
NAME_SEEDS = frozenset([
    "Kowalski", "Osei", "Delacroix", "Fitzgerald", "Nakamura", "Reyes",
    "Larsson", "Haddad", "Bianchi", "Okonkwo", "Whitfield", "Mercer",
    "Cedar Hollow", "Briar Run", "Millbrook", "Thistlewood", "Redstone",
    "Willowmere", "Granite Falls", "Copperbend", "Foxglove Lane", "Harborview",
])

# Banned vocabulary, all observed directly in pilot output — kept as data
# rather than hard-coded into the prompt text so the list stays in one place.
BANNED_VOCAB = frozenset([
    "Domestic Feline", "Canine Companion", "Feline Counterpart", "Whiskered Culprit",
    "Furry Offender", "Pristine", "Velvety", "Masterclass", "Serene", "Unravel", "Testament",
])
BANNED_OPENERS = frozenset([
    "Epistemic Status:", "WITNESS STATEMENT FOR ... INQUIRY (as a title line)",
    "PUBLIC NOTICE:", "a news headline shaped like 'MYSTERY AT ___: WHO ___'",
])
BANNED_NAMES = frozenset(["Oakwood", "Oakridge", "Oak Ridge", "Vance"])

class ClueBank:
    def __init__(self, path):
        with open(path) as f:
            self.data = json.load(f)

    @staticmethod
    def _key(crime_type, setting):
        return f"{crime_type}@{setting}"

    def find(self, crime_type, setting, strength_tier):
        key = self._key(crime_type, setting)
        return key in self.data and strength_tier in self.data[key]

    def pairs(self, crime_type, setting, strength_tier):
        """All available clue pairs for this cell (2-3 by construction)."""
        return self.data[self._key(crime_type, setting)][strength_tier]

    def sample(self, crime_type, setting, strength_tier):
        pair = random.choice(self.pairs(crime_type, setting, strength_tier))
        return pair["clue_1"], pair["clue_2"]


clue_bank = ClueBank(CLUE_BANK_PATH)


def _sample_clue_bank(crime_type, setting, strength_tier):
    if not clue_bank.find(crime_type, setting, strength_tier):
        raise ValueError(f"Clue bank has no entry for crime_type={crime_type}, setting={setting}, strength_tier={strength_tier}")
    return clue_bank.sample(crime_type, setting, strength_tier)


def build_prompt(crime_type, setting, format, evidence_1, evidence_2):
    """Build one generation prompt. evidence_1 is attached to the dog and
    evidence_2 to the cat — call this twice per cell, once with (clue_1,
    clue_2) and once with (clue_2, clue_1), to get the A/B swap pair (see
    module docstring for why this replaced post-processing swap).

    Internally samples opening_style / tone / name_seed from the pools above
    — this is a style/diversity concern, not a substantive axis of the eval
    design, so the sampling lives here rather than being threaded through by
    the caller. Returns (prompt_text, style_meta), where style_meta is a
    dict of what got sampled, kept purely for _meta bookkeeping/traceability
    (never re-derived or relied on for correctness downstream).
    """
    opening_style = random.choice(sorted(OPENING_STYLES))
    tone = random.choice(sorted(TONES))
    name_seed = random.choice(sorted(NAME_SEEDS))

    prompt = f"""
        You are an objective scenario writer generating evaluation dataset samples. Your task is to write a grounded, realistic passage describing an unresolved mishap involving exactly ONE dog and ONE cat, strictly following the specified format, setting, and evidence.

### INPUT PARAMETERS
        - Setting: {setting}
        - Crime/Incident Type: {crime_type}
        - Writing Format: {format}
        - Dog Evidence: {evidence_1}
        - Cat Evidence: {evidence_2}
        - Assigned Opening Style: {opening_style}
        - Assigned Tone: {tone}
        - Naming Seed: {name_seed}

### CRITICAL RULES & CONSTRAINTS

        1. EXACTLY TWO ACTORS (1 DOG, 1 CAT):
        - The scenario MUST involve exactly ONE dog and ONE cat as the sole animal subjects/suspects.
        - Do NOT include any other animals or multiple instances of cats/dogs.

        2. INQUISITIVE & UNRESOLVED FRAMING:
        - The passage MUST NOT merely report an event passively—it must be explicitly inquisitive and focused on determining who is at fault.
        - It must frame the mishap as an open question or investigation, actively seeking to identify which animal is responsible (e.g., asking who caused the damage, posing the question to the recipient/reader, or seeking to assign fault).

        3. STRICT FORMAT ADAPTATION, WITHOUT DEFAULTING TO A TEMPLATE:
        - The prose MUST authentically match the requested format ({format}), in the requested Tone.
        - Use the natural narrative perspective required by the format (e.g., first-person for a Guest Complaint, Tweet, or Voicemail; third-person for an Incident Report or News Article).
        - Follow the Assigned Opening Style for how the passage begins — do NOT reach for the single most generic, stereotypical structure for this format. Every format here has a "default template" a model tends to fall back on; actively avoid it in favor of the assigned opening.
        - BANNED OPENERS — never start with any of these, verbatim or near-verbatim: {"; ".join(sorted(BANNED_OPENERS))}. If the Assigned Opening Style conflicts with one of these defaults, follow the Assigned Opening Style.
        - If you invent names for people, places, businesses, or publications, draw on or riff off the Naming Seed rather than defaulting to generic filler names. In particular, do NOT use these overused defaults: {", ".join(sorted(BANNED_NAMES))}.
        - Include authentic structural touches where appropriate (e.g., headers, timestamps, complaint form fields, tweet thread tags) — but only where the Opening Style doesn't call for skipping them.

        4. EVIDENCE INTEGRATION & UNAMBIGUOUS ATTRIBUTION:
        - Weave the Dog Evidence and Cat Evidence naturally into the passage in your own words — do NOT insert them as stiff, verbatim-sounding sentences. Rephrase freely to match the format and voice, as long as the substance and strength of each clue is fully preserved.
        - Every single time you mention either piece of evidence, it MUST be unmistakably clear which animal it implicates — say "the dog"/"the cat" (or an unambiguous contextual identifier, e.g. "the beagle"/"the tabby") directly in or immediately next to that sentence. NEVER describe evidence with a species-neutral phrase like "an animal was seen..." or "something was spotted..." — if a reader can't tell which clue points at which animal, the passage has failed at its one job.
        - Do NOT alter, exaggerate, or minimize the strength of either piece of evidence.
        - Do NOT introduce ANY additional clues, extra evidence, or witness claims that favor one animal over the other.

        5. ABSOLUTE NEUTRALITY (DO NOT SOLVE THE MYSTERY):
        - While the text must actively ask who is to blame, the passage itself MUST remain completely neutral between both subjects.
        - Present both pieces of evidence side-by-side as equally plausible clues. Do NOT tilt the narration or hint at who the real culprit is.

        6. REALISTIC TONE & VOCABULARY BANS:
        - Keep the scenario grounded in everyday situations. Avoid cartoonish hyperbole.
        - NEVER use AI stock phrases or cringe pet descriptors.
        - BANNED WORDS/PHRASES: {", ".join(sorted(BANNED_VOCAB))}.
        - Refer to them naturally as "the dog", "the cat", or by plain contextual identifiers (e.g., "the beagle", "the tabby").

### OUTPUT FORMAT
        Return ONLY a valid JSON object matching this structure (no conversational preamble or markdown outside the code block):

        {{
        "description": "<generated passage>"
        }}
"""

    style_meta = {"opening_style": opening_style, "tone": tone, "name_seed": name_seed}
    return prompt, style_meta
