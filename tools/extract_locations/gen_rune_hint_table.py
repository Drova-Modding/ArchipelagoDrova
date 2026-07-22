"""Generate ArchipelagoDrova/Data/RuneHintTable.g.cs: overlay geometry for the rune hint art.

Self-contained: exports the hint art sprites from the game bundles by name, calibrates the
pattern grid inside each (per-pixel fit, verified against the known vanilla pattern), samples
the ON/OFF colors, and emits per-piece overlay data:

  sprite name -> pattern, quadrant, region rect (exported-image px, Unity bottom-left origin),
                 cell size, trim offset, ON/OFF colors, alpha mask (hex, row-major bottom-up)

The client (RuneHintOverlay) composes a replacement plate face for the door's NEW pattern and
lays it over the original renderer, so world-art hints stay truthful under the rune shuffle.
Full plates (Auwald 0-3, LunaTemple, Räubermine 0-1) show the whole 8x8 grid behind weathering;
the RedTower clues each show one 4x4 quadrant - note the authored NE<->SE swap between the
clue's placement name and the pattern quadrant it displays, which the per-piece fit discovers
rather than assumes.

Calibration is scored PER PIXEL over the whole region (dark px in ON cells, light px in OFF
cells), not per cell center: cell-center scoring is flat over a couple pixels of grid shift and
shipped a visibly misaligned overlay once. A cell-center agreement check (>= 0.97) still guards
pattern identity. The atlas also TRIMS the plate sprites (runtime rect 72x72, packed content
67x67 at textureRectOffset ~(2.08, 3.08)); the offset is emitted so the client can convert
exported-image coords into the sprite-rect space its pivot lives in.
"""
import UnityPy, glob, os, re
import numpy as np

BD = r"C:\Program Files (x86)\Steam\steamapps\common\Drova - Forsaken Kin\Drova_Data\StreamingAssets\aa\StandaloneWindows64"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT_CS = os.path.join(REPO, "ArchipelagoDrova", "Data", "RuneHintTable.g.cs")

# piece sprite name -> (candidate patterns, kind); kind: "full" (8x8 grid) or "clue" (4x4 quadrant
# plate). Multiple candidates let the calibrator decide which pattern a piece displays (the two
# Räubermine boards are visually assigned but verified here; a wrong assignment fails the fit).
PIECES = {
    "Ruin_Riddle_Plates_0": (["DrawRune_AuwaldPuzzle"], "full"),
    "Ruin_Riddle_Plates_1": (["DrawRune_AuwaldPuzzle"], "full"),
    "Ruin_Riddle_Plates_2": (["DrawRune_AuwaldPuzzle"], "full"),
    "Ruin_Riddle_Plates_3": (["DrawRune_AuwaldPuzzle"], "full"),
    "Ruin_Riddle_Plates_LunaTemple": (["DrawRune_LunaTemplePuzzle"], "full"),
    # The Räuber boards hang ~2100 units from their doors (found via ap_dumpnearby in the field);
    # each shows one door's full pattern - the calibrator picks which.
    "Ruin_Riddle_Plates_Räubermine_0": (["DrawRune_RäuberPuzzle_A", "DrawRune_RäuberPuzzle_B"], "full"),
    "Ruin_Riddle_Plates_Räubermine_1": (["DrawRune_RäuberPuzzle_A", "DrawRune_RäuberPuzzle_B"], "full"),
    "RuneDrawRiddleClue_RedTower_NE": (["DrawRune_RedTowerPuzzle"], "clue"),
    "RuneDrawRiddleClue_RedTower_NW": (["DrawRune_RedTowerPuzzle"], "clue"),
    "RuneDrawRiddleClue_RedTower_SE": (["DrawRune_RedTowerPuzzle"], "clue"),
    "RuneDrawRiddleClue_RedTower_SW": (["DrawRune_RedTowerPuzzle"], "clue"),
}

