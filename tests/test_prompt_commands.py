"""Prompt and preset commands.

The prompt is what the model is told it is, so these cover which scope a prompt
lands in, the length cap that stops an admin from filling the context window, and
preset expansion.
"""

import asyncio
import json

from aiagent.core.aiagent import AIAgent
from aiagent.core.throttle import ResponseThrottle
from aiagent.types.enums import MentionType

from . import fakes

COMMANDS = {command.qualified_name: command for command in AIAgent.__cog_commands__}


def run(name, cog, ctx, *args, **kwargs):
    return asyncio.run(COMMANDS[name].callback(cog, ctx, *args, **kwargs))


def setup(presets=None, max_prompt_length=200, is_owner=True, **guild_settings):
    settings = {
        "presets": json.dumps(presets or {}),
        "custom_text_prompt": None,
        "model": "qwen3:8b",
    }
    settings.update(guild_settings)

    config = fakes.Config(
        guild=fakes.Scope(**settings),
        member=fakes.Scope(custom_text_prompt=None),
        role=fakes.Scope(custom_text_prompt=None),
        channel=fakes.Scope(custom_text_prompt=None),
        max_prompt_length=max_prompt_length,
        custom_text_prompt=None,
    )

    cog = AIAgent.__new__(AIAgent)
    cog.config = config
    cog.bot = fakes.Bot()
    cog.bot.is_owner = _owner_check(is_owner)
    cog.ignore_regex = {}
    cog.channels_whitelist = {}
    cog.optindefault = {}
    cog.override_prompt_start_time = {}
    cog.openai_client = None
    cog.throttle = ResponseThrottle()

    ctx = fakes.Ctx(cog=cog)
    ctx.bot = cog.bot
    ctx.guild.channels = []
    ctx.message.attachments = []
    return cog, ctx


def _owner_check(result):
    async def is_owner(_user):
        return result
    return is_owner


# --- setting a prompt -------------------------------------------------------

def test_a_server_prompt_is_stored():
    cog, ctx = setup()
    run("aiagent prompt set", cog, ctx, None, prompt="you are a helpful bot")
    assert cog.config._guild.custom_text_prompt.value == "you are a helpful bot"


def test_setting_a_prompt_resets_the_conversation():
    """An old conversation under the previous persona would be confusing context."""
    cog, ctx = setup()
    run("aiagent prompt set", cog, ctx, None, prompt="a new persona")
    assert cog.override_prompt_start_time[ctx.guild.id] == ctx.message.created_at


def test_an_empty_prompt_clears_the_scope():
    cog, ctx = setup(custom_text_prompt="something")
    run("aiagent prompt set", cog, ctx, None, prompt=None)
    assert cog.config._guild.custom_text_prompt.value is None
    assert "no longer use a custom prompt" in ctx.replies_text()


def test_a_prompt_over_the_cap_is_refused_for_non_owners():
    cog, ctx = setup(max_prompt_length=10, is_owner=False)
    run("aiagent prompt set", cog, ctx, None, prompt="x" * 50)
    assert cog.config._guild.custom_text_prompt.value is None
    assert "too long" in ctx.replies_text()


def test_the_owner_may_exceed_the_cap():
    cog, ctx = setup(max_prompt_length=10, is_owner=True)
    run("aiagent prompt set", cog, ctx, None, prompt="x" * 50)
    assert cog.config._guild.custom_text_prompt.value == "x" * 50


def test_a_preset_name_expands_to_its_prompt():
    cog, ctx = setup(presets={"pirate": "you are a pirate"})
    run("aiagent prompt set", cog, ctx, None, prompt="pirate")
    assert cog.config._guild.custom_text_prompt.value == "you are a pirate"


def test_a_member_mention_targets_the_member_scope():
    cog, ctx = setup()
    member = fakes.Author(id=7)
    run("aiagent prompt set", cog, ctx, _member_mention(member), prompt="just for you")
    assert cog.config._member.custom_text_prompt.value == "just for you"
    assert cog.config._guild.custom_text_prompt.value is None


def _member_mention(member):
    """get_mention_type dispatches on isinstance, so use the real discord type."""
    import discord
    from unittest.mock import MagicMock

    mention = MagicMock(spec=discord.Member)
    mention.id = member.id
    mention.display_name = member.display_name
    return mention


