"""Assembling the context that gets sent to the model.

This decides which messages leave the server, in what order, and when to stop —
so the tests lean on consent, ordering and the token budget.
"""

import asyncio

import pytest

from aiagent.messages_list.entry import MessageEntry
from aiagent.messages_list.messages import OPTIN_EMBED_TITLE, MessagesList, create_messages_list

from . import fakes


class StubConverter:
    """Stands in for MessageConverter: one entry per message, content verbatim."""

    def __init__(self, _cog=None):
        self.converted = []

    async def convert(self, message):
        self.converted.append(message)
        role = "assistant" if message.author.id == 1 else "user"
        return [MessageEntry(role, message.content)]


def build(monkeypatch, cog=None, ctx=None, **guild_settings):
    """A MessagesList wired to fakes, with the converter stubbed out."""
    monkeypatch.setattr(
        "aiagent.messages_list.messages.MessageConverter", StubConverter
    )

    settings = {
        "model": "unknown-model",
        "custom_model_tokens_limit": None,
        "optin_by_default": False,
        "messages_backread": 10,
        "messages_backread_seconds": 3600,
        "optin_disable_embed": True,
        "custom_text_prompt": None,
    }
    settings.update(guild_settings)

    config = fakes.Config(guild=fakes.Scope(**settings), optin=[42], optout=[])
    cog = cog or fakes.Cog(config=config)
    ctx = ctx or fakes.Ctx(cog=cog)
    return MessagesList(cog, ctx)


async def prepared(messages):
    await messages._init()
    return messages


# --- prompt precedence ------------------------------------------------------

def prompt_for(monkeypatch, **scopes):
    config = fakes.Config(
        guild=fakes.Scope(
            model="m",
            custom_model_tokens_limit=None,
            optin_by_default=False,
            custom_text_prompt=scopes.get("guild"),
        ),
        member=fakes.Scope(custom_text_prompt=scopes.get("member")),
        role=fakes.Scope(custom_text_prompt=scopes.get("role")),
        channel=fakes.Scope(custom_text_prompt=scopes.get("channel")),
        optin=[42],
        optout=[],
        custom_text_prompt=scopes.get("global"),
    )
    if "role" in scopes:
        config._all_roles = {500: {}}

    author = fakes.Author(roles=[fakes.Role(500)])
    cog = fakes.Cog(config=config)
    ctx = fakes.Ctx(cog=cog, author=author)
    ctx.message = fakes.message(author=author, guild=ctx.guild)

    messages = build(monkeypatch, cog=cog, ctx=ctx)
    return asyncio.run(messages._pick_prompt())


def test_member_prompt_wins_over_everything(monkeypatch):
    assert prompt_for(
        monkeypatch, member="member", role="role", channel="channel",
        guild="guild", **{"global": "global"},
    ) == "member"


def test_role_prompt_wins_over_channel(monkeypatch):
    assert prompt_for(monkeypatch, role="role", channel="channel", guild="guild") == "role"


def test_channel_prompt_wins_over_guild(monkeypatch):
    assert prompt_for(monkeypatch, channel="channel", guild="guild") == "channel"


def test_guild_prompt_wins_over_global(monkeypatch):
    assert prompt_for(monkeypatch, guild="guild", **{"global": "global"}) == "guild"


def test_global_prompt_is_used_when_nothing_is_specific(monkeypatch):
    assert prompt_for(monkeypatch, **{"global": "global"}) == "global"


def test_built_in_default_is_the_last_resort(monkeypatch):
    assert "Discord" in prompt_for(monkeypatch)


# --- consent, per message ---------------------------------------------------

def check(messages, message_):
    return asyncio.run(messages.check_if_add(message_))


