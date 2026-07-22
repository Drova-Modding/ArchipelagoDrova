using ArchipelagoDrova.Data;
using Drova_Modding_API.Access;
using Il2CppDrova.QuestSystem;
using MelonLoader;
using UnityEngine;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Turns quest completion into AP location checks.
    ///
    /// DETECT, primary: the Modding API's GameEvents.OnQuestCompleted (postfix on
    /// AGVar&lt;QuestState&gt;.SetValue when its closed-generic body exists, otherwise the concrete
    /// GQuestStateOperation.OperateIntern fallback).
    /// DETECT, fallback: when the API reports the SetValue hook is NOT active
    /// (GameEvents.QuestSetValueHookActive == false), the OperateIntern fallback misses direct
    /// typed writes, so this polls every <see cref="PollInterval"/> seconds through the API's
    /// safe read path (QuestStateReader - virtual GetGenericValue, never the typed GetValue).
    ///
    /// The catch-up sweep on connect / save load runs through the same safe read path either way.
    /// </summary>
    public static class QuestTracker
    {
        private const float PollInterval = 1f;

        private static ArchipelagoClient _client;
        private static bool _pollActive;
        private static bool _wasConnected;
        private static bool _sweepPending;
        private static float _nextScan;

        private static readonly Dictionary<string, QuestState> LastState = new(StringComparer.Ordinal);
        private static readonly HashSet<string> SentThisSession = new(StringComparer.Ordinal);
        private static readonly HashSet<string> UnmappedLists = new(StringComparer.Ordinal);

        public static void Initialize(ArchipelagoClient archipelagoClient)
        {
            _client = archipelagoClient;

            GameEvents.OnQuestCompleted += OnQuestCompletedEvent;

            _pollActive = !GameEvents.QuestSetValueHookActive;
            MelonLogger.Msg("[AP quest] detection: GameEvents.OnQuestCompleted"
                + (_pollActive ? " + polling every " + PollInterval + "s (SetValue hook not active)" : "")
                + "; " + LocationTable.QuestCount + " quests mapped to AP locations.");
        }

        /// <summary>
        /// Queue the catch-up sweep. Location checks are idempotent by design, so re-sending is safe,
        /// and it is the only way checks completed while disconnected are not lost.
        /// </summary>
        public static void RequestSweep()
        {
            _sweepPending = true;
            LastState.Clear();
            SentThisSession.Clear();
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
            var database = ProviderAccess.GetGameDatabase();
            if (!database)
            {
                return;
            }

            var gvars = database._gvarDatabase;
            if (gvars == null)
            {
                return;
            }

            var lists = gvars.AllGVars;
            if (lists == null)
            {
                return;
            }

            int quests = 0;
            int mapped = 0;
            int completed = 0;

            for (int i = 0; i < lists.Count; i++)
            {
                var list = lists[i];
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

                bool known = LastState.TryGetValue(name, out var previous);
                LastState[name] = state;

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

        private static void OnQuestCompletedEvent(string gvarListName)
        {
            try
            {
                if (string.IsNullOrEmpty(gvarListName))
                {
                    return;
                }
                LastState[gvarListName] = QuestState.IsCompleted;
                Report(gvarListName, "api event");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP quest] OnQuestCompleted handler failed: " + e);
            }
        }

        private static bool Report(string gvarListName, string source)
        {
            if (!LocationTable.TryGetQuest(gvarListName, out string apName))
            {
                if (UnmappedLists.Add(gvarListName))
                {
                    MelonLogger.Msg("[AP quest] '" + gvarListName + "' completed but is not an AP location.");
                }
                return false;
            }

            if (!SentThisSession.Add(apName))
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
                var unityObject = obj.TryCast<UnityEngine.Object>();
                return unityObject ? unityObject.name : null;
            }
            catch
            {
                return null;
            }
        }
    }
}
