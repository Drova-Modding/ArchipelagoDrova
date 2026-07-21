using System.Text;

namespace ArchipelagoDrova.Data
{
    /// <summary>
    /// Lookup helpers over the generated tables in LocationTable.g.cs.
    /// The generated container keys are lowercase-hyphenated guids as read by UnityPy from
    /// GuidComponent._guidString. What that field actually looks like at runtime has never been
    /// observed, so every lookup on both sides goes through <see cref="NormalizeGuid"/>.
    /// </summary>
    public static partial class LocationTable
    {
        private static Dictionary<string, string> _containerIndex;
        private static Dictionary<string, string[]> _containerSlotIndex;
        private static Dictionary<string, string[]> _authoredLootIndex;
        private static Dictionary<string, string> _traderIndex;
        private static Dictionary<string, string[]> _traderUnitIndex;

        public static int ContainerCount
        {
            get { return ContainerGuidToName.Count; }
        }

        public static int QuestCount
        {
            get { return QuestNameToName.Count; }
        }

        public static int TraderSlotCount
        {
            get { return TraderSlotToName.Count; }
        }

        /// <summary>
        /// Fold a guid into the generated table's form (lowercase, hyphenated 8-4-4-4-12).
        /// Accepts hyphenated, unhyphenated, braced and uppercase input.
        /// Returns null when the input does not contain exactly 32 hex digits.
        /// </summary>
        public static string NormalizeGuid(string raw)
        {
            if (string.IsNullOrEmpty(raw))
            {
                return null;
            }

            var hex = new StringBuilder(32);
            for (int i = 0; i < raw.Length; i++)
            {
                char c = raw[i];
                if (c >= '0' && c <= '9')
                {
                    hex.Append(c);
                }
                else if (c >= 'a' && c <= 'f')
                {
                    hex.Append(c);
                }
                else if (c >= 'A' && c <= 'F')
                {
                    hex.Append((char)(c + 32));
                }
                else if (c == '-' || c == '{' || c == '}' || c == ' ')
                {
                    continue;
                }
                else
                {
                    return null;
                }

                if (hex.Length > 32)
                {
                    return null;
                }
            }

            if (hex.Length != 32)
            {
                return null;
            }

            hex.Insert(20, '-');
            hex.Insert(16, '-');
            hex.Insert(12, '-');
            hex.Insert(8, '-');
            return hex.ToString();
        }

        public static bool TryGetContainer(string rawGuid, out string apLocationName)
        {
            apLocationName = null;
            string key = NormalizeGuid(rawGuid);
            if (key == null)
            {
                return false;
            }
            return Containers.TryGetValue(key, out apLocationName);
        }

        /// <summary>
        /// Extra per-item location names for a multi-item container (slots 2..K). The base location
        /// from <see cref="TryGetContainer"/> is slot 1 and is NOT repeated here, so a caller sends
        /// the base name plus every name in this array. Returns false when the container has no
        /// extra slots, which is the overwhelmingly common case.
        /// </summary>
        public static bool TryGetContainerSlots(string rawGuid, out string[] apLocationNames)
        {
            apLocationNames = null;
            string key = NormalizeGuid(rawGuid);
            if (key == null)
            {
                return false;
            }
            return ContainerSlots.TryGetValue(key, out apLocationNames);
        }

        /// <summary>
        /// The authored ("_fixLoot") contents of a randomized container, as "readable_id:amount"
        /// entries. False for containers whose authored contents were never extracted (corpses,
        /// quickloot pickups, random-loot-only chests) - callers fall back to treating the whole
        /// inventory as vanilla loot there.
        /// </summary>
        public static bool TryGetAuthoredLoot(string rawGuid, out string[] entries)
        {
            entries = null;
            string key = NormalizeGuid(rawGuid);
            if (key == null)
            {
                return false;
            }
            return AuthoredLoot.TryGetValue(key, out entries);
        }

        public static bool TryGetQuest(string gvarListName, out string apLocationName)
        {
            apLocationName = null;
            if (string.IsNullOrEmpty(gvarListName))
            {
                return false;
            }
            return QuestNameToName.TryGetValue(gvarListName, out apLocationName);
        }

        /// <summary>
        /// Resolve a bought trader slot to its AP location name. The key is the trader's stable guid and
        /// the item's guid, both normalized, so the runtime pair matches the extracted one regardless of
        /// guid formatting. Returns false when either guid is malformed or the slot is not a location.
        /// </summary>
        public static bool TryGetTraderSlot(string rawTraderGuid, string rawItemGuid, out string apLocationName)
        {
            return TryGetTraderSlot(rawTraderGuid, rawItemGuid, out apLocationName, out _);
        }

