from __future__ import annotations

import asyncio

import disnake
from disnake.ext import commands

from bread.checks import check_permission
from bread.storage.repositories import tickets as ticket_repo
from bread.ui.components import bread_container, error, info, success

_OPEN_ID = "ticket:open"
_CLOSE_PREFIX = "ticket:close:"
_CLAIM_PREFIX = "ticket:claim:"


class Tickets(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    @commands.slash_command(name="ticket", description="Manage the ticket system.")
    async def ticket_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @ticket_group.sub_command(name="setup", description="Post a ticket panel and configure the system.")
    async def ticket_setup(
        self,
        inter: disnake.ApplicationCommandInteraction,
        panel_channel: disnake.TextChannel,
        category: disnake.CategoryChannel,
        support_role: disnake.Role,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(
                components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True
            )
        await inter.response.defer(ephemeral=True)
        open_btn = disnake.ui.Button(
            style=disnake.ButtonStyle.primary,
            label="🎫 Open a Ticket",
            custom_id=_OPEN_ID,
        )
        await panel_channel.send(components=[bread_container(
            "🎫 Support Tickets",
            "Need help? Click the button below to open a private support ticket.",
            "> A channel will be created just for you and the support team.",
            extra=[disnake.ui.ActionRow(open_btn)],
        )])
        await ticket_repo.set_config(inter.guild_id, panel_channel.id, category.id, support_role.id)  # type: ignore[arg-type]
        await inter.edit_original_response(components=[success(
            "Ticket Panel Created",
            f"**Channel:** {panel_channel.mention}",
            f"**Category:** `{category.name}`",
            f"**Support Role:** {support_role.mention}",
        )])

    @ticket_group.sub_command(name="list", description="List all open tickets in this server.")
    async def ticket_list(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(
                components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True
            )
        cfg = await ticket_repo.get_config(inter.guild_id)  # type: ignore[arg-type]
        open_tickets = cfg.get("open_tickets", {})
        if not open_tickets:
            return await inter.response.send_message(components=[info("Tickets", "No open tickets.")], ephemeral=True)
        lines = []
        for ch_id, ticket in open_tickets.items():
            ch = inter.guild.get_channel(int(ch_id))  # type: ignore[union-attr]
            ch_str = ch.mention if ch else f"`{ch_id}`"
            claimed = f" — claimed by <@{ticket['claimed_by']}>" if ticket.get("claimed_by") else ""
            lines.append(f"{ch_str} — opened by <@{ticket['opener_id']}>{claimed}")
        await inter.response.send_message(
            components=[info(f"🎫 Open Tickets ({len(open_tickets)})", *lines)], ephemeral=True
        )

    # ── Button handler ────────────────────────────────────────────────────────

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction) -> None:
        cid = inter.component.custom_id
        if cid == _OPEN_ID:
            await self._handle_open(inter)
        elif cid.startswith(_CLOSE_PREFIX):
            await self._handle_close(inter)
        elif cid.startswith(_CLAIM_PREFIX):
            await self._handle_claim(inter)

    async def _handle_open(self, inter: disnake.MessageInteraction) -> None:
        guild = inter.guild
        if not guild:
            return
        await inter.response.defer(ephemeral=True)
        cfg = await ticket_repo.get_config(guild.id)
        if not cfg.get("support_role"):
            return await inter.edit_original_response(
                components=[error("Not Configured", "The ticket system isn't set up. Ask an admin to run `/ticket setup`.")]
            )
        # Check existing ticket
        open_tickets = cfg.get("open_tickets", {})
        for ch_id_str, ticket in open_tickets.items():
            if ticket["opener_id"] == inter.author.id:
                ch = guild.get_channel(int(ch_id_str))
                if ch:
                    return await inter.edit_original_response(
                        components=[error("Already Open", f"You already have a ticket: {ch.mention}")]
                    )
        category = guild.get_channel(cfg["category"])
        support_role = guild.get_role(cfg["support_role"])
        if not isinstance(category, disnake.CategoryChannel) or not support_role:
            return await inter.edit_original_response(
                components=[error("Config Error", "Ticket system is misconfigured. Ask an admin to re-run `/ticket setup`.")]
            )
        ticket_num = len(open_tickets) + 1
        channel_name = f"ticket-{inter.author.name[:20]}-{ticket_num}".lower().replace(" ", "-")[:100]
        overwrites = {
            guild.default_role: disnake.PermissionOverwrite(view_channel=False),
            inter.author: disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            support_role: disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        try:
            ticket_ch = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"[bread tickets] Opened by {inter.author}",
            )
        except disnake.HTTPException as exc:
            return await inter.edit_original_response(components=[error("Failed", f"Could not create channel: {exc}")])
        await ticket_repo.open_ticket(guild.id, ticket_ch.id, inter.author.id)
        close_btn = disnake.ui.Button(
            style=disnake.ButtonStyle.danger, label="🔒 Close Ticket",
            custom_id=f"{_CLOSE_PREFIX}{ticket_ch.id}",
        )
        claim_btn = disnake.ui.Button(
            style=disnake.ButtonStyle.secondary, label="📌 Claim",
            custom_id=f"{_CLAIM_PREFIX}{ticket_ch.id}",
        )
        await ticket_ch.send(
            content=f"{inter.author.mention} {support_role.mention}",
            components=[bread_container(
                "🎫 Ticket Opened",
                f"**Opened by:** {inter.author.mention}",
                "> Describe your issue and a staff member will assist you shortly.",
                extra=[disnake.ui.ActionRow(close_btn, claim_btn)],
            )],
        )
        await inter.edit_original_response(
            components=[success("Ticket Opened", f"Your ticket has been created: {ticket_ch.mention}")]
        )

    async def _handle_close(self, inter: disnake.MessageInteraction) -> None:
        channel_id = int(inter.component.custom_id[len(_CLOSE_PREFIX):])
        guild = inter.guild
        if not guild:
            return
        ticket = await ticket_repo.get_ticket(guild.id, channel_id)
        is_owner = ticket and ticket["opener_id"] == inter.author.id
        if not is_owner and not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(
                components=[error("Permission Denied", "Only staff or the ticket owner can close tickets.")],
                ephemeral=True,
            )
        removed = await ticket_repo.close_ticket(guild.id, channel_id)
        if not removed:
            return await inter.response.send_message(
                components=[error("Not Found", "This ticket is not registered.")], ephemeral=True
            )
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, disnake.TextChannel):
            return await inter.response.send_message(
                components=[success("Ticket Closed", "Ticket record removed.")], ephemeral=True
            )
        await inter.response.send_message(components=[info("Closing Ticket", "This channel will be deleted in **5 seconds**...")])
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"[bread tickets] Closed by {inter.author}")
        except disnake.HTTPException:
            pass

    async def _handle_claim(self, inter: disnake.MessageInteraction) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(
                components=[error("Permission Denied", "Only staff can claim tickets.")], ephemeral=True
            )
        channel_id = int(inter.component.custom_id[len(_CLAIM_PREFIX):])
        guild = inter.guild
        if not guild:
            return
        await ticket_repo.claim_ticket(guild.id, channel_id, inter.author.id)
        await inter.response.send_message(components=[success(
            "Ticket Claimed",
            f"{inter.author.mention} is now handling this ticket.",
        )])


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(Tickets(bot))
