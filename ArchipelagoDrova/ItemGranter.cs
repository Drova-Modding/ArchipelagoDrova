using Archipelago.MultiClient.Net.Models;
using ArchipelagoDrova.Data;
using Drova_Modding_API.Access;
using Il2CppDrova;
using Il2CppDrova.InventorySystem;
using Il2CppDrova.Items;
using Il2CppDrova.Talent;
using MelonLoader;
using System.Runtime.CompilerServices;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Seam between the AP client and the game. Implementations must be safe to call every frame.
    /// </summary>
    public interface IItemGranter
    {
        /// <summary>
        /// Apply one AP item. Main thread only.
        /// The caller resolves the item name, because doing it from ItemInfo.ItemName throws while
        /// the DataPackage is settling.
        /// Returns false when the game is not ready yet; the pump then leaves the cursor
        /// un-advanced and retries next frame rather than losing the item.
        /// </summary>
        bool TryGrant(ItemInfo item, string name);
    }

    public class ItemGranter : IItemGranter
    {
        private readonly HashSet<string> _warnedNames = new HashSet<string>(StringComparer.Ordinal);

        /// <summary>
        /// Use the player the API handed us through PlayerAccess.OnPlayerFound rather than polling
        /// PlayerAccess.GetPlayer(). GetPlayer goes through EntityGameHandler.TryGet, which throws
        /// inside IL2CPP while the game manager is coming up instead of reporting false, and it can
        /// also return an actor that is not _isInitialized yet. The event waits for both.
        /// </summary>
        private static bool TryGetPlayer(out Actor player)
        {
            player = Core.Player;
            return player;
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        public bool TryGrant(ItemInfo item, string name)
        {
            if (!Core.InGameplayScene)
            {
                return false;
            }

            if (!TryGetPlayer(out var player))
            {
                return false;
            }

            if (string.IsNullOrEmpty(name))
            {
                // The DataPackage has not resolved this id yet. Retry instead of dropping the item.
                return false;
            }

            if (!ItemTable.Items.TryGetValue(name, out var grant))
            {
                if (_warnedNames.Add(name))
                {
                    MelonLogger.Warning("No grant mapping for AP item '" + name + "'; skipping it.");
                }
                // Consume it: an unmapped name would otherwise block the cursor forever.
                return true;
            }

            switch (grant.Kind)
            {
                case GrantKind.Item:
                    return GrantItem(player, grant, name);
                case GrantKind.Talent:
                    return GrantTalent(player, grant, name);
                case GrantKind.Xp:
                    return GrantXp(grant, name);
                case GrantKind.LearningPoint:
                    return GrantLearningPoint(grant, name);
                default:
                    MelonLogger.Error("Unhandled grant kind " + grant.Kind + " for AP item '" + name + "'.");
                    return true;
            }
        }

        // NoInlining: the JIT folds this into TryGrant and the stack trace then blames TryGrant for a
        // fault that happened in here, which makes an interop NRE unattributable.
        [MethodImpl(MethodImplOptions.NoInlining)]
        private bool GrantItem(Actor player, ItemGrant grant, string apName)
        {
            string step = "start";
            try
            {
                // ProviderAccess.ItemDatabase is GetGameDatabase()._itemDatabase, so it throws rather
                // than returning null when the game database is not up yet.
                step = "ProviderAccess.ItemDatabase";
                SubDatabase_Item database = ProviderAccess.ItemDatabase;
                // SubDatabase_Item derives from Il2CppSystem.Object, not UnityEngine.Object,
                // so there is no implicit bool here.
                if (database == null)
                {
                    return false;
                }

                step = "GetItemByReadableId('" + grant.Key + "')";
                Item item = database.GetItemByReadableId(grant.Key);
                if (!item)
                {
                    MelonLogger.Error("AP item '" + apName + "' maps to unknown readable id '" + grant.Key + "'.");
                    return true;
                }

                step = "player.GetInventory()";
                var inventory = player.GetInventory();
                if (!inventory)
                {
                    return false;
                }

                step = "new ItemStack";
                var stack = new ItemStack(item, grant.Amount);

                step = "inventory.AddItem";
                inventory.AddItem(stack, true);

                MelonLogger.Msg("Granted " + grant.Amount + "x " + grant.Key + " (AP item '" + apName + "').");
                return true;
            }
            catch (Exception e)
            {
                if (_warnedNames.Add("grantfail:" + apName))
                {
                    MelonLogger.Error("[AP item] granting '" + apName + "' (readable id '" + grant.Key +
                        "') failed at step [" + step + "]: " + e);
                }
                return false;
            }
        }

        private bool GrantTalent(Actor player, ItemGrant grant, string apName)
        {
            ITalentModule talents = player.TalentActorModule;
            if (talents == null)
            {
                return false;
            }

            talents.ForceLearnTalent(grant.Key);
            MelonLogger.Msg("Granted talent " + grant.Key + " (AP item '" + apName + "').");
            return true;
        }

        /// <summary>Same guarded pattern as TryGetPlayer: the handler lookup can throw, not just return null.</summary>
        private static bool TryGetStats(out PlayerAttributeStats stats)
        {
            stats = null;
            try
            {
                stats = PlayerAccess.GetPlayerAttributeStats();
            }
            catch
            {
                return false;
            }
            return stats;
        }

        private bool GrantXp(ItemGrant grant, string apName)
        {
            PlayerAttributeStats stats;
            if (!TryGetStats(out stats))
            {
                return false;
            }

            stats.AddExperiencePoints(grant.Amount);
            MelonLogger.Msg("Granted " + grant.Amount + " XP (AP item '" + apName + "').");
            return true;
        }

        private bool GrantLearningPoint(ItemGrant grant, string apName)
        {
            if (!TryGetStats(out var stats))
            {
                return false;
            }

            stats.GiveLearningPoint(grant.Amount);
            MelonLogger.Msg("Granted " + grant.Amount + " learning point(s) (AP item '" + apName + "').");
            return true;
        }
    }
}
