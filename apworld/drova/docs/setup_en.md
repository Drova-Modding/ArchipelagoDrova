# Drova - Forsaken Kin Randomizer Setup Guide

## Required Software

- [Drova - Forsaken Kin](https://store.steampowered.com/app/1697590/Drova__Forsaken_Kin/)
- [MelonLoader](https://melonwiki.xyz/#/README) 0.7.3 or newer
- [Drova Modding API](https://github.com/Drova-Modding/Drova-Modding-API/releases/latest)
- [The Drova Archipelago mod](https://github.com/Drova-Modding/ArchipelagoDrova/releases/latest)
- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases/latest), for generating and hosting

## Installation

1. Install MelonLoader and point it at your Drova install. Run the game once so MelonLoader creates its folders,
   then close it.
2. Install the Drova Modding API by putting `Drova_Modding_API.dll` into the game's `Mods/` folder.
3. From the Archipelago mod release, put the two files in their own folders:
   - `ArchipelagoDrova.dll` into `Mods/`
   - `Archipelago.MultiClient.Net.dll` into `UserLibs/`

   Both folders sit next to `Drova.exe`. Do not put both files in the same folder, and do not add any other DLLs from
   the release.
4. Start the game. The MelonLoader console should list ArchipelagoDrova among the loaded mods.

## Joining a MultiWorld Game

First you need a room to connect to. Generating a game is not covered here, see the
[Archipelago Setup Guide](/tutorial/Archipelago/setup_en#generating-a-game).

1. Start Drova and load into a save. A new game works, and so does an existing one, but use a dedicated save for
   your Archipelago run.
2. Connect in one of two ways:
   - Press **F7** in-game to open the Archipelago window, fill in the server address, slot name and password, and
     click Connect.
   - Or open the console and run `ap_connect <host> <port> <slot> [password]`, for example
     `ap_connect archipelago.gg 38281 Player1`.
3. The host takes no scheme and no port. `archipelago.gg` is correct; `ws://archipelago.gg` and
   `archipelago.gg:38281` are not — the port is its own field (or its own console argument).

Your connection details are remembered, so later sessions only need F7 and Connect.

## Playing

Play the game normally. Opening a container or finishing a quest that Archipelago is tracking sends the check
automatically, and items sent to you are added to your inventory as they arrive.

Your progress is stored in the Drova save itself, so loading an older save does not lose items: the mod replays
everything you have received since. Checks made while not connected are stored in the save too and are sent
automatically on the next connect. Beating the game reports your goal to the server.

## Troubleshooting

- **The mod is not listed at startup.** Check that `ArchipelagoDrova.dll` is in `Mods/` and that the Drova Modding API
  is installed. The Archipelago mod will refuse to load without it.
- **Connecting fails or hangs.** Check the host has no scheme (`archipelago.gg`, not `ws://archipelago.gg`), the port
  is in its own field, and the slot name matches the one in your yaml exactly, including case.
- **Nothing happens when I open chests.** Confirm you connected after loading the save, and that the categories you
  expect are enabled in your yaml.
