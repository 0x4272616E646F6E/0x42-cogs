"""Turning Discord messages into the text the model sees.

Everything the model knows about a channel comes through here, so these pin the
exact phrasing: names instead of raw IDs, and attachments described rather than
silently dropped.
"""

import asyncio
from unittest.mock import MagicMock

import discord

from aiagent.messages_list.converter.converter import MessageConverter
from aiagent.messages_list.converter.helpers import (
    format_embed_content,
    format_embed_text_content,
    format_sticker_content,
    format_text_content,
    mention_to_text,
)

from . import fakes


def make_message(**kwargs):
    guild = kwargs.pop("guild", None) or fakes.Guild()
    message = fakes.message(guild=guild, **kwargs)
    message.role_mentions = []
    message.channel_mentions = []
    return message


# --- plain text -------------------------------------------------------------

def test_a_users_message_is_attributed_to_them():
    message = make_message(content="hello world", author=fakes.Author(name="brandon"))
    assert format_text_content(message) == 'User "brandon" said: hello world'


def test_the_bots_own_message_is_not_attributed():
    """The bot's own words are the assistant turn; a name prefix would be noise."""
    guild = fakes.Guild()
    message = make_message(content="my reply", author=guild.me, guild=guild)
    assert format_text_content(message) == "my reply"


def test_an_empty_message_produces_nothing():
    assert format_text_content(make_message(content="")) is None
    assert format_text_content(make_message(content="   ")) is None


def test_a_join_is_described():
    message = make_message(content="", author=fakes.Author(name="newbie"))
    message.type = discord.MessageType.new_member
    described = format_text_content(message)
    assert "joined the server" in described and "newbie" in described


# --- mentions ---------------------------------------------------------------

def test_user_mentions_become_names():
    mentioned = fakes.Author(id=7, name="alice")
    message = make_message(content="hey <@7> look")
    message.mentions = [mentioned]
    mentioned.mention = "<@7>"
    assert mention_to_text(message) == "hey @alice look"


def test_role_mentions_become_names():
    role = MagicMock(spec=discord.Role)
    role.mention = "<@&500>"
    role.name = "moderators"
    message = make_message(content="ping <@&500>")
    message.role_mentions = [role]
    assert mention_to_text(message) == "ping @moderators"


def test_channel_mentions_become_names():
    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "<#200>"
    channel.name = "general"
    message = make_message(content="see <#200>")
    message.channel_mentions = [channel]
    assert mention_to_text(message) == "see #general"


def test_a_message_without_mentions_is_untouched():
    assert mention_to_text(make_message(content="plain text")) == "plain text"


# --- embeds and stickers ----------------------------------------------------

def test_an_embed_is_described():
    embed = type("Embed", (), {"title": "A Title", "description": "A description"})()
    message = make_message(content="", embeds=[embed], author=fakes.Author(name="brandon"))
    described = format_embed_content(message)
    assert "A Title" in described and "A description" in described
    assert 'User "brandon" sent' in described


def test_a_message_with_no_embed_yields_nothing():
    assert format_embed_content(make_message(content="hi")) is None


def test_embed_text_content_strips_the_url():
    message = make_message(content="look at https://example.com/thing")
    assert "https://" not in (format_embed_text_content(message) or "")


def test_a_url_only_message_has_no_embed_text():
    assert format_embed_text_content(make_message(content="https://example.com")) is None


def test_a_sticker_is_described():
    sticker = MagicMock()
    sticker.name = "party-blob"
    sticker.description = "a celebrating blob"

    async def fetch():
        return sticker

    message = make_message(content="", author=fakes.Author(name="brandon"))
    message.stickers = [MagicMock(fetch=fetch)]

    described = asyncio.run(format_sticker_content(message))
    assert "party-blob" in described and "a celebrating blob" in described


def test_a_sticker_that_cannot_be_fetched_still_names_it():
    """Sticker fetches hit the API and can fail; the name is already in hand."""
    async def fetch():
        raise RuntimeError("api down")

    sticker = MagicMock(fetch=fetch)
    sticker.name = "party-blob"

    message = make_message(content="")
    message.stickers = [sticker]

    assert "party-blob" in asyncio.run(format_sticker_content(message))


# --- the converter ----------------------------------------------------------

def convert(message):
    converter = MessageConverter(fakes.Cog())
    return asyncio.run(converter.convert(message))


def test_a_plain_message_becomes_one_user_entry():
    entries = convert(make_message(content="hello", author=fakes.Author(id=42)))
    assert len(entries) == 1
    assert entries[0].role == "user"


def test_a_bot_message_becomes_an_assistant_entry():
    guild = fakes.Guild()
    entries = convert(make_message(content="my reply", author=guild.me, guild=guild))
    assert entries[0].role == "assistant"


def test_an_attachment_is_described_and_the_text_kept():
    message = make_message(content="check this out", author=fakes.Author(name="brandon"))
    attachment = MagicMock()
    attachment.filename = "diagram.png"
    message.attachments = [attachment]

    entries = convert(message)
    combined = " ".join(entry.content for entry in entries)

    assert "diagram.png" in combined
    assert "check this out" in combined


def test_an_empty_message_converts_to_nothing():
    assert convert(make_message(content="")) is None


def test_an_embed_message_yields_both_the_embed_and_the_text():
    embed = type("Embed", (), {"title": "Title", "description": "Description"})()
    message = make_message(content="look https://example.com and my thoughts", embeds=[embed])

    entries = convert(message)
    combined = " ".join(entry.content for entry in entries)

    assert "Title" in combined
    assert "my thoughts" in combined
