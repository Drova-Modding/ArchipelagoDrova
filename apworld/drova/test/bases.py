from test.bases import WorldTestBase

from ..world import DrovaWorld


class DrovaTestBase(WorldTestBase):
    game = "Drova - Forsaken Kin"
    world: DrovaWorld
