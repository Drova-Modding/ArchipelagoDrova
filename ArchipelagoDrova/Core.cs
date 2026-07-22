using Drova_Modding_API.Access;
using Drova_Modding_API.GlobalFields;
using Drova_Modding_API.Systems.SaveGame;
using Il2CppDrova;
using Il2CppDrova.Saveables;
using MelonLoader;

[assembly: MelonInfo(typeof(ArchipelagoDrova.Core), "ArchipelagoDrova", "0.3.0", "TrustNoOneElse")]
[assembly: MelonGame("Just2D", "Drova")]
[assembly: MelonAdditionalDependencies("Drova_Modding_API")]

namespace ArchipelagoDrova
{
    public class Core : MelonMod
    {
        public static ApConfig Config { get; private set; }
        public static ArchipelagoStore Store { get; private set; }
        public static ArchipelagoClient Client { get; private set; }
        public static ApUi Ui { get; private set; }

        /// <summary>True while Scene_Gameplay_Main is loaded. The item granter gates on this.</summary>
        public static bool InGameplayScene { get; private set; }

        /// <summary>
        /// The player, or null until the API reports one. Set from PlayerAccess.OnPlayerFound, which
        /// is the API's own readiness signal: it only fires once the world is ready, no loading screen
        /// is up, and the actor is _isInitialized. Polling PlayerAccess.GetPlayer() instead is wrong
        /// twice over: it throws while the game manager is still coming up, and it can hand back an
        /// actor not initialized yet.
        /// </summary>
        public static Actor Player { get; private set; }

        /// <summary>True, once the player exists and is initialized. Use Unity's implicit bool so a
        /// destroyed actor reads as absent.</summary>
        public static bool PlayerReady => Player;

        private int _guiFailStreak;
        private int _lastGuiFailFrame = -1;
        private bool _shutDown;

        /// <summary>IMGUI can throw transiently (e.g. during scene teardown), so one exception must
        /// not cost the whole session its UI. Failures are counted per FRAME, not per call: OnGUI
        /// runs several times a frame (Layout, Repaint, input events), and a repaint-only fault would
        /// otherwise alternate fail/succeed forever without ever tripping a consecutive-call counter.
        /// A frame with no failure breaks the streak; a persistent fault disables the UI in ~15 frames.</summary>
        private const int MaxGuiFailStreak = 15;

        public override void OnInitializeMelon()
        {
            Config = ApConfig.Load();

            // The API's readiness signal for the player. Fires on every load, including after a save
            // is loaded, so this is the only thing that should decide when we may touch the player.
            PlayerAccess.OnPlayerFound += OnPlayerFound;

            Store = new ArchipelagoStore();
            SaveGameSystem.Instance.AddStore(Store);
            // A new game never calls Load(), so without this wipe the store would carry the
            // previous session's data into the fresh save.
            SaveGameSystem.BeforeSaveGameLoaded += OnBeforeSaveGameLoaded;

            Client = new ArchipelagoClient(Config, Store, new ItemGranter());
            Store.OnStateLoaded += Client.OnSaveGameStateLoaded;

            Ui = new ApUi(Client, Config);
            Client.OnMessage += Ui.AddToast;
            // The cheat command cannot be registered here: Drova's game manager does not exist yet
            // during melon init, so CheatGameHandler.TryGet throws. Deferred to scene load.

            // Game-side detection largely rides the Modding API's GameEvents (subscribed inside
            // each tracker); HarmonyInstance only goes where an AP-specific hook remains.
            QuestTracker.Initialize(Client);
            ContainerTracker.Initialize(Client, HarmonyInstance);
            TraderTracker.Initialize(Client);
            GoalTracker.Initialize(Client, HarmonyInstance);
            DeathTracker.Initialize(Client);
            KillTracker.Initialize(Client, Store);
            LearnTracker.Initialize(Client, Store);
            LootSuppressor.Initialize(HarmonyInstance);
            RuneShuffler.Initialize();
            RuneHintOverlay.Initialize();

            // Registered after Client.OnSaveGameStateLoaded so the save stamp is validated first.
            Store.OnStateLoaded += QuestTracker.RequestSweep;
            Store.OnStateLoaded += ContainerTracker.OnSaveGameStateLoaded;
            Store.OnStateLoaded += TraderTracker.OnSaveGameStateLoaded;
            // Catch up milestone counters both when a save loads and when a connection completes.
            Store.OnStateLoaded += KillTracker.SyncMilestones;
            Client.OnConnected += KillTracker.SyncMilestones;
            Store.OnStateLoaded += LearnTracker.SyncMilestones;
            Client.OnConnected += LearnTracker.SyncMilestones;

            LoggerInstance.Msg("Initialized. Press F7 for the Archipelago panel.");
        }

