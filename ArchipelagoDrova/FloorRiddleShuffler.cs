using ArchipelagoDrova.Data;
using Drova_Modding_API.Access;
using Il2CppDrova;
using MelonLoader;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Shuffles the library floor riddle per the seed's slot data ("floor_runes": the ordered
    /// stairs sequence, e.g. ["Sound", "Energy", "Summon"]).
    ///
    /// The circle room's FloorRiddleController records the order the five floor runes are struck
    /// in and compares it against two authored sequences when the check pedestal fires: the
    /// stairs sequence (vanilla Energy, Root, Fire - hinted by the clue images of the books
    /// "Geschichte der Runenmagie" I-III) and the secret sequence (Fire, Sound, Summon - hinted
    /// by the ORDER book IV's prose names the rune types in). Only the stairs sequence is
    /// shuffled: its hint is pure imagery, so swapping the three book images keeps it truthful,
    /// while the secret's hint is localized text nobody can swap. The apworld never deals a
    /// stairs sequence equal to the secret one.
    ///
    /// Both swaps are data-only:
    ///  - the controller's serialized stairs Sequence.Elements list is rewritten on scene load
    ///    (sequences are only read when the check variable flips, so mid-riddle timing is safe);
    ///  - OnLetterShown (physical books) and OnJournalLetterShown (journal re-reads - the
    ///    journal builds the same content prefab through its own pane, not GUI_Window_Letter)
    ///    swap the books' GUI_Notes_Library_RuneClue_* Image sprites for art rebuilt from
    ///    FloorClueTable, which also carries the hand-pixeled Sound and Summon clues the game
    ///    never shipped.
    /// </summary>
    public static class FloorRiddleShuffler
    {
        /// <summary>The library interior chunk; the only scene holding a FloorRiddleController.</summary>
        private const string LibraryScene = "Scene_Overworld_Interaction_-2_23";

        /// <summary>Result variable that identifies the stairs sequence on the controller.</summary>
        private const string StairsResultVar = "FloorRuneSolved_Stairs";

        /// <summary>Marks mod-built sprites so a swapped value is never re-swapped.</summary>
        private const string BuiltPrefix = "AP_";

        /// <summary>Book clue sprite name -> its slot in the stairs sequence. RuneClue_2 is the
        /// image of book I (Energy), RuneClue_0 of book II (Root), RuneClue_1 of book III (Fire).</summary>
        private static readonly Dictionary<string, int> ClueSlotBySprite = new()
        {
            { "GUI_Notes_Library_RuneClue_2", 0 },
            { "GUI_Notes_Library_RuneClue_0", 1 },
            { "GUI_Notes_Library_RuneClue_1", 2 },
        };

        /// <summary>The seed's stairs sequence. Null means vanilla.</summary>
        private static string[] _sequence;

        private static readonly Dictionary<string, Sprite> BuiltSprites = new();

        public static void Initialize()
        {
            SceneStreamAccess.AddSceneListener(LibraryScene, OnLibrarySceneLoaded);
            // Physical books and journal re-reads build the same content prefab through two
            // different funnels; both must be swept or a journal re-read shows vanilla clues.
            WindowContentAccess.OnLetterShown += window => SwapClueImages(window);
            // The journal hands over GUI_Journal_EntryController, but its letter content is not
            // among its children: the controller sits on GUI_Journal/Panel/Entries and instantiates
            // the letter prefab into _letterRoot, which is its SIBLING GUI_Journal/Panel/LettersRoot.
            // Walking the controller finds no clue image at all, and silently changes nothing.
            WindowContentAccess.OnJournalLetterShown += controller => SwapClueImages(controller._letterRoot);
        }

        /// <summary>
        /// Called on every connection; null, empty or malformed means vanilla. A vanilla
        /// configure still rewrites an already-loaded library, which undoes a previous room's
        /// shuffle when one session hops between rooms.
        /// </summary>
        public static void Configure(List<string> sequence)
        {
            _sequence = Validate(sequence);
            if (_sequence != null)
            {
                MelonLogger.Msg("Floor riddle shuffle configured: "
                    + string.Join(" -> ", _sequence) + ".");
            }

            var scene = SceneManager.GetSceneByName(LibraryScene);
            if (scene.IsValid() && scene.isLoaded)
            {
                ApplyToScene(scene);
            }
        }

        /// <summary>Returns the sequence as an array, or null when it is absent or unusable.</summary>
        private static string[] Validate(List<string> sequence)
        {
            if (sequence == null || sequence.Count == 0)
            {
                return null;
            }
            if (sequence.Count != FloorClueTable.VanillaSequence.Length
                || sequence.Distinct().Count() != sequence.Count
                || sequence.Any(rune => !FloorClueTable.Generated.ContainsKey(rune)))
            {
                MelonLogger.Warning("Floor riddle slot data is malformed ("
                    + string.Join(", ", sequence) + "); keeping vanilla.");
                return null;
            }
            return [.. sequence];
        }

        private static void OnLibrarySceneLoaded(Scene scene)
        {
            try
            {
                if (_sequence != null)
                {
                    ApplyToScene(scene);
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("Floor riddle scene apply failed: " + e);
            }
        }

        /// <summary>Writes the configured (or, unconfigured, the vanilla) stairs sequence.</summary>
        private static void ApplyToScene(Scene scene)
        {
            string[] order = _sequence ?? FloorClueTable.VanillaSequence;
            foreach (var controller in SceneStreamAccess.GetComponentsInScene<FloorRiddleController>(scene))
            {
                foreach (var sequence in controller._sequences)
                {
                    if (sequence.ResultVar == null || sequence.ResultVar.name != StairsResultVar)
                    {
                        continue;
                    }
                    sequence.Elements.Clear();
                    foreach (string rune in order)
                    {
                        if (!Enum.TryParse(rune, out FloorRiddleController.Element element))
                        {
                            MelonLogger.Error("Floor riddle: unknown element '" + rune + "'.");
                            return;
                        }
                        sequence.Elements.Add(element);
                    }
                    MelonLogger.Msg("Floor riddle stairs sequence set to "
                        + string.Join(" -> ", order) + ".");
                }
            }
        }

        private static void SwapClueImages(Component root)
        {
            try
            {
                if (_sequence == null || root == null)
                {
                    return;
                }
                foreach (var image in root.GetComponentsInChildren<Image>(true))
                {
                    var sprite = image.sprite;
                    if (sprite == null || sprite.name.StartsWith(BuiltPrefix)
                        || !ClueSlotBySprite.TryGetValue(sprite.name, out int slot))
                    {
                        continue;
                    }
                    string rune = _sequence[slot];
                    if (rune == FloorClueTable.VanillaSequence[slot])
                    {
                        continue;
                    }
                    var built = GetSprite(rune, sprite.pixelsPerUnit);
                    if (built != null)
                    {
                        image.sprite = built;
                    }
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("Floor riddle letter swap failed: " + e);
            }
        }

        private static Sprite GetSprite(string runeName, float pixelsPerUnit)
        {
            if (BuiltSprites.TryGetValue(runeName, out var cached) && cached != null)
            {
                return cached;
            }

            var pixels = FloorClueTable.DecodePixels(runeName, out int width, out int height);
            if (pixels == null)
            {
                MelonLogger.Warning("Floor riddle: no clue art for '" + runeName + "'.");
                return null;
            }

            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false)
            {
                name = BuiltPrefix + "FloorClue_" + runeName,
                // The clue art is painterly, not a pixel grid; bilinear matches how the vanilla
                // note atlas renders at letter-window scale.
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                // Survive scene loads: these are shared references handed to game windows.
                hideFlags = HideFlags.HideAndDontSave,
            };
            texture.SetPixels32(pixels);
            texture.Apply(false, false);

            var sprite = Sprite.Create(texture, new Rect(0f, 0f, width, height),
                new Vector2(0.5f, 0.5f), pixelsPerUnit);
            sprite.name = BuiltPrefix + "FloorClue_" + runeName;
            sprite.hideFlags = HideFlags.HideAndDontSave;
            BuiltSprites[runeName] = sprite;
            return sprite;
        }
    }
}
