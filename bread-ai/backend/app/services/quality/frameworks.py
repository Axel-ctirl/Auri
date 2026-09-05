"""Library-specific mistakes that a generic name check cannot see.

`api_check` proves that every name and signature resolves. Code can pass that
and still not work, because the mistake is in how a library is wired together
rather than in what it is called. A Discord bot that reads `message.content`
without the message content intent resolves perfectly and receives empty
strings. A cog that is defined and never loaded resolves perfectly and never
runs.

These are the errors a small model actually makes. They come from a handful of
libraries, they repeat, and each one is decidable from the syntax tree alone, so
they belong in a rule rather than in a hope that the model knows better.

Every rule states its evidence in the message, and every rule is narrow enough
to be wrong loudly rather than quietly: a rule that fires on working code gets
switched off and stops helping.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass

from .api_check import Finding

# The discord.py fork family. They share an ancestor, so they share the traps.
DISCORD_LIBRARIES = ("disnake", "discord", "nextcord")

# Calls that put a cog into a bot. Any one of them means the cog is wired up.
COG_REGISTRARS = ("add_cog", "load_extension", "load_extensions", "setup_hook")

# Blocking work that stalls the whole event loop when awaited code calls it.
BLOCKING_CALLS = {
    "time.sleep": "await asyncio.sleep() instead",
    "requests.get": "use aiohttp, or run it in an executor",
    "requests.post": "use aiohttp, or run it in an executor",
    "requests.put": "use aiohttp, or run it in an executor",
    "requests.delete": "use aiohttp, or run it in an executor",
    "subprocess.run": "use asyncio.create_subprocess_exec()",
    "subprocess.call": "use asyncio.create_subprocess_exec()",
}


@dataclass
class _Facts:
    """What one module's syntax tree says, gathered in a single pass."""

    imported: set[str]
    attribute_names: set[str]
    called_methods: set[str]
    assigned_attributes: set[str]
    class_bases: list[tuple[str, str, int]]  # class name, base as written, line
    function_names: set[str]
    constructor_calls: list[tuple[str, int]]  # dotted call as written, line
    keywords_used: set[str]
    identifiers: set[str]


def _dotted(node: ast.AST) -> str:
    """Render `a.b.c` from an attribute chain, or "" for anything else."""

    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return ""
    parts.append(current.id)
    return ".".join(reversed(parts))


def _gather(tree: ast.AST) -> _Facts:
    facts = _Facts(
        imported=set(),
        attribute_names=set(),
        called_methods=set(),
        assigned_attributes=set(),
        class_bases=[],
        function_names=set(),
        constructor_calls=[],
        keywords_used=set(),
        identifiers=set(),
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                facts.imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                facts.imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Attribute):
            facts.attribute_names.add(node.attr)
            if isinstance(node.ctx, ast.Store):
                facts.assigned_attributes.add(node.attr)
        elif isinstance(node, ast.Name):
            facts.identifiers.add(node.id)
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                facts.class_bases.append(
                    (node.name, _dotted(base) or getattr(base, "id", ""), node.lineno)
                )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            facts.function_names.add(node.name)
        elif isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            if dotted:
                facts.constructor_calls.append((dotted, node.lineno))
                facts.called_methods.add(dotted.rsplit(".", 1)[-1])
            for keyword in node.keywords:
                if keyword.arg:
                    facts.keywords_used.add(keyword.arg)

    return facts


def _registrar_sites(tree: ast.AST) -> list[tuple[str, str, int]]:
    """Every cog-registering call, with the function it sits in.

    Where the call sits matters. `bot.add_cog(...)` inside `setup(bot)` only runs
    when something loads this file as an extension, so in an answer that builds
    its own bot and never loads anything, that call is dead code.
    """

    enclosing: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    enclosing.setdefault(id(inner), node.name)

    sites: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        method = _dotted(node.func).rsplit(".", 1)[-1]
        if method in COG_REGISTRARS:
            sites.append((method, enclosing.get(id(node), ""), node.lineno))
    return sites


def _uses_discord(facts: _Facts) -> bool:
    return any(library in facts.imported for library in DISCORD_LIBRARIES)


def _message_content_intent(tree: ast.AST, facts: _Facts) -> Iterator[Finding]:
    """`.content` is empty unless the privileged intent is turned on."""

    if not _uses_discord(facts) or "content" not in facts.attribute_names:
        return
    intents_calls = [
        (dotted, line)
        for dotted, line in facts.constructor_calls
        if dotted.endswith("Intents.default") or dotted.endswith("Intents")
    ]
    if not intents_calls:
        # Intents built elsewhere, or passed in. Not decidable from here.
        return
    if any(dotted.endswith("Intents.all") for dotted, _line in facts.constructor_calls):
        return
    if "message_content" in facts.assigned_attributes or "message_content" in facts.keywords_used:
        return
    yield Finding(
        kind="framework",
        symbol="Intents.message_content",
        line=intents_calls[0][1],
        message=(
            "this reads `message.content` but never enables the message content intent, "
            "so the content arrives empty: set `intents.message_content = True` and turn "
            "the intent on in the developer portal"
        ),
    )


