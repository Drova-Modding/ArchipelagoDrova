from ..locations import LOCATION_DATA, TRADER_CATEGORY, TRADER_GROUP
from .bases import DrovaTestBase

TRADER_DATA = [location for location in LOCATION_DATA if location["category"] == TRADER_CATEGORY]

TRADERS_BY_FACTION = {
    faction: [location["name"] for location in TRADER_DATA if location["faction"] == faction]
    for faction in ("neutral", "nemeton", "ruinenlager")
}


class TestTraderTable(DrovaTestBase):
    options = {"randomize_chests": True}
    run_default_tests = False

    def test_traders_exist_and_are_faction_tagged(self) -> None:
        # The extractor should have found merchant stock; a category with no locations behind it
        # would silently produce an unplayable seed when enabled.
        self.assertTrue(TRADER_DATA)
        allowed = {"neutral", "nemeton", "ruinenlager"}
        for location in TRADER_DATA:
            with self.subTest(location["name"]):
                self.assertIn(location["faction"], allowed)

    def test_all_traders_in_the_datapackage(self) -> None:
        for names in TRADERS_BY_FACTION.values():
            for name in names:
                self.assertIn(name, self.world.location_name_to_id)

    def test_traders_form_their_own_group(self) -> None:
        self.assertEqual(
            set(self.world.location_name_groups[TRADER_GROUP]),
            {location["name"] for location in TRADER_DATA},
        )


class TestTradersDisabled(DrovaTestBase):
    options = {"randomize_chests": True, "randomize_traders": False}
    run_default_tests = False

    def test_no_trader_locations_created(self) -> None:
        created = {location.name for location in self.multiworld.get_locations(self.player)}
        for location in TRADER_DATA:
            self.assertNotIn(location["name"], created)


class TestTradersFactionFiltered(DrovaTestBase):
    options = {"randomize_chests": True, "randomize_traders": True, "faction": "nemeton"}
    run_default_tests = False

    def test_only_this_factions_traders(self) -> None:
        created = {location.name for location in self.multiworld.get_locations(self.player)}
        for name in TRADERS_BY_FACTION["neutral"] + TRADERS_BY_FACTION["nemeton"]:
            self.assertIn(name, created)
        for name in TRADERS_BY_FACTION["ruinenlager"]:
            self.assertNotIn(name, created)

    def test_slot_data_reports_traders(self) -> None:
        self.assertIs(self.world.fill_slot_data()["categories"]["traders"], True)
