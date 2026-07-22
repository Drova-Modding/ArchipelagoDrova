using ArchipelagoDrova.Data;
using Il2CppDrova.GUI;
using MelonLoader;
using UnityEngine;
using UnityEngine.UI;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Shuffles the rune-drawing riddles per the seed's slot data ("runes": original pattern
    /// name -> replacement pattern name).
    ///
    /// A rune door's requirement and its hint note reference the SAME DrawRune_* art (the door's
    /// Interact_Bhvr_RuneDrawing serializes the texture; the note's letter prefab shows the
    /// matching sprite from Atlas_GUI_Notes_Paper), so remapping by that name keeps every riddle
    /// solvable: the note that hints a door always shows whatever the door now requires. Both
    /// choke points come from the Modding API's WindowContentAccess:
    ///  - a drawing-target transformer (GUI_Window_Drawing.SetTargetTexture): every pattern
    ///    check goes through here; the transformer returns a mod-built texture holding the
    ///    replacement pattern's pixels.
    ///  - OnLetterShown (GUI_Window_Letter.ShowLetterContent, the funnel for world letters AND
    ///    journal re-reads): the handler swaps any DrawRune_* Image sprite in the content.
    ///
    /// Textures are rebuilt from RuneTable pixel data rather than borrowed from other puzzle
    /// instances, because the other puzzle's bundle may not be loaded. Pixels are copied
    /// verbatim, so GUI_Window_Drawing.CheckSuccess (per-pixel alpha + RGB comparison) behaves
    /// exactly as it would against the original texture. The PaperChase quest drawing is
    /// Freestyle mode (no target comparison) and is never in the map.
    /// </summary>
    public static class RuneShuffler
    {
        /// <summary>Marks mod-built textures/sprites so a swapped value is never re-swapped.</summary>
        private const string BuiltPrefix = "AP_";

        /// <summary>Original pattern name -> replacement pattern name. Null until configured.</summary>
        private static Dictionary<string, string> _map;

        private static readonly Dictionary<string, Texture2D> BuiltTextures = new();
        private static readonly Dictionary<string, Sprite> BuiltSprites = new();

        public static void Initialize()
        {
            Drova_Modding_API.Access.WindowContentAccess.RegisterDrawingTargetTransformer(TransformDrawingTarget);
            Drova_Modding_API.Access.WindowContentAccess.OnLetterShown += OnLetterShown;
        }

        /// <summary>Called on every connection; empty or null means vanilla riddles.</summary>
        public static void Configure(Dictionary<string, string> map)
        {
            _map = map != null && map.Count > 0 ? new Dictionary<string, string>(map) : null;
            if (_map != null)
            {
                MelonLogger.Msg("Rune shuffle configured: " + _map.Count + " patterns.");
            }
            // The world-art hints (riddle plates, clue stones) follow the same map.
            RuneHintOverlay.Configure(map);
        }

        /// <summary>Returns the replacement texture, or null to keep the vanilla pattern.</summary>
        private static Texture2D TransformDrawingTarget(Texture2D targetTexture)
        {
            try
            {
                if (_map == null || targetTexture == null || targetTexture.name.StartsWith(BuiltPrefix))
                {
                    return null;
                }
                if (_map.TryGetValue(targetTexture.name, out string replacement)
                    && replacement != targetTexture.name)
                {
                    return GetTexture(replacement);
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("Rune target swap failed: " + e);
            }
            return null;
        }

        private static void OnLetterShown(GUI_Window_Letter window)
        {
            try
            {
                if (_map == null || window == null)
                {
                    return;
                }
                foreach (var image in window.GetComponentsInChildren<Image>(true))
                {
                    var sprite = image.sprite;
                    if (sprite == null || sprite.name.StartsWith(BuiltPrefix))
                    {
                        continue;
                    }
                    if (_map.TryGetValue(sprite.name, out string replacement) && replacement != sprite.name)
                    {
                        var built = GetSprite(replacement, sprite.pixelsPerUnit);
                        if (built != null)
                        {
                            image.sprite = built;
                        }
                    }
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("Rune letter swap failed: " + e);
            }
        }

        private static Texture2D GetTexture(string runeName)
        {
            if (BuiltTextures.TryGetValue(runeName, out var cached) && cached != null)
            {
                return cached;
            }

            var pixels = RuneTable.DecodePixels(runeName);
            if (pixels == null)
            {
                MelonLogger.Warning("Rune map names unknown pattern '" + runeName + "'; keeping vanilla.");
                return null;
            }

            var texture = new Texture2D(8, 8, TextureFormat.RGBA32, false)
            {
                name = BuiltPrefix + runeName,
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp,
                // Survive scene loads: these are shared references handed to game windows.
                hideFlags = HideFlags.HideAndDontSave,
            };
            texture.SetPixels32(pixels);
            texture.Apply(false, false);
            BuiltTextures[runeName] = texture;
            return texture;
        }

        private static Sprite GetSprite(string runeName, float pixelsPerUnit)
        {
            if (BuiltSprites.TryGetValue(runeName, out var cached) && cached != null)
            {
                return cached;
            }

            var texture = GetTexture(runeName);
            if (texture == null)
            {
                return null;
            }

            var sprite = Sprite.Create(texture, new Rect(0f, 0f, 8f, 8f), new Vector2(0.5f, 0.5f), pixelsPerUnit);
            sprite.name = BuiltPrefix + runeName;
            sprite.hideFlags = HideFlags.HideAndDontSave;
            BuiltSprites[runeName] = sprite;
            return sprite;
        }
    }
}
