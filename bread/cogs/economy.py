from __future__ import annotations

import disnake
from disnake.ext import commands

from bread.storage.repositories import economy as economy_repo
from bread.ui.components import error, info, relative_time, success


class Economy(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    @commands.slash_command(description="Check your (or another member's) bread balance.")
    async def balance(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = None,  # type: ignore[assignment]
    ) -> None:
        target = member or inter.author
        bal = await economy_repo.get_balance(inter.guild_id, target.id)  # type: ignore[arg-type]
        await inter.response.send_message(components=[info(
            f"🪙 {target.display_name}'s Balance",
            f"**{bal:,}** bread coins",
        )])

    @commands.slash_command(description="Claim your daily bread coins.")
    async def daily(self, inter: disnake.ApplicationCommandInteraction) -> None:
        ok, value = await economy_repo.claim_daily(inter.guild_id, inter.author.id)  # type: ignore[arg-type]
        if ok:
            await inter.response.send_message(components=[success(
                "Daily Claimed!",
                f"You received **{value:,}** bread coins 🍞",
                f"> Come back in `24h` for your next daily.",
            )])
        else:
            await inter.response.send_message(components=[error(
                "Already Claimed",
                f"You already claimed your daily today.",
                f"> Try again {relative_time(int(__import__('time').time()) + value)}.",
            )], ephemeral=True)

    @commands.slash_command(description="Work for some bread coins.")
    async def work(self, inter: disnake.ApplicationCommandInteraction) -> None:
        ok, value = await economy_repo.claim_work(inter.guild_id, inter.author.id)  # type: ignore[arg-type]
        if ok:
            import random
            jobs = [
                "baked a fresh loaf", "delivered bread to the village", "ran the bakery",
                "sold sourdough at the market", "perfected a croissant recipe",
                "taste-tested 47 baguettes",
            ]
            await inter.response.send_message(components=[success(
                "Work Complete",
                f"You {random.choice(jobs)} and earned **{value:,}** bread coins.",
            )])
        else:
            await inter.response.send_message(components=[error(
                "Still Working",
                "You're still tired from your last job.",
                f"> You can work again {relative_time(int(__import__('time').time()) + value)}.",
            )], ephemeral=True)

    @commands.slash_command(description="Pay bread coins to another member.")
    async def pay(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        amount: int = commands.Param(ge=1, description="Amount to transfer (minimum 1)."),
    ) -> None:
        if member.id == inter.author.id:
            return await inter.response.send_message(components=[error("Invalid Target", "You can't pay yourself.")], ephemeral=True)
        if member.bot:
            return await inter.response.send_message(components=[error("Invalid Target", "You can't pay bots.")], ephemeral=True)
        ok = await economy_repo.transfer(inter.guild_id, inter.author.id, member.id, amount)  # type: ignore[arg-type]
        if not ok:
            bal = await economy_repo.get_balance(inter.guild_id, inter.author.id)  # type: ignore[arg-type]
            return await inter.response.send_message(components=[error(
                "Insufficient Funds",
                f"You only have **{bal:,}** bread coins.",
            )], ephemeral=True)
        await inter.response.send_message(components=[success(
            "Transfer Complete",
            f"Sent **{amount:,}** bread coins to {member.mention}.",
        )])

    @commands.slash_command(description="View the server's richest members.")
    async def richest(self, inter: disnake.ApplicationCommandInteraction) -> None:
        board = await economy_repo.leaderboard(inter.guild_id, limit=10)  # type: ignore[arg-type]
        if not board:
            return await inter.response.send_message(components=[info("Leaderboard", "No economy data yet — use `/daily` to get started!")], ephemeral=True)
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, bal) in enumerate(board):
            prefix = medals[i] if i < 3 else f"`{i + 1}.`"
            lines.append(f"{prefix} <@{uid}> — **{bal:,}** coins")
        await inter.response.send_message(components=[info("💰 Economy Leaderboard", *lines)])


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(Economy(bot))
