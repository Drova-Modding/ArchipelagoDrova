from dataclasses import dataclass

from Options import Choice, DeathLink, DefaultOnToggle, OptionGroup, PerGameCommonOptions, Range, Toggle


class Faction(Choice):
    """
    The faction you intend to join.

    Drova forks partway through the story: joining one faction permanently locks the other's questline.
    Only quests that are neutral or belong to the chosen faction are added as locations.
    "Remnants" is the English name of the Ruinenlager.
    """

    display_name = "Faction"

    option_nemeton = 0
    option_ruinenlager = 1

    alias_remnants = option_ruinenlager

    default = option_nemeton


class RandomizeChests(DefaultOnToggle):
    """
    Randomize the contents of lockable chests. 201 locations.
    """

    display_name = "Randomize Chests"


class RandomizeContainers(DefaultOnToggle):
    """
    Randomize the contents of barrels, crates, sacks and similar lootable containers. 196 locations.
    """

    display_name = "Randomize Containers"


class RandomizeQuests(DefaultOnToggle):
    """
    Turn quest completions into locations. 60 locations, minus the quests of the faction you did not join.
    """

    display_name = "Randomize Quests"


class SuppressVanillaLoot(DefaultOnToggle):
    """
    Randomized containers give up their normal contents, so a check hands you the Archipelago item
    instead of the Archipelago item plus the vanilla one.

    Keys, quest items and energy crystals are always kept, even with this on. This world has almost no
    logic, so the generator is told nearly every location is reachable from the start, which is only
    true while you still find the vanilla items progression physically depends on. Suppressing those
    could put a key behind the door it opens and make the seed unbeatable, so they are never stripped.

    On by default: a check hands you only its Archipelago item, the way most randomizers behave. Turn
    it off to keep the vanilla contents as well (an easier, more forgiving seed).
    """

    display_name = "Suppress Vanilla Loot"


class RandomizeCritters(Toggle):
    """
    Randomize ambient wildlife and animal carcasses: crows, small birds, dead boars and the like.
    134 locations.
    Off by default because hunting birds is a different activity from opening chests, and some
    flocks put a dozen checks in a single bush.
    """

    display_name = "Randomize Critters"


class RandomizeResources(Toggle):
    """
    Randomize harvestable resource nodes such as ore veins and herbs. 361 locations.
    """

    display_name = "Randomize Resources"


class RandomizeCaches(Toggle):
    """
    Randomize hidden caches and stashes. 978 locations.
    """

    display_name = "Randomize Caches"


class RandomizePickups(Toggle):
    """
    Randomize loose items lying around in the world. 3125 locations.
    This is by far the largest category and makes for a very long seed.
    """

    display_name = "Randomize Pickups"


class RandomizeTraders(Toggle):
    """
    Turn buying an item from a merchant into a location check. Around a thousand slots across the
    game's traders, minus the merchants of the faction you did not join.

    Trader stock is authored, not random, so each slot is a real location. Buying the item sends the
    check; the vanilla item is still added to your inventory as normal.
    """

    display_name = "Randomize Traders"


class EnemyKillChecks(Range):
    """
    Turn milestones of enemy kills into location checks. 0 disables them.

    Runtime enemy drops can never be Archipelago locations (they have no identity until they spawn),
    but a running kill count can: with this set to N, defeating enemies sends up to N checks, one each
    time your total kills reach a multiple of Enemy Kill Interval. These are extra locations reached by
    playing normally, so they never gate anything. The last check needs N * Enemy Kill Interval kills.
    """

    display_name = "Enemy Kill Checks"

    range_start = 0
    range_end = 50
    default = 0


class EnemyKillInterval(Range):
    """
    Kills between enemy-kill milestones. Milestone k fires at k times this many kills. Ignored when
    Enemy Kill Checks is 0. Larger values spread the checks across a longer playthrough.
    """

    display_name = "Enemy Kill Interval"

    range_start = 1
    range_end = 100
    default = 10


@dataclass
class DrovaOptions(PerGameCommonOptions):
    faction: Faction
    randomize_chests: RandomizeChests
    randomize_containers: RandomizeContainers
    randomize_quests: RandomizeQuests
    randomize_critters: RandomizeCritters
    randomize_resources: RandomizeResources
    randomize_caches: RandomizeCaches
    randomize_pickups: RandomizePickups
    randomize_traders: RandomizeTraders
    enemy_kill_checks: EnemyKillChecks
    enemy_kill_interval: EnemyKillInterval
    suppress_vanilla_loot: SuppressVanillaLoot
    death_link: DeathLink


option_groups = [
    OptionGroup(
        "Story",
        [Faction],
    ),
    OptionGroup(
        "Gameplay",
        [SuppressVanillaLoot],
    ),
    OptionGroup(
        "Location Pool",
        [
            RandomizeChests,
            RandomizeContainers,
            RandomizeQuests,
            RandomizeCritters,
            RandomizeResources,
            RandomizeCaches,
            RandomizePickups,
            RandomizeTraders,
            EnemyKillChecks,
            EnemyKillInterval,
        ],
    ),
]

option_presets = {
    "minimal": {
        "randomize_chests": True,
        "randomize_containers": False,
        "randomize_quests": False,
        "randomize_critters": False,
        "randomize_resources": False,
        "randomize_caches": False,
        "randomize_pickups": False,
    },
    "completionist": {
        "randomize_chests": True,
        "randomize_containers": True,
        "randomize_quests": True,
        "randomize_critters": True,
        "randomize_resources": True,
        "randomize_caches": True,
        "randomize_pickups": True,
    },
}
