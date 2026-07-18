from ..locations import LOCATION_DATA
from .bases import DrovaTestBase

QUEST_DATA = [location for location in LOCATION_DATA if location["kind"] == "Quest"]

QUESTS_BY_FACTION = {
    faction: [location["name"] for location in QUEST_DATA if location["faction"] == faction]
    for faction in ("neutral", "nemeton", "ruinenlager")
}


class FactionTestBase(DrovaTestBase):
    faction: str
    run_default_tests = False

    def check_quests(self) -> None:
        created = {location.name for location in self.multiworld.get_locations(self.player)}
        other = "ruinenlager" if self.faction == "nemeton" else "nemeton"

        with self.subTest("Every neutral quest exists"):
            for name in QUESTS_BY_FACTION["neutral"]:
                self.assertIn(name, created)

        with self.subTest("Every quest of the chosen faction exists"):
            self.assertTrue(QUESTS_BY_FACTION[self.faction])
            for name in QUESTS_BY_FACTION[self.faction]:
                self.assertIn(name, created)

        with self.subTest("No quest of the locked faction exists"):
            self.assertTrue(QUESTS_BY_FACTION[other])
            for name in QUESTS_BY_FACTION[other]:
                self.assertNotIn(name, created)

    def check_datapackage(self) -> None:
        # Both factions' quests must always be in location_name_to_id even though only one side is
        # ever created, since that lookup is the datapackage.
        for names in QUESTS_BY_FACTION.values():
            for name in names:
                self.assertIn(name, self.world.location_name_to_id)


class TestNemeton(FactionTestBase):
    faction = "nemeton"
    options = {"faction": "nemeton", "randomize_quests": True}

    def test_only_nemeton_quests(self) -> None:
        self.check_quests()

    def test_both_factions_are_in_the_datapackage(self) -> None:
        self.check_datapackage()

    def test_slot_data_faction(self) -> None:
        self.assertEqual(self.world.fill_slot_data()["faction"], "nemeton")


class TestRuinenlager(FactionTestBase):
    faction = "ruinenlager"
    options = {"faction": "ruinenlager", "randomize_quests": True}

    def test_only_ruinenlager_quests(self) -> None:
        self.check_quests()

    def test_both_factions_are_in_the_datapackage(self) -> None:
        self.check_datapackage()

    def test_slot_data_faction(self) -> None:
        self.assertEqual(self.world.fill_slot_data()["faction"], "ruinenlager")


class TestRemnantsAlias(FactionTestBase):
    faction = "ruinenlager"
    options = {"faction": "remnants", "randomize_quests": True}

    def test_remnants_resolves_to_ruinenlager(self) -> None:
        # "Remnants" is the English name of the Ruinenlager, so players will reach for it.
        self.assertEqual(self.world.options.faction.current_key, "ruinenlager")
        self.check_quests()
