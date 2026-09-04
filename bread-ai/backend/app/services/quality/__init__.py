"""Quality scoring for the English and code that goes into training."""

from .english import ProseScore, clean_docstring, looks_like_prose, score_prose

__all__ = ["ProseScore", "clean_docstring", "looks_like_prose", "score_prose"]