        /// <summary>
        /// Overload that also hands back the normalized "traderGuid:itemGuid" slot key, which is the
        /// cursor key for the per-unit purchase counter and for <see cref="GetTraderUnitNames"/>.
        /// </summary>
        public static bool TryGetTraderSlot(string rawTraderGuid, string rawItemGuid,
            out string apLocationName, out string slotKey)
        {
            apLocationName = null;
            slotKey = null;
            string traderKey = NormalizeGuid(rawTraderGuid);
            string itemKey = NormalizeGuid(rawItemGuid);
            if (traderKey == null || itemKey == null)
            {
                return false;
            }
            slotKey = traderKey + ":" + itemKey;
            return TraderSlots.TryGetValue(slotKey, out apLocationName);
        }

        /// <summary>
        /// Extra per-unit location names (units 2..K) for a slot key from
        /// <see cref="TryGetTraderSlot(string, string, out string, out string)"/>. The base location
        /// is unit 1 and not repeated here. Null for the common single-unit slot.
        /// </summary>
        public static string[] GetTraderUnitNames(string slotKey)
        {
            return slotKey != null && TraderUnits.TryGetValue(slotKey, out var names) ? names : null;
        }

        /// <summary>
        /// The generated keys re-normalized, so a stray format in the generator cannot desync the
        /// two sides of the lookup.
        /// </summary>
        private static Dictionary<string, string> Containers
        {
            get
            {
                if (_containerIndex == null)
                {
                    var built = new Dictionary<string, string>(ContainerGuidToName.Count, StringComparer.Ordinal);
                    foreach (var pair in ContainerGuidToName)
                    {
                        string key = NormalizeGuid(pair.Key) ?? pair.Key;
                        built[key] = pair.Value;
                    }
                    _containerIndex = built;
                }
                return _containerIndex;
            }
        }

        /// <summary>Same re-normalization as <see cref="Containers"/> for the extra-slot table.</summary>
        private static Dictionary<string, string[]> ContainerSlots
        {
            get
            {
                if (_containerSlotIndex == null)
                {
                    var built = new Dictionary<string, string[]>(ContainerGuidToSlotNames.Count, StringComparer.Ordinal);
                    foreach (var pair in ContainerGuidToSlotNames)
                    {
                        string key = NormalizeGuid(pair.Key) ?? pair.Key;
                        built[key] = pair.Value;
                    }
                    _containerSlotIndex = built;
                }
                return _containerSlotIndex;
            }
        }

        /// <summary>Same re-normalization as <see cref="Containers"/> for the authored-loot table.</summary>
        private static Dictionary<string, string[]> AuthoredLoot
        {
            get
            {
                if (_authoredLootIndex == null)
                {
                    var built = new Dictionary<string, string[]>(ContainerGuidToAuthoredLoot.Count, StringComparer.Ordinal);
                    foreach (var pair in ContainerGuidToAuthoredLoot)
                    {
                        string key = NormalizeGuid(pair.Key) ?? pair.Key;
                        built[key] = pair.Value;
                    }
                    _authoredLootIndex = built;
                }
                return _authoredLootIndex;
            }
        }

        /// <summary>
        /// The generated trader keys re-normalized half by half ("traderGuid:itemGuid"), so a stray
        /// guid format in the generator cannot desync the two sides of the lookup.
        /// </summary>
        /// <summary>Same half-by-half re-normalization as <see cref="TraderSlots"/> for the unit table.</summary>
        private static Dictionary<string, string[]> TraderUnits
        {
            get
            {
                if (_traderUnitIndex == null)
                {
                    var built = new Dictionary<string, string[]>(TraderSlotToUnitNames.Count, StringComparer.Ordinal);
                    foreach (var pair in TraderSlotToUnitNames)
                    {
                        int split = pair.Key.IndexOf(':');
                        if (split <= 0)
                        {
                            continue;
                        }
                        string traderKey = NormalizeGuid(pair.Key.Substring(0, split));
                        string itemKey = NormalizeGuid(pair.Key.Substring(split + 1));
                        if (traderKey == null || itemKey == null)
                        {
                            continue;
                        }
                        built[traderKey + ":" + itemKey] = pair.Value;
                    }
                    _traderUnitIndex = built;
                }
                return _traderUnitIndex;
            }
        }

        private static Dictionary<string, string> TraderSlots
        {
            get
            {
                if (_traderIndex == null)
                {
                    var built = new Dictionary<string, string>(TraderSlotToName.Count, StringComparer.Ordinal);
                    foreach (var pair in TraderSlotToName)
                    {
                        int split = pair.Key.IndexOf(':');
                        if (split <= 0)
                        {
                            continue;
                        }
                        string traderKey = NormalizeGuid(pair.Key.Substring(0, split));
                        string itemKey = NormalizeGuid(pair.Key.Substring(split + 1));
                        if (traderKey == null || itemKey == null)
                        {
                            continue;
                        }
                        built[traderKey + ":" + itemKey] = pair.Value;
                    }
                    _traderIndex = built;
                }
                return _traderIndex;
            }
        }
    }
}
