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


class RandomizeMuggings(Toggle):
    """
    Turn mugging an NPC (knocking them out in a brawl and opening their pockets) into a location
    check, once per NPC. Around 250 locations.

    NPCs of the faction you did not join stay in the pool but are excluded from progression and
    useful items: their camp may be partly or fully unreachable, so only filler can land on them.
    """

    display_name = "Randomize Muggings"


class StartWithTools(DefaultOnToggle):
    """
    Start with the tools for the two gathering minigames: the Silver Smasher pickaxe (mining) and
    an Old Spear (spearfishing). They arrive as starting items the moment the client connects, so
    ore veins and fishing spots - many of which are location checks - are workable from the start
    without first finding or buying the tools.
    """

    display_name = "Start With Tools"


class RandomizeTeleporters(Toggle):
    """
    Shuffle which cave each cave entrance leads into (an entrance randomizer).

    36 two-way cave links are shuffled among each other. Links stay two-way, so you can always walk
    back out the way you came in - no placement can strand you. Story-critical entrances are never
    shuffled: the Red Tower, the Library, both factions' home interiors, and quest dungeons keep
    their vanilla connections, and every shuffled entrance is reachable on foot, so this changes
    exploration without adding any logic requirements.
    """

    display_name = "Randomize Teleporters"


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


class AttributeLearnChecks(Range):
    """
    Turn milestones of attribute points bought at teachers into location checks. 0 disables them.

    With this set to N, milestone k is sent when your teacher-learned points reach k times
    Attribute Learn Interval. Only teacher learning counts: attribute points received as
    Archipelago items, perma-potions and level-ups do not advance the counter. The game teaches
    roughly 80 points in a full playthrough, so keep N times the interval at or below 80.
    """

    display_name = "Attribute Learn Checks"

    range_start = 0
    range_end = 80
    default = 0


class AttributeLearnInterval(Range):
    """
    Teacher-learned attribute points between milestones. Milestone k fires at k times this many
    points. Ignored when Attribute Learn Checks is 0.
    """

    display_name = "Attribute Learn Interval"

    range_start = 1
    range_end = 20
    default = 5


class TalentLearnChecks(Range):
    """
    Turn talents learned from teachers into location checks. 0 disables them.

    With this set to N, every talent learned (teacher menu or taught in dialogue) sends the next of
    N checks. Talents received as Archipelago items do not advance the counter.
    """

    display_name = "Talent Learn Checks"

    range_start = 0
    range_end = 10
    default = 0


class ConsumableStackSize(Choice):
    """
    How many units one consumable Archipelago item grants in-game.

    Applies to stackable consumables only (arrows, potions, food, throwables, traps, ore); gear,
    keys, recipes and quest items always grant exactly one. Each grant still varies around the
    chosen size so identical rewards do not feel like a metronome.

    - full: vanilla-ish stacks (20 arrows, 5 potions, 3 traps).
    - small: about half of full.
    - single: 1 unit per grant; ammo still comes in 5s, because a single arrow is not a reward.
    """

    display_name = "Consumable Stack Size"

    option_full = 0
    option_small = 1
    option_single = 2

    default = option_full


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
    randomize_muggings: RandomizeMuggings
    randomize_teleporters: RandomizeTeleporters
    start_with_tools: StartWithTools
    enemy_kill_checks: EnemyKillChecks
    enemy_kill_interval: EnemyKillInterval
    attribute_learn_checks: AttributeLearnChecks
    attribute_learn_interval: AttributeLearnInterval
    talent_learn_checks: TalentLearnChecks
    suppress_vanilla_loot: SuppressVanillaLoot
    consumable_stack_size: ConsumableStackSize
    death_link: DeathLink


option_groups = [
    OptionGroup(
        "Story",
        [Faction],
    ),
    OptionGroup(
        "Gameplay",
        [SuppressVanillaLoot, ConsumableStackSize, RandomizeTeleporters, StartWithTools],
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
            RandomizeMuggings,
            EnemyKillChecks,
            EnemyKillInterval,
            AttributeLearnChecks,
            AttributeLearnInterval,
            TalentLearnChecks,
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
