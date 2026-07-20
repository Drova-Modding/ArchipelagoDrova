"""Extract scene-placed NPC spawners (LazyActor) with their stable guids.

NPCs are not scene-baked actors: they are spawned at runtime by LazyActor (Drova.Utilities.
LazyLoading), which stamps the spawned actor's GuidComponent with ITS OWN scene-baked guid
(LazyActor._guid = base.GuidComponent.GetGuid(); actor.GetGuidComponent().SetNewGuid(_guid)).
The save then persists the actor under "GO#<that guid>", so the LazyActor guid is the stable,
per-install identity for the NPC - verified: every actor block in a real save matches a LazyActor
guid extracted here.

Also extracts every Actor prefab's serialized CustomStats._disableBrawlLoot (the flag that stops
the knockout-loot window from ever spawning - BrawlActor.AddLooter early-outs on it), joined onto
the spawner rows by the prefab's addressables asset guid (LazyActor._actorReference.m_AssetGUID).

Output: npcs.json  { guid: { name, scene, x, y, is_npc, prefab_guid, prefab, disable_brawl_loot } }
"""
import UnityPy, glob, os, pickle, json, sys, time, re

BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
idx = pickle.load(open("script_index.pkl", "rb"))
S = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}

files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
spawners = {}
prefabs = {}   # prefab asset: root GameObject name -> disable_brawl_loot (joined by name later)
t0 = time.time()

# --refine-only: skip the bundle scan and rebuild npcs.json from the cached raw files.
if "--refine-only" in sys.argv:
    spawners = json.load(open("npcs_raw.json"))
    prefabs = json.load(open("actor_defs.json"))
    files = []

for bi, f in enumerate(files):
    try:
        env = UnityPy.load(f)
    except Exception:
        continue
    for cab, sf in env.cabs.items():
        try:
            objlist = list(sf.objects.values())
        except Exception:
            continue
        gon, tr, go2tr, mb = {}, {}, {}, {}
        by_go = {}
        for o in objlist:
            try:
                tn = o.type.name
                if tn == "GameObject":
                    gon[o.path_id] = o.read_typetree().get("m_Name")
                elif tn in ("Transform", "RectTransform"):
                    d = o.read_typetree()
                    g = d.get("m_GameObject", {}).get("m_PathID")
                    tr[o.path_id] = (g, d.get("m_LocalPosition") or {}, d.get("m_Father", {}).get("m_PathID"))
                    go2tr[g] = o.path_id
                elif tn == "MonoBehaviour":
                    d = o.read_typetree()
                    scr = d.get("m_Script") or {}
                    fid, pid = scr.get("m_FileID"), scr.get("m_PathID")
                    if fid is None:
                        continue
                    tcab = sf.name if fid == 0 else os.path.basename(sf.externals[fid - 1].path.replace("\\", "/"))
                    cls = S.get((tcab.lower(), pid))
                    if not cls:
                        continue
                    g = d.get("m_GameObject", {}).get("m_PathID")
                    mb[o.path_id] = (cls, d, g)
                    by_go.setdefault(g, {})[cls] = d
            except Exception:
                continue
        if not mb:
            continue

        def world_pos(gpid):
            x = y = 0.0
            t = go2tr.get(gpid)
            n = 0
            while t is not None and n < 64:
                g, lp, fp = tr[t]
                x += lp.get("x", 0.0)
                y += lp.get("y", 0.0)
                if not fp or fp not in tr:
                    break
                t = fp
                n += 1
            return round(x, 2), round(y, 2)

        for pid, (cls, d, g) in mb.items():
            if cls == "LazyActor":
                sibs = by_go.get(g, {})
                gc = sibs.get("GuidComponent")
                guid = (gc or {}).get("_guidString")
                if not guid:
                    continue
                ref = d.get("_actorReference") or {}
                x, y = world_pos(g)
                spawners[guid] = {
                    "name": gon.get(g),
                    "scene": os.path.basename(f),
                    "x": x, "y": y,
                    "is_npc": bool(d.get("_isNpc")),
                    "prefab_guid": ref.get("m_AssetGUID") or "",
                }
            elif cls == "Actor":
                # Prefab (or scene) actor definition: CustomStats is a serialized module.
                stats = d.get("_customStats") or {}
                if "_disableBrawlLoot" in stats:
                    prefabs.setdefault(gon.get(g) or "", {})
                    prefabs[gon.get(g) or ""] = {
                        "disable_brawl_loot": bool(stats.get("_disableBrawlLoot")),
                        "is_npc_stats": bool(stats.get("_isNPC")),
                    }
    if bi % 400 == 0:
        print(f"  {bi}/{len(files)} spawners={len(spawners)} actor_defs={len(prefabs)} {time.time()-t0:.0f}s")
        sys.stdout.flush()

