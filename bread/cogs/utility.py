from __future__ import annotations

import secrets
import time

import disnake
from disnake.ext import commands

from bread.ui.components import bread_container, code_block, full_time, info, relative_time, success

_polls: dict[str, dict] = {}

_HELP_CATEGORIES = {
    "🔨 Moderation": [
        "`/warn` `/kick` `/ban` `/unban` `/tempban` `/softban` `/hardban` `/massban`",
        "`/timeout` `/untimeout` `/mute` `/unmute` `/mutesetup`",
        "`/jail setup|add|remove` — set up the jail system",
        "`/nickname set|reset` `/mrole add|remove`",
        "`/case view|list|delete|clear` — browse the moderation case log",
        "`/purge` `/slowmode` `/lock` `/unlock`",
        "`/modlog set|disable` — configure the mod-log channel",
    ],
    "🛡️ Security": [
        "`/antiraid config|status` — detect mass-join raids",
        "`/antinuke config|status|whitelist` — stop server nukes",
        "`/lockdown enable|disable` — lock all channels instantly",
        "`/fakeperms grant|revoke|list` — grant bot-only permissions to roles",
        "`/permaudit` — audit roles holding dangerous permissions",
    ],
    "🎭 Roles": [
        "`/autorole add|remove|list` — auto-assign roles on join",
        "`/reactionrole add|remove|list` — roles via emoji reactions",
        "`/vanityrole set|disable` — role for custom status keywords",
    ],
    "💰 Economy": [
        "`/balance [user]` — check bread coin balance",
        "`/daily` — claim your daily bread coins",
        "`/work` — earn coins every hour",
        "`/pay <user> <amount>` — transfer coins",
        "`/richest` — server leaderboard",
    ],
    "🎉 Giveaways": [
        "`/giveaway start` — launch a new giveaway",
        "`/giveaway end|reroll|cancel|list`",
    ],
    "🎫 Tickets": [
        "`/ticket setup` — post a support ticket panel",
        "`/ticket list` — view open tickets",
    ],
    "🤖 Automod": [
        "`/filter add|remove|list` — word filter",
        "`/autoresponder add|remove|list` — trigger → response rules",
    ],
    "💤 AFK": [
        "`/afk [reason]` — set your AFK status",
        "> Bread will notify anyone who mentions you, and welcome you back on return.",
    ],
    "🎮 Games": [
        "`/tictactoe [opponent] [difficulty]` — play vs a friend or AI",
        "`/minesweeper [mines]` — 5×5 button minesweeper",
        "`/rps` — rock, paper, scissors",
        "`/hangman` — guess the hidden word",
    ],
    "🧠 AI (OpenRouter)": [
        "`/ask <prompt>` — ask the AI anything",
        "`/roast <user>` `/compliment <user>`",
        "`/trivia` — AI trivia with button answers",
        "`/wyr` — would you rather with live votes",
        "`/eightball <question>` — magic 8-ball",
    ],
    "🔧 Utility": [
        "`/help` `/ping` `/serverinfo` `/userinfo` `/avatar`",
        "`/roleinfo` `/channelinfo` `/poll`",
    ],
}


