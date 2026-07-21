using ArchipelagoDrova.Data;
using HarmonyLib;
using Il2CppInterop.Runtime;
using Il2CppOpenWorldSystem;
using MelonLoader;
using UnityEngine;

namespace ArchipelagoDrova
{
    /// <summary>
    /// Entrance randomizer: rewires which cave each cave mouth leads into, per the seed's
    /// slot data ("teleporters": mouth gate name -> interior gate name).
    ///
    /// Drova has no doors between areas - every transition is an OW_Teleporter whose serialized
    /// _targetPos is an authored arrival anchor a few units beside its partner gate. Links are
    /// strict bidirectional pairs, and the shuffle only ever recombines PAIRS: given vanilla
    /// (M1 - I1) and (M2 - I2), the seed may produce (M1 - I2), and both directions are rewired
    /// together. Whatever gate the player enters, the gate they arrive at leads back, so no
    /// placement can strand them. The pool (TeleporterTable.g.cs) already excludes the Red Tower,
    /// the Library, both factions' home interiors and quest dungeons; gates outside the table are
    /// never touched.
    ///
    /// Rewiring means assigning each shuffled gate the arrival anchor of the vanilla gate that
    /// pointed at its new destination - values are copied verbatim from the table, never derived.
    /// Applied on connection to every existing OW_Teleporter (FindObjectsOfTypeAll reaches gates
    /// whose streaming chunk is inactive) and re-applied via an OnEnable postfix, which also covers
    /// gates the chunk streamer activates later. Both writes are idempotent absolute assignments,
    /// so reconnecting to a different room simply overwrites the previous wiring.
    /// </summary>
    public static class TeleporterShuffler
    {
        private sealed class Destination
        {
            public Vector2 TargetPos;
            public Vector2 TargetMoveDir;
        }

        /// <summary>Gate name -> destination to enforce. Null until slot data configures it.</summary>
        private static Dictionary<string, Destination> _destinations;

        public static void Initialize(HarmonyLib.Harmony harmony)
        {
            HookUtil.TryPostfix(harmony, typeof(OW_Teleporter), "OnEnable",
                typeof(TeleporterShuffler), nameof(OnEnablePostfix));
        }

        /// <summary>
        /// Called on every connection with the seed's mouth->interior map (empty = vanilla wiring,
        /// which matters when one session hops from a shuffled room to an unshuffled one).
        /// </summary>
        public static void Configure(Dictionary<string, string> mouthToInterior)
        {
            try
            {
                _destinations = BuildDestinations(mouthToInterior ?? new Dictionary<string, string>());
                ApplyToExistingGates();
            }
            catch (Exception e)
            {
                MelonLogger.Error("TeleporterShuffler.Configure failed: " + e);
            }
        }

        private static Dictionary<string, Destination> BuildDestinations(Dictionary<string, string> mouthToInterior)
        {
            // Start from vanilla for every pool gate so unmapped gates (and a later empty map)
            // always resolve to their authored link.
            var destinations = new Dictionary<string, Destination>();
            foreach (var entry in TeleporterTable.Generated)
            {
                destinations[entry.Key] = new Destination
                {
                    TargetPos = new Vector2(entry.Value.TargetX, entry.Value.TargetY),
                    TargetMoveDir = new Vector2(entry.Value.TargetDirX, entry.Value.TargetDirY),
                };
            }

            int rewired = 0;
            foreach (var pair in mouthToInterior)
            {
                string mouth = pair.Key;
                string interior = pair.Value;
                if (!TeleporterTable.Generated.TryGetValue(mouth, out var mouthGate)
                    || !TeleporterTable.Generated.TryGetValue(interior, out var interiorGate))
                {
                    // A future apworld may know gates this build does not; leaving them vanilla is
                    // the safe direction (the pair stays consistent because both sides are skipped
                    // together - an unknown name can never appear in Generated's partner links).
                    MelonLogger.Warning("Teleporter map names unknown gate '" + mouth + "' -> '" + interior + "'; keeping vanilla.");
                    continue;
                }

                // The mouth must land beside its new interior: exactly where the interior's vanilla
                // partner pointed. The interior must land beside the mouth: where the mouth's
                // vanilla partner pointed. Copied anchors, both directions rewired together.
                // (Partner names are always table members: the generator freezes whole pairs.)
                destinations[mouth] = VanillaDestination(interiorGate.Partner);
                destinations[interior] = VanillaDestination(mouthGate.Partner);
                if (mouth != interiorGate.Partner)
                {
                    rewired++;
                }
            }

            MelonLogger.Msg("Teleporter shuffle configured: " + mouthToInterior.Count + " links, " + rewired + " rewired.");
            return destinations;
        }

        private static Destination VanillaDestination(string gateName)
        {
            var gate = TeleporterTable.Generated[gateName];
            return new Destination
            {
                TargetPos = new Vector2(gate.TargetX, gate.TargetY),
                TargetMoveDir = new Vector2(gate.TargetDirX, gate.TargetDirY),
            };
        }

        private static void ApplyToExistingGates()
        {
            int applied = 0;
            var all = UnityEngine.Resources.FindObjectsOfTypeAll(Il2CppType.Of<OW_Teleporter>());
            foreach (var obj in all)
            {
                var teleporter = obj == null ? null : obj.TryCast<OW_Teleporter>();
                if (teleporter != null && Apply(teleporter))
                {
                    applied++;
                }
            }
            MelonLogger.Msg("Teleporter shuffle applied to " + applied + " gates.");
        }

        private static bool Apply(OW_Teleporter teleporter)
        {
            if (_destinations == null || !_destinations.TryGetValue(teleporter.name, out var destination))
            {
                return false;
            }
            teleporter._targetPos = destination.TargetPos;
            teleporter._targetMoveDir = destination.TargetMoveDir;
            return true;
        }

        private static void OnEnablePostfix(OW_Teleporter __instance)
        {
            try
            {
                Apply(__instance);
            }
            catch (Exception e)
            {
                MelonLogger.Error("Teleporter OnEnable patch failed: " + e);
            }
        }
    }
}
