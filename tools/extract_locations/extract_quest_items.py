"""
Drova quest item-reference extractor  ->  tools/extracted/quest_items.json

Answers "which items does a quest touch, and are any of them ORDINARY loot?" - the failure mode
behind the Missing questline fix: a quest that asks for something the game does not flag as quest
property (plain mushrooms) can soft-lock when the randomizer's LootSuppressor deletes the vanilla
copy at a randomized location. STORY_CRITICAL_GUIDS in gen_data.py currently hard-codes the two
cases found by hand; this sweep is the general version.

Where the data is: quest logic lives in NodeCanvas graphs (QuestGraph) and dialogue graphs
(DialogueTree). Their node payload is Odin-serialized and LZ4-compressed in `_serializedBytes`, so
node semantics ("give" vs "require") are NOT readable without decompressing it. They do not have to
be: every UnityEngine object a graph's nodes reference is serialized OUTSIDE the blob, as a plain
PPtr list in `_objectByteReferences` / `_objectReferences`. Resolving those PPtrs against the item
database yields, per graph, the exact set of items the quest can possibly interact with.

That is a deliberately conservative signal - it cannot tell a quest reward from a quest requirement,
so it over-reports rather than under-reports. For "is this item safe to suppress?" over-reporting is
the correct direction: a false positive costs one location, a false negative costs a soft-lock.

Output:
  {
    "graphs": {<graph name>: {"kind": "QuestGraph"|"DialogueTree", "items": [readable_id, ...]}},
    "items":  {<readable_id>: {"graphs": [...], "quest_valued": bool, "in_quest_category": bool,
                               "sell": n, "buy": n}},
    "ordinary": [readable_id, ...]     # referenced by a quest AND not flagged as quest property
  }

Run from tools/extract_locations (needs script_index.pkl). Reads item_values.json for the two
quest flags, so run extract_item_values.py first.
"""
import UnityPy, glob, os, pickle, json, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
OUT = os.path.join(HERE, "..", "extracted", "quest_items.json")
ITEM_VALUES_SRC = os.path.join(HERE, "..", "extracted", "item_values.json")

idx = pickle.load(open(os.path.join(HERE, "script_index.pkl"), "rb"))
S = {(k[0].lower() if k[0] else None, k[1]): v[0] for k, v in idx["scripts"].items()}
CAB2BUNDLE = {k.lower(): v for k, v in idx["cabs"].items()}

GRAPH_CLASSES = ("QuestGraph", "DialogueTree")
REF_FIELDS = ("_objectByteReferences", "_objectReferences")


def bn(p):
    return os.path.basename(p.replace("\\", "/"))


def sweep():
    files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
    print("bundles:", len(files)); sys.stdout.flush()

    graphs = {}          # graph name -> {"kind":..., "refs": set((cab, path_id))}
    item_need = set()
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
            for o in objlist:
                if o.type.name != "MonoBehaviour":
                    continue
                try:
                    d = o.read_typetree()
                except Exception:
                    continue
                scr = d.get("m_Script") or {}
                fid, pid = scr.get("m_FileID"), scr.get("m_PathID")
                if fid is None:
                    continue
                try:
                    tcab = sf.name if fid == 0 else bn(sf.externals[fid - 1].path)
                except Exception:
                    continue
                cls = S.get((tcab.lower(), pid))
                if cls not in GRAPH_CLASSES:
                    continue
                name = d.get("m_Name") or "?"
                rec = graphs.setdefault(name, {"kind": cls, "refs": set()})
                for field in REF_FIELDS:
                    for ptr in (d.get(field) or []):
                        if not isinstance(ptr, dict) or not ptr.get("m_PathID"):
                            continue
                        rfid = ptr.get("m_FileID", 0)
                        if rfid == 0:
                            rcab = sf.name
                        else:
                            try:
                                rcab = bn(sf.externals[rfid - 1].path)
                            except Exception:
                                continue
                        ref = (rcab.lower(), ptr["m_PathID"])
                        rec["refs"].add(ref)
                        item_need.add(ref)
        del env
        if bi % 200 == 0:
            print("  sweep %d/%d graphs=%d refs=%d %.0fs"
                  % (bi, len(files), len(graphs), len(item_need), time.time() - t0))
            sys.stdout.flush()
    print("sweep DONE %.0fs graphs=%d distinct refs=%d"
          % (time.time() - t0, len(graphs), len(item_need)))
    return graphs, item_need


