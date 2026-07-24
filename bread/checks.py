from __future__ import annotations

import disnake
from disnake.ext import commands

from bread.storage.repositories import fake_perms


async def check_permission(inter: disnake.ApplicationCommandInteraction, permission: str) -> bool:
    """True when the invoker has the real Discord permission named *permission*
    or a bread fake-permission for that name on any of their roles.
    Administrators always pass.
    """
    if inter.guild is None or not isinstance(inter.author, disnake.Member):
        return False
    member: disnake.Member = inter.author
    if member.guild_permissions.administrator:
        return True
    if getattr(member.guild_permissions, permission, False):
        return True
    role_ids = [r.id for r in member.roles]
    return await fake_perms.has_permission(inter.guild.id, role_ids, permission)


def has_bread_permission(permission: str):
    """Decorator version of ``check_permission`` for use with ``@commands.check``."""

    async def predicate(inter: disnake.ApplicationCommandInteraction) -> bool:
        return await check_permission(inter, permission)

    return commands.check(predicate)
