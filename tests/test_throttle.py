"""Limits on how much LLM work a burst of mentions can start, and how long it waits."""

import asyncio
from datetime import datetime, timedelta, timezone

from aiagent.core.throttle import (
    MAX_RESPONSE_DELAY,
    PRUNE_THRESHOLD,
    ResponseThrottle,
    SlotOutcome,
    delay_budget,
)

USER = 42
OTHER = 7
CHANNEL = 200
OTHER_CHANNEL = 201


# --- per-user cooldown ------------------------------------------------------

def test_a_first_response_is_allowed():
    throttle = ResponseThrottle(cooldown=10)
    assert throttle.seconds_remaining(USER, now=0) == 0


def test_a_second_response_is_held_off():
    throttle = ResponseThrottle(cooldown=10)
    throttle.record(USER, now=0)
    assert throttle.seconds_remaining(USER, now=1) == 9


def test_the_cooldown_expires():
    throttle = ResponseThrottle(cooldown=10)
    throttle.record(USER, now=0)
    assert throttle.seconds_remaining(USER, now=10) == 0


def test_one_users_cooldown_does_not_affect_another():
    throttle = ResponseThrottle(cooldown=10)
    throttle.record(USER, now=0)
    assert throttle.seconds_remaining(OTHER, now=1) == 0


def test_cooldown_entries_are_pruned():
    throttle = ResponseThrottle(cooldown=10)
    for user_id in range(PRUNE_THRESHOLD):
        throttle.record(user_id, now=0)

    throttle.record(999_999, now=1000)

    assert len(throttle._last_response) < PRUNE_THRESHOLD


def test_pruning_keeps_live_cooldowns():
    throttle = ResponseThrottle(cooldown=10)
    for user_id in range(PRUNE_THRESHOLD):
        throttle.record(user_id, now=0)
    throttle.record(USER, now=999)

    throttle.record(999_999, now=1000)

    assert throttle.seconds_remaining(USER, now=1000) > 0


# --- the delay budget -------------------------------------------------------

def test_a_fresh_message_has_the_full_budget():
    now = datetime.now(timezone.utc)
    assert delay_budget(now, now=now) == MAX_RESPONSE_DELAY


def test_the_budget_shrinks_with_the_message_age():
    now = datetime.now(timezone.utc)
    created = now - timedelta(seconds=20)
    assert delay_budget(created, now=now) == MAX_RESPONSE_DELAY - 20


def test_an_old_message_has_no_budget_left():
    now = datetime.now(timezone.utc)
    created = now - timedelta(seconds=MAX_RESPONSE_DELAY + 5)
    assert delay_budget(created, now=now) < 0


# --- slots ------------------------------------------------------------------

def test_slots_are_handed_out_up_to_the_cap():
    throttle = ResponseThrottle(max_concurrent=2)

    async def scenario():
        return [await throttle.acquire_slot(CHANNEL) for _ in range(2)]

    assert asyncio.run(scenario()) == [SlotOutcome.GRANTED, SlotOutcome.GRANTED]


def test_a_released_slot_can_be_taken_again():
    throttle = ResponseThrottle(max_concurrent=1)

    async def scenario():
        first = await throttle.acquire_slot(CHANNEL)
        throttle.release_slot()
        second = await throttle.acquire_slot(CHANNEL)
        return first, second

    assert asyncio.run(scenario()) == (SlotOutcome.GRANTED, SlotOutcome.GRANTED)


def test_an_already_stale_request_never_queues():
    throttle = ResponseThrottle(max_concurrent=1)

    async def scenario():
        await throttle.acquire_slot(CHANNEL)
        return await throttle.acquire_slot(CHANNEL, wait_budget=0)

    assert asyncio.run(scenario()) is SlotOutcome.TOO_SLOW


# --- queueing ---------------------------------------------------------------

def test_a_waiting_request_is_served_when_a_slot_frees():
    """The whole point of the queue: a small collision resolves itself."""
    throttle = ResponseThrottle(max_concurrent=1)

    async def scenario():
        await throttle.acquire_slot(CHANNEL)

        async def release_shortly():
            await asyncio.sleep(0.05)
            throttle.release_slot()

        releaser = asyncio.create_task(release_shortly())
        try:
            return await throttle.acquire_slot(CHANNEL, wait_budget=5)
        finally:
            await releaser

    assert asyncio.run(scenario()) is SlotOutcome.GRANTED


