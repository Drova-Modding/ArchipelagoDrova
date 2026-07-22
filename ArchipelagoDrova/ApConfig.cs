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