def _cog_never_loaded(tree: ast.AST, facts: _Facts) -> Iterator[Finding]:
    """A cog that is never registered is code that never runs."""

    if not _uses_discord(facts):
        return
    cogs = [(name, line) for name, base, line in facts.class_bases if base.split(".")[-1] == "Cog"]
    if not cogs:
        return
    builds_a_bot = any(
        dotted.split(".")[-1] in ("Bot", "InteractionBot", "AutoShardedBot", "Client")
        for dotted, _line in facts.constructor_calls
    )
    # A `setup(bot)` function on its own means this is an extension file, and
    # whatever loads it does the registering. An answer that also builds the bot
    # is meant to be the whole program, and then nothing loads the extension.
    if "setup" in facts.function_names and not builds_a_bot:
        return

    for registrar, enclosing_function, _line in _registrar_sites(tree):
        if registrar in ("load_extension", "load_extensions"):
            return
        if enclosing_function != "setup":
            return

    name, line = cogs[0]
    remedy = (
        "nothing calls `load_extension` on it, so add the cog directly with `bot.add_cog(...)`"
        if "setup" in facts.function_names
        else "add `bot.add_cog(...)`, or define `setup(bot)` and load this file as an extension"
    )
    yield Finding(
        kind="framework",
        symbol=name,
        line=line,
        message=(
            f"`{name}` is a cog that nothing loads, so none of its commands or listeners "
            f"will run: {remedy}"
        ),
    )


def _client_cannot_host_commands(tree: ast.AST, facts: _Facts) -> Iterator[Finding]:
    """`Client` is the bare gateway connection. Commands need a `Bot`."""

    if not _uses_discord(facts):
        return
    client_calls = [
        (dotted, line)
        for dotted, line in facts.constructor_calls
        if dotted.split(".")[-1] == "Client" and "Bot" not in dotted
    ]
    if not client_calls:
        return
    wants_commands = "add_cog" in facts.called_methods or any(
        name in facts.attribute_names for name in ("slash_command", "command", "tree")
    )
    if not wants_commands:
        return
    dotted, line = client_calls[0]
    yield Finding(
        kind="framework",
        symbol=dotted,
        line=line,
        message=(
            f"`{dotted}()` cannot host commands or cogs: use `commands.Bot` "
            "(or `commands.InteractionBot` for slash commands only)"
        ),
    )


def _blocking_call_in_async(tree: ast.AST, facts: _Facts) -> Iterator[Finding]:
    """One blocking call freezes every other request the process is serving."""

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            dotted = _dotted(inner.func)
            remedy = BLOCKING_CALLS.get(dotted)
            if remedy is None:
                continue
            yield Finding(
                kind="framework",
                symbol=dotted,
                line=inner.lineno,
                message=(
                    f"`{dotted}()` blocks the event loop inside `async def {node.name}`, "
                    f"stalling everything else the process is doing: {remedy}"
                ),
            )


def _echoes_without_allowed_mentions(tree: ast.AST, facts: _Facts) -> Iterator[Finding]:
    """Repeating user text verbatim is how a bot gets made to ping @everyone."""

    if not _uses_discord(facts) or "content" not in facts.attribute_names:
        return
    if "allowed_mentions" in facts.keywords_used:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        method = _dotted(node.func).rsplit(".", 1)[-1]
        if method not in ("send", "send_message"):
            continue
        if not node.args or isinstance(node.args[0], ast.Constant):
            continue
        yield Finding(
            kind="framework",
            symbol=method,
            line=node.lineno,
            confidence="likely",
            message=(
                "this repeats message text back to a channel without "
                "`allowed_mentions=AllowedMentions.none()`, which lets anyone make the bot "
                "ping @everyone by saying it once"
            ),
        )
        return


def _on_message_without_a_bot_check(tree: ast.AST, facts: _Facts) -> Iterator[Finding]:
    """A listener that does not skip bots eventually reacts to itself."""

    if not _uses_discord(facts):
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "on_message":
            continue
        checks_author = any(
            isinstance(inner, ast.Attribute) and inner.attr == "bot" for inner in ast.walk(node)
        )
        if checks_author:
            continue
        yield Finding(
            kind="framework",
            symbol="on_message",
            line=node.lineno,
            confidence="likely",
            message=(
                "`on_message` never checks `message.author.bot`, so the bot reacts to its "
                "own messages and to other bots: return early when the author is a bot"
            ),
        )
        return


RULES = (
    _message_content_intent,
    _on_message_without_a_bot_check,
    _cog_never_loaded,
    _client_cannot_host_commands,
    _blocking_call_in_async,
    _echoes_without_allowed_mentions,
)


def check_frameworks(tree: ast.AST) -> list[Finding]:
    """Every framework rule that fires on this tree."""

    facts = _gather(tree)
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(tree, facts))
    return findings
