from __future__ import annotations

import random
import secrets
from typing import Optional

import disnake
from disnake.ext import commands

from bread.ui.components import bread_container, error, info, success

# ─── In-memory game state ─────────────────────────────────────────────────────
_ttt_games: dict[str, dict] = {}
_ms_games: dict[str, dict] = {}
_hang_games: dict[str, dict] = {}
_rps_games: dict[str, int] = {}  # game_id -> owner_id

# ═══ Tic-Tac-Toe ═════════════════════════════════════════════════════════════

_WIN_LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def _ttt_winner(board: list) -> Optional[str]:
    for a, b, c in _WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def _ttt_minimax(board: list, is_max: bool, alpha: float, beta: float) -> float:
    w = _ttt_winner(board)
    if w == "O":
        return 1.0
    if w == "X":
        return -1.0
    if None not in board:
        return 0.0
    if is_max:
        best = -2.0
        for i in range(9):
            if board[i] is None:
                board[i] = "O"
                best = max(best, _ttt_minimax(board, False, alpha, beta))
                board[i] = None
                alpha = max(alpha, best)
                if beta <= alpha:
                    break
        return best
    else:
        best = 2.0
        for i in range(9):
            if board[i] is None:
                board[i] = "X"
                best = min(best, _ttt_minimax(board, True, alpha, beta))
                board[i] = None
                beta = min(beta, best)
                if beta <= alpha:
                    break
        return best


def _ttt_ai_move(board: list, difficulty: str) -> int:
    empty = [i for i in range(9) if board[i] is None]
    if difficulty == "easy":
        return random.choice(empty)
    best_score, best_move = -2.0, empty[0]
    for i in empty:
        board[i] = "O"
        score = _ttt_minimax(board, False, -2.0, 2.0)
        board[i] = None
        if score > best_score:
            best_score, best_move = score, i
    return best_move


_TTT_CELL = {
    None: ("​", disnake.ButtonStyle.secondary),
    "X": ("✖", disnake.ButtonStyle.danger),
    "O": ("⭕", disnake.ButtonStyle.primary),
}


def _ttt_build_rows(g: dict) -> list[disnake.ui.ActionRow]:
    board, gid, ended = g["board"], g["id"], g.get("ended", False)
    rows = []
    for row in range(3):
        btns = []
        for col in range(3):
            idx = row * 3 + col
            val = board[idx]
            label, style = _TTT_CELL[val]
            btns.append(disnake.ui.Button(
                style=style, label=label,
                custom_id=f"ttt:{gid}:{idx}",
                disabled=val is not None or ended,
            ))
        rows.append(disnake.ui.ActionRow(*btns))
    return rows


def _ttt_render(g: dict, status: str) -> list:
    player_o = "🤖 AI" if g.get("vs_ai") else f"<@{g['players']['O']}>"
    return [bread_container(
        "✖ Tic-Tac-Toe",
        f"**✖:** <@{g['players']['X']}>  vs  **⭕:** {player_o}",
        f"> {status}",
        extra=_ttt_build_rows(g),
    )]


# ═══ Minesweeper ═════════════════════════════════════════════════════════════

MS_ROWS, MS_COLS = 5, 5
_MS_NUM = ["　", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]


def _ms_new_mines(count: int) -> set[tuple[int, int]]:
    mines: set[tuple[int, int]] = set()
    while len(mines) < count:
        mines.add((random.randint(0, MS_ROWS - 1), random.randint(0, MS_COLS - 1)))
    return mines


def _ms_count(mines: set, r: int, c: int) -> int:
    return sum(
        1 for dr in (-1, 0, 1) for dc in (-1, 0, 1)
        if (dr or dc) and (r + dr, c + dc) in mines
    )


def _ms_flood(board: dict, r: int, c: int) -> None:
    if not (0 <= r < MS_ROWS and 0 <= c < MS_COLS):
        return
    pos = (r, c)
    if pos in board["revealed"] or pos in board["flagged"] or pos in board["mines"]:
        return
    board["revealed"].add(pos)
    if _ms_count(board["mines"], r, c) == 0:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr or dc:
                    _ms_flood(board, r + dr, c + dc)


