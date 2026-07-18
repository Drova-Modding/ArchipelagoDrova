"""
Drova trader / merchant inventory extractor  ->  tools/extracted/traders.json

Emits one Archipelago location per (trader placement, purchasable item) slot. The
downstream location name is "Trader - {trader_label} - {item}" (see gen_data.py),
so trader_label MUST be unique per trader guid.

WHY THIS IS A TWO-ASSET JOIN
---------------------------------------------------------------------------
Trader stock is authored statically, but the stock and the stable runtime guid
live on two different shipped assets that must be joined on the prefab AssetGUID:

  1. Scene `LazyActor` spawners carry the stable, scene-baked 36-char guid the
     client sees at runtime (LazyActor copies its GuidComponent guid onto the
     spawned NPC, cf. investigation) AND `_actorReference.m_AssetGUID` = the
     merchant prefab's addressable GUID.  -> (bakedGuid, assetGUID, worldPos)
  2. The merchant *prefab* bundle carries `Inventory_Trading._tradingItems`
     (the authored stock; the serialized per-slot field is `_item`, a PPtr to
     the Item ScriptableObject, plus `_chapter`).  -> (prefab path, items[])
  3. The prefab's AssetGUID is not on the prefab; it is recovered from the
     addressables catalog (StreamingAssets/aa/catalog.json), mapping the prefab
     asset path (read from the bundle's m_Container) -> GUID.
  4. Join LazyActor.assetGUID == prefab GUID.

Money slots (the currency the trader uses to buy from the player) are excluded:
the currency Item's `_readableId` is "misc_currency" (Item.IsMoney() in-game).

Faction: not stored on the trader; inferred from the LazyActor world position via
the AreaName polygons (same area_for() test as gen_locations.py). Merchants inside
a faction settlement are only reachable when the player sides with that faction, so
a trader whose faction cannot be PROVEN is EXCLUDED entirely -- identical to the
faction-quest rule; an unreachable location breaks generation.

Run from tools/extract_locations (needs script_index.pkl, areas_poly.json). Output
is deterministic (sorted keys). The full bundle sweep takes a few minutes.
"""
import UnityPy, glob, os, pickle, json, sys, time, collections, re, base64

HERE = os.path.dirname(os.path.abspath(__file__))
BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
CATALOG = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\catalog.json"
AREANAMES = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\Localization\en\AreaNames_en.loc"
OUT = os.path.join(HERE, "..", "extracted", "traders.json")

idx = pickle.load(open(os.path.join(HERE, "script_index.pkl"), "rb"))
S = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}
CAB2BUNDLE = {k.lower(): v for k, v in idx["cabs"].items()}

# The in-game currency item (Item.IsMoney()); every trader stocks one slot of it
# to pay the player when selling. Not an item you can take -> excluded.
MONEY_READABLE_IDS = {"misc_currency"}

# --- Faction territory by AreaName KEY -------------------------------------
# Drova has two mutually-exclusive joinable factions. Siding with one makes the
# other faction's merchants refuse to trade (hostile standing), so a merchant
# inside a faction settlement is reachable ONLY when the player sided with that
# faction. Attribution is inferred purely from the LazyActor world position:
#
#   nemeton  -- the Nemeton settlement. Every Nemeton-keyed placement clusters at
#               x~[2.8k..6.3k] y~[-6.2k..-2.6k] (the city), plus its EntryNemeton
#               gate (x~2.4k y~-5.4k) and Sacred Grove. -> NEMETON_AREAS.
#   ruinenlager -- the Remnants / Ruinenlager ("ruins camp") settlement. Verified:
#               the 14 Ruins-keyed merchants form one tight cluster at
#               x~[-1.6k..0.25k] y~[-1k..2.9k], and include NPC_Cuna (the Remnants
#               questgiver, per its DT_Quest_EnterRedTower / ReceiveRunestone
#               dialogue graphs) and NPC_Darwin (a Remnants scientist). The other
#               Ruin* keys are listed for completeness (Remnants-affiliated
#               districts); no merchant resolves to them but they are never neutral.
#   neutral  -- shared open-world areas verified to hold only wandering / roadside
#               traders far from either settlement (Floodplain Forest, the far-NE
#               caves, coniferous forest, moor, forest primeval, tavern).
#
# Any area NOT listed below -- or a position no polygon covers -- is UNPROVABLE, and
# the trader is EXCLUDED entirely, exactly like an unprovable-faction quest (an
# unreachable location breaks generation). Excluding a genuinely-neutral trader only
# loses content; mislabelling a faction-locked trader as neutral breaks seeds, so the
# neutral list is deliberately restricted to the areas observed and vetted here.
NEMETON_AREAS = {"Nemeton", "NemetonHain", "EntryNemeton"}
RUIN_AREAS = {"Ruins", "Ruincamp", "RuinSchmuggler", "RuinExplorer"}
NEUTRAL_AREAS = {"Auwald", "Cave", "Forest", "FriendlyMoor", "Leuchtwald", "Tavern"}


