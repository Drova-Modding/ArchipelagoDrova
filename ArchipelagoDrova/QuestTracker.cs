using ArchipelagoDrova.Data;
using Drova_Modding_API.Access;
using HarmonyLib;
using Il2CppDrova;
using Il2CppDrova.GlobalVarSystem;
using Il2CppDrova.QuestSystem;
using Il2CppInterop.Common;
using Il2CppInterop.Runtime;
using Il2CppInterop.Runtime.Runtime;
using Il2CppInterop.Runtime.Runtime.VersionSpecific.MethodInfo;
using MelonLoader;
using System.Reflection;
using System.Runtime.InteropServices;
using UnityEngine;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Reads a QuestState without ever touching a closed-generic non-virtual body.
    /// AGVarBase.GetGenericValue is abstract, so IL2CPP must fill the vtable slot on the concrete
    /// GQuestState class: virtual dispatch lands on a body that is guaranteed to exist.
    /// Never touch AGEnum&lt;T&gt;.Comparer / ._operator / ._compare: they are enums nested in an open
    /// generic, and the late-bound static field read throws.
    /// </summary>
    public static class QuestStateReader
    {
        /// <summary>Primary read path. Non-generic on the managed side, virtual on the native side.</summary>
        public static bool TryRead(AGVarBase gvar, out QuestState state)
        {
            state = QuestState.None;
            if (gvar == null)
            {
                return false;
            }

            try
            {
                Il2CppSystem.Object boxed = gvar.GetGenericValue();
                if (boxed == null)
                {
                    return false;
                }

                IntPtr data = IL2CPP.il2cpp_object_unbox(boxed.Pointer);
                if (data == IntPtr.Zero)
                {
                    return false;
                }

                // QuestState.value__ is System.Int32.
                state = (QuestState)Marshal.ReadInt32(data);
                return true;
            }
            catch (Exception e)
            {
                MelonLogger.Warning("[AP quest] GetGenericValue failed: " + e.Message);
                return false;
            }
        }

        /// <summary>
        /// IL2CPP.GetIl2CppMethodByToken does not throw on a body that was never AOT-compiled: it
        /// hands back a fabricated dummy MethodInfo with MethodPointer == 0, and invoking or patching
        /// that can hard-crash instead of raising. Any non-virtual closed-generic proxy method must be
        /// checked here first.
        /// </summary>
        public static unsafe bool HasNativeBody(MethodBase proxyMethod, out string detail)
        {
            detail = "";
            try
            {
                if (proxyMethod == null)
                {
                    detail = "proxy method not found";
                    return false;
                }

                FieldInfo field = Il2CppInteropUtils.GetIl2CppMethodInfoPointerFieldForGeneratedMethod(proxyMethod);
                if (field == null)
                {
                    detail = "no NativeMethodInfoPtr_ field";
                    return false;
                }

                // Reading the field runs the closed generic's cctor, which is itself a thing that can throw.
                IntPtr methodInfo = (IntPtr)field.GetValue(null);
                if (methodInfo == IntPtr.Zero)
                {
                    detail = "MethodInfo* == 0";
                    return false;
                }

                INativeMethodInfoStruct wrapped = UnityVersionHandler.Wrap((Il2CppMethodInfo*)methodInfo);
                IntPtr body = wrapped.MethodPointer;
                detail = "MethodInfo*=0x" + methodInfo.ToInt64().ToString("X") + " body=0x" + body.ToInt64().ToString("X");
                return body != IntPtr.Zero;
            }
            catch (Exception e)
            {
                detail = e.GetType().Name + ": " + e.Message;
                return false;
            }
        }
    }

    /// <summary>
    /// Turns quest completion into AP location checks.
    ///
    /// DETECT, primary: Harmony postfix on AGVar&lt;QuestState&gt;.SetValue, gated on a preflight that
    /// proves the closed-generic body exists. SetValue is the right chokepoint: SetGenericValue
    /// delegates down to it, so patching it catches typed and generic writes alike.
    /// DETECT, fallback: poll every <see cref="PollInterval"/> seconds through the safe read path.
    /// The fallback is structurally immune to the missing-body problem, so it is what runs whenever
    /// the preflight is not conclusive.
    ///
    /// READ: always QuestStateReader.TryRead (virtual GetGenericValue). The typed
    /// AGVar&lt;QuestState&gt;.GetValue is never called.
    /// </summary>
    public static class QuestTracker
    {
        private const float PollInterval = 1f;

        private static ArchipelagoClient _client;
        private static bool _patchActive;
        private static bool _pollActive;
        private static bool _wasConnected;
        private static bool _sweepPending;
        private static float _nextScan;

        private static readonly Dictionary<string, QuestState> _lastState = new Dictionary<string, QuestState>(StringComparer.Ordinal);
        private static readonly HashSet<string> _sentThisSession = new HashSet<string>(StringComparer.Ordinal);
        private static readonly HashSet<string> _unmappedLists = new HashSet<string>(StringComparer.Ordinal);

        public static void Initialize(ArchipelagoClient archipelagoClient, HarmonyLib.Harmony harmony)
        {
            _client = archipelagoClient;

            MethodBase setValue = null;
            string detail = "could not resolve AGVar<QuestState>.SetValue";
            try
            {
                setValue = AccessTools.Method(typeof(AGVar<QuestState>), nameof(AGVar<QuestState>.SetValue));
            }
            catch (Exception e)
            {
                detail = "resolving AGVar<QuestState>.SetValue threw: " + e.Message;
            }

            bool viable = setValue != null && QuestStateReader.HasNativeBody(setValue, out detail);

            MelonLogger.Msg("==================================================================");
            MelonLogger.Msg(" AP quest detection preflight: AGVar<QuestState>.SetValue -> " +
                (viable ? "BODY PRESENT" : "UNUSABLE"));
            MelonLogger.Msg("   " + detail);

            if (viable)
            {
                _patchActive = HookUtil.TryPostfix(harmony, setValue, typeof(QuestTracker),
                    nameof(SetValuePostfix), "AGVar<QuestState>.SetValue");
            }

            if (!_patchActive)
            {
                _pollActive = true;
                MelonLogger.Msg(" Quest detection: POLLING every " + PollInterval + "s (safe read path).");
            }
            else
            {
                MelonLogger.Msg(" Quest detection: Harmony postfix on AGVar<QuestState>.SetValue.");
            }
            MelonLogger.Msg("==================================================================");

            // Concrete, non-generic, always patchable. Free supplementary signal for quest-graph and
            // dialogue driven writes; costs nothing if the SetValue patch already covers them.
            HookUtil.TryPostfix(harmony, typeof(GQuestStateOperation), nameof(GQuestStateOperation.OperateIntern),
                typeof(QuestTracker), nameof(OperateInternPostfix));

            MelonLogger.Msg("[AP quest] " + LocationTable.QuestCount + " quests mapped to AP locations.");
        }

        /// <summary>
        /// Queue the catch-up sweep. Location checks are idempotent by design, so re-sending is safe,
        /// and it is the only way checks completed while disconnected are not lost.
        /// </summary>
        public static void RequestSweep()
        {
            _sweepPending = true;
            _lastState.Clear();
            _sentThisSession.Clear();
        }

        public static void Update()
        {
            try
            {
                bool connected = _client != null && _client.Connected;
                if (connected && !_wasConnected)
                {
                    RequestSweep();
                }
                _wasConnected = connected;

                if (!_pollActive && !_sweepPending)
                {
                    return;
                }

                if (Time.realtimeSinceStartup < _nextScan)
                {
                    return;
                }
                _nextScan = Time.realtimeSinceStartup + PollInterval;

                if (!Core.InGameplayScene || !connected)
                {
                    return;
                }

                Scan(_sweepPending);
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP quest] Update failed: " + e);
            }
        }

        /// <summary>
        /// Walks every quest var list through the safe read path.
        /// catchUp fires for anything already completed and seeds the transition cache;
        /// otherwise only a transition into IsCompleted fires.
        /// </summary>
        private static void Scan(bool catchUp)
        {
            GameDatabase database = ProviderAccess.GetGameDatabase();
            if (!database)
            {
                return;
            }

            SubDatabase_GVars gvars = database._gvarDatabase;
            if (gvars == null)
            {
                return;
            }

            Il2CppSystem.Collections.Generic.List<GVarList> lists = gvars.AllGVars;
            if (lists == null)
            {
                return;
            }

            int quests = 0;
            int mapped = 0;
            int completed = 0;

            for (int i = 0; i < lists.Count; i++)
            {
                GVarList list = lists[i];
                if (!list || !list.IsQuestVarList)
                {
                    continue;
                }

                quests++;
                string name = SafeName(list);
                if (name == null)
                {
                    continue;
                }

                if (!QuestStateReader.TryRead(list.GetQuestState(), out var state))
                {
                    continue;
                }

                bool known = _lastState.TryGetValue(name, out var previous);
                _lastState[name] = state;

                if (state != QuestState.IsCompleted)
                {
                    continue;
                }

                completed++;
                if (catchUp || !known || previous != QuestState.IsCompleted)
                {
                    if (Report(name, "scan"))
                    {
                        mapped++;
                    }
                }
            }

            if (catchUp && quests > 0)
            {
                _sweepPending = false;
                MelonLogger.Msg("[AP quest] catch-up sweep: " + quests + " quest lists, " + completed +
                    " completed, " + mapped + " sent as AP checks.");
                if (completed > 0 && mapped == 0)
                {
                    MelonLogger.Warning("[AP quest] no completed quest matched LocationTable.QuestNameToName. " +
                        "The GVarList name format probably differs from the generated keys.");
                }
            }
        }

        /// <summary>
        /// Primary detector. Mirrors the shipping Drova Modding API AGvarBoolPatch on AGVar&lt;bool&gt;;
        /// bool and enum only diverge inside Il2CppClassPointerStore, everything downstream is identical.
        /// The parameter name 't' must match the proxy signature.
        /// </summary>
        private static void SetValuePostfix(QuestState t, AGVar<QuestState> __instance)
        {
            try
            {
                if (t != QuestState.IsCompleted || __instance == null)
                {
                    return;
                }

                // Rejects foreign instances should identical-COMDAT-folding have merged this native
                // body with another int-backed enum instantiation.
                if (__instance.TryCast<GQuestState>() == null)
                {
                    return;
                }

                OnCompleted(__instance.Cast<AGVarBase>(), "SetValue");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP quest] SetValue postfix failed: " + e);
            }
        }

        /// <summary>Supplementary detector on the concrete non-generic operation node.</summary>
        private static void OperateInternPostfix(GQuestState variable, QuestState value)
        {
            try
            {
                if (value != QuestState.IsCompleted || variable == null)
                {
                    return;
                }
                OnCompleted(variable.Cast<AGVarBase>(), "OperateIntern");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP quest] OperateIntern postfix failed: " + e);
            }
        }

        private static void OnCompleted(AGVarBase gvar, string source)
        {
            GVarList parent = gvar.GetParent();
            if (!parent)
            {
                return;
            }

            string name = SafeName(parent);
            if (name == null)
            {
                return;
            }

            _lastState[name] = QuestState.IsCompleted;
            Report(name, source);
        }

        private static bool Report(string gvarListName, string source)
        {
            if (!LocationTable.TryGetQuest(gvarListName, out string apName))
            {
                if (_unmappedLists.Add(gvarListName))
                {
                    MelonLogger.Msg("[AP quest] '" + gvarListName + "' completed but is not an AP location.");
                }
                return false;
            }

            if (!_sentThisSession.Add(apName))
            {
                return true;
            }

            MelonLogger.Msg("[AP quest] " + gvarListName + " completed (" + source + ") -> '" + apName + "'.");
            _client.CheckLocationByName(apName);
            return true;
        }

        private static string SafeName(Il2CppSystem.Object obj)
        {
            try
            {
                UnityEngine.Object unityObject = obj.TryCast<UnityEngine.Object>();
                return unityObject ? unityObject.name : null;
            }
            catch
            {
                return null;
            }
        }
    }
}
