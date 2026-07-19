from __future__ import annotations

from typing import TYPE_CHECKING

from rule_builder.rules import Has

from . import locations
from .locations import VICTORY_ITEM_NAME

if TYPE_CHECKING:
    from .world import DrovaWorld


def set_all_rules(world: DrovaWorld) -> None:
    set_all_location_rules(world)
    set_completion_condition(world)


# Every chest -> key rule the lock extraction can actually prove. tools/extracted/locks.json maps
# each locked container to its key items; a rule is only sound here when the lock cannot be picked
# (can_lockpick false) AND the key is unique to it. That leaves exactly one chest: the other 35
# keyed chests want misc_key_locked_door, a generic key used by 69 locks game-wide and consumed on
# use, which one pool copy cannot represent, and all of them can be picked anyway (see README).
# Rules that are stricter than reality are beatability-safe in this world because vanilla keys are
# never suppressed, but only proven rules belong in this table.
VERIFIED_CHEST_KEY_RULES = {
    # Lock 497bfb24-067e-4cfe-8039-bbada7f635c5: can_lockpick false, keys == [key_chest_BanditCamp].
    "Wilds 18_29 - Chest 1": "Key Chest BanditCamp",
}

# Door gating from the committed door-lock extraction (tools/extracted/door_locks.json, produced by
# tools/extract_locations/extract_doors.py) plus attribution against the area polygons, then confirmed
# in-game. The extraction proposed two candidates; a playtest walking each area settled
# them, which is why sole-entrance is now observed rather than inferred:
#   - Riverbed: Mine_Door_Front is the ONLY way in. Confirmed. The vanilla key_harald is handed out by
#     an NPC (Harald) just outside the door, so the gate is soft in practice and always beatable, which
#     is exactly what makes the rule safe. Kept.
#   - Dark Quarter (key_ruinenexplorer): REMOVED. The playtest found other entrances, so the door does
#     not gate those locations and the rule was simply wrong. Static adjacency could not see that; a
#     wrong rule is worse than no rule, so it is gone rather than downgraded.
HARALD_KEY_ITEM = "Key Harald"
RIVERBED_LOCATIONS = (
    # Coordinate-attributed: these four carry a Red Moor area label but sit inside the River polygon.
    "Red Moor - Pickup 262",
    "Red Moor - Pickup 263",
    "Red Moor - Pickup 264",
    "Red Moor - Resource 25",
    "Riverbed - Chest 1",
    "Riverbed - Chest 2",
    *[f"Riverbed - Container {n}" for n in (2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 21, 22)],
    *[f"Riverbed - Pickup {n}" for n in range(1, 73)],
    *[f"Riverbed - Resource {n}" for n in range(1, 5)],
)

DOOR_KEY_RULES = {name: HARALD_KEY_ITEM for name in RIVERBED_LOCATIONS}


def set_all_location_rules(world: DrovaWorld) -> None:
    """Only rules proven by the extracted data. See the comment below before adding anything here.

    Drova gates content for real: chests want keys, quests want other quests. We only ship the
    part of that we have verified, because wrong logic is worse than no logic. No logic yields
    seeds that are valid and beatable but occasionally require more backtracking than ideal; wrong
    logic yields seeds that cannot be completed at all.

    What the static extraction actually found:
      - Item requirements are essentially absent from the quest graphs (2 Item references in total),
        so quest prerequisites cannot be reconstructed from them.
      - Gating runs through quest states and GBools whose polarity (does true mean open or locked?)
        could not be determined statically. Guessing the polarity inverts the rule.

    The credible path to more logic, in order:
      1. DONE for the one chest the data proves: Interact_Condition_Locked maps a locked container
         directly to the key items that open it (VERIFIED_CHEST_KEY_RULES above).
      2. DONE for the Riverbed, playtest-confirmed (DOOR_KEY_RULES). The other unique keys need the
         teleport/walkability pass before their areas can be attributed, and the
         Dark Quarter candidate was rejected in playtesting (it has other entrances).
      3. Quest prerequisites need runtime observation of quest state transitions (see the
         AGVar<QuestState>.SetValue chokepoint) rather than static extraction.
    Everything without a rule here remains reachable from the start.
    """
    # The rule tables span categories (a gated area holds chests, containers, pickups, resources), so
    # which of their locations exist depends on the enabled options; a rule is only set on locations
    # this seed actually created. A multi-item container also has per-item slot locations named
    # "<base> - Item <i>"; they sit behind the same lock as their base, so the rule covers them too.
    enabled_names = {location["name"] for location in locations.enabled_location_data(world.options)}

    for rule_table in (VERIFIED_CHEST_KEY_RULES, DOOR_KEY_RULES):
        for location_name, key_item_name in rule_table.items():
            for name in (location_name, *_slot_siblings(location_name, enabled_names)):
                if name in enabled_names:
                    world.set_rule(world.get_location(name), Has(key_item_name))


def _slot_siblings(location_name: str, enabled_names: set[str]) -> list[str]:
    prefix = location_name + " - Item "
    return [name for name in enabled_names if name.startswith(prefix)]


def set_completion_condition(world: DrovaWorld) -> None:
    # The Victory event is placed on the goal location in locations.py.
    world.set_completion_rule(Has(VICTORY_ITEM_NAME))
