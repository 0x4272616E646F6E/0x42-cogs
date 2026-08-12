"""The entry points: what happens between a Discord event and a response.

Two things matter here — that nothing is dispatched unless the bot was addressed
*and* the message passed validation, and that the cheap check runs first so an
ordinary channel message costs no config reads.
"""

import asyncio
import contextlib

from aiagent.core import handlers

from . import fakes


class Recorder:
    """Records which stage ran, in order."""

    def __init__(self, valid=True, mentioned=True):
        self.calls = []
        self._valid = valid
        self._mentioned = mentioned

    async def is_bot_mentioned_or_replied(self, _cog, _message):
        self.calls.append("mention")
        return self._mentioned

    async def is_valid_message(self, _cog, _ctx):
        self.calls.append("validate")
        return self._valid

    async def dispatch_response(self, _cog, _ctx):
        self.calls.append("dispatch")


def wire(monkeypatch, recorder):
    monkeypatch.setattr(
        handlers, "is_bot_mentioned_or_replied", recorder.is_bot_mentioned_or_replied
    )
    monkeypatch.setattr(handlers, "is_valid_message", recorder.is_valid_message)
    monkeypatch.setattr(handlers, "dispatch_response", recorder.dispatch_response)


class Bot(fakes.Bot):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx

    async def get_context(self, _message):
        self._ctx.got_context = True
        return self._ctx


def run_message(monkeypatch, recorder, content="@Red hello"):
    ctx = fakes.Ctx()
    ctx.got_context = False
    ctx.message = fakes.message(content=content, guild=ctx.guild)
    cog = fakes.Cog(bot=Bot(ctx))
    wire(monkeypatch, recorder)

    asyncio.run(handlers.handle_message(cog, ctx.message))
    return ctx


# --- handle_message ---------------------------------------------------------

def test_an_addressed_and_valid_message_is_dispatched(monkeypatch):
    recorder = Recorder()
    run_message(monkeypatch, recorder)
    assert recorder.calls == ["mention", "validate", "dispatch"]


def test_a_message_that_does_not_address_the_bot_is_dropped(monkeypatch):
    recorder = Recorder(mentioned=False)
    run_message(monkeypatch, recorder)
    assert "dispatch" not in recorder.calls


def test_an_unaddressed_message_costs_no_validation(monkeypatch):
    """Validation reads config and can build the LLM client; skip it for chatter."""
    recorder = Recorder(mentioned=False)
    run_message(monkeypatch, recorder)
    assert recorder.calls == ["mention"]


def test_an_unaddressed_message_does_not_even_build_a_context(monkeypatch):
    recorder = Recorder(mentioned=False)
    ctx = run_message(monkeypatch, recorder)
    assert ctx.got_context is False


def test_an_addressed_but_invalid_message_is_dropped(monkeypatch):
    recorder = Recorder(valid=False)
    run_message(monkeypatch, recorder)
    assert recorder.calls == ["mention", "validate"]


def test_the_mention_check_runs_before_validation(monkeypatch):
    recorder = Recorder()
    run_message(monkeypatch, recorder)
    assert recorder.calls.index("mention") < recorder.calls.index("validate")


# --- waiting for link embeds ------------------------------------------------

def test_a_message_with_a_url_waits_for_its_embed(monkeypatch):
    recorder = Recorder()
    waited = []

    async def fake_wait(ctx):
        waited.append(True)
        return ctx

    monkeypatch.setattr(handlers, "wait_for_embed", fake_wait)
    run_message(monkeypatch, recorder, content="@Red look at https://example.com")

    assert waited == [True]


def test_a_message_without_a_url_does_not_wait(monkeypatch):
    recorder = Recorder()
    waited = []

    async def fake_wait(ctx):
        waited.append(True)
        return ctx

    monkeypatch.setattr(handlers, "wait_for_embed", fake_wait)
    run_message(monkeypatch, recorder, content="@Red no links here")

    assert waited == []


def test_wait_for_embed_returns_once_the_embed_arrives(monkeypatch):
    """It polls the message; a valid embed on the first fetch must end it at once."""
    monkeypatch.setattr(handlers, "is_embed_valid", lambda _message: True)

    ctx = fakes.Ctx()
    fetched = []

    async def fetch_message(_id):
        fetched.append(True)
        return ctx.message

    ctx.channel.fetch_message = fetch_message

    result = asyncio.run(handlers.wait_for_embed(ctx))

    assert result is ctx
    assert fetched == []  # already valid, so no fetch at all


