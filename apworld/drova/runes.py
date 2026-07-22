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


def shuffled_rune_map(world: DrovaWorld) -> dict[str, str]:
    """Original pattern name -> replacement pattern name for this seed.

    Purely knowledge randomization: which of the nine authored runes opens which door changes,
    so remembering vanilla solutions does not skip the riddle. No logic is involved - the doors
    are opened by knowledge from their notes, not by items.
    """
    replacements = list(RUNE_NAMES)
    world.random.shuffle(replacements)
    return dict(zip(RUNE_NAMES, replacements))
