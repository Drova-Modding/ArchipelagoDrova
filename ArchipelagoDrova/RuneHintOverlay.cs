using ArchipelagoDrova.Data;
using Drova_Modding_API.Access;
using Drova_Modding_API.Systems.Rendering;
using MelonLoader;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Keeps world-art rune hints truthful under the rune shuffle: riddle plates and clue stones
    /// display their pattern as hand-authored art, so when a door's required pattern changes, this
    /// composes a replacement plate face (art's own cell colors, alpha-masked to the plate's
    /// broken edges) and lays it over the original renderer via the Modding API's SpriteOverlay
    /// (which supplies the lit material, interact-highlight registration and cleanup).
    ///
    /// Geometry comes from RuneHintTable.g.cs, calibrated offline against the vanilla patterns
    /// (per-pixel fit; the atlas-trim offset is baked into each piece). The overlay covers only
    /// the grid region; frames and weathered surroundings stay original.
    ///
    /// Sweep strategy: only the scenes in RuneHintTable.HintScenes (extracted offline) can
    /// contain hint art, so those - and nothing else - are registered with the API's
    /// SceneStreamAccess. Every other streamed chunk load costs the API one dictionary lookup;
    /// sweeping every scene cost ~20fps while walking, in the field.
    /// </summary>
    public static class RuneHintOverlay
    {
        private const string OverlayName = "AP_RuneHint";

        private static Dictionary<string, string> _map;
        private static bool _anyPieceRemapped;
        /// <summary>Renderer instance id -> its live overlay. SpriteOverlay.Destroy is deferred
        /// (end of frame), so liveness is checked through this map, never via transform.Find.</summary>
        private static readonly Dictionary<int, GameObject> _overlayByRenderer = new();
        private static readonly Dictionary<string, Sprite> _spriteCache = new();

        /// <summary>Called once from Core at melon init.</summary>
        public static void Initialize()
        {
            foreach (string sceneName in RuneHintTable.HintScenes)
            {
                SceneStreamAccess.AddSceneListener(sceneName, OnHintSceneLoaded);
            }
        }

        /// <summary>Called alongside RuneShuffler.Configure with the same pattern map.</summary>
        public static void Configure(Dictionary<string, string> map)
        {
            _map = map != null && map.Count > 0 ? new Dictionary<string, string>(map) : null;
            _anyPieceRemapped = false;
            if (_map != null)
            {
                foreach (var piece in RuneHintTable.Generated.Values)
                {
                    if (_map.TryGetValue(piece.Pattern, out string replacement) && replacement != piece.Pattern)
                    {
                        _anyPieceRemapped = true;
                        break;
                    }
                }
            }
            _spriteCache.Clear();

            // Reconfiguring (a different room, or back to vanilla) invalidates every overlay.
            DestroyOverlays();

            // Hint scenes already loaded won't fire their listener again - sweep them now.
            if (_anyPieceRemapped)
            {
                int created = 0;
                foreach (string sceneName in RuneHintTable.HintScenes)
                {
                    var scene = SceneManager.GetSceneByName(sceneName);
                    if (scene.IsValid() && scene.isLoaded)
                    {
                        created += SweepScene(scene);
                    }
                }
                MelonLogger.Msg("Rune hint overlays applied to " + created + " art piece(s).");
            }
        }

        private static void OnHintSceneLoaded(Scene scene)
        {
            try
            {
                if (!_anyPieceRemapped)
                {
                    return;
                }
                int created = SweepScene(scene);
                if (created > 0)
                {
                    MelonLogger.Msg("Rune hint overlays applied to " + created + " art piece(s) in " + scene.name + ".");
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("RuneHintOverlay scene sweep failed: " + e);
            }
        }

        private static int SweepScene(Scene scene)
        {
            int created = 0;
            foreach (var renderer in SceneStreamAccess.GetComponentsInScene<SpriteRenderer>(scene))
            {
                if (TryOverlay(renderer))
                {
                    created++;
                }
            }
            return created;
        }

        private static bool TryOverlay(SpriteRenderer renderer)
        {
            if (renderer == null || renderer.sprite == null)
            {
                return false;
            }
            if (!RuneHintTable.Generated.TryGetValue(renderer.sprite.name, out var piece))
            {
                return false;
            }
            if (!_map.TryGetValue(piece.Pattern, out string replacement) || replacement == piece.Pattern)
            {
                return false;
            }
            // Already overlaid and still alive (a reloaded scene brings new renderer instances,
            // whose ids miss this map; dead entries are overwritten below).
            int rendererId = renderer.GetInstanceID();
            if (_overlayByRenderer.TryGetValue(rendererId, out var existing) && existing != null)
            {
                return false;
            }
            return CreateOverlay(renderer, rendererId, piece, replacement);
        }

        private static bool CreateOverlay(SpriteRenderer parent, int rendererId, RuneHintPiece piece, string replacement)
        {
            var sprite = GetOverlaySprite(parent.sprite.name, piece, replacement, parent.sprite.pixelsPerUnit);
            if (sprite == null)
            {
                return false;
            }

            // Region center relative to the sprite pivot, in world units. The pivot is in
            // sprite-RECT pixel space (bottom-left origin); region coords are in the packed
            // image's space, one trim offset (baked into the piece) away.
            var pivot = parent.sprite.pivot;
            float ppu = parent.sprite.pixelsPerUnit;
            var localOffset = new Vector2(
                (piece.X + piece.OffsetX + piece.W / 2f - pivot.x) / ppu,
                (piece.Y + piece.OffsetY + piece.H / 2f - pivot.y) / ppu);

            var overlay = SpriteOverlay.Create(parent, sprite, localOffset, OverlayName);
            if (overlay == null)
            {
                return false;
            }
            _overlayByRenderer[rendererId] = overlay;
            return true;
        }

        private static Sprite GetOverlaySprite(string pieceName, RuneHintPiece piece, string replacement, float ppu)
        {
            string key = pieceName + "->" + replacement;
            if (_spriteCache.TryGetValue(key, out var cached) && cached != null)
            {
                return cached;
            }

            var pattern = DecodeTopDown(replacement);
            if (pattern == null)
            {
                MelonLogger.Warning("Rune hint overlay: unknown pattern '" + replacement + "'.");
                return null;
            }

            int rowOffset = piece.Quad is "SW" or "SE" ? 4 : 0;
            int colOffset = piece.Quad is "NE" or "SE" ? 4 : 0;

            var pixels = new Color32[piece.W * piece.H];
            var clear = new Color32(0, 0, 0, 0);
            for (int y = 0; y < piece.H; y++)
            {
                // Texture rows are bottom-up; pattern rows are top-down.
                int rowTopDown = Mathf.Clamp((int)((piece.H - 1 - y) / piece.CellSize), 0, piece.Cells - 1);
                for (int x = 0; x < piece.W; x++)
                {
                    if (!piece.MaskAt(x, y))
                    {
                        pixels[y * piece.W + x] = clear;
                        continue;
                    }
                    int col = Mathf.Clamp((int)(x / piece.CellSize), 0, piece.Cells - 1);
                    bool on = piece.Quad == "full"
                        ? pattern[rowTopDown][col]
                        : pattern[rowOffset + rowTopDown][colOffset + col];
                    pixels[y * piece.W + x] = on ? piece.OnColor : piece.OffColor;
                }
            }

            var sprite = SpriteOverlay.CreateRuntimeSprite(pixels, piece.W, piece.H, ppu, "AP_" + key);
            if (sprite != null)
            {
                _spriteCache[key] = sprite;
            }
            return sprite;
        }

        /// <summary>Pattern as [row top-down][col] booleans, from RuneTable's bottom-up pixels.</summary>
        private static bool[][] DecodeTopDown(string patternName)
        {
            var pixels = RuneTable.DecodePixels(patternName);
            if (pixels == null)
            {
                return null;
            }
            var rows = new bool[8][];
            for (int rowTopDown = 0; rowTopDown < 8; rowTopDown++)
            {
                int rowBottomUp = 7 - rowTopDown;
                rows[rowTopDown] = new bool[8];
                for (int col = 0; col < 8; col++)
                {
                    rows[rowTopDown][col] = pixels[rowBottomUp * 8 + col].a > 127;
                }
            }
            return rows;
        }

        private static void DestroyOverlays()
        {
            foreach (var overlay in _overlayByRenderer.Values)
            {
                SpriteOverlay.Destroy(overlay);
            }
            _overlayByRenderer.Clear();
        }
    }
}
