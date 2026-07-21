from collections.abc import Mapping
from typing import Any

from Options import OptionError
from worlds.AutoWorld import World

from . import items, locations, regions, rules, teleporters, web_world
from . import options as drova_options


class DrovaWorld(World):
    """
    Drova - Forsaken Kin is a top-down action RPG set in a celtic-inspired world powered by spirit energy.
    Choose a faction, uncover the fate of the old world, and decide what Drova becomes.
    """

    game = "Drova - Forsaken Kin"

    web = web_world.DrovaWebWorld()

    options_dataclass = drova_options.DrovaOptions
    options: drova_options.DrovaOptions

    location_name_to_id = locations.LOCATION_NAME_TO_ID
    item_name_to_id = items.ITEM_NAME_TO_ID

    item_name_groups = items.ITEM_NAME_GROUPS
    location_name_groups = locations.LOCATION_NAME_GROUPS

    origin_region_name = "Menu"

    topology_present = True

    # Mouth gate -> interior gate for this seed when teleporters are shuffled, else empty. Pure
    # client data: the pool is built so any permutation keeps everything reachable (see
    # teleporters.py), so this never touches regions or rules and UT does not need to mirror it.
    teleporter_map: dict[str, str] = {}

    def generate_early(self) -> None:
        # Universal Tracker regenerates this world locally to learn which locations the room has.
        # That regeneration must mirror the room the player connected to, not whatever their local
        # YAML happens to say, so any slot_data handed back through re_gen_passthrough overrides the
        # options that shape the location pool before anything is built from them.
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)
        if passthrough is not None:
            # A Choice stores an int but slot_data carries the key string, so map it back.
            self.options.faction.value = drova_options.Faction.options[passthrough["faction"]]
            self.options.suppress_vanilla_loot.value = int(passthrough["suppress_vanilla_loot"])
            # slot_data's category keys are the option names minus their randomize_ prefix.
            for category, enabled in passthrough["categories"].items():
                getattr(self.options, f"randomize_{category}").value = int(enabled)
            # Kill milestones change which synthetic locations exist, so UT must mirror them too.
            # Older rooms predate these keys; fall back to the current option value when absent.
            self.options.enemy_kill_checks.value = int(
                passthrough.get("enemy_kill_checks", self.options.enemy_kill_checks.value)
            )
            self.options.enemy_kill_interval.value = int(
                passthrough.get("enemy_kill_interval", self.options.enemy_kill_interval.value)
            )

        # Both of these are option mistakes rather than bugs, so fail early with an actionable message
        # instead of letting fill hit an impossible pool much later.
        enabled_locations = locations.enabled_location_data(self.options)

        if not enabled_locations:
            raise OptionError(
                f"Drova - Forsaken Kin ({self.player_name}): every location category is disabled. "
                f"Enable at least one of: {', '.join(sorted(locations.CATEGORY_TO_OPTION.values()))}."
            )

        progression_count = len(items.PROGRESSION_ITEM_NAMES)
        if len(enabled_locations) < progression_count:
            raise OptionError(
                f"Drova - Forsaken Kin ({self.player_name}): the enabled location categories only provide "
                f"{len(enabled_locations)} locations, but {progression_count} progression items must be placed. "
                f"Enable more location categories."
            )

        if self.options.randomize_teleporters:
            self.teleporter_map = teleporters.shuffled_teleporter_map(self)

    def create_regions(self) -> None:
        regions.create_and_connect_regions(self)
        locations.create_all_locations(self)

    def set_rules(self) -> None:
        rules.set_all_rules(self)

    def create_items(self) -> None:
        items.create_all_items(self)

    def create_item(self, name: str) -> items.DrovaItem:
        return items.create_item_by_name(self, name)

    def get_filler_item_name(self) -> str:
        return items.random_bonus_item_name(self)

    def interpret_slot_data(self, slot_data: Mapping[str, Any]) -> Mapping[str, Any]:
        # Universal Tracker protocol: returning a non-None value makes UT regenerate this world with
        # the value exposed as multiworld.re_gen_passthrough[game], which generate_early reads to
        # rebuild the room's options. slot_data already carries everything that shapes generation.
        return slot_data

    def fill_slot_data(self) -> Mapping[str, Any]:
        # Plain JSON types only. An Option instance or an Enum here corrupts the multidata.
        return {
            "seed_name": self.multiworld.seed_name,
            "death_link": bool(self.options.death_link),
            "suppress_vanilla_loot": bool(self.options.suppress_vanilla_loot),
            # Client-side grant sizing only; it never shapes generation, so UT does not re-apply it.
            "consumable_stack_size": self.options.consumable_stack_size.current_key,
            "faction": self.options.faction.current_key,
            "categories": {
                "chests": bool(self.options.randomize_chests),
                "containers": bool(self.options.randomize_containers),
                "quests": bool(self.options.randomize_quests),
                "critters": bool(self.options.randomize_critters),
                "resources": bool(self.options.randomize_resources),
                "caches": bool(self.options.randomize_caches),
                "pickups": bool(self.options.randomize_pickups),
                "traders": bool(self.options.randomize_traders),
                "muggings": bool(self.options.randomize_muggings),
            },
            # The client sends milestone k once the kill count reaches k * interval, for k in
            # 1..enemy_kill_checks. Location names are "Enemy Kills - {k}".
            "enemy_kill_checks": int(self.options.enemy_kill_checks.value),
            "enemy_kill_interval": int(self.options.enemy_kill_interval.value),
            # The client counts teacher-learned attribute points / talents and sends
            # "Attributes Learned - {k}" / "Talents Learned - {k}" up to these.
            "attribute_learn_checks": int(self.options.attribute_learn_checks.value),
            "attribute_learn_interval": int(self.options.attribute_learn_interval.value),
            "talent_learn_checks": int(self.options.talent_learn_checks.value),
            # Mouth gate -> interior gate. Empty when teleporters are not shuffled; the client
            # treats an absent/empty map as vanilla links.
            "teleporters": dict(self.teleporter_map),
        }

    def write_spoiler(self, spoiler_handle) -> None:
        if not self.teleporter_map:
            return
        spoiler_handle.write(f"\nTeleporter shuffle ({self.player_name}):\n")
        for mouth, interior in sorted(self.teleporter_map.items()):
            spoiler_handle.write(f"    {mouth} <-> {interior}\n")
