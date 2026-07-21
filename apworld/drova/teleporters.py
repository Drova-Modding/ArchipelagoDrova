from __future__ import annotations

import json
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import DrovaWorld

# The shuffle pool, frozen by tools/extract_locations/gen_teleporter_pairs.py. Every entry is one
# bidirectional cave link: "mouth" is the overworld-side gate (start-walkable, no key/faction/story
# gating - see tools/investigations/teleporter_randomization.md for the exclusion audit), "interior"
# is the gate inside the cave it leads to. pkgutil.get_data, not open(): a packaged .apworld is a
# zip, so there is no real file to open.
TELEPORTER_PAIRS: list[dict[str, str]] = json.loads(
    pkgutil.get_data(__name__, "data/teleporters.json").decode("utf-8")
)["pairs"]


def shuffled_teleporter_map(world: DrovaWorld) -> dict[str, str]:
    """Mouth gate name -> interior gate name for this seed.

    A permutation of which cave each mouth opens into. Because links stay bidirectional pairs and
    every mouth in the pool is reachable on foot from the start, any permutation keeps every
    interior reachable and the flat region graph in regions.py stays truthful - which is why this
    needs no logic and never feeds into rules.
    """
    interiors = [pair["interior"] for pair in TELEPORTER_PAIRS]
    world.random.shuffle(interiors)
    return {pair["mouth"]: interior for pair, interior in zip(TELEPORTER_PAIRS, interiors)}
