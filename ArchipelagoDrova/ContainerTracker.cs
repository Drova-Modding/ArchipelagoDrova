using ArchipelagoDrova.Data;
using Drova_Modding_API.Access;
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
    /// Detection is the Modding API's GameEvents where available, plus three AP-specific backstop
    /// hooks the API does not expose (inventory-changed, cache-broken, minigame-skip).
    /// </summary>
    public static class ContainerTracker
    {
        /// <summary>How many distinct lootable object types to describe in the log before going quiet.</summary>
        private const int GuidSampleLimit = 40;

        private static ArchipelagoClient _client;

        private static readonly HashSet<string> SentThisSession = new(StringComparer.Ordinal);
        private static readonly HashSet<string> LoggedGuids = new(StringComparer.Ordinal);
        private static int _unmatchedLogged;

        public static void Initialize(ArchipelagoClient archipelagoClient, HarmonyLib.Harmony harmony)
        {
            _client = archipelagoClient;

            // Detection comes from the Modding API's GameEvents wherever it has the chokepoint
            // (chests/corpses, pickups, pick-once objects, loot-all, cache-looted, resource
            // minigames). Three AP-specific backstops stay as own hooks below.
            GameEvents.OnLootInventoryOpened += InventoryOpenedEvent;
            GameEvents.OnPickupCollected += PickupUsedEvent;
            GameEvents.OnPickUpOnceLooted += PickUpOnceLootedEvent;
            GameEvents.OnLootedAll += LootAllEvent;
            GameEvents.OnCacheLooted += CacheLootedEvent;
            GameEvents.OnResourceMinigameFinished += ResourceMinigameFinishedEvent;

            // "Looted" (item removed from an open container) - the API only reports the open.
            Drova_Modding_API.Hooking.TryPostfix(harmony, typeof(Interact_Bhvr_LootInventory),
                nameof(Interact_Bhvr_LootInventory.InventoryChangedEventListener),
                typeof(ContainerTracker), nameof(InventoryChangedPostfix));
            // Cache BROKEN (before any pickup): keeps the location reachable when the loot roll
            // produces nothing at all; the API's OnCacheLooted only backstops the pickup.
            Drova_Modding_API.Hooking.TryPostfix(harmony, typeof(SpawnFromLootTable), nameof(SpawnFromLootTable.SpawnLoot),
                typeof(ContainerTracker), nameof(CacheSpawnLootPostfix));
            // Skipped minigames (MinigameModule.SetSkip) bypass the finish event entirely.
            Drova_Modding_API.Hooking.TryPostfix(harmony, typeof(Interact_Bhvr_ResourceSpot),
                nameof(Interact_Bhvr_ResourceSpot.GetItems),
                typeof(ContainerTracker), nameof(ResourceGetItemsPostfix));

            MelonLogger.Msg("[AP loot] " + LocationTable.ContainerCount + " world objects mapped to AP locations.");
        }

        public static void OnSaveGameStateLoaded()
        {
            SentThisSession.Clear();
        }

        private static void InventoryOpenedEvent(Interact_Bhvr_LootInventory container, bool openedByNpc)
        {
            try
            {
                if (openedByNpc || container == null)
                {
                    return;
                }
                Report(container, null, "opened");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] InventoryOpened handler failed: " + e);
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
        private static void PickUpOnceLootedEvent(Saveable_PickUp_Once pickup)
        {
            try
            {
                if (pickup == null)
                {
                    return;
                }
                Report(pickup, null, "pickup once");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] Saveable_PickUp_Once handler failed: " + e);
            }
        }

        /// <summary>Backstop for the same act, in case the saveable is absent on some pickups.</summary>
        private static void LootAllEvent(Interact_Bhvr_LootAll interaction)
        {
            try
            {
                if (interaction == null)
                {
                    return;
                }
                Report(interaction, null, "loot all");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] Interact_Bhvr_LootAll handler failed: " + e);
            }
        }

        private static void PickupUsedEvent(PickupInteraction pickup)
        {
            try
            {
                if (pickup == null)
                {
                    return;
                }
                Report(pickup, pickup._guid, "pickup");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] PickupInteraction handler failed: " + e);
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
        /// A pickup this cache spawned was taken; backstops SpawnLoot. Still keyed off the
        /// spawner's guid, not the spawned pickup's.
        /// </summary>
        private static void CacheLootedEvent(SpawnFromLootTable cache)
        {
            try
            {
                if (cache == null)
                {
                    return;
                }
                Report(cache, null, "cache looted");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] OnCacheLooted handler failed: " + e);
            }
        }

        private static void ResourceMinigameFinishedEvent(Interact_Bhvr_ResourceSpot spot, MinigameFinishedArgs args)
        {
            try
            {
                // MinigameFinishedArgs derives from Il2CppSystem.Object, so there is no implicit bool.
                if (spot == null || args == null || !IsPlayer(args.Actor))
                {
                    return;
                }

                // Deliberately not gated on SuccessValue: a failed attempt can still consume a charge,
                // and a spot whose last charge went on a failure would become unreachable.
                Report(spot, null, "resource worked");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] OnResourceMinigameFinished handler failed: " + e);
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

            var handler = ProviderAccess.GetEntityGameHandler();
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
            return TryResolveApLocation(behaviour, fallbackGuid, out apName, out _);
        }

        /// <summary>
        /// Overload that also hands back the guid the table matched on, which keys the
        /// authored-loot lookup the suppressor uses to strip only vanilla contents.
        /// </summary>
        public static bool TryResolveApLocation(Component behaviour, string fallbackGuid,
            out string apName, out string matchedGuid)
        {
            apName = null;
            matchedGuid = null;
            var chain = GuidChain(KnockoutOwnerOrSelf(behaviour));
            if (!string.IsNullOrEmpty(fallbackGuid))
            {
                chain.Add(fallbackGuid);
            }

            for (int i = 0; i < chain.Count; i++)
            {
                if (LocationTable.TryGetContainer(chain[i], out apName))
                {
                    matchedGuid = chain[i];
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// The knockout loot trigger is Instantiate()d at scene root (BrawlActor.SpawnLootTrigger),
        /// so the mugged NPC's guid is never in the trigger's own transform chain. Resolution is
        /// redirected to the knocked-out actor, whose GuidComponent carries the LazyActor spawner's
        /// stable scene guid (LazyActor stamps it onto the actor at spawn).
        /// </summary>
        private static Component KnockoutOwnerOrSelf(Component behaviour)
        {
            try
            {
                if (behaviour == null)
                {
                    return behaviour;
                }
                var knockout = behaviour.TryCast<Interact_Bhvr_LootKnockout>();
                if (knockout == null)
                {
                    return behaviour;
                }
                var brawl = knockout._actor;
                if (brawl == null)
                {
                    return behaviour;
                }
                var owner = brawl.Entity == null ? null : brawl.Entity.TryCast<Actor>();
                return owner != null ? (Component)owner : behaviour;
            }
            catch (Exception e)
            {
                MelonLogger.Warning("[AP loot] resolving a knockout's owner failed: " + e.Message);
                return behaviour;
            }
        }

        /// <summary>
        /// Every GuidComponent from the behavior up to the scene root, nearest first.
        /// GetComponentInParent only returns the nearest, which is wrong wherever GuidComponents nest:
        /// a runtime-spawned child carries its own freshly created guid, while the scene-baked guid
        /// that our table is keyed by lives further up. Verified in game: an ambient crow resolves as
        /// chain=[child-runtime-guid - crow-baked-guid], and only the second is a location.
        /// </summary>
        public static List<string> GuidChain(Component behaviour)
        {
            var chain = new List<string>();
            try
            {
                if (behaviour == null)
                {
                    return chain;
                }

                var node = behaviour.transform;
                while (node)
                {
                    var owner = node.GetComponent<GuidComponent>();
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
            var chain = GuidChain(KnockoutOwnerOrSelf(behaviour));
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
                if (LocationTable.TryGetContainer(chain[i], out string candidate))
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
            if (_unmatchedLogged < GuidSampleLimit && LoggedGuids.Add(key))
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

            // A multi-item container is worth one check per authored item: the base location plus
            // its extra slot locations (generated from the same guid). All of them fire on the same
            // physical act of opening, so they go through identical gating and dedup per name.
            Send(apName, raw, source);
            if (LocationTable.TryGetContainerSlots(raw, out string[] slotNames))
            {
                for (int i = 0; i < slotNames.Length; i++)
                {
                    Send(slotNames[i], raw, source);
                }
            }
        }

        private static void Send(string apName, string raw, string source)
        {
            // Connected, we know the seed's real location set: drop anything not in it without a
            // misleading "-> sent" line or burning the dedup slot. Offline we cannot tell, so fall
            // through and let CheckLocationByName queue it by name (dropped at flush if inactive).
            if (_client.Connected && !_client.IsLocationActiveInSeed(apName))
            {
                return;
            }

            if (!SentThisSession.Add(apName))
            {
                return;
            }

            MelonLogger.Msg("[AP loot] " + source + " -> '" + apName + "' (" + raw + ").");
            _client.CheckLocationByName(apName);
        }
    }
}
