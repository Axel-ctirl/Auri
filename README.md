# bread 🍞

A multipurpose Discord bot in the style of bored.rest / bleed.bot — moderation, anti-nuke/anti-raid
security, auto/reaction roles, economy, giveaways, tickets, automod, AFK tracking, button-driven games,
and AI commands (via OpenRouter). Every response is built with Discord's Components V2 layout system
(`disnake.ui.Container`/`Section`/`TextDisplay`/`Separator`) and leans on Discord markdown — blockquotes,
code blocks, inline code, and `<t:...>` timestamps — instead of classic embeds.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BOT_TOKEN, optionally OPENROUTER_API_KEY
python -m bread.bot
```

## Structure

- `bread/cogs/` — one cog per feature area (moderation, security, roles, economy, giveaways, tickets,
  automod, afk, games, ai, utility).
- `bread/events/` — gateway event listeners (member join/leave, message, reactions, audit log).
- `bread/storage/` — a small atomic JSON-file store plus typed repositories; no database server needed.
- `bread/ui/components.py` — shared Components V2 builders used by every command response.
- `bread/services/ai_client.py` — OpenRouter/Kimi wrapper used by `cogs/ai.py`.

## Notes

- No music/voice, welcome-message system, or leveling/XP system in this build.
- Anti-nuke/anti-raid are best-effort heuristics (audit-log polling + in-memory join tracking), not a
  guarantee against a determined, sufficiently-permissioned attacker.
- AI commands require `OPENROUTER_API_KEY`; without one they reply with a clear error instead of crashing.
- Interactive button grids (tic-tac-toe, minesweeper, trivia, polls, tickets, reaction roles) are routed
  through a manual `on_button_click` listener keyed by `custom_id`, since disnake's `View` convenience
  layer doesn't yet support buttons nested inside Components V2 containers/sections.
