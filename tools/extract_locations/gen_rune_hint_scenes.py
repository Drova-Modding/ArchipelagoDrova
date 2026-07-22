"""Generate ArchipelagoDrova/Data/RuneHintScenes.g.cs: which streamed scenes contain hint art.

Runtime motivation: Drova streams area chunk scenes continuously while the player walks. The
client used to sweep renderers on every scene load to find rune hint art, which cost visible
frame drops. This maps each hint art sprite to the scene(s) whose SpriteRenderers reference it,
so the client can skip every scene that provably contains none.

Pass 1: locate the hint sprites' (cab, path_id) asset identities.
Pass 2: for every streamed-scene bundle whose serialized files reference one of those cabs,
        read each SpriteRenderer's m_Sprite PPtr and match. Cab -> scene name comes from the
        bundle's AssetBundle container (runtime scene name = container basename sans .unity).
"""
import UnityPy, glob, os, json, sys, time

BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT_CS = os.path.join(REPO, "ArchipelagoDrova", "Data", "RuneHintScenes.g.cs")

SPRITES = {
    "Ruin_Riddle_Plates_0", "Ruin_Riddle_Plates_1", "Ruin_Riddle_Plates_2", "Ruin_Riddle_Plates_3",
    "Ruin_Riddle_Plates_LunaTemple",
    "Ruin_Riddle_Plates_Räubermine_0", "Ruin_Riddle_Plates_Räubermine_1",
    "RuneDrawRiddleClue_RedTower_NE", "RuneDrawRiddleClue_RedTower_NW",
    "RuneDrawRiddleClue_RedTower_SE", "RuneDrawRiddleClue_RedTower_SW",
}

files = sorted(glob.glob(os.path.join(BD, "*.bundle")))
t0 = time.time()

# ---- pass 1: sprite asset identities (a sprite may be duplicated into several cabs) ------------
sprite_ids = {}  # (cab_lower, path_id) -> sprite name
for bi, f in enumerate(files):
    try:
        env = UnityPy.load(f)
    except Exception:
        continue
    for o in env.objects:
        if o.type.name != "Sprite":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        if d.m_Name in SPRITES:
            sprite_ids[(o.assets_file.name.lower(), o.path_id)] = d.m_Name
    if bi % 500 == 0:
        print(f"pass1 {bi}/{len(files)} {time.time()-t0:.0f}s ids={len(sprite_ids)}"); sys.stdout.flush()
sprite_cabs = {cab for cab, _ in sprite_ids}
found_names = set(sprite_ids.values())
assert found_names == SPRITES, f"sprites not found in any bundle: {SPRITES - found_names}"
print(f"pass1 done: {len(sprite_ids)} sprite ids in cabs {sorted(sprite_cabs)}")

# ---- pass 2: scene bundles whose files reference those cabs ------------------------------------
scene_hits = {}  # scene name -> set of sprite names
for bi, f in enumerate(files):
    try:
        env = UnityPy.load(f)
    except Exception:
        continue
    is_scene, cab2scene = False, {}
    for o in env.objects:
        if o.type.name == "AssetBundle":
            d = o.read_typetree()
            is_scene = bool(d.get("m_IsStreamedSceneAssetBundle"))
            # m_SceneHashes maps scene path -> serialized-file CAB directly (CAB- uppercase there,
            # env.cabs keys lowercase). Ordering-based zips against env.cabs fail: the cab list
            # interleaves .sharedassets/.resS files and does not follow container order.
            for entry in d.get("m_SceneHashes") or []:
                path, cab_name = (entry[0], entry[1]) if isinstance(entry, (list, tuple)) else (entry, "")
                cab2scene[str(cab_name).lower()] = path
            break
    if not is_scene:
        continue

    for cab, sf in env.cabs.items():
        try:
            ext_names = [os.path.basename(e.path.replace("\\", "/")).lower() for e in sf.externals]
        except Exception:
            continue
        if not (sprite_cabs & set(ext_names)) and sf.name.lower() not in sprite_cabs:
            continue  # this scene file cannot reference the hint sprites
        try:
            objlist = list(sf.objects.values())
        except Exception:
            continue
        for o in objlist:
            if o.type.name != "SpriteRenderer":
                continue
            try:
                d = o.read_typetree()
            except Exception:
                continue
            sp = d.get("m_Sprite") or {}
            fid, pid = sp.get("m_FileID"), sp.get("m_PathID")
            if not pid:
                continue
            ref_cab = sf.name.lower() if fid == 0 else ext_names[fid - 1] if 0 < fid <= len(ext_names) else None
            name = sprite_ids.get((ref_cab, pid))
            if name is None:
                continue
            scene_path = cab2scene.get(cab, "")
            scene = os.path.splitext(os.path.basename(scene_path))[0] if scene_path else ""
            if not scene:
                print(f"WARNING: hit for {name} in {os.path.basename(f)} but no scene name for cab {cab}")
                continue
            scene_hits.setdefault(scene, set()).add(name)
    if bi % 500 == 0:
        print(f"pass2 {bi}/{len(files)} {time.time()-t0:.0f}s scenes={len(scene_hits)}"); sys.stdout.flush()

print(f"done {time.time()-t0:.0f}s")
for scene in sorted(scene_hits):
    print(f"  {scene}: {sorted(scene_hits[scene])}")
covered = set().union(*scene_hits.values()) if scene_hits else set()
assert covered == SPRITES, f"art pieces with no scene: {SPRITES - covered}"

lines = [
    "// Generated by tools/extract_locations/gen_rune_hint_scenes.py. Do not edit by hand.",
    "using System;",
    "using System.Collections.Generic;",
    "",
    "namespace ArchipelagoDrova.Data",
    "{",
    "    public static partial class RuneHintTable",
    "    {",
    "        /// <summary>Streamed scenes that contain rune hint art. Scene loads outside this",
    "        /// set are skipped without touching a single renderer - chunk scenes stream in",
    "        /// constantly while walking and sweeping them all cost visible frame drops.</summary>",
    "        public static readonly HashSet<string> HintScenes = new HashSet<string>(StringComparer.OrdinalIgnoreCase)",
    "        {",
]
for scene in sorted(scene_hits):
    pieces = ", ".join(sorted(scene_hits[scene]))
    lines.append(f'            "{scene}", // {pieces}')
lines += ["        };", "    }", "}", ""]
open(OUT_CS, "w", encoding="utf-8").write("\n".join(lines))
print(f"wrote {OUT_CS}")
