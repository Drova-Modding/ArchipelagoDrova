"""Freeze the localization the client ships for the items the game never named.

Output: ArchipelagoDrova/Data/ItemLocaTable.g.cs
  LocaPath          the loca path this mod owns, i.e. its own ArchipelagoDrova_<lang>.loc files
  RedirectedItems   readable ids pointed at that path with Item.SetLocalization
  Entries           language -> key -> text, written out with LocalizationAccess.CreateLocalizationEntries

`Item.GetLocalizedItemName()` looks up `<_locaPath>.<readable_id>_name` and renders the miss as the
literal string "[LOCA] Key not found: helmet_ede_bandage_name. Path: Items". Vanilla never hands
those items to the player, so the hole only becomes visible once the randomizer starts distributing
every item in the database. A second group is authored with `_hasLocalization = false` and names
itself "Id: armor_chest_banshee" instead.

Both are fixed the same way: `Item.SetLocalization("ArchipelagoDrova")` redirects the item to a loca
path this mod owns and can therefore write freely. Filling the missing key in place is not an option
- a loca path IS a file (`Items` -> `Localization/<lang>/Items_<lang>.loc`), so writing one key into
`Items` means overwriting the game's own file and losing the two thousand entries in it.

The redirect moves every lookup keyed on `_locaPath`, not just the name, which is why this file also
mirrors keys the game already ships:
  - rarity, `Rarity.ToString().ToLowerInvariant()` ("uncommon"), or the tooltip's "(Uncommon)" line
    turns into a [LOCA] error;
  - the item type of a weapon, `SubCategory.ToString().ToLowerInvariant()` ("weapon_dagger").
They are copied per language out of the game's `Items_<lang>.loc`, so they are duplicated game text
and go stale if the game ever retranslates them. Re-run this whenever the game updates.

Item names are English in every language: the mod has no translations of its own, and the game's own
English fallback would produce the same text anyway.

Descriptions are left alone. A missing one resolves with errorIfMissing:false and renders as an
empty line, which is already true of ~500 items the game ships.

Two wirings mean a missing key is not a hole and are skipped (see extract_item_loca.py):
  - copyName        the name comes from another Item entirely
  - customKey       the name comes from a LocalizedString pointing elsewhere. All 11 items in the
                    database that carry one are quest letters, and they are exactly the 11 items
                    with no `_name` key: the letter shows its own title out of `Letters/<chapter>`.
                    The shipped build calls `Item.HasCustomLocaKey` from four places, so the field
                    is live even though the stale `Managed\\Drova.dll` predates it.
Loca paths under `Debug/` are skipped as well, and items the randomizer cannot hand out are left
untouched - `SetLocalization` writes to the shared ScriptableObject, so it stays off the ~300
internal and NPC-only items this mod never gives anybody.

Names are generated from the readable id (`misc_lootbag_red` -> "Misc Lootbag Red") unless CURATED
gives a better one, which keeps a future content patch's new gaps covered automatically while the
handful of items that are actually reachable read like the game wrote them.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LOCA = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\Localization"
SRC = os.path.join(REPO, "tools", "extracted", "item_loca.json")
VALUES = os.path.join(REPO, "tools", "extracted", "item_values.json")
POOL = os.path.join(REPO, "apworld", "drova", "data", "items.json")
OUT_CS = os.path.join(REPO, "ArchipelagoDrova", "Data", "ItemLocaTable.g.cs")

# The loca path the client owns. It becomes the file name: ArchipelagoDrova_<lang>.loc.
MOD_LOCA_PATH = "ArchipelagoDrova"

# The path the mirrored rarity and item-type keys are copied from.
GAME_ITEM_PATH = "Items"

# Drova.Items.ItemMainCategory / ItemSubCategory, read off the shipped Il2CppDrova.dll. Only the
# members that matter here: the type key exists for weapons, and ammo and talismans have none.
MAIN_WEAPON = 0
SUB_NAMES = {1: "Weapon_Sword", 2: "Weapon_Spear", 3: "Weapon_Axe", 4: "Weapon_Dagger",
             5: "Weapon_Shield", 6: "Weapon_Talisman", 7: "Weapon_Bow", 8: "Weapon_Bow_Ammo",
             9: "Weapon_Slingshot", 10: "Weapon_Slingshot_Ammo", 37: "Weapon_BareHands"}
SUB_WITHOUT_TYPE_KEY = {"Weapon_Bow_Ammo", "Weapon_Slingshot_Ammo", "Weapon_Talisman"}

# Item.ItemRarity. All five are mirrored rather than only the ones in use, so a rebalance patch that
# moves an item to another rarity cannot turn its tooltip into a [LOCA] error.
RARITY_KEYS = ["common", "uncommon", "rare", "epic", "legendary"]

# Hand-written names for the gaps that are actually reachable, following the database's own naming:
# an NPC's belongings carry their name ("Tristan's Map"), a coin bag is a "Pouch", and the game calls
# a draugr a Bygone ("Helmet of a Bygone") and Brutus' faction the Nexus ("Nexus Helmet").
CURATED = {
    # The head bandage the NPC Ede wears.
    "helmet_ede_bandage": "Ede's Bandage",
    # Vendor trash in the shape of a small bag.
    "misc_lootbag_red": "Red Pouch",
    "armor_chest_banshee": "Banshee Shroud",
    "armor_chest_manshee": "Manshee Shroud",
    "armor_chest_draugr": "Bygone Armor",
    "armor_chest_draugr_brutus": "Nexus Bygone Armor",
    "armor_chest_draugr_dagger": "Bygone Rogue Armor",
    "armor_chest_draugr_mage": "Bygone Mage Robe",
    "armor_chest_draugr_spear": "Bygone Spear Armor",
    "armor_chest_ruinenlager_gladiator_noeffect": "Remnants' Gladiator Armor",
    "armor_druid_intro": "Druid Robe",
    "armor_underwear_chest": "Undershirt",
    "cons_flow_conjure_ripper": "Ripper Conjuration",
    "misc_key_locked_door": "Door Key",
    "weapon_dagger": "Dagger",
}


def pretty(readable_id):
    """armor_chest_banshee -> Armor Chest Banshee. Mirrors gen_data.pretty, which names AP items."""
    return " ".join(w[:1].upper() + w[1:] if w else w for w in readable_id.replace("_", " ").split(" "))


def parse_entries(text):
    """key -> value of a .loc file. Brace aware: keys may contain spaces ("Raven Mask_name") and a
    value may span lines or nest braces, so a line-based regex both misses keys and invents them."""
    entries, depth, key, buf = {}, 0, None, []
    for ch in text:
        if ch == "{":
            if depth == 0:
                key = "".join(buf).strip()
                buf = []
            else:
                buf.append(ch)
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                if key:
                    entries[key] = "".join(buf).strip()
                key, buf = None, []
            else:
                buf.append(ch)
        else:
            buf.append(ch)
    return entries


def entries_of(language, path):
    f = os.path.join(LOCA, language, "%s_%s.loc" % (path, language))
    if not os.path.exists(f):
        return {}
    with open(f, encoding="utf-8-sig", errors="replace") as fh:
        return parse_entries(fh.read())


def cs_string(value):
    """A C# literal, kept pure ASCII. Roslyn only assumes UTF-8 for a source file with a BOM, so a
    raw "Ungewöhnlich" in a generated file is at the mercy of the build machine's code page."""
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20 or ord(ch) > 0x7E:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def type_key(values):
    """The key Item.GetItemTypeLocaString() builds, or None for anything that has no type line."""
    if values.get("main") != MAIN_WEAPON:
        return None
    name = SUB_NAMES.get(values.get("sub"))
    if name is None or name in SUB_WITHOUT_TYPE_KEY:
        return None
    return name.lower()


