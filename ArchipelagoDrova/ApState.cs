namespace ArchipelagoDrova
{
    /// <summary>
    /// Everything the mod persists inside the Drova save game.
    /// <see cref="ApItemsApplied"/> is the index cursor into ArchipelagoSession.Items.AllItemsReceived:
    /// the item queue is not idempotent across reconnections, the cursor is.
    /// </summary>
    public class ApState
    {
        /// <summary>AP seed name from slot data when the world provides one, otherwise the room seed.</summary>
        public string SeedName { get; set; } = "";

        /// <summary>ArchipelagoSession.RoomState.Seed. Authoritative half of the save stamp.</summary>
        public string RoomSeed { get; set; } = "";

        /// <summary>Connected slot name. Another authoritative half of the save stamp.</summary>
        public string SlotName { get; set; } = "";

        public int Slot { get; set; } = -1;

        /// <summary>Count of AP items already granted. Never decreases.</summary>
        public int ApItemsApplied { get; set; }

        public List<long> CheckedLocations { get; set; } = [];

        /// <summary>
        /// Location names checked while no session was available. Names, not ids: resolving a name to
        /// its id needs the server's data package, which only a live session can provide. Flushed and
        /// emptied on the next successful connection.
        /// </summary>
        public List<string> PendingLocationNames { get; set; } = new();

        /// <summary>
        /// Total enemies defeated on this save. Monotonic; the enemy-kill milestone locations
        /// ("Enemy Kills - k") are sent when it reaches k * interval (an interval comes from slot data).
        /// </summary>
        public int EnemyKills { get; set; }

        /// <summary>Attribute points bought by teachers. Monotonic; drives "Attributes Learned - k".</summary>
        public int AttributesLearned { get; set; }  

        /// <summary>Talents learned from teachers/dialogue. Monotonic; drives "Talents Learned - k".</summary>
        public int TalentsLearned { get; set; }

        /// <summary>
        /// Cumulative units bought per trader slot ("traderGuid:itemGuid" -> count). Trader slots
        /// with a stock stack are several locations (base + "- Unit 2..K"); this cursor decides
        /// which unit the next purchase checks. Monotonic, survives restocking and reconnects.
        /// </summary>
        public Dictionary<string, int> TraderUnitsBought { get; set; } = new();

        /// <summary>True, once the outro was reached. Set even when the sending fails, so it can be retried.</summary>
        public bool GoalReached { get; set; }

        /// <summary>True, only after the server accepted the goal.</summary>
        public bool GoalSent { get; set; }
    }
}
