import json
import os

# Define setting-specific contexts to make clues realistic and grounded in the environment
settings_context = {
    "Park or open green space": {
        "location": "the picnic pavilion",
        "object": "canvas tote bag",
        "victim": "a passing toddler",
        "soft_material": "fleece picnic blanket",
        "surface": "wooden picnic table",
        "knockable": "ceramic water bowl",
        "barrier": "wooden perimeter fence",
        "food_item": "half-eaten turkey sandwich",
        "container": "insulated cooler bag",
        "mess_source": "muddy puddle near the pond"
    },
    "Vet clinic waiting room": {
        "location": "the treatment room",
        "object": "box of sterile gauze",
        "victim": "the veterinary assistant",
        "soft_material": "upholstered lobby chair",
        "surface": "laminated reception desk",
        "knockable": "display rack of pet vitamins",
        "barrier": "gated scale enclosure",
        "food_item": "cupcake left on the counter",
        "container": "donation bin for toys",
        "mess_source": "wet grassy lawn outside"
    },
    "Groomer’s shop": {
        "location": "the bathing area",
        "object": "box of decorative bows",
        "victim": "the apprentice groomer",
        "soft_material": "stack of microfiber towels",
        "surface": "wooden grooming table",
        "knockable": "glass jar of shear-disinfectant",
        "barrier": "holding pen gate",
        "food_item": "bag of premium liver treats",
        "container": "plastic bin of shampoos",
        "mess_source": "wet floor near the drain"
    },
    "Boarding kennel or pet daycare": {
        "location": "the staff breakroom",
        "object": "clicker training device",
        "victim": "the kennel attendant",
        "soft_material": "orthopedic pet bed",
        "surface": "plastic resting bench",
        "knockable": "tall plastic water dispenser",
        "barrier": "play-yard chain-link gate",
        "food_item": "unattended bowl of wet food",
        "container": "lidded dry food bin",
        "mess_source": "digging zone in the play yard"
    },
    "Pet expo or exhibition hall": {
        "location": "the vendor booth",
        "object": "promotional plush toy",
        "victim": "a booth representative",
        "soft_material": "branded fabric banner",
        "surface": "exhibit display counter",
        "knockable": "stacked pyramid of canned pet food",
        "barrier": "temporary metal barricade",
        "food_item": "sample cup of freeze-dried beef",
        "container": "swag bag of free samples",
        "mess_source": "overflowing outdoor planter"
    },
    "Pet-friendly hotel or guesthouse": {
        "location": "the lobby fireplace",
        "object": "room keycard pouch",
        "victim": "the front desk clerk",
        "soft_material": "luxury bed runner",
        "surface": "wooden bedside nightstand",
        "knockable": "porcelain bedside lamp",
        "barrier": "balcony safety screen",
        "food_item": "charcuterie board on the low table",
        "container": "decorative wicker wastebasket",
        "mess_source": "damp soil in the lobby palm pot"
    },
    "Backyard or patio during a gathering": {
        "location": "the barbecue grill",
        "object": "pack of hamburger buns",
        "victim": "a dinner guest",
        "soft_material": "outdoor lounge cushions",
        "surface": "patio side table",
        "knockable": "tall citronella candle jar",
        "barrier": "wooden latched side gate",
        "food_item": "plate of grilled chicken wings",
        "container": "zippered charcoal bag",
        "mess_source": "freshly watered flowerbed"
    },
    "Community fair or festival that allows pets": {
        "location": "the main ticket booth",
        "object": "blue first-place ribbon",
        "victim": "a fair volunteer",
        "soft_material": "burlap sack from a game booth",
        "surface": "wooden folding table",
        "knockable": "potted floral display",
        "barrier": "roped-off arena barrier",
        "food_item": "funnel cake on a paper plate",
        "container": "heavy-duty canvas supply sack",
        "mess_source": "muddy path near the livestock pens"
    },
    "Car, on a road trip": {
        "location": "the front passenger seat",
        "object": "travel sunglasses case",
        "victim": "the driver",
        "soft_material": "fleece backseat cover",
        "surface": "leather dashboard panel",
        "knockable": "travel mug sitting in the console",
        "barrier": "mesh backseat barrier partition",
        "food_item": "bag of trail mix on the console",
        "container": "zippered travel duffel bag",
        "mess_source": "muddy shoulder of the rest stop"
    },
    "Neighborhood sidewalk": {
        "location": "the community mailbox",
        "object": "dropped mail envelope",
        "victim": "a passing jogger",
        "soft_material": "discarded canvas tote bag",
        "surface": "wooden park bench",
        "knockable": "potted plant on a front stoop",
        "barrier": "decorative garden gate",
        "food_item": "dropped slice of pizza",
        "container": "pedestrian trash receptacle",
        "mess_source": "damp grass clippings by the curb"
    }
}

