using ArchipelagoDrova.Data;
using Drova_Modding_API.Access;
using Il2CppCustomFramework.Localization;
using Il2CppDrova.Items;
using MelonLoader;
using System.Collections.Generic;
using static Il2CppCustomFramework.Localization.LocalizationDB;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Gives the items the game never named a name, so an Archipelago drop does not arrive as
    /// "[LOCA] Key not found: helmet_ede_bandage_name" or "Id: armor_chest_banshee".
    ///
    /// Vanilla hands none of these out, which is why the gaps went unnoticed: the randomizer
    /// distributes the whole item database, so armor only ever worn by an NPC ends up in the
    /// player's inventory. Both shapes of the gap - a key nobody authored, and an item shipped with
    /// _hasLocalization off - are fixed by pointing the item at a loca path this mod owns and
    /// writing that path's files ourselves.
    ///
    /// Filling the key where it belongs is not an option: a loca path IS a file, so writing one key
    /// into "Items" means overwriting the game's own Items_&lt;lang&gt;.loc and losing the two
    /// thousand entries in it.
    ///
    /// The redirect moves every lookup keyed on Item._locaPath, so ItemLocaTable also carries the
    /// game's rarity and weapon-type text - without it the tooltip's "(Uncommon)" line becomes the
    /// next [LOCA] error.
    /// </summary>
    public static class ItemLocaDefaults
    {
        /// <summary>Written once per process, at the main menu. Repeating it every launch is what
        /// keeps the mirrored rarity text in step with a game update.</summary>
        private static bool _entriesWritten;

        /// <summary>Items already redirected this process. The write lands on the shared asset and
        /// outlives a scene load, but Addressables can drop and rebuild the database, so this is a
        /// fast path rather than a one-shot guard.</summary>
        private static readonly HashSet<string> _redirected = [];

        /// <summary>
        /// Writes ArchipelagoDrova_&lt;lang&gt;.loc into the game's localization folders. Call on the
        /// main menu: the localization database is a resource singleton that does not exist during
        /// melon init, and the files have to be there before the first tooltip is drawn.
        /// </summary>
        public static void WriteLocalizationEntries()
        {
            if (_entriesWritten) return;

            try
            {
                List<LocalizationAccess.LocalizationEntry> entries = [];
                foreach (KeyValuePair<ELanguage, Dictionary<string, string>> language in ItemLocaTable.Entries)
                {
                    foreach (KeyValuePair<string, string> entry in language.Value)
                    {
                        entries.Add(new LocalizationAccess.LocalizationEntry(entry.Key, entry.Value, language.Key));
                    }
                }

                LocalizationAccess.CreateLocalizationEntries(entries, ItemLocaTable.LocaPath);
                _entriesWritten = true;
            }
            catch (Exception e)
            {
                MelonLogger.Error("ItemLocaDefaults.WriteLocalizationEntries failed: " + e);
            }
        }

        /// <summary>
        /// Points the affected items at this mod's loca path. Call once the item database exists,
        /// which it does not before the game manager is up, so this runs on gameplay scene load.
        /// </summary>
        public static void ApplyToItemDatabase()
        {
            try
            {
                if (_redirected.Count == ItemLocaTable.RedirectedItems.Length) return;

                // Redirecting to a path with no file behind it would replace "Id: armor_chest_banshee"
                // with "[LOCA] Loca path not found", which is worse than the problem. The write can
                // fail on an install the player cannot write to, so prove the path resolves first.
                if (!LocaPathIsReadable()) return;

                SubDatabase_Item database = ProviderAccess.ItemDatabase;
                if (database == null) return;

                foreach (string readableId in ItemLocaTable.RedirectedItems)
                {
                    if (_redirected.Contains(readableId)) continue;

                    Item item = database.GetItemByReadableId(readableId);
                    if (!item) continue;

                    // Also sets _hasLocalization, which is the half that matters for the items
                    // shipped with it off: without it the item never asks the database anything.
                    item.SetLocalization(ItemLocaTable.LocaPath);
                    _redirected.Add(readableId);
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("ItemLocaDefaults.ApplyToItemDatabase failed: " + e);
            }
        }

        /// <summary>Whether the active language can actually read this mod's loca path.</summary>
        private static bool LocaPathIsReadable()
        {
            LocalizationDB database = LocalizationDB.Instance;
            if (!database)
            {
                return false;
            }

            // LocaPathExists reports on the file, not the key, but it takes one anyway - and it is
            // the call that loads the file in the first place.
            return database.LocaPathExists(ItemLocaTable.LocaPath, "common", database);
        }
    }
}
