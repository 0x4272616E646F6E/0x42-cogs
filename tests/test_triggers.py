"""The bot answers when tagged or replied to — and at no other time."""

import asyncio
import inspect
from unittest.mock import MagicMock

import discord

from aiagent.core import handlers
from aiagent.core.triggers import is_bot_mentioned_or_replied

BOT_USER = MagicMock(spec=discord.ClientUser)
BOT_USER.id = 1234
SOMEONE_ELSE = 5678


class FakeBot:
    user = BOT_USER


class FakeCog:
    bot = FakeBot()


def make_message(mentions=(), replied_to_author_id=None):
    message = MagicMock(spec=discord.Message)
    message.mentions = list(mentions)

    if replied_to_author_id is None:
        message.reference = None
    else:
        replied_to = MagicMock(spec=discord.Message)
        replied_to.author.id = replied_to_author_id
        reference = MagicMock()
        reference.resolved = replied_to
        message.reference = reference

    return message


def triggered(message):
    return asyncio.run(is_bot_mentioned_or_replied(FakeCog(), message))


def test_mentioning_the_bot_triggers_a_reply():
    assert triggered(make_message(mentions=[BOT_USER])) is True


def test_replying_to_the_bot_triggers_a_reply():
    assert triggered(make_message(replied_to_author_id=BOT_USER.id)) is True


def test_mentioning_someone_else_does_not_trigger():
    other = MagicMock(spec=discord.Member)
    assert triggered(make_message(mentions=[other])) is False


def test_replying_to_someone_else_does_not_trigger():
    assert triggered(make_message(replied_to_author_id=SOMEONE_ELSE)) is False


def test_an_ordinary_message_does_not_trigger():
    assert triggered(make_message()) is False


def test_no_percentage_roll_survives():
    """Replies are deterministic: no dice, no reply-percent lookup."""
    assert not hasattr(handlers, "get_percentage")

    source = inspect.getsource(handlers.handle_message)
    assert "random" not in source
    assert "is_bot_mentioned_or_replied" in source
