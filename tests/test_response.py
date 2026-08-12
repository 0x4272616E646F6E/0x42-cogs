"""Getting the generated text back into the channel."""

import asyncio

import discord
import pytest

from aiagent.response.chat import response as response_module
from aiagent.response.chat.response import (
    MAX_RESPONSE_CHUNKS,
    MESSAGE_LENGTH_LIMIT,
    TRUNCATION_NOTICE,
    send_response,
    split_response,
)


class _DeletedResponse:
    """Minimal stand-in for the aiohttp response discord.NotFound expects."""

    status = 404
    reason = "Not Found"


class FakeAuthor:
    id = 42
    display_name = "brandon"


class FakeMessage:
    def __init__(self, reply_fails=False):
        self.author = FakeAuthor()
        self.replies = []
        self._reply_fails = reply_fails

    async def reply(self, content, **_kwargs):
        if self._reply_fails:
            raise discord.NotFound(_DeletedResponse(), "message deleted")
        self.replies.append(content)


class FakeCtx:
    def __init__(self, reply_fails=False, interaction=None):
        self.message = FakeMessage(reply_fails)
        self.interaction = interaction
        self.sent = []

    async def send(self, content, **_kwargs):
        self.sent.append(content)


# --- chunking ---------------------------------------------------------------

def test_short_response_is_one_chunk():
    assert split_response("hello") == ["hello"]


def test_response_is_split_at_the_discord_limit():
    text = "x" * (MESSAGE_LENGTH_LIMIT * 2)
    assert len(split_response(text)) == 2


def test_runaway_response_is_capped():
    """A local model with no max_tokens must not flood the channel."""
    text = "x" * (MESSAGE_LENGTH_LIMIT * 10)
    chunks = split_response(text)
    assert len(chunks) == MAX_RESPONSE_CHUNKS
    assert chunks[-1].endswith(TRUNCATION_NOTICE)


def test_capped_chunks_still_respect_the_length_limit():
    text = "x" * (MESSAGE_LENGTH_LIMIT * 10)
    for chunk in split_response(text):
        assert len(chunk) <= MESSAGE_LENGTH_LIMIT


def test_response_exactly_at_the_cap_is_not_truncated():
    text = "x" * (MESSAGE_LENGTH_LIMIT * MAX_RESPONSE_CHUNKS)
    chunks = split_response(text)
    assert len(chunks) == MAX_RESPONSE_CHUNKS
    assert not chunks[-1].endswith(TRUNCATION_NOTICE)


# --- sending ----------------------------------------------------------------

def test_reply_is_used_for_the_first_chunk():
    ctx = FakeCtx()
    asyncio.run(send_response(ctx, "hello", can_reply=True))
    assert ctx.message.replies == ["hello"]
    assert ctx.sent == []


def test_remaining_chunks_are_plain_sends():
    ctx = FakeCtx()
    asyncio.run(send_response(ctx, "x" * (MESSAGE_LENGTH_LIMIT * 2), can_reply=True))
    assert len(ctx.message.replies) == 1
    assert len(ctx.sent) == 1


def test_deleted_message_falls_back_to_sending():
    """Replying to a deleted message raises; that must not lose the response."""
    ctx = FakeCtx(reply_fails=True)
    asyncio.run(send_response(ctx, "hello", can_reply=True))
    assert ctx.message.replies == []
    assert ctx.sent == ["hello"]


def test_can_reply_false_sends_without_replying():
    ctx = FakeCtx()
    asyncio.run(send_response(ctx, "hello", can_reply=False))
    assert ctx.message.replies == []
    assert ctx.sent == ["hello"]


def test_slash_command_uses_the_interaction_followup():
    class FakeFollowup:
        def __init__(self):
            self.sent = []

        async def send(self, content, **_kwargs):
            self.sent.append(content)

    class FakeInteraction:
        def __init__(self):
            self.followup = FakeFollowup()

    interaction = FakeInteraction()
    ctx = FakeCtx(interaction=interaction)
    asyncio.run(send_response(ctx, "hello", can_reply=True))
    assert interaction.followup.sent == ["hello"]
    assert ctx.message.replies == []


# --- removelist -------------------------------------------------------------

class FakeValue:
    def __init__(self, value):
        self.value = value

    async def __call__(self):
        return self.value


class FakeGuildConfig:
    def __init__(self, patterns):
        self.removelist_regexes = FakeValue(patterns)


class FakeConfig:
    def __init__(self, patterns):
        self._guild = FakeGuildConfig(patterns)

    def guild(self, _guild):
        return self._guild


class FakeMe:
    nick = "Red"


class FakeGuild:
    me = FakeMe()


class FakeBotUser:
    display_name = "Red"


class FakeBot:
    user = FakeBotUser()


class CleanupCtx:
    def __init__(self):
        self.guild = FakeGuild()
        self.bot = FakeBot()
        self.message = type("M", (), {"guild": FakeGuild()})()
        self.history_calls = 0

    def channel_history(self, limit):
        self.history_calls += 1

        async def empty():
            return
            yield  # pragma: no cover

        return empty()

    @property
    def channel(self):
        outer = self

        class Channel:
            def history(self, limit):
                return outer.channel_history(limit)

        return Channel()


def clean(patterns, text):
    ctx = CleanupCtx()
    result = asyncio.run(
        response_module.remove_patterns_from_response(ctx, FakeConfig(patterns), text)
    )
    return result, ctx


def test_patterns_are_stripped_from_the_response():
    result, _ = clean([r"<think>[\s\S]*?</think>"], "<think>hmm</think>the answer")
    assert result == "the answer"


def test_botname_placeholder_is_substituted():
    result, _ = clean([r"^{botname}:"], "Red: the answer")
    assert result == "the answer"


def test_channel_history_is_not_fetched_when_no_pattern_needs_it():
    """The {authorname} expansion costs an API call; skip it when unused."""
    _, ctx = clean([r"^nothing$"], "the answer")
    assert ctx.history_calls == 0


def test_channel_history_is_fetched_when_a_pattern_needs_it():
    _, ctx = clean([r"^{authorname}:"], "the answer")
    assert ctx.history_calls == 1


@pytest.mark.parametrize("pattern", [r"(unclosed", r"[z-a]"])
def test_broken_pattern_leaves_the_response_intact(pattern):
    result, _ = clean([pattern], "the answer")
    assert result == "the answer"