# --- the slash command ------------------------------------------------------

class Interaction:
    def __init__(self):
        self.deferred = False

    async def response_defer(self):
        self.deferred = True


def run_slash(monkeypatch, recorder, ctx):
    interaction = Interaction()

    class Response:
        async def defer(self_inner):
            interaction.deferred = True

    interaction.response = Response()

    async def from_interaction(_inter):
        return ctx

    monkeypatch.setattr(handlers.commands.Context, "from_interaction", from_interaction)
    wire(monkeypatch, recorder)

    cog = fakes.Cog(bot=Bot(ctx))
    asyncio.run(handlers.handle_slash_command(cog, interaction, "a question"))
    return interaction


def test_a_valid_slash_command_is_dispatched(monkeypatch):
    recorder = Recorder()
    ctx = fakes.Ctx()
    run_slash(monkeypatch, recorder, ctx)
    assert "dispatch" in recorder.calls


def test_the_slash_command_does_not_require_a_mention(monkeypatch):
    """Invoking /chat is addressing the bot; requiring a mention too would be absurd."""
    recorder = Recorder(mentioned=False)
    ctx = fakes.Ctx()
    run_slash(monkeypatch, recorder, ctx)
    assert "dispatch" in recorder.calls


def test_an_invalid_slash_command_is_refused_with_a_message(monkeypatch):
    recorder = Recorder(valid=False)
    ctx = fakes.Ctx()
    run_slash(monkeypatch, recorder, ctx)
    assert "not allowed" in ctx.replies_text()


def test_a_failing_slash_command_answers_instead_of_raising(monkeypatch):
    """An unhandled exception here would leave the interaction hanging."""
    recorder = Recorder()

    async def explode(_cog, _ctx):
        raise RuntimeError("the model fell over")

    ctx = fakes.Ctx()
    monkeypatch.setattr(handlers, "dispatch_response", explode)
    monkeypatch.setattr(handlers, "is_valid_message", recorder.is_valid_message)

    class Response:
        async def defer(self):
            pass

    interaction = Interaction()
    interaction.response = Response()

    async def from_interaction(_inter):
        return ctx

    monkeypatch.setattr(handlers.commands.Context, "from_interaction", from_interaction)

    asyncio.run(handlers.handle_slash_command(fakes.Cog(bot=Bot(ctx)), interaction, "q"))

    assert "Error in generating response" in ctx.replies_text()


def test_the_interaction_is_deferred_before_the_work_starts(monkeypatch):
    """Generation takes longer than Discord's 3s window."""
    recorder = Recorder()
    ctx = fakes.Ctx()
    interaction = run_slash(monkeypatch, recorder, ctx)
    assert interaction.deferred is True


# --- throttling -------------------------------------------------------------

def test_a_rapid_second_mention_is_refused(monkeypatch):
    """One user in a loop must not queue a generation per message."""
    recorder = Recorder()
    ctx = fakes.Ctx()
    ctx.got_context = False
    ctx.message = fakes.message(content="@Red hello", guild=ctx.guild)
    cog = fakes.Cog(bot=Bot(ctx))
    wire(monkeypatch, recorder)

    asyncio.run(handlers.handle_message(cog, ctx.message))
    asyncio.run(handlers.handle_message(cog, ctx.message))

    assert recorder.calls.count("dispatch") == 1
    assert ctx.reactions == ["\U0001f4a4"]


def test_the_cooldown_is_per_user(monkeypatch):
    recorder = Recorder()
    ctx = fakes.Ctx()
    ctx.got_context = False
    cog = fakes.Cog(bot=Bot(ctx))
    wire(monkeypatch, recorder)

    for user_id in (42, 7):
        ctx.author = fakes.Author(id=user_id)
        ctx.message = fakes.message(content="@Red hi", author=ctx.author, guild=ctx.guild)
        asyncio.run(handlers.handle_message(cog, ctx.message))

    assert recorder.calls.count("dispatch") == 2


