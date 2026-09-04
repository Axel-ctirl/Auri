"""Scoring the quality of English prose destined for a training set.

The model's writing voice is learned from the assistant side of its training
data, one sentence at a time. Feeding it hedging, filler and passive
constructions teaches exactly those. This module is the filter that keeps them
out, and it is deliberately opinionated about what good technical English is.

It is a heuristic, not a judge. It catches the obvious problems reliably and
says nothing useful about whether a well-formed paragraph is *correct*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Phrases that add length without adding meaning. Each one the model learns is a
# phrase it will emit at you later.
FILLER_PHRASES = (
    "basically",
    "essentially",
    "simply put",
    "as we all know",
    "needless to say",
    "it is important to note that",
    "it should be noted that",
    "in order to",
    "at the end of the day",
    "when it comes to",
    "the fact that",
    "in terms of",
    "very unique",
    "quite unique",
    "really just",
    "kind of a",
    "sort of a",
    "obviously",
    "clearly just",
    "of course, this",
    "as you can see",
)

# Openers that delay the answer. Technical writing should lead with it.
WEAK_OPENERS = (
    "so ",
    "well, ",
    "basically, ",
    "in this ",
    "this is a ",
    "there is a ",
    "there are a ",
    "it is a ",
    "let's ",
    "let us ",
    "first of all",
)

# Marker syntax that means a docstring is reference material, not prose.
MARKUP_MARKERS = (
    ":param",
    ":return",
    ":rtype",
    ":raises",
    ":type",
    "@param",
    "@return",
    "@throws",
    "@author",
    "Parameters\n",
    "Returns\n",
    "-----",
    "=====",
    ">>>",
    "...",
    "Args:",
    "Returns:",
    "Raises:",
    "Examples:",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
# "was created", "is being handled", "has been removed": be + past participle.
_PASSIVE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has been|have been|had been)\s+"
    r"(?:\w+ly\s+)?\w+(?:ed|en)\b",
    re.IGNORECASE,
)

MIN_WORDS = 8
MAX_MEAN_SENTENCE_WORDS = 34
MAX_FILLER_PER_HUNDRED_WORDS = 1.5
MAX_PASSIVE_RATIO = 0.4


@dataclass
class ProseScore:
    """A 0-to-1 quality score with the reasons behind it."""

    score: float
    words: int
    sentences: int
    mean_sentence_words: float
    filler_hits: list[str] = field(default_factory=list)
    passive_ratio: float = 0.0
    problems: list[str] = field(default_factory=list)

    @property
    def is_good(self) -> bool:
        return self.score >= 0.6 and not self.problems

    def as_dict(self) -> dict[str, object]:
        return {
            "score": round(self.score, 3),
            "words": self.words,
            "sentences": self.sentences,
            "mean_sentence_words": round(self.mean_sentence_words, 1),
            "filler_hits": self.filler_hits,
            "passive_ratio": round(self.passive_ratio, 3),
            "problems": self.problems,
        }


def score_prose(text: str) -> ProseScore:
    """Score a passage of technical English between 0 and 1."""

    stripped = (text or "").strip()
    words = _WORD.findall(stripped)
    word_count = len(words)

    sentences = [s for s in _SENTENCE_SPLIT.split(stripped) if s.strip()]
    sentence_count = max(len(sentences), 1)
    mean_length = word_count / sentence_count

    lowered = stripped.lower()
    filler_hits = [phrase for phrase in FILLER_PHRASES if phrase in lowered]
    passive_hits = len(_PASSIVE.findall(stripped))
    passive_ratio = passive_hits / sentence_count

    problems: list[str] = []
    if word_count < MIN_WORDS:
        problems.append(f"too short: {word_count} words")
    if mean_length > MAX_MEAN_SENTENCE_WORDS:
        problems.append(f"sentences average {mean_length:.0f} words")
    if word_count and (len(filler_hits) * 100 / word_count) > MAX_FILLER_PER_HUNDRED_WORDS:
        problems.append(f"filler: {', '.join(filler_hits[:3])}")
    if passive_ratio > MAX_PASSIVE_RATIO:
        problems.append(f"passive voice in {passive_ratio:.0%} of sentences")
    if any(lowered.startswith(opener) for opener in WEAK_OPENERS):
        problems.append("opens without leading with the answer")
    if not stripped.endswith((".", "!", "?", ":", "`", ")")):
        problems.append("ends mid-thought")

    # Start from one and subtract for each measurable fault, so the score is
    # explainable rather than an opaque number.
    score = 1.0
    score -= min(len(filler_hits) * 0.12, 0.36)
    score -= min(max(mean_length - 24, 0) * 0.02, 0.24)
    score -= min(max(passive_ratio - 0.2, 0) * 0.8, 0.24)
    if word_count < MIN_WORDS:
        score -= 0.5
    if sentence_count == 1 and word_count > 45:
        score -= 0.1  # one very long sentence is a paragraph in disguise

    return ProseScore(
        score=max(0.0, min(1.0, score)),
        words=word_count,
        sentences=len(sentences),
        mean_sentence_words=mean_length,
        filler_hits=filler_hits,
        passive_ratio=passive_ratio,
        problems=problems,
    )


def looks_like_prose(text: str) -> bool:
    """True when a passage reads as sentences rather than reference markup.

    A docstring that is mostly ``:param:`` lines is useful documentation and
    useless as an example of writing, so it must not train the voice.
    """

    stripped = (text or "").strip()
    if len(stripped) < 30:
        return False

    letters = sum(1 for character in stripped if character.isalpha())
    if letters / max(len(stripped), 1) < 0.55:
        return False

    marker_lines = sum(
        1
        for line in stripped.splitlines()
        if any(line.strip().startswith(marker.strip()) for marker in MARKUP_MARKERS)
    )
    if marker_lines > len(stripped.splitlines()) / 3:
        return False

    return bool(_SENTENCE_SPLIT.split(stripped)) and " " in stripped


def clean_docstring(raw: str) -> str:
    """Reduce a docstring to its prose, dropping reference sections.

    Everything from the first ``Args:``, ``Parameters``, ``:param`` or doctest
    marker onward is reference material. The paragraphs before it are the part
    written for a human to read.
    """

    if not raw:
        return ""

    text = raw.strip().strip('"').strip("'").strip()
    lines = [line.rstrip() for line in text.splitlines()]

    kept: list[str] = []
    for line in lines:
        candidate = line.strip()
        if any(candidate.startswith(marker.strip()) for marker in MARKUP_MARKERS):
            break
        if candidate in {"Args", "Arguments", "Parameters", "Returns", "Raises", "Yields"}:
            break
        kept.append(line)

    # Collapse the common leading indentation the source imposed.
    body = "\n".join(kept).strip()
    body = re.sub(r"\n[ \t]+", "\n", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()