def faction_for(area_key):
    """Return 'nemeton' | 'ruinenlager' | 'neutral', or None if unprovable."""
    if area_key in NEMETON_AREAS:
        return "nemeton"
    if area_key in RUIN_AREAS:
        return "ruinenlager"
    if area_key in NEUTRAL_AREAS:
        return "neutral"
    return None


# --- AreaName polygons (reused from gen_locations.py area_for) --------------
disp = {}
for m in re.finditer(r"^(\S+)\s*\{\s*(.*?)\s*\}",
                     open(AREANAMES, encoding="utf-8", errors="replace").read(), re.M):
    disp[m.group(1)] = m.group(2)

AP = json.load(open(os.path.join(HERE, "areas_poly.json")))
areas = [a for a in AP if a.get("key") and a.get("polys")]
for a in areas:
    pts = [p for poly in a["polys"] for p in poly]
    a["bb"] = (min(p[0] for p in pts), min(p[1] for p in pts),
               max(p[0] for p in pts), max(p[1] for p in pts))


def _in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xint = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
            if x < xint:
                inside = not inside
    return inside


def area_for(x, y):
    """Point-in-polygon against AreaName volumes; ties broken by _priority (higher
    wins). Returns (area_key, display_name) or (None, None). Same logic/behaviour
    as gen_locations.py:area_for(), but also returns the underlying key so faction
    can be classified from it."""
    hits = []
    for a in areas:
        bx0, by0, bx1, by1 = a["bb"]
        if not (bx0 <= x <= bx1 and by0 <= y <= by1):
            continue
        if any(_in_poly(x, y, poly) for poly in a["polys"]):
            hits.append(a)
    if not hits:
        return None, None
    best = max(hits, key=lambda a: (a.get("priority") or 0))
    return best["key"], disp.get(best["key"], best["key"])


