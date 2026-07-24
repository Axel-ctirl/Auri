from __future__ import annotations

import re

import disnake

from bread.storage.repositories import guild_configs
from bread.ui.components import bread_container


async def send_modlog(guild: disnake.Guild, title: str, *body_blocks: str) -> None:
    """Post a branded CV2 container to the guild's configured mod-log channel, if set."""
    cfg = await guild_configs.get(guild.id)
    channel_id = cfg.get("modlog_channel")
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, disnake.TextChannel):
        return
    try:
        await channel.send(components=[bread_container(title, *body_blocks)])
    except disnake.HTTPException:
        pass


def parse_duration(text: str) -> int:
    """Parse a human-readable duration string (e.g. ``'1h30m'``, ``'7d'``, ``'2w'``) → seconds.
    Raises ``ValueError`` if no valid units are found.
    """
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    total = sum(int(v) * units[u] for v, u in re.findall(r"(\d+)([smhdw])", text.lower()))
    if total == 0:
        raise ValueError(f"Cannot parse duration `{text}`. Use formats like `1h`, `30m`, `7d`, `2w`.")
    return total


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)