with open(SRC, encoding="utf-8") as fh:
    items = json.load(fh)
with open(VALUES, encoding="utf-8") as fh:
    values = json.load(fh)
with open(POOL, encoding="utf-8") as fh:
    pool = {entry["readable_id"] for entry in json.load(fh) if entry["kind"] == "Item"}

languages = sorted(os.listdir(LOCA))
game_entries = {lang: entries_of(lang, GAME_ITEM_PATH) for lang in languages}

names = {}
type_keys = set()
authored = {}
skipped = {"copyName": 0, "customKey": 0, "debugPath": 0, "outsidePool": 0}
for rid, rec in sorted(items.items()):
    if rec["copyName"]:
        skipped["copyName"] += 1
        continue
    if rec.get("customKey"):
        skipped["customKey"] += 1
        continue
    if rec["path"].startswith("Debug/"):
        skipped["debugPath"] += 1
        continue
    # An item with localization off never asks the database anything, so a present key proves
    # nothing for it - it names itself after its id either way and always needs the redirect.
    if rec["hasLoc"]:
        if rec["path"] not in authored:
            authored[rec["path"]] = entries_of("en", rec["path"])
        if (rid + "_name") in authored[rec["path"]]:
            continue
    if rid not in pool:
        skipped["outsidePool"] += 1
        continue

    names[rid] = CURATED.get(rid, pretty(rid))
    key = type_key(values.get(rid, {}))
    if key:
        type_keys.add(key)