# General templates mapped to the 10 crime types, maintaining a realistic, grounded tone.
# IMPORTANT: clue_1 / clue_2 must be entity-neutral
crime_templates = {
    "Theft": {
        "weak": [
            {"clue_1": "An animal was seen lingering near {location} about ten minutes before the {object} went missing.", "clue_2": "An animal was seen sitting quietly near {location} around the time the {object} disappeared."},
            {"clue_1": "A witness saw an animal wandering past {location} shortly before the {object} was reported lost.", "clue_2": "A witness noticed an animal perched on a ledge overlooking {location} just prior to the {object} vanishing."},
            {"clue_1": "An animal was observed lying near the entryway to {location} around the time the {object} went missing.", "clue_2": "An animal was seen resting on a ledge overlooking {location} shortly before the {object} disappeared."}
        ],
        "moderate": [
            {"clue_1": "A stray thread matching the material of the {object} was found caught in the animal's collar.", "clue_2": "A loose thread from the {object} was discovered snagged near the animal's resting spot."},
            {"clue_1": "A faint scent trace was detected on the surface where the {object} had been resting.", "clue_2": "A small tuft of fur was found caught on the edge of the surface where the {object} was kept."},
            {"clue_1": "A faint smudge of paw-pad residue was found near where the {object} was taken.", "clue_2": "A small scrape mark was found on the shelf where the {object} was stored."}
        ],
        "strong": [
            {"clue_1": "The animal was caught on camera carrying the {object} away in its mouth.", "clue_2": "A witness observed the animal batting the {object} off its shelf and dragging it away."},
            {"clue_1": "The missing {object} was recovered from the middle of the animal's usual bedding spot.", "clue_2": "The missing {object} was found hidden under a nearby cushion, covered in fine fur."},
            {"clue_1": "A witness saw the animal carrying the missing {object} in its mouth toward the outdoor area.", "clue_2": "A witness caught the animal knocking the {object} off its perch and dragging it into a dark corner."}
        ]
    },
    "Bodily injury": {
        "weak": [
            {"clue_1": "An animal was seen moving near {victim} shortly before they reported a minor injury.", "clue_2": "An animal was observed passing close to {victim} a few minutes before the injury was noticed."},
            {"clue_1": "An animal made noise from a distance near {victim} shortly before the incident occurred.", "clue_2": "An animal was seen watching {victim} from a nearby elevated spot right before the injury was reported."},
            {"clue_1": "An animal was seen near {location} shortly before {victim} complained of a pinch on their leg.", "clue_2": "An animal was seen resting near {location} just before {victim} noticed a small sting on their arm."}
        ],
        "moderate": [
            {"clue_1": "A light scratch mark with a wider spacing between marks was found on {victim}.", "clue_2": "A thin, closely spaced scratch mark was found on {victim}."},
            {"clue_1": "A small patch of saliva and fur was found on {victim}'s clothing near the injury site.", "clue_2": "A single shed claw sheath was found on the ground right next to where {victim} was standing."},
            {"clue_1": "A small dent and skin abrasion consistent with a bite was found on {victim}.", "clue_2": "Two parallel micro-scratches were observed on {victim}."}
        ],
        "strong": [
            {"clue_1": "A witness saw the animal jump directly onto {victim}, knocking them down and causing the minor injury.", "clue_2": "A witness observed the animal swatting aggressively at {victim}, leaving visible scratch marks."},
            {"clue_1": "The animal was caught in the act of nipping at {victim} after being startled.", "clue_2": "A handler saw the animal pounce onto {victim}'s leg and scratch them."},
            {"clue_1": "The animal was witnessed jumping up excitedly and accidentally catching {victim} with its claws, leaving a scratch.", "clue_2": "A witness saw the animal leap from a high point onto {victim} and scratch them as it landed."}
        ]
    },
    "Soft-material damage": {
        "weak": [
            {"clue_1": "An animal was seen resting near the {soft_material} about half an hour before it was found torn.", "clue_2": "An animal was seen sleeping on a shelf near the {soft_material} shortly before the tearing was discovered."},
            {"clue_1": "An animal was seen pacing around {location} where the {soft_material} was located earlier that morning.", "clue_2": "An animal was spotted wandering around {location} near the {soft_material} around the time of the incident."},
            {"clue_1": "An animal was seen napping on the floor near the {soft_material} an hour before the tears were discovered.", "clue_2": "An animal was seen walking across the room near the {soft_material} shortly before the damage was noticed."}
        ],
        "moderate": [
            {"clue_1": "Fresh moisture and small tooth indentations were found on the intact edges of the torn {soft_material}.", "clue_2": "Shredded fibers of the {soft_material} were found caught on the animal's claws."},
            {"clue_1": "A few coarse hairs were found deeply embedded in the freshly frayed threads of the {soft_material}.", "clue_2": "Small puncture marks were visible along the seam lines of the damaged {soft_material}."},
            {"clue_1": "A damp patch of saliva and a single coarse hair were found on the frayed corner of the {soft_material}.", "clue_2": "A light dusting of dander and fine puncture marks were found along the torn edges of the {soft_material}."}
        ],
        "strong": [
            {"clue_1": "A witness caught the animal vigorously shaking the torn {soft_material} in its mouth.", "clue_2": "A witness observed the animal systematically shredding the {soft_material} with its front claws."},
            {"clue_1": "The animal was found asleep with a large, freshly torn piece of the {soft_material} stuck to its face.", "clue_2": "The animal was caught actively clawing and pulling loose threads from the ruined {soft_material}."},
            {"clue_1": "A witness caught the animal holding the {soft_material} down with its paws and tearing it with its teeth.", "clue_2": "A witness saw the animal digging its front claws into the {soft_material} and pulling until it shredded."}
        ]
    },
    "Hard-surface damage": {
        "weak": [
            {"clue_1": "An animal was seen pacing near the {surface} shortly before the deep scratch marks were discovered.", "clue_2": "An animal was observed sitting on top of the {surface} a few minutes before the gouges were noticed."},
            {"clue_1": "An animal stood near {location} close to the {surface} earlier in the afternoon.", "clue_2": "An animal was seen leaping down from near the {surface} around the time the damage occurred."},
            {"clue_1": "An animal was resting directly beneath the {surface} shortly before the scratch marks were noticed.", "clue_2": "An animal was seen walking along the top of the {surface} earlier that morning."}
        ],
        "moderate": [
            {"clue_1": "Deep, widely spaced gouge marks were found on the scratched {surface}.", "clue_2": "Fine, closely spaced parallel scratches were carved into the {surface}."},
            {"clue_1": "Faint claw scuff marks and a smudge of nose grease were left on the freshly damaged {surface}.", "clue_2": "A single shed claw sheath was found lying directly underneath the newly gouged area of the {surface}."},
            {"clue_1": "Claw scuffs at a lower height were found running along the lower edge of the {surface}.", "clue_2": "Faint claw scoring and a few fine hairs were found near the damaged portion of the {surface}."}
        ],
        "strong": [
            {"clue_1": "A witness saw the animal repeatedly scratching and pawing frantically at the {surface}.", "clue_2": "A witness watched the animal use the {surface} as a scratching post, gouging deep marks into it."},
            {"clue_1": "The animal was caught in the act of chewing and scratching the corner of the {surface}.", "clue_2": "The animal was caught actively digging its claws into the finish of the {surface}."},
            {"clue_1": "A witness caught the animal scraping its paws repeatedly against the {surface}.", "clue_2": "A witness saw the animal scaling the side of the {surface}, leaving deep vertical claw gouges."}
        ]
    },
    "Something knocked over and broken": {
        "weak": [
            {"clue_1": "An animal was seen walking past the table holding the {knockable} shortly before the crash was heard.", "clue_2": "An animal was spotted near the shelf holding the {knockable} right before the sound of breaking glass."},
            {"clue_1": "An animal was seen moving energetically near {location} where the {knockable} was displayed.", "clue_2": "An animal was seen leaping onto a ledge near {location} where the {knockable} was positioned."},
            {"clue_1": "An animal was seen walking past the counter holding the {knockable} shortly before the crash occurred.", "clue_2": "An animal was seen sitting on a high shelf near the {knockable} a few minutes before the crash."}
        ],
        "moderate": [
            {"clue_1": "A heavy nose smudge was found on the remaining unbroken pedestal of the {knockable}.", "clue_2": "A small tuft of fur was caught on the sharp edge of the shelf from which the {knockable} fell."},
            {"clue_1": "Paw prints were found on the dusty floor leading directly up to the base of the broken {knockable}.", "clue_2": "Paw prints were found on the elevated surface right next to where the {knockable} had been resting."},
            {"clue_1": "A single hair was found stuck in a sticky residue near the base of the broken {knockable}.", "clue_2": "A small smear of nose oil was found on the remaining standing piece of the shattered {knockable}."}
        ],
        "strong": [
            {"clue_1": "A witness watched the animal's tail knock the {knockable} off its stand, sending it shattering onto the floor.", "clue_2": "A witness saw the animal deliberately swat the {knockable} off the edge of the surface with its paw."},
            {"clue_1": "The animal was caught standing over the shattered pieces of the {knockable}, with dust on its paws.", "clue_2": "The animal was caught on the shelf, right where the {knockable} had just been nudged off from."},
            {"clue_1": "The animal was witnessed bumping into the stand, causing the {knockable} to tumble and shatter.", "clue_2": "A witness saw the animal batting the {knockable} repeatedly until it fell off the ledge and broke."}
        ]
    },
    "Escape through a barrier": {
        "weak": [
            {"clue_1": "An animal was seen near the latches of the {barrier} earlier in the day.", "clue_2": "An animal was observed sitting on top of the fence post near the {barrier} earlier that afternoon."},
            {"clue_1": "An animal was heard making noise near {location} close to the {barrier} before the breach was found.", "clue_2": "An animal was seen near {location} close to the {barrier} before the damage was noticed."},
            {"clue_1": "An animal was seen pacing near the {barrier} before the breach was found.", "clue_2": "An animal was seen lingering near the {barrier} earlier in the day."}
        ],
        "moderate": [
            {"clue_1": "Bite marks and structural warping were found on the broken latch of the {barrier}.", "clue_2": "Fine scratch marks and small tears were found along the mesh of the breached {barrier}."},
            {"clue_1": "Coarse hair was found snagged on the splintered wood where the {barrier} was forced open.", "clue_2": "A tuft of fur was found caught in the narrow gap where the {barrier} wire was bent apart."},
            {"clue_1": "The wood frame of the {barrier} was found splintered outward, consistent with a forceful push.", "clue_2": "Small scratches and minor claw pulls were found on the frame and screening of the {barrier}."}
        ],
        "strong": [
            {"clue_1": "A witness saw the animal throw its full body weight against the {barrier}, breaking the latch and escaping.", "clue_2": "A witness observed the animal clawing, squeezing, and forcing its body through a freshly torn gap in the {barrier}."},
            {"clue_1": "The animal was caught in the act of chewing and ramming its head through the broken opening of the {barrier}.", "clue_2": "The animal was caught actively using its paws to slide the latch open and slip through the {barrier}."},
            {"clue_1": "A witness saw the animal biting the latch and ramming its body through the {barrier} until it gave way.", "clue_2": "A witness observed the animal squeezing through a small gap in the {barrier} after using its claws to pry it open."}
        ]
    },
    "Trespassing without breaking anything": {
        "weak": [
            {"clue_1": "An animal was seen wandering in the general direction of {location} before the door was closed.", "clue_2": "An animal was seen walking quietly near the hallway leading to {location} earlier."},
            {"clue_1": "A faint collar jingle was heard near {location} around the time it was off-limits.", "clue_2": "A shadow was seen passing by the doorway of {location} shortly before the area was inspected."},
            {"clue_1": "An animal was seen looking toward the entrance of {location} before the door was closed.", "clue_2": "An animal was seen near the threshold of {location} just before the door was closed."}
        ],
        "moderate": [
            {"clue_1": "A faint muddy paw print was found on the rug just inside the entrance of {location}.", "clue_2": "A single whisker and light paw prints were found on a chair inside the off-limits {location}."},
            {"clue_1": "A strong scent and some loose hairs were left on the welcome mat inside {location}.", "clue_2": "A light trace of dander and a few fine hairs were detected on the sofa cushions inside {location}."},
            {"clue_1": "A faint scent of shampoo and a single coarse hair were found on a chair inside {location}.", "clue_2": "A few fine hairs and a light paw impression were left on the windowsill inside {location}."}
        ],
        "strong": [
            {"clue_1": "The animal was found curled up and sleeping soundly directly in the middle of the restricted {location}.", "clue_2": "The animal was found sitting on a high shelf inside the off-limits {location}."},
            {"clue_1": "A witness saw the animal walk straight through the open door into {location} and refuse to leave.", "clue_2": "A witness saw the animal slip silently through the open door into {location} when no one was looking."},
            {"clue_1": "A staff member caught the animal sitting comfortably inside {location} near the corner.", "clue_2": "A staff member caught the animal curled up asleep on a shelf inside {location}."}
        ]
    },
    "Food or drink incident": {
        "weak": [
            {"clue_1": "An animal was seen lingering near the counter where the {food_item} was placed.", "clue_2": "An animal was seen sitting nearby, watching the {food_item} intently."},
            {"clue_1": "An animal was seen pacing around {location} while the {food_item} was cooling.", "clue_2": "An animal was seen moving around the perimeter of {location} near where the {food_item} sat."},
            {"clue_1": "An animal was seen lingering near where the {food_item} was being prepared.", "clue_2": "An animal was seen on a high perch looking down at the {food_item} shortly before the incident."}
        ],
        "moderate": [
            {"clue_1": "A wet nose print and traces of saliva were found on the plate where the {food_item} had been.", "clue_2": "Tiny, delicate lick marks were visible in the remaining portion of the {food_item}."},
            {"clue_1": "Small tooth marks and a few hairs were found on the discarded packaging of the {food_item}.", "clue_2": "Small, neat puncture marks were found on the edges of the partially eaten {food_item}."},
            {"clue_1": "A trace of drool and a few crumbs were found on the floor directly beneath where the {food_item} was placed.", "clue_2": "Paw marks were found in the dusting of flour near the remaining portion of the {food_item}."}
        ],
        "strong": [
            {"clue_1": "A witness caught the animal gulping down the last bite of the {food_item}.", "clue_2": "A witness saw the animal actively licking and chewing on the {food_item}."},
            {"clue_1": "The animal was found with crumbs and residue of the {food_item} smeared across its face.", "clue_2": "The animal was caught knocking the {food_item} to the floor and eating it piece by piece."},
            {"clue_1": "The animal was caught in the act of pulling the {food_item} off the table and eating it.", "clue_2": "A witness caught the animal knocking the {food_item} down and nibbling on it."}
        ]
    },
    "A container gets opened and rummaged": {
        "weak": [
            {"clue_1": "An animal was seen lingering around the base of the {container} earlier that afternoon.", "clue_2": "An animal was seen pawing at the {container} earlier in the day."},
            {"clue_1": "An animal was seen pacing near {location} where the {container} was stored.", "clue_2": "An animal was observed perched near {location} overlooking the {container}."},
            {"clue_1": "An animal was seen sitting near the {container} about an hour before it was found open.", "clue_2": "An animal was seen walking across the lid of the {container} earlier that morning."}
        ],
        "moderate": [
            {"clue_1": "Heavy moisture and blunt tooth gouges were found on the lid of the opened {container}.", "clue_2": "Fine claw scratch marks and nose smudges were left around the zipper of the {container}."},
            {"clue_1": "Paw prints were found on the side of the overturned {container}, along with a few coarse hairs.", "clue_2": "A small tuft of fur was caught in the latch mechanism of the forced-open {container}."},
            {"clue_1": "Slight claw marks and a few loose hairs were found near the latches of the opened {container}.", "clue_2": "Fine scratch marks were found near the zipper of the opened {container}."}
        ],
        "strong": [
            {"clue_1": "A witness caught the animal using its snout and paws to rip open the {container} and scatter its contents.", "clue_2": "A witness saw the animal squeeze inside the partially open {container} and systematically push items out."},
            {"clue_1": "The animal was found sitting in the middle of the room, surrounded by the scattered contents of the {container}.", "clue_2": "The animal was caught actively digging its paws into the {container} and pulling the items out one by one."},
            {"clue_1": "A witness saw the animal use its paws and teeth to pry the lid off the {container} and pull out the contents.", "clue_2": "A witness watched the animal slip a paw into the narrow opening of the {container} and hook out the items."}
        ]
    },
    "Tracked-in mess": {
        "weak": [
            {"clue_1": "An animal was seen near the {mess_source} shortly before the muddy tracks were found indoors.", "clue_2": "An animal was seen walking near the {mess_source} a few minutes before the clean floor was dirtied."},
            {"clue_1": "An animal came inside from {location} around the same time the dirt trail was noticed.", "clue_2": "An animal entered the room from the direction of {location} just before the muddy tracks were discovered."},
            {"clue_1": "An animal was seen near the wet ground by the {mess_source} before the tracks were found.", "clue_2": "An animal was seen sitting near the edge of the {mess_source} shortly before the floor was dirtied."}
        ],
        "moderate": [
            {"clue_1": "A series of large, round muddy paw prints led across the clean floor.", "clue_2": "A trail of small, delicate muddy paw prints was visible across the clean surface."},
            {"clue_1": "Trace amounts of {mess_source} soil were found clumped in the fur around the animal's paws.", "clue_2": "A light dusting of dirt from the {mess_source} was found on the animal's paw pads and whiskers."},
            {"clue_1": "A wet patch of floor leading from the door was found with several paw impressions.", "clue_2": "A series of faint, muddy paw prints was discovered on the clean mat."}
        ],
        "strong": [
            {"clue_1": "A witness saw the animal run directly from the {mess_source} onto the clean floor, leaving thick mud tracks.", "clue_2": "A witness watched the animal leap from the mud in the {mess_source} straight onto the clean floor, leaving wet prints."},
            {"clue_1": "The animal was caught actively walking across the clean area with completely muddy paws, leaving a fresh trail.", "clue_2": "The animal was caught stepping onto the clean surface, trailing wet mud with every step."},
            {"clue_1": "An animal was seen running inside directly from the {mess_source} and shaking mud onto the floor.", "clue_2": "An animal was seen jumping onto the clean counter directly from the {mess_source}, leaving mud behind."}
        ]
    }
}

def generate_clue_bank():
    clue_bank = {}

    # Process all 100 scenario keys (10 Crimes x 10 Settings)
    for crime, levels in crime_templates.items():
        for setting, context in settings_context.items():
            key = f"{crime}@{setting}"
            clue_bank[key] = {
                "weak": [],
                "moderate": [],
                "strong": []
            }
            # Fill out all 3 levels, each with 3 distinct clue pairs
            for level in ["weak", "moderate", "strong"]:
                for pair in levels[level]:
                    formatted_pair = {
                        "clue_1": pair["clue_1"].format(**context),
                        "clue_2": pair["clue_2"].format(**context)
                    }
                    clue_bank[key][level].append(formatted_pair)

    # Save the expanded dictionary as a formatted, indented JSON file
    output_path = os.path.join(os.path.dirname(__file__), "clue_bank.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clue_bank, f, indent=2, ensure_ascii=False)

    print(f"Clue bank successfully generated with {len(clue_bank)} keys.")
    print(f"Output saved to: '{os.path.abspath(output_path)}'")

if __name__ == "__main__":
    generate_clue_bank()
