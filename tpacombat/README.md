# TpaCombat — Fabric 1.21.11

Server-side TPA with combat tagging, combat-log punishment, a branded tab list, a per-player
settings menu on the **G** key, and a follower/friends system.

This is a Fabric port of the Forge 1.20.1 mod **TpaCombat 1.0.0 by Min2200**. Behaviour,
commands, config keys and player-facing messages are unchanged; only the platform layer was
rewritten. See [Porting notes](#porting-notes) for the places where Fabric forced a difference.

> **License:** the original mod is distributed as *All Rights Reserved*. This port carries that
> same license. Permission to redistribute it has to come from Min2200 — do not publish builds
> without it.

## Build

```bash
cd tpacombat
./gradlew build          # -> build/libs/tpacombat-1.0.0.jar
```

Drop the jar in `mods/` alongside **Fabric API**. Requires Java 21.

Pinned versions (`gradle.properties`): Minecraft 1.21.11, Fabric Loader 0.19.3,
yarn 1.21.11+build.6, Fabric API 0.141.6+1.21.11, Loom 1.17.19.

The mod declares `"environment": "server"`. Vanilla clients can join a server running it.

## Commands

| Command | Effect |
| --- | --- |
| `/tpa` | Lists everyone online as clickable `[Name]` buttons that send them a request. |
| `/tpa <player>` | Sends a teleport request. |
| `/tpaccept` | Accepts your most recent pending request. |
| `/tpdeny` | Denies your most recent pending request. |
| `/tpablock <player>` | Blocks a player from sending you requests, dropping any they have pending. |
| `/tpaunblock <player>` | Unblocks them. Works on offline players by the name recorded when blocked. |
| `/tpablocks` | Lists who you have blocked. |

Incoming requests arrive in chat with clickable `[Accept]` / `[Deny]` buttons. All commands are
available to every player — there are no permission levels.

## How it works

**Combat tag.** Any PvP hit tags both the attacker and the victim for `tagSeconds`. Every further
hit refreshes it. Arrows and tridents count, since the shooter is resolved as the attacker. Hits
blocked by a shield still tag. Creative and spectator players are never tagged. Mob damage does
not tag — this is a PvP-only system.

While tagged, an action bar counts the tag down once a second, and `/tpa`, `/tpaccept`, `/tpdeny`
and `/tpablock` all refuse to run.

**Combat logging.** Disconnecting while tagged kills the player where they stood, dropping their
inventory as a normal death. Kill credit goes to the last player who hit them, so the death
message and any kill tracking name the right person. If that player is offline the kill falls
back to a generic death. Deaths are announced server-wide when `broadcastCombatLog` is on.

A server stop or restart is **never** punished — the stopping flag is set before players are
kicked.

**Teleporting.** After `/tpaccept` the requester gets a `teleportDelaySeconds` countdown on the
action bar. Walking to a different block or entering combat cancels it and applies
`cancelCooldownSeconds` before they can send another request. The target going offline also
cancels it, but is not the requester's fault, so no cooldown is applied. Requests expire after
`requestTimeoutSeconds`, and are dropped if the requester logs off.

## Tab list

The server name and live player count are shown above the tab list, with command hints below it:

```
                        Exploit Smp
                        27 Players

              < the vanilla player grid goes here >

                 /gotorift  /maces  /tps
```

The name and the command hints use `tablist.accentColor` (red by default); the player count is
white. The footer is only a hint line — it does not register those commands or make them
clickable, so `/gotorift`, `/maces` and `/tps` still need to come from whatever provides them.

It is resent only when the player count actually changes, plus once to each player as they join,
so it costs one small packet per change rather than one per tick.

## Settings menu (G)

Press **G** (Quick Actions) to open the settings menu. It also appears in the pause menu under
**Custom Options**. No client mod is needed.

This uses vanilla **dialogs**, added to Minecraft in 1.21.6 — a server-driven UI that vanilla
clients render natively. It is not a chest GUI and not a Paper-only feature; Paper's Dialog API is
just a plugin-facing wrapper over the same system.

`/settings` opens a category grid; picking one shows just that category's settings, one per row,
with a **← Back** button. Navigation and values are never mixed into the same list.

The menu is built per player at the moment it opens (via `RegistryEntry.of`, not a registered
static dialog), which is what lets each row show that player's current value. Clicking a row
cycles it and re-opens the menu, so it reads as toggling in place. Toggles that change world
state are applied the instant they are clicked rather than on the next sweep.

Category buttons carry real item textures rather than unicode, using the `object` text component
added in 1.21.9. The same mechanism draws player heads beside names in the Friends list.

Item sprites **must** name the `minecraft:items` atlas explicitly:

```json
{ "object": "atlas", "atlas": "minecraft:items", "sprite": "minecraft:item/bell" }
```

The default atlas for an object component is `minecraft:blocks`, whose `blocks.json` only sources
the `block/` directory. An item sprite looked up there resolves to nothing and renders blank, with
no error logged anywhere — the dialog still loads fine.

| Category | Setting | Values |
| --- | --- | --- |
| Chat | Public Chat | ON / OFF |
| | Private Messages | Everyone / Friends / Following / Nobody |
| | Server Messages | ON / OFF |
| | Death Messages | ON / OFF |
| | Advancement Messages | ON / OFF |
| | Join/Leave Messages | ON / OFF |
| Notifications | TPA Alerts | ON / OFF |
| | Combat Alerts | ON / OFF |
| PvP | Totem Particles | ON / OFF |
| | Explosion Particles | ON / OFF |
| Privacy | Who Can TPA You | Everyone / Friends / Following / Nobody |
| General | Phantom Spawning | ON / OFF |
| | Keep Ender Pearls On Death | ON / OFF |
| | Night Vision | ON / OFF |
| Friends | follow list, filter and search | |

Everything is also reachable from chat: `/settings`, `/settings <category>`,
`/settings cycle <setting>`.

Settings are stored per player at `<world>/data/tpacombat_players.json`, flushed about once a
minute and on shutdown.

### How each toggle is enforced

The PvP and message toggles work by withholding outgoing packets from that player only, via a
mixin on `ServerCommonNetworkHandler#send`. Nothing about the world changes — these are purely
what *you* are shown.

- **Totem Particles** drops the totem entity-status packet. The totem still saves you; you just
  don't get the screen-filling animation.
- **Explosion Particles** drops explosion packets **only when they carry no knockback for you**.
  An explosion that actually shoves you is always delivered, so turning this on can't be used to
  dodge explosion physics — it removes the visual spam from explosions happening near you.
- **Death / Advancement / Join-Leave Messages** are matched on the vanilla translation key
  (`death.*`, `chat.type.advancement.*`, `multiplayer.player.*`) rather than on rendered text, so
  they keep working regardless of language or formatting.
- **Public Chat** drops player chat packets.
- **Server Messages** covers this mod's own broadcasts, such as combat-log announcements.
- **TPA / Combat Alerts** suppress this mod's own request and combat-tag messages.

### General

- **Phantom Spawning** — turning this off holds that player's `timeSinceRest` statistic at zero.
  The phantom spawner gates on each player's own value, so this suppresses phantoms for them and
  nobody else, with no mixin involved. The trade-off is that their "time since last rest"
  statistic stays pinned at zero.
- **Keep Ender Pearls On Death** — when off, that player's in-flight ender pearls are discarded
  when they die. When on, vanilla behaviour is left alone. There is no vanilla gamerule for this
  in 1.21.11, so it is enforced by the mod on the death event.
- **Night Vision** — an infinite, ambient, particle-free night vision effect, re-applied on a
  timer so it survives death, dimension changes and milk. Toggling it off only clears the
  infinite ambient instance, so potion- and beacon-granted night vision is left untouched.

## Followers and friends

Follows are one-directional. When two players follow each other they become **friends**, which is
what the `Friends` visibility level checks.

| Command | Effect |
| --- | --- |
| `/follow <player>` | Follow someone. They are told, and told if it made you friends. |
| `/unfollow <player>` | Stop following. |
| `/following` | Who you follow. |
| `/followers` | Who follows you. |
| `/friends` | Mutual follows. |

The **Friends** tab in the menu shows the same data with player heads beside each name. **Filter**
cycles between friends, following and followers; **Search** and **+ Follow** open a name-entry
screen (a dialog text input feeding `dynamic/run_command`). Clicking a name unfollows them —
addressed by UUID, so it works for offline players too.

**Who Can TPA You** (Privacy) uses this: set it to `Friends` and only mutual follows can send you
a request; `Following` allows people you follow; `Nobody` refuses everyone. It sits in front of
`/tpablock`, which remains a hard per-player block.

## Config

Written to `config/tpacombat.json` on first start, re-read on every server start. Values are
clamped to the same ranges the original Forge config enforced.

```json
{
  "combat": {
    "tagSeconds": 20,
    "punishCombatLog": true,
    "broadcastCombatLog": true,
    "untagOnKill": true
  },
  "tpa": {
    "requestTimeoutSeconds": 60,
    "teleportDelaySeconds": 5,
    "cancelOnMove": true,
    "cancelCooldownSeconds": 15
  },
  "tablist": {
    "enabled": true,
    "serverName": "Exploit Smp",
    "commands": ["/gotorift", "/maces", "/tps"],
    "accentColor": "red",
    "refreshTicks": 20
  }
}
```

| Key | Meaning |
| --- | --- |
| `combat.tagSeconds` | Seconds tagged after the last PvP hit dealt or received. 1–3600. |
| `combat.punishCombatLog` | Kill players who disconnect while tagged. |
| `combat.broadcastCombatLog` | Announce combat-log deaths server-wide. |
| `combat.untagOnKill` | Killing the player you were fighting clears your own tag. |
| `tpa.requestTimeoutSeconds` | Request lifetime. 1–3600. |
| `tpa.teleportDelaySeconds` | Countdown after accept. `0` teleports instantly. 0–3600. |
| `tpa.cancelOnMove` | Moving to another block cancels the countdown. |
| `tpa.cancelCooldownSeconds` | Cooldown after a self-inflicted cancel. `0` disables. 0–3600. |
| `tablist.enabled` | Show the custom tab list header and footer. |
| `tablist.serverName` | First header line, bold in the accent colour. |
| `tablist.commands` | Command hints listed in the footer. Any number of entries. |
| `tablist.accentColor` | Named Minecraft colour, e.g. `red`, `gold`, `aqua`. Bad names fall back to red. |
| `tablist.refreshTicks` | How often to check for a player-count change. 20 = once a second. 1–1200. |

Per-player settings are not in this file — they live in the world save, one entry per player.

Block lists are stored per world at `<world>/data/tpacombat_blocks.json`.

## Porting notes

Forge 1.20.1 and Fabric 1.21.11 share no API surface, so every platform call was rewritten. The
differences worth knowing about:

- **Config.** Fabric ships no config system, so `ForgeConfigSpec` became a GSON-backed JSON file.
  Key names, defaults and value ranges are identical. The original reloaded live on file edit;
  this one re-reads on server start.
- **Block lists.** Forge's `SavedData` (NBT, attached to the overworld) became a JSON file under
  the world save, keeping the "travels with the world" behaviour.
- **Damage hook.** `LivingHurtEvent` became `ServerLivingEntityEvents.AFTER_DAMAGE`. Forge fired
  before damage was applied; Fabric fires at the tail of `damage()` — but Fabric's own mixin skips
  the event when the hit killed the entity. A fatal blow therefore does not tag anyone. With the
  default `untagOnKill: true` this is invisible; with it set to `false`, a killer is no longer
  re-tagged by their own killing blow. Both parties are already tagged from the exchange leading
  up to it.
- **Kill credit.** `player.hurt(damageSources().playerAttack(killer), MAX_VALUE)` became
  `player.damage(world, world.getDamageSources().playerAttack(killer), MAX_VALUE)`, with
  `timeUntilRegen` zeroed first exactly as before so invulnerability frames can't absorb it.
- **Disconnect hook.** `PlayerLoggedOutEvent` became `ServerPlayConnectionEvents.DISCONNECT`,
  which also runs while the player is still in the world — required for the kill to drop items.
- **Text.** `Component`/`ClickEvent(Action, String)` became `Text`/`new ClickEvent.RunCommand(...)`,
  which is a sealed-interface record in 1.21.11. The client runs these through
  `CommandManager.stripLeadingSlash`, so commands work with or without a leading `/`.