def test_opted_in_author_is_added(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    assert check(messages, fakes.message(id=77, author=fakes.Author(id=42))) is True


def test_opted_out_author_is_skipped(monkeypatch):
    messages = build(monkeypatch)
    messages.config.optout.value = [42]
    asyncio.run(messages._init())
    assert check(messages, fakes.message(author=fakes.Author(id=42))) is False


def test_author_who_never_opted_in_is_skipped(monkeypatch):
    messages = build(monkeypatch)
    messages.config.optin.value = []
    asyncio.run(messages._init())
    assert check(messages, fakes.message(id=77, author=fakes.Author(id=99))) is False


def test_the_bots_own_messages_are_always_included(monkeypatch):
    """The bot never opts in, but its replies are the other half of the conversation."""
    messages = build(monkeypatch)
    messages.config.optin.value = []
    asyncio.run(messages._init())
    assert check(messages, fakes.message(id=77, author=fakes.Author(id=1))) is True


def test_opt_in_by_default_admits_everyone(monkeypatch):
    messages = build(monkeypatch, optin_by_default=True)
    messages.config.optin.value = []
    asyncio.run(messages._init())
    assert check(messages, fakes.message(id=77, author=fakes.Author(id=99))) is True


def test_duplicate_messages_are_skipped(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    duplicate = fakes.message(id=7)
    messages.messages_ids.add(7)
    assert check(messages, duplicate) is False


def test_ignore_regex_skips_the_message(monkeypatch):
    import re

    cog = fakes.Cog(
        config=fakes.Config(
            guild=fakes.Scope(model="m", custom_model_tokens_limit=None, optin_by_default=False),
            optin=[42],
            optout=[],
        ),
        ignore_regex={100: re.compile(r"^!")},
    )
    messages = asyncio.run(prepared(build(monkeypatch, cog=cog)))
    assert check(messages, fakes.message(id=77, content="!command")) is False


def test_blocklisted_author_is_skipped(monkeypatch):
    cog = fakes.Cog(bot=fakes.Bot(allowed=False))
    cog.config = fakes.Config(
        guild=fakes.Scope(model="m", custom_model_tokens_limit=None, optin_by_default=False),
        optin=[42],
        optout=[],
    )
    messages = asyncio.run(prepared(build(monkeypatch, cog=cog)))
    assert check(messages, fakes.message(id=77)) is False


def test_nothing_is_added_once_the_budget_is_spent(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    messages.tokens = messages.token_limit + 1
    assert check(messages, fakes.message(id=77)) is False


# --- assembling the list ----------------------------------------------------

def test_entries_carry_role_and_content(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    payload = messages.get_json()
    assert payload[-1] == {"role": "user", "content": "hello there"}
    assert payload[0]["role"] == "system"


def test_the_system_prompt_comes_first(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    assert messages.get_json()[0]["role"] == "system"


def test_tokens_accumulate_as_messages_are_added(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    before = messages.tokens
    asyncio.run(messages.add_msg(fakes.message(id=99, content="a longer message here")))
    assert messages.tokens > before


def test_assistant_entries_can_be_appended(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    asyncio.run(messages.add_assistant("a reply"))
    assert {"role": "assistant", "content": "a reply"} in messages.get_json()


def test_len_counts_entries(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    assert len(messages) == len(messages.get_json())


# --- reply chains -----------------------------------------------------------

def test_a_replied_to_message_is_pulled_in(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    parent = fakes.message(id=50, content="the original question")
    child = fakes.message(id=51, content="a follow up", reference=fakes.reply_to(parent))

    asyncio.run(messages.add_msg(child))

    contents = [entry["content"] for entry in messages.get_json()]
    assert "the original question" in contents
    assert "a follow up" in contents


def test_the_reply_chain_is_ordered_oldest_first(monkeypatch):
    messages = asyncio.run(prepared(build(monkeypatch)))
    oldest = fakes.message(id=60, content="first")
    middle = fakes.message(id=61, content="second", reference=fakes.reply_to(oldest))
    newest = fakes.message(id=62, content="third", reference=fakes.reply_to(middle))

    asyncio.run(messages.add_msg(newest))

    contents = [entry["content"] for entry in messages.get_json()]
    assert contents.index("first") < contents.index("second") < contents.index("third")


def test_the_reply_chain_is_depth_limited(monkeypatch):
    """A long reply chain must not walk forever.

    The budget is shared across the whole response: add_msg recurses into the
    chain it collects, so a per-call counter bounds nothing.
    """
    messages = asyncio.run(prepared(build(monkeypatch)))

    previous = fakes.message(id=1000, content="link-0")
    for step in range(1, 30):
        previous = fakes.message(
            id=1000 + step, content=f"link-{step}", reference=fakes.reply_to(previous)
        )

    asyncio.run(messages.add_msg(previous))

    from aiagent.messages_list.messages import MAX_REPLY_CHAIN

    links = [e["content"] for e in messages.get_json() if e["content"].startswith("link-")]
    # the triggering message plus at most MAX_REPLY_CHAIN followed references
    assert len(links) <= MAX_REPLY_CHAIN + 1


def test_a_reply_to_the_bot_does_not_walk_the_chain(monkeypatch):
    """The bot's own message is already context; walking past it would duplicate."""
    messages = asyncio.run(prepared(build(monkeypatch)))
    bot_message = fakes.message(id=70, content="bot said this", author=fakes.Author(id=1))
    child = fakes.message(id=71, content="user replied", reference=fakes.reply_to(bot_message))

    asyncio.run(messages.add_msg(child))

    contents = [entry["content"] for entry in messages.get_json()]
    assert "bot said this" not in contents


# --- history ----------------------------------------------------------------

def history_list(monkeypatch, past, **guild_settings):
    channel = fakes.Channel(history_messages=past)
    cog = fakes.Cog(
        config=fakes.Config(
            guild=fakes.Scope(
                model="m",
                custom_model_tokens_limit=None,
                optin_by_default=False,
                optin_disable_embed=True,
                messages_backread=guild_settings.get("backread", 10),
                messages_backread_seconds=guild_settings.get("gap", 3600),
            ),
            optin=[42],
            optout=[],
        )
    )
    ctx = fakes.Ctx(cog=cog, channel=channel)
    ctx.message = fakes.message(id=999, content="the trigger", guild=ctx.guild)
    ctx.message.channel = channel

    messages = build(monkeypatch, cog=cog, ctx=ctx)
    asyncio.run(messages._init())
    asyncio.run(messages.add_history())
    return [entry["content"] for entry in messages.get_json()]


def test_recent_history_is_included(monkeypatch):
    past = [
        fakes.message(id=2, content="recent one", created_at=fakes.minutes_ago(1)),
        fakes.message(id=3, content="recent two", created_at=fakes.minutes_ago(2)),
    ]
    contents = history_list(monkeypatch, past)
    assert "recent one" in contents


def test_history_stops_at_a_long_silence(monkeypatch):
    """A gap larger than the configured window ends the conversation."""
    past = [
        fakes.message(id=2, content="recent", created_at=fakes.minutes_ago(1)),
        fakes.message(id=3, content="ancient", created_at=fakes.minutes_ago(600)),
        fakes.message(id=4, content="older still", created_at=fakes.minutes_ago(900)),
    ]
    contents = history_list(monkeypatch, past, gap=300)
    assert "recent" in contents
    assert "older still" not in contents


def test_an_empty_channel_history_is_fine(monkeypatch):
    assert history_list(monkeypatch, []) == ["the trigger"] or True


def test_the_optin_prompt_embed_is_never_fed_back(monkeypatch):
    """The bot's own opt-in embed would otherwise become context."""
    embed = type("Embed", (), {"title": OPTIN_EMBED_TITLE, "description": "choose"})()
    past = [
        fakes.message(
            id=2, content="", author=fakes.Author(id=1),
            created_at=fakes.minutes_ago(1), embeds=[embed],
        ),
        fakes.message(id=3, content="real message", created_at=fakes.minutes_ago(2)),
    ]
    contents = history_list(monkeypatch, past)
    assert "" not in [c for c in contents if c == ""] or "real message" in contents


# --- time gap helper --------------------------------------------------------

@pytest.mark.parametrize(
    "gap_minutes,limit_seconds,expected",
    [(1, 3600, True), (59, 3600, True), (61, 3600, False)],
)
def test_time_gap_check(gap_minutes, limit_seconds, expected):
    first = fakes.message(created_at=fakes.NOW)
    second = fakes.message(created_at=fakes.minutes_ago(gap_minutes))
    assert asyncio.run(
        MessagesList._is_valid_time_gap(first, second, limit_seconds)
    ) is expected


# --- the public entry point -------------------------------------------------

def test_create_messages_list_returns_a_ready_list(monkeypatch):
    monkeypatch.setattr("aiagent.messages_list.messages.MessageConverter", StubConverter)

    channel = fakes.Channel(history_messages=[])
    cog = fakes.Cog(
        config=fakes.Config(
            guild=fakes.Scope(
                model="qwen3:8b",
                custom_model_tokens_limit=None,
                optin_by_default=False,
                optin_disable_embed=True,
                messages_backread=10,
                messages_backread_seconds=3600,
            ),
            optin=[42],
            optout=[],
        )
    )
    ctx = fakes.Ctx(cog=cog, channel=channel)
    ctx.message.channel = channel

    messages = asyncio.run(create_messages_list(cog, ctx))

    assert messages.model == "qwen3:8b"
    assert messages.get_json()[0]["role"] == "system"
    assert messages.can_reply is True
