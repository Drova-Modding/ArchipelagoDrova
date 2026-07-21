"""Extract every Item asset's buy/sell values, quest-category flag and authored category.

Output: tools/extracted/item_values.json
  { readable_id: {buy, sell, cat, cls, main, sub, rarity} }

`main`/`sub` are the game's own ItemMainCategory/ItemSubCategory enums (Drova.Items) - the
authored statement of what an item IS. gen_data.py uses them to classify equippable accessories
(Armor_Trinket=13 / Armor_Quiver=14 / Armor_Bag=15) as useful instead of guessing from ids or
prices: a "Boar Skull" is a trinket with a passive effect, not sale junk. `cls` is the asset's
MonoBehaviour class (always plain Item as of the current game build).

The game's Item.IsQuestItem is value-derived (buy == 0 && sell == 0), while _isInQuestCategory is
the separately authored UI flag. gen_data.py uses the values to keep quest-stage items (talisman
stones, lore letters, story props) out of the AP item pool: granting an item the game itself prices
as unsellable quest property is the sequence-skip direction. The category flag is recorded for
reference and for the client-side protection parity checks.

Items live in the item-database bundle, but the scan covers every bundle so a future content patch
that splits the database cannot silently truncate the output.
"""
import UnityPy, glob, os, json, sys, time, pickle

BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extracted", "item_values.json")

idx = pickle.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "script_index.pkl"), "rb"))
SCRIPTS = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}

files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
print("bundles:", len(files)); sys.stdout.flush()

values = {}
t0 = time.time()
for i, f in enumerate(files):
    try:
        env = UnityPy.load(f)
    except Exception:
        continue
    for cab, sf in env.cabs.items():
        try:
            objs = list(sf.objects.values())
        except Exception:
            continue
        for o in objs:
            if o.type.name != "MonoBehaviour":
                continue
            try:
                d = o.read_typetree()
            except Exception:
                continue
            rid = d.get("_readableId")
            if not rid or "_buyValue" not in d or "_sellValue" not in d:
                continue
            scr = d.get("m_Script") or {}
            fid, pid = scr.get("m_FileID"), scr.get("m_PathID")
            tcab = sf.name if fid == 0 else os.path.basename(sf.externals[fid - 1].path.replace("\\", "/"))
            icat = d.get("_itemCategory") or {}
            rec = {"buy": d["_buyValue"], "sell": d["_sellValue"],
                   "cat": int(bool(d.get("_isInQuestCategory", 0))),
                   "cls": SCRIPTS.get((tcab.lower(), pid), "?"),
                   "main": icat.get("_itemMainCategory", -1),
                   "sub": icat.get("_itemSubCategory", 0),
                   "rarity": d.get("_rarity", 0)}
            prev = values.get(rid)
            if prev is not None and prev != rec:
                print("WARN: conflicting values for %s: %s vs %s (keeping first)" % (rid, prev, rec))
                continue
            values[rid] = rec
    del env
    if i % 400 == 0:
        print("  %d/%d items=%d %.0fs" % (i, len(files), len(values), time.time() - t0)); sys.stdout.flush()

print("items:", len(values), "%.0fs" % (time.time() - t0))
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(values, fh, indent=1, sort_keys=True)
    fh.write("\n")
print("wrote", os.path.normpath(OUT))
