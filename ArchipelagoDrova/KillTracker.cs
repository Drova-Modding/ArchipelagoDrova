using HarmonyLib;
using Il2CppDrova;
using MelonLoader;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Turns enemy kills into location checks. Runtime enemy drops can never be Archipelago locations
    /// (they have no identity until they spawn), but a running kill count can: the apworld pre-allocates
    /// N milestone locations ("Enemy Kills - k") and this sends the k-th once the persisted kill count
    /// reaches k * interval.
    ///
    /// Detection is a Harmony postfix on <c>Entity.OnKilledOther</c>, the game's once-per-kill callback
    /// on the killer (its only caller is the _isDead-guarded death block in Health.CheckEvents). Counting
    /// only kills where the killer is the player intrinsically excludes ambient critters, NPC-vs-NPC and
    /// environmental deaths. Kills dealt indirectly (summons, damage-over-time, environment) carry a
    /// non-player source and are not counted; that undercounts rather than breaks, which is acceptable
    /// for a milestone counter.
    /// </summary>
    public static class KillTracker
    {
        private static ArchipelagoClient _client;
        private static ArchipelagoStore _store;

        public static void Initialize(ArchipelagoClient archipelagoClient, ArchipelagoStore archipelagoStore,
            HarmonyLib.Harmony harmony)
        {
            _client = archipelagoClient;
            _store = archipelagoStore;

            HookUtil.TryPostfix(harmony, typeof(Entity), nameof(Entity.OnKilledOther),
                typeof(KillTracker), nameof(OnKilledOtherPostfix));
        }

        /// <summary>
        /// Resend every milestone the current kill count already satisfies. Idempotent: the _client
        /// dedups against the save's checked list and queues names while disconnected, so this is the
        /// catch-up path for a save loaded with kills whose milestones were never sent (feature enabled
        /// mid-playthrough, offline kills, a reconnect). Runs on connect and on save load.
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

        private static void OnKilledOtherPostfix(Entity __instance, HealthChangeArgs changeArgs)
        {
            try
            {
                Actor player = Core.Player;
                if (!player || __instance == null || changeArgs == null)
                {
                    return;
                }

                // The killer is the patched Entity; count only the player's own kills.
                if (__instance.Pointer != player.Pointer)
                {
                    return;
                }

                Health victimHealth = changeArgs.TargetHealth;
                if (!victimHealth)
                {
                    return;
                }

                // A real actor, not a destructible prop, and not the player killing themselves.
                var ownerEntity = victimHealth.OwnerEntity;
                var victim = ownerEntity ? ownerEntity.TryCast<Actor>() : null;
                if (victim == null || victim.IsPlayer)
                {
                    return;
                }

                if (_store == null || _client == null)
                {
                    return;
                }

                int kills = _store.State.EnemyKills + 1;
                _store.State.EnemyKills = kills;
                _client.MarkStatePersistDirty();

                // Fast path: send only the milestone this kill just crossed. SyncMilestones is the
                // safety net for anything this misses (offline, not yet connected, config not in yet).
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
                MelonLogger.Error("[AP kill] OnKilledOther postfix failed: " + e);
            }
        }
    }
}
