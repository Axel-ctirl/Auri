from __future__ import annotations

from typing import Iterable

import disnake
from disnake import ui

from bread.config import BREAD_COLOR, BREAD_EMOJI, ERROR_COLOR, SUCCESS_COLOR


def bread_container(
    title: str,
    *body: str,
    color: disnake.Colour = BREAD_COLOR,
    extra: Iterable[ui.WrappedComponent] = (),
) -> ui.Container:
    """Build a single branded Components V2 container.

    Each string in ``body`` becomes its own ``TextDisplay`` block. Callers are expected to
    have already embedded markdown (blockquotes, code blocks, bold, ``<t:...>`` timestamps)
    into those strings, since bread renders everything through this one helper.
    """
    children: list = [ui.TextDisplay(f"### {BREAD_EMOJI} {title}")]
    if body:
        children.append(ui.Separator())
        for block in body:
            children.append(ui.TextDisplay(block))
    children.extend(extra)
    return ui.Container(*children, accent_colour=color)


def section_with_thumbnail(text: str, image_url: str) -> ui.Section:
    return ui.Section(text, accessory=ui.Thumbnail(image_url))


def success(title: str, *body: str, extra: Iterable[ui.WrappedComponent] = ()) -> ui.Container:
    return bread_container(f"✅ {title}", *body, color=SUCCESS_COLOR, extra=extra)


def error(title: str, *body: str, extra: Iterable[ui.WrappedComponent] = ()) -> ui.Container:
    return bread_container(f"❌ {title}", *body, color=ERROR_COLOR, extra=extra)


def info(title: str, *body: str, extra: Iterable[ui.WrappedComponent] = ()) -> ui.Container:
    return bread_container(title, *body, extra=extra)


def quote(text: str) -> str:
    """Render text as a Discord blockquote, prefixing every line with ``> ``."""
    lines = text.splitlines() or [""]
    return "\n".join(f"> {line}" if line else ">" for line in lines)


def code_block(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text}\n```"


def relative_time(unix_ts: int) -> str:
    return f"<t:{unix_ts}:R>"


def full_time(unix_ts: int) -> str:
    return f"<t:{unix_ts}:F>"


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)
