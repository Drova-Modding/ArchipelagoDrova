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


class TraderStackSize(Range):
    """
    How many units of a stocked stack are location checks. Ignored when Randomize Traders is off.

    A merchant slot that stocks several of an item sells several checks: the first purchase sends the
    slot's base location, the next ones send "- Unit 2" up to this many. Buying past it is ordinary
    vanilla shopping. Restocks continue where the last purchase stopped.

    5 is the extracted ceiling, so it cannot go higher; lower values trade trader checks for a shorter
    seed (1 means one check per slot, no matter how deep the stack).
    """

    display_name = "Trader Stack Size"

    range_start = 1
    range_end = 5
    default = 5


class RandomizeMuggings(Toggle):
    """
    Turn mugging an NPC (knocking them out in a brawl and opening their pockets) into a location
    check, once per NPC. Around 250 locations.

    NPCs of the faction you did not join stay in the pool but are excluded from progression and
    useful items: their camp may be partly or fully unreachable, so only filler can land on them.
    """

    display_name = "Randomize Muggings"


class RandomizeRunes(Toggle):
    """
    Shuffle the rune riddles: which of the nine drawn-rune patterns opens which rune door is
    re-rolled per seed, and every hint is updated to match - letter images are swapped, and the
    world-art hints (riddle plates, clue stones, painted boards) get a redrawn plate face showing
    the new pattern. The library floor riddle's stairs sequence is also re-rolled, with the
    books' clue images swapped to show the new sequence (its secret sequence stays vanilla).
    Every riddle stays solvable the intended way; you just cannot answer from memory of a
    previous run.
    """

    display_name = "Randomize Runes"


class StartWithTools(DefaultOnToggle):
    """
    Start with the tools for the two gathering minigames: the Bronze Pickaxe (mining) and an Old
    Spear (spearfishing). They arrive as starting items the moment the client connects, so ore veins
    and fishing spots - many of which are location checks - are workable from the start without
    first finding or buying the tools. Both are unbreakable, unlike the Silver Smasher, which is a
    better pickaxe that breaks on 80% of swings.
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

    Carnage Mode widens this to every pairable gate, story ones included, but does not turn it on:
    leave this off and a Carnage seed still has vanilla cave links.
    """

    display_name = "Randomize Teleporters"


class AllItems(Toggle):
    """
    Put every grantable item into the pool, including the ones normally held back.

    Drova marks a lot of real equipment as quest property (its buy and sell price are both zero),
    and the generator normally keeps those out so a check can never hand you story gear early:
    crafted and NPC armour sets, quest-gate props (seals, fragments, keys-in-all-but-name) and the
    world's lore notes and letters. Turning this on adds all of them to the loot pool, so you can
    find a spare armour set or a bundle you would otherwise only get from a quest.

    Genuinely unusable entries are still excluded either way - creature ability "weapons", boss
    ability scrolls, cosmetics and authoring leftovers - because they only show up as dead weight in
    the bag. This never changes logic (the world has almost none); it only widens what can drop.
    """

    display_name = "Allow All Items"


class Carnage(Toggle):
    """
    Maximum chaos, and the seed is allowed to break.

    Two safety rails come off:
      - The entrance shuffle, IF you turned Randomize Teleporters on, covers every pairable cave
        gate instead of the 36 safe ones - faction interiors, quest dungeons and the rest are all in
        the pool. Links stay two-way so you can always walk back, but an entrance can now drop you
        somewhere the story never meant you to reach. With that option off, cave links stay vanilla.
      - Vanilla loot suppression is forced on, and its protections are dropped: keys, quest items,
        energy crystals and riddle offerings are stripped from randomized containers along with
        everything else. Only the item's authored vanilla contents are removed, so anything you (or
        a cutscene) stashed in a chest is still safe - but a key can now be locked behind its own
        door, which is exactly the soft-lock the normal mode avoids.

    Because progression items can end up unreachable in the world, a Carnage seed may not be
    completable solo without other players sending those items. Turn it on for the spectacle, not
    for a guaranteed finish. Does not force Allow All Items - that stays a separate switch.
    """

    display_name = "Carnage Mode"


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


