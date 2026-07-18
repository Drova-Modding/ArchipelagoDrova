"""
Drova Interact_Condition_Locked extractor (doors, trapdoors, chests).

Recovers the lock dump referenced by the README (267 locks) that was never
committed. For EVERY object owning an Interact_Condition_Locked MonoBehaviour
it emits:

  guid            save guid (GuidComponent._guidString on the nearest ancestor
                  GameObject; this is the same component SaveRoot_Guid's
                  _guidComponent PPtr resolves to, cf. extract3.py) or null
  object_name     name of that ancestor GameObject (the container/door root)
  world_pos       {x, y} world position (transform-walk like extract3.world_pos)
  keys            readable item ids resolved from the _keyItems ItemStack
                  structs ({_item: PPtr, _amount, _isGarbage}; _readableId of
                  the referenced Item ScriptableObjects — e.g.
                  "key_chest_BanditCamp" for asset Misc_Key_BanditCamp —
                  resolved cross-bundle via script_index.pkl's cab->bundle map)
  can_lockpick    _canLockpick
  lockpick_talent m_Name of the _requiredLockpickingTalent asset (or null)
  remove_key      _removeKey
  is_door         true when the owner subtree has no Saveable_Inventory,
                  mirroring gen_locations.py's "Depot w/o inventory =
                  door/trapdoor" filter

Run from tools/extract_locations (needs script_index.pkl, rebuild with
build_script_index.py). Output: ../extracted/door_locks.json, deterministic
(sorted by guid/object_name/position).
"""
import UnityPy, glob, os, pickle, json, sys, time, collections, re

BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extracted", "door_locks.json")

idx = pickle.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "script_index.pkl"), "rb"))
S = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}
CAB2BUNDLE = {k.lower(): v for k, v in idx["cabs"].items()}
CABRE = re.compile(r"^cab-[0-9a-f]{32}$")

files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
locks = []           # records with unresolved PPtr refs
need = set()         # (cab_lower, path_id) of assets we must resolve (items, talents)
t0 = time.time()

def _bool(v):
    return bool(v)

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
        mb = {}                                   # path_id -> (cls, dict)
        by_go = collections.defaultdict(dict)     # go path_id -> {cls: dict}
        lock_pids = []
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
                    if cls == "Interact_Condition_Locked":
                        lock_pids.append(o.path_id)
            except Exception:
                continue
        if not lock_pids: continue

        # GameObjects whose GuidComponent is referenced by a SaveRoot_Guid
        # (= the authoritative save key, cf. extract3.py). Nested decorative
        # GuidComponents (e.g. Interact_Chest inside a sarcophagus) are NOT
        # referenced by any SaveRoot_Guid and must lose against the real root.
        saved_gc_gos = set()
        for _pid, (_cls, _d) in mb.items():
            if _cls != "SaveRoot_Guid": continue
            _ptr = _d.get("_guidComponent") or {}
            if _ptr.get("m_FileID") == 0 and _ptr.get("m_PathID"):
                _g = mb.get(_ptr["m_PathID"])
                if _g and _g[0] == "GuidComponent":
                    saved_gc_gos.add(_g[1].get("m_GameObject", {}).get("m_PathID"))

        # children map for subtree class scan
        children = collections.defaultdict(list)  # transform pid -> [transform pid]
        for tpid, (g, lp, fp) in tr.items():
            if fp: children[fp].append(tpid)

        def world_pos(gpid):
            x = y = 0.0; t = go2tr.get(gpid); n = 0
            while t is not None and n < 64:
                g, lp, fp = tr[t]
                x += lp.get("x", 0.0); y += lp.get("y", 0.0)
                if not fp or fp not in tr: break
                t = fp; n += 1
            return round(x, 2), round(y, 2)

        def ancestors(gpid):
            """GameObject path_ids from gpid up to the hierarchy root."""
            out, t, n = [], go2tr.get(gpid), 0
            while t is not None and n < 64:
                g, lp, fp = tr[t]
                out.append(g)
                if not fp or fp not in tr: break
                t = fp; n += 1
            return out

        def subtree_classes(root_gpid):
            cs, stack, n = set(), [go2tr.get(root_gpid)], 0
            while stack and n < 5000:
                t = stack.pop()
                if t is None: continue
                n += 1
                g = tr[t][0]
                cs |= set(by_go.get(g, {}))
                stack.extend(children.get(t, ()))
            return cs

        def ref(pptr):
            """PPtr -> (cab_lower, path_id) or None."""
            if not pptr or not pptr.get("m_PathID"):
                return None
            fid = pptr.get("m_FileID", 0)
            if fid == 0:
                tcab = sf.name
            else:
                try:
                    tcab = os.path.basename(sf.externals[fid-1].path.replace("\\", "/"))
                except Exception:
                    return None
            return (tcab.lower(), pptr["m_PathID"])

        scene = cab2scene.get(cab, "")
        for pid in lock_pids:
            cls, d = mb[pid]
            own_go = d.get("m_GameObject", {}).get("m_PathID")
            # save root = nearest ancestor whose GuidComponent is referenced by
            # a SaveRoot_Guid; fall back to nearest ancestor with any
            # GuidComponent (prefabs without a Saving child).
            guid, root = None, own_go
            fallback = None
            for g in ancestors(own_go):
                gc = by_go.get(g, {}).get("GuidComponent")
                if not gc: continue
                if g in saved_gc_gos:
                    guid, root = gc.get("_guidString") or None, g
                    break
                if fallback is None:
                    fallback = (gc.get("_guidString") or None, g)
            else:
                if fallback: guid, root = fallback
            wx, wy = world_pos(root)
            # _keyItems is a list of ItemStack structs: {_item: PPtr, _amount, _isGarbage}
            key_refs = [ref((p or {}).get("_item")) for p in (d.get("_keyItems") or [])]
            key_refs = [r for r in key_refs if r]
            tal_ref = ref(d.get("_requiredLockpickingTalent"))
            need.update(key_refs)
            if tal_ref: need.add(tal_ref)
            sub = subtree_classes(root)
            locks.append({
                "guid": guid,
                "object_name": gon.get(root),
                "world_pos": {"x": wx, "y": wy},
                "_key_refs": key_refs,
                "can_lockpick": _bool(d.get("_canLockpick")),
                "_tal_ref": tal_ref,
                "remove_key": _bool(d.get("_removeKey")),
                "is_door": "Saveable_Inventory" not in sub,
                "scene": scene,
                "bundle": os.path.basename(f),
            })
    if bi % 400 == 0:
        print(f"  pass1 {bi}/{len(files)} locks={len(locks)} {time.time()-t0:.0f}s"); sys.stdout.flush()

