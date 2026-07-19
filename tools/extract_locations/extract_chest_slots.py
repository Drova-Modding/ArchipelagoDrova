"""
Drova per-container fixed-loot extractor  ->  tools/extracted/chest_slots.json

Reads every container's authored contents STATICALLY from the shipped scene bundles, so
gen_data.py can emit one AP location per vanilla item slot instead of one per chest.

Where the data lives (verified against real chest hierarchies, cf. probe in the multi-slot
investigation): the container root owns the GuidComponent; a child GO carries
Saveable_Inventory whose `_lootBhvr` PPtr points at the Inventory_LootBhvr behaviour, and
THAT serializes the authored contents:

    Inventory_LootBhvr._lootBhvr._fixLoot = [ { _item: PPtr<Item>, _amount, _isGarbage }, ... ]

`_generatedLoot` is always empty in the bundles (rolled at runtime from the flavour loot
tables, capped by _maxLootAmount/_maxLootSellValue) and is deliberately NOT extracted:
it differs per save, so it can never be a deterministic location. Only _fixLoot slots are.

Item PPtrs are resolved to readable ids in a second pass over the item bundles, exactly
like extract_traders.py does for trader stock. The Item asset also carries the quest-item
flag the client's LootSuppressor honours (field name discovered at resolve time and
printed); it is emitted per slot so gen_data.py can skip protected slots.

Run from tools/extract_locations (needs script_index.pkl). Same guid model as extract3.py:
SaveRoot_Guid._guidComponent -> GuidComponent._guidString == the key the client sees.
"""
import UnityPy, glob, os, pickle, json, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
OUT = os.path.join(HERE, "..", "extracted", "chest_slots.json")

idx = pickle.load(open(os.path.join(HERE, "script_index.pkl"), "rb"))
S = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}
CAB2BUNDLE = {k.lower(): v for k, v in idx["cabs"].items()}

# Saveables that can reference the loot behaviour / inventory holding authored contents.
INVENTORY_SAVEABLES = ("Saveable_Inventory", "Saveable_LootInventory")


def bn(p):
    return os.path.basename(p.replace("\\", "/"))


def sweep():
    """Pass 1: every container guid -> raw fix-loot slots [(item_ref, amount, garbage)]."""
    files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
    by_guid = {}      # guid_lower -> {"object": name, "raw_slots": [(ref, amount, garbage)]}
    item_need = set()  # (cab_lower, path_id) to resolve in pass 2
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
            gon, mb = {}, {}
            by_go = collections.defaultdict(dict)
            has_saveroot = False
            for o in objlist:
                try:
                    tn = o.type.name
                    if tn == "GameObject":
                        gon[o.path_id] = o.read_typetree().get("m_Name")
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
                        if cls == "SaveRoot_Guid":
                            has_saveroot = True
                except Exception:
                    continue
            if not has_saveroot:
                continue

            def ext_ref(pptr):
                """PPtr -> (cab_lower, path_id) or None. Same shape as extract_traders.py."""
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
                """Same-cab PPtr -> (cls, dict) or None."""
                if not pptr or pptr.get("m_FileID", 0) != 0:
                    return None
                return mb.get(pptr.get("m_PathID"))

            for pid, (cls, d) in mb.items():
                if cls != "SaveRoot_Guid":
                    continue
                gc_ptr = d.get("_guidComponent") or {}
                guid = None
                if gc_ptr.get("m_FileID") == 0 and gc_ptr.get("m_PathID"):
                    g = mb.get(gc_ptr["m_PathID"])
                    if g and g[0] == "GuidComponent":
                        guid = g[1].get("_guidString")
                if not guid:
                    continue

                save_go = d.get("m_GameObject", {}).get("m_PathID")
                sibs = by_go.get(save_go, {})
                raw_slots = []
                for scls in INVENTORY_SAVEABLES:
                    sd = sibs.get(scls)
                    if not sd:
                        continue
                    # The authored contents: Inventory_LootBhvr._lootBhvr._fixLoot.
                    lb = local(sd.get("_lootBhvr"))
                    if lb:
                        fix = ((lb[1].get("_lootBhvr") or {}).get("_fixLoot")) or []
                        for slot in fix:
                            ref = ext_ref(slot.get("_item"))
                            if ref is None:
                                continue
                            item_need.add(ref)
                            raw_slots.append((ref, slot.get("_amount") or 1,
                                              1 if slot.get("_isGarbage") else 0))
                    # Directly-authored inventory items (rare; empty on every probed chest,
                    # but covered so an authored stack cannot silently vanish from the count).
                    inv = local(sd.get("_inventory"))
                    if inv:
                        for slot in (inv[1].get("_inventoryItems") or []):
                            if not isinstance(slot, dict):
                                continue
                            ref = ext_ref(slot.get("_item") or slot.get("Item"))
                            if ref is None:
                                continue
                            item_need.add(ref)
                            raw_slots.append((ref, slot.get("_amount") or slot.get("Amount") or 1, 0))
                if not raw_slots:
                    continue
                key = guid.lower()
                # First sighting wins, matching extract3's dedupe-by-save-key order.
                if key not in by_guid:
                    by_guid[key] = {"object": gon.get(save_go), "raw_slots": raw_slots}
        if bi % 200 == 0:
            print("  sweep %d/%d  containers=%d item_refs=%d  %.0fs"
                  % (bi, len(files), len(by_guid), len(item_need), time.time() - t0))
            sys.stdout.flush()
    print("sweep DONE %.0fs  containers_with_fixloot=%d item_refs=%d"
          % (time.time() - t0, len(by_guid), len(item_need)))
    return by_guid, item_need


def resolve_items(item_need):
    """Pass 2: item PPtr -> {readable_id, quest}. Mirrors extract_traders.resolve_items,
    additionally sniffing the Item asset's quest-item flag (the field backing Item.IsQuestItem)."""
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

    resolved = {}
    quest_fields = collections.Counter()
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
                quest = False
                for k, v in d.items():
                    if "quest" in k.lower():
                        quest_fields[k] += 1
                        if v:
                            quest = True
                resolved[(c, pid)] = {
                    "readable_id": d.get("_readableId"),
                    "quest": quest,
                }
        if bi % 200 == 0:
            print("  resolve %d/%d  %.0fs" % (bi, len(by_bundle), time.time() - t0))
            sys.stdout.flush()
    print("resolve DONE %.0fs  resolved=%d/%d  quest-flag fields seen: %s"
          % (time.time() - t0, len(resolved), len(item_need), dict(quest_fields) or "NONE (flag missing!)"))
    return resolved


def main():
    by_guid, item_need = sweep()
    resolved = resolve_items(item_need)

    out = {}
    dropped = 0
    for guid, rec in sorted(by_guid.items()):
        slots = []
        for ref, amount, garbage in rec["raw_slots"]:
            info = resolved.get(ref)
            if not info or not info.get("readable_id"):
                dropped += 1
                continue
            slots.append({
                "readable_id": info["readable_id"],
                "amount": amount,
                "garbage": garbage,
                "quest": bool(info.get("quest")),
            })
        if slots:
            out[guid] = {"object": rec["object"], "slots": slots}
    if dropped:
        print("WARNING: %d slot(s) dropped: item PPtr did not resolve to a readable id" % dropped)

    counts = collections.Counter(len(v["slots"]) for v in out.values())
    print("containers=%d  slot-count histogram: %s" % (len(out), dict(sorted(counts.items()))))
    print("multi-slot containers (>=2): %d" % sum(n for k, n in counts.items() if k >= 2))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()
