import asyncio
import inspect

from aiagent.messages_list import messages as messages_module
from aiagent.messages_list.messages import MessagesList, create_messages_list


class FakeValue:
    def __init__(self, value):
        self.value = value

    async def __call__(self):
        return self.value


class CountingValue:
    """A config value that records how many times it was read."""

    def __init__(self, value):
        self.value = value
        self.reads = 0

    async def __call__(self):
        self.reads += 1
        return self.value


class FakeGuildConfig:
    def __init__(self, model, custom_limit):
        self.model = CountingValue(model)
        self.custom_model_tokens_limit = CountingValue(custom_limit)
        self.optin_by_default = CountingValue(False)


class FakeConfig:
    def __init__(self, model="unknown-model", custom_limit=None):
        self._guild = FakeGuildConfig(model, custom_limit)
        self.optin = CountingValue([])
        self.optout = CountingValue([])

    def guild(self, _guild):
        return self._guild


def build_list(monkeypatch, model="unknown-model", custom_limit=None):
    """A MessagesList with only the attributes _init touches, and recorded calls."""

    async def fake_format_variables(ctx, text):
        return f"formatted:{text}"

    monkeypatch.setattr(messages_module, "format_variables", fake_format_variables)

    calls = []
    messages = MessagesList.__new__(MessagesList)
    messages.config = FakeConfig(model, custom_limit)
    messages.guild = object()
    messages.ctx = object()
    messages.init_message = "TRIGGER"

    async def fake_add_msg(message):
        calls.append(("add_msg", message))

    async def fake_pick_prompt():
        return "PROMPT"

    async def fake_add_system(content):
        calls.append(("add_system", content))

    messages.add_msg = fake_add_msg
    messages._pick_prompt = fake_pick_prompt
    messages.add_system = fake_add_system

    return messages, calls


def test_init_adds_trigger_message_then_the_server_prompt(monkeypatch):
    messages, calls = build_list(monkeypatch)

    asyncio.run(messages._init())

    assert calls == [
        ("add_msg", "TRIGGER"),
        ("add_system", "formatted:PROMPT"),
    ]


def test_init_falls_back_to_the_estimated_token_limit(monkeypatch):
    messages, _ = build_list(monkeypatch, model="unknown-model", custom_limit=None)

    asyncio.run(messages._init())

    assert messages.model == "unknown-model"
    assert messages.token_limit == 7000


def test_init_prefers_a_configured_token_limit(monkeypatch):
    messages, _ = build_list(monkeypatch, custom_limit=12345)

    asyncio.run(messages._init())

    assert messages.token_limit == 12345


def test_consent_state_is_read_once_per_response(monkeypatch):
    """check_if_add used to re-read all three lists for every message considered."""
    messages, _ = build_list(monkeypatch)

    asyncio.run(messages._init())

    assert messages.config.optin.reads == 1
    assert messages.config.optout.reads == 1
    assert messages.config._guild.optin_by_default.reads == 1
    assert messages._optin == set()
    assert messages._optout == set()
    assert messages._optin_by_default is False


def test_create_messages_list_takes_only_cog_and_ctx():
    assert list(inspect.signature(create_messages_list).parameters) == ["cog", "ctx"]


def test_init_takes_no_arguments():
    assert list(inspect.signature(MessagesList._init).parameters) == ["self"]
