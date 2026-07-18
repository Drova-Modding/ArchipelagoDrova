import re, json, collections
P = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Mods\saveGame.txt"
lines = open(P, encoding="utf-8", errors="replace").read().splitlines()

# Post-order hypothesis: Saveable_* lines accumulate, a "GO#<key> : ..." line closes the block.
blocks = {}
pending = []
order = []
for ln in lines:
    m = re.match(r'^(GO#[^ :]*) : ', ln)
    if m:
        key = m.group(1)[3:]  # strip GO#
        blocks[key] = pending
        order.append(key)
        pending = []
        continue
    m2 = re.match(r'^(Saveable_[A-Za-z_0-9]+) : ', ln)
    if m2:
        pending.append(m2.group(1))

print("GO# blocks:", len(blocks))
print("leftover pending (after last GO#):", len(pending))
guidre = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
guid_keys = [k for k in blocks if guidre.match(k)]
named_keys = [k for k in blocks if not guidre.match(k)]
print("guid-shaped keys:", len(guid_keys), " named keys:", len(named_keys))
print("named keys sample:", named_keys[:25])

# how many blocks have zero components?
empty = [k for k,v in blocks.items() if not v]
print("blocks with 0 components:", len(empty))

# component histogram over guid keys
hist = collections.Counter()
for k in guid_keys:
    for c in set(blocks[k]):
        hist[c]+=1
print("\n=== per-GUID-object component counts (distinct objects having that component) ===")
for c,n in hist.most_common():
    print(f"{n:6d}  {c}")

LOOT = {"Saveable_PickUp_Once","Saveable_LootInventory","Saveable_Depot",
        "Saveable_LootTablePickups","Saveable_ResourceSpot","Saveable_Inventory"}
loot_objs = {k:blocks[k] for k in guid_keys if LOOT & set(blocks[k])}
print("\nGUID objects with >=1 loot-ish component:", len(loot_objs))
for c in sorted(LOOT):
    print(f"  {c}: {sum(1 for k in loot_objs if c in loot_objs[k])}")

json.dump({k:blocks[k] for k in guid_keys}, open("save_guid_components.json","w"), indent=0)
print("\nwrote save_guid_components.json")
