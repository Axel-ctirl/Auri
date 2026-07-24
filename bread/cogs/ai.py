from __future__ import annotations

import secrets

import disnake
from disnake.ext import commands

from bread.services.ai_client import AIError
from bread.services.ai_client import ask as _ai_ask
from bread.ui.components import bread_container, error, info, success

_trivia_games: dict[str, dict] = {}
_wyr_games: dict[str, dict] = {}


class AI(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    # ── /ask ──────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Ask the AI anything.")
    async def ask(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="Your question or prompt."),
    ) -> None:
        await inter.response.defer()
        try:
            answer = await _ai_ask(prompt)
        except AIError as exc:
            return await inter.edit_original_response(components=[error("AI Error", str(exc))])
        await inter.edit_original_response(components=[info(
            "💬 Ask",
            f"**Q:** {prompt}",
            f"> {answer}",
        )])

    # ── /roast ────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Get a light-hearted AI roast of a user.")
    async def roast(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
    ) -> None:
        await inter.response.defer()
        try:
            text = await _ai_ask(
                f"Write a short, funny, light-hearted roast of a Discord user named '{member.display_name}'. "
                "One sentence. Keep it playful, not mean.",
                max_tokens=150,
            )
        except AIError as exc:
            return await inter.edit_original_response(components=[error("AI Error", str(exc))])
        await inter.edit_original_response(components=[info(
            f"🔥 Roasting {member.display_name}",
            f"> {text}",
        )])

    # ── /compliment ───────────────────────────────────────────────────────────

    @commands.slash_command(description="Send an AI-generated compliment to a user.")
    async def compliment(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
    ) -> None:
        await inter.response.defer()
        try:
            text = await _ai_ask(
                f"Write a short, genuine, heartfelt compliment for a Discord user named '{member.display_name}'. "
                "One sentence.",
                max_tokens=150,
            )
        except AIError as exc:
            return await inter.edit_original_response(components=[error("AI Error", str(exc))])
        await inter.edit_original_response(components=[success(
            f"💝 Complimenting {member.display_name}",
            f"> {text}",
        )])

    # ── /eightball ────────────────────────────────────────────────────────────

    @commands.slash_command(name="eightball", description="Ask the magic 8-ball a question.")
    async def eightball(
        self,
        inter: disnake.ApplicationCommandInteraction,
        question: str = commands.Param(description="Your yes/no question."),
    ) -> None:
        await inter.response.defer()
        try:
            answer = await _ai_ask(
                f"Give a mystical, 8-ball style answer to this question: '{question}'. "
                "Max 20 words. Be cryptic and fun.",
                max_tokens=80,
            )
        except AIError as exc:
            return await inter.edit_original_response(components=[error("AI Error", str(exc))])
        await inter.edit_original_response(components=[info(
            "🎱 Magic 8-Ball",
            f"**Q:** {question}",
            f"> 🎱 {answer}",
        )])

    # ── /trivia ───────────────────────────────────────────────────────────────

    @commands.slash_command(description="AI-generated trivia question with button answers.")
    async def trivia(self, inter: disnake.ApplicationCommandInteraction) -> None:
        await inter.response.defer()
        try:
            raw = await _ai_ask(
                "Generate a trivia question with 4 answer choices. "
                "Format your response EXACTLY like this:\n"
                "Q: <question>\n"
                "A: <option A>\n"
                "B: <option B>\n"
                "C: <option C>\n"
                "D: <option D>\n"
                "CORRECT: <A, B, C, or D>",
                max_tokens=300,
            )
        except AIError as exc:
            return await inter.edit_original_response(components=[error("AI Error", str(exc))])
        lines: dict[str, str] = {}
        for line in raw.strip().splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                lines[k.strip()] = v.strip()
        question = lines.get("Q", "Trivia question")
        options = [lines.get(k, f"Option {k}") for k in ("A", "B", "C", "D")]
        correct_letter = lines.get("CORRECT", "A").strip().upper()[:1]
        correct_idx = {"A": 0, "B": 1, "C": 2, "D": 3}.get(correct_letter, 0)
        game_id = secrets.token_hex(6)
        g = {
            "id": game_id,
            "question": question,
            "options": options,
            "correct_idx": correct_idx,
            "answers": {},
        }
        _trivia_games[game_id] = g
        opt_letters = list("ABCD")
        btn_row = disnake.ui.ActionRow(*[
            disnake.ui.Button(
                style=disnake.ButtonStyle.secondary,
                label=f"{opt_letters[i]}: {opt[:50]}",
                custom_id=f"trivia:{game_id}:{i}",
            )
            for i, opt in enumerate(options)
        ])
        await inter.edit_original_response(components=[info(
            "🧠 Trivia",
            f"**Q:** {question}",
            "> Pick your answer below!",
            extra=[btn_row],
        )])

    # ── /wyr ──────────────────────────────────────────────────────────────────

    @commands.slash_command(name="wyr", description="AI-generated 'Would You Rather' with live voting.")
    async def wyr(self, inter: disnake.ApplicationCommandInteraction) -> None:
        await inter.response.defer()
        try:
            raw = await _ai_ask(
                "Generate a fun, interesting 'Would You Rather' question with two options. "
                "Format EXACTLY like this:\n"
                "A: <option A>\n"
                "B: <option B>",
                max_tokens=150,
            )
        except AIError as exc:
            return await inter.edit_original_response(components=[error("AI Error", str(exc))])
        lines: dict[str, str] = {}
        for line in raw.strip().splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                lines[k.strip()] = v.strip()
        opt_a = lines.get("A", "Option A")
        opt_b = lines.get("B", "Option B")
        game_id = secrets.token_hex(6)
        g = {"id": game_id, "options": [opt_a, opt_b], "votes": {}}
        _wyr_games[game_id] = g
        btn_row = disnake.ui.ActionRow(
            disnake.ui.Button(style=disnake.ButtonStyle.primary, label=f"🅰️ {opt_a[:60]}", custom_id=f"wyr:{game_id}:0"),
            disnake.ui.Button(style=disnake.ButtonStyle.danger, label=f"🅱️ {opt_b[:60]}", custom_id=f"wyr:{game_id}:1"),
        )
        await inter.edit_original_response(components=[info(
            "🤔 Would You Rather...",
            "> Vote by clicking a button!",
            extra=[btn_row],
        )])

    # ── Button handler ────────────────────────────────────────────────────────

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction) -> None:
        cid = inter.component.custom_id
        if cid.startswith("trivia:"):
            await self._handle_trivia(inter)
        elif cid.startswith("wyr:"):
            await self._handle_wyr(inter)

    async def _handle_trivia(self, inter: disnake.MessageInteraction) -> None:
        parts = inter.component.custom_id.split(":")
        game_id, chosen_idx = parts[1], int(parts[2])
        g = _trivia_games.get(game_id)
        if not g:
            return await inter.response.send_message(
                components=[error("Expired", "This trivia question has expired.")], ephemeral=True
            )
        uid = str(inter.author.id)
        if uid in g["answers"]:
            prev_correct = g["answers"][uid] == g["correct_idx"]
            verb = "correctly ✅" if prev_correct else "incorrectly ❌"
            return await inter.response.send_message(
                components=[info("Already Answered", f"You already answered this question — {verb}.")], ephemeral=True
            )
        g["answers"][uid] = chosen_idx
        correct = chosen_idx == g["correct_idx"]
        opt_letters = list("ABCD")
        correct_answer = f"**{opt_letters[g['correct_idx']]}: {g['options'][g['correct_idx']]}**"
        correct_count = sum(1 for a in g["answers"].values() if a == g["correct_idx"])
        total = len(g["answers"])
        if correct:
            feedback = f"✅ Correct! The answer is {correct_answer}."
        else:
            feedback = f"❌ Wrong! The correct answer is {correct_answer}."
        await inter.response.send_message(
            components=[(success if correct else error)(
                "Trivia Answer",
                feedback,
                f"> `{correct_count}/{total}` players answered correctly so far.",
            )],
            ephemeral=True,
        )

    async def _handle_wyr(self, inter: disnake.MessageInteraction) -> None:
        parts = inter.component.custom_id.split(":")
        game_id, choice_idx = parts[1], int(parts[2])
        g = _wyr_games.get(game_id)
        if not g:
            return await inter.response.send_message(
                components=[error("Expired", "This WYR question has expired.")], ephemeral=True
            )
        g["votes"][str(inter.author.id)] = choice_idx
        votes_a = sum(1 for v in g["votes"].values() if v == 0)
        votes_b = sum(1 for v in g["votes"].values() if v == 1)
        total = len(g["votes"])
        pct_a = round(votes_a / total * 100) if total else 0
        pct_b = 100 - pct_a if total else 0
        opt_a, opt_b = g["options"]
        btn_row = disnake.ui.ActionRow(
            disnake.ui.Button(
                style=disnake.ButtonStyle.primary,
                label=f"🅰️ {opt_a[:40]} ({pct_a}%)",
                custom_id=f"wyr:{game_id}:0",
            ),
            disnake.ui.Button(
                style=disnake.ButtonStyle.danger,
                label=f"🅱️ {opt_b[:40]} ({pct_b}%)",
                custom_id=f"wyr:{game_id}:1",
            ),
        )
        await inter.response.edit_message(components=[info(
            "🤔 Would You Rather...",
            f"> **{total}** vote{'s' if total != 1 else ''} total",
            extra=[btn_row],
        )])


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(AI(bot))