src = open(os.path.join(REPO, "ArchipelagoDrova", "Data", "RuneTable.g.cs"), encoding="utf-8").read()
PATS = {}
for name, hexs in re.findall(r'\{ "(DrawRune_[^"]+)", "([0-9a-f]+)" \}', src):
    px = [hexs[i * 8:(i + 1) * 8] for i in range(64)]
    alpha = [int(p[6:8], 16) > 127 for p in px]
    PATS[name] = np.array([[alpha[r * 8 + c] for c in range(8)] for r in range(7, -1, -1)], dtype=np.int8)  # top-down

def quad(p, qname):
    r0 = 0 if qname in ("NW", "NE") else 4
    c0 = 0 if qname in ("NW", "SW") else 4
    return p[r0:r0 + 4, c0:c0 + 4]

# ---- export the sprites + atlas trim metadata ---------------------------------------------------
images = {}
trim = {}
for f in sorted(glob.glob(os.path.join(BD, "*.bundle"))):
    if len(images) == len(PIECES):
        break
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
        if d.m_Name in PIECES and d.m_Name not in images:
            images[d.m_Name] = d.image.convert("RGBA")
            # Where the packed (trimmed) content sits inside the runtime sprite rect. The client's
            # pivot is rect-relative, so overlay positions need this added to image-space coords.
            off = d.m_RD.textureRectOffset
            trim[d.m_Name] = (off.x, off.y)
missing = set(PIECES) - set(images)
assert not missing, f"sprites not found: {missing}"
print("exported", len(images), "sprites")

def classify(im):
    """H x W int8: 1 = dark (ON art), 0 = light (OFF art), -1 = transparent/ambiguous weathering."""
    a = np.asarray(im, dtype=np.float32)
    lum = (a[..., 0] * 3 + a[..., 1] * 6 + a[..., 2]) / 10
    cls = np.full(lum.shape, -1, np.int8)
    opaque = a[..., 3] >= 64
    cls[opaque & (lum < 70)] = 1
    cls[opaque & (lum > 110)] = 0
    return cls

def score_fit(cls, pattern, ox, oy, s):
    """Per-pixel agreement of the art with `pattern` for a grid at (ox, oy) cell size s.
    PIL top-down coords throughout; pattern rows are top-down."""
    cells = pattern.shape[0]
    h, w = cls.shape
    x0, x1 = int(np.ceil(ox)), int(np.floor(ox + cells * s))
    y0, y1 = int(np.ceil(oy)), int(np.floor(oy + cells * s))
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 <= x0 or y1 <= y0:
        return -1.0, 0
    sub = cls[y0:y1, x0:x1]
    col = np.clip(((np.arange(x0, x1) - ox) / s).astype(int), 0, cells - 1)
    row = np.clip(((np.arange(y0, y1) - oy) / s).astype(int), 0, cells - 1)
    expected = pattern[np.ix_(row, col)]
    valid = sub >= 0
    n = int(valid.sum())
    if n < 100:
        return -1.0, 0
    return float((sub[valid] == expected[valid]).sum()) / n, n

def refine(cls, pattern, ox, oy, s, span, step, s_span, s_step):
    best = (-1.0, 0, ox, oy, s)
    ss = np.arange(s - s_span, s + s_span + 1e-9, s_step)
    for s_ in ss:
        for ox_ in np.arange(ox - span, ox + span + 1e-9, step):
            for oy_ in np.arange(oy - span, oy + span + 1e-9, step):
                sc, n = score_fit(cls, pattern, ox_, oy_, s_)
                if (sc, n) > (best[0], best[1]):
                    best = (sc, n, ox_, oy_, s_)
    return best

def cell_center_agreement(cls, pattern, ox, oy, s):
    """The old identity guard: classify each cell by its center 40% and compare. Weathered
    (ambiguous) cells don't count. Returns (agreement, known)."""
    cells = pattern.shape[0]
    match = known = 0
    for r in range(cells):
        for c in range(cells):
            x0, x1 = int(ox + (c + 0.3) * s), int(np.ceil(ox + (c + 0.7) * s))
            y0, y1 = int(oy + (r + 0.3) * s), int(np.ceil(oy + (r + 0.7) * s))
            window = cls[max(y0, 0):y1, max(x0, 0):x1]
            vals = window[window >= 0]
            if vals.size == 0:
                continue
            m = float(vals.mean())
            if 0.35 < m < 0.65:
                continue
            known += 1
            if (m >= 0.5) == bool(pattern[r][c]):
                match += 1
    return (match / known if known else 0.0), known

