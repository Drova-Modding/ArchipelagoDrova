"""
Drova world-loot distribution extractor  ->  tools/extracted/loot_distribution.json

Answers "how often does the vanilla game actually hand the player item X?" so the apworld can
weight its filler/bonus pool the way Drova weights its own loot, instead of drawing uniformly
from the item database (which made a 5x stack of high-tier healing potions exactly as likely as
a handful of berries).

Four authored loot sources are counted, all of them static scene/asset data:

  1. world pickups  -  Saveable_PickUp_Once (~4.4k placements). The item is reached through
     _lootAll -> Interact_Bhvr_LootAll._loot -> Inventory._inventoryItems[]. These are the logs,
     berries, herbs and feathers lying around the map: by far the biggest source.
  2. loot-table nodes  -  SpawnFromLootTable._lootTable -> LootTable_Pickups (destroyable vases
     and boxes). Table entries are {Pickup, Range{min,max}, Chance, Chapter}; Pickup is a PPtr to
     a PickupInteraction on the pickup prefab, resolved to an item the same way as (1).
     _maxAmount caps how many entries a single roll may yield.
  3. resource spots  -  Interact_Bhvr_ResourceSpot._rewards -> ResourceSpotReward (mining, herb
     and fishing spots). Rewards[] is one entry per talent tier; tier 0 (no talent) is the
     baseline counted here, since that is what a run without the hobby talents sees.
  4. container fix loot  -  read straight from tools/extracted/chest_slots.json, which
     extract_chest_slots.py produces and which is the authority on authored container contents
     (it resolves containers through SaveRoot_Guid, so it also catches the critter corpses this
     sweep would miss - a local Inventory_LootBhvr pass found 290 of its 409 containers).
     RUN extract_chest_slots.py FIRST; without the file this source is simply absent.

Two identity rules matter and both cost a wrong first run:

  * Unity duplicates a shared asset into every bundle that references it, so the 159
    LootTable_Pickups objects in the bundles are really 2 tables and the ResourceSpotReward
    objects are a handful of presets. Aggregate assets by their authored id - `_guid` for loot
    tables / pickups / actor presets, `m_Name` for the reward presets - never by (cab, path_id).
  * The same prefab appears both as its source asset and as every scene placement of it.
    Placements are therefore deduped on the GuidComponent guid found by walking up the transform
    chain (the same guid the savegame uses as an object key); the prefab-source copies collapse
    into one, and every real placement keeps its own entry.

Enemy drops (ActorLootPreset) are extracted for reference only: their real weight depends on how
many actors of each kind the world spawns, which lives behind LazyActor spawners, so they are
reported separately and NOT folded into the world distribution.

Output shape:
  {
    "sources": {<source>: {<readable_id>: {"count": n, "amount": total_units}}},
    "tables":  {<table name>: {"placements": n, "max_amount": n, "items": {id: p_per_roll}}},
    "resource_spots": {<preset name>: {"placements": n, "items": {id: amount}}},
    "actor_presets": {<preset name>: [{"readable_id":..., "amount":...}]},   # reference only
    "totals":  {<readable_id>: {"count": .., "amount": ..}}
  }

`count` is "expected number of times the player finds this item across a full vanilla map sweep"
and `amount` the expected number of units, fractional where a loot-table chance is involved.

Run from tools/extract_locations (needs script_index.pkl), same conventions as the other
extractors here.
"""
import UnityPy, glob, os, pickle, json, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
OUT = os.path.join(HERE, "..", "extracted", "loot_distribution.json")

idx = pickle.load(open(os.path.join(HERE, "script_index.pkl"), "rb"))
S = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}
CAB2BUNDLE = {k.lower(): v for k, v in idx["cabs"].items()}

# Behaviours that carry a loot inventory for a pickup. Interact_Bhvr_LootAll is what every probed
# world pickup uses; the inventory variant is covered so a differently authored pickup cannot
# silently vanish from the counts.
LOOT_ALL_CLASSES = ("Interact_Bhvr_LootAll", "Interact_Bhvr_LootInventory")


def bn(p):
    return os.path.basename(p.replace("\\", "/"))