def _ms_build_rows(g: dict) -> list[disnake.ui.ActionRow]:
    board, gid = g["board"], g["id"]
    mines, revealed, flagged = board["mines"], board["revealed"], board["flagged"]
    over, won = board["game_over"], board["won"]
    ended = over or won
    rows = []
    for r in range(MS_ROWS):
        btns = []
        for c in range(MS_COLS):
            pos = (r, c)
            if over and pos in mines:
                label = "💥" if pos in revealed else "💣"
                style, disabled = disnake.ButtonStyle.danger, True
            elif pos in revealed:
                n = _ms_count(mines, r, c)
                label = _MS_NUM[n]
                style = disnake.ButtonStyle.success if n == 0 else disnake.ButtonStyle.primary
                disabled = True
            elif pos in flagged:
                label, style, disabled = "🚩", disnake.ButtonStyle.danger, ended
            else:
                label, style, disabled = "​", disnake.ButtonStyle.secondary, ended
            btns.append(disnake.ui.Button(
                style=style, label=label,
                custom_id=f"ms:{gid}:r{r}c{c}",
                disabled=disabled,
            ))
        rows.append(disnake.ui.ActionRow(*btns))
    flag_mode = board["flag_mode"]
    rows.append(disnake.ui.ActionRow(
        disnake.ui.Button(
            style=disnake.ButtonStyle.danger if flag_mode else disnake.ButtonStyle.secondary,
            label="🚩 Flag Mode: ON" if flag_mode else "🔍 Reveal Mode",
            custom_id=f"ms:{gid}:flag",
            disabled=ended,
        ),
        disnake.ui.Button(
            style=disnake.ButtonStyle.secondary, label="🔄 New Game",
            custom_id=f"ms:{gid}:new",
        ),
    ))
    return rows


def _ms_render(g: dict, status: str) -> list:
    board = g["board"]
    safe_total = MS_ROWS * MS_COLS - len(board["mines"])
    safe_rev = len(board["revealed"])
    return [bread_container(
        "💣 Minesweeper",
        f"**💣 Mines:** `{len(board['mines'])}`  |  **Safe revealed:** `{safe_rev}/{safe_total}`",
        f"> {status}",
        extra=_ms_build_rows(g),
    )]


# ═══ Hangman ═════════════════════════════════════════════════════════════════

