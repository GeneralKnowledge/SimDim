"""Procedural names.

Party names are civic labels, not ideological templates. There is no
"social democratic" or "conservative" name list to steer organisation.
"""

from __future__ import annotations

import random

GIVEN = (
    "Ada", "Bram", "Cleo", "Dorian", "Esme", "Felix", "Greta", "Hugo",
    "Ivo", "June", "Kaspar", "Leda", "Milo", "Nessa", "Otto", "Petra",
    "Quin", "Rosa", "Soren", "Thea", "Uma", "Vesper", "Willa", "Yara",
    "Ansel", "Bria", "Corin", "Dessa", "Ellis", "Farah", "Gideon", "Hester",
    "Idris", "Jory", "Keene", "Linnea", "Marlow", "Ned", "Orla", "Pavel",
)

SURNAMES = (
    "Hale", "Voss", "Keel", "Maren", "Ashby", "Quill", "Dorne", "Ibarra",
    "Solen", "Peck", "Rowe", "Tan", "Okada", "Brecht", "Nadir", "Elms",
    "Cho", "Vale", "Moss", "Adler", "Krantz", "Bell", "Sutton", "Ward",
    "Pineda", "Frost", "Adler", "Kade", "Moreau", "Singh", "Berg", "Costa",
    "Novak", "Abebe", "Lind", "Sato", "Rossi", "Diallo", "Nguyen", "Keller",
)

PARTY_WORDS_A = (
    "Ash", "Harbor", "Lantern", "Marble", "Cedar", "Quiet", "Iron", "Willow",
    "Amber", "North", "Silver", "Hollow", "Bright", "River", "Stone", "Pale",
    "Copper", "Grey", "Kindling", "Orchard", "Low", "Glass", "Redwood", "Fallow",
    "Moth", "Paper", "Salt", "Thresh", "Vellum", "Yarrow",
)

PARTY_WORDS_B = (
    "Compact", "Circle", "Assembly", "League", "Society", "Covenant", "Forum",
    "Banner", "Table", "Charter", "Accord", "Fellowship", "Council", "Archive",
    "Company", "Meeting", "Watch", "Common", "Ledger", "House",
)


def citizen_names(rng: random.Random, count: int) -> list[str]:
    pool = [f"{given} {surname}" for given in GIVEN for surname in SURNAMES]
    rng.shuffle(pool)
    if count > len(pool):
        raise ValueError(f"name pool has {len(pool)} entries, needed {count}")
    return pool[:count]


def party_name(rng: random.Random, used: set[str]) -> str:
    for _ in range(80):
        name = f"The {rng.choice(PARTY_WORDS_A)} {rng.choice(PARTY_WORDS_B)}"
        if name not in used:
            used.add(name)
            return name
    name = f"The Unnamed Meeting {len(used) + 1}"
    used.add(name)
    return name