# --- Addressables catalog: prefab asset path -> asset GUID ------------------
def load_catalog_path_to_guid():
    """Parse the binary Addressables catalog. Returns {asset_path: guid} for every
    key that is a 32-hex GUID pointing at an "Assets/..." internal id."""
    cat = json.load(open(CATALOG, encoding="utf-8"))
    bucketData = base64.b64decode(cat["m_BucketDataString"])
    keyData = base64.b64decode(cat["m_KeyDataString"])
    entryData = base64.b64decode(cat["m_EntryDataString"])
    internalIds = cat["m_InternalIds"]

    def u32(b, o):
        return int.from_bytes(b[o:o + 4], "little", signed=False)

    def i32(b, o):
        return int.from_bytes(b[o:o + 4], "little", signed=True)

    # buckets: one per key -> (keyDataOffset, [entryIndices])
    nb = u32(bucketData, 0)
    off = 4
    buckets = []
    for _ in range(nb):
        ko = u32(bucketData, off); off += 4
        ec = u32(bucketData, off); off += 4
        ents = [u32(bucketData, off + 4 * j) for j in range(ec)]
        off += 4 * ec
        buckets.append((ko, ents))

    def read_key(p):
        t = keyData[p]
        if t == 0:  # ASCII string
            ln = u32(keyData, p + 1)
            return keyData[p + 5:p + 5 + ln].decode("ascii", "replace")
        if t == 1:  # Unicode string
            ln = u32(keyData, p + 1)
            return keyData[p + 5:p + 5 + ln].decode("utf-16-le", "replace")
        if t == 2:
            return u32(keyData, p + 1)
        if t == 3:
            return int.from_bytes(keyData[p + 1:p + 3], "little")
        if t == 4:
            return i32(keyData, p + 1)
        return None

    # entries: 7 int32 each; we need internalId (index 0)
    ne = u32(entryData, 0)
    entry_internalid = []
    for i in range(ne):
        base = 4 + i * 28
        entry_internalid.append(i32(entryData, base))

    GUIDRE = re.compile(r"^[0-9a-f]{32}$")
    path2guid = {}
    for ko, ents in buckets:
        key = read_key(ko)
        if not (isinstance(key, str) and GUIDRE.match(key)):
            continue
        for ei in ents:
            if not (0 <= ei < ne):
                continue
            iid = entry_internalid[ei]
            if not (0 <= iid < len(internalIds)):
                continue
            path = internalIds[iid]
            if isinstance(path, str) and path.startswith("Assets/"):
                path2guid[path] = key
    return path2guid


def bn(p):
    return os.path.basename(p.replace("\\", "/"))


