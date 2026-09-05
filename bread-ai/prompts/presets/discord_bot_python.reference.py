"""A disnake bot that remembers what people say and quotes one back at random.

Every message in a channel is recorded, and `/random` replies with one of them,
picked at random from that same channel.

Run it:

    pip install "disnake>=2.10,<3"
    export DISCORD_TOKEN="your token"        # set DISCORD_TOKEN=... on Windows
    python random_message_bot.py

In the Discord developer portal, under Bot, turn on the **Message Content
Intent**. Without it `message.content` arrives empty and the bot records
nothing.
"""

from __future__ import annotations

import os
import random
from collections import defaultdict, deque

import disnake
from disnake.ext import commands

# Per channel, not global: a quote should come from the channel it is asked in.
# A deque with a maxlen keeps a busy server from growing this without limit.
HISTORY_LIMIT = 500

recorded: defaultdict[int, deque[str]] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))

intents = disnake.Intents.default()
intents.message_content = True

bot = commands.InteractionBot(intents=intents)


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} ({bot.user.id})")


@bot.event
async def on_message(message: disnake.Message) -> None:
    # Ignore bots, including this one, or it will eventually quote itself.
    if message.author.bot:
        return
    # Attachments and stickers arrive with empty content and nothing to quote.
    text = message.content.strip()
    if not text:
        return
    recorded[message.channel.id].append(text)


@bot.slash_command(name="random", description="Reply with a random message from this channel.")
async def random_message(inter: disnake.ApplicationCommandInteraction) -> None:
    history = recorded[inter.channel_id]
    if not history:
        await inter.response.send_message(
            "I have not seen any messages in this channel yet. "
            "I only remember what was said while I was online.",
            ephemeral=True,
        )
        return

    chosen = random.choice(list(history))
    await inter.response.send_message(
        f"> {chosen}",
        # Quoting text verbatim would otherwise let anyone make the bot ping
        # @everyone by saying it once.
        allowed_mentions=disnake.AllowedMentions.none(),
    )


@bot.slash_command(name="remembered", description="How many messages I remember from this channel.")
async def remembered(inter: disnake.ApplicationCommandInteraction) -> None:
    count = len(recorded[inter.channel_id])
    await inter.response.send_message(f"{count} message(s) from this channel.", ephemeral=True)


def main() -> None:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_TOKEN to your bot token before starting the bot.")
    bot.run(token)


if __name__ == "__main__":
    main()
