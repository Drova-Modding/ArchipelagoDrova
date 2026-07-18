# ArchipelagoDrova

An [Archipelago](https://archipelago.gg) multiworld randomizer for **Drova - Forsaken Kin**.

> **Just want to play?** Grab the release files, drop them in your game and Archipelago folders
> ([Install](#install)), then press **F7** in game to connect ([Connect](#connect)). To build a seed,
> copy the [YAML example](#configure-your-seed-yaml) and pick your options.

---

# For players

## Install

The [Releases page](https://github.com/Drova-Modding/ArchipelagoDrova/releases) has three downloads for
two audiences. **Everyone who plays** needs only the mod zip. **Whoever generates the seed** (one person
per game) also needs the apworld and a YAML — those go in the *Archipelago* app, which is separate from
the game.

### To play (join a room)

Download `ArchipelagoDrova-v*.zip`. It contains only game files:

```
Mods/       ArchipelagoDrova.dll
UserLibs/   Archipelago.MultiClient.Net.dll
README.md
```

Your **game folder** is where `Drova.exe` lives. On Steam: right-click **Drova - Forsaken Kin** →
**Manage** → **Browse local files**.

1. Install [MelonLoader](https://melonwiki.xyz) into the game folder (choose the **IL2CPP** path).
   Verified against 0.7.3. This creates the `Mods/` and `UserLibs/` folders.
2. Install the [Drova Modding API](https://github.com/Drova-Modding/Drova-Modding-API/releases/latest):
   download its `Drova_Modding_API.dll` and put it in `<game>/Mods/`. (It's a separate project, not
   bundled here.)
3. Unzip this mod and merge its `Mods/` and `UserLibs/` folders into the game folder. A mod manager like
   **Vortex** can install the zip for you — it deploys straight into the game root.

Launch once; MelonLoader shows a console confirming the mods loaded. Then [connect](#connect) to a room.

### To generate a seed (one person per game)

The apworld and sample config go in your **Archipelago install** (a separate program from the game).
Easiest: download **`ArchipelagoDrova-Archipelago-v*.zip`** and unzip it into your Archipelago **root** —
it places both files for you:

```
custom_worlds/  drova.apworld
Players/        Drova - Forsaken Kin.yaml
```

(Or grab the bare **`drova.apworld`** and drop it in `custom_worlds/` yourself.) Then edit the YAML —
see [Configure](#configure-your-seed-yaml).

Generate locally with Archipelago's `Generate.py`, then either host the result yourself or upload it to
[archipelago.gg](https://archipelago.gg)'s **Host Game** page. archipelago.gg can *host* a Drova seed but
cannot *generate* one — custom worlds are always generated locally.

## Connect

In game, press **F7** for the connection panel, or use the console command:

```
ap_connect <host> <port> <slot> [password]
```

Settings persist to `<game>/UserData/ArchipelagoDrova/config.json`, so you only enter them once.

## Configure your seed (YAML)

Options are set in your player YAML. The release includes a ready-to-edit
`Drova - Forsaken Kin.yaml`; drop it in your Archipelago `Players/` folder and edit. It looks like this:

```yaml
name: YourName
game: Drova - Forsaken Kin
Drova - Forsaken Kin:
  # Story
  faction: nemeton            # nemeton | ruinenlager (alias: remnants)

  # Location pool (which things become checks)
  randomize_chests: true      # 201 lockable chests
  randomize_containers: true  # 196 barrels, crates, sacks
  randomize_quests: true      # 60 quest completions (minus the faction you didn't join)
  randomize_critters: false   # 134 wildlife / carcasses
  randomize_resources: false  # 361 ore veins, herbs
  randomize_caches: false     # 978 hidden caches
  randomize_pickups: false    # 3125 loose world items (very long seed)
  randomize_traders: false    # ~890 merchant slots (faction-split)
  enemy_kill_checks: 0        # 0-50 kill milestones (0 = off)
  enemy_kill_interval: 10     # kills between each milestone

  # Gameplay
  suppress_vanilla_loot: true # true = only the AP item; false = AP item + vanilla loot (easier)

  death_link: false
```

Two presets are also available: `minimal` (chests only) and `completionist` (every loot toggle on).

## What gets randomized

**Locations** — 5055 total; how many are in *your* seed depends on the toggles above.

| Category | Count | Default | What it is |
|---|---:|---|---|
| Chest | 201 | on | chests |
| Container | 196 | on | crates, barrels, lootable props |
| Quest | 60 | on | a quest reaching `IsCompleted` |
| Critter | 134 | off | ambient wildlife and carcasses (crows, birds, dead boars) |
| Resource | 361 | off | ore veins, fishing spots |
| Cache | 978 | off | breakable loot-table caches |
| Pickup | 3125 | off | loose world items: herbs, berries, ore |
| Trader | 890 | off | buying an item from a merchant (faction-split) |

Defaults give **453** locations. Enabling every toggle gives roughly 5600 for one faction (both
factions' quests and traders never coexist in a seed), which is a *lot* of hunting: Pickup alone is
3125, and Critter can put a dozen checks in one bush.

**Enemy kills** are a separate, count-based category (`enemy_kill_checks`, default 0, up to 50). With
N enabled, `Enemy Kills - k` is sent when your total kills reach `k * enemy_kill_interval`. These are
reached just by playing, so they never gate anything. A kill only counts when the player lands the
final blow — critters, NPC-vs-NPC and environmental deaths don't count, and kills from summons or
damage-over-time are undercounted (never double-counted).

**Items** (805): 62 progression (15 keys, 3 charged energy crystals, 43 player flow abilities),
221 useful (weapons, armor, helmets, maps), 522 filler (consumables, recipes, quest items), plus
experience and learning point grants.

**Goal**: reach the outro. Dying does not route through the outro, so it cannot trigger a false goal.

## Factions

Drova forks between Nemeton and the Remnants (Ruinenlager); joining one locks the other's questline
**and its merchants**. The `faction` YAML option commits you up front, and only that faction's quests
and traders, plus neutral ones, become locations.

## Vanilla loot

By default (`suppress_vanilla_loot: true`) a randomized container hands you **only** the Archipelago
item, the way most randomizers behave. Set it to `false` and a container gives you **both** its vanilla
contents and the Archipelago item — the pool is duplicated rather than relocated, making the seed easier
and more forgiving.

Either way, **keys, quest items and energy crystals are always kept.** This world has almost no logic
(see below): the generator is told nearly every location is reachable from the start, which is only true
while you still find the vanilla items progression physically depends on. Suppressing a key could place
it behind the very door it opens — an unbeatable seed — so those items are never stripped.

NPC quest rewards, crafting and vanilla XP are never suppressed. A quest's check fires when its state
reaches `IsCompleted`, not when the reward changes hands.

---

# For contributors and maintainers

## Project layout

Two halves that must agree on ids, plus the pipeline that keeps them aligned:

- **`ArchipelagoDrova/`** — the in-game client. A MelonLoader mod for the IL2CPP build, built on the
  [Drova Modding API](https://github.com/Drova-Modding/Drova-Modding-API).
- **`apworld/drova/`** — the Archipelago generation side (Python), which produces seeds.
- **`tools/`** — the data pipeline that feeds both, so their ids can never drift.

**Do not ship `Newtonsoft.Json.dll`.** MelonLoader already provides 13.0.4, and the .NET runtime binds
it to the AP client's reference to v11 (it resolves already-loaded assemblies by simple name, ignoring
version and public key token). A second copy is at best inert.

## Building the apworld

Use Archipelago's own builder from an Archipelago source checkout. Do **not** zip the folder by hand:
the builder is what stamps `version` / `compatible_version` into the manifest, and a hand-made zip is
rejected at load with `Invalid or missing manifest file`.

```
copy apworld\drova  ->  <archipelago-source>\worlds\drova
python Launcher.py "Build APWorlds" -- "Drova - Forsaken Kin"
# -> build/apworlds/drova.apworld
```

Never load the folder and the `.apworld` at the same time. Archipelago will try to register the game twice.

## Cutting a release

A **Release** build of the C# project bundles the whole player-facing package automatically:

```
dotnet build ArchipelagoDrova\ArchipelagoDrova.csproj -c Release
# -> release/ArchipelagoDrova-v<version>.zip
```

The zip mirrors where files go (`Mods/`, `UserLibs/`, `drova.apworld`, the sample YAML, this README).
`drova.apworld` is **not committed** (it's a build artifact, gitignored to avoid drift). The pack
target does **not** rebuild it — it copies the `drova.apworld` at the repo root and **errors if it is
missing** — so build it first (see [Building the apworld](#building-the-apworld)), and rebuild it
whenever generation data changed. Bump `ReleaseVersion` in the csproj to match `world_version` in
`archipelago.json` before tagging.

Knobs (all optional):

- `-p:BundleRelease=true` — force the bundle on a Debug build (or `=false` to skip it on Release).
  (Named `BundleRelease`, not `PackRelease`: the latter is a reserved .NET SDK property.)
- `-p:BundleDrovaApi=false` — ship without the third-party `Drova_Modding_API.dll` (on by default).
- `-p:ReleaseVersion=X.Y.Z` — override the version in the zip name.

Debug builds skip packing and keep the fast deploy-to-game behavior (copies the DLLs straight into
`$(GamePath)`).

## Regenerating the data

Game ids can shift when Drova updates. To rebuild:

```
python tools/gen_data.py
```

It reads `tools/extracted/` and writes `apworld/drova/data/*.json` plus the generated C# tables.

Location and item ids are assigned from **frozen, append-only maps** in `tools/frozen/`, keyed by the
stable game identity (`Item.ReadableId` / `GuidComponent._guidString`) rather than by name or list order.
Existing ids are never renumbered, so renaming a location cannot invalidate an existing seed. These files
are committed on purpose. Do not edit them by hand.

`tools/extract_locations/` re-extracts the container table from the shipped asset bundles (requires
`pip install UnityPy`, takes ~4 minutes). Drova's bundles retain typetrees, so field names are read
directly with no Il2CppDumper step.

## Trader extraction

`randomize_traders` turns buying an item from a merchant into a check: 890 slots across 46 traders
(nemeton 402, ruinenlager 301, neutral 187). Trader stock is authored, not loot-rolled, so each slot
is a real location with stable identity — the merchant's scene-baked guid plus the item's guid, the
key both `tools/extract_locations/extract_traders.py` and the client's `TraderTracker` resolve.

Recovering it is a two-asset join the container extractor doesn't do: the stock lives on the merchant
prefab (`Inventory_Trading._tradingItems`) while the stable guid lives on the scene `LazyActor` that
spawns it, joined on the addressables AssetGUID. Faction is inferred from the LazyActor's world
position (the same area polygons quests use); the two settlement areas are `Nemeton`/`EntryNemeton`
and `Ruins`, with six shared biomes neutral. **This attribution is the one thing worth a playtest:** a
merchant mis-tagged neutral that is really faction-locked would create an unreachable location under
the other faction. Money slots and duplicate chapter variants are dropped; runtime "secret" stock and
dialogue-added items are not covered.

## Logic and locks: mostly no logic

101 locations carry playtest-confirmed key rules (see `rules.py`): `Wilds 18_29 - Chest 1` requires
`Key Chest BanditCamp`, and the 100 Riverbed locations require `Key Harald` (its door is the sole
entrance; the vanilla key is handed out by an NPC just outside, so the gate is always beatable).
Everything else is reachable from the start, so the remaining progression items are currently just
items.

This is not an oversight, and broader per-chest key logic is a dead end. `Interact_Condition_Locked` was
extracted from every bundle (267 locks; `tools/extracted/locks.json`) and the signal does not support gating:

- The 201 locks map exactly onto the 201 `Chest` locations, one to one.
- **165 of 201 have no key at all**, and **200 of 201 have `_canLockpick = true`**, so the key is optional.
- **34 of the 36 keyed chests want `misc_key_locked_door`**, a generic key used by 69 locks game-wide and
  consumed on use (`_removeKey`). One copy in the pool cannot open 34 chests. Gating on it is unsound.
- `Talent_Lockpicking` is learned in game with learn points, so the bypass is not AP-controlled either.

**Exactly one location is genuinely key-gated**: `Wilds 18_29 - Chest 1` needs `key_chest_BanditCamp` and
cannot be picked. That single verified rule now ships (`rules.py:VERIFIED_CHEST_KEY_RULES`). Getting
`misc_key_locked_door` into logic would be wrong for the reasons above: a wrong rule is worse than no rule.

**The real lead is doors, not chests.** The 13 unique keys (`key_ratcellar`, `key_harald`,
`key_ruinenexplorer`, ...) gate 66 doors and trapdoors, 21 of them hard gates with no lockpick. That is
region-access logic: the payoff is whatever locations sit behind each door.

The door-lock data is now committed: `tools/extract_locations/extract_doors.py` sweeps the bundles
for every `Interact_Condition_Locked` (267 locks: the 201 chest locks byte-identical to `locks.json`,
65 doors, 27 hard, 21 of those keyed) into `tools/extracted/door_locks.json`. Each locked door is then
attributed to the area it gates, against the same area polygons the quests use.

The extraction proposed several door candidates from static adjacency; each was walked in-game before
any rule shipped. Only one survived: **`Key Harald` gates the
100 Riverbed locations** — its door is the only way in, confirmed in game — so that rule ships
(`rules.py:DOOR_KEY_RULES`). Every other candidate was **rejected** for a reason static door-to-boundary
adjacency could not see: Dark Quarter (`key_ruinenexplorer`) and Tavern (`key_tavernKey`) have other
entrances; Rat Cellar (`key_ratcellar`) has a hidden opening and is quest-gated; Mine Bandit
(`key_chest_mineBanditMainKey`) can be entered by bandit capture and also needs all bandits killed;
Brutus (`item_brutus_seal_active`) is a one-way door with its nearby locations on the outside. Of the
keys that never needed a walk: harvey, tristanBill, mursel_mine, ShadyDistrict, tavernKey_Cellar and
sleepingTavernKey open pickable locks (no logic), and extractor and mineBanditEntry are used by no lock
at all. **The lesson: static extraction can propose door gates but cannot confirm them — five of six
plausible candidates had a bypass. A walkability check is mandatory before a door rule ships.**

## Excluded on purpose

Anything created at runtime cannot be a location, because its identity does not exist when the seed is
generated. That covers dropped loot, spawned enemies, crafted items and the `Box_Destructable_*`
breakables (which mint a fresh guid on every spawn). Ten `Corpse_Stalker` carcasses are also excluded:
they report loot but carry no inventory component, so they can never be opened. Anything whose faction
could not be *proven* is excluded rather than guessed at, because an unreachable location breaks seed
generation.

## Interop notes

Things that are true and cost real time to discover:

- **Quest state.** Read it via the non-generic virtual `AGVarBase.GetGenericValue()` and unbox. Never touch
  `AGEnum<T>.Comparer`, `._operator`, or `._compare`: nested enums inside an open generic throw on
  late-bound static field reads. Nested *structs* like `AGVar<T>.ChangeArgs` are fine. This asymmetry is
  the trap behind most "cannot read quest state" reports.
- **Missing IL2CPP method bodies do not throw.** They return a fabricated dummy with `MethodPointer == 0`,
  and calling it can hard-crash. Preflight before invoking a typed generic method.
- **Never apply AP items from the socket callback.** Every Archipelago callback runs on a ThreadPool
  thread; touching IL2CPP there corrupts the runtime. Marshal through `MainThreadDispatcher.Enqueue`.
- **Do not use the received-items queue.** Archipelago replays the entire item history on every reconnect,
  and the client library's own dedup guard never fires because `ItemInfo` does not override `Equals`. Use
  the save-persisted index cursor instead.
- **The Drova API's save docs are wrong in three places** (verified against its source):
  `AfterSaveGameLoaded` fires *before* stores are populated, so post-load work belongs in `IStorable.Load`;
  `BeforeSaveGameSaving` handlers run *after* your store was serialized; and a new game never calls
  `Load()`, so a store keeps the previous session's data unless wiped on `BeforeSaveGameLoaded`.
- **`<Nullable>enable</Nullable>` breaks under IL2CPP** (`NullableAttribute` resolves into `Il2Cppmscorlib`).
- `EnableDefaultCompileItems=false`: every new `.cs` must be added to the csproj by hand.
- **Never initialise a static field from the generated half of a partial class.** C# does not define
  static initialiser order across partial files, so `Items = Generated` in `ItemTable.cs` captured null
  because the csproj lists it before `ItemTable.g.cs`. Read generated tables from a property instead.
  This presents as a `NullReferenceException` that looks like an interop fault and is not one.
- **`ProviderAccess.Get*GameHandler()` and `PlayerAccess.GetPlayer()` THROW during bootstrap**, they do
  not return null: they call `<Handler>.TryGet`, which dereferences the game manager. Null-checking the
  result does not help. Prefer the API's readiness events, above all `PlayerAccess.OnPlayerFound`, which
  only fires once the world is ready, no loading screen is up, and the actor is `_isInitialized`.
- **Il2CppInterop cannot marshal a delegate whose parameter is a non-blittable struct.** That rules out
  subscribing to `EntityGameHandler.PlayerActorDiedEvent` (its arg is `EventArgs<Actor>`); a Harmony
  postfix on the listener works because it needs no delegate conversion. So "prefer GenericEvent over
  Harmony" does not hold for events with struct args.
- **Read apworld data with `pkgutil.get_data`, never `open()`.** A packaged `.apworld` is a zip, so there is
  no real file behind `__file__`. This works fine as a folder and fails only once packaged, which is the
  worst way to find out. Test the built `.apworld` with the folder world removed.
- **Location categories must stay in sync with the client's hooks.** If the apworld offers a category the
  mod cannot detect, those locations can never be sent and seeds become unwinnable.