# --- Sweep every bundle: collect Inventory_Trading prefabs + LazyActors -----
def sweep():
    path2guid = load_catalog_path_to_guid()
    print("catalog: %d asset-path -> guid mappings" % len(path2guid))

    files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
    trading_by_guid = {}   # assetGUID -> {name, items:[(item_ref,(cab,pid)), chapter], bundle}
    placements = []        # {guid, assetGUID, x, y}
    item_need = set()      # (cab_lower, path_id) to resolve in pass 2
    t0 = time.time()

    for bi, f in enumerate(files):
        try:
            env = UnityPy.load(f)
        except Exception:
            continue

        # AssetBundle container: prefab asset path + its root-GO PPtr (m_FileID 0).
        container = []  # (path, root_go_pathid)
        for o in env.objects:
            if o.type.name == "AssetBundle":
                d = o.read_typetree()
                for c in (d.get("m_Container") or []):
                    if not (isinstance(c, (list, tuple)) and len(c) == 2):
                        continue
                    name, info = c
                    ap = info.get("asset") if isinstance(info, dict) else None
                    if ap and ap.get("m_FileID") == 0 and ap.get("m_PathID"):
                        container.append((name, ap["m_PathID"]))
                break

        for cab, sf in env.cabs.items():
            try:
                objlist = list(sf.objects.values())
            except Exception:
                continue
            mb = {}
            by_go = collections.defaultdict(dict)
            tr = {}          # transform pid -> (go, local_pos, father)
            go2tr = {}
            trading_pids = []
            lazy_pids = []
            has_target = False
            for o in objlist:
                try:
                    tn = o.type.name
                    if tn in ("Transform", "RectTransform"):
                        d = o.read_typetree()
                        g = d.get("m_GameObject", {}).get("m_PathID")
                        tr[o.path_id] = (g, d.get("m_LocalPosition") or {},
                                         d.get("m_Father", {}).get("m_PathID"))
                        go2tr[g] = o.path_id
                    elif tn == "MonoBehaviour":
                        d = o.read_typetree()
                        scr = d.get("m_Script") or {}
                        fid, pid = scr.get("m_FileID"), scr.get("m_PathID")
                        if fid is None:
                            continue
                        tcab = sf.name if fid == 0 else bn(sf.externals[fid - 1].path)
                        cls = S.get((tcab.lower(), pid))
                        if not cls:
                            continue
                        mb[o.path_id] = (cls, d)
                        by_go[d.get("m_GameObject", {}).get("m_PathID")][cls] = d
                        if cls == "Inventory_Trading":
                            trading_pids.append(o.path_id); has_target = True
                        elif cls == "LazyActor":
                            lazy_pids.append(o.path_id); has_target = True
                except Exception:
                    continue
            if not has_target:
                continue

            def root_go(go):
                t = go2tr.get(go); n = 0
                last = go
                while t is not None and n < 64:
                    g, _lp, fp = tr.get(t, (None, None, None))
                    last = g
                    if not fp or fp not in tr:
                        break
                    t = fp; n += 1
                return last

            def world_pos(go):
                x = y = 0.0
                t = go2tr.get(go); n = 0
                while t is not None and n < 64:
                    g, lp, fp = tr[t]
                    x += lp.get("x", 0.0); y += lp.get("y", 0.0)
                    if not fp or fp not in tr:
                        break
                    t = fp; n += 1
                return round(x, 2), round(y, 2)

            def ext_ref(pptr):
                """PPtr -> (cab_lower, path_id) or None."""
                if not pptr or not pptr.get("m_PathID"):
                    return None
                fid = pptr.get("m_FileID", 0)
                if fid == 0:
                    tcab = sf.name
                else:
                    try:
                        tcab = bn(sf.externals[fid - 1].path)
                    except Exception:
                        return None
                return (tcab.lower(), pptr["m_PathID"])

            # -- Inventory_Trading prefabs -> assetGUID via container/catalog --
            if trading_pids:
                # map root-GO pathid -> prefab path (from this bundle's container)
                rootgo2path = {rp: name for name, rp in container}
                prefab_paths = [name for name, rp in container if name.endswith(".prefab")]
                for pid in trading_pids:
                    _cls, d = mb[pid]
                    tgo = d.get("m_GameObject", {}).get("m_PathID")
                    rgo = root_go(tgo)
                    path = rootgo2path.get(rgo)
                    if path is None and len(prefab_paths) == 1:
                        path = prefab_paths[0]     # single-prefab bundle fallback
                    guid = path2guid.get(path) if path else None
                    if not guid:
                        continue
                    items = []
                    for it in (d.get("_tradingItems") or []):
                        ip = it.get("_item") or it.get("Item") or {}
                        ref = ext_ref(ip)
                        if ref is None:
                            continue               # null / empty slot
                        item_need.add(ref)
                        items.append((ref, it.get("_chapter") or 0))
                    trading_by_guid[guid] = {
                        "name": gon_name(rgo, by_go, sf),
                        "items": items,
                        "bundle": os.path.basename(f),
                    }

            # -- LazyActor scene placements -> (baked guid, assetGUID, pos) ----
            for pid in lazy_pids:
                _cls, d = mb[pid]
                go = d.get("m_GameObject", {}).get("m_PathID")
                sibs = by_go.get(go, {})
                guid = None
                for scls, sd in sibs.items():
                    if "Guid" in scls:
                        gs = sd.get("_guidString")
                        if gs and len(gs) == 36:
                            guid = gs
                            break
                ar = d.get("_actorReference") or {}
                aguid = ar.get("m_AssetGUID")
                if not (guid and aguid):
                    continue
                wx, wy = world_pos(go)
                placements.append({"guid": guid, "assetGUID": aguid, "x": wx, "y": wy})

        if bi % 400 == 0:
            print("  sweep %d/%d  trading=%d placements=%d  %.0fs"
                  % (bi, len(files), len(trading_by_guid), len(placements), time.time() - t0))
            sys.stdout.flush()

    print("sweep DONE %.0fs  trading_prefabs=%d placements=%d item_refs=%d"
          % (time.time() - t0, len(trading_by_guid), len(placements), len(item_need)))
    return trading_by_guid, placements, item_need


def gon_name(go, by_go, sf):
    """GameObject m_Name for a path_id (read lazily from the cab)."""
    o = sf.objects.get(go)
    if o is None:
        return None
    try:
        return o.read_typetree().get("m_Name")
    except Exception:
        return None


