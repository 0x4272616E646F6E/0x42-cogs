"""The gate that decides whose messages reach the LLM.

This is the cog's consent boundary: a bug here sends the words of someone who
never opted in to the bot owner's server. Everything below asserts a refusal.
"""

import asyncio
import re

import pytest

from aiagent.core import validators


class FakeValue:
    def __init__(self, value):
        self.value = value

    async def __call__(self):
        return self.value


class FakeGuildConfig:
    def __init__(self, roles_whitelist, members_whitelist, min_length):
        self.roles_whitelist = FakeValue(roles_whitelist)
        self.members_whitelist = FakeValue(members_whitelist)
        self.messages_min_length = FakeValue(min_length)


class FakeConfig:
    def __init__(self, optin, optout, roles_whitelist, members_whitelist, min_length):
        self.optin = FakeValue(optin)
        self.optout = FakeValue(optout)
        self._guild = FakeGuildConfig(roles_whitelist, members_whitelist, min_length)

    def guild(self, _guild):
        return self._guild


class FakeBot:
    def __init__(self, allowed=True, cog_disabled=False, ignored=False):
        self._allowed = allowed
        self._cog_disabled = cog_disabled
        self._ignored = ignored
        self.user = FakeAuthor(id=1)

    async def allowed_by_whitelist_blacklist(self, _who):
        return self._allowed

    async def cog_disabled_in_guild(self, _cog, _guild):
        return self._cog_disabled

    async def ignored_channel_or_guild(self, _ctx):
        return not self._ignored


class FakeGuild:
    id = 100


class FakeChannel:
    id = 200


class FakeRole:
    def __init__(self, id):
        self.id = id


class FakeAuthor:
    def __init__(self, id=42, bot=False, roles=()):
        self.id = id
        self.bot = bot
        self.roles = list(roles)


class FakeMessage:
    def __init__(self, content="hello there", author=None):
        self.content = content
        self.author = author or FakeAuthor()
        self.mentions = []
        self.reference = None
        self.guild = FakeGuild()


class FakeCtx:
    def __init__(self, message=None, interaction=None):
        self.guild = FakeGuild()
        self.channel = FakeChannel()
        self.message = message or FakeMessage()
        self.author = self.message.author
        self.interaction = interaction


class FakeCog:
    def __init__(self, **kwargs):
        self.bot = kwargs.pop("bot", None) or FakeBot()
        self.config = FakeConfig(
            optin=kwargs.pop("optin", [42]),
            optout=kwargs.pop("optout", []),
            roles_whitelist=kwargs.pop("roles_whitelist", []),
            members_whitelist=kwargs.pop("members_whitelist", []),
            min_length=kwargs.pop("min_length", 2),
        )
        self.optindefault = kwargs.pop("optindefault", {})
        self.channels_whitelist = kwargs.pop("channels_whitelist", {100: [200]})
        self.ignore_regex = kwargs.pop("ignore_regex", {})
        self.openai_client = kwargs.pop("openai_client", object())


def valid(cog, ctx):
    return asyncio.run(validators.is_valid_message(cog, ctx))


# --- the happy path, so the refusals below mean something -------------------

def test_opted_in_user_in_a_whitelisted_channel_passes():
    assert valid(FakeCog(), FakeCtx()) is True


# --- consent ----------------------------------------------------------------

def test_user_who_never_opted_in_is_refused():
    assert valid(FakeCog(optin=[]), FakeCtx()) is False


def test_opted_out_user_is_refused_even_if_also_opted_in():
    """opt-out must win; the lists are edited independently."""
    assert valid(FakeCog(optin=[42], optout=[42]), FakeCtx()) is False


def test_opt_in_by_default_admits_the_server():
    assert valid(FakeCog(optin=[], optindefault={100: True}), FakeCtx()) is True


def test_opt_in_by_default_for_another_server_does_not_leak():
    assert valid(FakeCog(optin=[], optindefault={999: True}), FakeCtx()) is False


def test_bots_are_refused():
    message = FakeMessage(author=FakeAuthor(id=42, bot=True))
    assert valid(FakeCog(), FakeCtx(message=message)) is False


def test_reds_own_blocklist_is_respected():
    assert valid(FakeCog(bot=FakeBot(allowed=False)), FakeCtx()) is False


# --- where the bot is allowed to speak --------------------------------------

def test_channel_not_on_the_whitelist_is_refused():
    assert valid(FakeCog(channels_whitelist={100: [999]}), FakeCtx()) is False


def test_empty_whitelist_means_the_bot_is_silent():
    assert valid(FakeCog(channels_whitelist={}), FakeCtx()) is False


def test_cog_disabled_in_guild_is_respected():
    assert valid(FakeCog(bot=FakeBot(cog_disabled=True)), FakeCtx()) is False


def test_ignored_channel_is_respected():
    assert valid(FakeCog(bot=FakeBot(ignored=True)), FakeCtx()) is False


# --- role and member whitelist ----------------------------------------------

def test_member_whitelist_admits_only_listed_members():
    assert valid(FakeCog(members_whitelist=[42]), FakeCtx()) is True
    assert valid(FakeCog(members_whitelist=[7]), FakeCtx()) is False


def test_role_whitelist_admits_by_role():
    message = FakeMessage(author=FakeAuthor(id=42, roles=[FakeRole(500)]))
    assert valid(FakeCog(roles_whitelist=[500]), FakeCtx(message=message)) is True
    assert valid(FakeCog(roles_whitelist=[501]), FakeCtx(message=message)) is False


# --- message content --------------------------------------------------------

def test_message_below_the_minimum_length_is_refused():
    ctx = FakeCtx(message=FakeMessage(content="a"))
    assert valid(FakeCog(min_length=5), ctx) is False


def test_ignore_regex_refuses_the_message():
    cog = FakeCog(ignore_regex={100: re.compile(r"^!")})
    assert valid(cog, FakeCtx(message=FakeMessage(content="!ignore me"))) is False


def test_ignore_regex_for_another_guild_does_not_apply():
    cog = FakeCog(ignore_regex={999: re.compile(r"^!")})
    assert valid(cog, FakeCtx(message=FakeMessage(content="!ignore me"))) is True


# --- infrastructure ---------------------------------------------------------

def test_no_llm_client_refuses_rather_than_raising(monkeypatch):
    async def no_client(_bot, _config):
        return None

    monkeypatch.setattr(validators, "setup_llm_client", no_client)
    assert valid(FakeCog(openai_client=None), FakeCtx()) is False


def test_a_raising_check_refuses_rather_than_propagating(monkeypatch):
    async def explode(_cog, _ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(validators, "check_user_status", explode)
    assert valid(FakeCog(), FakeCtx()) is False


@pytest.mark.parametrize(
    "factory",
    [
        lambda: FakeCog(optin=[]),
        lambda: FakeCog(optout=[42]),
        lambda: FakeCog(channels_whitelist={}),
    ],
)
def test_every_refusal_is_silent(factory):
    """A refusal must never raise: handle_message has no error path for it."""
    assert valid(factory(), FakeCtx()) is False
