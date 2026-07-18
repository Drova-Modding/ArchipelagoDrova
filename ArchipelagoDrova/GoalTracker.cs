using HarmonyLib;
using Il2CppDrova;
using MelonLoader;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Sends the AP goal when the game loads an outro scene.
    /// Drova has good and bad endings (the outro SFX carry _Good/_Bad variants); v1 treats any outro
    /// as the goal, so both Scene_Outro_Lore and Scene_Outro_Credits count.
    /// The _client already guards on ApState.GoalSent, so this only has to fire.
    /// </summary>
    public static class GoalTracker
    {
        private const string OutroScenePrefix = "Scene_Outro";

        private static ArchipelagoClient _client;

        public static void Initialize(ArchipelagoClient archipelagoClient, HarmonyLib.Harmony harmony)
        {
            _client = archipelagoClient;

            // Prefix rather than postfix: the goal should be recorded on intent, before the scene swap
            // tears anything down.
            HookUtil.TryPrefix(harmony, typeof(SceneGameHandler), nameof(SceneGameHandler.ActuallyChangeScene),
                typeof(GoalTracker), nameof(ActuallyChangeScenePrefix));
        }

        private static void ActuallyChangeScenePrefix(string sceneName)
        {
            try
            {
                if (string.IsNullOrEmpty(sceneName))
                {
                    return;
                }

                if (!sceneName.StartsWith(OutroScenePrefix, StringComparison.OrdinalIgnoreCase))
                {
                    return;
                }

                MelonLogger.Msg("[AP goal] outro scene '" + sceneName + "' reached; sending the goal.");
                _client.SendGoal();
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP goal] ActuallyChangeScene prefix failed: " + e);
            }
        }
    }
}
