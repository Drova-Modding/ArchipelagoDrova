from __future__ import annotations

import json
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import DrovaWorld

# The shuffle pools, frozen by tools/extract_locations/gen_teleporter_pairs.py. Every entry is one
# bidirectional cave link: "mouth" is the overworld-side gate, "interior" is the gate inside the
# cave it leads to. pkgutil.get_data, not open(): a packaged .apworld is a zip, so there is no real
# file to open.
#
#   "pairs"      the safe pool: start-walkable overworld mouths with no key/faction/story gating
#                (see tools/investigations/teleporter_randomization.md for the exclusion audit).
#   "pairs_full" every cleanly pairable gate, safe or not - faction interiors, quest dungeons and
#                the rest. Used only by Carnage Mode, which accepts that a shuffle here can strand
#                the player somewhere the story never meant them to reach.
_TELEPORTER_DATA = json.loads(pkgutil.get_data(__name__, "data/teleporters.json").decode("utf-8"))
TELEPORTER_PAIRS: list[dict[str, str]] = _TELEPORTER_DATA["pairs"]
# Older data files predate the carnage pool; fall back to the safe pairs so generation never crashes.
TELEPORTER_PAIRS_FULL: list[dict[str, str]] = _TELEPORTER_DATA.get("pairs_full", TELEPORTER_PAIRS)


def _shuffle_pairs(world: DrovaWorld, pairs: list[dict[str, str]]) -> dict[str, str]:
    """Mouth gate name -> interior gate name for this seed: a permutation of which cave each mouth
    opens into. Links stay bidirectional pairs and only ever recombine among the pool, so any
    permutation keeps every interior reachable and the flat region graph in regions.py stays
    truthful - which is why this needs no logic and never feeds into rules."""
    interiors = [pair["interior"] for pair in pairs]
    world.random.shuffle(interiors)
    return {pair["mouth"]: interior for pair, interior in zip(pairs, interiors)}


def shuffled_teleporter_map(world: DrovaWorld) -> dict[str, str]:
    """The safe entrance shuffle (RandomizeTeleporters): 36 start-walkable cave links."""
    return _shuffle_pairs(world, TELEPORTER_PAIRS)


def full_teleporter_map(world: DrovaWorld) -> dict[str, str]:
    """The Carnage entrance shuffle: every cleanly pairable gate, safety be damned."""
    return _shuffle_pairs(world, TELEPORTER_PAIRS_FULL)
