from ..teleporters import TELEPORTER_PAIRS
from .bases import DrovaTestBase


class TestTeleporterPool(DrovaTestBase):
    def test_pool_is_well_formed(self) -> None:
        mouths = [pair["mouth"] for pair in TELEPORTER_PAIRS]
        interiors = [pair["interior"] for pair in TELEPORTER_PAIRS]
        with self.subTest("every gate appears exactly once and on exactly one side"):
            self.assertEqual(len(mouths), len(set(mouths)))
            self.assertEqual(len(interiors), len(set(interiors)))
            self.assertFalse(set(mouths) & set(interiors))
        with self.subTest("the excluded story gates never enter the pool"):
            for gate in mouths + interiors:
                self.assertNotIn("RedTower", gate)
                self.assertNotIn("Bib_", gate)

    def test_off_by_default_and_absent_from_slot_data(self) -> None:
        self.assertFalse(self.world.options.randomize_teleporters)
        self.assertEqual(self.world.fill_slot_data()["teleporters"], {})


class TestTeleporterShuffle(DrovaTestBase):
    options = {"randomize_teleporters": True}

    def test_slot_data_is_a_permutation_of_the_pool(self) -> None:
        shuffled = self.world.fill_slot_data()["teleporters"]
        self.assertEqual(set(shuffled.keys()), {pair["mouth"] for pair in TELEPORTER_PAIRS})
        self.assertEqual(
            sorted(shuffled.values()), sorted(pair["interior"] for pair in TELEPORTER_PAIRS)
        )