def test_waiting_longer_than_the_budget_gives_up():
    """A reply that arrives after the conversation moved on is worse than none."""
    throttle = ResponseThrottle(max_concurrent=1)

    async def scenario():
        await throttle.acquire_slot(CHANNEL)
        return await throttle.acquire_slot(CHANNEL, wait_budget=0.05)

    assert asyncio.run(scenario()) is SlotOutcome.TOO_SLOW


def test_the_queue_is_bounded():
    throttle = ResponseThrottle(max_concurrent=1, max_queue_depth=2)

    async def scenario():
        await throttle.acquire_slot(CHANNEL)
        waiters = [
            asyncio.create_task(throttle.acquire_slot(CHANNEL, wait_budget=5))
            for _ in range(2)
        ]
        await asyncio.sleep(0.05)  # let them queue

        overflow = await throttle.acquire_slot(CHANNEL, wait_budget=5)

        for task in waiters:
            task.cancel()
        return overflow

    assert asyncio.run(scenario()) is SlotOutcome.QUEUE_FULL


def test_one_busy_channel_does_not_block_another():
    """Depth is per channel, so a flooded channel cannot starve a quiet one."""
    throttle = ResponseThrottle(max_concurrent=1, max_queue_depth=1)

    async def scenario():
        await throttle.acquire_slot(CHANNEL)
        queued = asyncio.create_task(throttle.acquire_slot(CHANNEL, wait_budget=5))
        await asyncio.sleep(0.05)

        full = await throttle.acquire_slot(CHANNEL, wait_budget=5)
        elsewhere = asyncio.create_task(
            throttle.acquire_slot(OTHER_CHANNEL, wait_budget=5)
        )
        await asyncio.sleep(0.05)
        depth_elsewhere = throttle.queue_depth(OTHER_CHANNEL)

        queued.cancel()
        elsewhere.cancel()
        return full, depth_elsewhere

    full, depth_elsewhere = asyncio.run(scenario())
    assert full is SlotOutcome.QUEUE_FULL
    assert depth_elsewhere == 1  # it queued rather than being refused


def test_the_queue_empties_as_waiters_are_served():
    throttle = ResponseThrottle(max_concurrent=1, max_queue_depth=5)

    async def scenario():
        await throttle.acquire_slot(CHANNEL)
        waiter = asyncio.create_task(throttle.acquire_slot(CHANNEL, wait_budget=5))
        await asyncio.sleep(0.05)
        queued_depth = throttle.queue_depth(CHANNEL)

        throttle.release_slot()
        await waiter

        return queued_depth, throttle.queue_depth(CHANNEL)

    assert asyncio.run(scenario()) == (1, 0)


def test_giving_up_leaves_no_trace_in_the_queue():
    """A timed-out waiter must not permanently occupy a queue place."""
    throttle = ResponseThrottle(max_concurrent=1, max_queue_depth=2)

    async def scenario():
        await throttle.acquire_slot(CHANNEL)
        await throttle.acquire_slot(CHANNEL, wait_budget=0.05)
        return throttle.queue_depth(CHANNEL)

    assert asyncio.run(scenario()) == 0


def test_a_timed_out_wait_does_not_leak_a_slot():
    """asyncio can grant the semaphore as the timeout fires; the slot must come back."""
    throttle = ResponseThrottle(max_concurrent=1)

    async def scenario():
        await throttle.acquire_slot(CHANNEL)
        await throttle.acquire_slot(CHANNEL, wait_budget=0.05)
        throttle.release_slot()
        return throttle.in_flight

    assert asyncio.run(scenario()) == 0


def test_busy_reports_whether_a_request_would_wait():
    throttle = ResponseThrottle(max_concurrent=1)

    async def scenario():
        before = throttle.busy
        await throttle.acquire_slot(CHANNEL)
        return before, throttle.busy

    assert asyncio.run(scenario()) == (False, True)


def test_in_flight_reflects_taken_slots():
    throttle = ResponseThrottle(max_concurrent=2)

    async def scenario():
        await throttle.acquire_slot(CHANNEL)
        during = throttle.in_flight
        throttle.release_slot()
        return during, throttle.in_flight

    assert asyncio.run(scenario()) == (1, 0)
