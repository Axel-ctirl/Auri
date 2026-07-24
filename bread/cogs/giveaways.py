from __future__ import annotations

import random
import time

import disnake
from disnake.ext import commands, tasks

from bread.checks import check_permission
from bread.storage.repositories import giveaways as giveaway_repo
from bread.ui.components import BREAD_COLOR, bread_container, error, full_time, info, relative_time, success
from bread.utils import parse_duration

_ENTER_PREFIX = "giveaway:enter:"


class Giveaways(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot
        self.check_giveaways.start()

    def cog_unload(self) -> None:
        self.check_giveaways.cancel()

    # ── Background task ───────────────────────────────────────────────────────

    @tasks.loop(seconds=15)
    async def check_giveaways(self) -> None:
        now = int(time.time())
        active = await giveaway_repo.list_all_active()
        for g in active:
            if g["end_ts"] <= now:
                await self._end_giveaway(g["guild_id"], g["id"])

    @check_giveaways.before_loop
    async def before_check(self) -> None:
        await self.bot.wait_until_ready()

    async def _end_giveaway(self, guild_id: int, giveaway_id: str) -> None:
        g = await giveaway_repo.end(guild_id, giveaway_id)
        if not g:
            return
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(g["channel_id"])
        if not isinstance(channel, disnake.TextChannel):
            return
        entrants = g["entrants"]
        winners_count = min(g["winners_count"], len(entrants))
        if not entrants or winners_count == 0:
            result_text = "> No valid entries — no winners drawn."
        else:
            winner_ids = random.sample(entrants, winners_count)
            result_text = "**Winners:** " + " ".join(f"<@{uid}>" for uid in winner_ids)
        try:
            msg = await channel.fetch_message(g["message_id"])
            await msg.edit(components=[bread_container(
                "🎉 Giveaway Ended!",
                f"**Prize:** {g['prize']}",
                result_text,
                f"> Hosted by <@{g['host_id']}> — ended {full_time(g['end_ts'])}",
            )])
            await channel.send(result_text + f"\nCongratulations! The giveaway for **{g['prize']}** has ended.")
        except disnake.HTTPException:
            pass

    def _build_giveaway_message(self, g: dict) -> list:
        required_role_id = g.get("required_role")
        req_str = f"> Requires role: <@&{required_role_id}>" if required_role_id else ""
        enter_btn = disnake.ui.Button(
            style=disnake.ButtonStyle.success,
            label="🎉 Enter Giveaway",
            custom_id=f"{_ENTER_PREFIX}{g['id']}",
        )
        lines = [
            f"**Prize:** {g['prize']}",
            f"**Winners:** `{g['winners_count']}`",
            f"**Ends:** {relative_time(g['end_ts'])} ({full_time(g['end_ts'])})",
            f"**Hosted by:** <@{g['host_id']}>",
        ]
        if req_str:
            lines.append(req_str)
        lines.append(f"> **{len(g['entrants'])}** entries so far.")
        return [bread_container(
            "🎉 Giveaway",
            *lines,
            extra=[disnake.ui.ActionRow(enter_btn)],
        )]

    # ── /giveaway ─────────────────────────────────────────────────────────────

    @commands.slash_command(name="giveaway", description="Manage server giveaways.")
    async def giveaway_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @giveaway_group.sub_command(name="start", description="Start a new giveaway.")
    async def giveaway_start(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prize: str = commands.Param(description="What is being given away."),
        duration: str = commands.Param(description="How long the giveaway runs (e.g. `1h`, `7d`)."),
        winners: int = commands.Param(default=1, ge=1, le=20, description="Number of winners."),
        required_role: disnake.Role = None,  # type: ignore[assignment]
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True)
        try:
            secs = parse_duration(duration)
        except ValueError as exc:
            return await inter.response.send_message(components=[error("Invalid Duration", str(exc))], ephemeral=True)
        end_ts = int(time.time()) + secs
        g = await giveaway_repo.create(
            guild_id=inter.guild_id,  # type: ignore[arg-type]
            channel_id=inter.channel_id,
            prize=prize,
            end_ts=end_ts,
            winners_count=winners,
            host_id=inter.author.id,
            required_role=required_role.id if required_role else None,
        )
        await inter.response.send_message(components=self._build_giveaway_message(g))
        msg = await inter.original_response()
        await giveaway_repo.set_message_id(inter.guild_id, g["id"], msg.id)  # type: ignore[arg-type]

    @giveaway_group.sub_command(name="end", description="End a giveaway early.")
    async def giveaway_end(
        self,
        inter: disnake.ApplicationCommandInteraction,
        giveaway_id: str,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True)
        await inter.response.defer(ephemeral=True)
        await self._end_giveaway(inter.guild_id, giveaway_id)  # type: ignore[arg-type]
        await inter.edit_original_response(components=[success("Giveaway Ended", f"Giveaway `{giveaway_id}` has been ended.")])

    @giveaway_group.sub_command(name="reroll", description="Reroll winners for an ended giveaway.")
    async def giveaway_reroll(
        self,
        inter: disnake.ApplicationCommandInteraction,
        giveaway_id: str,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True)
        g = await giveaway_repo.get(inter.guild_id, giveaway_id)  # type: ignore[arg-type]
        if not g:
            return await inter.response.send_message(components=[error("Not Found", f"Giveaway `{giveaway_id}` not found.")], ephemeral=True)
        entrants = g["entrants"]
        n = min(g["winners_count"], len(entrants))
        if n == 0:
            return await inter.response.send_message(components=[error("No Entries", "There were no entries to reroll from.")], ephemeral=True)
        winner_ids = random.sample(entrants, n)
        result = "**New winners:** " + " ".join(f"<@{uid}>" for uid in winner_ids)
        await inter.response.send_message(components=[success("Rerolled!", f"**Prize:** {g['prize']}", result)])

    @giveaway_group.sub_command(name="cancel", description="Cancel and remove a running giveaway.")
    async def giveaway_cancel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        giveaway_id: str,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True)
        removed = await giveaway_repo.cancel(inter.guild_id, giveaway_id)  # type: ignore[arg-type]
        if not removed:
            return await inter.response.send_message(components=[error("Not Found", f"Giveaway `{giveaway_id}` not found.")], ephemeral=True)
        await inter.response.send_message(components=[success("Giveaway Cancelled", f"Giveaway `{giveaway_id}` removed.")])

    @giveaway_group.sub_command(name="list", description="List active giveaways in this server.")
    async def giveaway_list(self, inter: disnake.ApplicationCommandInteraction) -> None:
        active = await giveaway_repo.list_active(inter.guild_id)  # type: ignore[arg-type]
        if not active:
            return await inter.response.send_message(components=[info("Giveaways", "No active giveaways right now.")], ephemeral=True)
        lines = [f"`{g['id']}` **{g['prize']}** — ends {relative_time(g['end_ts'])} — `{len(g['entrants'])}` entries" for g in active]
        await inter.response.send_message(components=[info("Active Giveaways", *lines)], ephemeral=True)

    # ── Button handler: giveaway entry ───────────────────────────────────────

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction) -> None:
        cid = inter.component.custom_id
        if not cid.startswith(_ENTER_PREFIX):
            return
        giveaway_id = cid[len(_ENTER_PREFIX):]
        guild_id = inter.guild_id
        g = await giveaway_repo.get(guild_id, giveaway_id)  # type: ignore[arg-type]
        if not g or g["ended"]:
            return await inter.response.send_message(
                components=[error("Giveaway Over", "This giveaway has already ended.")], ephemeral=True
            )
        required_role_id = g.get("required_role")
        if required_role_id:
            member = inter.author
            if not isinstance(member, disnake.Member) or not any(r.id == required_role_id for r in member.roles):
                return await inter.response.send_message(
                    components=[error("Role Required", f"You need <@&{required_role_id}> to enter this giveaway.")], ephemeral=True
                )
        added = await giveaway_repo.add_entrant(guild_id, giveaway_id, inter.author.id)  # type: ignore[arg-type]
        if not added:
            return await inter.response.send_message(
                components=[info("Already Entered", "You're already in this giveaway — good luck!")], ephemeral=True
            )
        refreshed = await giveaway_repo.get(guild_id, giveaway_id)  # type: ignore[arg-type]
        if refreshed and not refreshed["ended"]:
            try:
                await inter.response.edit_message(components=self._build_giveaway_message(refreshed))
            except disnake.HTTPException:
                await inter.response.send_message(
                    components=[success("Entered!", f"You're in! **{len(refreshed['entrants'])}** entries so far. 🍞")], ephemeral=True
                )
        else:
            await inter.response.send_message(
                components=[success("Entered!", "You've been entered — good luck! 🍞")], ephemeral=True
            )


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(Giveaways(bot))
