"""Extract OW_Teleporter gate network from Drova bundles.

Pass 1: find bundles containing Scene_Teleporters.unity (cheap header scan).
Pass 2: deep-parse those bundles; dump every GO that owns OW_Teleporter,
HitReceiveBhvr_OW_Teleporter or Interact_Bhvr_Teleport, with world pos,
_targetPos, move dirs, GO active state, parent-chain names and sibling classes.
"""
import UnityPy, glob, os, pickle, json, sys, time, collections

BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
IDXDIR = r"C:\Users\fpabs\source\repos\ArchipelagoDrova\tools\extract_locations"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "teleporters.json")

idx = pickle.load(open(os.path.join(IDXDIR, "script_index.pkl"), "rb"))
S = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}

WANT = {"OW_Teleporter", "HitReceiveBhvr_OW_Teleporter", "Interact_Bhvr_Teleport"}

files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
t0 = time.time()

# pass 1: which bundles hold Scene_Teleporters (or logic scenes)
targets = []
for bi, f in enumerate(files):
    try:
        env = UnityPy.load(f)
    except Exception:
        continue
    for o in env.objects:
        if o.type.name == "AssetBundle":
            d = o.read_typetree()
            cont = d.get("m_Container") or []
            paths = [c[0] if isinstance(c, (list, tuple)) else c for c in cont]
            if any("teleporter" in (p or "").lower() for p in paths):
                targets.append((f, paths))
            break
    if bi % 500 == 0:
        print(f"pass1 {bi}/{len(files)} {time.time()-t0:.0f}s hits={len(targets)}"); sys.stdout.flush()

print("TARGET BUNDLES:", [(os.path.basename(f), p) for f, p in targets]); sys.stdout.flush()

results = []
for f, paths in targets:
    env = UnityPy.load(f)
    scene_paths, is_scene = [], False
    for o in env.objects:
        if o.type.name == "AssetBundle":
            d = o.read_typetree()
            is_scene = bool(d.get("m_IsStreamedSceneAssetBundle"))
            cont = d.get("m_Container") or []
            scene_paths = [c[0] if isinstance(c, (list, tuple)) else c for c in cont]
            break
    base = [c for c in env.cabs if c.startswith("cab-")]
    cab2scene = dict(zip(base, scene_paths)) if (is_scene and len(base) == len(scene_paths)) else {}

    for cab, sf in env.cabs.items():
        try:
            objlist = list(sf.objects.values())
        except Exception:
            continue
        gon, goact, tr, go2tr = {}, {}, {}, {}
        mb, by_go = {}, collections.defaultdict(dict)
        for o in objlist:
            try:
                tn = o.type.name
                if tn == "GameObject":
                    d = o.read_typetree()
                    gon[o.path_id] = d.get("m_Name")
                    goact[o.path_id] = d.get("m_IsActive")
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

        def world_pos(gpid):
            x = y = 0.0; t = go2tr.get(gpid); n = 0
            while t is not None and n < 64:
                g, lp, fp = tr[t]
                x += lp.get("x", 0.0); y += lp.get("y", 0.0)
                if not fp or fp not in tr: break
                t = fp; n += 1
            return round(x, 2), round(y, 2)

        def chain_names(gpid):
            names = []; t = go2tr.get(gpid); n = 0
            while t is not None and n < 64:
                g, lp, fp = tr[t]
                names.append(gon.get(g))
                if not fp or fp not in tr: break
                t = fp; n += 1
            return names

        scene = cab2scene.get(cab, "")
        for gpid, cs in by_go.items():
            hit = WANT & set(cs)
            if not hit: continue
            entry = {
                "name": gon.get(gpid), "active": goact.get(gpid),
                "scene": scene, "bundle": os.path.basename(f),
                "classes": sorted(cs), "chain": chain_names(gpid),
                "pos": world_pos(gpid),
            }
            tp = cs.get("OW_Teleporter")
            if tp:
                entry["targetPos"] = tp.get("_targetPos")
                entry["moveDir"] = tp.get("_moveDir")
                entry["targetMoveDir"] = tp.get("_targetMoveDir")
            hr = cs.get("HitReceiveBhvr_OW_Teleporter")
            if hr:
                entry["cooldown"] = hr.get("_teleportCooldown")
                entry["trigger"] = hr.get("_triggerModule")
                # _teleporter PPtr may point to another GO's component
                tpp = hr.get("_teleporter") or {}
                entry["hit_tp_ref"] = tpp.get("m_PathID")
            ib = cs.get("Interact_Bhvr_Teleport")
            if ib:
                entry["interact_mode"] = ib.get("_mode")
                entry["interact_tp_ref"] = (ib.get("_teleporter") or {}).get("m_PathID")
            # parent-chain sibling classes (conditions wrapping the gate)
            parent_cls = set()
            t = go2tr.get(gpid); n = 0
            while t is not None and n < 8:
                g, lp, fp = tr[t]
                parent_cls |= set(by_go.get(g, {}))
                if not fp or fp not in tr: break
                t = fp; n += 1
            entry["chain_classes"] = sorted(parent_cls - set(cs))
            results.append(entry)

print(f"DONE {time.time()-t0:.0f}s gates={len(results)}")
json.dump(results, open(OUT, "w"), indent=1)
print(OUT)
