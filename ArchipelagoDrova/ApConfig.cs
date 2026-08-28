using MelonLoader;
using MelonLoader.Utils;
using Newtonsoft.Json;

namespace ArchipelagoDrova
{
    /// <summary>
    /// JSON config stored at &lt;game&gt;/UserData/ArchipelagoDrova/config.json.
    /// </summary>
    public class ApConfig
    {
        public string Host { get; set; } = "archipelago.gg";
        public int Port { get; set; } = 38281;
        public string SlotName { get; set; } = "";
        public string Password { get; set; } = "";
        public bool AutoConnect { get; set; }
        public bool DeathLink { get; set; } = false;

        /// <summary>
        /// Force incoming DeathLinks to knock the player out instead of killing them, whatever the seed
        /// asked for. One-way on purpose: a local setting may soften a seed's DeathLink, never sharpen it,
        /// so a room that agreed on knockouts cannot be turned back into kills from one player's config.
        /// </summary>
        public bool DeathLinkKnockout { get; set; } = false;

        /// <summary>Seconds a DeathLink knockout keeps the player down.</summary>
        public float DeathLinkKnockoutSeconds { get; set; } = 6f;

        /// <summary>
        /// Health fraction a DeathLink knockout leaves the player on (0.1 = 10%), or 0 to leave their
        /// health alone. It cannot kill: a knocked-out actor takes no hits either.
        /// </summary>
        public float DeathLinkKnockoutHealthPercent { get; set; } = 0f;

        public static string DataDirectory => Path.Combine(MelonEnvironment.UserDataDirectory, "ArchipelagoDrova");

        public static string FilePath => Path.Combine(DataDirectory, "config.json");

        public static ApConfig Load()
        {
            try
            {
                Directory.CreateDirectory(DataDirectory);
                if (!File.Exists(FilePath))
                {
                    var created = new ApConfig();
                    created.Save();
                    return created;
                }

                string json = File.ReadAllText(FilePath);
                var loaded = JsonConvert.DeserializeObject<ApConfig>(json);
                if (loaded == null)
                {
                    MelonLogger.Warning("config.json was empty or invalid; using defaults.");
                    return new ApConfig();
                }
                return loaded;
            }
            catch (Exception e)
            {
                MelonLogger.Error("Failed to load config.json, using defaults: " + e);
                return new ApConfig();
            }
        }

        public void Save()
        {
            try
            {
                Directory.CreateDirectory(DataDirectory);
                File.WriteAllText(FilePath, JsonConvert.SerializeObject(this, Formatting.Indented));
            }
            catch (Exception e)
            {
                MelonLogger.Error("Failed to save config.json: " + e);
            }
        }
    }
}
