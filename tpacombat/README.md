# TpaCombat — Fabric 1.21.11

Server-side TPA with combat tagging, combat-log punishment and a branded tab list.

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
                        Exploit SMP
                        27 Players

              < the vanilla player grid goes here >

                 /gotorift  /maces  /tps
```

The name and the command hints use `tablist.accentColor` (red by default); the player count is
white. The footer is only a hint line — it does not register those commands or make them
clickable, so `/gotorift`, `/maces` and `/tps` still need to come from whatever provides them.

It is resent only when the player count actually changes, plus once to each player as they join,
so it costs one small packet per change rather than one per tick.

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
    "serverName": "Exploit SMP",
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
  which is a sealed-interface record in 1.21.11.
