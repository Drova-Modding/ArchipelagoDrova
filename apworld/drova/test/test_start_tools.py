from ..items import START_TOOL_NAMES
from .bases import DrovaTestBase


class TestStartToolsDefaultOn(DrovaTestBase):
    def test_tools_are_precollected(self) -> None:
        precollected = [item.name for item in self.multiworld.precollected_items[self.player]]
        for name in START_TOOL_NAMES:
            with self.subTest(name):
                self.assertIn(name, precollected)

    def test_tool_names_are_real_items(self) -> None:
        for name in START_TOOL_NAMES:
            self.assertIn(name, self.world.item_name_to_id)


class TestStartToolsOff(DrovaTestBase):
    options = {"start_with_tools": False}

    def test_no_tools_precollected(self) -> None:
        precollected = [item.name for item in self.multiworld.precollected_items[self.player]]
        for name in START_TOOL_NAMES:
            self.assertNotIn(name, precollected)
