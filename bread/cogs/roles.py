from __future__ import annotations

import disnake
from disnake.ext import commands

from bread.checks import check_permission
from bread.storage.repositories import guild_configs, reaction_roles
from bread.ui.components import error, info, success


class Roles(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    # ── /autorole ─────────────────────────────────────────────────────────────

    @commands.slash_command(name="autorole", description="Auto-assign roles on member join.")
    async def autorole_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @autorole_group.sub_command(name="add", description="Add a role to auto-assign on join.")
    async def autorole_add(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
        kind: str = commands.Param(default="human", choices=["human", "bot"], description="Apply to humans or bots."),
    ) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Roles.")], ephemeral=True)
        await guild_configs.add_autorole(inter.guild_id, role.id, kind)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Auto-Role Added", f"**Role:** {role.mention}", f"**Applies to:** `{kind}s`")])

    @autorole_group.sub_command(name="remove", description="Remove a role from auto-assign.")
    async def autorole_remove(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
        kind: str = commands.Param(default="human", choices=["human", "bot"]),
    ) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Roles.")], ephemeral=True)
        removed = await guild_configs.remove_autorole(inter.guild_id, role.id, kind)  # type: ignore[arg-type]
        if not removed:
            return await inter.response.send_message(components=[error("Not Found", f"{role.mention} is not in the `{kind}` autorole list.")], ephemeral=True)
        await inter.response.send_message(components=[success("Auto-Role Removed", f"**Role:** {role.mention}")])

    @autorole_group.sub_command(name="list", description="List all configured auto-roles.")
    async def autorole_list(self, inter: disnake.ApplicationCommandInteraction) -> None:
        cfg = await guild_configs.get(inter.guild_id)  # type: ignore[arg-type]
        autorole = cfg.get("autorole", {"human": [], "bot": []})
        human_roles = [inter.guild.get_role(r) for r in autorole["human"]]  # type: ignore[union-attr]
        bot_roles = [inter.guild.get_role(r) for r in autorole["bot"]]  # type: ignore[union-attr]
        human_str = " ".join(r.mention for r in human_roles if r) or "*(none)*"
        bot_str = " ".join(r.mention for r in bot_roles if r) or "*(none)*"
        await inter.response.send_message(components=[info("Auto-Roles", f"**Humans:** {human_str}", f"**Bots:** {bot_str}")], ephemeral=True)

    # ── /reactionrole ─────────────────────────────────────────────────────────

    @commands.slash_command(name="reactionrole", description="Assign roles via message reactions.")
    async def rr_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @rr_group.sub_command(name="add", description="Link an emoji reaction on a message to a role.")
    async def rr_add(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message_id: str = commands.Param(description="ID of the target message."),
        emoji: str = commands.Param(description="Emoji to listen for (unicode or :name:)."),
        role: disnake.Role = None,  # type: ignore[assignment]
    ) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Roles.")], ephemeral=True)
        if not role:
            return await inter.response.send_message(components=[error("Missing Role", "Please provide a role.")], ephemeral=True)
        try:
            mid = int(message_id)
        except ValueError:
            return await inter.response.send_message(components=[error("Invalid ID", f"`{message_id}` is not a valid message ID.")], ephemeral=True)
        await reaction_roles.add(inter.guild_id, mid, emoji.strip(), role.id)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Reaction Role Added", f"**Message ID:** `{mid}`", f"**Emoji:** {emoji}  →  **Role:** {role.mention}")])

    @rr_group.sub_command(name="remove", description="Remove a reaction-role link.")
    async def rr_remove(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message_id: str,
        emoji: str,
    ) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Roles.")], ephemeral=True)
        try:
            mid = int(message_id)
        except ValueError:
            return await inter.response.send_message(components=[error("Invalid ID", f"`{message_id}` is not a valid message ID.")], ephemeral=True)
        removed = await reaction_roles.remove(inter.guild_id, mid, emoji.strip())  # type: ignore[arg-type]
        if not removed:
            return await inter.response.send_message(components=[error("Not Found", "No reaction-role found for that message and emoji.")], ephemeral=True)
        await inter.response.send_message(components=[success("Reaction Role Removed", f"**Message ID:** `{mid}`  **Emoji:** {emoji}")])

    @rr_group.sub_command(name="list", description="List all reaction roles in this server.")
    async def rr_list(self, inter: disnake.ApplicationCommandInteraction) -> None:
        entries = await reaction_roles.list(inter.guild_id)  # type: ignore[arg-type]
        if not entries:
            return await inter.response.send_message(components=[info("Reaction Roles", "No reaction roles configured.")], ephemeral=True)
        lines = []
        for e in entries:
            role = inter.guild.get_role(e["role_id"])  # type: ignore[union-attr]
            role_str = role.mention if role else f"`{e['role_id']}`"
            lines.append(f"`msg:{e['message_id']}` {e['emoji']} → {role_str}")
        await inter.response.send_message(components=[info("Reaction Roles", *lines)], ephemeral=True)

    # ── /vanityrole ───────────────────────────────────────────────────────────

    @commands.slash_command(name="vanityrole", description="Grant a role based on status keywords.")
    async def vanityrole_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @vanityrole_group.sub_command(name="set", description="Grant a role to members whose status contains a phrase.")
    async def vanityrole_set(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
        phrase: str = commands.Param(description="Text that must appear in the member's custom status."),
    ) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Roles.")], ephemeral=True)
        await guild_configs.set_vanity(inter.guild_id, role.id, phrase)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success(
            "Vanity Role Set",
            f"**Role:** {role.mention}",
            f'**Phrase:** `"{phrase}"`',
            "> Members whose custom status contains this phrase will receive the role on their next presence update.",
        )])

    @vanityrole_group.sub_command(name="disable", description="Disable the vanity role for this server.")
    async def vanityrole_disable(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Roles.")], ephemeral=True)
        await guild_configs.set_vanity(inter.guild_id, None, None)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Vanity Role Disabled", "Vanity role has been turned off.")])

    # ── Presence update: vanity role check ───────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: disnake.Member, after: disnake.Member) -> None:
        guild = after.guild
        cfg = await guild_configs.get(guild.id)
        vanity = cfg.get("vanity")
        if not vanity:
            return
        role_id: int = vanity["role_id"]
        phrase: str = vanity["phrase"].lower()
        role = guild.get_role(role_id)
        if not role:
            return
        has_status = any(
            isinstance(a, disnake.CustomActivity) and a.name and phrase in a.name.lower()
            for a in after.activities
        )
        has_role = role in after.roles
        try:
            if has_status and not has_role:
                await after.add_roles(role, reason="[bread] Vanity role — status matched.")
            elif not has_status and has_role:
                await after.remove_roles(role, reason="[bread] Vanity role — status no longer matches.")
        except disnake.HTTPException:
            pass


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(Roles(bot))
