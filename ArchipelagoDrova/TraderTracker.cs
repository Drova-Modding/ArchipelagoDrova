using ArchipelagoDrova.Data;
using HarmonyLib;
using Il2CppDrova;
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

        private static readonly HashSet<string> _sentThisSession = new HashSet<string>(StringComparer.Ordinal);

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
                Actor trader = __instance._actor;
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
                List<string> chain = ContainerTracker.GuidChain(trader);
                string apName = null;
                for (int i = 0; i < chain.Count; i++)
                {
                    if (LocationTable.TryGetTraderSlot(chain[i], itemGuid, out apName))
                    {
                        break;
                    }
                }

                if (apName == null)
                {
                    return;
                }

                if (!_sentThisSession.Add(apName))
                {
                    return;
                }

                MelonLogger.Msg("[AP trader] bought -> '" + apName + "'.");
                _client.CheckLocationByName(apName);
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP trader] RemoveItemFromTrader postfix failed: " + e);
            }
        }
    }
}
