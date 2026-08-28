using Archipelago.MultiClient.Net.BounceFeatures.DeathLink;
using Il2CppDrova;
using Il2CppDrova.Brawl;
using MelonLoader;
using UnityEngine;

namespace ArchipelagoDrova
{
    /// <summary>What an incoming DeathLink does to the player. Seed-controlled; see ApConfig.</summary>
    public enum DeathLinkMode
    {
        /// <summary>Kill them. Drova's only death penalty is reloading the last save, which is the
        /// whole problem in a co-op room: everything since that save is gone, quest state included.</summary>
        Kill,

        /// <summary>Put them down for a few seconds instead, the way losing a brawl does. Nothing
        /// reloads, so nothing is lost.</summary>
        Knockout,
    }

    /// <summary>
    /// DeathLink both ways.
    ///
    /// SEND: the Modding API's GameEvents.OnPlayerDied (its postfix exists because the game's
    /// PlayerActorDiedEvent takes a non-blittable struct that delegate marshaling rejects).
    ///
    /// RECEIVE: kill through the player's Health, or - in <see cref="DeathLinkMode.Knockout"/> - the
    /// game's own brawl knockout. If the player is not loaded and alive, either is deferred rather
    /// than dropped.
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

        /// <summary>What an incoming death does here. Set from slot data on connect (ArchipelagoClient).</summary>
        public static DeathLinkMode Mode { get; set; } = DeathLinkMode.Kill;

        /// <summary>How long a knockout keeps the player down. Local, from config.json.</summary>
        public static float KnockoutSeconds { get; set; } = 6f;

        /// <summary>
        /// Health fraction the player is left on by a knockout, or 0 to leave their health alone.
        /// Local, from config.json. Never kills: a knocked-out actor cannot be hit either, so this is
        /// a penalty you feel after standing up, not a second death.
        /// </summary>
        public static float KnockoutHealthPercent { get; set; }

        private static float _lastSendAt = -100f;
        private static float _suppressOwnDeathUntil = -100f;

        private static bool _deathPending;
        private static string _pendingCause;

        // The brawl wrapper is reused for as long as the player actor is the same one: its constructor
        // subscribes to the actor's HealthChangedEvent and RemoveKnockout never unsubscribes, so a new
        // wrapper per DeathLink would pile listeners onto the player.
        private static BrawlActor _brawl;
        private static Actor _brawlOwner;
        private static bool _knockedOut;
        private static float _wakeAt;

        public static void Initialize(ArchipelagoClient archipelagoClient)
        {
            _client = archipelagoClient;
            _client.OnRemoteDeath += OnRemoteDeath;

            Drova_Modding_API.Access.GameEvents.OnPlayerDied += OnPlayerDiedEvent;
        }

        public static void Update()
        {
            try
            {
                if (_deathPending)
                {
                    TryApplyPendingDeath();
                }

                UpdateKnockout();
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP death] Update failed: " + e);
            }
        }

        // ---------------------------------------------------------------- send

        private static void OnPlayerDiedEvent()
        {
            try
            {
                ReportOwnDeath("api event");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP death] OnPlayerDied handler failed: " + e);
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
            // Already marshalled onto the main thread by ArchipelagoClient.
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
            // initialised. Polling PlayerAccess.GetPlayer() here would throw during bootstrap.
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

            if (Mode == DeathLinkMode.Knockout)
            {
                // No death, so nothing to suppress on the way out: the send path only ever fires on a
                // real death, and a knockout is not one.
                _deathPending = false;
                ApplyKnockout(player);
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

        // ---------------------------------------------------------------- knockout

        /// <summary>
        /// Put the player down instead of killing them: exactly the state losing a brawl leaves them in
        /// (input blocked, AI and queued actions stopped, hit collider off - so they cannot be finished
        /// off while helpless), lifted again by <see cref="UpdateKnockout"/>. Nothing reloads, so items
        /// received since the last save survive, which is the point of the mode.
        /// </summary>
        private static void ApplyKnockout(Actor player)
        {
            if (_knockedOut)
            {
                // Already down through us: extend instead of restarting, so a burst of DeathLinks is one
                // blackout rather than a stutter of stand-ups.
                _wakeAt = Math.Max(_wakeAt, Time.realtimeSinceStartup + KnockoutSeconds);
                return;
            }

            try
            {
                // A knockout the game itself started (a brawl, a scripted defeat) owns the player's
                // state and ends it through its own service. Stacking ours on top would give the
                // stand-up two owners, so treat the DeathLink as already served.
                if (player.CustomStats != null && player.CustomStats.IsKnockout)
                {
                    MelonLogger.Msg("[AP death] remote DeathLink arrived during a knockout; dropping it.");
                    return;
                }

                if (_brawl == null || _brawlOwner != player)
                {
                    _brawl = new BrawlActor(player);
                    _brawlOwner = player;
                }

                // Armed before the call, not after: Knockout() blocks input as its very first step, so
                // a throw halfway through would otherwise leave the player blocked with no timer left
                // to stand them back up.
                _knockedOut = true;
                _wakeAt = Time.realtimeSinceStartup + KnockoutSeconds;
                _brawl.Knockout();

                if (KnockoutHealthPercent > 0f)
                {
                    // Same overload disambiguation as the kill path.
                    player.GetHealth().SetHealthPercent(KnockoutHealthPercent, (Entity)null);
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP death] applying the remote knockout failed: " + e);
                return;
            }

            MelonLogger.Msg("[AP death] knocked out by remote DeathLink: " + (_pendingCause ?? "no cause given"));
            Core.Ui?.AddToast("DeathLink: knocked out (" + (_pendingCause ?? "no cause given") + ")");
        }

        /// <summary>Stands the player back up once their time is served, or drops the knockout when the
        /// actor it belongs to is gone (save load, main menu) and its input block died with it.</summary>
        private static void UpdateKnockout()
        {
            if (!_knockedOut)
            {
                return;
            }

            if (!Core.InGameplayScene || !Core.Player || Core.Player != _brawlOwner)
            {
                _knockedOut = false;
                _brawl = null;
                _brawlOwner = null;
                return;
            }

            if (Time.realtimeSinceStartup < _wakeAt)
            {
                return;
            }

            _knockedOut = false;
            try
            {
                _brawl.RemoveKnockout();
                MelonLogger.Msg("[AP death] knockout over; player is back up.");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP death] ending the knockout failed: " + e);
            }
        }
    }
}