def test_a_non_txt_attachment_is_refused():
    cog, ctx = setup()

    class Attachment:
        filename = "prompt.pdf"

        async def read(self):
            return b"nope"

    ctx.message.attachments = [Attachment()]
    run("aiagent prompt set", cog, ctx, None, prompt=None)
    assert "Must be a `.txt` file" in ctx.replies_text()


def test_a_txt_attachment_becomes_the_prompt():
    cog, ctx = setup()

    class Attachment:
        filename = "prompt.txt"

        async def read(self):
            return "from a file".encode()

    ctx.message.attachments = [Attachment()]
    run("aiagent prompt set", cog, ctx, None, prompt=None)
    assert cog.config._guild.custom_text_prompt.value == "from a file"


# --- presets ----------------------------------------------------------------

def stored_presets(cog):
    return json.loads(cog.config._guild.presets.value)


def test_a_preset_is_added():
    cog, ctx = setup()
    run("aiagent prompt preset add", cog, ctx, prompt="pirate|you are a pirate")
    assert stored_presets(cog) == {"pirate": "you are a pirate"}


def test_a_preset_without_a_separator_is_refused():
    cog, ctx = setup()
    run("aiagent prompt preset add", cog, ctx, prompt="no separator here")
    assert stored_presets(cog) == {}
    assert "Invalid format" in ctx.replies_text()


def test_a_duplicate_preset_name_is_refused():
    cog, ctx = setup(presets={"pirate": "arr"})
    run("aiagent prompt preset add", cog, ctx, prompt="pirate|different")
    assert stored_presets(cog) == {"pirate": "arr"}
    assert "already exists" in ctx.replies_text()


def test_a_preset_named_after_a_channel_is_refused():
    """`[p]aiagent prompt set #general` would otherwise be ambiguous."""
    cog, ctx = setup()
    channel = type("Channel", (), {"name": "general", "id": 200})()
    ctx.guild.channels = [channel]

    run("aiagent prompt preset add", cog, ctx, prompt="general|clashing name")

    assert stored_presets(cog) == {}
    assert "conflicts with the channel" in ctx.replies_text()


def test_an_over_long_preset_is_refused_for_non_owners():
    cog, ctx = setup(max_prompt_length=10, is_owner=False)
    run("aiagent prompt preset add", cog, ctx, prompt="name|" + "x" * 50)
    assert stored_presets(cog) == {}


def test_a_preset_is_removed():
    cog, ctx = setup(presets={"pirate": "arr", "formal": "be formal"})
    run("aiagent prompt preset remove", cog, ctx, "pirate")
    assert stored_presets(cog) == {"formal": "be formal"}


def test_removing_an_unknown_preset_is_refused():
    cog, ctx = setup(presets={"pirate": "arr"})
    run("aiagent prompt preset remove", cog, ctx, "nonexistent")
    assert stored_presets(cog) == {"pirate": "arr"}


def test_presets_are_listed():
    cog, ctx = setup(presets={"pirate": "you are a pirate"})
    run("aiagent prompt preset show", cog, ctx)
    assert "pirate" in ctx.replies_text()


def test_an_empty_preset_list_says_so():
    cog, ctx = setup()
    run("aiagent prompt preset show", cog, ctx)
    assert "No presets" in ctx.replies_text()


# --- showing ----------------------------------------------------------------

def test_showing_the_server_prompt_falls_back_to_the_default():
    cog, ctx = setup()
    run("aiagent prompt show", cog, ctx, None)
    assert "Discord" in ctx.replies_text()


def test_showing_a_set_server_prompt():
    cog, ctx = setup(custom_text_prompt="a custom persona")
    run("aiagent prompt show", cog, ctx, None)
    assert "a custom persona" in ctx.replies_text()


def test_embed_titles_name_the_scope():
    cog, _ctx = setup()
    for mention_type, expected in [
        (MentionType.USER, "user"),
        (MentionType.ROLE, "role"),
        (MentionType.SERVER, "server"),
    ]:
        entity = fakes.Author() if mention_type == MentionType.USER else fakes.Role()
        title = asyncio.run(cog._get_embed_title(mention_type, entity))
        assert expected in title.lower()
