"""Shrinks long questions down to fit the model's input limit, either by cutting them
off or summarizing them, depending on how far over the limit they are."""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


#counts tokens with tiktoken, falls back to a rough word count if tiktoken isnt available
def count_tokens(text: str) -> int:
    """Count tokens using tiktoken if available, otherwise rough word count."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())


def truncate_text(text: str, max_tokens: int = 3_000) -> tuple[str, str]:
    """Truncate text to max_tokens. Returns (truncated, method_label)."""
    tokens = count_tokens(text)
    if tokens <= max_tokens:
        return text, "original"

    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        encoded = enc.encode(text)
        truncated = enc.decode(encoded[:max_tokens])
        return truncated, "truncated"
    except Exception:
        words = text.split()
        truncated = " ".join(words[:max_tokens])
        return truncated, "truncated"


#keeps adding whole sentences one by one until adding another would go over the limit
def summarize_text(text: str, target_tokens: int = 3_000) -> tuple[str, str]:
    """Returns (summary, method_label)."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary_parts: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        if current_tokens + sentence_tokens > target_tokens and summary_parts:
            break
        summary_parts.append(sentence)
        current_tokens += sentence_tokens

    return " ".join(summary_parts), "summarized"


#picks how to shrink the input based on how far over the limit it is:
#under the limit, leave it alone. up to 2x over, just truncate. way over, summarize instead.
def restructure_input(text: str) -> tuple[str, str]:
    """Returns (restructured_text, method_label)."""
    tokens = count_tokens(text)
    max_input = settings.max_input_tokens
    reserved = settings.reserved_context_tokens
    effective_limit = max_input - reserved

    if tokens <= effective_limit:
        return text, "original"

    if tokens <= effective_limit * 2:
        return truncate_text(text, effective_limit)

    return summarize_text(text, effective_limit)