# --- Pass 2: resolve item PPtrs -> (guid, readable_id) ----------------------
def resolve_items(item_need):
    by_bundle = collections.defaultdict(set)
    unmapped = 0
    for cab, pid in item_need:
        b = CAB2BUNDLE.get(cab)
        if b:
            by_bundle[b].add((cab, pid))
        else:
            unmapped += 1
    if unmapped:
        print("WARNING: %d item refs in cabs not in script_index cab map" % unmapped)

    resolved = {}   # (cab_lower, path_id) -> {"guid":..., "readable_id":...}
    t0 = time.time()
    for bi, (b, refs) in enumerate(sorted(by_bundle.items())):
        try:
            env = UnityPy.load(os.path.join(BD, b))
        except Exception as e:
            print("FAIL", b, e)
            continue
        for cab, sf in env.cabs.items():
            cl = cab.lower()
            for c, pid in refs:
                if c != cl:
                    continue
                o = sf.objects.get(pid)
                if o is None:
                    continue
                try:
                    d = o.read_typetree()
                except Exception:
                    continue
                resolved[(c, pid)] = {
                    "guid": d.get("_guid"),
                    "readable_id": d.get("_readableId"),
                }
        if bi % 200 == 0:
            print("  resolve %d/%d  %.0fs" % (bi, len(by_bundle), time.time() - t0))
            sys.stdout.flush()
    print("resolve DONE %.0fs  resolved=%d/%d" % (time.time() - t0, len(resolved), len(item_need)))
    return resolved


def build_labels(kept_traders):
    """Assign a UNIQUE human label per distinct trader_guid.

    Base label = prefab name with a leading "NPC_" stripped, underscores -> spaces,
    title-cased (e.g. NPC_Cuna -> "Cuna"). Two distinct trader guids can share a base
    label (the same prefab placed twice, e.g. NPC_Darwin). Disambiguation, applied
    per colliding base-label group and fully deterministic:
      1. If appending the resolved area makes every guid in the group unique, use
         "Base (Area)".
      2. Otherwise fall back to "Base #i", where i is the 1-based rank of the guid
         within the group ordered by the guid string.
    kept_traders: {trader_guid: {"name":prefab_name, "area":dispname}}.
    Returns {trader_guid: label}.
    """
    def base_of(name):
        n = name or "Trader"
        if n.startswith("NPC_"):
            n = n[4:]
        return n.replace("_", " ").strip().title() or "Trader"

    groups = collections.defaultdict(list)   # base -> [guid,...]
    for g, info in kept_traders.items():
        groups[base_of(info["name"])].append(g)

    labels = {}
    for base, guids in groups.items():
        if len(guids) == 1:
            labels[guids[0]] = base
            continue
        area_labels = {g: "%s (%s)" % (base, kept_traders[g]["area"] or "Unknown") for g in guids}
        if len(set(area_labels.values())) == len(guids):
            labels.update(area_labels)
        else:
            for i, g in enumerate(sorted(guids), 1):
                labels[g] = "%s #%d" % (base, i)
    return labels


