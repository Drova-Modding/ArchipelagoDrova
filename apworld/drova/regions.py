from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Region

if TYPE_CHECKING:
    from .world import DrovaWorld

HUB_REGION = "Drova"

# Roughly a fifth of the extracted containers could not be resolved to a named area and fall back to
# their chunk coordinates ("Wilds 9_31"). 95 chunk names would be noise, so they share one region.
WILDS_REGION = "The Wilds"
_WILDS_AREA_PREFIX = "Wilds "


def region_for_area(area: str) -> str:
    if not area or area.startswith(_WILDS_AREA_PREFIX):
        return WILDS_REGION
    return area


def all_region_names() -> list[str]:
    """Every region except the origin, in a stable order."""
    # Imported here rather than at module level: locations.py needs region_for_area from this module,
    # so a module level import back into it would be circular.
    from . import locations

    return [HUB_REGION, WILDS_REGION, *locations.AREA_REGIONS]


def create_and_connect_regions(world: DrovaWorld) -> None:
    create_all_regions(world)
    connect_regions(world)


def create_all_regions(world: DrovaWorld) -> None:
    world.multiworld.regions += [
        Region(name, world.player, world.multiworld) for name in [world.origin_region_name, *all_region_names()]
    ]


def connect_regions(world: DrovaWorld) -> None:
    # Drova has a real, connected map, but we have no verified connectivity data for it: the static
    # extraction recovered which area a container sits in, not which areas border each other or what
    # gates the borders. Inventing a connectivity graph would produce confidently wrong logic, so every
    # area hangs directly off the hub with no requirements. Real gating belongs in location rules
    # (see rules.py), where it can be added incrementally as verified data arrives, rather than being
    # guessed at here.
    menu = world.get_region(world.origin_region_name)
    hub = world.get_region(HUB_REGION)
    menu.connect(hub, "Wake Up in Drova")

    for region_name in all_region_names():
        if region_name == HUB_REGION:
            continue
        hub.connect(world.get_region(region_name), f"{HUB_REGION} to {region_name}")
