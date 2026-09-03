"""Deterministic backend used for tests and for trying the UI with no weights.

It never loads a model and never touches the network. Responses are obviously
synthetic on purpose: the point is to exercise streaming, citations, stop and
persistence, not to pretend to be a language model.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from datetime import datetime, timezone

from .base import BackendStatus, ChatTurn, GenerationParams, InferenceBackend, StopSignal

LANGUAGE_HINTS = {
    "python": "python",
    "java": "java",
    "javascript": "javascript",
    "typescript": "typescript",
    "react": "tsx",
    "rust": "rust",
    "golang": "go",
    " go ": "go",
    "c++": "cpp",
    "c#": "csharp",
    "kotlin": "kotlin",
    "php": "php",
    "ruby": "ruby",
    "sql": "sql",
    "bash": "bash",
    "shell": "bash",
    "html": "html",
    "css": "css",
    "yaml": "yaml",
    "luau": "lua",
    "lua": "lua",
    "roblox": "lua",
    "paper": "java",
    "fabric": "java",
    "minecraft": "java",
    "dockerfile": "dockerfile",
    "docker": "dockerfile",
}

SNIPPETS = {
    "python": 'def summarize_lines(path: str) -> dict[str, int]:\n'
    '    """Count lines, words and characters in a text file."""\n'
    "    counts = {\"lines\": 0, \"words\": 0, \"characters\": 0}\n"
    "    with open(path, \"r\", encoding=\"utf-8\") as handle:\n"
    "        for line in handle:\n"
    "            counts[\"lines\"] += 1\n"
    "            counts[\"words\"] += len(line.split())\n"
    "            counts[\"characters\"] += len(line)\n"
    "    return counts\n",
    "java": "public final class GreetCommand implements CommandExecutor {\n"
    "    @Override\n"
    "    public boolean onCommand(CommandSender sender, Command command,\n"
    "                             String label, String[] args) {\n"
    "        if (!(sender instanceof Player player)) {\n"
    "            sender.sendMessage(\"Only players can run this command.\");\n"
    "            return true;\n"
    "        }\n"
    "        player.sendMessage(Component.text(\"Hello from Bread.\"));\n"
    "        return true;\n"
    "    }\n"
    "}\n",
    "typescript": "export interface RetryOptions {\n"
    "  attempts: number;\n"
    "  baseDelayMs: number;\n"
    "}\n\n"
    "export async function withRetry<T>(\n"
    "  operation: () => Promise<T>,\n"
    "  options: RetryOptions,\n"
    "): Promise<T> {\n"
    "  let lastError: unknown;\n"
    "  for (let attempt = 0; attempt < options.attempts; attempt += 1) {\n"
    "    try {\n"
    "      return await operation();\n"
    "    } catch (error) {\n"
    "      lastError = error;\n"
    "      await new Promise((resolve) =>\n"
    "        setTimeout(resolve, options.baseDelayMs * 2 ** attempt),\n"
    "      );\n"
    "    }\n"
    "  }\n"
    "  throw lastError;\n"
    "}\n",
    "lua": "local AntiSpeed = {}\n\n"
    "function AntiSpeed.check(player, deltaSeconds, maxStudsPerSecond)\n"
    "    local character = player.Character\n"
    "    if not character or not character.PrimaryPart then\n"
    "        return true\n"
    "    end\n"
    "    local velocity = character.PrimaryPart.AssemblyLinearVelocity\n"
    "    return velocity.Magnitude <= maxStudsPerSecond * deltaSeconds\n"
    "end\n\n"
    "return AntiSpeed\n",
}

DEFAULT_SNIPPET = SNIPPETS["python"]


class MockBackend(InferenceBackend):
    name = "mock"

    def __init__(self, delay_seconds: float = 0.01, **options: object) -> None:
        super().__init__(**options)
        self.delay_seconds = delay_seconds
        self._loaded = False

    def load(self) -> None:
        self._loaded = True
        self.loaded_at = datetime.now(timezone.utc)
        self.load_seconds = 0.0

    def unload(self) -> None:
        self._loaded = False
        self.loaded_at = None

    def status(self) -> BackendStatus:
        return BackendStatus(
            loaded=self._loaded,
            backend=self.name,
            model_id="bread/mock",
            tokenizer_id="bread/mock",
            quantization_mode="none",
            dtype="n/a",
            device="cpu",
            context_length=8192,
            loaded_at=self.loaded_at,
            load_seconds=self.load_seconds,
            detail="Canned responses. No weights are loaded and nothing is downloaded.",
        )

    def stream(
        self,
        turns: list[ChatTurn],
        params: GenerationParams,
        stop_signal: StopSignal | None = None,
    ) -> Iterator[str]:
        if not self._loaded:
            self.load()
        reply = self._compose(turns)
        for token in _tokenize_for_stream(reply):
            if stop_signal is not None and stop_signal.stopped:
                return
            yield token
            if self.delay_seconds:
                time.sleep(self.delay_seconds)

    def _compose(self, turns: list[ChatTurn]) -> str:
        last_user = next(
            (turn.content for turn in reversed(turns) if turn.role == "user"), ""
        )
        language = _guess_language(last_user)
        snippet = SNIPPETS.get(language, DEFAULT_SNIPPET)
        topic = _first_sentence(last_user) or "your request"
        return (
            f"**Mock backend.** Bread is running without a real model, so this answer "
            f"is a fixed template rather than a generated one.\n\n"
            f"Reading your request as: _{topic}_\n\n"
            "Assumptions I would state to a real model run:\n\n"
            "1. The project already builds and its tests pass before the change.\n"
            "2. You want readable code over the shortest possible code.\n"
            "3. Anything I cannot verify is called out instead of guessed.\n\n"
            f"```{language}\n{snippet}```\n\n"
            "Set `MODEL_BACKEND=transformers` (or `llama_cpp`) in `.env` and load a "
            "model from the Models page to get a real answer."
        )


def _guess_language(text: str) -> str:
    lowered = f" {text.lower()} "
    for needle, language in LANGUAGE_HINTS.items():
        if needle in lowered:
            return language
    return "python"


def _first_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    match = re.split(r"(?<=[.?!])\s", cleaned, maxsplit=1)[0]
    return match[:180]


def _tokenize_for_stream(text: str) -> list[str]:
    """Split into word-ish pieces so the UI sees a realistic token cadence."""

    return re.findall(r"\s+|\S+", text)
