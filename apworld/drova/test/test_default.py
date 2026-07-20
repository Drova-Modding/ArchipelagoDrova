from ..items import BONUS_ITEM_NAMES, PROGRESSION_ITEM_NAMES
from ..locations import CATEGORY_TO_OPTION, GOAL_LOCATION_NAME, LOCATION_DATA, VICTORY_ITEM_NAME
from .bases import DrovaTestBase

# Derived, not pinned: the default seed is chests + containers + the quests the chosen faction can
# reach. Regenerating the data legitimately moves this, and a pinned number only ever gets edited to
# match whatever the data already said.
DEFAULT_CATEGORIES = ("Chest", "Container")
DEFAULT_LOCATION_COUNT = sum(
    1 for location in LOCATION_DATA
    if location["category"] in DEFAULT_CATEGORIES
    or (location["kind"] == "Quest" and location.get("faction") in ("neutral", "nemeton"))
)


class TestDefaultOptions(DrovaTestBase):
    # Explicitly restating the defaults, so that the default tests (fill, reachability) actually run here.
    options = {
        "faction": "nemeton",
        "randomize_chests": True,
        "randomize_containers": True,
        "randomize_quests": True,
        "randomize_resources": False,
        "randomize_caches": False,
        "randomize_pickups": False,
    }

    def test_default_location_count(self) -> None:
        self.assertEqual(len(self.multiworld.get_unfilled_locations(self.player)), DEFAULT_LOCATION_COUNT)

    def test_goal_event(self) -> None:
        goal = self.world.get_location(GOAL_LOCATION_NAME)

        with self.subTest("The goal location is an event, so it must have no address"):
            self.assertIsNone(goal.address)

        with self.subTest("The goal location holds the Victory event item"):
            self.assertEqual(goal.item.name, VICTORY_ITEM_NAME)
            self.assertIsNone(goal.item.code)
            self.assertTrue(goal.item.advancement)

    def test_every_progression_item_is_placed(self) -> None:
        with self.subTest("The data table still has the expected number of progression items"):
            self.assertEqual(len(PROGRESSION_ITEM_NAMES), 62)

        pool_names = [item.name for item in self.multiworld.itempool]
        for name in PROGRESSION_ITEM_NAMES:
            with self.subTest(name):
                self.assertIn(name, pool_names)

    def test_filler_item_name_is_repeatable(self) -> None:
        # get_filler_item_name must be able to be called any number of times, so every name it can
        # return is repeatable: XP/LP are granted as raw stats, the rest are stackable items.
        for _ in range(50):
            self.assertIn(self.world.get_filler_item_name(), BONUS_ITEM_NAMES)


class TestSlotData(DrovaTestBase):
    options = {
        "faction": "ruinenlager",
        "death_link": True,
    }

    def test_slot_data_shape(self) -> None:
        slot_data = self.world.fill_slot_data()

        with self.subTest("The client reads these two keys"):
            self.assertEqual(slot_data["seed_name"], self.multiworld.seed_name)
            self.assertIs(slot_data["death_link"], True)

        with self.subTest("Faction is emitted as its key string, not as an int or an Option"):
            self.assertEqual(slot_data["faction"], "ruinenlager")

        with self.subTest("Every category the world knows is reported to the client"):
            # The client gates on these, so a category missing here is a category it never checks.
            # Derived from CATEGORY_TO_OPTION rather than pinned, so adding a category cannot be
            # forgotten in slot_data without this failing.
            expected_keys = {
                option_name.replace("randomize_", "") for option_name in CATEGORY_TO_OPTION.values()
            }
            self.assertEqual(set(slot_data["categories"]), expected_keys)

        with self.subTest("Categories are plain bools"):
            for key, value in slot_data["categories"].items():
                self.assertIsInstance(value, bool, key)
            self.assertIs(slot_data["categories"]["chests"], True)
            self.assertIs(slot_data["categories"]["pickups"], False)

    def test_slot_data_is_json_safe(self) -> None:
        # An Option instance or an Enum in slot_data corrupts the multidata, so verify it round trips.
        import json

        slot_data = self.world.fill_slot_data()
        self.assertEqual(json.loads(json.dumps(slot_data)), dict(slot_data))
