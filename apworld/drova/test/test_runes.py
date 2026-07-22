from ..runes import RUNE_NAMES
from .bases import DrovaTestBase


class TestRunesDefaultOff(DrovaTestBase):
    def test_pool_is_well_formed(self) -> None:
        # All nine pattern-check doors: letter hints swap by sprite name, world-art hints get
        # overdrawn plate faces from the client's RuneHintOverlay.
        self.assertEqual(
            RUNE_NAMES,
            [
                "DrawRune_AuwaldPuzzle",
                "DrawRune_CityPuzzle",
                "DrawRune_LibraryPuzzleA",
                "DrawRune_LibraryPuzzleB",
                "DrawRune_LibraryPuzzleC",
                "DrawRune_LunaTemplePuzzle",
                "DrawRune_RedTowerPuzzle",
                "DrawRune_RäuberPuzzle_A",
                "DrawRune_RäuberPuzzle_B",
            ],
        )
        with self.subTest("the freestyle PaperChase drawing is never in the pool"):
            self.assertNotIn("DrawRune_PaperChase", RUNE_NAMES)

    def test_absent_from_slot_data_by_default(self) -> None:
        self.assertFalse(self.world.options.randomize_runes)
        self.assertEqual(self.world.fill_slot_data()["runes"], {})


class TestRuneShuffle(DrovaTestBase):
    options = {"randomize_runes": True}

    def test_slot_data_is_a_permutation(self) -> None:
        shuffled = self.world.fill_slot_data()["runes"]
        self.assertEqual(set(shuffled.keys()), set(RUNE_NAMES))
        self.assertEqual(sorted(shuffled.values()), sorted(RUNE_NAMES))