print("items: %d, redirected: %d, mirrored type keys: %s, skipped: %s"
      % (len(items), len(names), sorted(type_keys) or "none", skipped))
for rid, name in sorted(names.items()):
    print("  %-45s %s%s" % (rid, name, "" if rid in CURATED else "   (generated)"))

# language -> key -> text
entries = {}
for lang in languages:
    table = {}
    for rid, name in names.items():
        table[rid + "_name"] = name
    for key in RARITY_KEYS + sorted(type_keys):
        value = game_entries[lang].get(key) or game_entries["en"].get(key)
        if value is None:
            print("WARNING: no value for mirrored key '%s' in any language, tooltip line will error" % key)
            continue
        if key not in game_entries[lang]:
            print("WARNING: %s_%s.loc has no '%s', falling back to the English text" % (GAME_ITEM_PATH, lang, key))
        table[key] = value
    entries[lang] = table

lines = ["// Generated by tools/extract_locations/gen_item_loca_defaults.py. Do not edit by hand.",
         "using System.Collections.Generic;",
         "using static Il2CppCustomFramework.Localization.LocalizationDB;",
         "",
         "namespace ArchipelagoDrova.Data",
         "{",
         "    public static partial class ItemLocaTable",
         "    {",
         "        /// <summary>The loca path this mod owns. It is also the file name the entries are",
         "        /// written to: Localization/&lt;lang&gt;/ArchipelagoDrova_&lt;lang&gt;.loc.</summary>",
         "        public const string LocaPath = %s;" % cs_string(MOD_LOCA_PATH),
         "",
         "        /// <summary>Readable ids of the items redirected to <see cref=\"LocaPath\"/>, either",
         "        /// because the game authored no name for them or because they ship with localization",
         "        /// switched off and name themselves after their id.</summary>",
         "        public static readonly string[] RedirectedItems =",
         "        {"]
for rid in sorted(names):
    lines.append("            %s," % cs_string(rid))
lines += ["        };",
          "",
          "        /// <summary>Language -> key -> text. Item names are English in every language; the",
          "        /// rarity and weapon-type keys are the game's own text, mirrored because the redirect",
          "        /// moves those lookups onto this path as well.</summary>",
          "        public static readonly Dictionary<ELanguage, Dictionary<string, string>> Entries = new Dictionary<ELanguage, Dictionary<string, string>>",
          "        {"]
for lang in languages:
    lines.append("            { ELanguage.%s, new Dictionary<string, string>" % lang)
    lines.append("            {")
    for key, value in sorted(entries[lang].items()):
        lines.append("                { %s, %s }," % (cs_string(key), cs_string(value)))
    lines.append("            } },")
lines += ["        };", "    }", "}", ""]

with open(OUT_CS, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(lines))
print("wrote", os.path.normpath(OUT_CS))
