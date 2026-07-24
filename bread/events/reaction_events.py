from __future__ import annotations

import disnake
from disnake.ext import commands

from bread.storage.repositories import reaction_roles


class ReactionEvents(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent) -> None:
        await self._handle_reaction(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: disnake.RawReactionActionEvent) -> None:
        await self._handle_reaction(payload, add=False)

    async def _handle_reaction(self, payload: disnake.RawReactionActionEvent, *, add: bool) -> None:
        if not payload.guild_id or payload.user_id == self.bot.user.id:  # type: ignore[union-attr]
            return
        emoji_str = str(payload.emoji)
        entry = await reaction_roles.find(payload.guild_id, payload.message_id, emoji_str)
        if not entry:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role = guild.get_role(entry["role_id"])
        if not role:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        try:
            if add:
                await member.add_roles(role, reason="[bread] Reaction role.")
            else:
                await member.remove_roles(role, reason="[bread] Reaction role removed.")
        except disnake.HTTPException:
            pass


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(ReactionEvents(bot))
