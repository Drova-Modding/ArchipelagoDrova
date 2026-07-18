from unittest import mock

from BaseClasses import MultiWorld

from ..locations import CATEGORY_TO_OPTION
from .bases import DrovaTestBase

ALL_OFF = {option_name: False for option_name in CATEGORY_TO_OPTION.values()}

# What the "room" was generated with. Deliberately disagrees with LOCAL_YAML_OPTIONS on the faction,
# on every category toggle that matters, and on suppress_vanilla_loot, so a regeneration that leaks
# any local value produces a visibly different world.
ROOM_OPTIONS = {
    **ALL_OFF,
    "faction": "ruinenlager",
    "randomize_quests": True,
    "randomize_pickups": True,
    "suppress_vanilla_loot": True,
}

# What the tracker user's local YAML says. Chests stay on because generate_early rejects a world
# with every category disabled, and that guard must not fire for the local values anyway.
LOCAL_YAML_OPTIONS = {
    **ALL_OFF,
    "faction": "nemeton",
    "randomize_chests": True,
    "suppress_vanilla_loot": False,
}


class TestInterpretSlotData(DrovaTestBase):
    options = dict(ROOM_OPTIONS)
    run_default_tests = False

    def test_returns_slot_data_unchanged(self) -> None:
        # Universal Tracker's contract: a non-None return value triggers a regeneration with that
        # value in multiworld.re_gen_passthrough. slot_data already holds every option that shapes
        # the location pool, so it is handed back as-is.
        slot_data = self.world.fill_slot_data()
        self.assertEqual(self.world.interpret_slot_data(slot_data), slot_data)


class TestRegenFollowsPassthrough(DrovaTestBase):
    options = dict(LOCAL_YAML_OPTIONS)
    run_default_tests = False
    auto_construct = False

    def world_setup_with_passthrough(self, passthrough: dict) -> None:
        # world_setup builds the MultiWorld and immediately runs the generation steps, so the only
        # window to plant re_gen_passthrough before generate_early reads it is right after
        # set_options constructs the world instances. Universal Tracker itself sets the attribute
        # at the equivalent point of its regeneration pass.
        original_set_options = MultiWorld.set_options

        def plant_passthrough(multiworld: MultiWorld, args) -> None:
            original_set_options(multiworld, args)
            multiworld.re_gen_passthrough = {self.game: passthrough}

        with mock.patch.object(MultiWorld, "set_options", plant_passthrough):
            self.world_setup()

    def test_regen_recreates_the_room_not_the_local_yaml(self) -> None:
        # First generation plays the part of the room the tracker connects to.
        self.options = dict(ROOM_OPTIONS)
        self.world_setup()
        room_slot_data = self.world.fill_slot_data()
        room_locations = {location.name for location in self.multiworld.get_locations(self.player)}
        passthrough = self.world.interpret_slot_data(room_slot_data)

        # Second generation is the tracker's local pass: a YAML that disagrees on everything, with
        # the room's slot_data passed through. The passthrough must win completely.
        self.options = dict(LOCAL_YAML_OPTIONS)
        self.world_setup_with_passthrough(passthrough)
        regen_locations = {location.name for location in self.multiworld.get_locations(self.player)}

        self.assertEqual(regen_locations, room_locations)

        with self.subTest("The regenerated options mirror the room"):
            # seed_name differs by construction, so compare everything the options control instead.
            regen_slot_data = self.world.fill_slot_data()
            for key in ("faction", "suppress_vanilla_loot", "categories"):
                self.assertEqual(regen_slot_data[key], room_slot_data[key], key)

    def test_without_passthrough_the_local_yaml_wins(self) -> None:
        # No re_gen_passthrough means a normal generation, so the local options must be untouched.
        self.options = dict(LOCAL_YAML_OPTIONS)
        self.world_setup()
        self.assertEqual(self.world.options.faction.current_key, "nemeton")
        self.assertTrue(self.world.options.randomize_chests)
        self.assertFalse(self.world.options.randomize_pickups)