class Utility(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    # ── /help ─────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Browse all bread commands by category.")
    async def help(self, inter: disnake.ApplicationCommandInteraction) -> None:
        lines = []
        for category, cmds in _HELP_CATEGORIES.items():
            lines.append(f"**{category}**")
            lines.extend(cmds)
            lines.append("")
        await inter.response.send_message(components=[info("🍞 bread — Command Reference", *lines)], ephemeral=True)

    # ── /ping ─────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Check the bot's latency.")
    async def ping(self, inter: disnake.ApplicationCommandInteraction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await inter.response.send_message(components=[success(
            "🏓 Pong!",
            f"**WebSocket latency:** `{latency_ms}ms`",
        )])

    # ── /serverinfo ───────────────────────────────────────────────────────────

    @commands.slash_command(description="View information about this server.")
    async def serverinfo(self, inter: disnake.ApplicationCommandInteraction) -> None:
        guild = inter.guild
        if not guild:
            return
        bots = sum(1 for m in guild.members if m.bot)
        humans = guild.member_count - bots if guild.member_count else 0
        lines = [
            f"**Owner:** <@{guild.owner_id}>",
            f"**Created:** {full_time(int(guild.created_at.timestamp()))} ({relative_time(int(guild.created_at.timestamp()))})",
            f"**Members:** `{guild.member_count}` total — `{humans}` humans, `{bots}` bots",
            f"**Roles:** `{len(guild.roles)}`  |  **Channels:** `{len(guild.channels)}`",
            f"**Emojis:** `{len(guild.emojis)}`  |  **Stickers:** `{len(guild.stickers)}`",
            f"**Boosts:** `{guild.premium_subscription_count}` (Level `{guild.premium_tier}`)",
            f"**Verification:** `{guild.verification_level}`",
        ]
        if guild.description:
            lines.insert(0, f"> {guild.description}")
        await inter.response.send_message(components=[info(f"🏠 {guild.name}", *lines)])

    # ── /userinfo ─────────────────────────────────────────────────────────────

    @commands.slash_command(description="View information about a member.")
    async def userinfo(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = None,  # type: ignore[assignment]
    ) -> None:
        target = member or inter.author
        if not isinstance(target, disnake.Member):
            return
        roles = [r.mention for r in reversed(target.roles) if not r.is_default()]
        roles_str = " ".join(roles[:10]) + (f" *(+{len(roles) - 10} more)*" if len(roles) > 10 else "") if roles else "*(none)*"
        lines = [
            f"**Username:** `{target}`  |  **ID:** `{target.id}`",
            f"**Account created:** {full_time(int(target.created_at.timestamp()))} ({relative_time(int(target.created_at.timestamp()))})",
            f"**Joined server:** {full_time(int(target.joined_at.timestamp()))} ({relative_time(int(target.joined_at.timestamp()))})" if target.joined_at else "",
            f"**Roles ({len(roles)}):** {roles_str}",
        ]
        if target.bot:
            lines.append("> 🤖 This is a bot account.")
        if target.premium_since:
            lines.append(f"> 💎 Server boosting since {full_time(int(target.premium_since.timestamp()))}")
        await inter.response.send_message(components=[info(f"👤 {target.display_name}", *[l for l in lines if l])])

    # ── /avatar ───────────────────────────────────────────────────────────────

    @commands.slash_command(description="View a member's avatar.")
    async def avatar(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = None,  # type: ignore[assignment]
    ) -> None:
        target = member or inter.author
        if not isinstance(target, disnake.Member):
            return
        avatar_url = target.display_avatar.url
        await inter.response.send_message(components=[info(
            f"🖼️ {target.display_name}'s Avatar",
            f"[Click to open full size]({avatar_url})",
            f"> `{avatar_url}`",
        )])

    # ── /roleinfo ─────────────────────────────────────────────────────────────

    @commands.slash_command(description="View information about a role.")
    async def roleinfo(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
    ) -> None:
        dangerous = [
            p for p in ("administrator", "manage_guild", "manage_roles", "ban_members", "kick_members")
            if getattr(role.permissions, p, False)
        ]
        lines = [
            f"**ID:** `{role.id}`  |  **Color:** `{role.colour}`",
            f"**Members:** `{len(role.members)}`",
            f"**Position:** `{role.position}`",
            f"**Mentionable:** `{role.mentionable}`  |  **Hoisted:** `{role.hoist}`",
            f"**Created:** {full_time(int(role.created_at.timestamp()))}",
        ]
        if dangerous:
            lines.append(f"> ⚠️ Holds dangerous permissions: `{'`, `'.join(dangerous)}`")
        await inter.response.send_message(components=[info(f"🎭 Role: {role.name}", *lines)])

    # ── /channelinfo ──────────────────────────────────────────────────────────

    @commands.slash_command(description="View information about a channel.")
    async def channelinfo(
        self,
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.TextChannel = None,  # type: ignore[assignment]
    ) -> None:
        target = channel or inter.channel
        if not isinstance(target, disnake.TextChannel):
            return await inter.response.send_message(
                components=[info("Channel Info", "This command only works in text channels.")], ephemeral=True
            )
        lines = [
            f"**ID:** `{target.id}`",
            f"**Category:** `{target.category.name if target.category else 'None'}`",
            f"**Created:** {full_time(int(target.created_at.timestamp()))}",
            f"**NSFW:** `{target.is_nsfw()}`",
            f"**Slowmode:** `{target.slowmode_delay}s`",
        ]
        if target.topic:
            lines.insert(0, f"> {target.topic}")
        await inter.response.send_message(components=[info(f"#️⃣ #{target.name}", *lines)])

    # ── /poll ─────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Create a button-based poll.")
    async def poll(
        self,
        inter: disnake.ApplicationCommandInteraction,
        question: str = commands.Param(description="The poll question."),
        option1: str = commands.Param(description="First option."),
        option2: str = commands.Param(description="Second option."),
        option3: str = commands.Param(default=None, description="Third option (optional)."),  # type: ignore[assignment]
        option4: str = commands.Param(default=None, description="Fourth option (optional)."),  # type: ignore[assignment]
    ) -> None:
        options = [o for o in [option1, option2, option3, option4] if o]
        poll_id = secrets.token_hex(6)
        g = {"id": poll_id, "question": question, "options": options, "votes": {}}
        _polls[poll_id] = g
        btn_styles = [
            disnake.ButtonStyle.primary,
            disnake.ButtonStyle.danger,
            disnake.ButtonStyle.success,
            disnake.ButtonStyle.secondary,
        ]
        btns = disnake.ui.ActionRow(*[
            disnake.ui.Button(
                style=btn_styles[i % len(btn_styles)],
                label=f"{opt[:77]}",
                custom_id=f"poll:{poll_id}:{i}",
            )
            for i, opt in enumerate(options)
        ])
        await inter.response.send_message(components=[info(
            f"📊 {question}",
            "> Cast your vote by clicking a button below!",
            extra=[btns],
        )])

    # ── Poll button handler ───────────────────────────────────────────────────

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction) -> None:
        cid = inter.component.custom_id
        if not cid.startswith("poll:"):
            return
        parts = cid.split(":")
        poll_id, choice_idx = parts[1], int(parts[2])
        g = _polls.get(poll_id)
        if not g:
            return await inter.response.send_message(
                components=[info("Expired", "This poll has expired.")], ephemeral=True
            )
        g["votes"][str(inter.author.id)] = choice_idx
        options = g["options"]
        total = len(g["votes"])
        vote_counts = [sum(1 for v in g["votes"].values() if v == i) for i in range(len(options))]
        result_lines = []
        for i, opt in enumerate(options):
            count = vote_counts[i]
            pct = round(count / total * 100) if total else 0
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            result_lines.append(f"**{opt}** — `{bar}` **{pct}%** (`{count}` votes)")
        btn_styles = [
            disnake.ButtonStyle.primary,
            disnake.ButtonStyle.danger,
            disnake.ButtonStyle.success,
            disnake.ButtonStyle.secondary,
        ]
        btns = disnake.ui.ActionRow(*[
            disnake.ui.Button(
                style=btn_styles[i % len(btn_styles)],
                label=f"{opt[:60]} ({vote_counts[i]})",
                custom_id=f"poll:{poll_id}:{i}",
            )
            for i, opt in enumerate(options)
        ])
        await inter.response.edit_message(components=[info(
            f"📊 {g['question']}",
            f"> **{total}** vote{'s' if total != 1 else ''} cast",
            *result_lines,
            extra=[btns],
        )])


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(Utility(bot))