print(f"DONE {time.time()-t0:.0f}s spawners={len(spawners)} actor_defs={len(prefabs)}")
json.dump(spawners, open("npcs_raw.json", "w"), indent=1)
json.dump(prefabs, open("actor_defs.json", "w"), indent=1)
print("wrote npcs_raw.json / actor_defs.json")

# --- refine: the curated mugging table ------------------------------------------------------------
# Keep named settlement NPCs (LazyActor_NPC_*), drop the ones whose prefab disables brawl loot
# (BrawlActor.AddLooter early-outs on CustomStats._disableBrawlLoot: the mug window never spawns,
# so the location could never send). Faction comes from the trader table where the same guid sells
# goods (proven at extraction), else from the majority faction of the traders in the same area
# (the camps are faction-homogeneous), else neutral.
NPC_PREFIX = "LazyActor_NPC_"

# Area resolution: same polygon volumes gen_locations.py uses.
LOC = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\Localization\en\AreaNames_en.loc"
disp = {}
for m in re.finditer(r"^(\S+)\s*\{\s*(.*?)\s*\}", open(LOC, encoding="utf-8", errors="replace").read(), re.M):
    disp[m.group(1)] = m.group(2)
AP = json.load(open("areas_poly.json"))
areas = [a for a in AP if a.get("key") and a.get("polys")]
for a in areas:
    pts = [p for poly in a["polys"] for p in poly]
    a["bb"] = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


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
    hits = [a for a in areas
            if a["bb"][0] <= x <= a["bb"][2] and a["bb"][1] <= y <= a["bb"][3]
            and any(_in_poly(x, y, poly) for poly in a["polys"])]
    if not hits:
        return ""
    best = max(hits, key=lambda a: (a.get("priority") or 0))
    return disp.get(best["key"], best["key"])


traders = json.load(open("../extracted/traders.json"))
trader_faction = {}
area_factions = {}
for key, rec in traders.items():
    guid = key.split(":")[0]
    trader_faction[guid] = rec.get("faction", "neutral")
    if rec.get("area"):
        area_factions.setdefault(rec["area"], []).append(rec.get("faction", "neutral"))


def area_faction(area):
    votes = [f for f in area_factions.get(area, []) if f in ("nemeton", "ruinenlager")]
    if votes and all(v == votes[0] for v in votes):
        return votes[0]
    return "neutral"


def prefab_of(spawner_name):
    base = spawner_name[len("LazyActor_"):]
    for candidate in (base, re.sub(r"_\d+$", "", base)):
        if candidate in prefabs:
            return candidate, prefabs[candidate]
    return base, None


refined = {}
dropped_loot = []
for guid, rec in sorted(spawners.items()):
    name = rec.get("name") or ""
    if not rec["is_npc"] or not name.startswith(NPC_PREFIX):
        continue
    prefab_name, definition = prefab_of(name)
    if definition and definition["disable_brawl_loot"]:
        dropped_loot.append(name)
        continue
    area = area_for(rec["x"], rec["y"])
    refined[guid] = {
        # Trailing spawner counters ("Ada_01") are authoring noise, not identity; duplicates that
        # collide after stripping get a stable numeric suffix below.
        "label": re.sub(r"_\d+$", "", name[len(NPC_PREFIX):]),
        "area": area,
        "x": rec["x"], "y": rec["y"],
        "prefab": prefab_name,
        "faction": trader_faction.get(guid) or area_faction(area),
    }

# Duplicate labels (two spawners of the same NPC) get a stable numeric suffix by guid order.
by_label = {}
for guid in sorted(refined):
    by_label.setdefault(refined[guid]["label"], []).append(guid)
for label, guids in by_label.items():
    if len(guids) > 1:
        for i, guid in enumerate(guids, 1):
            refined[guid]["label"] = "%s %d" % (label, i)

json.dump(refined, open("../extracted/npcs.json", "w"), indent=1, sort_keys=True)
print(f"refined muggable NPCs: {len(refined)} (dropped {len(dropped_loot)} with disabled brawl loot: {dropped_loot})")
import collections
print("factions:", dict(collections.Counter(r['faction'] for r in refined.values())))
