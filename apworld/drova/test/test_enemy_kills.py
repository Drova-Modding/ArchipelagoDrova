import json

from ..locations import KILL_MILESTONE_CATEGORY, LOCATION_DATA
from .bases import DrovaTestBase

MILESTONE_NAMES = sorted(
    (location["name"] for location in LOCATION_DATA if location["category"] == KILL_MILESTONE_CATEGORY),
    key=lambda name: int(name.rsplit(" ", 1)[1]),
)


def _created_milestones(world_test) -> list[str]:
    return [
        location.name
        for location in world_test.multiworld.get_locations(world_test.player)
        if location.name.startswith("Enemy Kills - ")
    ]


class TestKillMilestonesDisabled(DrovaTestBase):
    options = {"randomize_chests": True, "enemy_kill_checks": 0}
    run_default_tests = False

    def test_no_milestone_locations_created(self) -> None:
        self.assertEqual(_created_milestones(self), [])

    def test_all_milestones_stay_in_the_datapackage(self) -> None:
        # Every milestone that could exist under any option must be in location_name_to_id even when
        # this seed creates none of them, since that lookup is the datapackage.
        self.assertEqual(len(MILESTONE_NAMES), 50)
        for name in MILESTONE_NAMES:
            with self.subTest(name):
                self.assertIn(name, self.world.location_name_to_id)


class TestKillMilestonesEnabled(DrovaTestBase):
    options = {"randomize_chests": True, "enemy_kill_checks": 5, "enemy_kill_interval": 20}

    def test_exactly_the_first_n_are_created(self) -> None:
        created = set(_created_milestones(self))
        self.assertEqual(created, {f"Enemy Kills - {k}" for k in range(1, 6)})
        self.assertNotIn("Enemy Kills - 6", created)

    def test_slot_data_carries_the_counter_config(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["enemy_kill_checks"], 5)
        self.assertEqual(slot_data["enemy_kill_interval"], 20)
        # Must round-trip as plain JSON or it corrupts the multidata.
        self.assertEqual(json.loads(json.dumps(slot_data)), dict(slot_data))


class TestKillMilestonesInNameGroups(DrovaTestBase):
    options = {"randomize_chests": True}
    run_default_tests = False

    def test_milestones_form_their_own_group(self) -> None:
        self.assertEqual(set(self.world.location_name_groups["Enemy Kills"]), set(MILESTONE_NAMES))
