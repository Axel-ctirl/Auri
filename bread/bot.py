from __future__ import annotations

import logging
import pkgutil

import disnake
from disnake.ext import commands

from bread.config import BOT_TOKEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
_log = logging.getLogger("bread")

intents = disnake.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.InteractionBot(intents=intents)


def _load_package(package_name: str) -> None:
    package = __import__(package_name, fromlist=["_"])
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name.startswith("_"):
            continue
        full_name = f"{package_name}.{module_info.name}"
        bot.load_extension(full_name)
        _log.info("Loaded extension %s", full_name)


@bot.event
async def on_ready() -> None:
    user = bot.user
    _log.info("bread is online as %s (%s)", user, user.id if user else "unknown")


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
    _load_package("bread.cogs")
    _load_package("bread.events")
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
