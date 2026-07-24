from __future__ import annotations

import disnake
from disnake.ext import commands

from bread.storage.repositories import guild_configs


class MemberEvents(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: disnake.Member) -> None:
        cfg = await guild_configs.get(member.guild.id)
        kind = "bot" if member.bot else "human"
        role_ids = cfg.get("autorole", {}).get(kind, [])
        roles = [member.guild.get_role(rid) for rid in role_ids]
        roles_to_add = [r for r in roles if r is not None]
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="[bread] Auto-role on join.")
            except disnake.HTTPException:
                pass
        security_cog = self.bot.get_cog("Security")
        if security_cog:
            await security_cog.check_antiraid(member)  # type: ignore[attr-defined]


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(MemberEvents(bot))
