from __future__ import annotations

import time

import disnake
from disnake.ext import commands

from bread.checks import check_permission
from bread.storage.repositories import guild_configs, warnings
from bread.ui.components import (
    code_block, error, full_time, info, quote, relative_time, success
)
from bread.utils import format_duration, parse_duration, send_modlog


async def _deny(inter: disnake.ApplicationCommandInteraction) -> None:
    await inter.response.send_message(
        components=[error("Permission Denied", "You don't have permission to run this command.")],
        ephemeral=True,
    )


class Moderation(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    # ── /warn ────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Warn a member and log a case.")
    async def warn(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "moderate_members"):
            return await _deny(inter)
        if member.top_role >= inter.author.top_role and not inter.author.guild_permissions.administrator:  # type: ignore[union-attr]
            return await inter.response.send_message(
                components=[error("Hierarchy Error", "You cannot warn someone with an equal or higher role.")],
                ephemeral=True,
            )
        case = await warnings.add_case(inter.guild_id, member.id, inter.author.id, "warn", reason)  # type: ignore[arg-type]
        await inter.response.send_message(
            components=[success(
                "Warning Issued",
                f"**Member:** {member.mention} (`{member.id}`)",
                f"**Case:** `#{case['id']}`",
                f"> {reason}",
            )]
        )
        await send_modlog(
            inter.guild,  # type: ignore[arg-type]
            "⚠️ Warning",
            f"**Member:** {member.mention} (`{member.id}`)",
            f"**Moderator:** {inter.author.mention}",
            f"**Case:** `#{case['id']}`",
            quote(reason),
        )

    # ── /kick ─────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Kick a member from the server.")
    async def kick(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "kick_members"):
            return await _deny(inter)
        if member.top_role >= inter.author.top_role and not inter.author.guild_permissions.administrator:  # type: ignore[union-attr]
            return await inter.response.send_message(
                components=[error("Hierarchy Error", "You cannot kick someone with an equal or higher role.")],
                ephemeral=True,
            )
        try:
            await member.kick(reason=f"[bread] {reason} — by {inter.author}")
        except disnake.Forbidden:
            return await inter.response.send_message(
                components=[error("Missing Permissions", "I don't have permission to kick that member.")],
                ephemeral=True,
            )
        case = await warnings.add_case(inter.guild_id, member.id, inter.author.id, "kick", reason)  # type: ignore[arg-type]
        await inter.response.send_message(
            components=[success(
                "Member Kicked",
                f"**Member:** {member} (`{member.id}`)",
                f"**Case:** `#{case['id']}`",
                quote(reason),
            )]
        )
        await send_modlog(inter.guild, "👢 Kick", f"**Member:** {member} (`{member.id}`)", f"**Moderator:** {inter.author.mention}", f"**Case:** `#{case['id']}`", quote(reason))  # type: ignore[arg-type]

    # ── /ban ──────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Ban a member from the server.")
    async def ban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
        delete_message_days: int = commands.Param(default=1, ge=0, le=7, description="Days of messages to delete (0-7)."),
    ) -> None:
        if not await check_permission(inter, "ban_members"):
            return await _deny(inter)
        try:
            await inter.guild.ban(member, reason=f"[bread] {reason} — by {inter.author}", delete_message_days=delete_message_days)  # type: ignore[union-attr]
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't ban that member.")], ephemeral=True)
        case = await warnings.add_case(inter.guild_id, member.id, inter.author.id, "ban", reason)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Member Banned", f"**Member:** {member} (`{member.id}`)", f"**Case:** `#{case['id']}`", quote(reason))])
        await send_modlog(inter.guild, "🔨 Ban", f"**Member:** {member} (`{member.id}`)", f"**Moderator:** {inter.author.mention}", f"**Case:** `#{case['id']}`", quote(reason))  # type: ignore[arg-type]

    # ── /unban ────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Unban a user by their ID.")
    async def unban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_id: str = commands.Param(description="The user's ID (18-digit number)."),
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "ban_members"):
            return await _deny(inter)
        try:
            uid = int(user_id)
        except ValueError:
            return await inter.response.send_message(components=[error("Invalid ID", f"`{user_id}` is not a valid user ID.")], ephemeral=True)
        try:
            ban_entry = await inter.guild.fetch_ban(disnake.Object(uid))  # type: ignore[union-attr]
            await inter.guild.unban(ban_entry.user, reason=f"[bread] {reason} — by {inter.author}")  # type: ignore[union-attr]
        except disnake.NotFound:
            return await inter.response.send_message(components=[error("Not Banned", f"No ban found for user ID `{uid}`.")], ephemeral=True)
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't unban members.")], ephemeral=True)
        await inter.response.send_message(components=[success("Member Unbanned", f"**User ID:** `{uid}`", quote(reason))])
        await send_modlog(inter.guild, "🔓 Unban", f"**User ID:** `{uid}`", f"**Moderator:** {inter.author.mention}", quote(reason))  # type: ignore[arg-type]

    # ── /tempban ──────────────────────────────────────────────────────────────

    @commands.slash_command(description="Temporarily ban a member.")
    async def tempban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        duration: str = commands.Param(description="Duration e.g. `1h`, `7d`, `2w`."),
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "ban_members"):
            return await _deny(inter)
        try:
            secs = parse_duration(duration)
        except ValueError as exc:
            return await inter.response.send_message(components=[error("Invalid Duration", str(exc))], ephemeral=True)
        unban_at = int(time.time()) + secs
        try:
            await inter.guild.ban(member, reason=f"[bread tempban {secs}s] {reason} — by {inter.author}", delete_message_days=1)  # type: ignore[union-attr]
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't ban that member.")], ephemeral=True)
        case = await warnings.add_case(inter.guild_id, member.id, inter.author.id, "tempban", reason)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success(
            "Member Temp-Banned",
            f"**Member:** {member} (`{member.id}`)",
            f"**Duration:** `{format_duration(secs)}` — expires {relative_time(unban_at)}",
            f"**Case:** `#{case['id']}`",
            quote(reason),
        )])
        await send_modlog(inter.guild, "⏱️ Temp-Ban", f"**Member:** {member}", f"**Duration:** `{format_duration(secs)}`", f"**Moderator:** {inter.author.mention}", f"**Case:** `#{case['id']}`", quote(reason))  # type: ignore[arg-type]
        # Schedule unban
        async def _unban_later() -> None:
            import asyncio
            await asyncio.sleep(secs)
            try:
                await inter.guild.unban(member, reason="[bread] Temp-ban expired.")  # type: ignore[union-attr]
            except disnake.HTTPException:
                pass
        self.bot.loop.create_task(_unban_later())

    # ── /softban ──────────────────────────────────────────────────────────────

    @commands.slash_command(description="Softban a member (ban + immediate unban to delete messages).")
    async def softban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "ban_members"):
            return await _deny(inter)
        try:
            await inter.guild.ban(member, reason=f"[bread softban] {reason}", delete_message_days=7)  # type: ignore[union-attr]
            await inter.guild.unban(member, reason="[bread] Softban — immediate unban.")  # type: ignore[union-attr]
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't ban that member.")], ephemeral=True)
        case = await warnings.add_case(inter.guild_id, member.id, inter.author.id, "softban", reason)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Member Softbanned", f"**Member:** {member} (`{member.id}`)", f"**Case:** `#{case['id']}`", quote(reason))])
        await send_modlog(inter.guild, "🧹 Softban", f"**Member:** {member}", f"**Moderator:** {inter.author.mention}", f"**Case:** `#{case['id']}`", quote(reason))  # type: ignore[arg-type]

    # ── /hardban ──────────────────────────────────────────────────────────────

    @commands.slash_command(description="Hardban a member (ban + delete all message history).")
    async def hardban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "ban_members"):
            return await _deny(inter)
        try:
            await inter.guild.ban(member, reason=f"[bread hardban] {reason} — by {inter.author}", delete_message_days=7)  # type: ignore[union-attr]
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't ban that member.")], ephemeral=True)
        case = await warnings.add_case(inter.guild_id, member.id, inter.author.id, "hardban", reason)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Member Hard-Banned", f"**Member:** {member} (`{member.id}`)", "7 days of messages deleted.", f"**Case:** `#{case['id']}`", quote(reason))])
        await send_modlog(inter.guild, "🔒 Hard-Ban", f"**Member:** {member}", f"**Moderator:** {inter.author.mention}", f"**Case:** `#{case['id']}`", quote(reason))  # type: ignore[arg-type]

    # ── /massban ──────────────────────────────────────────────────────────────

    @commands.slash_command(description="Ban multiple users by ID (space or comma separated).")
    async def massban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_ids: str = commands.Param(description="Space or comma-separated user IDs."),
        reason: str = "Mass ban.",
    ) -> None:
        if not await check_permission(inter, "ban_members"):
            return await _deny(inter)
        await inter.response.defer()
        ids = [s.strip() for s in user_ids.replace(",", " ").split() if s.strip().isdigit()]
        if not ids:
            return await inter.edit_original_response(components=[error("No Valid IDs", "No valid user IDs found in the input.")])
        banned, failed = [], []
        for uid_str in ids:
            try:
                await inter.guild.ban(disnake.Object(int(uid_str)), reason=f"[bread massban] {reason} — by {inter.author}", delete_message_days=1)  # type: ignore[union-attr]
                banned.append(uid_str)
            except disnake.HTTPException:
                failed.append(uid_str)
        lines = [f"**Banned:** {len(banned)} users", f"**Failed:** {len(failed)} users"]
        if failed:
            lines.append(code_block(" ".join(failed)))
        await inter.edit_original_response(components=[success("Mass Ban Complete", *lines)])
        await send_modlog(inter.guild, "💥 Mass Ban", f"**Moderator:** {inter.author.mention}", f"**Banned:** {len(banned)} users", quote(reason))  # type: ignore[arg-type]

    # ── /timeout ──────────────────────────────────────────────────────────────

    @commands.slash_command(description="Timeout (mute) a member for a duration.")
    async def timeout(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        duration: str = commands.Param(description="Duration e.g. `10m`, `1h`, `7d` (max 28d)."),
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "moderate_members"):
            return await _deny(inter)
        try:
            secs = parse_duration(duration)
        except ValueError as exc:
            return await inter.response.send_message(components=[error("Invalid Duration", str(exc))], ephemeral=True)
        secs = min(secs, 28 * 86400)
        try:
            await member.timeout(duration=secs, reason=f"[bread] {reason} — by {inter.author}")
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't timeout that member.")], ephemeral=True)
        case = await warnings.add_case(inter.guild_id, member.id, inter.author.id, "timeout", reason)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success(
            "Member Timed Out",
            f"**Member:** {member.mention}",
            f"**Duration:** `{format_duration(secs)}`",
            f"**Case:** `#{case['id']}`",
            quote(reason),
        )])
        await send_modlog(inter.guild, "⏸️ Timeout", f"**Member:** {member}", f"**Duration:** `{format_duration(secs)}`", f"**Moderator:** {inter.author.mention}", f"**Case:** `#{case['id']}`", quote(reason))  # type: ignore[arg-type]

    # ── /untimeout ────────────────────────────────────────────────────────────

    @commands.slash_command(description="Remove a member's timeout.")
    async def untimeout(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "moderate_members"):
            return await _deny(inter)
        try:
            await member.timeout(duration=None, reason=f"[bread] {reason} — by {inter.author}")
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't remove that timeout.")], ephemeral=True)
        await inter.response.send_message(components=[success("Timeout Removed", f"**Member:** {member.mention}", quote(reason))])

    # ── /mute ─────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Apply the mute role to a member.")
    async def mute(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "moderate_members"):
            return await _deny(inter)
        cfg = await guild_configs.get(inter.guild_id)  # type: ignore[arg-type]
        mute_role_id = cfg.get("mute_role")
        if not mute_role_id:
            return await inter.response.send_message(
                components=[error("No Mute Role", "Set a mute role with `/mutesetup <role>` first.")],
                ephemeral=True,
            )
        mute_role = inter.guild.get_role(mute_role_id)  # type: ignore[union-attr]
        if not mute_role:
            return await inter.response.send_message(components=[error("Mute Role Missing", "The configured mute role no longer exists.")], ephemeral=True)
        try:
            await member.add_roles(mute_role, reason=f"[bread mute] {reason} — by {inter.author}")
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't manage that member's roles.")], ephemeral=True)
        case = await warnings.add_case(inter.guild_id, member.id, inter.author.id, "mute", reason)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Member Muted", f"**Member:** {member.mention}", f"**Case:** `#{case['id']}`", quote(reason))])
        await send_modlog(inter.guild, "🔇 Mute", f"**Member:** {member}", f"**Moderator:** {inter.author.mention}", f"**Case:** `#{case['id']}`", quote(reason))  # type: ignore[arg-type]

    @commands.slash_command(description="Set the mute role for this server.")
    async def mutesetup(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await _deny(inter)
        await guild_configs.set_mute_role(inter.guild_id, role.id)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Mute Role Set", f"Mute role set to {role.mention}.")])

    # ── /unmute ───────────────────────────────────────────────────────────────

    @commands.slash_command(description="Remove the mute role from a member.")
    async def unmute(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "moderate_members"):
            return await _deny(inter)
        cfg = await guild_configs.get(inter.guild_id)  # type: ignore[arg-type]
        mute_role_id = cfg.get("mute_role")
        if not mute_role_id:
            return await inter.response.send_message(components=[error("No Mute Role", "No mute role is configured.")], ephemeral=True)
        mute_role = inter.guild.get_role(mute_role_id)  # type: ignore[union-attr]
        if mute_role and mute_role in member.roles:
            try:
                await member.remove_roles(mute_role, reason=f"[bread unmute] {reason}")
            except disnake.Forbidden:
                return await inter.response.send_message(components=[error("Missing Permissions", "I can't manage that member's roles.")], ephemeral=True)
        await inter.response.send_message(components=[success("Member Unmuted", f"**Member:** {member.mention}", quote(reason))])

    # ── /jail ─────────────────────────────────────────────────────────────────

    @commands.slash_command(name="jail", description="Jail management commands.")
    async def jail_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @jail_group.sub_command(name="setup", description="Configure the jail role and channel.")
    async def jail_setup(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
        channel: disnake.TextChannel,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await _deny(inter)
        await guild_configs.set_jail(inter.guild_id, role.id, channel.id)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Jail Configured", f"**Role:** {role.mention}", f"**Channel:** {channel.mention}")])

    @jail_group.sub_command(name="add", description="Jail a member (removes roles, applies jail role).")
    async def jail_add(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await _deny(inter)
        cfg = await guild_configs.get(inter.guild_id)  # type: ignore[arg-type]
        jail_role_id, jail_channel_id = cfg.get("jail_role"), cfg.get("jail_channel")
        if not jail_role_id:
            return await inter.response.send_message(components=[error("Not Configured", "Run `/jail setup` first.")], ephemeral=True)
        jail_role = inter.guild.get_role(jail_role_id)  # type: ignore[union-attr]
        if not jail_role:
            return await inter.response.send_message(components=[error("Jail Role Missing", "The configured jail role no longer exists.")], ephemeral=True)
        saved_roles = [r.id for r in member.roles if not r.is_default() and r != jail_role]
        try:
            await member.edit(roles=[jail_role], reason=f"[bread jail] {reason} — by {inter.author}")
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't manage that member's roles.")], ephemeral=True)
        case = await warnings.add_case(inter.guild_id, member.id, inter.author.id, "jail", reason)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Member Jailed", f"**Member:** {member.mention}", f"**Case:** `#{case['id']}`", quote(reason))])
        await send_modlog(inter.guild, "🔒 Jail", f"**Member:** {member}", f"**Moderator:** {inter.author.mention}", f"**Case:** `#{case['id']}`", quote(reason))  # type: ignore[arg-type]
        if jail_channel_id:
            ch = inter.guild.get_channel(jail_channel_id)  # type: ignore[union-attr]
            if isinstance(ch, disnake.TextChannel):
                try:
                    await ch.send(f"{member.mention}, you have been jailed. Reason: {reason}", delete_after=30)
                except disnake.HTTPException:
                    pass

    @jail_group.sub_command(name="remove", description="Unjail a member.")
    async def jail_remove(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await _deny(inter)
        cfg = await guild_configs.get(inter.guild_id)  # type: ignore[arg-type]
        jail_role_id = cfg.get("jail_role")
        if jail_role_id:
            jail_role = inter.guild.get_role(jail_role_id)  # type: ignore[union-attr]
            if jail_role and jail_role in member.roles:
                try:
                    await member.remove_roles(jail_role, reason=f"[bread unjail] {reason}")
                except disnake.Forbidden:
                    return await inter.response.send_message(components=[error("Missing Permissions", "I can't manage that member's roles.")], ephemeral=True)
        await inter.response.send_message(components=[success("Member Released", f"**Member:** {member.mention}", quote(reason))])
        await send_modlog(inter.guild, "🔓 Unjail", f"**Member:** {member}", f"**Moderator:** {inter.author.mention}", quote(reason))  # type: ignore[arg-type]

    # ── /purge ────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Bulk-delete messages from this channel.")
    async def purge(
        self,
        inter: disnake.ApplicationCommandInteraction,
        amount: int = commands.Param(ge=1, le=100, description="Number of messages to delete (1–100)."),
        member: disnake.Member = None,  # type: ignore[assignment]
    ) -> None:
        if not await check_permission(inter, "manage_messages"):
            return await _deny(inter)
        await inter.response.defer(ephemeral=True)
        check = (lambda m: m.author == member) if member else None
        deleted = await inter.channel.purge(limit=amount, check=check)  # type: ignore[union-attr]
        await inter.edit_original_response(
            components=[success("Messages Purged", f"Deleted **{len(deleted)}** message(s){f' from {member.mention}' if member else ''}.")]
        )

    # ── /slowmode ─────────────────────────────────────────────────────────────

    @commands.slash_command(description="Set slowmode for this channel (0 = off).")
    async def slowmode(
        self,
        inter: disnake.ApplicationCommandInteraction,
        seconds: int = commands.Param(ge=0, le=21600, description="Slowmode in seconds (0 to disable)."),
    ) -> None:
        if not await check_permission(inter, "manage_channels"):
            return await _deny(inter)
        try:
            await inter.channel.edit(slowmode_delay=seconds)  # type: ignore[union-attr]
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't edit this channel.")], ephemeral=True)
        msg = f"Slowmode disabled." if seconds == 0 else f"Slowmode set to `{seconds}s`."
        await inter.response.send_message(components=[success("Slowmode Updated", msg)])

    # ── /lock / /unlock ───────────────────────────────────────────────────────

    @commands.slash_command(description="Lock a channel (prevent @everyone from sending messages).")
    async def lock(
        self,
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.TextChannel = None,  # type: ignore[assignment]
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "manage_channels"):
            return await _deny(inter)
        target = channel or inter.channel  # type: ignore[assignment]
        overwrite = target.overwrites_for(inter.guild.default_role)  # type: ignore[union-attr]
        overwrite.send_messages = False
        try:
            await target.set_permissions(inter.guild.default_role, overwrite=overwrite, reason=f"[bread lock] {reason}")  # type: ignore[union-attr]
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't edit permissions in that channel.")], ephemeral=True)
        await inter.response.send_message(components=[success("Channel Locked", f"**Channel:** {target.mention}", quote(reason))])

    @commands.slash_command(description="Unlock a channel.")
    async def unlock(
        self,
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.TextChannel = None,  # type: ignore[assignment]
        reason: str = "No reason provided.",
    ) -> None:
        if not await check_permission(inter, "manage_channels"):
            return await _deny(inter)
        target = channel or inter.channel  # type: ignore[assignment]
        overwrite = target.overwrites_for(inter.guild.default_role)  # type: ignore[union-attr]
        overwrite.send_messages = None
        try:
            await target.set_permissions(inter.guild.default_role, overwrite=overwrite, reason=f"[bread unlock] {reason}")  # type: ignore[union-attr]
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't edit permissions in that channel.")], ephemeral=True)
        await inter.response.send_message(components=[success("Channel Unlocked", f"**Channel:** {target.mention}", quote(reason))])

    # ── /nickname ─────────────────────────────────────────────────────────────

    @commands.slash_command(name="nickname", description="Manage member nicknames.")
    async def nickname_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @nickname_group.sub_command(name="set", description="Set a member's nickname.")
    async def nickname_set(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        nickname: str = commands.Param(max_length=32),
    ) -> None:
        if not await check_permission(inter, "manage_nicknames"):
            return await _deny(inter)
        try:
            await member.edit(nick=nickname)
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't change that member's nickname.")], ephemeral=True)
        await inter.response.send_message(components=[success("Nickname Set", f"**Member:** {member.mention}", f"**New nickname:** `{nickname}`")])

    @nickname_group.sub_command(name="reset", description="Reset a member's nickname.")
    async def nickname_reset(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
    ) -> None:
        if not await check_permission(inter, "manage_nicknames"):
            return await _deny(inter)
        try:
            await member.edit(nick=None)
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't reset that member's nickname.")], ephemeral=True)
        await inter.response.send_message(components=[success("Nickname Reset", f"**Member:** {member.mention}")])

    # ── /mrole ────────────────────────────────────────────────────────────────

    @commands.slash_command(name="mrole", description="Give or take a role from a member.")
    async def mrole_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @mrole_group.sub_command(name="add", description="Give a role to a member.")
    async def mrole_add(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        role: disnake.Role,
    ) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await _deny(inter)
        try:
            await member.add_roles(role, reason=f"[bread] mrole add — by {inter.author}")
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't add that role (it may be above mine).")], ephemeral=True)
        await inter.response.send_message(components=[success("Role Added", f"**Member:** {member.mention}", f"**Role:** {role.mention}")])

    @mrole_group.sub_command(name="remove", description="Remove a role from a member.")
    async def mrole_remove(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        role: disnake.Role,
    ) -> None:
        if not await check_permission(inter, "manage_roles"):
            return await _deny(inter)
        try:
            await member.remove_roles(role, reason=f"[bread] mrole remove — by {inter.author}")
        except disnake.Forbidden:
            return await inter.response.send_message(components=[error("Missing Permissions", "I can't remove that role (it may be above mine).")], ephemeral=True)
        await inter.response.send_message(components=[success("Role Removed", f"**Member:** {member.mention}", f"**Role:** {role.mention}")])

    # ── /case ─────────────────────────────────────────────────────────────────

    @commands.slash_command(name="case", description="View and manage mod cases.")
    async def case_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @case_group.sub_command(name="view", description="View a specific case by ID.")
    async def case_view(
        self,
        inter: disnake.ApplicationCommandInteraction,
        case_id: int,
    ) -> None:
        if not await check_permission(inter, "kick_members"):
            return await _deny(inter)
        case = await warnings.get_case(inter.guild_id, case_id)  # type: ignore[arg-type]
        if not case:
            return await inter.response.send_message(components=[error("Case Not Found", f"No case `#{case_id}` in this server.")], ephemeral=True)
        await inter.response.send_message(components=[info(
            f"Case #{case['id']}",
            f"**Type:** `{case['type']}`",
            f"**User:** <@{case['user_id']}> (`{case['user_id']}`)",
            f"**Moderator:** <@{case['mod_id']}>",
            f"**When:** {full_time(case['timestamp'])} ({relative_time(case['timestamp'])})",
            quote(case["reason"]),
        )], ephemeral=True)

    @case_group.sub_command(name="list", description="List all cases, optionally filtered by user.")
    async def case_list(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = None,  # type: ignore[assignment]
    ) -> None:
        if not await check_permission(inter, "kick_members"):
            return await _deny(inter)
        cases = await warnings.list_cases(inter.guild_id, user_id=member.id if member else None)  # type: ignore[arg-type]
        if not cases:
            return await inter.response.send_message(
                components=[info("No Cases", f"No cases found{f' for {member.mention}' if member else ''}.") ],
                ephemeral=True,
            )
        lines = []
        for c in cases[:20]:
            ts = relative_time(c["timestamp"])
            lines.append(f"`#{c['id']}` **{c['type']}** — <@{c['user_id']}> — {ts}")
        suffix = f"\n> *…and {len(cases) - 20} more. Filter by user to see all.*" if len(cases) > 20 else ""
        await inter.response.send_message(
            components=[info(f"Cases{f' for {member}' if member else ''}", "\n".join(lines) + suffix)],
            ephemeral=True,
        )

    @case_group.sub_command(name="delete", description="Delete a specific case by ID.")
    async def case_delete(
        self,
        inter: disnake.ApplicationCommandInteraction,
        case_id: int,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await _deny(inter)
        deleted = await warnings.delete_case(inter.guild_id, case_id)  # type: ignore[arg-type]
        if not deleted:
            return await inter.response.send_message(components=[error("Not Found", f"No case `#{case_id}` found.")], ephemeral=True)
        await inter.response.send_message(components=[success("Case Deleted", f"Case `#{case_id}` has been removed.")])

    @case_group.sub_command(name="clear", description="Clear all cases for a specific member.")
    async def case_clear(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await _deny(inter)
        count = await warnings.clear_cases(inter.guild_id, member.id)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Cases Cleared", f"Removed **{count}** case(s) for {member.mention}.")])

    # ── /modlog ───────────────────────────────────────────────────────────────

    @commands.slash_command(name="modlog", description="Configure the mod-log channel.")
    async def modlog_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @modlog_group.sub_command(name="set", description="Set the mod-log channel.")
    async def modlog_set(
        self,
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.TextChannel,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await _deny(inter)
        await guild_configs.set_modlog_channel(inter.guild_id, channel.id)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Mod Log Set", f"Mod log will be sent to {channel.mention}.")])

    @modlog_group.sub_command(name="disable", description="Disable the mod-log.")
    async def modlog_disable(
        self,
        inter: disnake.ApplicationCommandInteraction,
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await _deny(inter)
        await guild_configs.set_modlog_channel(inter.guild_id, None)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Mod Log Disabled", "Mod log has been turned off.")])


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(Moderation(bot))
