"""Generate the shared Archipelago id tables for Drova.

Single source of truth for both sides:
  - apworld/drova/data/items.json / locations.json   consumed by the Python world
  - ArchipelagoDrova/Data/ItemTable.g.cs / LocationTable.g.cs   consumed by the C# mod

Item identity is the game's own readable id (Item.ReadableId), resolvable at runtime with
SubDatabase_Item.GetItemByReadableId. AP item names are the prettified readable id; all 1112
are unique and prettify without collision.

Location identity is GuidComponent._guidString, which is baked into the scene asset and is the
same key the save file uses (verified: it reproduces the save's "GO#<guid>" map).

IDs must NEVER be renumbered: they are the network datapackage, and clients/trackers cache them
by checksum. Both id maps are therefore FROZEN files keyed by the stable game identity
(readable id / guid) rather than by name or list order, so renaming a location or reordering the
input cannot shift an existing id. Regeneration only ever appends new keys.

Run:  python tools/gen_data.py
"""

import json
import os
import sys

# AP allows 1..2**53-1 but recommends staying inside 2**31-1 so 32-bit ints suffice.
ITEM_BASE_ID = 4762000
LOCATION_BASE_ID = 4800000

# A trader slot with a stock stack of N sells min(N, this) checks; the rest is vanilla shopping.
# The distribution is heavy-tailed (median stack 1, max 160 povage), so uncapped would balloon the
# trader category from ~900 to ~6100 pure money-pump locations.
TRADER_UNIT_CAP = 5

# Enemy-kill milestone locations are synthetic: they have no world object and are not extracted.
# The client sends them from a persistent kill count. Every milestone that could exist under any
# option must be in the datapackage, so a fixed maximum is baked in and the apworld creates only
# the first enemy_kill_checks of them per seed. Raising this later only appends new frozen ids.
MAX_KILL_MILESTONES = 50

# Teacher-learning milestones, same synthetic model: the client counts attribute points bought at
# teachers (LearnService.ApplyData) and talents learned (TalentActorModule.LearnTalent - the AP
# item grants go through ForceLearnTalent and never count). Maxima match what the game can teach:
# ~80 attribute points and a handful of talents.
MAX_ATTRIBUTE_MILESTONES = 80
MAX_TALENT_MILESTONES = 10

