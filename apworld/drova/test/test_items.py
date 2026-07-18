import collections

from ..items import (
    FILLER_ITEM_NAME,
    FILLER_ITEM_NAMES,
    ITEM_DATA,
    ITEM_NAME_GROUPS,
    ITEM_NAME_TO_ID,
    PROGRESSION_ITEM_NAMES,
    USEFUL_ITEM_NAMES,
)
from .bases import DrovaTestBase


class TestItemTable(DrovaTestBase):
    options = {"randomize_chests": True}
    run_default_tests = False

    def test_item_table_is_consistent(self) -> None:
        with self.subTest("Names and ids are unique"):
            self.assertEqual(len(ITEM_NAME_TO_ID), len(ITEM_DATA))
            self.assertEqual(len(set(ITEM_NAME_TO_ID.values())), len(ITEM_DATA))

        # The tables are generated from the game's own data by tools/gen_data.py, so exact counts are
        # expected to move when Drova updates or the classifier improves. Assert the invariants the
        # world actually depends on instead of pinning the numbers.
        with self.subTest("Every classification is populated"):
            self.assertTrue(PROGRESSION_ITEM_NAMES)
            self.assertTrue(USEFUL_ITEM_NAMES)
            self.assertTrue(FILLER_ITEM_NAMES)
            self.assertEqual(
                len(PROGRESSION_ITEM_NAMES) + len(USEFUL_ITEM_NAMES) + len(FILLER_ITEM_NAMES),
                len(ITEM_DATA),
            )

        with self.subTest("The classifications are disjoint"):
            self.assertFalse(set(PROGRESSION_ITEM_NAMES) & set(USEFUL_ITEM_NAMES))
            self.assertFalse(set(PROGRESSION_ITEM_NAMES) & set(FILLER_ITEM_NAMES))
            self.assertFalse(set(USEFUL_ITEM_NAMES) & set(FILLER_ITEM_NAMES))

        with self.subTest("The pool can fill a default seed"):
            # Progression must fit, and useful + filler must be able to top the pool up to any
            # reachable location count.
            self.assertGreater(len(USEFUL_ITEM_NAMES) + len(FILLER_ITEM_NAMES), len(PROGRESSION_ITEM_NAMES))

        with self.subTest("The filler item is filler and exists"):
            self.assertIn(FILLER_ITEM_NAME, FILLER_ITEM_NAMES)

    def test_item_name_groups(self) -> None:
        for group in ("Keys", "Flow Abilities", "Energy Crystals", "Weapons", "Armor"):
            with self.subTest(group):
                self.assertTrue(ITEM_NAME_GROUPS[group])
                for name in ITEM_NAME_GROUPS[group]:
                    self.assertIn(name, ITEM_NAME_TO_ID)

        with self.subTest("Keys, crystals and flow abilities are exactly the progression items"):
            progression_groups = (
                ITEM_NAME_GROUPS["Keys"] | ITEM_NAME_GROUPS["Flow Abilities"] | ITEM_NAME_GROUPS["Energy Crystals"]
            )
            self.assertEqual(progression_groups, set(PROGRESSION_ITEM_NAMES))


class TestSmallPoolFill(DrovaTestBase):
    # 201 chests: enough for all 62 progression items, then a subset of the useful items.
    options = {
        "randomize_chests": True,
        "randomize_containers": False,
        "randomize_quests": False,
        "randomize_resources": False,
        "randomize_caches": False,
        "randomize_pickups": False,
    }

    def test_pool_fills_exactly(self) -> None:
        self.assertEqual(len(self.multiworld.itempool), len(self.multiworld.get_unfilled_locations(self.player)))

    def test_no_filler_needed_yet(self) -> None:
        # 62 progression + 139 useful == 201, so the useful items alone finish the pool.
        counts = collections.Counter(item.name for item in self.multiworld.itempool)
        self.assertEqual(sum(counts.values()), 201)
        self.assertEqual(len([name for name in counts if name in USEFUL_ITEM_NAMES]), 201 - 62)
        self.assertEqual(counts[FILLER_ITEM_NAME], 0)

    def test_no_unintended_duplicates(self) -> None:
        # Nothing repeats while there are still distinct items left to place.
        counts = collections.Counter(item.name for item in self.multiworld.itempool)
        self.assertEqual(max(counts.values()), 1)


class TestLargePoolFill(DrovaTestBase):
    options = {
        "randomize_chests": True,
        "randomize_containers": True,
        "randomize_quests": True,
        "randomize_resources": True,
        "randomize_caches": True,
        "randomize_pickups": True,
    }
    run_default_tests = False

    def test_pool_fills_exactly(self) -> None:
        self.assertEqual(len(self.multiworld.itempool), len(self.multiworld.get_unfilled_locations(self.player)))

    def test_repeatable_filler_covers_the_overflow(self) -> None:
        # There are far more locations than distinct items, so the rest must be repeatable filler.
        location_count = len(self.multiworld.get_unfilled_locations(self.player))
        counts = collections.Counter(item.name for item in self.multiworld.itempool)

        with self.subTest("Every distinct item was used"):
            self.assertEqual(len([name for name in counts if counts[name] >= 1]), len(ITEM_DATA))

        with self.subTest("The overflow is all Experience Boost"):
            self.assertEqual(counts[FILLER_ITEM_NAME], location_count - len(ITEM_DATA) + 1)
