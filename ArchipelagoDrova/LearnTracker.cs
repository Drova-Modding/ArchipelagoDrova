using Drova_Modding_API.Access;
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
    /// Detection is the Modding API's GameEvents: OnAttributePointsLearned (LearnService.ApplyData,
    /// the teacher menu's single commit point - net points per session, already deduped per menu
    /// instance; the sleep-menu level-up allocation, perma-potions and the AP stat items go through
    /// other paths and never fire) and OnTalentLearned (TalentActorModule.LearnTalent with the
    /// no-op-on-known filter; the AP item grants use ForceLearnTalent and never fire). The talent
    /// event reports any actor, so the player filter lives here.
    /// </summary>
    public static class LearnTracker
    {
        private static ArchipelagoClient _client;
        private static ArchipelagoStore _store;

        public static void Initialize(ArchipelagoClient archipelagoClient, ArchipelagoStore archipelagoStore)
        {
            _client = archipelagoClient;
            _store = archipelagoStore;

            GameEvents.OnAttributePointsLearned += OnAttributePointsLearned;
            GameEvents.OnTalentLearned += OnTalentLearned;
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

        private static void OnAttributePointsLearned(LearnService service, int learned)
        {
            try
            {
                if (_store == null || _client == null)
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
                MelonLogger.Error("[AP learn] OnAttributePointsLearned failed: " + e);
            }
        }

        private static void OnTalentLearned(Actor actor, TalentContainer container)
        {
            try
            {
                if (_store == null || _client == null || actor == null || !actor.IsPlayer)
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
                MelonLogger.Error("[AP learn] OnTalentLearned failed: " + e);
            }
        }
    }
}