class QuestItemSupply(Range):
    """
    How many units of each quest-needed ordinary item the pool guarantees.

    Drova has plenty of fetch quests that ask for things the game does not mark as quest property:
    logs for Jendrik, three apples and five berries for Agilo, ten meat for Tiaa, silver ore through
    the whole pit, healing ointment for Larea, Basaltroot / Ruin Blossom / Mandragora for the herb
    hand-ins. With suppress_vanilla_loot on, the world stops handing those out, so the pool has to.

    This is the floor per item, on top of the single copy every distinct item already gets, and it is
    a minimum rather than a budget: common things still show up far more often through the ordinary
    weighted loot draw. It only applies once a seed has more locations than distinct items.

    0 disables the floor entirely.
    """

    display_name = "Quest Item Supply"

    range_start = 0
    range_end = 20
    default = 8


class PermanentHerbSupply(Range):
    """
    How many of each permanent stat herb the pool guarantees.

    Basaltroot, Brainfood Plant, Hawthorne, Cliff Lichen and Luminous Bass are quest hand-ins AND
    permanent +1 stat raises, so this is a power dial as much as a supply one: N here is up to +N to
    five different stats on top of the seed's ordinary +1 attribute rewards. Vanilla places about
    five of each.

    Separate from Quest Item Supply so a generous stock of logs and ore does not have to mean a
    generous stock of permanent stats. 0 leaves them as ordinary once-each items.
    """

    display_name = "Permanent Herb Supply"

    range_start = 0
    range_end = 20
    default = 5


class MandragoraSupply(Range):
    """
    How many Mandragora the pool guarantees.

    Henik's swamp questline asks for them, and vanilla grows eight - as Alraune creatures you kill,
    not pickups, which is why the randomizer never suppresses the vanilla ones. This is a top-up on
    a supply that already exists, so it can safely sit low; it has its own dial because a Mandragora
    sells for 100 gold and a large stock is real money.
    """

    display_name = "Mandragora Supply"

    range_start = 0
    range_end = 20
    default = 7


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


class DeathLinkMode(Choice):
    """
    What a DeathLink sent by another player does to you.

    Your own deaths always broadcast a DeathLink; this only decides what an incoming one costs.

    - kill: you die, exactly as if the world had killed you.
    - knockout: you black out where you stand for a few seconds instead - the state losing a brawl
      leaves you in. Nothing can hit you while you are down, and nothing reloads.

    Drova has no death penalty other than reloading your last save, which makes a kill expensive in a
    co-op room: every DeathLink costs the whole session since that save. Knockouts cost you the run of
    the fight you were in, and nothing else. The mod's config.json can force knockouts locally
    (`DeathLinkKnockout`) and set how long they last; a local setting can only soften a seed's
    DeathLink, never sharpen it.
    """

    display_name = "DeathLink Mode"

    option_kill = 0
    option_knockout = 1

    default = option_kill


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
    trader_stack_size: TraderStackSize
    randomize_muggings: RandomizeMuggings
    randomize_teleporters: RandomizeTeleporters
    randomize_runes: RandomizeRunes
    all_items: AllItems
    carnage: Carnage
    start_with_tools: StartWithTools
    enemy_kill_checks: EnemyKillChecks
    enemy_kill_interval: EnemyKillInterval
    attribute_learn_checks: AttributeLearnChecks
    attribute_learn_interval: AttributeLearnInterval
    talent_learn_checks: TalentLearnChecks
    suppress_vanilla_loot: SuppressVanillaLoot
    consumable_stack_size: ConsumableStackSize
    quest_item_supply: QuestItemSupply
    permanent_herb_supply: PermanentHerbSupply
    mandragora_supply: MandragoraSupply
    death_link: DeathLink
    death_link_mode: DeathLinkMode


option_groups = [
    OptionGroup(
        "Story",
        [Faction],
    ),
    OptionGroup(
        "Gameplay",
        [SuppressVanillaLoot, ConsumableStackSize, QuestItemSupply, PermanentHerbSupply, MandragoraSupply,
         RandomizeTeleporters, RandomizeRunes, AllItems, Carnage, StartWithTools],
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
            TraderStackSize,
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
