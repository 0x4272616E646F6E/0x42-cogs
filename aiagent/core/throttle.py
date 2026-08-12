"""Bounding how much work a mention can start, and how long it may wait.

`/chat` has carried a cooldown since the beginning, but mention-triggered
responses had none: any opted-in user in a whitelisted channel could mention the
bot in a loop and start a generation every time. Nothing queued, nothing was
refused, and the requests piled into the LLM server until they timed out — which
on self-hosted hardware means one person can saturate the GPU for everyone.

Three limits, because they stop different things:

* a per-user cooldown stops one person looping,
* a concurrency cap stops a crowd arriving at once — a local server generates one
  or two streams at a time, so handing it twenty requests does not make them
  finish sooner, it makes all twenty miss the timeout,
* a bounded per-channel queue lets a small collision resolve itself instead of
  telling the second person to try again.

The queue is bounded in two directions, and the second one is the important one.
Depth is capped so a backlog cannot grow without limit. More subtly, nobody waits
longer than the answer stays worth having: the wait budget is whatever is left of
`MAX_RESPONSE_DELAY` after the message's own age. A reply that arrives two minutes
into a conversation that has moved on is worse than no reply, so a request that
cannot start in time is dropped rather than answered late.

Deriving the wait from the message age means there is one deadline, not two knobs
that can disagree.
"""

import asyncio
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

# A user must wait this long between mention-triggered responses.
USER_COOLDOWN_SECONDS = 10

# Generations in flight at once, across the whole bot.
MAX_CONCURRENT_RESPONSES = 2

# Requests waiting for a slot, per channel.
MAX_QUEUE_DEPTH = 5

# How late a response may start before it is not worth sending at all.
MAX_RESPONSE_DELAY = 60

# Cooldown entries are tiny, but a busy bot would still accumulate them forever.
PRUNE_THRESHOLD = 1000


class SlotOutcome(Enum):
    """Why a request may or may not proceed."""

    GRANTED = "granted"
    QUEUE_FULL = "queue_full"
    TOO_SLOW = "too_slow"


def delay_budget(created_at: datetime, now: Optional[datetime] = None) -> float:
    """Seconds left to start answering `created_at` before it is stale."""
    now = now or datetime.now(timezone.utc)
    age = (now - created_at).total_seconds()
    return MAX_RESPONSE_DELAY - age


class ResponseThrottle:
    """Per-user cooldown, a bot-wide concurrency cap, and a bounded queue."""

    def __init__(
        self,
        cooldown: float = USER_COOLDOWN_SECONDS,
        max_concurrent: int = MAX_CONCURRENT_RESPONSES,
        max_queue_depth: int = MAX_QUEUE_DEPTH,
    ):
        self.cooldown = cooldown
        self.max_concurrent = max_concurrent
        self.max_queue_depth = max_queue_depth
        self._last_response: Dict[int, float] = {}
        self._waiting: Dict[int, int] = {}
        self._slots = asyncio.Semaphore(max_concurrent)

    # --- per-user cooldown ---------------------------------------------------

    def seconds_remaining(self, user_id: int, now: Optional[float] = None) -> float:
        """How long until this user may trigger another response. 0 when ready."""
        now = time.monotonic() if now is None else now
        last = self._last_response.get(user_id)
        if last is None:
            return 0.0
        return max(0.0, self.cooldown - (now - last))

    def record(self, user_id: int, now: Optional[float] = None) -> None:
        """Start this user's cooldown."""
        now = time.monotonic() if now is None else now
        if len(self._last_response) >= PRUNE_THRESHOLD:
            self._prune(now)
        self._last_response[user_id] = now

    def _prune(self, now: float) -> None:
        self._last_response = {
            user_id: at
            for user_id, at in self._last_response.items()
            if now - at < self.cooldown
        }

    # --- slots and the queue -------------------------------------------------

    @property
    def busy(self) -> bool:
        """True when every generation slot is taken, so a request would wait."""
        return self._slots.locked()

    @property
    def in_flight(self) -> int:
        return self.max_concurrent - self._slots._value

    def queue_depth(self, channel_id: int) -> int:
        return self._waiting.get(channel_id, 0)

    async def acquire_slot(
        self, channel_id: int = 0, wait_budget: float = MAX_RESPONSE_DELAY
    ) -> SlotOutcome:
        """Take a generation slot, waiting at most `wait_budget` seconds for one."""
        if wait_budget <= 0:
            return SlotOutcome.TOO_SLOW

        # Free slot: take it without touching the queue at all.
        if not self._slots.locked():
            await self._slots.acquire()
            return SlotOutcome.GRANTED

        if self.queue_depth(channel_id) >= self.max_queue_depth:
            return SlotOutcome.QUEUE_FULL

        self._waiting[channel_id] = self.queue_depth(channel_id) + 1
        try:
            # Python 3.11's Semaphore hands the value back if the acquire is
            # cancelled after being granted, so a timeout here cannot leak a slot.
            await asyncio.wait_for(self._slots.acquire(), wait_budget)
            return SlotOutcome.GRANTED
        except asyncio.TimeoutError:
            return SlotOutcome.TOO_SLOW
        finally:
            remaining = self.queue_depth(channel_id) - 1
            if remaining > 0:
                self._waiting[channel_id] = remaining
            else:
                self._waiting.pop(channel_id, None)

    def release_slot(self) -> None:
        self._slots.release()
