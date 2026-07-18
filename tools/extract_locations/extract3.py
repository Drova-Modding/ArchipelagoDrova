"""
DEFINITIVE Drova saveable-object extractor.
Reproduces the runtime save's `dynamicSavedObjects` map ("GO#<guid>") STATICALLY from shipped bundles.

Model (verified against real chest hierarchy):
  Container_Chest_Vertical   [GuidComponent, Depot_Wrapper]   <- container root; owns the GUID
    Interaction              [Interact_Bhvr_LootInventory, Interact_LootBhvr_Chest, ...]
    Saving                   [SaveRoot_Guid, Saveable_Depot, Saveable_Inventory]
    Inventory                [Inventory, Inventory_LootBhvr]
  SaveRoot_Guid._guidComponent -> PPtr -> GuidComponent._guidString  == save key
"""
import UnityPy, glob, os, pickle, json, sys, time, collections, re

BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
idx = pickle.load(open("script_index.pkl", "rb"))
S = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}
CABRE = re.compile(r"^cab-[0-9a-f]{32}$")

LOOT_SAVEABLES = {"Saveable_Depot", "Saveable_LootInventory", "Saveable_PickUp_Once",
                  "Saveable_LootTablePickups", "Saveable_ResourceSpot", "Saveable_Inventory"}

files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
out, areas = [], []
t0 = time.time()

for bi, f in enumerate(files):
    try:
        env = UnityPy.load(f)
    except Exception:
        continue
    scene_paths, is_scene = [], False
    for o in env.objects:
        if o.type.name == "AssetBundle":
            d = o.read_typetree()
            is_scene = bool(d.get("m_IsStreamedSceneAssetBundle"))
            cont = d.get("m_Container") or []
            scene_paths = [c[0] if isinstance(c, (list, tuple)) else c for c in cont]
            break
    base = [c for c in env.cabs if CABRE.match(c)]
    cab2scene = dict(zip(base, scene_paths)) if (is_scene and len(base) == len(scene_paths)) else {}

    for cab, sf in env.cabs.items():
        try:
            objlist = list(sf.objects.values())
        except Exception:
            continue
        gon, tr, go2tr = {}, {}, {}
        mb = {}                       # path_id -> (cls, dict)
        by_go = collections.defaultdict(dict)   # go path_id -> {cls: dict}
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
                    if fid is None: continue
                    tcab = sf.name if fid == 0 else os.path.basename(sf.externals[fid-1].path.replace("\\", "/"))
                    cls = S.get((tcab.lower(), pid))
                    if not cls: continue
                    mb[o.path_id] = (cls, d)
                    by_go[d.get("m_GameObject", {}).get("m_PathID")][cls] = d
            except Exception:
                continue
        if not mb: continue

        def world_pos(gpid):
            x = y = 0.0; t = go2tr.get(gpid); n = 0
            while t is not None and n < 64:
                g, lp, fp = tr[t]
                x += lp.get("x", 0.0); y += lp.get("y", 0.0)
                if not fp or fp not in tr: break
                t = fp; n += 1
            return round(x, 2), round(y, 2)

        scene = cab2scene.get(cab, "")
        for gpid, cs in by_go.items():
            if "AreaName" in cs:
                ax, ay = world_pos(gpid)
                areas.append({"key": cs["AreaName"].get("_areaKey"), "scene": scene, "x": ax, "y": ay})

        # --- authoritative: iterate SaveRoot_Guid, resolve _guidComponent PPtr ---
        for pid, (cls, d) in mb.items():
            if cls not in ("SaveRoot_Guid", "SaveRoot_Dynamic"): continue
            save_go = d.get("m_GameObject", {}).get("m_PathID")
            sibs = by_go.get(save_go, {})
            saveables = sorted(c for c in sibs if c.startswith("Saveable_"))
            if cls == "SaveRoot_Dynamic":
                out.append({"key": None, "kind": "DYNAMIC", "saveables": saveables,
                            "scene": scene, "bundle": os.path.basename(f)})
                continue
            custom = (d.get("_customSaveKey") or "").strip()
            gc_ptr = d.get("_guidComponent") or {}
            guid = owner_go = None
            if gc_ptr.get("m_FileID") == 0 and gc_ptr.get("m_PathID"):
                g = mb.get(gc_ptr["m_PathID"])
                if g and g[0] == "GuidComponent":
                    guid = g[1].get("_guidString")
                    owner_go = g[1].get("m_GameObject", {}).get("m_PathID")
            key = custom or guid
            if not key: continue
            root = owner_go if owner_go is not None else save_go
            wx, wy = world_pos(root)
            # loot behaviours anywhere in the owner's subtree (children of root)
            subtree_cls = set()
            rt = go2tr.get(root)
            for tpid, (g2, lp2, fp2) in tr.items():
                if fp2 == rt or g2 == root:
                    subtree_cls |= set(by_go.get(g2, {}))
            out.append({
                "key": key, "kind": "GUID", "custom": bool(custom),
                "name": gon.get(root), "saveables": saveables,
                "loot": sorted(set(subtree_cls) & {
                    "Interact_Bhvr_LootInventory", "Interact_LootBhvr_Chest", "Depot_Wrapper",
                    "PickupInteraction", "ResourceSpotReward", "Interact_Bhvr_LootKnockout"}),
                "is_loot": bool(set(saveables) & LOOT_SAVEABLES),
                "scene": scene, "bundle": os.path.basename(f), "x": wx, "y": wy,
            })
    if bi % 400 == 0:
        print(f"  {bi}/{len(files)} out={len(out)} {time.time()-t0:.0f}s"); sys.stdout.flush()

print(f"DONE {time.time()-t0:.0f}s entries={len(out)} areas={len(areas)}")
json.dump(out, open("saveobjects.json", "w"), indent=1)
json.dump(areas, open("areas3.json", "w"), indent=1)