# Standard Steam location; override with the DROVA_PATH env var if your install is elsewhere.
GAME_DIR = os.environ.get("DROVA_PATH", r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin")
READABLE_IDS = os.path.join(GAME_DIR, "Mods", "readable_ids.txt")
# Area loca key -> English display name. Location areas use the display names; the client uses this
# map to translate the save's PlayerAreaLocaKey into the display name for the progress highlight.
AREAS_LOC = os.path.join(GAME_DIR, "Drova_Data", "StreamingAssets", "Localization", "en", "AreaNames_en.loc")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSON_DIR = os.path.join(REPO, "apworld", "drova", "data")
OUT_CS_DIR = os.path.join(REPO, "ArchipelagoDrova", "Data")
OUT_CS = os.path.join(OUT_CS_DIR, "ItemTable.g.cs")
OUT_CS_LOC = os.path.join(OUT_CS_DIR, "LocationTable.g.cs")

# Frozen, append-only id assignments. Committed to the repo. Never edit by hand.
FROZEN_DIR = os.path.join(REPO, "tools", "frozen")
FROZEN_ITEM_IDS = os.path.join(FROZEN_DIR, "item_ids.json")       # readable id / synthetic name -> id
FROZEN_LOCATION_IDS = os.path.join(FROZEN_DIR, "location_ids.json")  # container guid / quest key -> id

# Produced by the static bundle extractor (tools/extract_locations/).
LOCATIONS_SRC = os.path.join(REPO, "tools", "extracted", "ap_locations.json")
QUESTS_SRC = os.path.join(REPO, "tools", "extracted", "ap_quests.json")

# Trader stock, keyed "<traderGuid>:<itemGuid>" (tools/extract_locations/extract_traders.py). Each
# record carries a unique trader_label, the item's readable id, an area, and a proven faction.
TRADERS_SRC = os.path.join(REPO, "tools", "extracted", "traders.json")

# Per-container authored contents (tools/extract_locations/extract_chest_slots.py): guid ->
# {object, slots:[{readable_id, amount, garbage, quest}]}. A container whose fixed loot holds K
# eligible items gets K locations instead of 1 (the base location stays untouched as slot 1;
# slots 2..K are appended), so a chest with three items sends three checks when opened.
CHEST_SLOTS_SRC = os.path.join(REPO, "tools", "extracted", "chest_slots.json")

# Per-item buy/sell values (tools/extract_locations/extract_item_values.py). The game defines
# Item.IsQuestItem as buy == 0 && sell == 0; classify() uses this to keep quest property (talisman
# stage stones, lore letters, story props, NPC outfits) out of the grantable pool. Keys, charged
# crystals and flow abilities are classified before the value check and are unaffected: their pool
# copies are intentionally redundant.
ITEM_VALUES_SRC = os.path.join(REPO, "tools", "extracted", "item_values.json")

# Vanilla loot frequency (tools/extract_locations/extract_loot_distribution.py): how many times a
# full sweep of Drova hands the player each item, counted over world pickups, destroyable loot
# tables, resource spots and authored container slots. Carried into items.json as `world_count` so
# the apworld can weight its repeatable overflow the way the game weights its own loot instead of
# drawing uniformly (which made a 5x stack of healing potions as likely as a handful of berries).
LOOT_DIST_SRC = os.path.join(REPO, "tools", "extracted", "loot_distribution.json")

# Items every quest/dialogue graph references (tools/extract_locations/extract_quest_items.py).
# Quests routinely ask for things the game does NOT flag as quest property - logs for Jendrik's
# woodpile, silver ore for half the prologue, mushrooms for "Missing". With suppression on, the
# vanilla copies are gone, so the ONLY way to hand one over is to receive it from the pool. Rather
# than pull those objects out of the location table (which costs checks and still leaves the item
# unobtainable if nobody sends it), the pool guarantees a working supply of each: see
# QUEST_SUPPLY_ITEM_IDS and the quest_supply flag carried into items.json.
QUEST_ITEMS_SRC = os.path.join(REPO, "tools", "extracted", "quest_items.json")

# Playtest additions. The graph sweep reads the item PPtrs a graph references, which misses any
# hand-in whose item lives inside the compressed Odin node blob, and its "is this quest logic?"
# filter only trusts DT_Quest_* / QuestGraph names. Both under-report, and playtesting found the
# gaps - so these are listed by hand, with the quest that needs them. English names in comments
# because that is how they come back from testers; ids resolved through Localization/en/Items_en.loc.
# The floor is split into groups so the yaml can tune them apart: handing out ten logs and handing
# out nine permanent +1 Strength herbs are not the same decision, and Mandragora is a 100-gold root
# whose count testers want to match vanilla's eight. Anything flagged and not listed here is an
# ordinary fetch material and follows the general quest_item_supply option.
SUPPLY_GROUP_IDS = {
    "permanent_herb": {
        "item_permaherb_strength",  # Basaltroot
        "item_permaherb_mind",      # Brainfood Plant
        "item_permaherb_life",      # Hawthorne
        "item_permaherb_skill",     # Cliff Lichen
        "item_permaherb_flow",      # Luminous Bass
    },
    "mandragora": {"item_alraune"},
}


def supply_group(rid):
    for group, ids in SUPPLY_GROUP_IDS.items():
        if rid in ids:
            return group
    return "quest"


QUEST_SUPPLY_EXTRA_IDS = {
    "item_alraune",             # Mandragora - Henik, "Deep in the Swamp" (~7 in vanilla)
    "item_ruinherb",            # Ruin Blossom - Aidan (its only graph is DT_PreApo_1_NPC_Aidan,
                                #   which the DT_Quest_ name filter skipped)
    "item_permaherb_strength",  # Basaltroot   - Aidan
    "item_permaherb_mind",      # Brainfood Plant
    "item_permaherb_life",      # Hawthorne
    "item_permaherb_skill",     # Cliff Lichen
    "item_permaherb_flow",      # Luminous Bass
    "item_healthPlant_1",       # healing plants: testers ask for the higher tiers too
    "item_healthPlant_2",
    "item_meat_raw",            # ten meat for Tiaa (monster drops make this the easy one)
    "item_ironore",             # "silver and iron" - the pit runs on both
}

# Coins. Drova has no separate money counter: Inventory.GetCurrencyFromInventory() looks up the
# ItemStack whose Item carries ItemBhvr_ICurrency and reads its Amount, so money IS the
# misc_currency stack in the bag and the client's ordinary AddItem grant path pays the player with
# no special casing. Worth including precisely because coins are the single most common thing the
# vanilla world drops (383 of ~4700 finds), so leaving them out skewed the whole distribution.
# The purses are separate items that pay out a chunk when used.
CURRENCY_IDS = {"misc_currency", "misc_bagOfCurrency", "misc_bagOfCurrency_big"}

# Objects that report loot but carry no inventory component, so there is nothing to open and the
# check could never be sent. Verified in game: Corpse_Stalker is not interactable, while
# Critter_Crow (which does have Saveable_Inventory) loots fine. An unreachable location is worse
# than a missing one: it can never be completed.
UNREACHABLE_SRC = os.path.join(REPO, "tools", "extracted", "unreachable.json")

# Story-critical objects that must never become locations, so their vanilla contents survive
# suppression. Keyed by GuidComponent guid (lowercase), value is the human reason. Removing a
# location never renumbers ids (they stay in the frozen file, unused).
#
# "Missing" (BanditMine/BanditMineBrutus, neutral -> in every seed) needs ordinary mushrooms
# collected around the mine plus the mine's weapon pack / relic / note to resolve. Ordinary
# mushrooms carry no IsQuestItem flag, so the client would suppress them and the quest could
# soft-lock with pickups enabled.
#
# MetaObjects_SavePlayerInventory_Lothar_Mining is not a world chest at all: the Lothar capture
# sequence stows the player's entire inventory in it. As a randomized location the suppressor
# would delete everything in it except keys/quest items/crystals - the player's whole kit.
STORY_CRITICAL_GUIDS = {
    "1f3320bf-b5bc-472c-af8a-06f331b9ccb0": "Lothar capture: holds the player's own confiscated gear",
    # Container_Chest_Slated_Curly_Silver in the bandit mine ("Cave - Chest 21"). The bandit capture
    # cutscene (DT_TeleportToBanditMine -> DS_TransferInventoryNode, target inventory-DB guid below)
    # transfers the player's ENTIRE inventory into it, same mechanism as the Lothar chest. Confirmed
    # in the field: a captured player opened it as a randomized location and the suppressor ate their
    # transferred belongings.
    "3d8311f8-6bed-4232-abb8-9c11df2f17ed": "Bandit-mine capture (Missing): holds the player's own confiscated gear",
    # PickUp_Cons_Mushroom around the bandit mine (scenes 13/14_36) - the quest's mushroom supply.
    "8223fb75-92fc-4a7b-b123-0d5e3a71a50d": "Missing: ordinary mushroom near mine",
    "b12b6731-fa78-4826-a72a-9a199feaf26a": "Missing: ordinary mushroom near mine",
    "b9e4fdd0-5cc6-464d-bf04-a278fbcc1536": "Missing: ordinary mushroom near mine",
    "d698f61b-d18b-4b24-bfde-f916f7cff8d7": "Missing: ordinary mushroom near mine",
    "292ca21b-720b-40f2-b806-ec0905def241": "Missing: ordinary mushroom near mine",
    "021a2d2a-c834-428b-abe1-4d148e166fec": "Missing: ordinary mushroom near mine",
    "95b18157-8530-41c3-9983-0544f0612b03": "Missing: ordinary mushroom near mine",
    "ab52d4ae-3b31-4a90-888b-7c2b0f1f32c4": "Missing: ordinary mushroom near mine",
    "fcd2b846-82c1-475d-9ca3-324e470b146f": "Missing: ordinary mushroom near mine",
    "12aa2cf5-d8a4-4220-a329-86108715215b": "Missing: ordinary mushroom near mine",
    # PickUp_Mine_Weapons / PickUp_MineRelic / PickUp_MineBanditNote - quest stages may require
    # physically holding these; the relic and note are probably IsQuestItem (client keeps them
    # anyway), but keeping them out of the pool is the safe direction for all three.
    "fbe0eb55-a690-445d-8f4a-3c93cb665327": "Missing: mine weapon pack",
    "c231ff79-ddcc-4559-8c5a-7b9559f2a01a": "Missing: mine relic",
    "2efe8200-5100-4ba2-b473-7958f557e949": "Missing: mine bandit note",
}

# Animal-derived loot: killable ambient critters (crows, small birds) and lootable carcasses. They
# carry Saveable_LootInventory, which chests and crates never do. Hunting birds is a different
# activity from opening a chest, and one bush can hold a flock of twelve, so they get their own
# opt-in category instead of padding the default seed.
CRITTERS_SRC = os.path.join(REPO, "tools", "extracted", "critters.json")

# Muggable NPCs (tools/extract_locations/extract_npcs.py): LazyActor spawner guid ->
# {label, area, faction}. The spawner's scene-baked guid is stamped onto the spawned actor
# (LazyActor.SetNewGuid), so it is the same key the save uses for the NPC. Knocking the NPC out and
# opening the mug window sends the check. Opposite-faction NPCs stay in the pool (some are still
# reachable) but the apworld marks them EXCLUDED, so nothing valuable can land on them.
NPCS_SRC = os.path.join(REPO, "tools", "extracted", "npcs.json")

# Location categories and their default enabled state. 5005 containers is far too many for one
# seed, so the apworld gates them by category; these defaults keep a fresh seed sane.
CATEGORY_DEFAULTS = {
    "Chest": True,
    "Container": True,
    "Critter": False,
    "Resource": False,
    "Cache": False,
    "Pickup": False,
    "Trader": False,
    "KillMilestone": False,
    "Mugging": False,
    "AttributeMilestone": False,
    "TalentMilestone": False,
}

# Flow abilities that belong to NPCs/bosses, not the player.
FLOW_EXCLUDE = {
    "flow_battleCry_npc",
    "flow_blink_brutus",
    "flow_blink_brutus_ada",
    "flow_blink_draugr",
    "flow_revive_brutus",
}

# weapon_* holds both player gear and creature ability sets (weapon_golem_spells_firetrap,
# weapon_weapon_bear_insane, ...). Whitelisting the real equipment types is safer than trying to
# name every creature.
PLAYER_WEAPON_TYPES = ("axe", "sword", "spear", "dagger", "shield", "bow", "sling")

# Authoring leftovers and NPC-only variants. Matched on whole underscore-separated tokens so that
# genuine items are not caught (item_golemsalve and the golemRoom notes must survive a "golem" filter).
#
# The named-NPC tokens cover boss ability scrolls (cons_flow_bady_scream_shockwave and friends) and
# story-stage weapon variants (weapon_axe_bady_dull/sharp). Field-verified: a granted Bady scroll
# shows up as an unusable consumable in the player's inventory. The letters that merely mention an
# NPC survive because their id is one fused token (item_letterMehlunaToBady).
JUNK_TOKENS = {"npc", "mock", "dummy", "debug", "placeholder", "test", "combotest", "defaultcreature",
               "bady", "ebru", "diemo", "jero", "molvina"}

# Non-items that we grant through other verified game calls.
# PlayerAttributeStats.AddExperiencePoints / GiveLearningPoint.
# The XP/LP tiers exist so the pool overflow is not a wall of identical +250 XP: the apworld hands
# out the big tiers a capped handful of times per seed and pads the rest with the small ones
# (see apworld/drova/items.py). Names are frozen id keys - never rename, only append.
SYNTHETIC = [
    # (ap_name, kind, key, amount, classification)
    ("Experience Boost", "Xp", "", 250, "filler"),
    ("Learning Point", "LearningPoint", "", 1, "useful"),
    ("Tiny Experience Boost", "Xp", "", 5, "filler"),
    ("Small Experience Boost", "Xp", "", 10, "filler"),
    ("Medium Experience Boost", "Xp", "", 50, "filler"),
    ("Large Experience Boost", "Xp", "", 100, "filler"),
    ("Massive Experience Boost", "Xp", "", 1000, "filler"),
    # LP is permanent character power: useful, so it can never land on an excluded location.
    ("2 Learning Points", "LearningPoint", "", 2, "useful"),
    ("5 Learning Points", "LearningPoint", "", 5, "useful"),
    # Permanent attribute raises through PlayerAttributeStats.ImproveAttribute (the perma-potion
    # path, thresholds included) and Health.ChangeMaxHealth. Useful classification: real character
    # power must never land on an excluded location. The apworld caps each at ~10 per seed.
    ("1 Strength", "Attribute", "strength", 1, "useful"),
    ("1 Dexterity", "Attribute", "dexterity", 1, "useful"),
    ("1 Mind", "Attribute", "mind", 1, "useful"),
    ("5 Max Health", "MaxHealth", "", 5, "useful"),
]


def pretty(readable_id):
    """armor_chest_banshee -> Armor Chest Banshee. Verified collision-free over all 1112 ids."""
    return " ".join(w[:1].upper() + w[1:] if w else w for w in readable_id.replace("_", " ").split(" "))


def is_junk(rid):
    """Authoring leftovers and NPC-only variants, matched on whole tokens."""
    return bool(JUNK_TOKENS.intersection(rid.lower().split("_")))


def _load_item_values():
    if not os.path.exists(ITEM_VALUES_SRC):
        print("WARNING: %s missing - quest-valued items stay in the pool" % ITEM_VALUES_SRC)
        return {}
    with open(ITEM_VALUES_SRC, encoding="utf-8") as fh:
        return json.load(fh)


ITEM_VALUES = _load_item_values()


def _load_quest_supply_items():
    """Ordinary items a quest can consume, which the pool must therefore supply in usable numbers.

    Two filters:
      * ORDINARY only - anything the game already flags (IsQuestItem / quest category / Misc_Key) is
        never suppressed in the first place, so the player keeps finding it in the world.
      * referenced by quest logic - a DT_Quest_* dialogue or a QuestGraph. Ambient chatter
        (DT_PreApo_*, DT_EntityInfo_*) mentions beer and torches constantly without consuming any.

    Deliberately NOT filtered on shop availability: buying ten logs is a fallback, not a plan, and
    the pool supply costs nothing but a few overflow slots. Items with no world presence drop out -
    they are quest rewards handed over by an NPC, which suppression never touches.
    """
    if not os.path.exists(QUEST_ITEMS_SRC):
        print("WARNING: %s missing - quest-critical ordinary items are unprotected" % QUEST_ITEMS_SRC)
        return set()
    with open(QUEST_ITEMS_SRC, encoding="utf-8") as fh:
        data = json.load(fh)
    ordinary = set(data.get("ordinary") or ())
    referenced = set()
    for name, graph in (data.get("graphs") or {}).items():
        if not (name.startswith("DT_Quest_") or graph.get("kind") == "QuestGraph"):
            continue
        referenced.update(graph.get("items") or ())
    world = set()
    if os.path.exists(LOOT_DIST_SRC):
        with open(LOOT_DIST_SRC, encoding="utf-8") as fh:
            world = set((json.load(fh).get("totals") or {}))
    # Coins are fungible - a quest that wants payment takes money earned anywhere - and the pool
    # already hands currency out weighted by how much the world drops, so a floor would do nothing.
    return ((ordinary & referenced & world) | QUEST_SUPPLY_EXTRA_IDS) - CURRENCY_IDS


QUEST_SUPPLY_ITEM_IDS = _load_quest_supply_items()


def _load_world_counts():
    """readable id -> expected number of vanilla finds across the whole map (see LOOT_DIST_SRC)."""
    if not os.path.exists(LOOT_DIST_SRC):
        print("WARNING: %s missing - every item gets world_count 0 and the apworld falls back to "
              "an unweighted overflow draw" % LOOT_DIST_SRC)
        return {}
    with open(LOOT_DIST_SRC, encoding="utf-8") as fh:
        totals = json.load(fh).get("totals") or {}
    return {rid: round(rec.get("count", 0.0), 2) for rid, rec in totals.items()}


WORLD_COUNTS = _load_world_counts()


def is_quest_valued(rid):
    """The game's own Item.IsQuestItem: buy == 0 && sell == 0. Unknown ids count as sellable,
    because excluding something we have no data for is the risky direction (pool-only loss)."""
    rec = ITEM_VALUES.get(rid)
    return rec is not None and rec["buy"] == 0 and rec["sell"] == 0


# Drova.Items.ItemSubCategory values (see extract_item_values.py). The authored taxonomy is the
# ground truth for what an item IS: the "trophies" that sounded like sale junk (Boar Skull, Tooth
# of the Viper) are Armor_Trinket - equippable accessories with passive effects.
SUB_ARMOR_EQUIP = {12, 13, 14, 15}   # Armor_Helmet / Armor_Trinket / Armor_Quiver / Armor_Bag
SUB_MISC_KEY = 24                    # Misc_Key: glyph stones, seal stones, quest-gate props
SUB_CONSUMABLE_FOOD = 17             # cooked meals and drinks - recipe outputs, not world drops

# The prefix rules below cover the id families Drova actually uses for gear, keys and consumables,
# but a handful of items sit on one-off prefixes their author never reused - tool_torch,
# consumable_potion_darkbrew_healing, throwing_knife/throwing_ensnare, quiver_simple_name,
# ring_aldo_name. Nothing about them is special: the loot-distribution sweep finds torches 36 times
# and darkbrew potions 25, more than most things already in the pool. So instead of adding a prefix
# rule per straggler, unmatched ids fall through to the authored subcategory, which is the real
# taxonomy anyway. The value sets are read off what the prefix rules already accept.
SUB_FALLBACK_FILLER = {
    16,   # Consumable_Potion        potions, brews, salves
    17,   # Consumable_Food          cooked meals, drinks
    18,   # Consumable_Plant         herbs, health/flow plants
    19,   # Consumable_Raw           fish, raw meat
    21,   # Misc_Material            animal parts, trophies, coins, ore
    22,   # Misc_Gatherable          apples, eggs, honey, mushrooms
    27,   # Consumable_Custom        single-use flow scrolls
    34,   # Consumable_Throwable     throwing knives, bombs, traps, torches
}
SUB_FALLBACK_USEFUL = SUB_ARMOR_EQUIP | {SUB_MISC_KEY}

# Fallback exclusions - things whose subcategory says "ordinary loot" but which must stay vanilla:
#   riddle offerings gate the riddle doors the rune randomizer works with (Misc_Material by
#     subcategory, keys in everything but name),
#   the AI heal potion is NPC-only (buy 0 / sell 1, so the quest-value test does not catch it).
FALLBACK_EXCLUDE_PREFIXES = ("misc_riddle_",)
FALLBACK_EXCLUDE_IDS = {"consumable_potion_aiheal"}


def item_subcategory(rid):
    rec = ITEM_VALUES.get(rid)
    return rec.get("sub", 0) if rec else 0


def classify(rid):
    """Return (classification, include) for a readable id.

    progression: gates real content -> keys, charged crystals, player flow abilities
    useful:      weapons/armor/helmets
    filler:      consumables/recipes

    Gear and filler prefixes additionally require the item to be sellable (is_quest_valued false):
    a zero-value item is quest property by the game's own definition - talisman stage stones, lore
    letters, story props, NPC outfit variants - and granting those from the pool is the
    sequence-skip direction. Keys, crystals and flow abilities are exempt: their pool copies are
    intentionally redundant with the never-suppressed vanilla ones.
    """
    if is_junk(rid):
        return None, False
    if rid in RARE_USEFUL_IDS:
        return "useful", True
    if rid.startswith("key_") or rid == "misc_key_locked_door":
        return "progression", True
    if rid.startswith("item_energycrystal_"):
        # Only charged crystals gate anything; empty ones are the pre-quest state.
        return ("progression", True) if rid.endswith("_charged") else (None, False)
    if rid.startswith("flow_"):
        return (None, False) if rid in FLOW_EXCLUDE else ("progression", True)
    if rid.startswith("misc_worldmap") or rid.startswith("misc_map_"):
        return "useful", True
    if rid == "weapon_axe_improvisedpickaxe":
        # Internal intro prop: it has no localization at all (renders as "Id: weapon_axe_..."),
        # the real player pickaxe is tool_pickaxe_silberhauer below.
        return None, False
    if rid.startswith("tool_pickaxe"):
        # Minigame tools. Only the Silver Smasher (the sturdy pickaxe Merik sells) is worth
        # granting; the broken variant is a quest prop. tool_torch is not handled here - it is an
        # ordinary throwable-category consumable and reaches the subcategory fallback below.
        return ("useful", True) if rid == "tool_pickaxe_silberhauer" else (None, False)
    if rid.startswith("weapon_"):
        if is_quest_valued(rid):
            return None, False
        parts = rid.split("_")
        return ("useful", True) if len(parts) > 1 and parts[1] in PLAYER_WEAPON_TYPES else (None, False)
    if rid.startswith("armor_") or rid.startswith("helmet_"):
        return (None, False) if is_quest_valued(rid) else ("useful", True)
    if rid.startswith("recipe_flow_"):
        # Ability/spell scrolls: the game's primary way to LEARN flow abilities, not crafting
        # recipes (authored Consumable_Custom, not Consumable_Recipe). Real character power.
        return (None, False) if is_quest_valued(rid) else ("useful", True)
    if rid.startswith("cons_") or rid.startswith("recipe_"):
        return (None, False) if is_quest_valued(rid) else ("filler", True)
    # Cosmetics and authoring leftovers are not worth randomizing.
    if rid.startswith(("hair_", "beard_", "deco", "template_", "test_", "mock_", "skin_")):
        return None, False
    # item_* is a catch-all: notes, treasure maps, food. Keep them as filler so the pool can fill
    # the location count, but never let logic depend on them.
    if rid.startswith("item_"):
        if is_quest_valued(rid):
            return None, False
        # Equippable accessories (trinkets, quivers, bags, the one item_ helmet) and permanent
        # stat items are character power, not filler: useful keeps them off excluded locations.
        if item_subcategory(rid) in SUB_ARMOR_EQUIP:
            return "useful", True
        if rid.startswith(("item_permapotion_", "item_permaherb_")):
            return "useful", True
        # Authored keys (glyph/seal stones, quest-gate props). Their pool copies are redundant
        # with the vanilla ones, which slot_is_protected/LootSuppressor now keep obtainable.
        if item_subcategory(rid) == SUB_MISC_KEY:
            return "useful", True
        return "filler", True
    # Everything else: trust the authored subcategory rather than the id prefix (see
    # SUB_FALLBACK_* above). Same sellability gate as the prefix rules - a zero-value item is
    # quest property by the game's own definition.
    if rid in CURRENCY_IDS:
        return "filler", True
    if rid.startswith(FALLBACK_EXCLUDE_PREFIXES) or rid in FALLBACK_EXCLUDE_IDS:
        return None, False
    if not is_quest_valued(rid):
        sub = item_subcategory(rid)
        if sub in SUB_FALLBACK_USEFUL:
            return "useful", True
        if sub in SUB_FALLBACK_FILLER:
            return "filler", True
    return None, False


# --- Consumable stack sizes ----------------------------------------------------------------------
# Every pool item grants exactly one unit by default. That cripples ammo and consumables: a vanilla
# chest stack of 20 arrows becomes a single arrow, so suppression makes them far scarcer than vanilla.
# Stackables therefore grant a usable quantity when received. Matched on tokens in the lowercased
# readable id; the amount is a client-side grant quantity only (the apworld ignores it, so changing it
# never renumbers ids or affects generation). Tune the sizes and token lists freely.
#
# Stacking is gated to the consumable namespaces: item_ plus the three one-off prefixes the
# subcategory fallback in classify() lets through (tool_torch, throwing_knife/throwing_ensnare,
# consumable_potion_darkbrew_healing - all ordinary consumables their author happened to name
# differently). Abilities (flow_/cons_flow_), gear (weapon_/armor_/helmet_), keys, recipes and maps
# (misc_) always grant one; the gate is also what stops "arrow" catching the flow_poisonArrow ability.
# NO_STACK wins first, for collisions left inside item_: perma* items are permanent one-time
# upgrades (permapotion/permaherb) that must stay at 1 even though they contain "potion"/"herb".
# "extract" keeps item_callashroom_extract (a My Very Own Talisman quest ingredient that
# "callashroom" would stack to 5) a single-unit grant; at amount 1 it also drops out of the
# repeatable consumable-chunk bonus pool, so a seed hands out at most one.
# "alraune" (Mandragora) is a rare quest root worth 100 gold and quests count it one at a time, so a
# grant hands over exactly one - which also keeps the mandragora_supply option honest: N means N.
NO_STACK_TOKENS = ("perma", "respec", "extract", "alraune")

STACKABLE_PREFIXES = ("item_", "tool_torch", "throwing_", "consumable_", "misc_currency")

# Coins per misc_currency grant. Vanilla drops 2638 coins over 383 finds (~7 a pile); 10 keeps the
# pool's total payout in the same order as the world's once the draw weights are applied. The purses
# are single items that pay out on use, so they stay at 1.
CURRENCY_STACK = 10

# Vanilla-rare consumables that must not be ordinary spammable filler: they get useful
# classification (one guaranteed pool copy, never on excluded locations) and, via NO_STACK above,
# grant a single unit. The respec potion ("potion of forget") is a rare, build-defining item.
RARE_USEFUL_IDS = {"item_potion_respec"}
STACK_RULES = (
    # (amount, tokens) - first matching rule wins. Tokens are substrings of the lowercased id.
    (20, ("arrow", "bolt")),
    (10, ("throwingknife", "throwingaxe", "splittertrap")),
    # throwing_knife / throwing_ensnare: the underscore keeps them out of the "throwingknife" token
    # above, and vanilla drops them in 2-3s, so they sit with the other thrown traps rather than
    # with the 10-packs.
    (5, ("potion", "salve")),
    # Crafting ore and utility explosives, so the bonus pool can hand them out in useful chunks.
    # "bomb" also catches item_troutskewersbombus (a food); 3 skewers is fine.
    (5, ("ironstone", "silverstone", "silverore", "ironore", "logwood")),
    (3, ("bomb", "trap", "throwing_")),
    (5, ("meat", "fish_", "food", "mushroom", "callashroom", "healthplant", "flowplant",
         "berry", "bread", "cheese", "herb", "plant")),
)


# Gatherables, plants, raw food and cooked food stack even when no token matches: apples,
# earthroot, bogwheat and povage are picked by the handful in vanilla exactly like the mushrooms and
# berries the tokens already catch, and a one-apple grant is not a reward. Materials (sub 21: claws,
# furs, ore, coins) stay out - a stack of five bear claws is a very different thing.
SUB_STACKABLE = {17, 18, 19, 22}
SUB_STACK_AMOUNT = 5


def stack_amount(rid):
    """How many units one AP grant of this item hands over. 1 for everything but consumables."""
    if not rid.startswith(STACKABLE_PREFIXES):
        return 1
    low = rid.lower()
    if rid == "misc_currency":
        return CURRENCY_STACK
    if any(t in low for t in NO_STACK_TOKENS):
        return 1
    for amount, tokens in STACK_RULES:
        if any(t in low for t in tokens):
            return amount
    if item_subcategory(rid) in SUB_STACKABLE:
        return SUB_STACK_AMOUNT
    return 1


def load_frozen(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_frozen(path, mapping):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, indent=1, sort_keys=True)
        fh.write("\n")


def assign_ids(keys, frozen, base):
    """Append-only id assignment keyed by stable game identity.

    Existing keys keep their id forever. New keys take the next free slot. Nothing is renumbered,
    so renaming a location or reordering the source data cannot invalidate a generated seed.
    """
    changed = False
    used = set(frozen.values())
    nxt = base
    for key in sorted(keys):
        if key in frozen:
            continue
        while nxt in used:
            nxt += 1
        frozen[key] = nxt
        used.add(nxt)
        changed = True
    over = [k for k, v in frozen.items() if v > 2 ** 31 - 1]
    if over:
        sys.exit("id exceeds the AP-recommended 32-bit range: %s" % over[:3])
    return changed


def load_readable_ids():
    if not os.path.exists(READABLE_IDS):
        sys.exit("readable_ids.txt not found at %s" % READABLE_IDS)
    with open(READABLE_IDS, encoding="utf-8", errors="replace") as fh:
        ids = [line.strip() for line in fh if line.strip()]
    if len(ids) != len(set(ids)):
        sys.exit("readable_ids.txt contains duplicates")
    return ids


def build_items(readable_ids):
    items = []
    for rid in sorted(readable_ids):
        classification, include = classify(rid)
        if not include:
            continue
        items.append({
            "name": pretty(rid),
            "readable_id": rid,
            "kind": "Item",
            "amount": stack_amount(rid),
            "classification": classification,
            # The game's own sell price, so the apworld can tell actual junk from rare valuables
            # (a Tooth of the Viper sells for 100, a plain Feather for 1) without re-deriving it.
            "sell": (ITEM_VALUES.get(rid) or {}).get("sell", 0),
            # How often vanilla Drova actually gives this item out; 0 for anything the world never
            # drops (shop-only gear, quest rewards, recipes). The apworld's repeatable overflow is
            # drawn with these as weights.
            "world_count": WORLD_COUNTS.get(rid, 0.0),
            # A quest can ask the player to hand this over, and it is not quest-flagged, so
            # suppression removes every vanilla copy. The apworld guarantees pool copies of these.
            "quest_supply": rid in QUEST_SUPPLY_ITEM_IDS,
            # Cooked food (Consumable_Food) is a recipe output the player makes at a fire, so the
            # world never drops it and world_count is 0 - which would freeze it at a single pool
            # copy. The apworld gives this a flat nominal draw weight instead so it can repeat.
            "cooked_food": classification == "filler" and item_subcategory(rid) == SUB_CONSUMABLE_FOOD,
            # Which yaml option sizes this item's floor (see SUPPLY_GROUP_IDS).
            "supply_group": supply_group(rid) if rid in QUEST_SUPPLY_ITEM_IDS else "",
        })
    for name, kind, key, amount, classification in SYNTHETIC:
        items.append({
            "name": name,
            "readable_id": key,
            "kind": kind,
            "amount": amount,
            "classification": classification,
            "sell": 0,
            "world_count": 0.0,
            "quest_supply": False,
            "supply_group": "",
            "cooked_food": False,
        })

    names = [i["name"] for i in items]
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        sys.exit("AP item name collision: %s" % dupes)

    # Key ids by the stable game identity, not the display name, so prettifying can change freely.
    frozen = load_frozen(FROZEN_ITEM_IDS)
    keys = [i["readable_id"] or i["name"] for i in items]
    if assign_ids(keys, frozen, ITEM_BASE_ID):
        save_frozen(FROZEN_ITEM_IDS, frozen)
    for item in items:
        item["id"] = frozen[item["readable_id"] or item["name"]]
    items.sort(key=lambda i: i["name"])
    return items


def slot_is_protected(readable_id, quest):
    """Mirror of the client's LootSuppressor.IsProtected: these items are never suppressed, so
    a slot holding one keeps its vanilla item in the chest and must not become a location.

    The extractor's `quest` flag reads the Item asset's IsInQuestCategory; the client protects on
    (IsQuestItem || IsInQuestCategory), so this side stays a subset only where the extraction has no
    values to derive IsQuestItem from - which is fine: an extra check on a protected item is
    additive, never a loss."""
    if quest:
        return True
    rid = (readable_id or "").lower()
    if not rid:
        return True
    if rid.startswith("key_") or rid == "misc_key_locked_door":
        return True
    if rid.startswith("item_energycrystal_"):
        return True
    # Riddle offerings gate doors/statues that can hide randomized locations; the client keeps
    # them (see LootSuppressor.IsProtected), so their slots must not become checks.
    if rid.startswith("misc_riddle_"):
        return True
    # Items the game itself authors as keys (ItemSubCategory.Misc_Key: glyph stones, the Bygones
    # seal stone, quest-gate props like Karotte's weapon). Keys in all but prefix - suppressing
    # one could lock whatever it opens, so the client keeps them and their slots are no checks.
    if item_subcategory(rid) == SUB_MISC_KEY:
        return True
    return False


def eligible_slot_count(chest_slots, guid):
    """How many AP checks this container is worth (minimum 1: the base location)."""
    rec = chest_slots.get(guid.lower())
    if not rec:
        return 1
    eligible = [s for s in rec["slots"] if not slot_is_protected(s["readable_id"], s["quest"])]
    return max(1, len(eligible))


def build_locations():
    """Container locations from the static bundle extraction, plus quest locations."""
    locations = []

    unreachable = {}
    if os.path.exists(UNREACHABLE_SRC):
        with open(UNREACHABLE_SRC, encoding="utf-8") as fh:
            unreachable = json.load(fh)

    critters = {}
    if os.path.exists(CRITTERS_SRC):
        with open(CRITTERS_SRC, encoding="utf-8") as fh:
            critters = json.load(fh)

    chest_slots = {}
    if os.path.exists(CHEST_SLOTS_SRC):
        with open(CHEST_SLOTS_SRC, encoding="utf-8") as fh:
            chest_slots = json.load(fh)
    else:
        print("WARNING: %s missing - every container stays a single location" % CHEST_SLOTS_SRC)

    if os.path.exists(LOCATIONS_SRC):
        with open(LOCATIONS_SRC, encoding="utf-8") as fh:
            raw = json.load(fh)
        skipped = 0
        extra_slots = 0
        quest_critical = 0
        for name, rec in raw.items():
            guid = rec["guid"].lower()
            if guid in unreachable:
                skipped += 1
                continue
            if guid in STORY_CRITICAL_GUIDS:
                quest_critical += 1
                continue
            # The extractor calls anything with an inventory a Container. Reclassify animals.
            category = "Critter" if guid in critters else rec["category"]
            locations.append({
                "name": name,
                "key": rec["guid"],
                "kind": "Container",
                "category": category,
                "area": rec.get("area", ""),
                "classification": "default",
            })
            # One extra location per additional eligible authored item. The base location above is
            # slot 1 and keeps its name and frozen id, so existing seeds stay valid; extra slots
            # get their own frozen keys ("<guid>#slot<i>"), which only ever appends ids. The kind
            # is ContainerSlot so the C# emitter can route them into the slot table instead of the
            # guid->name table (their keys are not bare guids and must never be looked up as such).
            for i in range(2, eligible_slot_count(chest_slots, guid) + 1):
                extra_slots += 1
                locations.append({
                    "name": "%s - Item %d" % (name, i),
                    "key": "%s#slot%d" % (rec["guid"], i),
                    "kind": "ContainerSlot",
                    "category": category,
                    "area": rec.get("area", ""),
                    "classification": "default",
                })
        if skipped:
            print("skipped %d unreachable container(s): nothing to loot on them" % skipped)
        if quest_critical:
            print("kept %d story-critical object(s) vanilla (Missing questline, Lothar gear chest)" % quest_critical)
        if extra_slots:
            print("added %d extra slot location(s) from authored multi-item containers" % extra_slots)
    else:
        print("WARNING: %s missing - no container locations generated" % LOCATIONS_SRC)

    if os.path.exists(QUESTS_SRC):
        with open(QUESTS_SRC, encoding="utf-8") as fh:
            quests = json.load(fh)
        for key, rec in sorted(quests.items()):
            faction = rec.get("faction", "unknown")
            # An unknown faction could turn out to be locked, which would make the location
            # unreachable and break generation. Excluding is the safe half of that trade.
            if faction == "unknown":
                continue
            # Internal var lists with no journal topic are not player-facing quests.
            if not rec.get("playerFacing"):
                continue
            title = rec.get("title") or rec.get("name") or key
            # Each faction has its own copy of some quests ("The Expedition" exists twice).
            # Only one is ever emitted per seed, but the id table must hold every location
            # that could exist under any option combination, so the names must differ.
            if faction in ("nemeton", "ruinenlager"):
                title = "%s (%s)" % (title, "Nemeton" if faction == "nemeton" else "Remnants")
            locations.append({
                "name": "Quest - %s" % title,
                "key": rec.get("guid") or key,
                "kind": "Quest",
                "category": "Quest",
                "area": "",
                "faction": faction,
                "quest_name": rec.get("name", ""),
                "classification": "default",
            })
    else:
        print("WARNING: %s missing - no quest locations generated" % QUESTS_SRC)

    if os.path.exists(TRADERS_SRC):
        with open(TRADERS_SRC, encoding="utf-8") as fh:
            traders = json.load(fh)
        trader_units = 0
        for key, rec in sorted(traders.items()):
            # trader_label is unique per trader guid and item ids are unique within a trader, so the
            # name never collides. Faction is proven at extraction; unprovable traders are excluded
            # there, exactly like faction quests.
            name = "Trader - %s - %s" % (rec["trader_label"], pretty(rec["item_readable_id"]))
            locations.append({
                "name": name,
                "key": key,
                "kind": "Trader",
                "category": "Trader",
                "area": rec.get("area", ""),
                "faction": rec.get("faction", "neutral"),
                "classification": "default",
            })
            # A slot with an authored stock stack sells several checks: the base location is unit 1
            # (name and frozen id unchanged, so existing seeds stay valid) and units 2..K append,
            # capped so bulk-material stacks (160x povage) cannot flood the pool. Past the cap the
            # purchase is ordinary vanilla shopping.
            for unit in range(2, min(rec.get("amount", 1), TRADER_UNIT_CAP) + 1):
                trader_units += 1
                locations.append({
                    "name": "%s - Unit %d" % (name, unit),
                    "key": "%s#unit%d" % (key, unit),
                    "kind": "TraderUnit",
                    "category": "Trader",
                    "area": rec.get("area", ""),
                    "faction": rec.get("faction", "neutral"),
                    "classification": "default",
                })
        if trader_units:
            print("added %d extra trader unit location(s) from stocked stacks (cap %d)" % (trader_units, TRADER_UNIT_CAP))

    if os.path.exists(NPCS_SRC):
        with open(NPCS_SRC, encoding="utf-8") as fh:
            npcs = json.load(fh)
        for guid, rec in sorted(npcs.items()):
            locations.append({
                "name": "Mugging - %s" % pretty(rec["label"]),
                "key": guid,
                "kind": "Mugging",
                "category": "Mugging",
                "area": rec.get("area", ""),
                "faction": rec.get("faction", "neutral"),
                "classification": "default",
            })

    # Synthetic enemy-kill milestones. No world object and no extraction: the client sends milestone
    # k once the persistent kill count reaches k * interval (interval is a per-seed option). Keyed by
    # a stable synthetic id so the frozen map assigns them like anything else.
    for k in range(1, MAX_KILL_MILESTONES + 1):
        locations.append({
            "name": "Enemy Kills - %d" % k,
            "key": "killmilestone_%d" % k,
            "kind": "KillMilestone",
            "category": "KillMilestone",
            "area": "",
            "milestone": k,
            "classification": "default",
        })
    for k in range(1, MAX_ATTRIBUTE_MILESTONES + 1):
        locations.append({
            "name": "Attributes Learned - %d" % k,
            "key": "attributemilestone_%d" % k,
            "kind": "AttributeMilestone",
            "category": "AttributeMilestone",
            "area": "",
            "milestone": k,
            "classification": "default",
        })
    for k in range(1, MAX_TALENT_MILESTONES + 1):
        locations.append({
            "name": "Talents Learned - %d" % k,
            "key": "talentmilestone_%d" % k,
            "kind": "TalentMilestone",
            "category": "TalentMilestone",
            "area": "",
            "milestone": k,
            "classification": "default",
        })

    if not locations:
        return locations

    # Some quests genuinely share a journal title (two different quests are both called "Missing").
    # Disambiguate every member of a colliding group with its stable quest key so the result does
    # not depend on ordering.
    counts = {}
    for loc in locations:
        counts[loc["name"]] = counts.get(loc["name"], 0) + 1
    for loc in locations:
        if counts[loc["name"]] > 1 and loc["kind"] == "Quest":
            suffix = loc.get("quest_name", "").replace("QuestVars_", "").replace("QVars_", "")
            if suffix:
                loc["name"] = "%s (%s)" % (loc["name"], suffix)

    names = [loc["name"] for loc in locations]
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        sys.exit("AP location name collision: %s" % dupes[:5])

    frozen = load_frozen(FROZEN_LOCATION_IDS)
    if assign_ids([loc["key"] for loc in locations], frozen, LOCATION_BASE_ID):
        save_frozen(FROZEN_LOCATION_IDS, frozen)
    for loc in locations:
        loc["id"] = frozen[loc["key"]]
    locations.sort(key=lambda loc: loc["name"])
    return locations


def write_json(payload, filename):
    os.makedirs(OUT_JSON_DIR, exist_ok=True)
    path = os.path.join(OUT_JSON_DIR, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return path


def write_cs_locations(locations):
    """Runtime lookup for the mod: game guid / quest key -> AP location name."""
    os.makedirs(OUT_CS_DIR, exist_ok=True)
    lines = [
        "// Generated by tools/gen_data.py. Do not edit by hand.",
        "using System.Collections.Generic;",
        "",
        "namespace ArchipelagoDrova.Data",
        "{",
        "    public static partial class LocationTable",
        "    {",
        "        /// <summary>GuidComponent guid -> AP location name.</summary>",
        "        public static readonly Dictionary<string, string> ContainerGuidToName = new Dictionary<string, string>",
        "        {",
    ]
    for loc in locations:
        # Muggings resolve through the same guid map: the client walks the knocked-out NPC's
        # GuidComponent chain, and the NPC carries the LazyActor spawner's scene guid.
        if loc["kind"] in ("Container", "Mugging"):
            lines.append('            { "%s", "%s" },' % (cs_escape(loc["key"]), cs_escape(loc["name"])))
    lines += [
        "        };",
        "",
        "        /// <summary>GuidComponent guid -> extra per-item AP location names (slots 2..K).</summary>",
        "        public static readonly Dictionary<string, string[]> ContainerGuidToSlotNames = new Dictionary<string, string[]>",
        "        {",
    ]
    slot_names = {}
    for loc in locations:
        if loc["kind"] == "ContainerSlot":
            guid = loc["key"].split("#", 1)[0]
            slot_names.setdefault(guid, []).append(loc["name"])
    for guid in sorted(slot_names):
        # Numeric slot order ("Item 2" before "Item 10"), purely for readable diffs.
        ordered = sorted(slot_names[guid], key=lambda n: int(n.rsplit(" ", 1)[1]))
        joined = ", ".join('"%s"' % cs_escape(n) for n in ordered)
        lines.append('            { "%s", new[] { %s } },' % (cs_escape(guid), joined))
    lines += [
        "        };",
        "",
        '        /// <summary>GuidComponent guid -> authored loot as "readable_id:amount" entries.',
        "        /// The loot suppressor removes exactly these from a randomized container instead of",
        "        /// wiping it, so items a player (or a cutscene) put there afterwards survive.</summary>",
        "        public static readonly Dictionary<string, string[]> ContainerGuidToAuthoredLoot = new Dictionary<string, string[]>",
        "        {",
    ]
    chest_slots = {}
    if os.path.exists(CHEST_SLOTS_SRC):
        with open(CHEST_SLOTS_SRC, encoding="utf-8") as fh:
            chest_slots = json.load(fh)
    location_guids = {loc["key"].lower() for loc in locations if loc["kind"] == "Container"}
    for guid in sorted(chest_slots):
        if guid.lower() not in location_guids:
            continue
        # Protected slots (quest items, keys, riddle offerings) never become checks and their items
        # must survive in the container, so they are left out of the strip list entirely.
        slots = [s for s in chest_slots[guid]["slots"]
                 if not slot_is_protected(s["readable_id"], s["quest"])]
        if not slots:
            continue
        entries = ", ".join(
            '"%s:%d"' % (cs_escape(s["readable_id"]), s["amount"])
            for s in slots
        )
        lines.append('            { "%s", new[] { %s } },' % (cs_escape(guid), entries))
    lines += [
        "        };",
        "",
        "        /// <summary>Quest GVarList name -> AP location name.</summary>",
        "        public static readonly Dictionary<string, string> QuestNameToName = new Dictionary<string, string>",
        "        {",
    ]
    for loc in locations:
        if loc["kind"] == "Quest":
            lines.append(
                '            { "%s", "%s" },'
                % (cs_escape(loc.get("quest_name") or loc["key"]), cs_escape(loc["name"]))
            )
    lines += [
        "        };",
        "",
        "        /// <summary>\"traderGuid:itemGuid\" -> AP location name.</summary>",
        "        public static readonly Dictionary<string, string> TraderSlotToName = new Dictionary<string, string>",
        "        {",
    ]
    for loc in locations:
        if loc["kind"] == "Trader":
            lines.append('            { "%s", "%s" },' % (cs_escape(loc["key"]), cs_escape(loc["name"])))
    lines += [
        "        };",
        "",
        '        /// <summary>"traderGuid:itemGuid" -> extra per-unit AP location names (units 2..K).</summary>',
        "        public static readonly Dictionary<string, string[]> TraderSlotToUnitNames = new Dictionary<string, string[]>",
        "        {",
    ]
    unit_names = {}
    for loc in locations:
        if loc["kind"] == "TraderUnit":
            slot_key = loc["key"].split("#", 1)[0]
            unit_names.setdefault(slot_key, []).append(loc["name"])
    for slot_key in sorted(unit_names):
        ordered = sorted(unit_names[slot_key], key=lambda n: int(n.rsplit(" ", 1)[1]))
        joined = ", ".join('"%s"' % cs_escape(n) for n in ordered)
        lines.append('            { "%s", new[] { %s } },' % (cs_escape(slot_key), joined))
    lines += [
        "        };",
        "",
        "        /// <summary>Area loca key (SavegameData.PlayerAreaLocaKey) -> English area display name.</summary>",
        "        public static readonly Dictionary<string, string> AreaKeyToName = new Dictionary<string, string>",
        "        {",
    ]
    for key, name in sorted(load_area_names().items()):
        lines.append('            { "%s", "%s" },' % (cs_escape(key), cs_escape(name)))
    lines += [
        "        };",
        "    }",
        "}",
        "",
    ]
    with open(OUT_CS_LOC, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines))
    return OUT_CS_LOC


def cs_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def load_area_names():
    """AreaNames_en.loc: `<key> { <display name> }` per line, same parse gen_locations.py uses."""
    if not os.path.exists(AREAS_LOC):
        print("WARNING: %s missing - area highlight map will be empty" % AREAS_LOC)
        return {}
    import re
    text = open(AREAS_LOC, encoding="utf-8", errors="replace").read()
    return {m.group(1): m.group(2) for m in re.finditer(r"^(\S+)\s*\{\s*(.*?)\s*\}", text, re.M)}


def write_cs(items):
    os.makedirs(os.path.dirname(OUT_CS), exist_ok=True)
    lines = [
        "// Generated by tools/gen_data.py. Do not edit by hand.",
        "using System.Collections.Generic;",
        "",
        "namespace ArchipelagoDrova.Data",
        "{",
        "    public static partial class ItemTable",
        "    {",
        "        public static readonly Dictionary<string, ItemGrant> Generated = new Dictionary<string, ItemGrant>",
        "        {",
    ]
    for item in items:
        lines.append(
            '            { "%s", new ItemGrant(GrantKind.%s, "%s", %d) },'
            % (cs_escape(item["name"]), item["kind"], cs_escape(item["readable_id"]), item["amount"])
        )
    lines += [
        "        };",

        "    }",
        "}",
        "",
    ]
    with open(OUT_CS, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines))
    return OUT_CS


