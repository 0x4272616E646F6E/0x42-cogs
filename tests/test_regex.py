"""Admin-supplied regexes must not be able to wedge the bot.

None of these tests execute a catastrophic pattern — that is the whole point.
`re` holds the GIL while matching, so running one here would hang the test run
exactly as it would hang the bot.
"""

import re

from aiagent.config.defaults import DEFAULT_REMOVE_PATTERNS
from aiagent.utils import regex

# The shapes that actually blow up exponentially.
DANGEROUS = [
    r"(a+)+$",
    r"(a*)*$",
    r"([a-z]+)*$",
    r"(\w+\s*)+$",
    r"(\d+)+$",
    r"(a+){2,}$",
]

# Patterns an admin might plausibly want, none of which nest unbounded repeats.
SAFE = [
    r"^\[?spoiler\]?",
    r"<think>[\s\S]*?</think>",
    r"^(User )?\"?Red\"? (said|says|replied):?",
    r"\n*\[Image[^\]]+\]",
    r"(a|b)+",
    r"(a{1,20})+",
    r"https?://\S+",
]


def test_dangerous_patterns_are_rejected():
    for pattern in DANGEROUS:
        error = regex.validate_pattern(pattern)
        assert error is not None, f"should have been rejected: {pattern}"
        assert "exponential" in error or "unbounded" in error


def test_safe_patterns_are_accepted():
    for pattern in SAFE:
        assert regex.validate_pattern(pattern) is None, f"false positive: {pattern}"


def test_every_shipped_removelist_pattern_passes_validation():
    """The defaults must not trip the check we impose on users."""
    for pattern in DEFAULT_REMOVE_PATTERNS:
        concrete = pattern.replace("{botname}", "Red").replace("{authorname}", "brandon")
        assert regex.validate_pattern(concrete) is None, f"default rejected: {pattern}"


def test_invalid_syntax_is_rejected():
    error = regex.validate_pattern(r"(unclosed")
    assert error is not None and "valid regex" in error


def test_escaped_quantifiers_are_not_mistaken_for_nesting():
    assert regex.validate_pattern(r"(a\+)+") is None


def test_quantifiers_inside_character_classes_are_not_nesting():
    assert regex.validate_pattern(r"([+*])+") is None


def test_search_matches_and_misses():
    assert regex.search(re.compile("spoiler"), "big spoiler ahead") is True
    assert regex.search(re.compile("spoiler"), "nothing here") is False
    assert regex.search(re.compile("."), "") is False


def test_search_input_is_capped():
    huge = "b" * (regex.MAX_INPUT_LENGTH * 2) + "needle"
    # the needle sits beyond the cap, so it must not be found
    assert regex.search(re.compile("needle"), huge) is False


def test_sub_strips_matches():
    assert regex.sub(r"<think>.*?</think>", "<think>hmm</think>hello") == "hello"


def test_sub_output_is_capped():
    huge = "z" * (regex.MAX_INPUT_LENGTH * 2)
    assert len(regex.sub(r"q", huge)) == regex.MAX_INPUT_LENGTH


def test_sub_leaves_text_alone_on_invalid_pattern():
    assert regex.sub(r"(unclosed", "hello") == "hello"
