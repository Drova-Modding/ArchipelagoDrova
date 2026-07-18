"""Generate Archipelago location_name_to_id from the static extraction."""
import json, collections, hashlib, re, math

O = json.load(open("saveobjects.json"))
A = json.load(open("areas3.json"))

# --- area key -> English display name (from AreaNames_en.loc) ---
LOC = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\Localization\en\AreaNames_en.loc"
disp = {}
for m in re.finditer(r"^(\S+)\s*\{\s*(.*?)\s*\}", open(LOC, encoding="utf-8", errors="replace").read(), re.M):
    disp[m.group(1)] = m.group(2)

AP = json.load(open("areas_poly.json"))
areas = [a for a in AP if a.get("key") and a.get("polys")]
# precompute bboxes
for a in areas:
    pts = [p for poly in a["polys"] for p in poly]
    a["bb"] = (min(p[0] for p in pts), min(p[1] for p in pts),
               max(p[0] for p in pts), max(p[1] for p in pts))

def _in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i+1) % n]
        if (y1 > y) != (y2 > y):
            xint = (x2-x1) * (y-y1) / ((y2-y1) or 1e-12) + x1
            if x < xint: inside = not inside
    return inside

def area_for(x, y):
    """Point-in-polygon against AreaName volumes; ties broken by _priority (higher wins)."""
    hits = []
    for a in areas:
        bx0, by0, bx1, by1 = a["bb"]
        if not (bx0 <= x <= bx1 and by0 <= y <= by1): continue
        if any(_in_poly(x, y, poly) for poly in a["polys"]):
            hits.append(a)
    if not hits: return None
    best = max(hits, key=lambda a: (a.get("priority") or 0))
    return disp.get(best["key"], best["key"])

def category(r):
    """Depot == lock/cover state, and DOORS have one too. A Depot is only a real chest
    when it also carries an actual inventory (Saveable_Inventory)."""
    s = set(r["saveables"])
    if "Saveable_Depot" in s:
        return "Chest" if "Saveable_Inventory" in s else None      # Depot w/o inventory = door/trapdoor
    if "Saveable_LootInventory" in s or "Saveable_Inventory" in s: return "Container"
    if "Saveable_ResourceSpot" in s: return "Resource"
    if "Saveable_LootTablePickups" in s: return "Cache"
    if "Saveable_PickUp_Once" in s: return "Pickup"
    return None

G = [r for r in O if r["kind"] == "GUID" and r["is_loot"] and r["key"] and category(r)]
print("loot entries after door/no-inventory filter:", len(G))
# dedupe by save key
seen, rows = set(), []
for r in sorted(G, key=lambda r: (r["key"] or "")):
    if r["key"] in seen: continue
    seen.add(r["key"]); rows.append(r)
print("distinct loot save keys:", len(rows))

# group -> stable numbered names
CHUNKRE = re.compile(r"_(-?\d+)_(-?\d+)\.unity$")
def fallback_region(r):
    """No AreaName volume covers this point -> name by overworld chunk coords (still stable+meaningful)."""
    m = CHUNKRE.search(r["scene"] or "")
    if m: return f"Wilds {m.group(1)}_{m.group(2)}"
    return "Unknown"

groups = collections.defaultdict(list)
n_area = n_fb = 0
for r in rows:
    a = area_for(r["x"], r["y"])
    if a: n_area += 1
    else: a = fallback_region(r); n_fb += 1
    groups[(a, category(r))].append(r)
print(f"region: inside an AreaName volume = {n_area} | fallback to chunk = {n_fb}")

BASE = 8_400_000_000        # AP id namespace for Drova (int64-safe)
SPACE = 1 << 32             # 4.29e9 slots for ~5k locations => collisions vanishingly rare
name_to_id, table = {}, {}
used = {}
for (area, cat), items in sorted(groups.items()):
    # deterministic order: by world position then guid  => stable across runs
    items.sort(key=lambda r: (round(r["y"], 1), round(r["x"], 1), r["key"]))
    for i, r in enumerate(items, 1):
        nm = f"{area} - {cat} {i}"
        # id is derived from the GUID only => stable even if names/areas are re-derived later
        h = int(hashlib.sha256(r["key"].encode()).hexdigest(), 16) % SPACE
        while h in used and used[h] != r["key"]:   # deterministic linear probe on collision
            h = (h + 1) % SPACE
        used[h] = r["key"]
        name_to_id[nm] = BASE + h
        table[nm] = {"guid": r["key"], "category": cat, "area": area,
                     "object": r["name"], "scene": r["scene"], "x": r["x"], "y": r["y"]}

# collision check
ids = list(name_to_id.values())
print("names:", len(name_to_id), "| unique ids:", len(set(ids)), "| collisions:", len(ids)-len(set(ids)))
print("\n=== per-area counts ===")
for k, v in collections.Counter(v["area"] for v in table.values()).most_common():
    print(f"  {v:5d}  {k}")
print("\n=== per-category ===")
for k, v in collections.Counter(v["category"] for v in table.values()).most_common():
    print(f"  {v:5d}  {k}")
print("\n=== sample location names ===")
for nm in list(table)[:15]:
    print(f"  {name_to_id[nm]:>9d}  {nm:42s} <- {table[nm]['guid']} ({table[nm]['object']})")

json.dump(table, open("ap_locations.json", "w"), indent=1)
json.dump(name_to_id, open("ap_location_name_to_id.json", "w"), indent=1)
print("\nwrote ap_locations.json / ap_location_name_to_id.json")