_HANG_STAGES = [
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========```",
]
_MAX_WRONG = len(_HANG_STAGES) - 1

_WORDS = [
    "python", "discord", "giveaway", "moderator", "administrator",
    "wavelength", "cryptography", "javascript", "engineering", "philosophy",
    "breadcrumb", "saxophone", "laboratory", "vocabulary", "imagination",
    "thunderstorm", "championship", "caterpillar", "celebration", "development",
    "adventure", "watermelon", "skateboard", "helicopter", "astronaut",
]

_HANG_CHUNKS = ["ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY", "Z"]


def _hang_build_rows(g: dict) -> list[disnake.ui.ActionRow]:
    gid, guessed, ended = g["id"], g["guessed"], g.get("ended", False)
    rows = []
    for chunk in _HANG_CHUNKS:
        btns = []
        for letter in chunk:
            used = letter.lower() in guessed
            btns.append(disnake.ui.Button(
                style=disnake.ButtonStyle.danger if used else disnake.ButtonStyle.secondary,
                label=letter,
                custom_id=f"hang:{gid}:{letter.lower()}",
                disabled=used or ended,
            ))
        rows.append(disnake.ui.ActionRow(*btns))
    return rows


def _hang_render(g: dict, status: str) -> list:
    word, guessed, wrong = g["word"], g["guessed"], g["wrong"]
    display = " ".join(c if c in guessed else "\\_" for c in word)
    stage = _HANG_STAGES[min(wrong, _MAX_WRONG)]
    wrong_letters = ", ".join(f"`{l.upper()}`" for l in sorted(guessed) if l not in word) or "*(none)*"
    return [bread_container(
        "📝 Hangman",
        stage,
        f"**Word:** `{display}`",
        f"**Wrong guesses:** {wrong_letters}  **({wrong}/{_MAX_WRONG})**",
        f"> {status}",
        extra=_hang_build_rows(g),
    )]


# ═══ Cog ═════════════════════════════════════════════════════════════════════

class Games(commands.Cog):
    def __init__(self, bot: commands.InteractionBot) -> None:
        self.bot = bot

    # ── /tictactoe ────────────────────────────────────────────────────────────

    @commands.slash_command(description="Play tic-tac-toe — against a friend or the AI!")
    async def tictactoe(
        self,
        inter: disnake.ApplicationCommandInteraction,
        opponent: disnake.Member = None,  # type: ignore[assignment]
        difficulty: str = commands.Param(default="hard", choices=["easy", "hard"], description="AI difficulty (ignored for PvP)."),
    ) -> None:
        vs_ai = opponent is None or opponent.bot or opponent.id == inter.author.id
        if not vs_ai and opponent.id == inter.author.id:
            vs_ai = True
        game_id = secrets.token_hex(6)
        bot_uid = self.bot.user.id if self.bot.user else 0  # type: ignore[union-attr]
        players = {"X": inter.author.id, "O": bot_uid if vs_ai else opponent.id}
        g: dict = {
            "id": game_id,
            "board": [None] * 9,
            "players": players,
            "current_turn": "X",
            "vs_ai": vs_ai,
            "difficulty": difficulty,
            "ended": False,
        }
        _ttt_games[game_id] = g
        opp_str = "🤖 AI" if vs_ai else opponent.mention  # type: ignore[union-attr]
        status = f"{inter.author.mention}'s turn! (**✖**)"
        await inter.response.send_message(components=_ttt_render(g, f"**✖:** {inter.author.mention}  vs  **⭕:** {opp_str}\n> {status}"))

    # ── /minesweeper ──────────────────────────────────────────────────────────

    @commands.slash_command(description="Play minesweeper on a 5×5 button grid!")
    async def minesweeper(
        self,
        inter: disnake.ApplicationCommandInteraction,
        mines: int = commands.Param(default=5, ge=1, le=15, description="Number of mines (1–15)."),
    ) -> None:
        game_id = secrets.token_hex(6)
        board: dict = {
            "mines": _ms_new_mines(mines),
            "revealed": set(),
            "flagged": set(),
            "game_over": False,
            "won": False,
            "flag_mode": False,
        }
        g = {"id": game_id, "board": board, "owner_id": inter.author.id}
        _ms_games[game_id] = g
        await inter.response.send_message(
            components=_ms_render(g, "Click cells to reveal them. Use **🚩 Flag Mode** to place flags.")
        )

    # ── /rps ─────────────────────────────────────────────────────────────────

    @commands.slash_command(description="Play rock, paper, scissors against the bot!")
    async def rps(self, inter: disnake.ApplicationCommandInteraction) -> None:
        game_id = secrets.token_hex(6)
        _rps_games[game_id] = inter.author.id
        choices_row = disnake.ui.ActionRow(
            disnake.ui.Button(style=disnake.ButtonStyle.secondary, label="🪨 Rock", custom_id=f"rps:{game_id}:rock"),
            disnake.ui.Button(style=disnake.ButtonStyle.secondary, label="📄 Paper", custom_id=f"rps:{game_id}:paper"),
            disnake.ui.Button(style=disnake.ButtonStyle.secondary, label="✂️ Scissors", custom_id=f"rps:{game_id}:scissors"),
        )
        await inter.response.send_message(components=[bread_container(
            "🪨 Rock Paper Scissors",
            f"{inter.author.mention}, pick your move!",
            extra=[choices_row],
        )])

    # ── /hangman ─────────────────────────────────────────────────────────────

    @commands.slash_command(description="Play hangman — guess the hidden word letter by letter!")
    async def hangman(self, inter: disnake.ApplicationCommandInteraction) -> None:
        word = random.choice(_WORDS)
        game_id = secrets.token_hex(6)
        g: dict = {
            "id": game_id,
            "word": word,
            "guessed": set(),
            "wrong": 0,
            "owner_id": inter.author.id,
            "ended": False,
        }
        _hang_games[game_id] = g
        await inter.response.send_message(
            components=_hang_render(g, f"{inter.author.mention}, guess the **{len(word)}-letter word** by clicking letters!")
        )

    # ── Button dispatcher ─────────────────────────────────────────────────────

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction) -> None:
        cid = inter.component.custom_id
        if cid.startswith("ttt:"):
            await self._handle_ttt(inter)
        elif cid.startswith("ms:"):
            await self._handle_ms(inter)
        elif cid.startswith("hang:"):
            await self._handle_hang(inter)
        elif cid.startswith("rps:"):
            await self._handle_rps(inter)

    # ── Tic-Tac-Toe handler ───────────────────────────────────────────────────

    async def _handle_ttt(self, inter: disnake.MessageInteraction) -> None:
        parts = inter.component.custom_id.split(":")
        game_id, cell_idx = parts[1], int(parts[2])
        g = _ttt_games.get(game_id)
        if not g:
            return await inter.response.send_message(
                components=[error("Expired", "This game has expired.")], ephemeral=True
            )
        if g.get("ended"):
            return await inter.response.send_message(
                components=[error("Game Over", "This game has already ended.")], ephemeral=True
            )
        current = g["current_turn"]
        expected = g["players"][current]
        if inter.author.id != expected:
            name = "✖ X" if current == "X" else "⭕ O"
            return await inter.response.send_message(
                components=[error("Not Your Turn", f"It's **{name}**'s turn.")], ephemeral=True
            )
        board = g["board"]
        if board[cell_idx] is not None:
            return await inter.response.send_message(
                components=[error("Invalid Move", "That cell is already occupied.")], ephemeral=True
            )
        board[cell_idx] = current
        winner = _ttt_winner(board)
        if winner:
            g["ended"] = True
            if g.get("vs_ai") and winner == "O":
                status = "🤖 **AI wins!** Better luck next time."
            else:
                status = f"🎉 <@{g['players'][winner]}> **wins!**"
            return await inter.response.edit_message(components=_ttt_render(g, status))
        if None not in board:
            g["ended"] = True
            return await inter.response.edit_message(components=_ttt_render(g, "It's a **draw**! 🤝"))
        g["current_turn"] = "O" if current == "X" else "X"
        if g.get("vs_ai") and g["current_turn"] == "O":
            ai_idx = _ttt_ai_move(board, g.get("difficulty", "hard"))
            board[ai_idx] = "O"
            winner = _ttt_winner(board)
            if winner:
                g["ended"] = True
                return await inter.response.edit_message(components=_ttt_render(g, "🤖 **AI wins!** Better luck next time."))
            if None not in board:
                g["ended"] = True
                return await inter.response.edit_message(components=_ttt_render(g, "It's a **draw**! 🤝"))
            g["current_turn"] = "X"
            return await inter.response.edit_message(components=_ttt_render(g, f"<@{g['players']['X']}>'s turn! (**✖**)"))
        next_uid = g["players"][g["current_turn"]]
        symbol = "✖" if g["current_turn"] == "X" else "⭕"
        await inter.response.edit_message(components=_ttt_render(g, f"<@{next_uid}>'s turn! (**{symbol}**)"))

    # ── Minesweeper handler ───────────────────────────────────────────────────

    async def _handle_ms(self, inter: disnake.MessageInteraction) -> None:
        import re
        cid = inter.component.custom_id
        parts = cid.split(":", 2)
        game_id, action = parts[1], parts[2]
        g = _ms_games.get(game_id)
        if not g:
            return await inter.response.send_message(
                components=[error("Expired", "This game has expired.")], ephemeral=True
            )
        if inter.author.id != g["owner_id"]:
            return await inter.response.send_message(
                components=[error("Not Your Game", "Start your own with `/minesweeper`!")], ephemeral=True
            )
        board = g["board"]
        if action == "flag":
            board["flag_mode"] = not board["flag_mode"]
            mode = "**Flag** 🚩" if board["flag_mode"] else "**Reveal** 🔍"
            return await inter.response.edit_message(components=_ms_render(g, f"Switched to {mode} mode."))
        if action == "new":
            mine_count = len(board["mines"])
            g["board"] = {
                "mines": _ms_new_mines(mine_count),
                "revealed": set(),
                "flagged": set(),
                "game_over": False,
                "won": False,
                "flag_mode": False,
            }
            return await inter.response.edit_message(
                components=_ms_render(g, "New game! Click cells to reveal them.")
            )
        m = re.match(r"r(\d+)c(\d+)", action)
        if not m:
            return
        r, c = int(m.group(1)), int(m.group(2))
        pos = (r, c)
        if board["game_over"] or board["won"]:
            return await inter.response.send_message(
                components=[error("Game Over", "Use **🔄 New Game** to start fresh.")], ephemeral=True
            )
        if board["flag_mode"]:
            if pos in board["revealed"]:
                return await inter.response.send_message(
                    components=[error("Already Revealed", "Can't flag a cell that's already revealed.")], ephemeral=True
                )
            if pos in board["flagged"]:
                board["flagged"].remove(pos)
                status = f"Flag removed from `({r}, {c})`."
            else:
                board["flagged"].add(pos)
                status = f"🚩 Flagged `({r}, {c})`."
            return await inter.response.edit_message(components=_ms_render(g, status))
        if pos in board["flagged"]:
            return await inter.response.send_message(
                components=[error("Flagged", "Remove the flag first before revealing.")], ephemeral=True
            )
        if pos in board["revealed"]:
            return
        if pos in board["mines"]:
            board["game_over"] = True
            board["revealed"].add(pos)
            return await inter.response.edit_message(components=_ms_render(g, "💥 **You hit a mine!** Game over."))
        _ms_flood(board, r, c)
        safe_total = MS_ROWS * MS_COLS - len(board["mines"])
        if len(board["revealed"]) >= safe_total:
            board["won"] = True
            return await inter.response.edit_message(
                components=_ms_render(g, "🎉 **You cleared the board!** You win!")
            )
        remaining = safe_total - len(board["revealed"])
        await inter.response.edit_message(
            components=_ms_render(g, f"`{remaining}` safe cell{'s' if remaining != 1 else ''} remaining.")
        )

    # ── Hangman handler ───────────────────────────────────────────────────────

    async def _handle_hang(self, inter: disnake.MessageInteraction) -> None:
        parts = inter.component.custom_id.split(":")
        game_id, letter = parts[1], parts[2]
        g = _hang_games.get(game_id)
        if not g:
            return await inter.response.send_message(
                components=[error("Expired", "This game has expired.")], ephemeral=True
            )
        if inter.author.id != g["owner_id"]:
            return await inter.response.send_message(
                components=[error("Not Your Game", "Start your own with `/hangman`!")], ephemeral=True
            )
        if g.get("ended"):
            return await inter.response.send_message(
                components=[error("Game Over", "This game has already ended.")], ephemeral=True
            )
        word, guessed = g["word"], g["guessed"]
        if letter in guessed:
            return
        guessed.add(letter)
        if letter not in word:
            g["wrong"] += 1
            if g["wrong"] >= _MAX_WRONG:
                g["ended"] = True
                return await inter.response.edit_message(
                    components=_hang_render(g, f"💀 You lost! The word was **{word}**.")
                )
            remaining_wrong = _MAX_WRONG - g["wrong"]
            return await inter.response.edit_message(
                components=_hang_render(g, f"❌ `{letter.upper()}` is not in the word. `{remaining_wrong}` wrong guess{'es' if remaining_wrong != 1 else ''} left.")
            )
        if all(ch in guessed for ch in word):
            g["ended"] = True
            return await inter.response.edit_message(
                components=_hang_render(g, f"🎉 You guessed it — the word was **{word}**!")
            )
        await inter.response.edit_message(
            components=_hang_render(g, f"✅ `{letter.upper()}` is in the word! Keep going.")
        )

    # ── RPS handler ───────────────────────────────────────────────────────────

    async def _handle_rps(self, inter: disnake.MessageInteraction) -> None:
        parts = inter.component.custom_id.split(":")
        game_id, choice = parts[1], parts[2]
        owner_id = _rps_games.get(game_id)
        if owner_id is None:
            return await inter.response.send_message(
                components=[error("Expired", "This game has expired.")], ephemeral=True
            )
        if inter.author.id != owner_id:
            return await inter.response.send_message(
                components=[error("Not Your Game", "Use `/rps` to start your own!")], ephemeral=True
            )
        del _rps_games[game_id]
        bot_choice = random.choice(["rock", "paper", "scissors"])
        beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
        symbols = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
        user_sym, bot_sym = symbols[choice], symbols[bot_choice]
        if choice == bot_choice:
            result, container = "It's a **tie**! 🤝", info
        elif beats[choice] == bot_choice:
            result, container = "You **win**! 🎉", success
        else:
            result, container = "You **lose**! 😔", error
        await inter.response.edit_message(components=[container(
            "🪨 Rock Paper Scissors",
            f"**You:** {user_sym} `{choice.capitalize()}`",
            f"**Bot:** {bot_sym} `{bot_choice.capitalize()}`",
            f"> {result}",
        )])


def setup(bot: commands.InteractionBot) -> None:
    bot.add_cog(Games(bot))
