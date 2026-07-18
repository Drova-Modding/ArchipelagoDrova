using HarmonyLib;
using MelonLoader;
using System.Reflection;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Applies every Harmony patch by hand.
    /// We deliberately use no [HarmonyPatch] attributes: MelonLoader auto-applies those at melon
    /// registration, which would (a) defeat the runtime preflight that has to gate the
    /// AGVar&lt;QuestState&gt; patch and (b) make one bad target take the whole set down with it.
    /// Patching one target at a time also gives an honest per-hook line in the log.
    /// </summary>
    public static class HookUtil
    {
        public static bool TryPostfix(HarmonyLib.Harmony harmony, Type targetType, string targetMethod, Type patchType, string patchMethod)
        {
            MethodInfo target = FindTarget(targetType, targetMethod);
            if (target == null)
            {
                return false;
            }
            return Apply(harmony, target, patchType, patchMethod, false, Label(targetType, targetMethod));
        }

        public static bool TryPrefix(HarmonyLib.Harmony harmony, Type targetType, string targetMethod, Type patchType, string patchMethod)
        {
            MethodInfo target = FindTarget(targetType, targetMethod);
            if (target == null)
            {
                return false;
            }
            return Apply(harmony, target, patchType, patchMethod, true, Label(targetType, targetMethod));
        }

        /// <summary>Overload for targets the caller already resolved and preflighted.</summary>
        public static bool TryPostfix(HarmonyLib.Harmony harmony, MethodBase target, Type patchType, string patchMethod, string label)
        {
            if (target == null)
            {
                MelonLogger.Error("[AP hook] no target for " + label + "; hook disabled.");
                return false;
            }
            return Apply(harmony, target, patchType, patchMethod, false, label);
        }

        private static MethodInfo FindTarget(Type targetType, string targetMethod)
        {
            try
            {
                MethodInfo target = AccessTools.Method(targetType, targetMethod);
                if (target == null)
                {
                    MelonLogger.Error("[AP hook] target method not found: " + Label(targetType, targetMethod) + "; hook disabled.");
                }
                return target;
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP hook] resolving " + Label(targetType, targetMethod) + " threw: " + e);
                return null;
            }
        }

        private static bool Apply(HarmonyLib.Harmony harmony, MethodBase target, Type patchType, string patchMethod, bool asPrefix, string label)
        {
            try
            {
                MethodInfo patch = AccessTools.Method(patchType, patchMethod);
                if (patch == null)
                {
                    MelonLogger.Error("[AP hook] patch method " + patchType.Name + "." + patchMethod + " not found; " + label + " disabled.");
                    return false;
                }

                HarmonyMethod wrapped = new HarmonyMethod(patch);
                if (asPrefix)
                {
                    harmony.Patch(target, prefix: wrapped);
                }
                else
                {
                    harmony.Patch(target, postfix: wrapped);
                }

                MelonLogger.Msg("[AP hook] " + (asPrefix ? "prefix" : "postfix") + " -> " + label);
                return true;
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP hook] FAILED to patch " + label + ": " + e);
                return false;
            }
        }

        private static string Label(Type targetType, string targetMethod)
        {
            return targetType.Name + "." + targetMethod;
        }
    }
}