def main():
    trading_by_guid, placements, item_need = sweep()
    resolved = resolve_items(item_need)

    # Attribute each placement to an area/faction. A placement whose merchant prefab
    # has no trading stock is not a trader; drop silently.
    n_no_stock = n_no_faction = 0
    kept_traders = {}          # trader_guid -> {name, area(disp), area_key, faction}
    trader_placements = []     # (trader_guid, trading_record, area_disp, faction)
    excluded_areas = collections.Counter()
    for pl in placements:
        rec = trading_by_guid.get(pl["assetGUID"])
        if rec is None:
            n_no_stock += 1
            continue
        area_key, area_disp = area_for(pl["x"], pl["y"])
        faction = faction_for(area_key)
        if faction is None:
            n_no_faction += 1
            excluded_areas[area_key or "<no polygon>"] += 1
            continue
        tguid = pl["guid"].lower()
        kept_traders[tguid] = {"name": rec["name"], "area": area_disp or "",
                               "area_key": area_key, "faction": faction,
                               "x": pl["x"], "y": pl["y"]}
        trader_placements.append((tguid, rec, area_disp or "", faction))

    labels = build_labels(kept_traders)

    # Build slots, collapsing (trader, item) duplicates that differ only by _chapter
    # (keep the lowest chapter). Key = "<traderGuid>:<itemGuid>" (both lowercased).
    out = {}
    lowest_chapter = {}
    n_money = n_dup = n_unresolved = 0
    for tguid, rec, area_disp, faction in trader_placements:
        label = labels[tguid]
        for ref, chapter in rec["items"]:
            info = resolved.get(ref)
            if not info or not info.get("guid"):
                n_unresolved += 1
                continue
            readable = info.get("readable_id") or ""
            if readable in MONEY_READABLE_IDS:
                n_money += 1
                continue
            iguid = info["guid"].lower()
            key = "%s:%s" % (tguid, iguid)
            if key in out:
                n_dup += 1
                if chapter < lowest_chapter.get(key, 1 << 30):
                    lowest_chapter[key] = chapter   # keep lowest chapter (record only)
                continue
            lowest_chapter[key] = chapter
            out[key] = {
                "trader_guid": tguid,
                "trader_label": label,
                "item_guid": iguid,
                "item_readable_id": readable,
                "area": area_disp,
                "faction": faction,
            }

    out = {k: out[k] for k in sorted(out)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, sort_keys=True)

    # --- summary ---
    fac_counts = collections.Counter(v["faction"] for v in out.values())
    kept_trader_guids = {v["trader_guid"] for v in out.values()}
    print("\n=== SUMMARY ===")
    print("traders kept (distinct guids): %d" % len(kept_trader_guids))
    print("slots kept:                    %d" % len(out))
    print("faction split (slots):         nemeton=%d ruinenlager=%d neutral=%d"
          % (fac_counts["nemeton"], fac_counts["ruinenlager"], fac_counts["neutral"]))
    fac_traders = collections.Counter(kept_traders[g]["faction"] for g in kept_trader_guids)
    print("faction split (traders):       nemeton=%d ruinenlager=%d neutral=%d"
          % (fac_traders["nemeton"], fac_traders["ruinenlager"], fac_traders["neutral"]))
    print("placements dropped, no stock:  %d" % n_no_stock)
    print("placements EXCLUDED, unprovable faction: %d" % n_no_faction)
    if excluded_areas:
        print("  excluded-by-area:", dict(excluded_areas))
    print("money slots dropped:           %d" % n_money)
    print("duplicate (chapter) slots dropped: %d" % n_dup)
    print("item refs unresolved (dropped):    %d" % n_unresolved)
    print("labels: %d distinct across %d trader guids"
          % (len(set(labels[g] for g in kept_trader_guids)), len(kept_trader_guids)))

    print("\nper-area kept traders (by KEY):")
    for (ak, adisp, fac), n in sorted(collections.Counter(
            (kept_traders[g]["area_key"], kept_traders[g]["area"], kept_traders[g]["faction"])
            for g in kept_trader_guids).items()):
        print("  key=%-16s (%-22s) %-12s %d" % (ak, adisp, fac, n))

    if os.environ.get("TRADERS_DEBUG"):
        dbg = [{"label": labels[g], "name": kept_traders[g]["name"],
                "area_key": kept_traders[g]["area_key"], "area": kept_traders[g]["area"],
                "faction": kept_traders[g]["faction"],
                "x": kept_traders[g]["x"], "y": kept_traders[g]["y"]}
               for g in kept_trader_guids]
        dbg.sort(key=lambda r: (r["area_key"] or "", r["label"]))
        json.dump(dbg, open(os.environ["TRADERS_DEBUG"], "w"), indent=1)
        print("wrote debug ->", os.environ["TRADERS_DEBUG"])

    print("\nsample entries:")
    for k in list(out)[:4]:
        print("  %s -> %s" % (k, out[k]))
    print("\nwrote %s  (%d slots)" % (os.path.normpath(OUT), len(out)))


if __name__ == "__main__":
    main()
