"""Dependency-free token estimation.

The cog only needs to know roughly how much channel history fits in a model's
context window. It cannot know exactly: every local model ships its own
tokenizer, and no OpenAI-compatible endpoint exposes one.

Using `tiktoken` for this was worse than useless here — it downloads a 1.7MB
vocabulary from the internet on first use, on the event loop, which is a strange
thing for a cog built around a local LLM to do, and it still only produced an
estimate for a tokenizer the model isn't using.

The coefficients below were calibrated against `cl100k_base` over representative
Discord content (prose, code blocks, URLs, JSON, custom emoji, CJK). They are
deliberately biased to **over**-estimate: across that sample the estimate ranged
from 1.03x to 2.57x the real count and never came in under. Over-estimating
costs a little history; under-estimating overflows the model's context and the
request fails outright.
"""

import math

# Calibrated worst case for dense ASCII (JSON, minified code) is ~2.2 chars per
# token; prose is nearer 5.5, so this runs conservative for ordinary chat.
ASCII_CHARS_PER_TOKEN = 2.2

# Non-ASCII (CJK, emoji) costs roughly one to three tokens per character.
TOKENS_PER_WIDE_CHAR = 2


def estimate_tokens(text: str) -> int:
    """Conservative upper estimate of how many tokens `text` will occupy."""
    if not text:
        return 0

    ascii_chars = sum(1 for character in text if ord(character) < 128)
    wide_chars = len(text) - ascii_chars

    return math.ceil(ascii_chars / ASCII_CHARS_PER_TOKEN) + TOKENS_PER_WIDE_CHAR * wide_chars
