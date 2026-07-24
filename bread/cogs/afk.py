from __future__ import annotations

import disnake
from disnake.ext import commands

from bread.storage.repositories import afk as afk_repo
from bread.ui.components import success


class AFK(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    @commands.slash_command(description="Set your AFK status with an optional message.")
    async def afk(
        self,
        inter: disnake.ApplicationCommandInteraction,
        reason: str = commands.Param(default="AFK", description="Why you're going AFK."),
    ) -> None:
        await afk_repo.set_afk(inter.guild_id, inter.author.id, reason)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success(
            "AFK Set",
            f"> {reason}",
            "> I'll notify anyone who mentions you, and welcome you back when you return.",
        )])


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(AFK(bot))
