from ..teleporters import TELEPORTER_PAIRS, TELEPORTER_PAIRS_FULL
from .bases import DrovaTestBase


def _well_formed(test, pairs) -> None:
    mouths = [pair["mouth"] for pair in pairs]
    interiors = [pair["interior"] for pair in pairs]
    test.assertEqual(len(mouths), len(set(mouths)))
    test.assertEqual(len(interiors), len(set(interiors)))
    test.assertFalse(set(mouths) & set(interiors))


class TestTeleporterPool(DrovaTestBase):
    def test_pool_is_well_formed(self) -> None:
        mouths = [pair["mouth"] for pair in TELEPORTER_PAIRS]
        interiors = [pair["interior"] for pair in TELEPORTER_PAIRS]
        with self.subTest("every gate appears exactly once and on exactly one side"):
            _well_formed(self, TELEPORTER_PAIRS)
        with self.subTest("the excluded story gates never enter the safe pool"):
            for gate in mouths + interiors:
                self.assertNotIn("RedTower", gate)
                self.assertNotIn("Bib_", gate)

    def test_full_pool_is_well_formed_and_superset(self) -> None:
        with self.subTest("full pool is well formed"):
            _well_formed(self, TELEPORTER_PAIRS_FULL)
        with self.subTest("the safe pool's gates are all in the full pool"):
            safe = {p["mouth"] for p in TELEPORTER_PAIRS} | {p["interior"] for p in TELEPORTER_PAIRS}
            full = {p["mouth"] for p in TELEPORTER_PAIRS_FULL} | {p["interior"] for p in TELEPORTER_PAIRS_FULL}
            self.assertLessEqual(safe, full)
        with self.subTest("the full pool actually adds the excluded story/faction gates"):
            full = {p["mouth"] for p in TELEPORTER_PAIRS_FULL} | {p["interior"] for p in TELEPORTER_PAIRS_FULL}
            self.assertTrue(any("Bib_" in g for g in full))
            self.assertTrue(any("Druid" in g for g in full))

    def test_off_by_default_and_absent_from_slot_data(self) -> None:
        self.assertFalse(self.world.options.randomize_teleporters)
        self.assertFalse(self.world.options.carnage)
        self.assertEqual(self.world.fill_slot_data()["teleporters"], {})


class TestTeleporterShuffle(DrovaTestBase):
    options = {"randomize_teleporters": True}

    def test_slot_data_is_a_permutation_of_the_pool(self) -> None:
        shuffled = self.world.fill_slot_data()["teleporters"]
        self.assertEqual(set(shuffled.keys()), {pair["mouth"] for pair in TELEPORTER_PAIRS})
        self.assertEqual(
            sorted(shuffled.values()), sorted(pair["interior"] for pair in TELEPORTER_PAIRS)
        )


class TestCarnageTeleporters(DrovaTestBase):
    # Carnage forces the full shuffle even with the ordinary toggle left off, and forces suppression
    # on even when the seed explicitly turned it off.
    options = {"carnage": True, "randomize_teleporters": False, "suppress_vanilla_loot": False}

    def test_slot_data_is_a_permutation_of_the_full_pool(self) -> None:
        shuffled = self.world.fill_slot_data()["teleporters"]
        self.assertEqual(set(shuffled.keys()), {pair["mouth"] for pair in TELEPORTER_PAIRS_FULL})
        self.assertEqual(
            sorted(shuffled.values()), sorted(pair["interior"] for pair in TELEPORTER_PAIRS_FULL)
        )

    def test_carnage_forces_suppression_and_flags_slot_data(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["carnage"])
        # Suppression was explicitly off in the yaml; carnage overrides it to on.
        self.assertTrue(slot_data["suppress_vanilla_loot"])
        self.assertTrue(self.world.options.suppress_vanilla_loot)
