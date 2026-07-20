using HarmonyLib;
using Il2CppDrova;
using Il2CppDrova.GUI.LearnGUI;
using Il2CppDrova.Talent;
using MelonLoader;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Turns teacher learning into milestone location checks, the KillTracker model: the apworld
    /// pre-allocates "Attributes Learned - k" / "Talents Learned - k" and this sends the k-th once
    /// the persisted counter reaches k.
    ///
    /// Attribute points: postfix on LearnService.ApplyData, the teacher menu's single commit point.
    /// Its _totalStatsChanged field is the net points bought in that session (undo clicks inside the
    /// menu cancel out). The sleep-menu level-up allocation, perma-potions and the AP stat items all
    /// go through other paths and never count.
    ///
    /// Talents: prefix/postfix pair on TalentActorModule.LearnTalent, whose only callers are the
    /// teacher menu, dialogue-taught talents and LearnUtil - all genuine teaching. The AP item
    /// grants use ForceLearnTalent and never count. The prefix snapshots CanLearnTalent because
    /// LearnTalent silently no-ops on an already-known talent, and a no-op must not count.
    /// </summary>
    public static class LearnTracker
    {
        private static ArchipelagoClient _client;
        private static ArchipelagoStore _store;

        // Set by the LearnTalent prefix when the call will actually learn something; consumed by
        // the postfix. Main-thread only, no reentry: LearnTalent does not call itself.
        private static bool _pendingTalentLearn;

        // ApplyData is once-per-confirm on a per-menu service instance; remembering the last
        // handled instance makes a double invocation harmless.
        private static IntPtr _lastServiceHandled = IntPtr.Zero;

        public static void Initialize(ArchipelagoClient archipelagoClient, ArchipelagoStore archipelagoStore,
            HarmonyLib.Harmony harmony)
        {
            _client = archipelagoClient;
            _store = archipelagoStore;

            HookUtil.TryPostfix(harmony, typeof(LearnService), nameof(LearnService.ApplyData),
                typeof(LearnTracker), nameof(ApplyDataPostfix));
            HookUtil.TryPrefix(harmony, typeof(TalentActorModule), nameof(TalentActorModule.LearnTalent),
                typeof(LearnTracker), nameof(LearnTalentPrefix));
            HookUtil.TryPostfix(harmony, typeof(TalentActorModule), nameof(TalentActorModule.LearnTalent),
                typeof(LearnTracker), nameof(LearnTalentPostfix));
        }

        /// <summary>
        /// Resend every milestone the persisted counters already satisfy. Idempotent (the client
        /// dedups and queues offline); the catch-up path for saves with learning that predates the
        /// feature or happened offline. Runs on connect and on save load.
        /// </summary>
        public static void SyncMilestones()
        {
            try
            {
                if (_client == null || _store == null)
                {
                    return;
                }
                SendUpTo("Attributes Learned - ",
                    _store.State.AttributesLearned / _client.AttributeLearnInterval, _client.AttributeLearnChecks);
                SendUpTo("Talents Learned - ", _store.State.TalentsLearned, _client.TalentLearnChecks);
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP learn] SyncMilestones failed: " + e);
            }
        }

        private static void SendUpTo(string prefix, int count, int checks)
        {
            int reached = count < checks ? count : checks;
            for (int k = 1; k <= reached; k++)
            {
                _client.CheckLocationByName(prefix + k);
            }
        }

        private static void ApplyDataPostfix(LearnService __instance)
        {
            try
            {
                if (__instance == null || _store == null || _client == null)
                {
                    return;
                }
                if (__instance.Pointer == _lastServiceHandled)
                {
                    return;
                }
                _lastServiceHandled = __instance.Pointer;

                int learned = __instance._totalStatsChanged;
                if (learned <= 0)
                {
                    return;
                }

                int before = _store.State.AttributesLearned;
                int total = before + learned;
                _store.State.AttributesLearned = total;
                _client.MarkStatePersistDirty();
                MelonLogger.Msg("[AP learn] " + learned + " attribute point(s) learned at a teacher (total "
                    + total + ").");

                // Milestone k fires at k * interval points, like the kill milestones. One teacher
                // session can cross several milestones at once.
                int checks = _client.AttributeLearnChecks;
                int interval = _client.AttributeLearnInterval;
                for (int k = before / interval + 1; k <= total / interval && k <= checks; k++)
                {
                    _client.CheckLocationByName("Attributes Learned - " + k);
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP learn] ApplyData postfix failed: " + e);
            }
        }

        private static void LearnTalentPrefix(TalentActorModule __instance, TalentContainer container)
        {
            _pendingTalentLearn = false;
            try
            {
                if (__instance == null || container == null)
                {
                    return;
                }
                var actor = __instance.GetActor();
                if (actor == null || !actor.IsPlayer)
                {
                    return;
                }
                _pendingTalentLearn = __instance.CanLearnTalent(container.GUID);
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP learn] LearnTalent prefix failed: " + e);
            }
        }

        private static void LearnTalentPostfix()
        {
            try
            {
                if (!_pendingTalentLearn)
                {
                    return;
                }
                _pendingTalentLearn = false;

                if (_store == null || _client == null)
                {
                    return;
                }

                int total = _store.State.TalentsLearned + 1;
                _store.State.TalentsLearned = total;
                _client.MarkStatePersistDirty();
                MelonLogger.Msg("[AP learn] talent learned (total " + total + ").");

                if (total <= _client.TalentLearnChecks)
                {
                    _client.CheckLocationByName("Talents Learned - " + total);
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP learn] LearnTalent postfix failed: " + e);
            }
        }
    }
}
