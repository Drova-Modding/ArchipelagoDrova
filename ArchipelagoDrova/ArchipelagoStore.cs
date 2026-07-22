using Drova_Modding_API.Systems.SaveGame.Store;
using Il2CppDrova.Saveables;
using MelonLoader;
using Newtonsoft.Json;

namespace ArchipelagoDrova
{
    /// <summary>
    /// The AP state store persisted inside the native .sav via the Drova Modding API save system.
    /// A JSON side-car under UserData/ArchipelagoDrova mirrors it for diagnostics only.
    /// </summary>
    public class ArchipelagoStore : IStorable
    {
        public const string StoreKey = "ArchipelagoDrova_State";

        public string SaveGameKey => StoreKey;

        public ApState State { get; private set; } = new();

        /// <summary>
        /// True when the loaded save was stamped with a different seed/slot than the live session.
        /// The client refuses to apply items or send checks while this is set.
        /// </summary>
        public bool Mismatched { get; private set; }

        /// <summary>Raised on the main thread once Load() populated the state.</summary>
        public event Action OnStateLoaded;

        // The identity of the connected session, kept outside ApState so it survives Reset() and the
        // Load() that replaces the state object. Connecting stamps the state, but a save loads AFTER
        // autoconnect, so Reset() then wipes that stamp and Load() swaps the object out from under it.
        // Any save written in that window used to persist seed "" forever, which silently disabled
        // mismatch detection.
        private string _liveSeedName = "";
        private string _liveRoomSeed = "";
        private string _liveSlotName = "";
        private int _liveSlot = -1;
        private bool _haveLiveIdentity;

        public string Save()
        {
            // Stamp at serialization time. This is the only point guaranteed to be after both Reset()
            // and Load(), so it is the only place the stamp cannot be lost.
            if (_haveLiveIdentity && !Mismatched && string.IsNullOrEmpty(State.RoomSeed))
            {
                State.SeedName = _liveSeedName;
                State.RoomSeed = _liveRoomSeed;
                State.SlotName = _liveSlotName;
                State.Slot = _liveSlot;
                MelonLogger.Msg("Stamped the save being written with AP seed '" + _liveRoomSeed +
                    "' slot '" + _liveSlotName + "'.");
            }

            string json;
            try
            {
                json = JsonConvert.SerializeObject(State);
            }
            catch (Exception e)
            {
                MelonLogger.Error("Failed to serialize AP state: " + e);
                return "";
            }

            WriteSideCar(json);
            return json;
        }

        /// <summary>
        /// Push the current state straight into the live savegame's data bag, so it rides the very next
        /// disk write. Drova's AUTOSAVE serializes the savegame but never fires the API's
        /// BeforeSaveGameSaving, so it never calls <see cref="Save"/> - only hard/quit saves did. That
        /// left the item cursor and checks stale after an autosave-only session, and reconnecting then
        /// re-applied already-received items (XP re-granted, level ups from nothing). Injecting the state
        /// into Savegame.Current here means an autosave persists it too. Main thread only: touches IL2CPP.
        /// </summary>
        public void PushToLiveSavegame()
        {
            try
            {
                var current = Savegame.Current;
                if (current == null)
                {
                    return;
                }

                var data = current.Data;
                if (data == null)
                {
                    return;
                }

                string json = Save(); // stamps and refreshes the diagnostics side-car
                if (!string.IsNullOrEmpty(json))
                {
                    data.SetString(StoreKey, json);
                }
            }
            catch (Exception e)
            {
                MelonLogger.Warning("Could not push AP state into the live savegame: " + e.Message);
            }
        }

        public void Load(string result)
        {
            // The API fires AfterSaveGameLoaded before stores are populated, so all post-load work lives here.
            try
            {
                var loaded = JsonConvert.DeserializeObject<ApState>(result);
                State = loaded ?? new ApState();
                State.CheckedLocations ??= [];
                // Saves written before these fields existed deserialize them as null.
                State.PendingLocationNames ??= [];
                Mismatched = false;
                MelonLogger.Msg("Loaded AP state: seed '" + State.RoomSeed + "' slot '" + State.SlotName +
                    "' items applied " + State.ApItemsApplied + ", checks " + State.CheckedLocations.Count + ".");
            }
            catch (Exception e)
            {
                MelonLogger.Error("Failed to deserialize AP state, starting empty: " + e);
                State = new ApState();
                Mismatched = false;
            }

            try
            {
                OnStateLoaded?.Invoke();
            }
            catch (Exception e)
            {
                MelonLogger.Error("OnStateLoaded handler failed: " + e);
            }
        }

        /// <summary>
        /// Wipe the state. Must run on BeforeSaveGameLoaded: a new game never calls Load(), so without
        /// this the store would silently carry the previous session's data into the fresh save.
        /// </summary>
        public void Reset()
        {
            State = new ApState();
            Mismatched = false;
        }

        /// <summary>
        /// Stamp an unstamped save with the live session identity, or flag a mismatch when the save
        /// belongs to a different seed/slot. Never throws, never hard-fails the game.
        /// </summary>
        public void StampOrValidate(string seedName, string roomSeed, string slotName, int slot)
        {
            // Remember the identity independently of ApState, which Reset()/Load() replace.
            _liveSeedName = seedName ?? "";
            _liveRoomSeed = roomSeed ?? "";
            _liveSlotName = slotName ?? "";
            _liveSlot = slot;
            _haveLiveIdentity = !string.IsNullOrEmpty(_liveRoomSeed) || !string.IsNullOrEmpty(_liveSlotName);

            bool unstamped = string.IsNullOrEmpty(State.RoomSeed) && string.IsNullOrEmpty(State.SlotName);
            if (unstamped)
            {
                State.SeedName = seedName ?? "";
                State.RoomSeed = roomSeed ?? "";
                State.SlotName = slotName ?? "";
                State.Slot = slot;
                Mismatched = false;
                MelonLogger.Msg("Stamped this save with AP seed '" + State.RoomSeed + "' slot '" + State.SlotName + "'.");
                return;
            }

            bool seedOk = string.IsNullOrEmpty(State.RoomSeed) || State.RoomSeed == roomSeed;
            bool slotOk = string.IsNullOrEmpty(State.SlotName) || State.SlotName == slotName;
            if (seedOk && slotOk)
            {
                Mismatched = false;
                return;
            }

            Mismatched = true;
            MelonLogger.Error("==================================================================");
            MelonLogger.Error(" ARCHIPELAGO SAVE MISMATCH - items and checks are DISABLED.");
            MelonLogger.Error("   save was stamped: seed '" + State.RoomSeed + "' slot '" + State.SlotName + "'");
            MelonLogger.Error("   connected session: seed '" + roomSeed + "' slot '" + slotName + "'");
            MelonLogger.Error(" Load the save that belongs to this multiworld, or connect to the");
            MelonLogger.Error(" room this save was started in.");
            MelonLogger.Error("==================================================================");
        }

        private void WriteSideCar(string json)
        {
            try
            {
                Directory.CreateDirectory(ApConfig.DataDirectory);
                File.WriteAllText(Path.Combine(ApConfig.DataDirectory, "state.json"), json);
            }
            catch (Exception e)
            {
                MelonLogger.Warning("Failed to write the AP state side-car: " + e.Message);
            }
        }
    }
}
