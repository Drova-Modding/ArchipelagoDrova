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
        private static Dictionary<string, string> _traderIndex;

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

            StringBuilder hex = new StringBuilder(32);
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
            apLocationName = null;
            string traderKey = NormalizeGuid(rawTraderGuid);
            string itemKey = NormalizeGuid(rawItemGuid);
            if (traderKey == null || itemKey == null)
            {
                return false;
            }
            return TraderSlots.TryGetValue(traderKey + ":" + itemKey, out apLocationName);
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
                    Dictionary<string, string> built = new Dictionary<string, string>(ContainerGuidToName.Count, StringComparer.Ordinal);
                    foreach (KeyValuePair<string, string> pair in ContainerGuidToName)
                    {
                        string key = NormalizeGuid(pair.Key) ?? pair.Key;
                        built[key] = pair.Value;
                    }
                    _containerIndex = built;
                }
                return _containerIndex;
            }
        }

        /// <summary>
        /// The generated trader keys re-normalized half by half ("traderGuid:itemGuid"), so a stray
        /// guid format in the generator cannot desync the two sides of the lookup.
        /// </summary>
        private static Dictionary<string, string> TraderSlots
        {
            get
            {
                if (_traderIndex == null)
                {
                    Dictionary<string, string> built = new Dictionary<string, string>(TraderSlotToName.Count, StringComparer.Ordinal);
                    foreach (KeyValuePair<string, string> pair in TraderSlotToName)
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
