"""Build tools/extracted/drova_loot.xlsx - every drop chance and stack range in one workbook.

Source data, all produced by the extractors under tools/extract_locations:
  loot_distribution.json  world pickups, destroyable loot tables, resource spots, per-item totals
  chest_slots.json        authored container contents
  item_values.json        buy/sell/rarity/category straight off the Item assets
  quest_items.json        which quests reference which items
  ../apworld/drova/data/items.json   what the randomizer actually does with each item

English display names come from the game's own Items_en.loc so a sheet can be read without
knowing the readable ids.

Sheets:
  Overview        one row per item: where it comes from, how often, min/max stack, pool handling
  Loot tables     per table entry: drop chance, min/max units, chapter gate
  Resource spots  per preset and talent tier: flat amount plus the bonus roll
  World pickups   per item: placements and the stack sizes they hand over
  Container loot  per item: authored slots and their stack sizes
  Quest items     ordinary items a quest touches, with their supply floor

Run: python tools/make_loot_workbook.py
"""
import collections
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTED = os.path.join(REPO, "tools", "extracted")
OUT = os.path.join(EXTRACTED, "drova_loot.xlsx")
GAME_DIR = os.environ.get("DROVA_PATH", r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin")
ITEMS_LOC = os.path.join(GAME_DIR, "Drova_Data", "StreamingAssets", "Localization", "en", "Items_en.loc")

try:
    import xlsxwriter
except ImportError:
    sys.exit("xlsxwriter is required: pip install xlsxwriter")


def load(name, required=True):
    path = os.path.join(EXTRACTED, name)
    if not os.path.exists(path):
        if required:
            sys.exit("missing %s - run the extractor that produces it first" % path)
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_display_names():
    """readable id -> English name. Falls back to the id when the game has no entry."""
    names = {}
    if not os.path.exists(ITEMS_LOC):
        print("WARNING: %s not found - sheets will show readable ids only" % ITEMS_LOC)
        return names
    with open(ITEMS_LOC, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.match(r"\s*(\S+)_name\s*\{\s*(.*?)\s*\}\s*$", line)
            if m:
                names[m.group(1)] = m.group(2)
    return names


CATEGORY_NAMES = {
    0: "Weapon", 1: "Armor", 2: "Consumable", 3: "Misc", 4: "Quest",
}
SUB_NAMES = {
    8: "Ammo", 10: "Crafting stone", 12: "Helmet", 13: "Trinket", 14: "Quiver", 15: "Bag",
    16: "Potion", 17: "Food", 18: "Plant", 19: "Raw food", 20: "Ability scroll",
    21: "Material", 22: "Gatherable", 23: "Writing", 24: "Key", 27: "Flow scroll",
    30: "Currency", 34: "Throwable", 35: "Recipe", 36: "Note",
}


def main():
    dist = load("loot_distribution.json")
    chests = load("chest_slots.json")
    values = load("item_values.json")
    quests = load("quest_items.json", required=False)
    with open(os.path.join(REPO, "apworld", "drova", "data", "items.json"), encoding="utf-8") as fh:
        pool = {i["readable_id"]: i for i in json.load(fh) if i["readable_id"]}
    loca = load_display_names()

    sources = dist.get("sources") or {}
    totals = dist.get("totals") or {}
    amounts = dist.get("amounts") or {}
    tables = dist.get("tables") or {}
    spots = dist.get("resource_spots") or {}

    def name_of(rid):
        return loca.get(rid, rid)

    def stack_range(source, rid):
        """(min, max) authored stack size for an item from one source, or (None, None)."""
        hist = (amounts.get(source) or {}).get(rid)
        if not hist:
            return None, None
        keys = [int(k) for k in hist]
        return min(keys), max(keys)

    wb = xlsxwriter.Workbook(OUT)
    head = wb.add_format({"bold": True, "bg_color": "#DDDDDD", "border": 1, "text_wrap": True, "valign": "top"})
    pct = wb.add_format({"num_format": "0.00%"})
    num2 = wb.add_format({"num_format": "0.00"})

    def sheet(title, columns, rows, widths=None, formats=None):
        ws = wb.add_worksheet(title)
        ws.freeze_panes(1, 1)
        for c, col in enumerate(columns):
            ws.write(0, c, col, head)
            ws.set_column(c, c, (widths or {}).get(c, max(11, min(34, len(col) + 3))),
                          (formats or {}).get(c))
        for r, row in enumerate(rows, start=1):
            for c, cell in enumerate(row):
                ws.write(r, c, cell)
        if rows:
            ws.autofilter(0, 0, len(rows), len(columns) - 1)
        return ws

    # --- Overview -----------------------------------------------------------------------------
    every_id = set(totals) | set(pool) | {rid for rec in chests.values() for rid in
                                          (s["readable_id"] for s in rec.get("slots", []))}
    rows = []
    for rid in sorted(every_id):
        v = values.get(rid) or {}
        p = pool.get(rid) or {}
        t = totals.get(rid) or {}
        per_source = {k: (sources.get(k) or {}).get(rid, {}).get("count", 0)
                      for k in ("world_pickup", "loot_table", "resource_spot", "container_fixloot")}
        mins, maxs = [], []
        for src in ("world_pickup", "resource_spot", "container_fixloot"):
            lo, hi = stack_range(src, rid)
            if lo is not None:
                mins.append(lo)
                maxs.append(hi)
        count = t.get("count", 0)
        units = t.get("amount", 0)
        rows.append([
            name_of(rid), rid,
            CATEGORY_NAMES.get(v.get("main"), v.get("main", "")),
            SUB_NAMES.get(v.get("sub"), v.get("sub", "")),
            v.get("buy", ""), v.get("sell", ""), v.get("rarity", ""),
            round(count, 2), round(units, 2),
            round(units / count, 2) if count else "",
            min(mins) if mins else "", max(maxs) if maxs else "",
            round(per_source["world_pickup"], 2), round(per_source["loot_table"], 2),
            round(per_source["resource_spot"], 2), round(per_source["container_fixloot"], 2),
            p.get("classification", "not in pool"), p.get("amount", ""),
            "yes" if p.get("quest_supply") else "", p.get("supply_group", ""),
        ])
    sheet("Overview",
          ["Item", "readable id", "Category", "Subcategory", "Buy", "Sell", "Rarity",
           "World finds", "World units", "Avg units/find", "Min stack", "Max stack",
           "Pickups", "Loot tables", "Resource spots", "Container slots",
           "AP class", "AP grant", "Quest supply", "Supply group"],
          rows, widths={0: 30, 1: 34})

    # --- Loot tables --------------------------------------------------------------------------
    rows = []
    for tname, rec in sorted(tables.items()):
        for e in rec.get("entries", []):
            rows.append([
                tname, rec.get("placements", 0), rec.get("max_amount", 0),
                name_of(e["readable_id"]), e["readable_id"],
                e["chance"], e.get("effective_chance", e["chance"]),
                e["min"], e["max"],
                round(e.get("effective_chance", e["chance"]) * (e["min"] + e["max"]) / 2.0, 4),
                e.get("chapter", ""),
            ])
    sheet("Loot tables",
          ["Table", "Placements in world", "Max items per roll", "Item", "readable id",
           "Drop chance", "Chance after cap", "Min units", "Max units",
           "Expected units per roll", "Chapter"],
          rows, widths={0: 30, 3: 28, 4: 32}, formats={5: pct, 6: pct, 9: num2})

    # --- Resource spots -----------------------------------------------------------------------
    rows = []
    for sname, rec in sorted(spots.items()):
        for tier in rec.get("tiers", []):
            for e in tier.get("entries", []):
                rows.append([
                    sname, rec.get("placements", 0), tier["tier"],
                    "talent" if e.get("needs_talent") else "base",
                    name_of(e["readable_id"]), e["readable_id"],
                    e["amount"], e["bonus_chance"], e["bonus_amount"],
                    e["min"], e["max"],
                    round(e["amount"] + e["bonus_chance"] * e["bonus_amount"], 3),
                ])
    sheet("Resource spots",
          ["Preset", "Placements in world", "Talent tier", "Requires talent", "Item", "readable id",
           "Base amount", "Bonus chance", "Bonus amount", "Min units", "Max units",
           "Expected units"],
          rows, widths={0: 32, 4: 28, 5: 32}, formats={7: pct, 11: num2})

    # --- World pickups ------------------------------------------------------------------------
    rows = []
    for rid, hist in sorted((amounts.get("world_pickup") or {}).items()):
        keys = sorted(int(k) for k in hist)
        placements = sum(hist.values())
        units = sum(int(k) * v for k, v in hist.items())
        rows.append([
            name_of(rid), rid, placements, units, min(keys), max(keys),
            round(units / placements, 2) if placements else "",
            ", ".join("%sx%d" % (k, hist[str(k)]) for k in keys),
        ])
    sheet("World pickups",
          ["Item", "readable id", "Placements", "Total units", "Min stack", "Max stack",
           "Avg stack", "Stack sizes (size x placements)"],
          rows, widths={0: 28, 1: 32, 7: 34})

    # --- Container loot -----------------------------------------------------------------------
    per_item = collections.defaultdict(collections.Counter)
    quest_slots = collections.Counter()
    for rec in chests.values():
        for slot in rec.get("slots", []):
            per_item[slot["readable_id"]][slot.get("amount") or 1] += 1
            if slot.get("quest"):
                quest_slots[slot["readable_id"]] += 1
    rows = []
    for rid, hist in sorted(per_item.items()):
        keys = sorted(hist)
        slots = sum(hist.values())
        units = sum(k * v for k, v in hist.items())
        rows.append([
            name_of(rid), rid, slots, units, min(keys), max(keys),
            round(units / slots, 2), quest_slots.get(rid, 0),
            ", ".join("%dx%d" % (k, hist[k]) for k in keys),
        ])
    sheet("Container loot",
          ["Item", "readable id", "Authored slots", "Total units", "Min stack", "Max stack",
           "Avg stack", "Quest-flagged slots", "Stack sizes (size x slots)"],
          rows, widths={0: 28, 1: 32, 8: 34})

    # --- Quest items --------------------------------------------------------------------------
    rows = []
    ordinary = set((quests.get("ordinary") or ()))
    by_item = collections.defaultdict(list)
    for gname, g in (quests.get("graphs") or {}).items():
        for rid in g.get("items", []):
            by_item[rid].append(gname)
    for rid in sorted(ordinary):
        p = pool.get(rid) or {}
        t = totals.get(rid) or {}
        graphs = sorted(by_item.get(rid, []))
        rows.append([
            name_of(rid), rid, round(t.get("count", 0), 2),
            p.get("classification", "not in pool"), p.get("amount", ""),
            "yes" if p.get("quest_supply") else "", p.get("supply_group", ""),
            len(graphs), ", ".join(g.replace("DT_Quest_", "") for g in graphs[:6]),
        ])
    sheet("Quest items",
          ["Item", "readable id", "World finds", "AP class", "AP grant", "Quest supply",
           "Supply group", "Graphs", "Referenced by (first 6)"],
          rows, widths={0: 28, 1: 32, 8: 60})

    wb.close()
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()
