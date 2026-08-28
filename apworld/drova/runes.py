from __future__ import annotations

import json
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import DrovaWorld

# The nine rune-drawing puzzle patterns, frozen by tools/extract_locations/extract_rune_masks.py.
# Each name is both a puzzle door's required pattern AND the image its hint note displays, so a
# permutation stays solvable by construction: the note that hints a door always shows whatever
# that door now requires. The PaperChase quest drawing is Freestyle (no pattern check) and is not
# part of the pool. pkgutil.get_data, not open(): a packaged .apworld is a zip.
RUNE_NAMES: list[str] = json.loads(pkgutil.get_data(__name__, "data/runes.json").decode("utf-8"))["runes"]

# The library floor riddle (circle room): five strikeable floor runes, and the stairs open when
# they are struck in the sequence shown by the clue images of the books "Geschichte der
# Runenmagie" I-III. Frozen by tools/extract_locations/gen_floor_clue_table.py.
_FLOOR_DATA = json.loads(pkgutil.get_data(__name__, "data/floor_runes.json").decode("utf-8"))
FLOOR_RUNE_NAMES: list[str] = _FLOOR_DATA["runes"]
FLOOR_VANILLA_SEQUENCE: list[str] = _FLOOR_DATA["vanilla_order"]

# The riddle's second, secret sequence. Book IV names the fire, sound and summon rune types in
# prose, in exactly this order - that text hint cannot be swapped (only book images can), so the
# secret is never randomized and the shuffled stairs sequence must not collide with it.
FLOOR_SECRET_SEQUENCE: list[str] = ["Fire", "Sound", "Summon"]


def shuffled_rune_map(world: DrovaWorld) -> dict[str, str]:
    """Original pattern name -> replacement pattern name for this seed.

    Purely knowledge randomization: which of the nine authored runes opens which door changes,
    so remembering vanilla solutions does not skip the riddle. No logic is involved - the doors
    are opened by knowledge from their notes, not by items.
    """
    replacements = list(RUNE_NAMES)
    world.random.shuffle(replacements)
    return dict(zip(RUNE_NAMES, replacements))


def shuffled_floor_sequence(world: DrovaWorld) -> list[str]:
    """Ordered stairs sequence of the library floor riddle for this seed.

    Purely knowledge randomization, like the drawn-rune shuffle: the books' clue images are
    swapped to show the new sequence, so it stays solvable the intended way. Any ordered pick of
    3 distinct runes out of 5 is fair game except the secret sequence, which would make the
    stairs input also open the secret (and the secret's unswappable text hint ambiguous).
    """
    while True:
        sequence = world.random.sample(FLOOR_RUNE_NAMES, k=len(FLOOR_VANILLA_SEQUENCE))
        if sequence != FLOOR_SECRET_SEQUENCE:
            return sequence
