"""Library wiring mistakes: the ones a name check cannot see.

Each rule has a case that must fire and a case that must not. A rule that fires
on working code gets switched off and stops helping, so the negative cases carry
as much weight as the positive ones.
"""

from __future__ import annotations

from app.services.quality.api_check import check_code


def problems(source: str) -> list[str]:
    return [finding.message for finding in check_code(source).certain]


def suspicions(source: str) -> list[str]:
    return [finding.message for finding in check_code(source).likely]


# ------------------------------------------------------- message content intent
def test_reading_content_without_the_intent_is_caught():
    source = """
import disnake
from disnake.ext import commands

bot = commands.Bot(command_prefix="!", intents=disnake.Intents.default())


@bot.event
async def on_message(message):
    print(message.content)
"""
    assert any("message content intent" in problem for problem in problems(source))


def test_enabling_the_intent_by_attribute_is_accepted():
    source = """
import disnake
from disnake.ext import commands

intents = disnake.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_message(message):
    print(message.content)
"""
    assert not any("message content intent" in problem for problem in problems(source))


def test_enabling_the_intent_by_keyword_is_accepted():
    source = """
import disnake
from disnake.ext import commands

bot = commands.Bot(command_prefix="!", intents=disnake.Intents(message_content=True))


@bot.event
async def on_message(message):
    print(message.content)
"""
    assert not any("message content intent" in problem for problem in problems(source))


def test_intents_all_is_accepted():
    source = """
import disnake
from disnake.ext import commands

bot = commands.Bot(command_prefix="!", intents=disnake.Intents.all())


@bot.event
async def on_message(message):
    print(message.content)
"""
    assert not any("message content intent" in problem for problem in problems(source))


def test_intents_built_elsewhere_are_not_guessed_at():
    """Nothing here says what the passed-in intents contain, so say nothing."""

    source = """
import disnake
from disnake.ext import commands


def build(intents):
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_message(message):
        print(message.content)

    return bot
"""
    assert not any("message content intent" in problem for problem in problems(source))


# ------------------------------------------------------------------- cog wiring
def test_a_cog_nothing_loads_is_caught():
    source = """
import disnake
from disnake.ext import commands


class Greeter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


bot = commands.InteractionBot()
bot.run("token")
"""
    assert any("nothing loads" in problem for problem in problems(source))


def test_an_extension_file_is_left_alone():
    """A `setup(bot)` and no bot of its own is a file meant to be loaded."""

    source = """
from disnake.ext import commands


class Greeter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Greeter(bot))
"""
    assert not any("nothing loads" in problem for problem in problems(source))


def test_a_setup_nothing_calls_is_caught_when_the_answer_builds_its_own_bot():
    source = """
import disnake
from disnake.ext import commands


class Greeter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Greeter(bot))


bot = commands.InteractionBot()
bot.run("token")
"""
    assert any("nothing loads" in problem for problem in problems(source))


def test_adding_the_cog_directly_is_accepted():
    source = """
from disnake.ext import commands


class Greeter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


bot = commands.InteractionBot()
bot.add_cog(Greeter(bot))
bot.run("token")
"""
    assert not any("nothing loads" in problem for problem in problems(source))


def test_loading_the_extension_is_accepted():
    source = """
from disnake.ext import commands


class Greeter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Greeter(bot))


bot = commands.InteractionBot()
bot.load_extension(__name__)
bot.run("token")
"""
    assert not any("nothing loads" in problem for problem in problems(source))


# ------------------------------------------------------------- Client vs Bot
def test_a_bare_client_cannot_hold_cogs():
    source = """
import disnake
from disnake.ext import commands


class Greeter(commands.Cog):
    pass


bot = disnake.Client(intents=disnake.Intents.default())
bot.add_cog(Greeter())
"""
    assert any("cannot host commands" in problem for problem in problems(source))


def test_a_client_used_as_a_client_is_fine():
    source = """
import disnake

client = disnake.Client(intents=disnake.Intents.default())


@client.event
async def on_ready():
    print("ready")
"""
    assert not any("cannot host commands" in problem for problem in problems(source))


# --------------------------------------------------------- blocking the loop
def test_a_blocking_sleep_inside_async_is_caught():
    source = """
import time


async def handler():
    time.sleep(5)
"""
    assert any("blocks the event loop" in problem for problem in problems(source))