        private void OnPlayerFound(Actor player)
        {
            try
            {
                Player = player;
                LoggerInstance.Msg("Player ready; Archipelago items can now be granted.");
                // Anything the pump could not apply while the player was absent is now applicable.
                Client.NudgeItems();
                // Teleporter re-apply on world-ready and rune-hint scene sweeps are handled by
                // the Modding API (TeleporterAccess / SceneStreamAccess listeners).
            }
            catch (Exception e)
            {
                LoggerInstance.Error("OnPlayerFound failed: " + e);
            }
        }

        private void OnBeforeSaveGameLoaded(Savegame saveGame)
        {
            try
            {
                Store.Reset();
                // A new game never calls Load(), so OnStateLoaded never fires for it. Without these
                // clears the trackers' session dedup carries over: a location already sent from the
                // previous save this session would be silently swallowed in the new one.
                ContainerTracker.OnSaveGameStateLoaded();
                QuestTracker.RequestSweep();
            }
            catch (Exception e)
            {
                LoggerInstance.Error("BeforeSaveGameLoaded failed: " + e);
            }
        }

        public override void OnSceneWasLoaded(int buildIndex, string sceneName)
        {
            try
            {
                // Retried per scene until it takes: the handler only exists once the game is up.
                Ui.RegisterCheat();

                if (sceneName == SceneNames.GameplayMain)
                {
                    InGameplayScene = true;
                    if (Config.AutoConnect && !Client.Connected)
                    {
                        Client.Connect(Config.Host, Config.Port, Config.SlotName, Config.Password);
                    }
                }
                else if (sceneName == SceneNames.MainMenu)
                {
                    InGameplayScene = false;
                    Player = null;
                }

            }
            catch (Exception e)
            {
                LoggerInstance.Error("OnSceneWasLoaded failed: " + e);
            }
        }

        public override void OnSceneWasUnloaded(int buildIndex, string sceneName)
        {
            if (sceneName == SceneNames.GameplayMain)
            {
                InGameplayScene = false;
                // The actor does not survive the scene; OnPlayerFound provides the next one.
                Player = null;
            }
        }

        public override void OnUpdate()
        {
            try
            {
                Client.Pump();
                QuestTracker.Update();
                DeathTracker.Update();
                TraderTracker.Pump();
                Ui.Update();
            }
            catch (Exception e)
            {
                LoggerInstance.Error("OnUpdate failed: " + e);
            }
        }

        public override void OnGUI()
        {
            if (_guiFailStreak >= MaxGuiFailStreak)
            {
                return;
            }

            try
            {
                Ui.Draw();
            }
            catch (Exception e)
            {
                int frame = UnityEngine.Time.frameCount;
                if (frame == _lastGuiFailFrame)
                {
                    // Already counted and logged this frame; OnGUI fires per IMGUI event.
                    return;
                }

                // Consecutive failing frames; any clean frame in between breaks the chain.
                _guiFailStreak = frame == _lastGuiFailFrame + 1 ? _guiFailStreak + 1 : 1;
                _lastGuiFailFrame = frame;
                LoggerInstance.Error("OnGUI failed (frame streak " + _guiFailStreak + "/" + MaxGuiFailStreak + "): " + e);
                if (_guiFailStreak >= MaxGuiFailStreak)
                {
                    LoggerInstance.Error("Disabling the Archipelago UI for this session.");
                }
            }
        }

        public override void OnDeinitializeMelon()
        {
            Shutdown();
        }

        public override void OnApplicationQuit()
        {
            Shutdown();
        }

        private void Shutdown()
        {
            if (_shutDown)
            {
                return;
            }
            _shutDown = true;

            try
            {
                SaveGameSystem.BeforeSaveGameLoaded -= OnBeforeSaveGameLoaded;
                Client?.Disconnect();
            }
            catch (Exception e)
            {
                LoggerInstance.Error("Shutdown failed: " + e);
            }
        }
    }
}