def tally(records, field):
    counts = {}
    for rec in records:
        key = rec.get(field, "?")
        counts[key] = counts.get(key, 0) + 1
    return counts


def main():
    readable_ids = load_readable_ids()
    items = build_items(readable_ids)
    locations = build_locations()

    item_ids = [i["id"] for i in items]
    print("readable ids read : %d" % len(readable_ids))
    print("items generated   : %d  (id %d..%d)" % (len(items), min(item_ids), max(item_ids)))
    for key, count in sorted(tally(items, "classification").items()):
        print("  %-12s %4d" % (key, count))
    supply = [i for i in items if i.get("quest_supply")]
    groups = tally(supply, "supply_group")
    print("  %-12s %4d  (quest-consumable ordinary items; the pool guarantees copies: %s)"
          % ("quest_supply", len(supply),
             ", ".join("%s=%d" % kv for kv in sorted(groups.items()))))
    with_world = [i for i in items if i.get("world_count")]
    print("  %-12s %4d  (vanilla loot frequency known; total %.0f finds)"
          % ("world_count", len(with_world), sum(i["world_count"] for i in with_world)))

    print("wrote %s" % write_json(items, "items.json"))
    print("wrote %s" % write_cs(items))

    if locations:
        loc_ids = [loc["id"] for loc in locations]
        print("\nlocations         : %d  (id %d..%d)" % (len(locations), min(loc_ids), max(loc_ids)))
        for key, count in sorted(tally(locations, "category").items()):
            default = CATEGORY_DEFAULTS.get(key, True)
            print("  %-12s %4d   default=%s" % (key, count, "on" if default else "off"))
        # The apworld also filters quests by the chosen faction, so a real default seed is smaller
        # than the raw category totals: neutral quests plus one faction's, never both.
        enabled = [l for l in locations if CATEGORY_DEFAULTS.get(l["category"], True)]
        for faction in ("nemeton", "ruinenlager"):
            seed = [l for l in enabled if l.get("faction", "neutral") in ("neutral", faction)]
            print("  -> default seed, faction=%-11s %d locations" % (faction, len(seed)))
        print("wrote %s" % write_json(locations, "locations.json"))
        print("wrote %s" % write_cs_locations(locations))
    else:
        print("\nno locations generated yet")


if __name__ == "__main__":
    main()
