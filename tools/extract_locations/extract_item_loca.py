"""Extract every Item asset's localization wiring (loca path, copy-from-item and custom-key flags).

Output: tools/extracted/item_loca.json
  { readable_id: {path, hasLoc, copyName, customKey: [path, key] | null} }

`Item.GetLocalizedItemName()` resolves `LocalizationDB.Localize(_locaPath, _readableId + "_name")`,
so an item whose `<_locaPath>_<lang>.loc` file has no `<readable_id>_name` entry renders as the raw
error string "[LOCA] Key not found: ...". Vanilla never hands several of those items to the player,
so the gap only shows once the randomizer starts distributing them - see gen_item_loca_defaults.py,
which diffs this against the shipped .loc files.

Two wirings make a missing key harmless and are recorded so the diff can skip them: `copyName` items
pull their name from another Item entirely (`_copyLocaItem`), and `customKey` items name themselves
through a `[SerializeReference] LocalizedString` pointing somewhere else - every quest letter uses it
to show its own title out of `Letters/<chapter>`. `_customLocaKey` exists only in the shipped
GameAssembly; the `Managed\\Drova.dll` in the game folder predates it and does not mention the field.
"""
import UnityPy, glob, os, json, sys, time

BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extracted", "item_loca.json")


def custom_loca_key(d):
    """Resolve the _customLocaKey SerializeReference into [locaPath, locaKey], or None."""
    rid = (d.get("_customLocaKey") or {}).get("rid", -2)
    if rid in (-1, -2):
        return None
    for ref in (d.get("references") or {}).get("RefIds", []):
        if ref.get("rid") != rid:
            continue
        data = ref.get("data") or {}
        path, key = data.get("_path"), data.get("_key")
        return [path, key] if path and key else None
    return None


files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
print("bundles:", len(files)); sys.stdout.flush()

items = {}
t0 = time.time()
for i, f in enumerate(files):
    try:
        env = UnityPy.load(f)
    except Exception:
        continue
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        try:
            d = o.read_typetree()
        except Exception:
            continue
        rid = d.get("_readableId")
        # _locaPath is Item-specific; _buyValue keeps other _readableId carriers (recipes) out.
        if not rid or "_locaPath" not in d or "_buyValue" not in d:
            continue
        rec = {"path": d.get("_locaPath") or "Items",
               "hasLoc": int(bool(d.get("_hasLocalization", 1))),
               "copyName": int(bool(d.get("_copyLocaFromItem", 0)) and bool(d.get("_copyName", 1))),
               "customKey": custom_loca_key(d)}
        prev = items.get(rid)
        if prev is not None and prev != rec:
            print("WARN: conflicting loca wiring for %s: %s vs %s (keeping first)" % (rid, prev, rec))
            continue
        items[rid] = rec
    del env
    if i % 400 == 0:
        print("  %d/%d items=%d %.0fs" % (i, len(files), len(items), time.time() - t0)); sys.stdout.flush()

print("items:", len(items), "%.0fs" % (time.time() - t0))
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(items, fh, indent=1, sort_keys=True)
    fh.write("\n")
print("wrote", os.path.normpath(OUT))
