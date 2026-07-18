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

        /// <summary>Connected slot name. Other authoritative half of the save stamp.</summary>
        public string SlotName { get; set; } = "";

        public int Slot { get; set; } = -1;

        /// <summary>Count of AP items already granted. Never decreases.</summary>
        public int ApItemsApplied { get; set; } = 0;

        public List<long> CheckedLocations { get; set; } = new List<long>();

        /// <summary>
        /// Location names checked while no session was available. Names, not ids: resolving a name to
        /// its id needs the server's datapackage, which only a live session can provide. Flushed and
        /// emptied on the next successful connection.
        /// </summary>
        public List<string> PendingLocationNames { get; set; } = new List<string>();

        /// <summary>
        /// Total enemies defeated on this save. Monotonic; the enemy-kill milestone locations
        /// ("Enemy Kills - k") are sent when it reaches k * interval (interval comes from slot data).
        /// </summary>
        public int EnemyKills { get; set; } = 0;

        /// <summary>True, once the outro was reached. Set even when the send fails, so it can be retried.</summary>
        public bool GoalReached { get; set; } = false;

        /// <summary>True, only after the server accepted the goal.</summary>
        public bool GoalSent { get; set; } = false;
    }
}
