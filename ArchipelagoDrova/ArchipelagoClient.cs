using Archipelago.MultiClient.Net;
using Archipelago.MultiClient.Net.BounceFeatures.DeathLink;
using Archipelago.MultiClient.Net.Enums;
using Archipelago.MultiClient.Net.Helpers;
using Archipelago.MultiClient.Net.MessageLog.Messages;
using Archipelago.MultiClient.Net.Models;
using Drova_Modding_API.Systems;
using MelonLoader;
using System.Collections.ObjectModel;
using UnityEngine;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Owns the Archipelago _session. Every library callback arrives on a ThreadPool thread and is
    /// marshalled onto the Unity main thread through <see cref="MainThreadDispatcher"/>.
    /// </summary>
    public class ArchipelagoClient
    {
        public const string GameName = "Drova - Forsaken Kin";

        private const float MaxReconnectDelay = 60f;
        private const float PendingFlushRetryInterval = 30f;

        private readonly ApConfig _config;
        private readonly ArchipelagoStore _store;
        private readonly IItemGranter _granter;

        // Typed as the concrete _session: CreateDeathLinkService is an extension on ArchipelagoSession.
        private ArchipelagoSession _session;
        private DeathLinkService _deathLink;

        private volatile bool _itemsDirty;
        private int _loggedGrantFailure = -1;
        private bool _loggedNameResolveFailure;
        private bool _connecting;
        private bool _wantConnection;
        private bool _applyingRemoteDeath;
        // The ApState whose goal send is in flight (null = none). A plain bool would be global
        // while the goal flags are per-save: a different save loading mid-send would find the
        // flag still set and have its own retry suppressed until the next connect.
        private ApState _goalSendState;
        private int _reconnectAttempt;
        private float _reconnectAt = -1f;
        private float _nextPendingFlushAt;

        private string _host = "";
        private int _port = 38281;
        private string _slotName = "";
        private string _password = "";

        public bool Connected { get; private set; } = false;
        public string Status { get; private set; } = "Disconnected";
        public string SlotName { get { return _slotName; } }
        public string Seed { get; private set; } = "";
        public int Team { get; private set; } = -1;
        public int Slot { get; private set; } = -1;
        public Dictionary<string, object> SlotData { get; private set; }
        public bool DeathLinkEnabled { get; private set; } = false;

        /// <summary>Number of enemy-kill milestone checks this seed offers (0 = feature off).</summary>
        public int EnemyKillChecks { get; private set; } = 0;

        /// <summary>Kills between milestones. Milestone k fires at k * this many kills.</summary>
        public int EnemyKillInterval { get; private set; } = 1;

        /// <summary>Number of attributes-learned milestone checks this seed offers (0 = off).</summary>
        public int AttributeLearnChecks { get; private set; } = 0;

        /// <summary>Teacher-learned points between milestones. Milestone k fires at k * this.</summary>
        public int AttributeLearnInterval { get; private set; } = 1;

        /// <summary>Number of talents-learned milestone checks this seed offers (0 = off).</summary>
        public int TalentLearnChecks { get; private set; } = 0;

        public int ItemsApplied { get { return _store.State.ApItemsApplied; } }
        public int ItemsReceived { get; private set; } = 0;
        public int LocationsChecked { get; private set; } = 0;
        public int LocationsTotal { get; private set; } = 0;

        /// <summary>
        /// The location ids the generator actually placed in THIS seed (from AllLocations). The
        /// datapackage knows every location the game can define, so a name for a category this seed
        /// disabled still resolves to a real id; suppressing loot or sending a check for one destroys the
        /// vanilla item and sends a check the server drops. Everything acting on a location gates on this.
        /// </summary>
        private readonly HashSet<long> _activeLocationIds = new();

        /// <summary>
        /// Set when persisted state changed (item granted, check recorded, kill counted) and must be
        /// pushed into the live savegame so an autosave persists it. Written from any thread (AP
        /// callbacks run on the ThreadPool), drained on the main thread in Pump.
        /// </summary>
        private volatile bool _statePersistDirty;

        /// <summary>Raised on the main thread after an item was successfully granted.</summary>
        public event Action<ItemInfo> OnItemToGrant;

        /// <summary>Raised on the main thread for every server message. Text is already flattened.</summary>
        public event Action<string> OnMessage;

        /// <summary>Raised on the main thread when a remote DeathLink arrives. Kill the player here.</summary>
        public event Action<DeathLink> OnRemoteDeath;

        /// <summary>Raised on the main thread once a login has succeeded and slot data is available.</summary>
        public event Action OnConnected;

        public ArchipelagoClient(ApConfig config, ArchipelagoStore store, IItemGranter granter)
        {
            _config = config;
            _store = store;
            _granter = granter;
        }

        // ---------------------------------------------------------------- connect

        public void Connect(string host, int port, string slotName, string password)
        {
            if (_connecting)
            {
                MelonLogger.Msg("Archipelago connect already in progress.");
                return;
            }

            if (Connected || _session != null)
            {
                Disconnect();
            }

            _host = (host ?? "").Trim();
            _port = port;
            _slotName = (slotName ?? "").Trim();
            _password = password ?? "";
            _wantConnection = true;
            _reconnectAttempt = 0;
            _reconnectAt = -1f;
            StartConnectTask();
        }

        private void StartConnectTask()
        {
            _connecting = true;
            Status = "Connecting to " + _host + ":" + _port + "...";
            string h = _host;
            int p = _port;
            string s = _slotName;
            string pw = _password;

            // TryConnectAndLogin blocks for up to ~8s, so it must never touch the Unity main thread.
            Task.Run(() =>
            {
                ArchipelagoSession created = null;
                try
                {
                    // Scheme-less _host: the library probes wss:// first and falls back to ws://.
                    created = ArchipelagoSessionFactory.CreateSession(h, p);
                    var result = created.TryConnectAndLogin(
                        GameName,
                        s,
                        ItemsHandlingFlags.AllItems,
                        null, // version: the library's own supported protocol version; it tracks the library, so it is the right default
                        null, // tags: none; DeathLink's tag is added later by EnableDeathLink()
                        null, // uuid: let the library generate one
                        string.IsNullOrEmpty(pw) ? null : pw,
                        true);

                    var sessionForCallback = created;
                    MainThreadDispatcher.Enqueue(() => HandleLoginResult(sessionForCallback, result));
                }
                catch (Exception e)
                {
                    string message = e.Message;
                    MainThreadDispatcher.Enqueue(() => HandleLoginFailed("connect threw: " + message));
                }
            });
        }

        private void HandleLoginResult(ArchipelagoSession newSession, LoginResult result)
        {
            try
            {
                _connecting = false;

                if (result is not LoginSuccessful success)
                {
                    string message = result is LoginFailure failure && failure.Errors != null
                        ? string.Join("; ", failure.Errors)
                        : "unknown login error";
                    CloseSocket(newSession);
                    HandleLoginFailed(message);
                    return;
                }

                _session = newSession;
                Subscribe();

                Connected = true;
                Team = success.Team;
                Slot = success.Slot;
                SlotData = success.SlotData;
                Seed = ReadSeed();
                _reconnectAttempt = 0;
                Status = "Connected as " + _slotName;
                MelonLogger.Msg("Archipelago connected: slot " + _slotName + " (" + Slot + "), seed '" + Seed + "'.");

                _session.SetClientState(ArchipelagoClientState.ClientPlaying);
                SetupDeathLink();
                SetupLootSuppression();
                SetupConsumableStackSize();
                SetupKillMilestones();
                SetupTeleporterShuffle();

                _store.StampOrValidate(ReadSeedName(), Seed, _slotName, Slot);

                BuildActiveLocationSet();
                RefreshLocationCounts();
                ResendCheckedLocations();
                FlushPendingLocationChecks();
                RetryGoalIfPending();
                _itemsDirty = true;

                // Listeners (e.g. the kill tracker catching up milestones) run last, once slot data,
                // the save stamp and the check queues are all settled.
                try
                {
                    OnConnected?.Invoke();
                }
                catch (Exception e)
                {
                    MelonLogger.Error("OnConnected handler failed: " + e);
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("HandleLoginResult failed: " + e);
            }
        }

        private void HandleLoginFailed(string message)
        {
            _connecting = false;
            Connected = false;
            Status = "Login failed: " + message;
            MelonLogger.Error("Archipelago login failed: " + message);
            ScheduleReconnect();
        }

        private string ReadSeed()
        {
            try
            {
                return _session.RoomState.Seed ?? "";
            }
            catch (Exception e)
            {
                MelonLogger.Warning("Could not read RoomState.Seed: " + e.Message);
                return "";
            }
        }

        private string ReadSeedName()
        {
            if (SlotData != null && SlotData.TryGetValue("seed_name", out object value) && value != null)
            {
                return value.ToString();
            }
            return Seed;
        }

        public void Disconnect()
        {
            _wantConnection = false;
            _reconnectAt = -1f;
            _reconnectAttempt = 0;

            var closing = _session;
            _session = null;
            _deathLink = null;
            Connected = false;
            DeathLinkEnabled = false;
            Status = "Disconnected";

            if (closing == null)
            {
                return;
            }

            Unsubscribe(closing);
            CloseSocket(closing);
            MelonLogger.Msg("Archipelago disconnected.");
        }

        private void CloseSocket(ArchipelagoSession target)
        {
            if (target == null)
            {
                return;
            }

            // A failed login leaves the socket already closed, and DisconnectAsync throws on that.
            // Closing an already-closed socket is the expected path here, not an error worth reporting.
            if (!target.Socket.Connected)
            {
                return;
            }

            try
            {
                var closing = target.Socket.DisconnectAsync();
                closing.ContinueWith(
                    t => MelonLogger.Msg("Socket disconnect failed (harmless): " + t.Exception?.GetBaseException().Message),
                    TaskContinuationOptions.OnlyOnFaulted);
            }
            catch (Exception e)
            {
                MelonLogger.Msg("Socket disconnect threw (harmless): " + e.Message);
            }
        }

        // ---------------------------------------------------------------- reconnect

        private void ScheduleReconnect()
        {
            if (!_wantConnection)
            {
                return;
            }

            _reconnectAttempt++;
            float delay = Math.Min(MaxReconnectDelay, (float)Math.Pow(2d, Math.Min(_reconnectAttempt, 6)));
            _reconnectAt = Time.realtimeSinceStartup + delay;
            Status = "Reconnecting in " + (int)delay + "s (attempt " + _reconnectAttempt + ")...";
            MelonLogger.Msg("Archipelago reconnect scheduled in " + (int)delay + "s.");
        }

        private void HandleSocketClosed()
        {
            if (!Connected && !_wantConnection)
            {
                return;
            }

            // There is no Reconnect(): the socket is not reusable, so the next attempt builds a new _session.
            Unsubscribe(_session);
            _session = null;
            _deathLink = null;
            Connected = false;
            DeathLinkEnabled = false;
            MelonLogger.Warning("Archipelago socket closed.");
            ScheduleReconnect();
        }

        // ---------------------------------------------------------------- events

        private void Subscribe()
        {
            _session.Items.ItemReceived += OnItemReceivedThreaded;
            _session.Socket.ErrorReceived += OnErrorReceivedThreaded;
            _session.Socket.SocketClosed += OnSocketClosedThreaded;
            _session.MessageLog.OnMessageReceived += OnMessageReceivedThreaded;
        }

        private void Unsubscribe(ArchipelagoSession target)
        {
            if (target == null)
            {
                return;
            }

            try
            {
                target.Items.ItemReceived -= OnItemReceivedThreaded;
                target.Socket.ErrorReceived -= OnErrorReceivedThreaded;
                target.Socket.SocketClosed -= OnSocketClosedThreaded;
                target.MessageLog.OnMessageReceived -= OnMessageReceivedThreaded;
            }
            catch (Exception e)
            {
                MelonLogger.Warning("Unsubscribe failed: " + e.Message);
            }
        }

        private void OnItemReceivedThreaded(ReceivedItemsHelper helper)
        {
            // Dirty flag only. The queue replays the whole history on every resync, so the item is
            // applied by the index cursor pump on the main thread instead of here.
            try
            {
                _itemsDirty = true;
            }
            catch (Exception e)
            {
                MelonLogger.Error("ItemReceived handler failed: " + e);
            }
        }

        private void OnErrorReceivedThreaded(Exception e, string message)
        {
            try
            {
                string text = message ?? (e != null ? e.Message : "unknown socket error");
                MainThreadDispatcher.Enqueue(() => MelonLogger.Error("Archipelago socket error: " + text));
            }
            catch (Exception inner)
            {
                MelonLogger.Error("ErrorReceived handler failed: " + inner);
            }
        }

        private void OnSocketClosedThreaded(string reason)
        {
            // reason is always empty on net6; do not parse it.
            try
            {
                MainThreadDispatcher.Enqueue(() =>
                {
                    try
                    {
                        HandleSocketClosed();
                    }
                    catch (Exception e)
                    {
                        MelonLogger.Error("HandleSocketClosed failed: " + e);
                    }
                });
            }
            catch (Exception e)
            {
                MelonLogger.Error("SocketClosed handler failed: " + e);
            }
        }

        private void OnMessageReceivedThreaded(LogMessage message)
        {
            try
            {
                string text = message.ToString();
                MainThreadDispatcher.Enqueue(() =>
                {
                    try
                    {
                        MelonLogger.Msg("[AP] " + text);
                        OnMessage?.Invoke(text);
                    }
                    catch (Exception e)
                    {
                        MelonLogger.Error("OnMessage handler failed: " + e);
                    }
                });
            }
            catch (Exception e)
            {
                MelonLogger.Error("MessageReceived handler failed: " + e);
            }
        }

        // ---------------------------------------------------------------- pump

        /// <summary>Flag that persisted state changed; the main-thread Pump pushes it into the savegame.</summary>
        public void MarkStatePersistDirty()
        {
            _statePersistDirty = true;
        }

        /// <summary>Main thread. Drives reconnects, the item cursor, and live-savegame persistence.</summary>
        public void Pump()
        {
            // Drain any pending persist first, even while disconnected: the game keeps autosaving, and
            // the state must be in the savegame before the next write. Savegame.Current is null at the
            // menu, where PushToLiveSavegame no-ops.
            if (_statePersistDirty)
            {
                _statePersistDirty = false;
                _store.PushToLiveSavegame();
            }

            if (_reconnectAt > 0f && Time.realtimeSinceStartup >= _reconnectAt)
            {
                _reconnectAt = -1f;
                StartConnectTask();
            }

            if (!Connected || _session == null)
            {
                return;
            }

            if (_itemsDirty)
            {
                PumpItems();
            }

            // A queued name whose resolution threw at connect time (datapackage still in flight) would
            // otherwise wait for the next connect or save load. Retry occasionally while connected.
            if (!_store.Mismatched
                && _store.State.PendingLocationNames.Count > 0
                && Time.realtimeSinceStartup >= _nextPendingFlushAt)
            {
                _nextPendingFlushAt = Time.realtimeSinceStartup + PendingFlushRetryInterval;
                FlushPendingLocationChecks();
            }
        }

        private void PumpItems()
        {
            if (_store.Mismatched)
            {
                return;
            }

            // Clear the flag before reading the list: an item arriving mid-pump then re-dirties us
            // instead of being swallowed by a clear at the end.
            _itemsDirty = false;

            ReadOnlyCollection<ItemInfo> all;
            try
            {
                all = _session.Items.AllItemsReceived;
            }
            catch (Exception e)
            {
                MelonLogger.Error("Could not read AllItemsReceived: " + e);
                _itemsDirty = true;
                return;
            }

            ItemsReceived = all.Count;
            var state = _store.State;

            for (int i = state.ApItemsApplied; i < all.Count; i++)
            {
                var info = all[i];
                bool granted;
                try
                {
                    granted = _granter.TryGrant(info, ResolveItemName(info));
                }
                catch (Exception e)
                {
                    // The cursor deliberately does not advance on failure, so this retries every
                    // frame. Log it once per index instead of once per frame.
                    if (_loggedGrantFailure != i)
                    {
                        _loggedGrantFailure = i;
                        MelonLogger.Error("Granting AP item at index " + i + " threw: " + e);
                    }
                    granted = false;
                }

                if (!granted)
                {
                    // Not ready. Leave the cursor where it is and retry next frame.
                    _itemsDirty = true;
                    return;
                }

                state.ApItemsApplied = i + 1;
                _statePersistDirty = true;

                try
                {
                    OnItemToGrant?.Invoke(info);
                }
                catch (Exception e)
                {
                    MelonLogger.Error("OnItemToGrant handler failed: " + e);
                }
            }
        }

        /// <summary>
        /// Resolve an item name without going through ItemInfo.ItemName.
        /// That property resolves against the sending player's game, which is null until the players
        /// list is populated, and it throws rather than returning null. Everything we receive belongs
        /// to our own game, so ask for it by our game name explicitly.
        /// Returns null when it cannot be resolved yet; the caller then retries.
        /// </summary>
        private string ResolveItemName(ItemInfo info)
        {
            try
            {
                return _session.Items.GetItemName(info.ItemId, GameName);
            }
            catch (Exception e)
            {
                if (!_loggedNameResolveFailure)
                {
                    _loggedNameResolveFailure = true;
                    MelonLogger.Msg("[AP item] name for id " + info.ItemId + " not resolvable yet: " + e.Message);
                }
                return null;
            }
        }

        /// <summary>
        /// Ask the pump to try the pending items again, for when something the _granter was waiting on
        /// (the player, a loaded scene) has just become available.
        /// </summary>
        public void NudgeItems()
        {
            _itemsDirty = true;
        }

        /// <summary>Called from the _store once a save game was loaded. Main thread.</summary>
        public void OnSaveGameStateLoaded()
        {
            if (!Connected || _session == null)
            {
                return;
            }

            _store.StampOrValidate(ReadSeedName(), Seed, _slotName, Slot);
            RefreshLocationCounts();
            ResendCheckedLocations();
            FlushPendingLocationChecks();
            RetryGoalIfPending();
            _itemsDirty = true;
        }

        private void RetryGoalIfPending()
        {
            if (_store.State.GoalReached && !_store.State.GoalSent)
            {
                SendGoal();
            }
        }

        // ---------------------------------------------------------------- locations

        public void CheckLocation(long id)
        {
            if (_store.Mismatched)
            {
                MelonLogger.Warning("Save/seed mismatch; refusing to send location check " + id + ".");
                return;
            }

            // Record before sending: the send can fail, but a recorded check is re-sent by
            // ResendCheckedLocations on every connect and save load, so it can never be lost.
            if (!_store.State.CheckedLocations.Contains(id))
            {
                _store.State.CheckedLocations.Add(id);
                _statePersistDirty = true;
            }

            if (!Connected || _session == null)
            {
                MelonLogger.Msg("Not connected; location check " + id + " recorded, will be sent on reconnect.");
                return;
            }

            SendChecks(new long[] { id });
        }

        /// <summary>
        /// Seam for the location detection work: resolve an AP location by name and check it.
        /// No-ops with a warning when the name is unknown to the connected world.
        /// </summary>
        public void CheckLocationByName(string apLocationName)
        {
            if (string.IsNullOrEmpty(apLocationName))
            {
                return;
            }

            // A name cannot be resolved to an id without a _session (the id lives in the server's
            // datapackage), so an offline check is persisted by name and flushed on connect.
            // Mismatched queues too: the live _session belongs to a different room, so resolving the
            // name against ITS datapackage would record a foreign id. The name is room-independent
            // and is flushed once this save is connected to the room it belongs to.
            if (!Connected || _session == null || _store.Mismatched)
            {
                QueuePendingLocation(apLocationName);
                return;
            }

            long id;
            try
            {
                id = _session.Locations.GetLocationIdFromName(GameName, apLocationName);
            }
            catch (Exception e)
            {
                // Transient (datapackage not cached yet); keep the name queued for the next flush.
                MelonLogger.Error("GetLocationIdFromName('" + apLocationName + "') threw: " + e);
                QueuePendingLocation(apLocationName);
                return;
            }

            if (id == -1)
            {
                // Permanently unknown to this world; retrying cannot fix it, so drop it from the queue.
                _store.State.PendingLocationNames.Remove(apLocationName);
                MelonLogger.Warning("Unknown AP location name '" + apLocationName + "'; ignoring.");
                return;
            }

            if (!_activeLocationIds.Contains(id))
            {
                // Known to the datapackage but not placed in this seed (its category is off). Sending it
                // would do nothing, and the loot suppressor is gated the same way so the vanilla item was
                // never taken. Drop it from the queue and stay silent.
                _store.State.PendingLocationNames.Remove(apLocationName);
                return;
            }

            _store.State.PendingLocationNames.Remove(apLocationName);
            CheckLocation(id);
        }

        private void QueuePendingLocation(string apLocationName)
        {
            var pending = _store.State.PendingLocationNames;
            if (!pending.Contains(apLocationName))
            {
                pending.Add(apLocationName);
                MelonLogger.Msg("Location check '" + apLocationName + "' queued, will be sent on reconnect.");
            }
        }

        /// <summary>
        /// Resolve and send every location that was checked while no _session was available.
        /// CheckLocationByName removes each name from the queue once it resolves.
        /// </summary>
        private void FlushPendingLocationChecks()
        {
            if (_store.Mismatched)
            {
                return;
            }

            var pending = _store.State.PendingLocationNames;
            if (pending == null || pending.Count == 0)
            {
                return;
            }

            MelonLogger.Msg("Sending " + pending.Count + " location check(s) queued while disconnected.");
            // Copy: CheckLocationByName mutates the queue as names resolve.
            foreach (string name in pending.ToArray())
            {
                CheckLocationByName(name);
            }
        }

        /// <summary>
        /// Re-send every location this save has checked. The server ignores duplicates and the
        /// helper diffs locally, so this is free and makes a reload self-healing.
        /// </summary>
        private void ResendCheckedLocations()
        {
            if (_store.Mismatched)
            {
                return;
            }

            var checkedLocations = _store.State.CheckedLocations;
            if (checkedLocations == null || checkedLocations.Count == 0)
            {
                return;
            }

            SendChecks(checkedLocations.ToArray());
        }

        private void SendChecks(long[] ids)
        {
            var target = _session;
            if (target == null)
            {
                return;
            }

            try
            {
                var sending = target.Locations.CompleteLocationChecksAsync(ids);
                sending.ContinueWith(
                    t => MelonLogger.Error("CompleteLocationChecksAsync failed: " + t.Exception),
                    TaskContinuationOptions.OnlyOnFaulted);
                sending.ContinueWith(
                    t => MainThreadDispatcher.Enqueue(RefreshLocationCounts),
                    TaskContinuationOptions.OnlyOnRanToCompletion);
            }
            catch (Exception e)
            {
                MelonLogger.Error("CompleteLocationChecksAsync threw: " + e);
            }
        }

        /// <summary>
        /// Snapshot the ids the generator placed in this seed. AllLocations is fixed for the life of a
        /// room, so this is rebuilt once per connect (before the resend/flush that gate on it).
        /// </summary>
        private void BuildActiveLocationSet()
        {
            _activeLocationIds.Clear();
            if (_session == null)
            {
                return;
            }

            try
            {
                foreach (long id in _session.Locations.AllLocations)
                {
                    _activeLocationIds.Add(id);
                }
                MelonLogger.Msg("[AP] " + _activeLocationIds.Count + " locations active in this seed.");
            }
            catch (Exception e)
            {
                MelonLogger.Error("Building the active-location set failed: " + e);
            }
        }

        /// <summary>
        /// Name and checked-state of every location the generator placed in this seed, for the progress
        /// panel. Server truth: AllLocationsChecked includes checks sent by other sessions and collects.
        /// Empty when not connected. Names resolve through the room's own datapackage, so they exist
        /// even for locations a newer local table no longer knows.
        /// </summary>
        public List<KeyValuePair<string, bool>> GetSeedLocationStates()
        {
            var states = new List<KeyValuePair<string, bool>>();
            var session = _session;
            if (!Connected || session == null)
            {
                return states;
            }

            try
            {
                var checkedIds = new HashSet<long>(session.Locations.AllLocationsChecked);
                foreach (long id in session.Locations.AllLocations)
                {
                    string name = session.Locations.GetLocationNameFromId(id);
                    if (string.IsNullOrEmpty(name))
                    {
                        continue;
                    }
                    states.Add(new KeyValuePair<string, bool>(name, checkedIds.Contains(id)));
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("Snapshotting location states for the progress panel failed: " + e);
            }
            return states;
        }

        /// <summary>
        /// True only for a location the generator placed in this seed. False when not connected, when the
        /// name is unknown, or when it belongs to a category this seed left off. Callers must not suppress
        /// vanilla loot or send a check for a location this returns false for.
        /// </summary>
        public bool IsLocationActiveInSeed(string apLocationName)
        {
            if (!Connected || _session == null || string.IsNullOrEmpty(apLocationName))
            {
                return false;
            }

            long id;
            try
            {
                id = _session.Locations.GetLocationIdFromName(GameName, apLocationName);
            }
            catch
            {
                return false;
            }

            return id != -1 && _activeLocationIds.Contains(id);
        }

        private void RefreshLocationCounts()
        {
            try
            {
                if (_session == null)
                {
                    return;
                }
                LocationsChecked = _session.Locations.AllLocationsChecked.Count;
                LocationsTotal = _session.Locations.AllLocations.Count;
            }
            catch (Exception e)
            {
                MelonLogger.Warning("Could not refresh location counts: " + e.Message);
            }
        }

        // ---------------------------------------------------------------- goal

        public void SendGoal()
        {
            var state = _store.State;
            if (state.GoalSent)
            {
                return;
            }

            // Reached and Sent are separate flags on purpose: Reached persists the intent, and Sent
            // only flips once the server accepted it. A failed, offline or mismatched send is retried
            // on the next connect and save load instead of being latched away forever. The intent is
            // recorded before any guard: only the send touches the server, the flag belongs to the save.
            state.GoalReached = true;
            _statePersistDirty = true;

            if (_store.Mismatched)
            {
                MelonLogger.Warning("Save/seed mismatch; the goal is recorded and will be sent once "
                    + "this save is connected to its own room.");
                return;
            }

            if (!Connected || _session == null)
            {
                MelonLogger.Warning("Not connected; the goal is recorded and will be sent on reconnect.");
                return;
            }

            // Skip only when THIS save's send is already in flight. Another save's in-flight send
            // is not a reason to skip: it protects its own ApState, not this one.
            if (_goalSendState == state)
            {
                return;
            }

            _goalSendState = state;
            var target = _session;
            Task.Run(() =>
            {
                try
                {
                    target.SetGoalAchieved();
                    MainThreadDispatcher.Enqueue(() =>
                    {
                        // Guarded clear: a newer send for a different save may own the marker now.
                        if (_goalSendState == state)
                        {
                            _goalSendState = null;
                        }
                        // The captured state, not _store.State: if a different save loaded mid-send,
                        // its goal flags must not be touched.
                        state.GoalSent = true;
                        _statePersistDirty = true;
                        MelonLogger.Msg("Archipelago goal sent.");
                    });
                }
                catch (Exception e)
                {
                    MelonLogger.Error("SetGoalAchieved failed: " + e);
                    MainThreadDispatcher.Enqueue(() =>
                    {
                        if (_goalSendState == state)
                        {
                            _goalSendState = null;
                        }
                    });
                }
            });
        }

        // ---------------------------------------------------------------- chat

        /// <summary>
        /// Outbound chat. Server commands ("!hint &lt;item&gt;", "!release", "!collect") go through
        /// the same channel. The server's reply comes back through MessageLog like any other chat
        /// line, so there is no result handling here. Main thread is fine: Say only queues the
        /// packet on the socket, it does not block.
        /// </summary>
        public void Say(string text)
        {
            if (string.IsNullOrWhiteSpace(text))
            {
                return;
            }

            if (!Connected || _session == null)
            {
                MelonLogger.Warning("Not connected; chat message not sent.");
                return;
            }

            try
            {
                _session.Say(text);
            }
            catch (Exception e)
            {
                MelonLogger.Error("Say failed: " + e);
            }
        }

        // ---------------------------------------------------------------- deathlink

        /// <summary>
        /// Whether randomized containers give up their vanilla loot. Seed-controlled: an older seed
        /// without the key keeps the additive behaviour it was generated for.
        /// </summary>
        private void SetupLootSuppression()
        {
            bool suppress = false;
            if (SlotData != null && SlotData.TryGetValue("suppress_vanilla_loot", out object value) && value != null)
            {
                suppress = ToBool(value, false);
            }

            LootSuppressor.Enabled = suppress;
            MelonLogger.Msg(suppress
                ? "Vanilla loot suppression ON: randomized containers give only their Archipelago item, "
                    + "except keys and quest items."
                : "Vanilla loot suppression off: containers give their normal contents as well.");
        }

        /// <summary>
        /// Reads the consumable grant sizing from slot data. Absent (older seeds) or unknown keys
        /// keep the full table amounts the seed was generated for.
        /// </summary>
        private void SetupConsumableStackSize()
        {
            var size = ConsumableStackSize.Full;
            if (SlotData != null && SlotData.TryGetValue("consumable_stack_size", out object value) && value != null)
            {
                switch (value.ToString())
                {
                    case "small":
                        size = ConsumableStackSize.Small;
                        break;
                    case "single":
                        size = ConsumableStackSize.Single;
                        break;
                }
            }

            ItemGranter.StackSize = size;
            if (size != ConsumableStackSize.Full)
            {
                MelonLogger.Msg("Consumable stack size: " + size.ToString().ToLowerInvariant() + ".");
            }
        }

        /// <summary>
        /// Hands the seed's entrance shuffle to the teleporter rewiring. Absent or empty (older
        /// seeds, option off) configures vanilla wiring, which also undoes a previous room's
        /// shuffle when one session hops between rooms.
        /// </summary>
        private void SetupTeleporterShuffle()
        {
            var map = new Dictionary<string, string>();
            if (SlotData != null && SlotData.TryGetValue("teleporters", out object value)
                && value is Newtonsoft.Json.Linq.JObject jsonMap)
            {
                foreach (var property in jsonMap.Properties())
                {
                    map[property.Name] = property.Value?.ToString() ?? "";
                }
            }

            TeleporterShuffler.Configure(map);
        }

        /// <summary>
        /// Reads the enemy-kill milestone _config from slot data. Absent (older seeds) leaves the
        /// feature off. Interval is clamped to at least 1 so the tracker can never divide by zero.
        /// </summary>
        private void SetupKillMilestones()
        {
            EnemyKillChecks = ReadIntSlotData("enemy_kill_checks", 0);
            EnemyKillInterval = Math.Max(1, ReadIntSlotData("enemy_kill_interval", 1));
            AttributeLearnChecks = ReadIntSlotData("attribute_learn_checks", 0);
            AttributeLearnInterval = Math.Max(1, ReadIntSlotData("attribute_learn_interval", 1));
            TalentLearnChecks = ReadIntSlotData("talent_learn_checks", 0);

            if (EnemyKillChecks > 0)
            {
                MelonLogger.Msg("Enemy-kill milestones: " + EnemyKillChecks + " check(s), one every "
                    + EnemyKillInterval + " kill(s).");
            }
        }

        private int ReadIntSlotData(string key, int fallback)
        {
            if (SlotData == null || !SlotData.TryGetValue(key, out object value) || value == null)
            {
                return fallback;
            }
            try
            {
                return Convert.ToInt32(value);
            }
            catch
            {
                return fallback;
            }
        }

        private void SetupDeathLink()
        {
            bool enabled = _config.DeathLink;
            if (SlotData != null && SlotData.TryGetValue("death_link", out object value) && value != null)
            {
                enabled = ToBool(value, enabled);
            }

            if (!enabled)
            {
                DeathLinkEnabled = false;
                return;
            }

            try
            {
                _deathLink = _session.CreateDeathLinkService();
                _deathLink.OnDeathLinkReceived += OnDeathLinkReceivedThreaded;
                _deathLink.EnableDeathLink();
                DeathLinkEnabled = true;
                MelonLogger.Msg("DeathLink enabled.");
            }
            catch (Exception e)
            {
                DeathLinkEnabled = false;
                MelonLogger.Error("Could not enable DeathLink: " + e);
            }
        }

        private static bool ToBool(object value, bool fallback)
        {
            try
            {
                if (value is bool b)
                {
                    return b;
                }
                return Convert.ToInt64(value) != 0L;
            }
            catch
            {
                return fallback;
            }
        }

        private void OnDeathLinkReceivedThreaded(DeathLink death)
        {
            try
            {
                MainThreadDispatcher.Enqueue(() =>
                {
                    try
                    {
                        // Guards our own death hook against re-broadcasting the death we are applying.
                        _applyingRemoteDeath = true;
                        MelonLogger.Msg("DeathLink from " + death.Source + ": " + death.Cause);
                        OnRemoteDeath?.Invoke(death);
                    }
                    catch (Exception e)
                    {
                        MelonLogger.Error("OnRemoteDeath handler failed: " + e);
                    }
                    finally
                    {
                        _applyingRemoteDeath = false;
                    }
                });
            }
            catch (Exception e)
            {
                MelonLogger.Error("DeathLinkReceived handler failed: " + e);
            }
        }

        /// <summary>Seam for the death hook: call when the player dies of their own accord.</summary>
        public void SendDeathLink(string cause)
        {
            if (!DeathLinkEnabled || _deathLink == null || _applyingRemoteDeath)
            {
                return;
            }

            try
            {
                _deathLink.SendDeathLink(new DeathLink(_slotName, cause));
            }
            catch (Exception e)
            {
                MelonLogger.Error("SendDeathLink failed: " + e);
            }
        }
    }
}
