using ArchipelagoDrova.Data;
using Drova_Modding_API.Access;
using HarmonyLib;
using Il2CppDrova;
using Il2CppDrova.Crafting;
using Il2CppDrova.InteractionSystem;
using Il2CppDrova.InventorySystem;
using Il2CppDrova.Saveables;
using MelonLoader;
using UnityEngine;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Turns looting a tracked world object into an AP location check.
    ///
    /// ATTACH STRATEGY: Harmony postfixes on the behaviours' own methods rather than per-instance
    /// GenericEvent subscriptions. VERIFIED_HOOKS prefers GenericEvent, but it does not work here:
    /// neither OpenArgs nor InventoryChangedEventArgs carries a back-reference to the behaviour or its
    /// GameObject, so a single shared listener could not tell which container fired. That would force
    /// one Il2Cpp delegate closure per instance, kept alive by hand across streamed scene load and
    /// unload. A postfix hands us __instance for free, is applied once at startup, and covers streamed
    /// and runtime-spawned instances alike.
    ///
    /// Most chosen targets are event listeners, i.e. delegate targets, so their addresses are taken and
    /// they cannot be inlined away. Where a non-listener is also patched it is a backstop only: if it
    /// gets inlined it silently never fires, which costs nothing.
    ///
    /// Covers all five loot categories: Chest and Container (Interact_Bhvr_LootInventory), Pickup
    /// (PickupInteraction), Cache (SpawnFromLootTable), Resource (Interact_Bhvr_ResourceSpot).
    /// </summary>
    public static class ContainerTracker
    {
        /// <summary>How many distinct lootable object types to describe in the log before going quiet.</summary>
        private const int GuidSampleLimit = 40;

        private static ArchipelagoClient _client;

        private static readonly HashSet<string> _sentThisSession = new HashSet<string>(StringComparer.Ordinal);
        private static readonly HashSet<string> _loggedGuids = new HashSet<string>(StringComparer.Ordinal);
        private static int _unmatchedLogged;

        public static void Initialize(ArchipelagoClient archipelagoClient, HarmonyLib.Harmony harmony)
        {
            _client = archipelagoClient;

            // Chests and lootable containers. Interact_Bhvr_LootKnockout inherits both of these and
            // overrides neither, so corpse loot funnels through the same patches.
            HookUtil.TryPostfix(harmony, typeof(Interact_Bhvr_LootInventory),
                nameof(Interact_Bhvr_LootInventory.InventoryOpened),
                typeof(ContainerTracker), nameof(InventoryOpenedPostfix));
            HookUtil.TryPostfix(harmony, typeof(Interact_Bhvr_LootInventory),
                nameof(Interact_Bhvr_LootInventory.InventoryChangedEventListener),
                typeof(ContainerTracker), nameof(InventoryChangedPostfix));

            // Hand-placed ground pickups. InteractionEndedEventListener only fires for loot dropped at
            // runtime (currency, ore); scene-placed pickups such as berries and mushrooms never reach
            // it. Those go through Interact_Bhvr_LootAll instead, which is what Saveable_PickUp_Once
            // (the "WasPicked" record) listens to. Verified in game: dropped loot logged here, plants
            // logged nothing at all.
            HookUtil.TryPostfix(harmony, typeof(PickupInteraction),
                nameof(PickupInteraction.InteractionEndedEventListener),
                typeof(ContainerTracker), nameof(PickupUsedPostfix));
            HookUtil.TryPostfix(harmony, typeof(Saveable_PickUp_Once),
                nameof(Saveable_PickUp_Once.LootAllListener),
                typeof(ContainerTracker), nameof(PickUpOnceLootedPostfix));
            HookUtil.TryPostfix(harmony, typeof(Interact_Bhvr_LootAll),
                nameof(Interact_Bhvr_LootAll.LootAll),
                typeof(ContainerTracker), nameof(LootAllPostfix));

            // Loot-table caches (the ModuleCreator_Destroyable breakables). SpawnFromLootTable sits on
            // the same GameObject as the cache's GuidComponent, so the guid resolves off the SPAWNER.
            // The spawned pickups carry runtime SaveRoot_Dynamic ids and must never be the key.
            HookUtil.TryPostfix(harmony, typeof(SpawnFromLootTable), nameof(SpawnFromLootTable.SpawnLoot),
                typeof(ContainerTracker), nameof(CacheSpawnLootPostfix));
            HookUtil.TryPostfix(harmony, typeof(SpawnFromLootTable),
                nameof(SpawnFromLootTable.OnInteractionUsedEventListener),
                typeof(ContainerTracker), nameof(CacheLootedPostfix));

            // Resource spots (mining veins, fishing spots). Interact_Bhvr_ResourceSpot_AI is a separate
            // class on a separate subtree, so neither of these can fire for NPC harvesting.
            HookUtil.TryPostfix(harmony, typeof(Interact_Bhvr_ResourceSpot),
                nameof(Interact_Bhvr_ResourceSpot.MinigameFinishedEventListener),
                typeof(ContainerTracker), nameof(ResourceMinigameFinishedPostfix));
            HookUtil.TryPostfix(harmony, typeof(Interact_Bhvr_ResourceSpot),
                nameof(Interact_Bhvr_ResourceSpot.GetItems),
                typeof(ContainerTracker), nameof(ResourceGetItemsPostfix));

            MelonLogger.Msg("[AP loot] " + LocationTable.ContainerCount + " world objects mapped to AP locations.");
        }

        public static void OnSaveGameStateLoaded()
        {
            _sentThisSession.Clear();
        }

        private static void InventoryOpenedPostfix(Interact_Bhvr_LootInventory __instance, bool openedbyNpc)
        {
            try
            {
                if (openedbyNpc || __instance == null)
                {
                    return;
                }
                Report(__instance, null, "opened");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] InventoryOpened postfix failed: " + e);
            }
        }

        private static void InventoryChangedPostfix(Interact_Bhvr_LootInventory __instance, InventoryChangedEventArgs arg0)
        {
            try
            {
                if (__instance == null)
                {
                    return;
                }

                // Only an item leaving the container is loot. Added covers the player depositing into a
                // depot, and IsInLoadingStage covers the container being populated on load.
                if (arg0.IsInLoadingStage || arg0.Action != InventoryChangedEventArgs.EAction.Removed)
                {
                    return;
                }

                Report(__instance, null, "looted");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] InventoryChanged postfix failed: " + e);
            }
        }

        /// <summary>
        /// A scene-placed pickup was taken. Saveable_PickUp_Once is the game's own "WasPicked" record,
        /// so this is the authoritative signal for berries, mushrooms and the like.
        /// </summary>
        private static void PickUpOnceLootedPostfix(Saveable_PickUp_Once __instance)
        {
            try
            {
                if (__instance == null)
                {
                    return;
                }
                Report(__instance, null, "pickup once");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] Saveable_PickUp_Once postfix failed: " + e);
            }
        }

        /// <summary>Backstop for the same act, in case the saveable is absent on some pickups.</summary>
        private static void LootAllPostfix(Interact_Bhvr_LootAll __instance)
        {
            try
            {
                if (__instance == null)
                {
                    return;
                }
                Report(__instance, null, "loot all");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] Interact_Bhvr_LootAll postfix failed: " + e);
            }
        }

        private static void PickupUsedPostfix(PickupInteraction __instance)
        {
            try
            {
                if (__instance == null)
                {
                    return;
                }
                Report(__instance, __instance._guid, "pickup");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] PickupInteraction postfix failed: " + e);
            }
        }

        /// <summary>
        /// The cache was broken open. Its contents are rolled randomly from a loot table, so the check
        /// keys off the cache's own guid and never off what happened to drop.
        /// Firing here rather than only on pickup also keeps the location reachable when the roll
        /// produces nothing at all, which would otherwise leave it permanently unsendable.
        /// </summary>
        private static void CacheSpawnLootPostfix(SpawnFromLootTable __instance)
        {
            try
            {
                if (__instance == null)
                {
                    return;
                }
                Report(__instance, null, "cache broken");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] SpawnLoot postfix failed: " + e);
            }
        }

        /// <summary>
        /// A pickup this cache spawned was taken. Listener-shaped, so it cannot be inlined; backstops
        /// SpawnLoot. Still keyed off the spawner's guid, not the spawned pickup's.
        /// </summary>
        private static void CacheLootedPostfix(SpawnFromLootTable __instance)
        {
            try
            {
                if (__instance == null)
                {
                    return;
                }
                Report(__instance, null, "cache looted");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] OnInteractionUsedEventListener postfix failed: " + e);
            }
        }

        private static void ResourceMinigameFinishedPostfix(Interact_Bhvr_ResourceSpot __instance, MinigameFinishedArgs arg0)
        {
            try
            {
                // MinigameFinishedArgs derives from Il2CppSystem.Object, so there is no implicit bool.
                if (__instance == null || arg0 == null || !IsPlayer(arg0.Actor))
                {
                    return;
                }

                // Deliberately not gated on SuccessValue: a failed attempt can still consume a charge,
                // and a spot whose last charge went on a failure would become unreachable.
                Report(__instance, null, "resource worked");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] MinigameFinished postfix failed: " + e);
            }
        }

        /// <summary>
        /// Backstop for a skipped minigame (MinigameModule.SetSkip) that could bypass the finish event.
        /// No Actor is available here, but Interact_Bhvr_ResourceSpot is the player-only class.
        /// </summary>
        private static void ResourceGetItemsPostfix(Interact_Bhvr_ResourceSpot __instance)
        {
            try
            {
                if (__instance == null)
                {
                    return;
                }
                Report(__instance, null, "resource worked");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] GetItems postfix failed: " + e);
            }
        }

        /// <summary>Shared with the trader tracker, which must count only non-player traders.</summary>
        public static bool IsPlayer(Actor actor)
        {
            if (!actor)
            {
                return false;
            }

            EntityGameHandler handler = ProviderAccess.GetEntityGameHandler();
            if (handler == null)
            {
                return false;
            }

            return handler.CheckIsPlayer(actor);
        }

        /// <summary>
        /// True only for a location the current seed actually includes. The loot suppressor must consult
        /// this on top of TryResolveApLocation: the table it matches against holds every location the game
        /// can define, including categories this seed left off, whose containers keep their vanilla loot.
        /// </summary>
        public static bool IsLocationActiveInSeed(string apName)
        {
            return _client != null && _client.IsLocationActiveInSeed(apName);
        }

        /// <summary>
        /// True when this behaviour belongs to an object that is an AP location, with its name.
        /// Shared with the loot suppressor, which must only ever touch randomized containers.
        /// </summary>
        public static bool TryResolveApLocation(Component behaviour, string fallbackGuid, out string apName)
        {
            apName = null;
            List<string> chain = GuidChain(behaviour);
            if (!string.IsNullOrEmpty(fallbackGuid))
            {
                chain.Add(fallbackGuid);
            }

            for (int i = 0; i < chain.Count; i++)
            {
                if (LocationTable.TryGetContainer(chain[i], out apName))
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// Every GuidComponent from the behaviour up to the scene root, nearest first.
        /// GetComponentInParent only returns the nearest, which is wrong wherever GuidComponents nest:
        /// a runtime-spawned child carries its own freshly created guid, while the scene-baked guid
        /// that our table is keyed by lives further up. Verified in game: an ambient crow resolves as
        /// chain=[child-runtime-guid <- crow-baked-guid], and only the second is a location.
        /// </summary>
        public static List<string> GuidChain(Component behaviour)
        {
            List<string> chain = new List<string>();
            try
            {
                if (behaviour == null)
                {
                    return chain;
                }

                Transform node = behaviour.transform;
                while (node)
                {
                    GuidComponent owner = node.GetComponent<GuidComponent>();
                    if (owner)
                    {
                        string guid = owner._guidString;
                        if (!string.IsNullOrEmpty(guid))
                        {
                            chain.Add(guid);
                        }
                    }
                    node = node.parent;
                }
            }
            catch (Exception e)
            {
                MelonLogger.Warning("[AP loot] walking the GuidComponent chain failed: " + e.Message);
            }
            return chain;
        }

        private static void Report(Component behaviour, string fallbackGuid, string source)
        {
            List<string> chain = GuidChain(behaviour);
            if (!string.IsNullOrEmpty(fallbackGuid))
            {
                chain.Add(fallbackGuid);
            }

            // Take the first guid the table knows, not simply the nearest one. A spawned child's own
            // guid is created at runtime and can never be in the table; its scene-baked ancestor can.
            string raw = null;
            string apName = null;
            bool known = false;
            for (int i = 0; i < chain.Count; i++)
            {
                string candidate;
                if (LocationTable.TryGetContainer(chain[i], out candidate))
                {
                    raw = chain[i];
                    apName = candidate;
                    known = true;
                    break;
                }
            }
            if (raw == null && chain.Count > 0)
            {
                raw = chain[0];
            }

            // Log the whole chain, including the no-guid case. Reporting only the nearest guid, and
            // returning silently when there was none, made "the hook never fired", "the object has no
            // guid" and "the guid is a runtime one" all look identical in the log.
            // The budget is keyed by object NAME, not guid: runtime-spawned objects mint a fresh guid
            // on every spawn, so a guid-keyed budget got burned by a handful of boxes and dropped
            // loot and then hid every later object type.
            string owner = behaviour != null && behaviour.gameObject != null ? behaviour.gameObject.name : "<none>";
            string key = source + ":" + owner;
            if (_unmatchedLogged < GuidSampleLimit && _loggedGuids.Add(key))
            {
                _unmatchedLogged++;
                MelonLogger.Msg("[AP loot] guid sample " + _unmatchedLogged + "/" + GuidSampleLimit +
                    ": object='" + owner + "' source=" + source + " matched=" + known +
                    " chain=[" + string.Join(" <- ", chain) + "]" + (chain.Count == 0 ? " (no GuidComponent anywhere in the parent chain)" : ""));
            }

            if (!known)
            {
                // Silent: the overwhelming majority of lootable world objects are not AP locations.
                return;
            }

            // Connected, we know the seed's real location set: drop anything not in it without a
            // misleading "-> sent" line or burning the dedup slot. Offline we cannot tell, so fall
            // through and let CheckLocationByName queue it by name (dropped at flush if inactive).
            if (_client.Connected && !_client.IsLocationActiveInSeed(apName))
            {
                return;
            }

            if (!_sentThisSession.Add(apName))
            {
                return;
            }

            MelonLogger.Msg("[AP loot] " + source + " -> '" + apName + "' (" + raw + ").");
            _client.CheckLocationByName(apName);
        }
    }
}
