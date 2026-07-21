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

    /// <summary>Mirror of the apworld's consumable_stack_size option keys.</summary>
    public enum ConsumableStackSize
    {
        Full,
        Small,
        Single,
    }

    public class ItemGranter : IItemGranter
    {
        /// <summary>Set from slot data on connect. Full matches the generated table amounts.</summary>
        public static ConsumableStackSize StackSize = ConsumableStackSize.Full;

        private readonly HashSet<string> _warnedNames = new(StringComparer.Ordinal);

        // Consumable chunks vary per grant so 20 arrows is a nominal size, not a metronome.
        private readonly Random _amountRoll = new();

        /// <summary>
        /// Stackable grants (amount > 1) vary uniformly between 50% and 150% of the (option-scaled)
        /// table amount, minimum 1. Single-unit grants (gear, recipes, quest items) always stay
        /// exactly 1. "single" skips the variance: it grants a flat 1, except ammo-sized stacks
        /// (table amount >= 10: arrows, bolts, throwables) which grant a flat 5 - one arrow per
        /// check is not a reward.
        /// </summary>
        private int RollAmount(int tableAmount)
        {
            if (tableAmount <= 1)
            {
                return tableAmount;
            }
            switch (StackSize)
            {
                case ConsumableStackSize.Single:
                    return tableAmount >= 10 ? 5 : 1;
                case ConsumableStackSize.Small:
                    tableAmount = Math.Max(2, (tableAmount + 1) / 2);
                    break;
            }
            int low = Math.Max(1, (tableAmount + 1) / 2);
            int high = tableAmount + tableAmount / 2;
            return _amountRoll.Next(low, high + 1);
        }

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
                case GrantKind.Attribute:
                    return GrantAttribute(grant, name);
                case GrantKind.MaxHealth:
                    return GrantMaxHealth(player, grant, name);
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
                var database = ProviderAccess.ItemDatabase;
                // SubDatabase_Item derives from Il2CppSystem.Object, not UnityEngine.Object,
                // so there is no implicit bool here.
                if (database == null)
                {
                    return false;
                }

                step = "GetItemByReadableId('" + grant.Key + "')";
                var item = database.GetItemByReadableId(grant.Key);
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

                int amount = RollAmount(grant.Amount);

                step = "new ItemStack";
                var stack = new ItemStack(item, amount);

                step = "inventory.AddItem";
                inventory.AddItem(stack, true);

                MelonLogger.Msg("Granted " + amount + "x " + grant.Key + " (AP item '" + apName + "').");
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
            var talents = player.TalentActorModule;
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
            if (!TryGetStats(out var stats))
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

        /// <summary>
        /// Permanent attribute raise through the same path the game's perma-potions and trainers
        /// use (ImproveAttribute), so the perma-stat thresholds fire exactly like vanilla.
        /// </summary>
        private bool GrantAttribute(ItemGrant grant, string apName)
        {
            if (!TryGetStats(out var stats))
            {
                return false;
            }

            GenericStatDesc desc;
            try
            {
                var container = GlobalStatsSettings.GetStatContainer();
                if (container == null)
                {
                    return false;
                }
                switch (grant.Key)
                {
                    case "strength":
                        desc = container.StrengthStat;
                        break;
                    case "dexterity":
                        desc = container.DexStat;
                        break;
                    case "mind":
                        desc = container.MindStat;
                        break;
                    default:
                        MelonLogger.Error("Unknown attribute '" + grant.Key + "' for AP item '" + apName + "'.");
                        return true;
                }
            }
            catch
            {
                // The stats container is not up yet; retry on the next pump.
                return false;
            }

            if (desc == null)
            {
                return false;
            }

            stats.ImproveAttribute(desc, grant.Amount);
            MelonLogger.Msg("Granted +" + grant.Amount + " " + grant.Key + " (AP item '" + apName + "').");
            return true;
        }

        private bool GrantMaxHealth(Actor player, ItemGrant grant, string apName)
        {
            var health = player.GetHealth();
            if (health == null)
            {
                return false;
            }

            health.ChangeMaxHealth(grant.Amount, true);
            MelonLogger.Msg("Granted +" + grant.Amount + " max health (AP item '" + apName + "').");
            return true;
        }
    }
}
