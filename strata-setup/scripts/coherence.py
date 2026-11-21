#!/usr/bin/env python3
"""Shared output-coherence checks for Strata benchmark/stress tooling.

Detects degenerate model output (gibberish, repeated tokens, empty answers)
so benchmarks can fail loudly instead of silently recording garbage throughput.
"""
from __future__ import annotations

import re

PUNCT_RUN = re.compile(r"([^\w\s])\1{3,}")


def is_degenerate(text: str | None, min_words: int = 5, unique_ratio: float = 0.3) -> bool:
    """Return True when text looks like degenerate model output."""
    if text is None:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    words = stripped.split()
    if len(words) >= min_words:
        if len(set(words)) / len(words) < unique_ratio:
            return True
    # Long runs of the same punctuation character ("!!!!", "!!!!!!") are gibberish.
    if PUNCT_RUN.search(stripped):
        return True
    # A single repeated character repeated many times.
    if len(stripped) >= 8 and len(set(stripped)) <= 2:
        return True
    return False


def response_text(message: dict | None) -> str:
    """Extract the best available text from an OpenAI-style message object."""
    if not isinstance(message, dict):
        return ""
    for key in ("content", "reasoning_content", "text"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def is_degenerate_response(message: dict | None) -> bool:
    """Check a full chat-completion message object for degenerate output."""
    return is_degenerate(response_text(message))
