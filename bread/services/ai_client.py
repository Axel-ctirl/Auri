from __future__ import annotations

from openai import APIError, APITimeoutError, AsyncOpenAI

from bread.config import OPENROUTER_API_KEY, OPENROUTER_MODEL

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

BREAD_PERSONA = (
    "You are bread, a witty, friendly Discord bot mascot shaped like a loaf of bread. "
    "Keep replies short (1-4 sentences unless asked for more), playful, and safe for a "
    "general Discord server. Use Discord markdown (bold, inline code) sparingly for emphasis. "
    "Never break character by mentioning you are an AI model."
)


class AIError(RuntimeError):
    """Raised when the OpenRouter/Kimi call fails or is unavailable."""


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if not OPENROUTER_API_KEY:
        raise AIError("No `OPENROUTER_API_KEY` is configured for this bot.")
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
    return _client


async def ask(prompt: str, system: str | None = None, *, max_tokens: int = 500) -> str:
    """Send ``prompt`` to the configured OpenRouter Kimi model and return the reply text."""
    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": system or BREAD_PERSONA},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            timeout=30,
        )
    except APITimeoutError as exc:
        raise AIError("The AI took too long to respond. Try again in a moment.") from exc
    except APIError as exc:
        raise AIError(f"The AI request failed: {exc.message or exc}") from exc

    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise AIError("The AI returned an empty response.")
    return content
