from __future__ import annotations

import time

import disnake
from disnake.ext import commands

from bread.storage.repositories import afk as afk_repo, guild_configs
from bread.ui.components import bread_container, format_duration, info, success


class MessageEvents(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message) -> None:
        if message.author.bot or not message.guild:
            return
        guild_id = message.guild.id
        user_id = message.author.id

        # ── AFK return detection ──────────────────────────────────────────────
        afk_entry = await afk_repo.get_afk(guild_id, user_id)
        if afk_entry:
            cleared = await afk_repo.clear_afk(guild_id, user_id)
            if cleared:
                duration = int(time.time()) - cleared["since"]
                try:
                    await message.channel.send(
                        components=[success(
                            "Welcome Back!",
                            f"Hey {message.author.mention}, you're back after `{format_duration(duration)}`.",
                            f"> Your AFK reason was: {cleared['reason']}",
                        )],
                        delete_after=10,
                    )
                except disnake.HTTPException:
                    pass

        # ── AFK mention notifications ──────────────────────────────────────────
        for mentioned in message.mentions:
            if mentioned.bot or mentioned.id == user_id:
                continue
            entry = await afk_repo.get_afk(guild_id, mentioned.id)
            if entry:
                duration = int(time.time()) - entry["since"]
                try:
                    await message.channel.send(
                        components=[info(
                            f"💤 {mentioned.display_name} is AFK",
                            f"> {entry['reason']}",
                            f"> Away for `{format_duration(duration)}`.",
                        )],
                        delete_after=15,
                    )
                except disnake.HTTPException:
                    pass

        # ── Word filter ───────────────────────────────────────────────────────
        cfg = await guild_configs.get(guild_id)
        filters = cfg.get("filters", [])
        if filters:
            content_lower = message.content.lower()
            if any(word in content_lower for word in filters):
                try:
                    await message.delete()
                except disnake.HTTPException:
                    pass
                try:
                    await message.channel.send(
                        components=[bread_container(
                            "⚠️ Message Removed",
                            f"> {message.author.mention}, your message was removed for containing a filtered word.",
                        )],
                        delete_after=8,
                    )
                except disnake.HTTPException:
                    pass
                return

        # ── Autoresponder ─────────────────────────────────────────────────────
        autoresponders = cfg.get("autoresponders", [])
        content_lower = message.content.lower()
        for entry in autoresponders:
            trigger = entry["trigger"]
            exact = entry.get("exact", False)
            matched = (content_lower == trigger) if exact else (trigger in content_lower)
            if matched:
                try:
                    await message.channel.send(entry["response"])
                except disnake.HTTPException:
                    pass
                break


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(MessageEvents(bot))
