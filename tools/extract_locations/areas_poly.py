"""Extract AreaName trigger volumes WITH their collider polygons for point-in-polygon region assignment."""
import UnityPy, pickle, os, json, glob, collections

BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
idx = pickle.load(open("script_index.pkl", "rb"))
S = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}

out = []
for f in glob.glob(os.path.join(BD, "*.bundle")):
    try: env = UnityPy.load(f)
    except Exception: continue
    # only bundles that contain an AreaName MonoBehaviour
    for cab, sf in env.cabs.items():
        try: objlist = list(sf.objects.values())
        except Exception: continue
        gon, tr, go2tr = {}, {}, {}
        area_gos, colliders = {}, collections.defaultdict(list)
        found = False
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
                elif tn in ("PolygonCollider2D", "BoxCollider2D", "CircleCollider2D", "CompositeCollider2D"):
                    d = o.read_typetree()
                    colliders[d.get("m_GameObject", {}).get("m_PathID")].append((tn, d))
                elif tn == "MonoBehaviour":
                    d = o.read_typetree(); scr = d.get("m_Script") or {}
                    fid, pid = scr.get("m_FileID"), scr.get("m_PathID")
                    if fid is None: continue
                    tcab = sf.name if fid == 0 else os.path.basename(sf.externals[fid-1].path.replace("\\", "/"))
                    if S.get((tcab.lower(), pid)) == "AreaName":
                        area_gos[d.get("m_GameObject", {}).get("m_PathID")] = d
                        found = True
            except Exception: continue
        if not found: continue

        def wpos(g):
            x = y = 0.0; t = go2tr.get(g); n = 0
            while t is not None and n < 64:
                _, lp, fp = tr[t]; x += lp.get("x", 0.0); y += lp.get("y", 0.0)
                if not fp or fp not in tr: break
                t = fp; n += 1
            return x, y

        for g, d in area_gos.items():
            ox, oy = wpos(g)
            polys = []
            for tn, cd in colliders.get(g, []):
                off = cd.get("m_Offset") or {}
                if tn == "PolygonCollider2D":
                    pts = (cd.get("m_Points") or {}).get("m_Paths") or []
                    for path in pts:
                        polys.append([[ox + off.get("x",0) + p["x"], oy + off.get("y",0) + p["y"]] for p in path])
                elif tn == "BoxCollider2D":
                    sz = cd.get("m_Size") or {}
                    hw, hh = sz.get("x",0)/2, sz.get("y",0)/2
                    cx, cy = ox+off.get("x",0), oy+off.get("y",0)
                    polys.append([[cx-hw,cy-hh],[cx+hw,cy-hh],[cx+hw,cy+hh],[cx-hw,cy+hh]])
            out.append({"key": d.get("_areaKey"), "priority": d.get("_priority"),
                        "name": gon.get(g), "x": ox, "y": oy,
                        "colliders": [t for t,_ in colliders.get(g, [])], "polys": polys})
print("AreaName volumes:", len(out))
print("with polygons:", sum(1 for a in out if a["polys"]))
ch = collections.Counter(t for a in out for t in a["colliders"])
print("collider types:", dict(ch))
for a in out[:8]:
    print(f"  {a['key']:18s} prio={a['priority']} colliders={a['colliders']} polys={len(a['polys'])} pts={[len(p) for p in a['polys']][:4]}")
json.dump(out, open("areas_poly.json","w"))
