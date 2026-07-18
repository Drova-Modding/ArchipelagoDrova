from ..locations import CATEGORY_TO_OPTION
from ..rules import (
    DOOR_KEY_RULES,
    HARALD_KEY_ITEM,
    RIVERBED_LOCATIONS,
    VERIFIED_CHEST_KEY_RULES,
)
from .bases import DrovaTestBase

ALL_RULES = {**VERIFIED_CHEST_KEY_RULES, **DOOR_KEY_RULES}
ALL_CATEGORIES_ON = {option_name: True for option_name in CATEGORY_TO_OPTION.values()}


class TestVerifiedChestKeyRules(DrovaTestBase):
    options = {"randomize_chests": True}

    def test_rule_table_names_are_real(self) -> None:
        # A typo in either column would silently produce a rule on nothing.
        for location_name, key_item_name in ALL_RULES.items():
            with self.subTest(location_name):
                self.assertIn(location_name, self.world.location_name_to_id)
                self.assertIn(key_item_name, self.world.item_name_to_id)

    def test_each_chest_depends_on_its_key(self) -> None:
        for location_name, key_item_name in VERIFIED_CHEST_KEY_RULES.items():
            with self.subTest(location_name):
                self.assertAccessDependency([location_name], [[key_item_name]], only_check_listed=True)


class TestDoorKeyRules(DrovaTestBase):
    # The gated area spans several container categories, so all of them must be on for every rule to attach.
    options = dict(ALL_CATEGORIES_ON)

    def test_riverbed_depends_on_the_harald_key(self) -> None:
        self.assertAccessDependency(
            sorted(RIVERBED_LOCATIONS), [[HARALD_KEY_ITEM]], only_check_listed=True
        )


class TestDoorRulesWithPartialCategories(DrovaTestBase):
    # With everything but chests off, most gated locations do not exist; generation must still work
    # and the surviving chest must still carry its rule.
    options = {"randomize_chests": True}

    def test_surviving_gated_chest_keeps_its_rule(self) -> None:
        created = {location.name for location in self.multiworld.get_locations(self.player)}
        self.assertIn("Riverbed - Chest 1", created)
        self.assertNotIn("Riverbed - Pickup 1", created)
        self.assertAccessDependency(["Riverbed - Chest 1"], [[HARALD_KEY_ITEM]], only_check_listed=True)


class TestRulesAbsentWithoutChests(DrovaTestBase):
    # The rules must not be set when the chest locations they attach to do not exist.
    options = {
        "randomize_chests": False,
        "randomize_containers": True,
    }
    run_default_tests = False

    def test_generation_succeeds_without_chest_locations(self) -> None:
        created = {location.name for location in self.multiworld.get_locations(self.player)}
        for location_name in VERIFIED_CHEST_KEY_RULES:
            self.assertNotIn(location_name, created)
