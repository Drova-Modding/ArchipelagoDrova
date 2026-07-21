"""Freeze the teleporter shuffle pool from the raw gate extraction.

Reads teleporters.json (extract_teleporters.py) and emits:
  - apworld/drova/data/teleporters.json      the shuffleable pairs (mouth/interior gate names)
  - ArchipelagoDrova/Data/TeleporterTable.g.cs  vanilla link data the client needs to remap

Pool rule: walk-in cave gates ("Teleporter_*") whose overworld mouth is start-walkable and
carries no key/faction/story gating. Everything else stays vanilla. The full reasoning and the
per-gate verdicts live in tools/investigations/teleporter_randomization.md.
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RAW = json.load(open(os.path.join(HERE, "teleporters.json")))
OUT_JSON = os.path.join(REPO, "apworld", "drova", "data", "teleporters.json")
OUT_CS = os.path.join(REPO, "ArchipelagoDrova", "Data", "TeleporterTable.g.cs")

# Gates excluded from the shuffle pool. Pairs, both directions listed for auditability.
EXCLUDE_PREFIXES = (
    "Teleporter_RedTower",    # goal tower: entrance is story-enabled, floors chain to the finale
    "Teleporter_Bib_",        # library: sole access, Etage1 pair is quest-gated (spawns inactive)
)
EXCLUDE_NAMES = {
    # Nemeton faction interiors - a Ruinenlager player must never be ported inside.
    "Teleporter_Druid_Cave_Enter", "Teleporter_Druid_Cave_Exit",
    "Teleporter_Druid_Leader_Enter", "Teleporter_Druid_Leader_Exit",
    "Teleporter_Nemeton_Storeroom_Enter", "Teleporter_Nemeton_Storeroom_Exit",
    "Teleporter_Market_Storage_Enter", "Teleporter_Market_Storage_Exit",
    # Ruinenlager faction interiors - mirror of the above for Nemeton players.
    "Teleporter_Ruinenlager_Hallway_Low", "Teleporter_Hallway_Low_Back",
    "Teleporter_ShadyDistrict_Enter", "Teleporter_ShadyDistrict_Exit",
    "Teleporter_UnderTheAcademy_Enter", "Teleporter_UnderTheAcademy_Exit",
    "Teleporter_Auwald_Kaserne_Enter", "Teleporter_Auwald_Kaserne_Exit",
    # Quest-critical interiors and hubs.
    "Teleporter_BanditMine_Enter", "Teleporter_BanditMine_Exit",
    "Teleporter_OwainCave_Entrance", "Teleporter_OwainCave_Exit",
    "Teleporter_SmugglersCave", "Teleporter_SmugglersCave_Exit",
    "Teleporter_Atlanterdungeon_Enter", "Teleporter_Atlanterdungeon_Exit",
    "Teleporter_Mine_Back", "Teleporter_Mine_Back_01",
    "Teleporter_Tavern_ToDownStairs", "Teleporter_Tavern_ToUpstairs",
    # Mouth sits inside the Ruinenlager city polygon; opposite-faction access is unverified.
    "Teleporter_BrutusEnter", "Teleporter_Brutus_Exit",
    "Teleporter_MushroomCave", "Teleporter_MushroomCave_Back",
    # Mouth sits inside the Riverbed, which DOOR_KEY_RULES gates behind Key Harald as the sole
    # entrance. A shuffled interior behind it would silently inherit that gate.
    "Teleporter_River_Enter", "Teleporter_River_Exit",
    "Teleporter_HiddenCave01", "Teleporter_HiddenCave01_Back",
}

def excluded(name):
    return name in EXCLUDE_NAMES or any(name.startswith(p) for p in EXCLUDE_PREFIXES)

def is_interior(x, y):
    # Interiors live in far map bands the overworld never reaches; the overworld proper spans
    # roughly x in [-20k, 36k], y in [-12k, 12k]. Verified against every extracted gate.
    return y > 12000 or y < -12000 or x > 36000 or x < -20000

# All walk-in gates (GO owns OW_Teleporter), deduped across bundle copies.
gates = {}
for e in RAW:
    if "OW_Teleporter" not in e["classes"] or not (e["name"] or "").startswith("Teleporter_"):
        continue
    key = (e["name"], tuple(e["pos"]))
    if key not in gates:
        t = e.get("targetPos") or {}
        d = e.get("targetMoveDir") or {}
        gates[key] = {
            "name": e["name"], "x": e["pos"][0], "y": e["pos"][1],
            "tx": t.get("x", 0.0), "ty": t.get("y", 0.0),
            "dx": d.get("x", 0.0), "dy": d.get("y", 0.0),
            "active": e["active"],
        }
gates = list(gates.values())
by_name = {}
for g in gates:
    assert g["name"] not in by_name, f"duplicate gate name {g['name']}"
    by_name[g["name"]] = g

def nearest(x, y, exclude):
    best, bd = None, math.inf
    for o in gates:
        if o is exclude:
            continue
        d = math.hypot(o["x"] - x, o["y"] - y)
        if d < bd:
            bd, best = d, o
    return best, bd

# Pair every non-excluded gate by matching its arrival anchor to the nearest gate.
partner = {}
for g in gates:
    if excluded(g["name"]):
        continue
    p, dist = nearest(g["tx"], g["ty"], g)
    assert p is not None and dist < 120, f"{g['name']}: no partner within 120 units ({dist:.0f})"
    assert not excluded(p["name"]), f"{g['name']} pairs with excluded {p['name']}"
    partner[g["name"]] = p["name"]

pairs = []
for name, pname in sorted(partner.items()):
    assert partner.get(pname) == name, f"{name} <-> {pname} is not mutual"
    if name > pname:
        continue  # emit each pair once
    a, b = by_name[name], by_name[pname]
    a_int, b_int = is_interior(a["x"], a["y"]), is_interior(b["x"], b["y"])
    assert a_int != b_int, f"{name} <-> {pname}: not one mouth + one interior ({a_int}, {b_int})"
    assert a["active"] and b["active"], f"{name} <-> {pname}: inactive gate in pool"
    mouth, interior = (b, a) if a_int else (a, b)
    pairs.append({"mouth": mouth["name"], "interior": interior["name"]})

pairs.sort(key=lambda p: p["mouth"])
json.dump({"pairs": pairs}, open(OUT_JSON, "w"), indent=1)
print(f"pool: {len(pairs)} pairs -> {OUT_JSON}")

def f(v):
    return repr(round(v, 2)).rstrip("0").rstrip(".") + "f" if v == v else "0f"

lines = [
    "// Generated by tools/extract_locations/gen_teleporter_pairs.py. Do not edit by hand.",
    "using System.Collections.Generic;",
    "",
    "namespace ArchipelagoDrova.Data",
    "{",
    "    public static partial class TeleporterTable",
    "    {",
    "        /// <summary>Vanilla link data per pool gate: its partner and where it sends the player.</summary>",
    "        public static readonly Dictionary<string, TeleporterGate> Generated = new Dictionary<string, TeleporterGate>",
    "        {",
]
for p in pairs:
    for name in (p["mouth"], p["interior"]):
        g = by_name[name]
        other = partner[name]
        lines.append(
            f'            {{ "{name}", new TeleporterGate("{other}", {f(g["tx"])}, {f(g["ty"])}, {f(g["dx"])}, {f(g["dy"])}) }},'
        )
lines += [
    "        };",
    "    }",
    "}",
    "",
]
open(OUT_CS, "w", encoding="utf-8").write("\n".join(lines))
print(f"table: {2 * len(pairs)} gates -> {OUT_CS}")
