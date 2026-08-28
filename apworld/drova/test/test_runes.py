from ..runes import FLOOR_RUNE_NAMES, FLOOR_SECRET_SEQUENCE, FLOOR_VANILLA_SEQUENCE, RUNE_NAMES
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

    def test_floor_pool_is_well_formed(self) -> None:
        self.assertEqual(FLOOR_RUNE_NAMES, ["Energy", "Fire", "Root", "Sound", "Summon"])
        self.assertEqual(FLOOR_VANILLA_SEQUENCE, ["Energy", "Root", "Fire"])
        # Book IV's prose hints the secret in this order; it is never randomized.
        self.assertEqual(FLOOR_SECRET_SEQUENCE, ["Fire", "Sound", "Summon"])

    def test_absent_from_slot_data_by_default(self) -> None:
        self.assertFalse(self.world.options.randomize_runes)
        self.assertEqual(self.world.fill_slot_data()["runes"], {})
        self.assertEqual(self.world.fill_slot_data()["floor_runes"], [])


class TestRuneShuffle(DrovaTestBase):
    options = {"randomize_runes": True}

    def test_slot_data_is_a_permutation(self) -> None:
        shuffled = self.world.fill_slot_data()["runes"]
        self.assertEqual(set(shuffled.keys()), set(RUNE_NAMES))
        self.assertEqual(sorted(shuffled.values()), sorted(RUNE_NAMES))

    def test_floor_sequence_is_valid(self) -> None:
        sequence = self.world.fill_slot_data()["floor_runes"]
        self.assertEqual(len(sequence), 3)
        self.assertEqual(len(set(sequence)), 3)
        self.assertTrue(set(sequence) <= set(FLOOR_RUNE_NAMES))
        # A stairs sequence equal to the secret would make one input open both doors and the
        # secret's unswappable text hint ambiguous.
        self.assertNotEqual(sequence, FLOOR_SECRET_SEQUENCE)
