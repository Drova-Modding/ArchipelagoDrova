using Drova_Modding_API.Access;
using Il2CppDrova;
using MelonLoader;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Turns enemy kills into location checks. Runtime enemy drops can never be Archipelago locations
    /// (they have no identity until they spawn), but a running kill count can: the apworld pre-allocates
    /// N milestone locations ("Enemy Kills - k"), and this sends the k-th once the persisted kill count
    /// reaches k * interval.
    ///
    /// Detection is the Modding API's GameEvents.OnPlayerKilledActor (postfix on Entity.OnKilledOther,
    /// the game's once-per-kill callback on the killer). The event already excludes ambient critters,
    /// NPC-vs.-NPC, environmental deaths, destructible props and self-kills. Kills dealt indirectly
    /// (summons, damage-over-time, environment) carry a non-player source and are not counted; that
    /// undercounts rather than breaks, which is acceptable for a milestone counter.
    /// </summary>
    public static class KillTracker
    {
        private static ArchipelagoClient _client;
        private static ArchipelagoStore _store;

        public static void Initialize(ArchipelagoClient archipelagoClient, ArchipelagoStore archipelagoStore)
        {
            _client = archipelagoClient;
            _store = archipelagoStore;

            GameEvents.OnPlayerKilledActor += OnPlayerKilledActor;
        }

        /// <summary>
        /// Resend every milestone the current kill count already satisfies. Idempotent: the _client
        /// dedups against the save's checked list and queues names while disconnected, so this is the
        /// catch-up path for a save loaded with kills whose milestones were never sent (feature-enabled
        /// mid-playthrough, offline kills, a reconnection). Runs on connection and on save load.
        /// </summary>
        public static void SyncMilestones()
        {
            try
            {
                if (_client == null || _store == null)
                {
                    return;
                }

                int reached = MilestonesReached(_store.State.EnemyKills);
                for (int k = 1; k <= reached; k++)
                {
                    _client.CheckLocationByName("Enemy Kills - " + k);
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP kill] SyncMilestones failed: " + e);
            }
        }

        /// <summary>How many milestones a kill count satisfies, capped at the seed's configured count.</summary>
        private static int MilestonesReached(int kills)
        {
            int checks = _client.EnemyKillChecks;
            if (checks <= 0)
            {
                return 0;
            }
            int reached = kills / _client.EnemyKillInterval;
            return reached > checks ? checks : reached;
        }

        private static void OnPlayerKilledActor(Actor victim)
        {
            try
            {
                if (_store == null || _client == null)
                {
                    return;
                }

                int kills = _store.State.EnemyKills + 1;
                _store.State.EnemyKills = kills;
                _client.MarkStatePersistDirty();

                // Fast path: send only the milestone this kill just crossed. SyncMilestones is the
                // safety net for anything this misses (offline, not yet connected, config is not in yet).
                int checks = _client.EnemyKillChecks;
                int interval = _client.EnemyKillInterval;
                if (checks > 0 && interval > 0 && kills % interval == 0)
                {
                    int milestone = kills / interval;
                    if (milestone <= checks)
                    {
                        _client.CheckLocationByName("Enemy Kills - " + milestone);
                    }
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP kill] OnPlayerKilledActor failed: " + e);
            }
        }
    }
}
