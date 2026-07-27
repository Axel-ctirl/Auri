# AuriCombat

DonutSMP-style TPA and combat tagging for **Paper 1.21.11** (Java 21).

```bash
mvn clean package        # -> target/auri-combat-1.0.0.jar
```

Drop the jar in `plugins/`, restart, then edit `plugins/AuriCombat/config.yml` and
`/auricombat reload`.

## Commands

| Command | Aliases | What it does |
|---|---|---|
| `/tpa <player>` | | Ask to teleport to them |
| `/tpahere <player>` | | Ask them to teleport to you |
| `/tpaccept [player]` | `/tpyes` | Accept — the name disambiguates a queue |
| `/tpdeny [player]` | `/tpadeny`, `/tpno` | Deny |
| `/tpacancel` | `/tpcancel` | Withdraw your outgoing request |
| `/tpatoggle` | `/tptoggle` | Stop receiving requests entirely |
| `/tpaguitoggle` | | Swap the menu popup for clickable chat |
| `/auricombat reload` | `/auri` | Reload config |

## Permissions

| Node | Default | Grants |
|---|---|---|
| `auri.tpa.use` | everyone | The TPA commands |
| `auri.tpa.bypass.warmup` | op | Teleport with no warmup |
| `auri.tpa.bypass.cooldown` | op | No cooldown between requests |
| `auri.combat.bypass` | nobody | Never get tagged, never get command-blocked |
| `auri.admin` | op | `/auricombat reload` |

The two bypass nodes are how ranks get their perks — grant `auri.tpa.bypass.cooldown` to
VIP, both to MVP, and so on.

## Combat tagging

Any player-attributable damage tags **both** parties for `combat.duration` seconds (default
20). Re-hitting refreshes the window rather than stacking it. Tag sources, each individually
switchable: melee, projectiles, explosions, a player's tamed pets, and optionally ender-pearl
landings.

End crystals get special handling. Paper's `DamageSource` credits arrows to their shooter and
beds/anchors to whoever lit them, but a crystal is its own causing entity — so the player who
last hit a crystal is recorded and the resulting explosion is credited to them. That's what
makes crystal PvP tag correctly.

While tagged, a player can't use an elytra (deploy *or* firework boost), riptide, or any
command on the blocked list. Ender pearls and totems can be blocked too; both are off by
default.

Disconnecting while tagged drops the inventory on the ground where they logged, wipes it on
the player so nothing dupes on rejoin, kills them, and broadcasts
`<player> has combat logged!`.

### Command blocker

```yaml
bypass-colons: true       # /essentials:home is checked as /home
match-entire-words: true  # a "/warp" entry won't also eat "/warpstone"
```

Both default to on. Without the first, any plugin-prefixed alias walks straight through the
blocklist; without the second, short entries over-block.

## TPA

Requests expire after 60s. Sending starts the cooldown immediately — not on accept — so
spamming requests costs the sender something. Accepting starts a warmup that cancels if the
traveller moves off their block or takes damage.

**Safe-teleport** is the piece that stops `/tpa` traps from being a free kill. Before landing
anyone, the destination is checked for lava, fire, suffocation, and the void; if it's lethal,
the search spirals outward through `search-radius` × `search-vertical` for the nearest
survivable spot. If nothing in that box is safe the teleport is refused outright, unless you
set `fallback-to-original: true`.

Requests arrive as a three-row menu — red wool to deny, sender's head in the middle, green
wool to accept — or as clickable `[ACCEPT]` / `[DENY]` chat buttons for players who ran
`/tpaguitoggle`.

### The combat tag gates TPA at three points

Blocking only the `/tpa` command leaves the bypass wide open, so all three are enforced:

1. **Sending** — tagged players can't send, and can't send *to* someone who's tagged.
2. **Accepting** — re-checked at accept time, because the request may predate the fight.
3. **Mid-warmup** — an in-flight teleport is cancelled if the traveller gets tagged, which
   closes the "queue a teleport one tick before swinging" hole.

## Messages

Every string lives under `messages:` in config.yml and is
[MiniMessage](https://docs.advntr.dev/minimessage/format.html)-formatted. Set any one to `""`
to silence it. Player names are inserted as unparsed placeholders, so a name containing
MiniMessage tags renders as literal text instead of injecting formatting into a broadcast.