def sweep():
    files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
    print("bundles:", len(files)); sys.stdout.flush()

    item_need = set()                       # (cab, path_id) -> resolved to readable ids in pass 2
    ref_pickup_guid = {}                    # PickupInteraction ref -> its authored _guid
    pickup_items = {}                       # PickupInteraction _guid -> [(item_ref, amount)]
    ref_table_guid = {}                     # LootTable_Pickups ref -> its authored _guid
    tables = {}                             # table _guid -> record
    ref_spot_name = {}                      # ResourceSpotReward ref -> preset name
    spot_rewards = {}                       # preset name -> [(item_ref, amount)] at talent tier 0
    # placements, deduped on the save guid of the placed object
    world_pickups = {}                      # save guid -> [(item_ref, amount)]
    table_hits = {}                         # save guid -> table ref
    spot_hits = {}                          # save guid -> reward ref
    actor_presets = {}                      # preset _guid -> (name, stacks)
    anon = collections.Counter()            # placements with no guid, kept under synthetic keys
    t0 = time.time()

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
            cabl = sf.name.lower()

            mb = {}                                  # path_id -> (cls, dict)
            by_go = collections.defaultdict(dict)    # go path_id -> {cls: dict}
            tr_of_go, parent_of_tr, go_of_tr = {}, {}, {}
            for o in objlist:
                try:
                    tn = o.type.name
                    if tn in ("Transform", "RectTransform"):
                        d = o.read_typetree()
                        g = (d.get("m_GameObject") or {}).get("m_PathID")
                        go_of_tr[o.path_id] = g
                        tr_of_go[g] = o.path_id
                        parent_of_tr[o.path_id] = (d.get("m_Father") or {}).get("m_PathID")
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
                        by_go[(d.get("m_GameObject") or {}).get("m_PathID")][cls] = d
                except Exception:
                    continue
            if not mb:
                continue

            def ext_ref(pptr):
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

            def local(pptr):
                if not pptr or pptr.get("m_FileID", 0) != 0:
                    return None
                return mb.get(pptr.get("m_PathID"))

            def go_chain(go):
                """The GameObject and each of its transform ancestors, root last."""
                seen, tr = set(), tr_of_go.get(go)
                while tr is not None and tr not in seen:
                    seen.add(tr)
                    g = go_of_tr.get(tr)
                    if g is None:
                        return
                    yield g
                    tr = parent_of_tr.get(tr)

            def save_guid(d, kind):
                """The GuidComponent guid identifying this placement, or None.

                Walk the transform chain for a GuidComponent; a SaveRoot_Guid on the way up points
                at one directly (pickups keep theirs on a sibling branch, not on the save node).
                A *prefab source* carries the component with an EMPTY _guidString - the guid is
                stamped per scene placement - and Unity copies those prefabs into every bundle that
                references them (~16 pickup prefabs x 326 bundles). Returning None for them is what
                keeps 1.3k phantom pickups out of the distribution."""
                for g in go_chain((d.get("m_GameObject") or {}).get("m_PathID")):
                    sibs = by_go.get(g, {})
                    gc = sibs.get("GuidComponent")
                    if gc and gc.get("_guidString"):
                        return gc["_guidString"].lower()
                    sr = sibs.get("SaveRoot_Guid")
                    if sr:
                        got = local(sr.get("_guidComponent"))
                        if got and got[0] == "GuidComponent" and got[1].get("_guidString"):
                            return got[1]["_guidString"].lower()
                anon[kind] += 1
                return None

            def inventory_items(inv_d):
                out = []
                for slot in (inv_d.get("_inventoryItems") or []):
                    if not isinstance(slot, dict):
                        continue
                    ref = ext_ref(slot.get("_item"))
                    if ref is None:
                        continue
                    item_need.add(ref)
                    out.append((ref, slot.get("_amount") or 1))
                return out

            def items_of_loot_all(la_d):
                inv = local(la_d.get("_loot") or la_d.get("_inventory"))
                if not inv or inv[0] != "Inventory":
                    return []
                return inventory_items(inv[1])

            # Pickup prefabs: PickupInteraction identifies the pickup, a LootAll behaviour under
            # the same root holds the Inventory that names the item.
            for pid, (cls, d) in mb.items():
                if cls == "PickupInteraction" and d.get("_guid"):
                    ref_pickup_guid[(cabl, pid)] = d["_guid"]
            for pid, (cls, d) in mb.items():
                if cls not in LOOT_ALL_CLASSES:
                    continue
                items = items_of_loot_all(d)
                if not items:
                    continue
                for g in go_chain((d.get("m_GameObject") or {}).get("m_PathID")):
                    pi = by_go.get(g, {}).get("PickupInteraction")
                    if pi is None:
                        continue
                    if pi.get("_guid"):
                        pickup_items.setdefault(pi["_guid"], items)
                    break

            for pid, (cls, d) in mb.items():
                # --- 1. world pickups
                if cls == "Saveable_PickUp_Once":
                    la = local(d.get("_lootAll"))
                    if la and la[0] in LOOT_ALL_CLASSES:
                        got = items_of_loot_all(la[1])
                        g = got and save_guid(d, "pickup")
                        if g:
                            world_pickups.setdefault(g, got)
                    continue

                # --- 2. loot tables and their placements
                if cls == "LootTable_Pickups":
                    guid = d.get("_guid") or ("noguid:%s:%s" % (cabl, pid))
                    ref_table_guid[(cabl, pid)] = guid
                    if guid not in tables:
                        entries = []
                        for e in (d.get("_items") or []):
                            rng = e.get("Range") or {}
                            entries.append({
                                "pickup": ext_ref(e.get("Pickup")),
                                "chance": e.get("Chance") or 0.0,
                                "min": rng.get("_min", 1),
                                "max": rng.get("_max", 1),
                                "chapter": e.get("Chapter", 0),
                            })
                        tables[guid] = {"name": d.get("m_Name"), "max_amount": d.get("_maxAmount", 0),
                                        "entries": entries}
                    continue
                if cls == "SpawnFromLootTable":
                    ref = ext_ref(d.get("_lootTable"))
                    g = ref and save_guid(d, "table")
                    if g:
                        table_hits.setdefault(g, ref)
                    continue

                # --- 3. resource spots
                if cls == "ResourceSpotReward":
                    name = d.get("m_Name") or ("noname:%s:%s" % (cabl, pid))
                    ref_spot_name[(cabl, pid)] = name
                    if name not in spot_rewards:
                        # Rewards[] is one entry per talent tier: [0] is the no-talent baseline and
                        # the rest are what the hobby talents upgrade it to. Every item carries a
                        # Bonus {chance, extra amount} on top of its flat _amount, so a spot's real
                        # yield is a range, not a number.
                        tiers = []
                        for tier_index, tier in enumerate(d.get("Rewards") or []):
                            entries = []
                            for it in (tier.get("_items") or []):
                                st = it.get("_itemStack") or {}
                                ref = ext_ref(st.get("_item"))
                                if ref is None:
                                    continue
                                item_need.add(ref)
                                bonus = it.get("Bonus") or {}
                                entries.append({
                                    "item": ref,
                                    "amount": st.get("_amount") or 0,
                                    "bonus_chance": bonus.get("_chanceInpercent") or 0.0,
                                    "bonus_amount": bonus.get("_bonusAmount") or 0,
                                    "needs_talent": bool((tier.get("_availableTalent") or {}).get("m_PathID")),
                                })
                            tiers.append({"tier": tier_index, "entries": entries})
                        spot_rewards[name] = tiers
                    continue
                if cls == "Interact_Bhvr_ResourceSpot":
                    ref = ext_ref(d.get("_rewards"))
                    g = ref and save_guid(d, "spot")
                    if g:
                        spot_hits.setdefault(g, ref)
                    continue

                # --- reference only: enemy loot presets
                if cls == "ActorLootPreset":
                    guid = d.get("_guid") or ("noguid:%s:%s" % (cabl, pid))
                    if guid in actor_presets:
                        continue
                    stacks = []
                    for st in (d.get("_lootableItemStacks") or []):
                        ref = ext_ref(st.get("_item"))
                        if ref is not None:
                            item_need.add(ref)
                        stacks.append({"item": ref, "amount": st.get("_amount") or 1})
                    actor_presets[guid] = (d.get("m_Name") or guid, stacks)
        del env
        if bi % 200 == 0:
            print("  sweep %d/%d pickups=%d tables=%d/%d spots=%d %.0fs"
                  % (bi, len(files), len(world_pickups), len(tables), len(table_hits),
                     len(spot_hits), time.time() - t0))
            sys.stdout.flush()

    print("sweep DONE %.0fs  pickups=%d  tables=%d (%d placements)  spot presets=%d (%d placements)"
          "  item_refs=%d  prefab-source copies skipped=%s"
          % (time.time() - t0, len(world_pickups), len(tables), len(table_hits),
             len(spot_rewards), len(spot_hits), len(item_need), dict(anon)))
    return locals()


