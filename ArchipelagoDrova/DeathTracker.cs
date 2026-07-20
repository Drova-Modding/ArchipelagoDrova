using Archipelago.MultiClient.Net.BounceFeatures.DeathLink;
using Drova_Modding_API.Access;
using HarmonyLib;
using Il2CppDrova;
using MelonLoader;
using UnityEngine;

namespace ArchipelagoDrova
{
    /// <summary>
    /// DeathLink both ways.
    ///
    /// SEND: a Harmony postfix on EntityGameHandler.PlayerActorDiedListener.
    /// Subscribing to PlayerActorDiedEvent directly is NOT possible: its argument
    /// EntityGameHandler.EventArgs&lt;Actor&gt; is a non-blittable struct, and Il2CppInterop's
    /// DelegateSupport.ConvertDelegate rejects those outright. Verified at runtime, not guessed.
    /// The postfix needs no delegate marshaling, so it works where the event cannot.
    ///
    /// RECEIVE: kill through the player's Health. If the player is not loaded and alive, the kill is
    /// deferred rather than dropped.
    /// </summary>
    public static class DeathTracker
    {
        /// <summary>Two deaths cannot legitimately land inside this window; the detectors can.</summary>
        private const float SendDedupeWindow = 2f;

        /// <summary>
        /// The _client's applyingRemoteDeath flag only spans the synchronous OnRemoteDeath invoke.
        /// Drova's death flow may raise PlayerActorDiedEvent a frame or more later, so we hold our own
        /// suppression window over the kill we caused. The window starts when the kill is actually
        /// applied, not when it was queued: a deferred kill (_deathPending) can wait out any fixed
        /// window, e.g. across a loading screen, and _deathPending itself suppresses sends until then.
        /// </summary>
        private const float RemoteKillSuppression = 5f;

        private static ArchipelagoClient _client;

        private static float _lastSendAt = -100f;
        private static float _suppressOwnDeathUntil = -100f;

        private static bool _deathPending;
        private static string _pendingCause;

        public static void Initialize(ArchipelagoClient archipelagoClient, HarmonyLib.Harmony harmony)
        {
            _client = archipelagoClient;
            _client.OnRemoteDeath += OnRemoteDeath;

            HookUtil.TryPostfix(harmony, typeof(EntityGameHandler), nameof(EntityGameHandler.PlayerActorDiedListener),
                typeof(DeathTracker), nameof(PlayerActorDiedListenerPostfix));
        }

        public static void Update()
        {
            try
            {
                if (_deathPending)
                {
                    TryApplyPendingDeath();
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP death] Update failed: " + e);
            }
        }

        // ---------------------------------------------------------------- send

        private static void PlayerActorDiedListenerPostfix()
        {
            try
            {
                ReportOwnDeath("listener");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP death] PlayerActorDiedListener postfix failed: " + e);
            }
        }

        private static void ReportOwnDeath(string source)
        {
            if (_client == null || !_client.DeathLinkEnabled)
            {
                return;
            }

            float now = Time.realtimeSinceStartup;
            // A queued remote kill counts as suppression too: its timed window only starts once the
            // kill is applied (TryApplyPendingDeath), so a death landing while it is still pending
            // is that remote kill (or races with it) and must not echo back out as our own.
            if (_deathPending || now < _suppressOwnDeathUntil)
            {
                return;
            }

            if (now - _lastSendAt < SendDedupeWindow)
            {
                return;
            }
            _lastSendAt = now;

            MelonLogger.Msg("[AP death] player died (" + source + "); broadcasting DeathLink.");
            // The _client also refuses to send it while it is applying a remote death.
            _client.SendDeathLink(_client.SlotName + " fell in Drova.");
        }

        // ---------------------------------------------------------------- receive

        private static void OnRemoteDeath(DeathLink death)
        {
            // Already marshaled onto the main thread by ArchipelagoClient.
            _deathPending = true;
            _pendingCause = death != null ? death.Cause : null;
            TryApplyPendingDeath();
        }

        private static void TryApplyPendingDeath()
        {
            if (!Core.InGameplayScene)
            {
                return;
            }

            // Core.Player comes from PlayerAccess.OnPlayerFound, so it is only set once the actor is
            // initialized. Polling PlayerAccess.GetPlayer() here would throw during bootstrap.
            var player = Core.Player;
            if (!player)
            {
                return;
            }

            var health = player.GetHealth();
            if (!health)
            {
                return;
            }

            if (health.IsDead)
            {
                // Already dead when it arrived: the death is satisfied. Killing them again after the
                // respawn would be a second, unrelated death.
                _deathPending = false;
                MelonLogger.Msg("[AP death] remote DeathLink arrived while already dead; dropping it.");
                return;
            }

            if (!health.IsAlive)
            {
                // Loaded but not yet in a killable state. Keep it pending and retry next frame.
                return;
            }

            // Hand over suppression from the pending flag to the timed window: the grace period
            // starts now, at apply time, no matter how long the kill sat in the queue.
            _deathPending = false;
            _suppressOwnDeathUntil = Time.realtimeSinceStartup + RemoteKillSuppression;

            try
            {
                // CanDieInCombat can otherwise clamp the player at 1 HP instead of killing them.
                health.SetCanDie(true);
                // Disambiguate SetHealthPercent(float, Entity) from SetHealthPercent(float, Action<T>).
                health.SetHealthPercent(0f, (Entity)null);
                MelonLogger.Msg("[AP death] applied remote DeathLink: " + (_pendingCause ?? "no cause given"));
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP death] applying the remote death failed: " + e);
                return;
            }

            if (!health.IsDead)
            {
                // Deliberately not escalating to EndGameOperation.KillPlayer(): that is the scripted
                // bad-end path, and it could load an outro scene, which GoalTracker would read as victory.
                MelonLogger.Warning("[AP death] player survived the DeathLink kill (health clamped?). " +
                    "Not escalating; report this.");
            }
        }
    }
}