def test_a_mention_while_the_model_is_busy_waits_its_turn(monkeypatch):
    """A small collision should resolve itself rather than telling people to retry."""
    recorder = Recorder()
    ctx = fakes.Ctx()
    ctx.got_context = False
    ctx.message = fakes.message(content="@Red hello", guild=ctx.guild)
    cog = fakes.Cog(bot=Bot(ctx))
    wire(monkeypatch, recorder)

    async def scenario():
        for _ in range(cog.throttle.max_concurrent):
            await cog.throttle.acquire_slot(ctx.channel.id)

        async def release_shortly():
            await asyncio.sleep(0.05)
            cog.throttle.release_slot()

        releaser = asyncio.create_task(release_shortly())
        await handlers.handle_message(cog, ctx.message)
        await releaser

    asyncio.run(scenario())

    assert "dispatch" in recorder.calls
    # queued, so the user was told they are waiting
    assert "\u23f3" in ctx.reactions


def test_a_full_queue_is_refused(monkeypatch):
    """Past the depth cap, refuse rather than let a backlog grow."""
    recorder = Recorder()
    ctx = fakes.Ctx()
    ctx.got_context = False
    ctx.message = fakes.message(content="@Red hello", guild=ctx.guild)
    cog = fakes.Cog(bot=Bot(ctx))
    wire(monkeypatch, recorder)

    async def scenario():
        for _ in range(cog.throttle.max_concurrent):
            await cog.throttle.acquire_slot(ctx.channel.id)

        waiters = [
            asyncio.create_task(
                cog.throttle.acquire_slot(ctx.channel.id, wait_budget=5)
            )
            for _ in range(cog.throttle.max_queue_depth)
        ]
        await asyncio.sleep(0.05)

        await handlers.handle_message(cog, ctx.message)

        for task in waiters:
            task.cancel()

    asyncio.run(scenario())

    assert "dispatch" not in recorder.calls
    assert "\U0001f4a4" in ctx.reactions


def test_a_message_too_old_to_answer_is_dropped(monkeypatch):
    """Answering now would land in a conversation that has moved on."""
    from datetime import datetime, timedelta, timezone

    from aiagent.core.throttle import MAX_RESPONSE_DELAY

    recorder = Recorder()
    ctx = fakes.Ctx()
    ctx.got_context = False
    ctx.message = fakes.message(
        content="@Red hello",
        guild=ctx.guild,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=MAX_RESPONSE_DELAY + 5),
    )
    cog = fakes.Cog(bot=Bot(ctx))
    wire(monkeypatch, recorder)

    asyncio.run(handlers.handle_message(cog, ctx.message))

    assert "dispatch" not in recorder.calls
    assert "\U0001f4a4" in ctx.reactions


def test_the_slot_is_released_even_when_generation_fails(monkeypatch):
    """A leaked slot would permanently reduce the bot's capacity."""
    recorder = Recorder()
    ctx = fakes.Ctx()
    ctx.got_context = False
    ctx.message = fakes.message(content="@Red hello", guild=ctx.guild)
    cog = fakes.Cog(bot=Bot(ctx))

    async def explode(_cog, _ctx):
        raise RuntimeError("the model fell over")

    wire(monkeypatch, recorder)
    monkeypatch.setattr(handlers, "dispatch_response", explode)

    with contextlib.suppress(RuntimeError):
        asyncio.run(handlers.handle_message(cog, ctx.message))

    assert cog.throttle.in_flight == 0


def test_a_busy_slash_command_is_refused_without_generating(monkeypatch):
    recorder = Recorder()
    ctx = fakes.Ctx()

    async def scenario():
        for _ in range(cog.throttle.max_concurrent):
            await cog.throttle.acquire_slot(ctx.channel.id)
        waiters = [
            asyncio.create_task(cog.throttle.acquire_slot(ctx.channel.id, wait_budget=5))
            for _ in range(cog.throttle.max_queue_depth)
        ]
        await asyncio.sleep(0.05)
        await handlers.handle_slash_command(cog, interaction, "a question")
        for task in waiters:
            task.cancel()

    class Response:
        async def defer(self):
            pass

    interaction = Interaction()
    interaction.response = Response()

    async def from_interaction(_inter):
        return ctx

    monkeypatch.setattr(handlers.commands.Context, "from_interaction", from_interaction)
    wire(monkeypatch, recorder)
    cog = fakes.Cog(bot=Bot(ctx))

    asyncio.run(scenario())

    assert "dispatch" not in recorder.calls
    assert "generating as much as it can" in ctx.replies_text()
