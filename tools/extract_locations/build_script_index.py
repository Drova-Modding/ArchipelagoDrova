import UnityPy, glob, os, pickle, time, sys, collections
BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
print("bundles:", len(files)); sys.stdout.flush()

# (cab_name, path_id) -> class name ; also cab_name -> bundle file
script_index = {}
cab_to_bundle = {}
t0=time.time()
for i, f in enumerate(files):
    try:
        env = UnityPy.load(f)
    except Exception as e:
        print("FAIL", os.path.basename(f), e); continue
    for cab, sf in env.cabs.items():
        cab_to_bundle[cab] = os.path.basename(f)
    for o in env.objects:
        if o.type.name != "MonoScript":
            continue
        try:
            d = o.read_typetree()
        except Exception:
            continue
        cabname = getattr(o.assets_file, "name", None)
        script_index[(cabname, o.path_id)] = (d.get("m_ClassName"), d.get("m_Namespace"), d.get("m_AssemblyName"))
    if i % 200 == 0:
        print(f"  {i}/{len(files)} scripts={len(script_index)} cabs={len(cab_to_bundle)} {time.time()-t0:.0f}s"); sys.stdout.flush()

print("MonoScript entries:", len(script_index), "cabs:", len(cab_to_bundle), f"{time.time()-t0:.0f}s")
pickle.dump({"scripts":script_index,"cabs":cab_to_bundle}, open("script_index.pkl","wb"))

names = collections.Counter(v[0] for v in script_index.values())
print("\n=== interesting classes present ===")
for k in ["GuidComponent","PickupInteraction","Interact_Bhvr_LootInventory","Interact_Bhvr_LootKnockout",
          "SaveRoot_Guid","SaveRoot_Dynamic","Depot_Wrapper","Interact_LootBhvr_Chest","Interact_Bhvr_LootAll"]:
    print(f"  {k}: {names.get(k,0)}")