def resolve_items(item_need):
    """Item PPtr -> readable id. Same two-pass shape as extract_chest_slots.resolve_items."""
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

    resolved, t0 = {}, time.time()
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
                try:
                    o = sf.objects.get(pid)
                except Exception:
                    continue
                if o is None:
                    continue
                try:
                    d = o.read_typetree()
                except Exception:
                    continue
                rid = d.get("_readableId")
                if rid:
                    resolved[(c, pid)] = rid
        del env
        if bi % 200 == 0:
            print("  resolve %d/%d %.0fs" % (bi, len(by_bundle), time.time() - t0)); sys.stdout.flush()
    print("resolve DONE %.0fs resolved=%d/%d" % (time.time() - t0, len(resolved), len(item_need)))
    return resolved


def main():
    d = sweep()
    resolved = resolve_items(d["item_need"])

    def rid(ref):
        return resolved.get(ref)

    sources = {k: collections.defaultdict(lambda: {"count": 0.0, "amount": 0.0})
               for k in ("world_pickup", "loot_table", "resource_spot", "container_fixloot")}
    dropped = collections.Counter()

    def add(src, ref, count, amount):
        r = rid(ref)
        if not r:
            dropped[src] += 1
            return
        e = sources[src][r]
        e["count"] += count
        e["amount"] += amount

    # 1. world pickups: one placement, authored amount.
    amounts = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for items in d["world_pickups"].values():
        for ref, amount in items:
            add("world_pickup", ref, 1, amount)
            r = rid(ref)
            if r:
                amounts["world_pickup"][r][amount] += 1

    # 2. loot tables: expected yield per placement. Each entry rolls independently at Chance for a
    #    uniform amount in [min,max]; _maxAmount caps how many entries one roll may yield, so the
    #    per-entry expectations are scaled down when they sum above the cap.
    placements = collections.Counter()
    for ref in d["table_hits"].values():
        guid = d["ref_table_guid"].get(ref)
        if guid:
            placements[guid] += 1
        else:
            dropped["table_ref"] += 1
    table_out = {}
    for guid, tab in d["tables"].items():
        hits = placements.get(guid, 0)
        exp = []
        for e in tab["entries"]:
            pguid = d["ref_pickup_guid"].get(e["pickup"])
            items = d["pickup_items"].get(pguid) or []
            if not items:
                dropped["table_pickup"] += 1
                continue
            avg = (e["min"] + e["max"]) / 2.0
            for ref, per in items:
                exp.append((ref, e["chance"], e["chance"] * avg * per))
        total_chance = sum(c for _, c, _ in exp)
        cap = tab["max_amount"] or 0
        scale = (cap / total_chance) if (cap and total_chance > cap) else 1.0
        rec = {"placements": hits, "max_amount": cap, "cap_scale": round(scale, 4),
               "items": {}, "entries": []}
        for e in tab["entries"]:
            pguid = d["ref_pickup_guid"].get(e["pickup"])
            for ref2, per in (d["pickup_items"].get(pguid) or []):
                r2 = rid(ref2)
                if not r2:
                    continue
                rec["entries"].append({
                    "readable_id": r2,
                    "chance": round(e["chance"], 6),
                    "effective_chance": round(e["chance"] * scale, 6),
                    "min": e["min"] * per,
                    "max": e["max"] * per,
                    "chapter": e["chapter"],
                })
        for ref, chance, units in exp:
            r = rid(ref)
            if not r:
                dropped["loot_table"] += 1
                continue
            rec["items"][r] = round(rec["items"].get(r, 0.0) + chance * scale, 4)
            if hits:
                add("loot_table", ref, hits * chance * scale, hits * units * scale)
        table_out[tab["name"] or guid] = rec

    # 3. resource spots: baseline (no-talent) tier, once per placement.
    spot_placements = collections.Counter()
    for ref in d["spot_hits"].values():
        name = d["ref_spot_name"].get(ref)
        if name:
            spot_placements[name] += 1
        else:
            dropped["spot_ref"] += 1
    spot_out = {}
    for name, tiers in d["spot_rewards"].items():
        hits = spot_placements.get(name, 0)
        rec = {"placements": hits, "items": {}, "tiers": []}
        for tier in tiers:
            out_entries = []
            for e in tier["entries"]:
                r = rid(e["item"])
                if not r:
                    continue
                out_entries.append({
                    "readable_id": r,
                    "amount": e["amount"],
                    "bonus_chance": round(e["bonus_chance"], 4),
                    "bonus_amount": e["bonus_amount"],
                    "min": e["amount"],
                    "max": e["amount"] + e["bonus_amount"],
                    "needs_talent": e["needs_talent"],
                })
            rec["tiers"].append({"tier": tier["tier"], "entries": out_entries})
        # The no-talent tier is what an average run sees, so it is what feeds the distribution.
        for e in (tiers[0]["entries"] if tiers else []):
            r = rid(e["item"])
            if r:
                rec["items"][r] = e["amount"]
            if hits:
                add("resource_spot", e["item"], hits, hits * e["amount"])
                if r:
                    amounts["resource_spot"][r][e["amount"]] += hits
        spot_out[name] = rec

    # 4. container fix loot, from the frozen chest-slot extraction (already keyed by save guid).
    chest_src = os.path.join(HERE, "..", "extracted", "chest_slots.json")
    if os.path.exists(chest_src):
        with open(chest_src, encoding="utf-8") as fh:
            chests = json.load(fh)
        cslots = 0
        for rec in chests.values():
            for slot in rec.get("slots", []):
                if slot.get("quest"):
                    continue          # quest property is never grantable loot
                e = sources["container_fixloot"][slot["readable_id"]]
                e["count"] += 1
                e["amount"] += slot.get("amount") or 1
                amounts["container_fixloot"][slot["readable_id"]][slot.get("amount") or 1] += 1
                cslots += 1
        print("container fix loot: %d containers, %d slots from %s"
              % (len(chests), cslots, os.path.normpath(chest_src)))
    else:
        print("WARNING: %s missing - container loot is absent from the distribution" % chest_src)

    totals = collections.defaultdict(lambda: {"count": 0.0, "amount": 0.0})
    for src in sources.values():
        for r, e in src.items():
            totals[r]["count"] += e["count"]
            totals[r]["amount"] += e["amount"]

    def clean(dd):
        return {r: {"count": round(e["count"], 3), "amount": round(e["amount"], 3)}
                for r, e in sorted(dd.items())}

    presets = {name: [{"readable_id": rid(s["item"]), "amount": s["amount"]} for s in stacks]
               for name, stacks in d["actor_presets"].values()}

    # Per-placement guid -> what that object holds. gen_data.py needs this to keep a location that
    # holds a quest-critical item from being randomized at all: chest slots carry their item in
    # chest_slots.json, but pickups, destroyable caches and resource spots do not, and their guid is
    # the only thing tying an AP location back to an item.
    placements = {}
    for guid, its in d["world_pickups"].items():
        rids = sorted({r for r in (rid(ref) for ref, _ in its) if r})
        if rids:
            placements[guid] = {"source": "world_pickup", "items": rids}
    for guid, ref in d["table_hits"].items():
        tab = d["tables"].get(d["ref_table_guid"].get(ref))
        if not tab:
            continue
        rids = sorted({r for e in tab["entries"]
                       for ref2, _ in (d["pickup_items"].get(d["ref_pickup_guid"].get(e["pickup"])) or [])
                       for r in [rid(ref2)] if r})
        if rids:
            placements[guid] = {"source": "loot_table", "items": rids}
    for guid, ref in d["spot_hits"].items():
        tiers = d["spot_rewards"].get(d["ref_spot_name"].get(ref)) or []
        base = tiers[0]["entries"] if tiers else []
        rids = sorted({r for r in (rid(e["item"]) for e in base) if r})
        if rids:
            placements[guid] = {"source": "resource_spot", "items": rids}
    print("placements with a known item: %d" % len(placements))

    out = {
        "placements": placements,
        "sources": {k: clean(v) for k, v in sources.items()},
        "tables": table_out,
        "resource_spots": spot_out,
        # source -> readable id -> {stack size: how many placements hand over that many}. Min/max
        # per item fall straight out of this; loot tables carry their ranges on the entries instead.
        "amounts": {src: {r: {str(k): v for k, v in sorted(h.items())} for r, h in per.items()}
                    for src, per in amounts.items()},
        "actor_presets": presets,
        "totals": clean(totals),
    }
    if dropped:
        print("WARNING: unresolved refs: %s" % dict(dropped))
    for k, v in out["sources"].items():
        print("source %-18s distinct=%-4d count=%.1f" % (k, len(v), sum(x["count"] for x in v.values())))
    print("distinct items in world distribution: %d" % len(totals))
    for r, e in sorted(totals.items(), key=lambda kv: -kv[1]["count"])[:25]:
        print("  %8.1f %10.1f  %s" % (e["count"], e["amount"], r))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, ensure_ascii=True)
        fh.write("\n")
    print("wrote", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
