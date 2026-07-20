import collections

from Options import OptionError

from ..locations import CATEGORY_TO_OPTION, COUNT_GATED_CATEGORIES, LOCATION_DATA, MUGGING_CATEGORY
from .bases import DrovaTestBase

# Derived from the generated table, not pinned. The counts legitimately move whenever the extraction
# improves or Drova patches, and pinning them only produced failures that had to be hand-edited back
# to whatever the data already said, which tests nothing. What is worth asserting is the behaviour:
# every category has an option, each toggle contributes exactly its own locations, and the item pool
# matches the location count.
CATEGORY_COUNTS = collections.Counter(location["category"] for location in LOCATION_DATA)

# Milestone categories (kills, attributes learned, talents learned) are NOT driven by a randomize_
# toggle: they are count-gated by Range options and default to zero created, so the toggle-based
# tests below exclude them.
TOGGLE_CATEGORY_COUNTS = {
    category: count for category, count in CATEGORY_COUNTS.items() if category not in COUNT_GATED_CATEGORIES
}

# Locations of the faction not chosen are never created, so those counts are faction-dependent. Both
# quests and traders carry a faction, so the subtraction is per category, not just quests.
# Muggings are the exception: opposite-faction NPCs stay in the pool (marked EXCLUDED instead of
# dropped), so they never subtract.
NON_NEMETON_BY_CATEGORY = collections.Counter(
    location["category"] for location in LOCATION_DATA
    if location.get("faction") not in (None, "neutral", "nemeton")
    and location["category"] != MUGGING_CATEGORY
)
NON_NEMETON_TOTAL = sum(NON_NEMETON_BY_CATEGORY.values())

ALL_OFF = {option_name: False for option_name in CATEGORY_TO_OPTION.values()}


class TestLocationTable(DrovaTestBase):
    options = {"randomize_chests": True}
    run_default_tests = False

    def test_every_category_is_populated(self) -> None:
        for category in CATEGORY_TO_OPTION:
            with self.subTest(category):
                self.assertGreater(CATEGORY_COUNTS[category], 0)

    def test_every_category_has_an_option(self) -> None:
        # A category the client cannot be told to check, or an option with no locations behind it,
        # would both silently produce an unplayable seed. Kill milestones are optioned too, just via
        # the enemy_kill_checks Range rather than a toggle, so they are checked separately.
        self.assertEqual(set(TOGGLE_CATEGORY_COUNTS), set(CATEGORY_TO_OPTION))
        for category in COUNT_GATED_CATEGORIES:
            self.assertGreater(CATEGORY_COUNTS[category], 0, category)


class TestOnlyChests(DrovaTestBase):
    options = {**ALL_OFF, "randomize_chests": True}

    def test_only_chests_are_created(self) -> None:
        locations = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(len(locations), CATEGORY_COUNTS["Chest"])

    def test_pool_matches_locations_exactly(self) -> None:
        self.assertEqual(len(self.multiworld.itempool), len(self.multiworld.get_unfilled_locations(self.player)))


class TestAllCategories(DrovaTestBase):
    options = {option_name: True for option_name in CATEGORY_TO_OPTION.values()}

    def test_all_categories_are_created(self) -> None:
        # Everything except the quests and traders locked out by the default Nemeton faction. Kill
        # milestones are excluded: enemy_kill_checks is not a toggle and defaults to zero created.
        expected = sum(TOGGLE_CATEGORY_COUNTS.values()) - NON_NEMETON_TOTAL
        self.assertEqual(len(self.multiworld.get_unfilled_locations(self.player)), expected)

    def test_pool_matches_locations_exactly(self) -> None:
        self.assertEqual(len(self.multiworld.itempool), len(self.multiworld.get_unfilled_locations(self.player)))


class TestEachToggleAddsItsCategory(DrovaTestBase):
    options = {**ALL_OFF, "randomize_chests": True}
    run_default_tests = False
    auto_construct = False

    def test_each_toggle_adds_exactly_its_category(self) -> None:
        # Chests alone are the baseline, since something has to stay enabled to satisfy generate_early.
        self.options = {**ALL_OFF, "randomize_chests": True}
        self.world_setup()
        baseline = len(self.multiworld.get_unfilled_locations(self.player))
        self.assertEqual(baseline, CATEGORY_COUNTS["Chest"])

        for category, option_name in CATEGORY_TO_OPTION.items():
            if option_name == "randomize_chests":
                continue
            with self.subTest(category):
                self.options = {**ALL_OFF, "randomize_chests": True, option_name: True}
                self.world_setup()
                added = len(self.multiworld.get_unfilled_locations(self.player)) - baseline
                # The default Nemeton faction locks out the other faction's quests and traders.
                expected = CATEGORY_COUNTS[category] - NON_NEMETON_BY_CATEGORY[category]
                self.assertEqual(added, expected)


class TestMuggingFactionExclusion(DrovaTestBase):
    options = {**ALL_OFF, "randomize_chests": True, "randomize_muggings": True, "faction": "nemeton"}

    def test_opposite_faction_muggings_are_excluded(self) -> None:
        # Opposite-faction NPCs may be partly or fully unreachable, so their muggings stay in the
        # pool but must never hold progression or useful items; own-faction and neutral muggings
        # are ordinary locations.
        from BaseClasses import LocationProgressType

        mugging_faction = {
            location["name"]: location.get("faction", "neutral")
            for location in LOCATION_DATA
            if location["category"] == MUGGING_CATEGORY
        }
        seen_excluded = 0
        for location in self.multiworld.get_unfilled_locations(self.player):
            faction = mugging_faction.get(location.name)
            if faction is None:
                continue
            should_exclude = faction not in ("neutral", "nemeton")
            self.assertEqual(
                location.progress_type == LocationProgressType.EXCLUDED, should_exclude, location.name
            )
            seen_excluded += 1 if should_exclude else 0
        self.assertGreater(seen_excluded, 0)


class TestNoCategories(DrovaTestBase):
    options = dict(ALL_OFF)
    run_default_tests = False
    auto_construct = False

    def test_disabling_everything_raises(self) -> None:
        with self.assertRaises(OptionError):
            self.world_setup()


class TestTooFewLocations(DrovaTestBase):
    # 54 neutral + 2 Nemeton quests is fewer than the 62 progression items that must be placed.
    options = {**ALL_OFF, "randomize_quests": True, "faction": "nemeton"}
    run_default_tests = False
    auto_construct = False

    def test_fewer_locations_than_progression_items_raises(self) -> None:
        with self.assertRaises(OptionError):
            self.world_setup()
