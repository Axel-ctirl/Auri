from __future__ import annotations

import disnake
from disnake.ext import commands

from bread.checks import check_permission
from bread.storage.repositories import guild_configs
from bread.ui.components import error, info, success


class Automod(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    # ── /filter ───────────────────────────────────────────────────────────────

    @commands.slash_command(name="filter", description="Manage the word filter.")
    async def filter_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @filter_group.sub_command(name="add", description="Add a word or phrase to the filter.")
    async def filter_add(
        self,
        inter: disnake.ApplicationCommandInteraction,
        word: str = commands.Param(description="Word or phrase to block (case-insensitive)."),
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(
                components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True
            )
        await guild_configs.add_filter(inter.guild_id, word.lower())  # type: ignore[arg-type]
        await inter.response.send_message(components=[success("Filter Added", f"Added `{word.lower()}` to the word filter.")])

    @filter_group.sub_command(name="remove", description="Remove a word or phrase from the filter.")
    async def filter_remove(
        self,
        inter: disnake.ApplicationCommandInteraction,
        word: str = commands.Param(description="Word or phrase to remove."),
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(
                components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True
            )
        removed = await guild_configs.remove_filter(inter.guild_id, word.lower())  # type: ignore[arg-type]
        if not removed:
            return await inter.response.send_message(
                components=[error("Not Found", f"`{word.lower()}` is not in the filter.")], ephemeral=True
            )
        await inter.response.send_message(components=[success("Filter Removed", f"Removed `{word.lower()}` from the filter.")])

    @filter_group.sub_command(name="list", description="List all filtered words in this server.")
    async def filter_list(self, inter: disnake.ApplicationCommandInteraction) -> None:
        cfg = await guild_configs.get(inter.guild_id)  # type: ignore[arg-type]
        words = cfg.get("filters", [])
        if not words:
            return await inter.response.send_message(
                components=[info("Word Filter", "No words in the filter. Use `/filter add` to add some.")], ephemeral=True
            )
        lines = [f"• `{w}`" for w in words]
        await inter.response.send_message(components=[info(f"Word Filter ({len(words)})", *lines)], ephemeral=True)

    # ── /autoresponder ────────────────────────────────────────────────────────

    @commands.slash_command(name="autoresponder", description="Manage autoresponder triggers.")
    async def ar_group(self, inter: disnake.ApplicationCommandInteraction) -> None:
        pass

    @ar_group.sub_command(name="add", description="Add a trigger → response rule.")
    async def ar_add(
        self,
        inter: disnake.ApplicationCommandInteraction,
        trigger: str = commands.Param(description="Text that triggers the response."),
        response: str = commands.Param(description="What the bot replies with."),
        exact: bool = commands.Param(default=False, description="Require exact message match (default: contains match)."),
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(
                components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True
            )
        await guild_configs.add_autoresponder(inter.guild_id, trigger.lower(), response, exact)  # type: ignore[arg-type]
        match_mode = "exact match" if exact else "contains match"
        await inter.response.send_message(components=[success(
            "Autoresponder Added",
            f"**Trigger:** `{trigger.lower()}` *({match_mode})*",
            f"**Response:** {response}",
        )])

    @ar_group.sub_command(name="remove", description="Remove an autoresponder by trigger text.")
    async def ar_remove(
        self,
        inter: disnake.ApplicationCommandInteraction,
        trigger: str = commands.Param(description="Trigger text to remove."),
    ) -> None:
        if not await check_permission(inter, "manage_guild"):
            return await inter.response.send_message(
                components=[error("Permission Denied", "You need Manage Server.")], ephemeral=True
            )
        removed = await guild_configs.remove_autoresponder(inter.guild_id, trigger.lower())  # type: ignore[arg-type]
        if not removed:
            return await inter.response.send_message(
                components=[error("Not Found", f"No autoresponder found for trigger `{trigger.lower()}`.")], ephemeral=True
            )
        await inter.response.send_message(components=[success("Autoresponder Removed", f"Removed trigger `{trigger.lower()}`.")])

    @ar_group.sub_command(name="list", description="List all autoresponders in this server.")
    async def ar_list(self, inter: disnake.ApplicationCommandInteraction) -> None:
        cfg = await guild_configs.get(inter.guild_id)  # type: ignore[arg-type]
        ars = cfg.get("autoresponders", [])
        if not ars:
            return await inter.response.send_message(
                components=[info("Autoresponders", "No autoresponders configured.")], ephemeral=True
            )
        lines = []
        for entry in ars:
            mode = "exact" if entry.get("exact") else "contains"
            lines.append(f"• `{entry['trigger']}` *({mode})* → {entry['response']}")
        await inter.response.send_message(components=[info(f"Autoresponders ({len(ars)})", *lines)], ephemeral=True)


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(Automod(bot))