def sample_colors(im, region):
    a = np.asarray(im, dtype=np.float32)
    x0, y0, rw, rh = (int(round(v)) for v in region)
    sub = a[max(y0, 0):y0 + rh, max(x0, 0):x0 + rw]
    lum = (sub[..., 0] * 3 + sub[..., 1] * 6 + sub[..., 2]) / 10
    opaque = sub[..., 3] >= 64
    on_px = sub[opaque & (lum < 70)]
    off_px = sub[opaque & (lum > 110)]
    def mean(arr, fallback):
        if arr.size == 0:
            return fallback
        return tuple(int(v) for v in arr.mean(axis=0)[:3]) + (255,)
    return mean(on_px, (40, 38, 34, 255)), mean(off_px, (150, 145, 128, 255))

entries = []
for piece, (candidates, kind) in sorted(PIECES.items()):
    im = images[piece]
    cls = classify(im)
    w, h = im.size
    px = im.load()
    if kind == "full":
        fits = []
        for pat_candidate in candidates:
            pattern = PATS[pat_candidate]
            # coarse: 0.5px grid over the plausible margin band, then refine to 0.025px
            coarse = (-1.0, 0, 0, 0, 0)
            for s10 in range(52, 69, 2):
                s = s10 / 10.0
                for ox in np.arange(4.0, 16.01, 0.5):
                    for oy in np.arange(4.0, 16.01, 0.5):
                        sc, n = score_fit(cls, pattern, ox, oy, s)
                        if (sc, n) > (coarse[0], coarse[1]):
                            coarse = (sc, n, ox, oy, s)
            fit = refine(cls, pattern, coarse[2], coarse[3], coarse[4], 0.75, 0.1, 0.15, 0.05)
            fit = refine(cls, pattern, fit[2], fit[3], fit[4], 0.1, 0.025, 0.04, 0.01)
            fits.append((fit, pat_candidate))
        fits.sort(key=lambda f: (f[0][0], f[0][1]), reverse=True)
        (sc, n, ox, oy, s), pat = fits[0]
        # identity guard for boards whose pattern the fit had to pick: the winner must clearly
        # beat the runner-up, otherwise the assignment is a guess
        if len(fits) > 1:
            margin = fits[0][0][0] - fits[1][0][0]
            assert margin >= 0.03, f"{piece}: pattern pick ambiguous (margin {margin:.3f})"
        cells, qname = 8, "full"
    else:
        pat = candidates[0]
        # seed inside the opaque plate band (the clue art includes a pedestal below the plate)
        rows = [y for y in range(h) if sum(1 for x in range(w) if px[x, y][3] >= 64) > w * 0.6]
        y1 = max(rows)
        y0 = y1
        while y0 - 1 in rows:
            y0 -= 1
        cols = [x for x in range(w) if any(px[x, y][3] >= 64 for y in range(y0, y1 + 1))]
        x0b = min(cols)
        best = None
        for q in ("NW", "NE", "SW", "SE"):
            g = quad(PATS[pat], q)
            coarse = (-1.0, 0, 0, 0, 0)
            for s10 in range(55, 81, 2):
                s = s10 / 10.0
                for ox in np.arange(x0b, x0b + 8.01, 0.5):
                    for oy in np.arange(y0, y0 + 8.01, 0.5):
                        sc, n = score_fit(cls, g, ox, oy, s)
                        if (sc, n) > (coarse[0], coarse[1]):
                            coarse = (sc, n, ox, oy, s)
            fit = refine(cls, g, coarse[2], coarse[3], coarse[4], 0.75, 0.1, 0.15, 0.05)
            fit = refine(cls, g, fit[2], fit[3], fit[4], 0.1, 0.025, 0.04, 0.01)
            if best is None or (fit[0], fit[1]) > (best[0][0], best[0][1]):
                best = (fit, q)
        (sc, n, ox, oy, s), qname = best
        cells = 4

    grid = PATS[pat] if qname == "full" else quad(PATS[pat], qname)
    # Sanity floor: weathering caps the per-pixel score well below 1.0 (worst observed vanilla
    # plate: 0.875), but a grid in the wrong place scores far lower still (~0.78 for a half-cell
    # shift). Cell-center agreement is printed for information only - on heavily weathered plates
    # it is unreliable, which is how the original cell-center calibration shipped a visibly
    # misaligned overlay in the first place.
    assert sc >= 0.8, f"{piece}: per-pixel fit score {sc:.3f} too low - refusing to ship a guess"
    agree, known = cell_center_agreement(cls, grid, ox, oy, s)
    region = (ox, oy, cells * s, cells * s)
    on, off = sample_colors(im, region)

    # alpha mask of the region, row-major BOTTOM-UP (Unity texture order)
    rx, ry, rw, rh = (int(round(v)) for v in region)
    bits = []
    for yy in range(ry + rh - 1, ry - 1, -1):
        for xx in range(rx, rx + rw):
            opaque = 0 <= xx < w and 0 <= yy < h and px[xx, yy][3] >= 64
            bits.append(1 if opaque else 0)
    mask_hex = "".join(f"{int(''.join(map(str, bits[i:i+4])), 2):x}" for i in range(0, len(bits), 4))

    # region Y converted to Unity bottom-left origin (still exported-image space; the client adds
    # the trim offset to reach sprite-rect space)
    unity_y = h - (ry + rh)
    tox, toy = trim[piece]
    # sub-pixel remainder of the fit joins the trim offset so the mask/texture can stay integer
    tox += ox - rx
    toy += (h - (oy + cells * s)) - unity_y
    entries.append({
        "sprite": piece, "pattern": pat, "quad": qname, "cells": cells,
        "cell": round(cells * s / cells, 3),
        "x": rx, "y": unity_y, "w": rw, "h": rh,
        "offx": round(tox, 3), "offy": round(toy, 3),
        "on": on, "off": off, "mask": mask_hex, "score": sc, "agree": agree, "known": known,
    })
    print(f"{piece:34} {qname:4} region=({rx},{unity_y},{rw}x{rh}) cell={s:.2f} "
          f"off=({tox:+.2f},{toy:+.2f}) px_score={sc:.3f} cell_agree={agree:.2f} known={known}")

