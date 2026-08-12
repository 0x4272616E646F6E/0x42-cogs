"""Stand-ins for the Discord and Red objects the cog reaches for.

Small and explicit rather than mock-everything: each fake exposes only what the
code under test actually touches, so a test failing here means the cog changed
its expectations, not that a mock drifted.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import discord

from aiagent.core.throttle import ResponseThrottle

# Anchored at import rather than a fixed date: message age is now load-bearing
# (the response delay budget is derived from it), so a hardcoded timestamp would
# make every fake message look hours stale.
NOW = datetime.now(timezone.utc)


class Value:
    """A Red config value. Records reads and writes."""

    def __init__(self, value):
        self.value = value
        self.reads = 0
        self.writes = []

    async def __call__(self):
        self.reads += 1
        return self.value

    async def set(self, value):
        self.writes.append(value)
        self.value = value

    async def clear(self):
        self.writes.append(None)
        self.value = None


class Scope:
    """A config scope (guild/member/role/channel). Unknown keys read as None."""

    def __init__(self, **values):
        self._values = {name: Value(value) for name, value in values.items()}

    def __getattr__(self, name):
        values = self.__dict__.setdefault("_values", {})
        if name not in values:
            values[name] = Value(None)
        return values[name]

    async def get_raw(self):
        return {name: value.value for name, value in self._values.items()}

    async def clear(self):
        for value in self._values.values():
            await value.clear()


class Config:
    """Enough of redbot's Config for the paths under test."""

    def __init__(self, guild=None, member=None, role=None, channel=None, **globals_):
        self._guild = guild if guild is not None else Scope()
        self._member = member if member is not None else Scope()
        self._role = role if role is not None else Scope()
        self._channel = channel if channel is not None else Scope()
        self._globals = {name: Value(value) for name, value in globals_.items()}
        self._all_roles = {}
        self._all_members = {}

    def __getattr__(self, name):
        globals_ = self.__dict__.setdefault("_globals", {})
        if name not in globals_:
            globals_[name] = Value(None)
        return globals_[name]

    def guild(self, _guild):
        return self._guild

    def guild_from_id(self, _guild_id):
        return self._guild

    def member(self, _member):
        return self._member

    def member_from_ids(self, _guild_id, _member_id):
        return self._member

    def role(self, _role):
        return self._role

    def channel(self, _channel):
        return self._channel

    async def all_roles(self):
        return self._all_roles

    async def all_members(self, _guild=None):
        return self._all_members

    async def all_guilds(self):
        return {}


class Author:
    def __init__(self, id=42, name="brandon", bot=False, roles=()):
        self.id = id
        self.name = name
        self.display_name = name
        self.nick = name
        self.bot = bot
        self.roles = list(roles)
        self.mention = f"<@{id}>"
        self.top_role = self.roles[0] if self.roles else Role(id=0, name="@everyone")

    def __eq__(self, other):
        return isinstance(other, Author) and other.id == self.id

    def __hash__(self):
        return hash(self.id)


class Role:
    def __init__(self, id=500, name="members"):
        self.id = id
        self.name = name


def message(
    id=1,
    content="hello there",
    author=None,
    created_at=None,
    reference=None,
    embeds=(),
    guild=None,
):
    """A discord.Message stand-in that passes isinstance checks."""
    fake = MagicMock(spec=discord.Message)
    fake.id = id
    fake.content = content
    fake.author = author or Author()
    fake.created_at = created_at or NOW
    fake.reference = reference
    fake.embeds = list(embeds)
    fake.attachments = []
    fake.stickers = []
    fake.mentions = []
    fake.guild = guild or Guild()
    fake.type = discord.MessageType.default
    return fake


def reply_to(target):
    """A message reference whose resolved message is `target`."""
    reference = MagicMock()
    reference.resolved = target
    reference.channel_id = 200
    reference.message_id = target.id
    return reference


class Channel:
    def __init__(self, id=200, name="general", history_messages=(), topic="a channel"):
        self.id = id
        self.name = name
        self.topic = topic
        self.sent = []
        self._history = list(history_messages)

    def history(self, limit=None, before=None, after=None, oldest_first=None):
        messages = self._history[:limit] if limit else self._history

        async def iterator():
            for item in messages:
                yield item

        return iterator()

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class Guild:
    def __init__(self, id=100, name="Test Server", members=(), emojis=()):
        self.id = id
        self.name = name
        self.members = list(members)
        self.emojis = list(emojis)
        self.me = Author(id=1, name="Red")
        self.me.nick = "Red"


class Bot:
    def __init__(self, allowed=True, embed_color=0x00FF00):
        self.user = Author(id=1, name="Red")
        self._allowed = allowed
        self._embed_color = embed_color

    async def allowed_by_whitelist_blacklist(self, _who):
        return self._allowed

    async def cog_disabled_in_guild(self, _cog, _guild):
        return False

    async def ignored_channel_or_guild(self, _ctx):
        return True

    async def get_embed_color(self, _message):
        return self._embed_color

    async def is_owner(self, _user):
        return True

    def get_guild(self, _id):
        return Guild()


class Cog:
    """The attributes MessagesList and the settings mixins read off the cog."""

    def __init__(self, config=None, bot=None, **kwargs):
        self.config = config or Config()
        self.bot = bot or Bot()
        self.ignore_regex = kwargs.pop("ignore_regex", {})
        self.override_prompt_start_time = kwargs.pop("override_prompt_start_time", {})
        self.channels_whitelist = kwargs.pop("channels_whitelist", {})
        self.optindefault = kwargs.pop("optindefault", {})
        self.openai_client = kwargs.pop("openai_client", None)
        # a real throttle: the handlers depend on its behaviour, not just its shape
        self.throttle = kwargs.pop("throttle", None) or ResponseThrottle()


class Ctx:
    """A commands.Context stand-in that records what was sent back."""

    def __init__(self, cog=None, message_=None, channel=None, guild=None, author=None):
        self.guild = guild or Guild()
        self.channel = channel or Channel()
        self.author = author or Author()
        self.message = message_ or message(author=self.author, guild=self.guild)
        self.bot = cog.bot if cog else Bot()
        self.interaction = None
        self.clean_prefix = "!"
        self.me = self.guild.me
        self.sent = []
        self.reactions = []

    async def send(self, content=None, *, embed=None, **kwargs):
        self.sent.append(embed if embed is not None else content)
        return embed if embed is not None else content

    async def embed_color(self):
        return 0x00FF00

    async def react_quietly(self, emoji, message=None):
        self.reactions.append(emoji)

    async def tick(self):
        self.reactions.append("tick")

    def replies_text(self):
        """Everything sent back, flattened to searchable text."""
        text = []
        for item in self.sent:
            if isinstance(item, str):
                text.append(item)
            else:
                text.append(str(getattr(item, "title", "")))
                text.append(str(getattr(item, "description", "")))
                for field in getattr(item, "fields", []):
                    text.append(f"{field.name} {field.value}")
        return "\n".join(text)


def minutes_ago(count):
    return NOW - timedelta(minutes=count)