def resolve_items(item_need):
    """Ref -> readable id, for the refs that are Item assets (everything else resolves to None)."""
    by_bundle = collections.defaultdict(set)
    for cab, pid in item_need:
        b = CAB2BUNDLE.get(cab)
        if b:
            by_bundle[b].add((cab, pid))

    resolved, t0 = {}, time.time()
    for bi, (b, refs) in enumerate(sorted(by_bundle.items())):
        try:
            env = UnityPy.load(os.path.join(BD, b))
        except Exception:
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
                if o is None or o.type.name != "MonoBehaviour":
                    continue
                try:
                    d = o.read_typetree()
                except Exception:
                    continue
                rid = d.get("_readableId")
                # Items carry both a readable id and a price pair; other addressable assets that
                # happen to have a readable id (abilities, talents) do not.
                if rid and "_buyValue" in d and "_sellValue" in d:
                    resolved[(c, pid)] = rid
        del env
        if bi % 200 == 0:
            print("  resolve %d/%d items=%d %.0fs" % (bi, len(by_bundle), len(resolved), time.time() - t0))
            sys.stdout.flush()
    print("resolve DONE %.0fs item refs=%d" % (time.time() - t0, len(resolved)))
    return resolved


def main():
    graphs, item_need = sweep()
    resolved = resolve_items(item_need)

    values = {}
    if os.path.exists(ITEM_VALUES_SRC):
        with open(ITEM_VALUES_SRC, encoding="utf-8") as fh:
            values = json.load(fh)
    else:
        print("WARNING: %s missing - quest flags unavailable" % ITEM_VALUES_SRC)

    out_graphs, by_item = {}, collections.defaultdict(set)
    for name, rec in graphs.items():
        rids = sorted({resolved[r] for r in rec["refs"] if r in resolved})
        if not rids:
            continue
        out_graphs[name] = {"kind": rec["kind"], "items": rids}
        for rid in rids:
            by_item[rid].add(name)

    items_out, ordinary = {}, []
    for rid, names in sorted(by_item.items()):
        v = values.get(rid) or {}
        buy, sell = v.get("buy", 0), v.get("sell", 0)
        quest_valued = bool(v) and buy == 0 and sell == 0     # the game's own Item.IsQuestItem
        in_cat = bool(v.get("cat"))                           # the authored _isInQuestCategory flag
        items_out[rid] = {"graphs": sorted(names), "quest_valued": quest_valued,
                          "in_quest_category": in_cat, "buy": buy, "sell": sell}
        if not quest_valued and not in_cat:
            ordinary.append(rid)

    print("\ngraphs referencing items : %d" % len(out_graphs))
    print("distinct items referenced: %d" % len(items_out))
    print("of which ORDINARY (neither quest-valued nor in the quest category): %d" % len(ordinary))
    for rid in sorted(ordinary, key=lambda r: -len(items_out[r]["graphs"]))[:30]:
        rec = items_out[rid]
        print("  %-38s graphs=%-3d sell=%-4d %s" % (rid, len(rec["graphs"]), rec["sell"],
                                                    ", ".join(rec["graphs"][:3])))

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"graphs": out_graphs, "items": items_out, "ordinary": sorted(ordinary)},
                  fh, indent=1, sort_keys=True, ensure_ascii=True)
        fh.write("\n")
    print("wrote", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