def test_requests_inside_async_is_caught():
    source = """
import requests


async def fetch():
    return requests.get("https://example.invalid").text
"""
    assert any("blocks the event loop" in problem for problem in problems(source))


def test_the_async_version_is_accepted():
    source = """
import asyncio


async def handler():
    await asyncio.sleep(5)
"""
    assert not any("blocks the event loop" in problem for problem in problems(source))


def test_blocking_calls_in_ordinary_functions_are_left_alone():
    source = """
import time


def handler():
    time.sleep(5)
"""
    assert problems(source) == []


# ------------------------------------------------------------ echoing text
def test_echoing_user_text_without_allowed_mentions_is_a_suspicion():
    source = """
import disnake
from disnake.ext import commands

intents = disnake.Intents.default()
intents.message_content = True
bot = commands.InteractionBot(intents=intents)
seen = []


@bot.event
async def on_message(message):
    seen.append(message.content)


@bot.slash_command()
async def echo(inter):
    await inter.response.send_message(seen[-1])
"""
    assert any("ping @everyone" in note for note in suspicions(source))
    # A suspicion, not a fact: it never fails the check.
    assert not any("ping @everyone" in problem for problem in problems(source))


def test_blocking_mentions_is_accepted():
    source = """
import disnake
from disnake.ext import commands

intents = disnake.Intents.default()
intents.message_content = True
bot = commands.InteractionBot(intents=intents)
seen = []


@bot.event
async def on_message(message):
    seen.append(message.content)


@bot.slash_command()
async def echo(inter):
    await inter.response.send_message(seen[-1], allowed_mentions=disnake.AllowedMentions.none())
"""
    assert not any("ping @everyone" in note for note in suspicions(source))


# ------------------------------------------------------------------ no library
def test_code_that_uses_none_of_this_is_untouched():
    source = """
def add(left, right):
    return left + right
"""
    assert check_code(source).findings == []


# ------------------------------------------------------ install instructions
def test_an_import_the_install_command_misses_is_caught():
    from app.services.quality.api_check import check_answer

    answer = """
Install it with:

```sh
pip install disnake
```

Then:

```python
import disnake
from dotenv import load_dotenv

load_dotenv()
```
"""
    messages = [finding.message for finding in check_answer(answer).certain]
    assert any("python-dotenv" in message for message in messages)


def test_a_complete_install_command_is_accepted():
    from app.services.quality.api_check import check_answer

    answer = """
```sh
pip install disnake python-dotenv
```

```python
import disnake
from dotenv import load_dotenv
```
"""
    assert not any("install" in finding.message for finding in check_answer(answer).certain)


def test_an_answer_with_no_install_command_is_not_second_guessed():
    """The reader may already have the dependencies. Say nothing."""

    from app.services.quality.api_check import check_answer

    answer = """
```python
import disnake
from dotenv import load_dotenv
```
"""
    assert not any("install" in finding.message for finding in check_answer(answer).certain)


def test_standard_library_imports_never_need_installing():
    from app.services.quality.api_check import check_answer

    answer = """
```sh
pip install requests
```

```python
import json
import os
import requests
```
"""
    assert not any("install" in finding.message for finding in check_answer(answer).certain)


def test_a_version_pin_still_counts_as_installed():
    from app.services.quality.api_check import check_answer

    answer = """
```sh
pip install "disnake>=2.10,<3"
```

```python
import disnake
```
"""
    assert not any("install" in finding.message for finding in check_answer(answer).certain)


# ---------------------------------------------------------- on_message hygiene
def test_a_listener_that_never_skips_bots_is_a_suspicion():
    source = """
import disnake
from disnake.ext import commands

intents = disnake.Intents.default()
intents.message_content = True
bot = commands.InteractionBot(intents=intents)
seen = []


@bot.event
async def on_message(message):
    seen.append(message.content)
"""
    assert any("author.bot" in note for note in suspicions(source))


def test_skipping_bots_is_accepted():
    source = """
import disnake
from disnake.ext import commands

intents = disnake.Intents.default()
intents.message_content = True
bot = commands.InteractionBot(intents=intents)
seen = []


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    seen.append(message.content)
"""
    assert not any("author.bot" in note for note in suspicions(source))
