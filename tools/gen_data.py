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

# Enemy-kill milestone locations are synthetic: they have no world object and are not extracted.
# The client sends them from a persistent kill count. Every milestone that could exist under any
# option must be in the datapackage, so a fixed maximum is baked in and the apworld creates only
# the first enemy_kill_checks of them per seed. Raising this later only appends new frozen ids.
MAX_KILL_MILESTONES = 50

# Standard Steam location; override with the DROVA_PATH env var if your install is elsewhere.
GAME_DIR = os.environ.get("DROVA_PATH", r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin")
READABLE_IDS = os.path.join(GAME_DIR, "Mods", "readable_ids.txt")

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

# Objects that report loot but carry no inventory component, so there is nothing to open and the
# check could never be sent. Verified in game: Corpse_Stalker is not interactable, while
# Critter_Crow (which does have Saveable_Inventory) loots fine. An unreachable location is worse
# than a missing one: it can never be completed.
UNREACHABLE_SRC = os.path.join(REPO, "tools", "extracted", "unreachable.json")

# Animal-derived loot: killable ambient critters (crows, small birds) and lootable carcasses. They
# carry Saveable_LootInventory, which chests and crates never do. Hunting birds is a different
# activity from opening a chest, and one bush can hold a flock of twelve, so they get their own
# opt-in category instead of padding the default seed.
CRITTERS_SRC = os.path.join(REPO, "tools", "extracted", "critters.json")

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
JUNK_TOKENS = {"npc", "mock", "dummy", "debug", "placeholder", "test", "combotest", "defaultcreature"}

# Non-items that we grant through other verified game calls.
# PlayerAttributeStats.AddExperiencePoints / GiveLearningPoint.
SYNTHETIC = [
    # (ap_name, kind, key, amount, classification)
    ("Experience Boost", "Xp", "", 250, "filler"),
    ("Learning Point", "LearningPoint", "", 1, "useful"),
]


def pretty(readable_id):
    """armor_chest_banshee -> Armor Chest Banshee. Verified collision-free over all 1112 ids."""
    return " ".join(w[:1].upper() + w[1:] if w else w for w in readable_id.replace("_", " ").split(" "))


def is_junk(rid):
    """Authoring leftovers and NPC-only variants, matched on whole tokens."""
    return bool(JUNK_TOKENS.intersection(rid.lower().split("_")))


def classify(rid):
    """Return (classification, include) for a readable id.

    progression: gates real content -> keys, charged crystals, player flow abilities
    useful:      weapons/armor/helmets
    filler:      consumables/recipes
    """
    if is_junk(rid):
        return None, False
    if rid.startswith("key_") or rid == "misc_key_locked_door":
        return "progression", True
    if rid.startswith("item_energycrystal_"):
        # Only charged crystals gate anything; empty ones are the pre-quest state.
        return ("progression", True) if rid.endswith("_charged") else (None, False)
    if rid.startswith("flow_"):
        return (None, False) if rid in FLOW_EXCLUDE else ("progression", True)
    if rid.startswith("misc_worldmap") or rid.startswith("misc_map_"):
        return "useful", True
    if rid.startswith("weapon_"):
        parts = rid.split("_")
        return ("useful", True) if len(parts) > 1 and parts[1] in PLAYER_WEAPON_TYPES else (None, False)
    if rid.startswith("armor_") or rid.startswith("helmet_"):
        return "useful", True
    if rid.startswith("cons_") or rid.startswith("recipe_"):
        return "filler", True
    # Cosmetics and authoring leftovers are not worth randomizing.
    if rid.startswith(("hair_", "beard_", "deco", "template_", "test_", "mock_", "skin_")):
        return None, False
    # item_* is a catch-all: quest items, notes, treasure maps, food. Keep them as filler so the
    # pool can fill the location count, but never let logic depend on them.
    if rid.startswith("item_"):
        return "filler", True
    return None, False


# --- Consumable stack sizes ----------------------------------------------------------------------
# Every pool item grants exactly one unit by default. That cripples ammo and consumables: a vanilla
# chest stack of 20 arrows becomes a single arrow, so suppression makes them far scarcer than vanilla.
# Stackables therefore grant a usable quantity when received. Matched on tokens in the lowercased
# readable id; the amount is a client-side grant quantity only (the apworld ignores it, so changing it
# never renumbers ids or affects generation). Tune the sizes and token lists freely.
#
# Only the item_ namespace holds stackable consumables; abilities (flow_/cons_flow_), gear (weapon_/
# armor_/helmet_), keys, recipes and maps (misc_) are other prefixes and always grant one. This prefix
# gate also stops "arrow" catching the flow_poisonArrow ability.
# NO_STACK wins first, for the one collision left inside item_: perma* items are permanent one-time
# upgrades (permapotion/permaherb) that must stay at 1 even though they contain "potion"/"herb".
NO_STACK_TOKENS = ("perma",)
STACK_RULES = (
    # (amount, tokens) - first matching rule wins. Tokens are substrings of the lowercased id.
    (20, ("arrow", "bolt")),
    (10, ("throwingknife", "throwingaxe", "splittertrap")),
    (5, ("potion", "salve")),
    (5, ("meat", "fish_", "food", "mushroom", "callashroom", "healthplant", "flowplant",
         "berry", "bread", "cheese", "herb", "plant")),
)


def stack_amount(rid):
    """How many units one AP grant of this item hands over. 1 for everything but item_ consumables."""
    if not rid.startswith("item_"):
        return 1
    low = rid.lower()
    if any(t in low for t in NO_STACK_TOKENS):
        return 1
    for amount, tokens in STACK_RULES:
        if any(t in low for t in tokens):
            return amount
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
        })
    for name, kind, key, amount, classification in SYNTHETIC:
        items.append({
            "name": name,
            "readable_id": key,
            "kind": kind,
            "amount": amount,
            "classification": classification,
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
    a slot holding one keeps its vanilla item in the chest and must not become a location."""
    if quest:
        return True
    rid = (readable_id or "").lower()
    if not rid:
        return True
    if rid.startswith("key_") or rid == "misc_key_locked_door":
        return True
    if rid.startswith("item_energycrystal_"):
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
        for name, rec in raw.items():
            guid = rec["guid"].lower()
            if guid in unreachable:
                skipped += 1
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
        for key, rec in sorted(traders.items()):
            # trader_label is unique per trader guid and item ids are unique within a trader, so the
            # name never collides. Faction is proven at extraction; unprovable traders are excluded
            # there, exactly like faction quests.
            locations.append({
                "name": "Trader - %s - %s" % (rec["trader_label"], pretty(rec["item_readable_id"])),
                "key": key,
                "kind": "Trader",
                "category": "Trader",
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
        if loc["kind"] == "Container":
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
        "    }",
        "}",
        "",
    ]
    with open(OUT_CS_LOC, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines))
    return OUT_CS_LOC


def cs_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


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
