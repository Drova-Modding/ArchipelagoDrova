# Drova - Forsaken Kin

## Where is the options page?

The [player options page for this game](../player-options) contains all the options you need to configure and export a
config file.

## What is Drova - Forsaken Kin?

Drova - Forsaken Kin is a top-down pixel-art action RPG by Just2D, set in a celtic-inspired world where a resource
called spirit energy powers everything and is running out. You arrive as an outsider, pick a side between the two
settlements of Nemeton and the Remnants, and work out what happened to the old world.

It is an open, gothic-style RPG: no level scaling, no quest markers, and enemies that will kill you if you walk into
them too early.

## What does randomization do to this game?

The contents of the world's containers are replaced with Archipelago items. Which kinds of containers are included is
up to you, since the game has just over 5000 of them and that is far too many for one seed:

- **Chests** (201) and **Containers** (196) are on by default. Together with quests, this makes for a roughly
  450 location seed.
- **Quests** (60) are on by default. Completing a quest sends its check.
- **Resources** (361), **Caches** (978) and **Pickups** (3125) are off by default. Turn these on for a much
  longer game.

Your faction choice matters for generation. Joining a faction permanently locks the other's questline, so only quests
that are neutral or belong to your chosen faction become locations. Pick the faction in your options and stick to it
in-game.

You can also turn buying from merchants into checks (Randomize Traders): each item a trader stocks is a location, so
shopping sends checks. Traders are faction-split like quests, so only your faction's and neutral merchants count.

And you can turn milestones of enemy kills into checks (Enemy Kill Checks). Defeated enemies do not drop Archipelago
items directly, but every so many kills sends a check, so combat itself becomes a source of checks.

## What items can appear in other players' worlds?

Anything Drova has that can be handed to you:

- **Keys** and **charged energy crystals**, which open real content
- **Flow abilities**, the game's combat and utility skills
- **Weapons, armor, helmets and maps**
- **Consumables, recipes and quest items**
- **Experience Boosts** and **Learning Points**

## What does another world's item look like in Drova?

Items belonging to other players are not shown in the world itself. When you open a container or finish a quest that
holds someone else's item, the client sends the check and reports what was found.

## A note on logic

This version of the world ships light item logic: one chest requires its unpickable key, and the Riverbed area
requires Harald's Key (its door is the only way in); every other location is considered reachable from the start,
and the seed is completed by finishing the game. This is deliberate. The remaining key and quest requirements
Drova actually enforces have not been verified yet, and wrong logic produces unbeatable seeds, while absent logic
only means you may occasionally have to come back to a container later.
