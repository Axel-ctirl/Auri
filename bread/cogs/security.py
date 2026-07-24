from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

import disnake
from disnake.ext import commands

from bread.checks import check_permission
from bread.storage.repositories import fake_perms, guild_configs
from bread.ui.components import code_block, error, info, success
from bread.utils import send_modlog

_join_timestamps: dict[int, deque] = defaultdict(lambda: deque(maxlen=50))
_nuke_tracker: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

DANGEROUS_PERMS = [
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "ban_members", "kick_members", "manage_webhooks", "manage_expressions",
]


class Security(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    # ── Runtime: anti-raid join detection ────────────────────────────────────

    async def check_antiraid(self, member: disnake.Member) -> None:
        guild = member.guild
        cfg = await guild_configs.get(guild.id)
        ar = cfg.get("antiraid", {})
        if not ar.get("enabled"):
            return
        threshold: int = ar.get("threshold", 5)
        window: int = ar.get("window", 10)
        action: str = ar.get("action", "alert")
        now = time.time()
        q = _join_timestamps[guild.id]
        q.append(now)
        recent = [t for t in q if now - t <= window]
        if len(recent) < threshold:
            return
        _join_timestamps[guild.id].clear()
        if action == "kick":
            for m in list(guild.members):
                if now - m.joined_at.timestamp() <= window:
                    try:
                        await m.kick(reason="[bread antiraid] Mass-join detected.")
                    except disnake.HTTPException:
                        pass
        elif action == "lockdown":
            for ch in guild.text_channels:
                try:
                    ow = ch.overwrites_for(guild.default_role)
                    ow.send_messages = False
                    await ch.set_permissions(guild.default_role, overwrite=ow, reason="[bread antiraid] Lockdown.")
                except disnake.HTTPException:
                    pass
        await send_modlog(guild, "🚨 Anti-Raid Triggered", f"**{len(recent)} joins** in `{window}s` — action: `{action}`")

    # ── /antiraid ─────────────────────────────────────────────────────────────

    @commands.slash_command(name="antiraid", description="Anti-raid configuration.")
    async def antiraid_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @antiraid_group.sub_command(name="config", description="Configure anti-raid settings.")
    async def antiraid_config(
        self,
        inter: disnake.ApplicationCommandInteraction,
        enabled: bool = None,  # type: ignore[assignment]
        threshold: int = commands.Param(default=None, ge=2, le=50, description="Joins to trigger."),
        window: int = commands.Param(default=None, ge=1, le=60, description="Time window in seconds."),
        action: str = commands.Param(default=None, choices=["kick", "lockdown", "alert"]),
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True)
        cfg = await guild_configs.set_antiraid(
            inter.guild_id,  # type: ignore[arg-type]
            **{k: v for k, v in dict(enabled=enabled, threshold=threshold, window=window, action=action).items() if v is not None},
        )
        await inter.response.send_message(components=[success(
            "Anti-Raid Updated",
            f"**Enabled:** `{cfg['enabled']}`",
            f"**Threshold:** `{cfg['threshold']}` joins in `{cfg['window']}s`",
            f"**Action:** `{cfg['action']}`",
        )])

    @antiraid_group.sub_command(name="status", description="View current anti-raid configuration.")
    async def antiraid_status(self, inter: disnake.ApplicationCommandInteraction) -> None:
        cfg = await guild_configs.get(inter.guild_id)  # type: ignore[arg-type]
        ar = cfg.get("antiraid", {})
        await inter.response.send_message(components=[info(
            "Anti-Raid Status",
            f"**Enabled:** `{ar.get('enabled', False)}`",
            f"**Threshold:** `{ar.get('threshold', 5)}` joins in `{ar.get('window', 10)}s`",
            f"**Action:** `{ar.get('action', 'alert')}`",
        )], ephemeral=True)

    # ── /antinuke ─────────────────────────────────────────────────────────────

    @commands.slash_command(name="antinuke", description="Anti-nuke configuration.")
    async def antinuke_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @antinuke_group.sub_command(name="config", description="Configure anti-nuke settings.")
    async def antinuke_config(
        self,
        inter: disnake.ApplicationCommandInteraction,
        enabled: bool = None,  # type: ignore[assignment]
        threshold: int = commands.Param(default=None, ge=1, le=20, description="Actions before punishment."),
        punishment: str = commands.Param(default=None, choices=["strip_roles", "kick", "ban"]),
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True)
        cfg = await guild_configs.set_antinuke(
            inter.guild_id,  # type: ignore[arg-type]
            **{k: v for k, v in dict(enabled=enabled, threshold=threshold, punishment=punishment).items() if v is not None},
        )
        await inter.response.send_message(components=[success(
            "Anti-Nuke Updated",
            f"**Enabled:** `{cfg['enabled']}`",
            f"**Threshold:** `{cfg['threshold']}` actions in `{cfg['window']}s`",
            f"**Punishment:** `{cfg['punishment']}`",
        )])

    @antinuke_group.sub_command(name="status", description="View current anti-nuke configuration.")
    async def antinuke_status(self, inter: disnake.ApplicationCommandInteraction) -> None:
        cfg = await guild_configs.get(inter.guild_id)  # type: ignore[arg-type]
        an = cfg.get("antinuke", {})
        whitelist_ids = an.get("whitelist", [])
        wl_str = ", ".join(f"<@{uid}>" for uid in whitelist_ids) if whitelist_ids else "*(none)*"
        await inter.response.send_message(components=[info(
            "Anti-Nuke Status",
            f"**Enabled:** `{an.get('enabled', False)}`",
            f"**Threshold:** `{an.get('threshold', 3)}` actions in `{an.get('window', 10)}s`",
            f"**Punishment:** `{an.get('punishment', 'strip_roles')}`",
            f"**Whitelist:** {wl_str}",
        )], ephemeral=True)

    @antinuke_group.sub_command(name="whitelist", description="Add or remove a user from the anti-nuke whitelist.")
    async def antinuke_whitelist(
        self,
        inter: disnake.ApplicationCommandInteraction,
        action: str = commands.Param(choices=["add", "remove"]),
        user: disnake.Member = None,  # type: ignore[assignment]
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True)
        if not user:
            return await inter.response.send_message(components=[error("Missing User", "Please provide a user.")], ephemeral=True)
        if action == "add":
            await guild_configs.antinuke_whitelist_add(inter.guild_id, user.id)  # type: ignore[arg-type]
            await inter.response.send_message(components=[success("Whitelist Updated", f"{user.mention} added to anti-nuke whitelist.")])
        else:
            removed = await guild_configs.antinuke_whitelist_remove(inter.guild_id, user.id)  # type: ignore[arg-type]
            if not removed:
                return await inter.response.send_message(components=[error("Not Found", f"{user.mention} is not in the whitelist.")], ephemeral=True)
            await inter.response.send_message(components=[success("Whitelist Updated", f"{user.mention} removed from anti-nuke whitelist.")])

    # ── /lockdown ─────────────────────────────────────────────────────────────

    @commands.slash_command(description="Lock all channels in the server (panic button).")
    async def lockdown(
        self,
        inter: disnake.ApplicationCommandInteraction,
        action: str = commands.Param(choices=["enable", "disable"]),
        reason: str = "Security lockdown.",
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True)
        await inter.response.defer()
        locked, failed = 0, 0
        for ch in inter.guild.text_channels:  # type: ignore[union-attr]
            try:
                ow = ch.overwrites_for(inter.guild.default_role)  # type: ignore[union-attr]
                ow.send_messages = False if action == "enable" else None
                await ch.set_permissions(inter.guild.default_role, overwrite=ow, reason=f"[bread lockdown] {reason}")  # type: ignore[union-attr]
                locked += 1
            except disnake.HTTPException:
                failed += 1
        verb = "Enabled" if action == "enable" else "Disabled"
        await inter.edit_original_response(components=[success(
            f"Lockdown {verb}",
            f"**Channels affected:** `{locked}`",
            f"**Failed:** `{failed}`",
        )])
        await send_modlog(inter.guild, f"🔒 Lockdown {verb}", f"**Moderator:** {inter.author.mention}", f"**Reason:** {reason}")  # type: ignore[arg-type]

    # ── /fakeperms ────────────────────────────────────────────────────────────

    @commands.slash_command(name="fakeperms", description="Manage bread fake permissions.")
    async def fakeperms_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    VALID_FAKE_PERMS = [
        "kick_members", "ban_members", "manage_roles", "manage_channels",
        "manage_guild", "manage_messages", "manage_nicknames", "moderate_members",
    ]

    @fakeperms_group.sub_command(name="grant", description="Grant a bread fake permission to a role.")
    async def fakeperms_grant(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
        permission: str = commands.Param(choices=VALID_FAKE_PERMS),
    ) -> None:
        if not inter.author.guild_permissions.administrator:  # type: ignore[union-attr]
            return await inter.response.send_message(components=[error("Permission Denied", "Only administrators can manage fake permissions.")], ephemeral=True)
        await fake_perms.grant(inter.guild_id, role.id, permission)  # type: ignore[arg-type]
        await inter.response.send_message(components=[success(
            "Fake Permission Granted",
            f"**Role:** {role.mention}",
            f"**Permission:** `{permission}`",
            "> This role can now use bread commands that require this permission, without holding the real Discord permission.",
        )])

    @fakeperms_group.sub_command(name="revoke", description="Revoke a bread fake permission from a role.")
    async def fakeperms_revoke(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
        permission: str = commands.Param(choices=VALID_FAKE_PERMS),
    ) -> None:
        if not inter.author.guild_permissions.administrator:  # type: ignore[union-attr]
            return await inter.response.send_message(components=[error("Permission Denied", "Only administrators can manage fake permissions.")], ephemeral=True)
        removed = await fake_perms.revoke(inter.guild_id, role.id, permission)  # type: ignore[arg-type]
        if not removed:
            return await inter.response.send_message(components=[error("Not Found", f"That role doesn't have fake `{permission}`.")], ephemeral=True)
        await inter.response.send_message(components=[success("Fake Permission Revoked", f"**Role:** {role.mention}", f"**Permission:** `{permission}`")])

    @fakeperms_group.sub_command(name="list", description="List all fake permissions in this server.")
    async def fakeperms_list(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not inter.author.guild_permissions.administrator:  # type: ignore[union-attr]
            return await inter.response.send_message(components=[error("Permission Denied", "Only administrators can view fake permissions.")], ephemeral=True)
        guild_perms = await fake_perms.list_guild(inter.guild_id)  # type: ignore[arg-type]
        if not guild_perms:
            return await inter.response.send_message(components=[info("Fake Permissions", "No fake permissions configured.")], ephemeral=True)
        lines = []
        for role_id, perms in guild_perms.items():
            role = inter.guild.get_role(int(role_id))  # type: ignore[union-attr]
            name = role.mention if role else f"`{role_id}`"
            lines.append(f"{name} → `{'`, `'.join(perms)}`")
        await inter.response.send_message(components=[info("Fake Permissions", *lines)], ephemeral=True)

    # ── /permaudit ────────────────────────────────────────────────────────────

    @commands.slash_command(description="Audit which roles hold dangerous Discord permissions.")
    async def permaudit(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True)
        rows = []
        for role in inter.guild.roles:  # type: ignore[union-attr]
            dangerous = [p for p in DANGEROUS_PERMS if getattr(role.permissions, p, False)]
            if dangerous and not role.is_default():
                rows.append(f"{role.name:<30} {', '.join(dangerous)}")
        if not rows:
            return await inter.response.send_message(components=[success("Permission Audit", "No roles with dangerous permissions found.")], ephemeral=True)
        header = f"{'Role':<30} {'Permissions'}"
        table = header + "\n" + "-" * 60 + "\n" + "\n".join(rows)
        await inter.response.send_message(components=[info("Permission Audit", code_block(table))], ephemeral=True)

    # ── Audit log listener for anti-nuke ──────────────────────────────────────

    @commands.Cog.listener("on_audit_log_entry_create")
    async def on_audit_log_entry_create(self, entry: disnake.AuditLogEntry) -> None:
        if not entry.guild:
            return
        guild = entry.guild
        cfg = await guild_configs.get(guild.id)
        an = cfg.get("antinuke", {})
        if not an.get("enabled"):
            return
        whitelist: list[int] = an.get("whitelist", [])
        actor = entry.user
        if actor is None or actor.id == self.bot.user.id:  # type: ignore[union-attr]
            return
        if guild.owner_id and actor.id == guild.owner_id:
            return
        if actor.id in whitelist:
            return
        watched = {
            disnake.AuditLogAction.ban,
            disnake.AuditLogAction.kick,
            disnake.AuditLogAction.channel_delete,
            disnake.AuditLogAction.role_delete,
            disnake.AuditLogAction.webhook_create,
        }
        if entry.action not in watched:
            return
        threshold: int = an.get("threshold", 3)
        window: int = an.get("window", 10)
        now = time.time()
        tracker = _nuke_tracker[guild.id]
        actor_actions = tracker[actor.id]
        actor_actions.append(now)
        recent = [t for t in actor_actions if now - t <= window]
        tracker[actor.id] = recent
        if len(recent) < threshold:
            return
        tracker[actor.id] = []
        punishment: str = an.get("punishment", "strip_roles")
        member = guild.get_member(actor.id)
        if not member:
            return
        try:
            if punishment == "strip_roles":
                safe_roles = [r for r in member.roles if r.is_default()]
                await member.edit(roles=safe_roles, reason="[bread antinuke] Mass-action detected.")
            elif punishment == "kick":
                await member.kick(reason="[bread antinuke] Mass-action detected.")
            elif punishment == "ban":
                await guild.ban(member, reason="[bread antinuke] Mass-action detected.")
        except disnake.HTTPException:
            pass
        await send_modlog(
            guild,
            "🛡️ Anti-Nuke Triggered",
            f"**Actor:** {actor.mention} (`{actor.id}`)",
            f"**Action:** `{entry.action.name}`",
            f"**Punishment:** `{punishment}`",
            f"> `{len(recent)}` actions detected in `{window}s` — threshold: `{threshold}`",
        )


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(Security(bot))
