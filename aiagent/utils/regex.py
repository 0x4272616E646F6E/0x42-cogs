r"""Keeping admin-supplied regexes from wedging the bot.

Two patterns in this cog come from users: `[p]aiagent trigger ignore` runs against
every message the bot considers, and `[p]aiagent response removelist` runs against
every generated reply. A pattern such as `(a+)+$` backtracks exponentially, so a
careless one can hang the bot.

The obvious defence — evaluate on a worker thread with `asyncio.wait_for` — does
not work, and the cog used to rely on it. CPython's `re` does not release the GIL
while matching, so a runaway match starves every other thread including the event
loop. Measured: a main thread managed 0 iterations of a `time.sleep(0.005)` loop
in 8 seconds while one daemon thread chewed on `(a+)+$`. The timeout fires, the
await returns, and the bot is still frozen. `re` also offers no timeout of its own.

So the gate has to be *before* the pattern is ever stored:

1. `validate_pattern` rejects invalid syntax, and rejects the exponential shape —
   an unboundedly repeated group that itself contains an unbounded quantifier,
   which is what `(a+)+`, `([a-z]+)*` and `(\w+\s*)+` all are.
2. `MAX_INPUT_LENGTH` caps what any pattern is ever run against, which bounds
   polynomial blowups too.

Known limit, stated rather than papered over: this rejects the common exponential
shape, not every possible slow pattern. `(a|a)+$` is exponential and reads as
harmless to this check. Patterns are admin-level settings, and an admin can
already disrupt a server in louder ways; the aim is to stop an accident, not a
determined attacker.
"""

import logging
import re
from typing import Iterator, Optional

logger = logging.getLogger("red.0x42_cogs.aiagent")

# Nothing is ever matched against more than this many characters.
MAX_INPUT_LENGTH = 8000

UNBOUNDED_QUANTIFIERS = ("+", "*")


def _scan(pattern: str) -> Iterator[tuple]:
    """Walk a pattern yielding (index, char), skipping escapes and character classes."""
    index, length, in_class = 0, len(pattern), False

    while index < length:
        char = pattern[index]

        if char == "\\":
            index += 2
            continue
        if in_class:
            if char == "]":
                in_class = False
            index += 1
            continue
        if char == "[":
            in_class = True
            index += 1
            continue

        yield index, char
        index += 1


def _has_unbounded_quantifier(pattern: str) -> bool:
    for index, char in _scan(pattern):
        if char in UNBOUNDED_QUANTIFIERS:
            return True
        if char == "{":
            close = pattern.find("}", index)
            if close != -1 and pattern[index + 1:close].endswith(","):
                return True
    return False


def _repeated_group_bodies(pattern: str) -> Iterator[str]:
    """Yield the body of every group that is repeated an unbounded number of times."""
    starts = []

    for index, char in _scan(pattern):
        if char == "(":
            starts.append(index)
        elif char == ")" and starts:
            start = starts.pop()
            following = pattern[index + 1:index + 2]

            if following in UNBOUNDED_QUANTIFIERS:
                yield pattern[start + 1:index]
            elif following == "{":
                close = pattern.find("}", index)
                if close != -1 and pattern[index + 2:close].endswith(","):
                    yield pattern[start + 1:index]


def validate_pattern(pattern: str) -> Optional[str]:
    """Return an error message if `pattern` is unusable or dangerous, else None."""
    try:
        re.compile(pattern)
    except re.error as error:
        return f"That isn't a valid regex pattern: {error}"

    for body in _repeated_group_bodies(pattern):
        if _has_unbounded_quantifier(body):
            return (
                "That pattern nests one unbounded repeat inside another, like `(a+)+`. "
                "Those can take exponential time and would hang the bot, so it can't be "
                "saved. Rewrite it with a bounded repeat, e.g. `(a{1,20})+`."
            )

    return None


def search(compiled: re.Pattern, text: str) -> bool:
    """True if `compiled` matches, evaluated against a capped slice of `text`."""
    if not text:
        return False
    return bool(compiled.search(text[:MAX_INPUT_LENGTH]))


def sub(pattern: str, text: str) -> str:
    """Strip everything matching `pattern` from `text`; leave it be if it won't compile."""
    capped = text[:MAX_INPUT_LENGTH]
    try:
        return re.compile(pattern).sub("", capped).strip(" \n")
    except re.error:
        logger.warning(f"Skipped an invalid regex pattern: {pattern!r}")
        return capped
