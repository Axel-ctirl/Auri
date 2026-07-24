from __future__ import annotations

import os

from disnake import Colour
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "moonshotai/kimi-k2")

BREAD_COLOR = Colour(0xC68842)
ERROR_COLOR = Colour(0xE05B5B)
SUCCESS_COLOR = Colour(0x5BC272)

BREAD_EMOJI = "🍞"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
