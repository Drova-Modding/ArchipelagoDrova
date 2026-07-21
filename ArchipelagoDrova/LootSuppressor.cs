using ArchipelagoDrova.Data;
using HarmonyLib;
using Il2CppDrova.InteractionSystem;
using Il2CppDrova.Items;
using Il2CppDrova.InventorySystem;
using MelonLoader;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Empties randomized containers of their vanilla loot, so a check gives you the Archipelago item
    /// instead of the AP item plus the original contents.
    ///
    /// WHY SOME ITEMS ARE NEVER TAKEN: this apworld has no logic. Static extraction proved logic cannot
    /// be derived (Drova's locked doors gate sub-parts of regions that also have unlocked entrances, and
    /// nothing in the shipped data records where those sub-parts end), so the generator is told every
    /// location is reachable from the start. That is only true while the player keeps every vanilla item
    /// progression physically depends on. Suppress a key and the generator may place that key behind the
    /// door it opens, which no other player can rescue: an unbeatable seed.
    ///
    /// So keys, quest items and energy crystals stay. Everything else is fair game. The cost is that the
    /// keys in the AP pool are redundant; the benefit is that seeds cannot break.
    /// </summary>
    public static class LootSuppressor
    {
        private static bool _enabled;

        /// <summary>Set from slot data on the connection. Off unless the seed asks for it.</summary>
        public static bool Enabled
        {
            get { return _enabled; }
            set { _enabled = value; }
        }

        public static void Initialize(HarmonyLib.Harmony harmony)
        {
            // Empty the container BEFORE its loot window is built. The window is created in
            // CreateLootInventory, which reads _ownerInventory to lay out its slots. Stripping in the
            // old InventoryOpened postfix ran AFTER that, tearing items out from under the rendered
            // slot view, so the game logged "Cant find item in Slots" and the window flashed open then
            // shut. A prefix here means the window is built already empty: no desync, clean close.
            // Interact_Bhvr_LootKnockout (corpses) OVERRIDES CreateLootInventory, so both the base and
            // the override must be patched or corpse loot would keep its vanilla contents.
            HookUtil.TryPrefix(harmony, typeof(Interact_Bhvr_LootInventory),
                nameof(Interact_Bhvr_LootInventory.CreateLootInventory),
                typeof(LootSuppressor), nameof(CreateLootInventoryPrefix));
            HookUtil.TryPrefix(harmony, typeof(Interact_Bhvr_LootKnockout),
                nameof(Interact_Bhvr_LootKnockout.CreateLootInventory),
                typeof(LootSuppressor), nameof(CreateLootInventoryPrefix));

            // Quickloot and world pickups hand the contents straight over, so this one has to be a
            // prefix: after LootAll runs the items are already in the player's bag.
            HookUtil.TryPrefix(harmony, typeof(Interact_Bhvr_LootAll), nameof(Interact_Bhvr_LootAll.LootAll),
                typeof(LootSuppressor), nameof(LootAllPrefix));

            // Resource spots (ore veins, fishing spots) put their yield straight into the worker's
            // inventory inside GetItems(Inventory, ITalentModule, float), so the only clean cut is to
            // skip the method. Harmony still runs ContainerTracker's check-sending postfix when a
            // prefix skips the original, so the location fires without the vanilla ore/fish.
            HookUtil.TryPrefix(harmony, typeof(Interact_Bhvr_ResourceSpot),
                nameof(Interact_Bhvr_ResourceSpot.GetItems),
                typeof(LootSuppressor), nameof(ResourceGetItemsPrefix));
        }

        /// <summary>
        /// Items the player must keep for progression to remain physically possible without logic.
        /// Internal: the trader tracker applies the same rule to purchased stock.
        /// </summary>
        internal static bool IsProtected(Item item)
        {
            if (item == null)
            {
                return true;
            }

            // The game's own flag. Cheaper and more reliable than guessing from the id.
            // IsQuestItem is value-derived (buy == 0 && sell == 0); IsInQuestCategory is the authored
            // flag. They disagree on sellable quest gear - the Lyra (buy 200/sell 40, category set) is
            // the instrument the talisman quest's engraving step physically requires - so either flag
            // protects. The static extraction's slot "quest" flag reads IsInQuestCategory, keeping the
            // two sides of the location table consistent.
            if (item.IsQuestItem || item.IsInQuestCategory)
            {
                return true;
            }

            // Items the game authors as keys without the key_ prefix (glyph stones, the Bygones seal
            // stone, quest-gate props). Keys in all but name: suppressing one could lock whatever it
            // opens. Mirrored by slot_is_protected in tools/gen_data.py.
            var category = item.Category;
            if (category != null && category.SubCategory == Il2CppDrova.Items.ItemSubCategory.Misc_Key)
            {
                return true;
            }

            string readableId = item.ReadableId;
            if (string.IsNullOrEmpty(readableId))
            {
                // Unknown identity: keep it. Suppressing something we cannot name is the risky direction.
                return true;
            }

            if (readableId.StartsWith("key_", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
            if (readableId.Equals("misc_key_locked_door", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
            // Charged crystals drive the shrine/energy progression.
            if (readableId.StartsWith("item_energycrystal_", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
            // Riddle offerings (horn, conch, mirror, incense, sundial, ceremonial sword, silver
            // figurines) are keys in all but name: riddle doors and god statues consume them, and
            // whatever they gate can hold randomized locations. Most are NOT quest-flagged (buy
            // 25/sell 5), so without this they would be suppressed and, since they are not in the AP
            // item pool, gone from the seed entirely.
            if (readableId.StartsWith("misc_riddle_", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }

            return false;
        }

        // IInventoryContainer, not Inventory: knocked-out NPCs route their inventory through
        // Init() into _runtimeContainer, and OwnerInventory is the interface-typed union of both.
        //
        // Containers with extracted authored loot are stripped of EXACTLY that loot, nothing more.
        // A container can legitimately hold items that are not vanilla loot: the player uses chests
        // as storage, and both capture sequences (Lothar, bandit mine) stow the player's entire
        // inventory in a chest through DS_TransferInventoryNode. Wiping everything non-protected
        // deleted those. Containers without authored data (corpses, quickloot pickups,
        // random-loot-only chests) keep the old full strip: nothing can be stashed in them between
        // spawn and looting, so everything present is vanilla loot.
        private static void Strip(IInventoryContainer inventory, string apName, string matchedGuid, string source)
        {
            if (inventory == null || inventory.IsEmpty)
            {
                return;
            }

            Dictionary<string, int> authoredLeft = null;
            if (LocationTable.TryGetAuthoredLoot(matchedGuid, out string[] authored))
            {
                authoredLeft = new Dictionary<string, int>(authored.Length, StringComparer.OrdinalIgnoreCase);
                foreach (var entry in authored)
                {
                    int split = entry.LastIndexOf(':');
                    if (split <= 0 || !int.TryParse(entry.Substring(split + 1), out int amount) || amount <= 0)
                    {
                        continue;
                    }
                    string readableId = entry.Substring(0, split);
                    authoredLeft[readableId] = authoredLeft.TryGetValue(readableId, out int have) ? have + amount : amount;
                }
            }

            // Snapshot first: RemoveItem mutates the list we would otherwise be iterating.
            var snapshot = new List<ItemStack>();
            foreach (var stack in inventory.InventoryItems)
            {
                snapshot.Add(stack);
            }

            int removed = 0;
            int kept = 0;
            int foreign = 0;
            foreach (var stack in snapshot)
            {
                if (stack == null || stack.Item == null)
                {
                    continue;
                }

                if (IsProtected(stack.Item))
                {
                    kept++;
                    continue;
                }

                if (authoredLeft != null)
                {
                    string readableId = stack.Item.ReadableId;
                    if (string.IsNullOrEmpty(readableId) ||
                        !authoredLeft.TryGetValue(readableId, out int left) || left <= 0)
                    {
                        foreign++;
                        continue;
                    }
                    int take = Math.Min(left, stack.Amount);
                    inventory.RemoveItem(stack.Item, take, false);
                    authoredLeft[readableId] = left - take;
                    removed++;
                    continue;
                }

                inventory.RemoveItem(stack.Item, stack.Amount, false);
                removed++;
            }

            if (removed > 0 || kept > 0 || foreign > 0)
            {
                MelonLogger.Msg("[AP loot] " + source + " '" + apName + "': suppressed " + removed +
                    " vanilla item(s)" + (kept > 0 ? ", kept " + kept + " progression-critical" : "") +
                    (foreign > 0 ? ", left " + foreign + " non-authored item(s) untouched" : "") + ".");
            }
        }

        /// <summary>
        /// Runs just before the loot window is built (chests, containers and, via the LootKnockout
        /// override, corpses and mugged NPCs), so emptying the container here yields a clean empty
        /// window instead of desyncing an already-rendered slot view. OwnerInventory is populated by
        /// this point: BeginInteraction builds the window view from it right after this call.
        /// </summary>
        private static void CreateLootInventoryPrefix(Interact_Bhvr_LootInventory __instance)
        {
            try
            {
                if (!_enabled || __instance == null)
                {
                    return;
                }

                if (!ContainerTracker.TryResolveApLocation(__instance, null, out string apName, out string guid))
                {
                    // Not a randomized container. Its loot is not ours to take.
                    return;
                }

                if (!ContainerTracker.IsLocationActiveInSeed(apName))
                {
                    // A location in the table but not in this seed (its category is off). There is no AP
                    // item to replace the loot with, so stripping it would just delete the vanilla item.
                    return;
                }

                // OwnerInventory, not _ownerInventory: for knocked-out NPCs the real inventory
                // lives in the runtime container that Init() installed, and _ownerInventory is null.
                Strip(__instance.OwnerInventory, apName, guid, "opened");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] suppressing before the loot window failed: " + e);
            }
        }

        /// <summary>
        /// Bool prefix: returning false skips the vanilla yield entirely. Yields are plain materials
        /// (ore, fish, plants) created inside GetItems, so there is no protected-item concern and
        /// nothing to strip afterward - the items must simply never be created.
        /// </summary>
        private static bool ResourceGetItemsPrefix(Interact_Bhvr_ResourceSpot __instance)
        {
            try
            {
                if (!_enabled || __instance == null)
                {
                    return true;
                }

                if (!ContainerTracker.TryResolveApLocation(__instance, null, out string apName))
                {
                    return true;
                }

                if (!ContainerTracker.IsLocationActiveInSeed(apName))
                {
                    return true;
                }

                MelonLogger.Msg("[AP loot] resource '" + apName + "': suppressed the vanilla yield.");
                return false;
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] suppressing a resource yield failed: " + e);
                return true;
            }
        }

        private static void LootAllPrefix(Interact_Bhvr_LootAll __instance)
        {
            try
            {
                if (!_enabled || __instance == null)
                {
                    return;
                }

                if (!ContainerTracker.TryResolveApLocation(__instance, null, out string apName, out string guid))
                {
                    return;
                }

                if (!ContainerTracker.IsLocationActiveInSeed(apName))
                {
                    // In the table but not in this seed: no AP item to give, so keep the vanilla loot.
                    return;
                }

                // Interop interfaces have no implicit class->interface conversion; Cast goes
                // through the il2cpp type system, where Inventory does implement the interface.
                var lootInventory = __instance.LootInventory;
                Strip(lootInventory == null ? null : lootInventory.Cast<IInventoryContainer>(), apName, guid, "loot all");
            }
            catch (Exception e)
            {
                MelonLogger.Error("[AP loot] suppressing a loot-all failed: " + e);
            }
        }
    }
}
