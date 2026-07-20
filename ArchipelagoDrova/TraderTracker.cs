using ArchipelagoDrova.Data;
using HarmonyLib;
using Il2CppDrova;
using Il2CppDrova.Items;
using Il2CppDrova.TradingSystem;
using Il2CppTradingSystem.ItemContainers;
using MelonLoader;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Turns buying an item from a merchant into an AP location check. Trader stock is authored at
    /// design time (Inventory_Trading._tradingItems), so unlike runtime enemy drops each slot has a
    /// stable identity: the trader's scene-baked guid plus the item's guid. The extractor freezes that
    /// pair; here the same pair is resolved at purchase time.
    ///
    /// Hook: postfix on TraderActorAdapter.RemoveItemFromTrader, which fires exactly once per bought
    /// stack inside MarketPlace.CompleteTrading and never on hover/preview/drag. The same method also
    /// fires on the player-side adapter when the player SELLS, so a purchase is distinguished by the
    /// adapter's actor not being the player.
    /// </summary>
    public static class TraderTracker
    {
        private static ArchipelagoClient _client;

        private static readonly HashSet<string> _sentThisSession = new(StringComparer.Ordinal);

        private struct PendingRemoval
        {
            public Item Item;
            public int Amount;
            public string ApName;
        }

        // Purchases to claw back under suppress_vanilla_loot. Deferred one frame: at
        // RemoveItemFromTrader time CompleteTrading may not have handed the goods to the player yet,
        // so removing immediately could miss them.
        private static readonly List<PendingRemoval> _pendingRemovals = new();

        public static void Initialize(ArchipelagoClient archipelagoClient, HarmonyLib.Harmony harmony)
        {
            _client = archipelagoClient;

            HookUtil.TryPostfix(harmony, typeof(TraderActorAdapter),
                nameof(TraderActorAdapter.RemoveItemFromTrader),
                typeof(TraderTracker), nameof(RemoveItemFromTraderPostfix));

            MelonLogger.Msg("[AP trader] " + LocationTable.TraderSlotCount + " trader slots mapped to AP locations.");
        }

        public static void OnSaveGameStateLoaded()
        {
            _sentThisSession.Clear();
            _pendingRemovals.Clear();
        }

        /// <summary>Called from Core.OnUpdate: applies the deferred purchase clawbacks.</summary>
        public static void Pump()
        {
            if (_pendingRemovals.Count == 0)
            {
                return;
            }

            var player = Core.Player;
            if (!player)
            {
                _pendingRemovals.Clear();
                return;
            }
            var inventory = player.GetInventory();
            if (!inventory)
            {
                _pendingRemovals.Clear();
                return;
            }

            foreach (var pending in _pendingRemovals)
            {
                try
                {
                    inventory.RemoveItem(pending.Item, pending.Amount, false);
                    MelonLogger.Msg("[AP trader] '" + pending.ApName + "': suppressed the purchased vanilla item.");
                }
                catch (Exception e)
                {
                    MelonLogger.Error("[AP trader] clawing back a purchase for '" + pending.ApName + "' failed: " + e);
                }
            }
            _pendingRemovals.Clear();
        }

        private static void RemoveItemFromTraderPostfix(TraderActorAdapter __instance, ItemTraderStack itemStack)
        {
            try
            {
                if (__instance == null || itemStack == null)
                {
                    return;
                }

                // Only a non-player trader losing stock is a buy; the player-side adapter fires on sells.
                var trader = __instance._actor;
                if (!trader || ContainerTracker.IsPlayer(trader))
                {
                    return;
                }

                string itemGuid = itemStack.Id;
                if (string.IsNullOrEmpty(itemGuid))
                {
                    return;
                }

                // Match the first (traderGuid, itemGuid) pair the table knows, walking the trader's guid
                // chain the same way containers do so a nested runtime guid cannot mask the scene guid.
                var chain = ContainerTracker.GuidChain(trader);
                string apName = null;
                string slotKey = null;
                for (int i = 0; i < chain.Count; i++)
                {
                    if (LocationTable.TryGetTraderSlot(chain[i], itemGuid, out apName, out slotKey))
                    {
                        break;
                    }
                }

                if (apName == null)
                {
                    return;
                }

                // A stocked slot is several locations (base + "- Unit 2..K"). The persisted cursor
                // decides which unit this purchase reaches, so buying 3 sends the next 3 unchecked
                // units, restocks continue where the last purchase stopped, and everything past the
                // last unit is ordinary vanilla shopping.
                int bought = itemStack.Amount > 0 ? itemStack.Amount : 1;
                string[] extraUnits = LocationTable.GetTraderUnitNames(slotKey);
                int totalUnits = 1 + (extraUnits?.Length ?? 0);

                var store = Core.Store;
                int already = 0;
                if (store != null && !store.Mismatched)
                {
                    store.State.TraderUnitsBought.TryGetValue(slotKey, out already);
                }

                int newChecks = 0;
                for (int unit = already; unit < already + bought && unit < totalUnits; unit++)
                {
                    string unitName = unit == 0 ? apName : extraUnits[unit - 1];
                    if (!_sentThisSession.Add(unitName))
                    {
                        continue;
                    }
                    MelonLogger.Msg("[AP trader] bought -> '" + unitName + "'.");
                    _client.CheckLocationByName(unitName);
                    newChecks++;
                }

                if (store != null && !store.Mismatched && already < totalUnits)
                {
                    store.State.TraderUnitsBought[slotKey] = Math.Min(already + bought, totalUnits);
                    _client.MarkStatePersistDirty();
                }

                // Under suppression a shop slot sells CHECKS: one purchased unit is clawed back per
                // check this purchase sent (the money is spent regardless, like every
                // shop-randomizer). Units beyond the checks - and anything after the last unit
                // location - stay in the player's bag as ordinary bought goods.
                if (newChecks > 0 && LootSuppressor.Enabled && ContainerTracker.IsLocationActiveInSeed(apName))
                {
                    var boughtItem = itemStack.GetItem();
                    if (boughtItem && !LootSuppressor.IsProtected(boughtItem))
                    {
                        PendingRemoval pending;
                        pending.Item = boughtItem;
                        pending.Amount = newChecks;
                        pending.ApName = apName;
                        _pendingRemovals.Add(pending);
                    }
                }
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP trader] RemoveItemFromTrader postfix failed: " + e);
            }
        }
    }
}