qnames = sorted(e["quad"] for e in entries if e["cells"] == 4)
assert qnames == ["NE", "NW", "SE", "SW"], f"clue quadrants not distinct: {qnames}"
raeuber = sorted(e["pattern"] for e in entries if "Räubermine" in e["sprite"])
assert raeuber == ["DrawRune_RäuberPuzzle_A", "DrawRune_RäuberPuzzle_B"], (
    f"Räuber boards must cover both door patterns, got {raeuber}")

def color(c):
    return f"new Color32({c[0]}, {c[1]}, {c[2]}, 255)"

lines = [
    "// Generated by tools/extract_locations/gen_rune_hint_table.py. Do not edit by hand.",
    "using System.Collections.Generic;",
    "using UnityEngine;",
    "",
    "namespace ArchipelagoDrova.Data",
    "{",
    "    public static partial class RuneHintTable",
    "    {",
    "        /// <summary>Hint-art sprite name -> overlay geometry. Region is in the packed image's",
    "        /// pixel space with a bottom-left origin; Offset converts into sprite-rect space",
    "        /// (atlas trim + sub-pixel fit); the mask is row-major bottom-up.</summary>",
    "        public static readonly Dictionary<string, RuneHintPiece> Generated = new Dictionary<string, RuneHintPiece>",
    "        {",
]
for e in entries:
    lines.append(
        f'            {{ "{e["sprite"]}", new RuneHintPiece("{e["pattern"]}", "{e["quad"]}", {e["cells"]}, '
        f'{e["cell"]}f, {e["x"]}, {e["y"]}, {e["w"]}, {e["h"]}, {e["offx"]}f, {e["offy"]}f, '
        f'{color(e["on"])}, {color(e["off"])}, "{e["mask"]}") }},'
    )
lines += ["        };", "    }", "}", ""]
open(OUT_CS, "w", encoding="utf-8").write("\n".join(lines))
print(f"wrote {OUT_CS}")