print(f"pass1 DONE {time.time()-t0:.0f}s locks={len(locks)} refs_to_resolve={len(need)}")

# ---- pass 2: resolve referenced assets (Items, Talents) to readable ids ----
by_bundle = collections.defaultdict(set)
unmapped = set()
for cab, pid2 in need:
    b = CAB2BUNDLE.get(cab)
    if b: by_bundle[b].add((cab, pid2))
    else: unmapped.add((cab, pid2))
if unmapped:
    print(f"WARNING: {len(unmapped)} refs in cabs not in script_index cab map")

resolved = {}     # (cab_lower, path_id) -> (class, m_Name)
for b, refs in sorted(by_bundle.items()):
    try:
        env = UnityPy.load(os.path.join(BD, b))
    except Exception as e:
        print("FAIL", b, e); continue
    want = {r[1]: r for r in refs}   # path_id -> ref  (cabs within one bundle don't share ids in practice; guard below)
    for cab, sf in env.cabs.items():
        cl = cab.lower()
        for pid2 in list(want):
            if (cl, pid2) not in refs: continue
            o = sf.objects.get(pid2)
            if o is None: continue
            try:
                d = o.read_typetree()
            except Exception:
                continue
            scr = d.get("m_Script") or {}
            fid, spid = scr.get("m_FileID"), scr.get("m_PathID")
            cls2 = None
            if fid is not None:
                try:
                    tcab = sf.name if fid == 0 else os.path.basename(sf.externals[fid-1].path.replace("\\", "/"))
                    cls2 = S.get((tcab.lower(), spid))
                except Exception:
                    pass
            # Item assets carry the runtime id in _readableId (matches AP items.json
            # and the old locks.json); fall back to the asset name (talents etc.).
            resolved[(cl, pid2)] = (cls2, d.get("_readableId") or d.get("m_Name"))
print(f"pass2 DONE {time.time()-t0:.0f}s resolved={len(resolved)}/{len(need)}")
print("resolved asset classes:", collections.Counter(c for c, n in resolved.values()))

def readable(r):
    if r is None: return None
    got = resolved.get(r)
    return got[1] if got else f"UNRESOLVED:{r[0]}:{r[1]}"

out = []
for L in locks:
    out.append({
        "guid": L["guid"],
        "object_name": L["object_name"],
        "world_pos": L["world_pos"],
        "keys": sorted(filter(None, (readable(r) for r in L["_key_refs"]))),
        "can_lockpick": L["can_lockpick"],
        "lockpick_talent": readable(L["_tal_ref"]),
        "remove_key": L["remove_key"],
        "is_door": L["is_door"],
        "scene": L["scene"],
        "bundle": L["bundle"],
    })
out.sort(key=lambda r: (r["guid"] is None, r["guid"] or "", r["object_name"] or "",
                        r["world_pos"]["x"], r["world_pos"]["y"]))
json.dump(out, open(OUT, "w"), indent=1)
print(f"wrote {os.path.normpath(OUT)}  entries={len(out)}")
print("is_door=True:", sum(1 for r in out if r["is_door"]),
      "| doors w/ can_lockpick=False:", sum(1 for r in out if r["is_door"] and not r["can_lockpick"]),
      "| keyed:", sum(1 for r in out if r["keys"]))
