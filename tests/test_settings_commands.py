"""The settings commands, driven through their callbacks.

`Command.callback` is the undecorated coroutine, so these exercise the real
command bodies — validation, guards and the config writes they perform — without
needing a live bot. Permission gating is covered separately in test_permissions.
"""

import asyncio
import json

import pytest

from aiagent.core.aiagent import AIAgent
from aiagent.core.throttle import ResponseThrottle

from . import fakes

COMMANDS = {command.qualified_name: command for command in AIAgent.__cog_commands__}


def run(name, cog, ctx, *args, **kwargs):
    """Invoke a command body the way discord.py would."""
    return asyncio.run(COMMANDS[name].callback(cog, ctx, *args, **kwargs))


def setup(**guild_settings):
    settings = {
        "channels_whitelist": [],
        "parameters": None,
        "removelist_regexes": [],
        "messages_backread": 10,
        "messages_backread_seconds": 3600,
        "custom_model_tokens_limit": None,
        "messages_min_length": 2,
        "ignore_regex": None,
        "public_forget": False,
        "optin_by_default": False,
        "optin_disable_embed": False,
        "model": "qwen3:8b",
        "roles_whitelist": [],
        "members_whitelist": [],
    }
    settings.update(guild_settings)
    config = fakes.Config(
        guild=fakes.Scope(**settings),
        optin=[],
        optout=[],
        llm_endpoint="http://localhost:11434/v1",
        llm_endpoint_request_timeout=60,
        max_prompt_length=200,
        endpoint_model_history={},
    )
    # A real AIAgent, with the attributes __init__ would set. Using the real class
    # means the command bodies reach their real helper methods.
    cog = AIAgent.__new__(AIAgent)
    cog.config = config
    cog.bot = fakes.Bot()
    cog.ignore_regex = {}
    cog.channels_whitelist = {}
    cog.optindefault = {}
    cog.override_prompt_start_time = {}
    cog.openai_client = None
    cog.throttle = ResponseThrottle()
    return cog, fakes.Ctx(cog=cog)


def guild_value(cog, key):
    return getattr(cog.config._guild, key).value


# --- channel whitelist ------------------------------------------------------

class FakeTextChannel:
    def __init__(self, id=200):
        self.id = id


def test_adding_a_channel_stores_it_and_updates_the_cache():
    cog, ctx = setup()
    channel = FakeTextChannel()

    run("aiagent add", cog, ctx, channel)

    assert guild_value(cog, "channels_whitelist") == [200]
    # the runtime cache is what the message handler reads
    assert cog.channels_whitelist[ctx.guild.id] == [200]


def test_adding_the_same_channel_twice_is_refused():
    cog, ctx = setup(channels_whitelist=[200])
    run("aiagent add", cog, ctx, FakeTextChannel())
    assert "already in whitelist" in ctx.replies_text()


def test_removing_a_channel_updates_both_store_and_cache():
    cog, ctx = setup(channels_whitelist=[200])
    run("aiagent remove", cog, ctx, FakeTextChannel())
    assert guild_value(cog, "channels_whitelist") == []
    assert cog.channels_whitelist[ctx.guild.id] == []


def test_removing_a_channel_that_is_not_whitelisted_is_refused():
    cog, ctx = setup(channels_whitelist=[])
    run("aiagent remove", cog, ctx, FakeTextChannel())
    assert "not in whitelist" in ctx.replies_text()


# --- opt in / opt out -------------------------------------------------------

def test_opting_in_adds_the_user():
    cog, ctx = setup()
    run("aiagent optin", cog, ctx)
    assert ctx.author.id in cog.config.optin.value


def test_opting_in_twice_says_so():
    cog, ctx = setup()
    cog.config.optin.value = [42]
    run("aiagent optin", cog, ctx)
    assert "already opted in" in ctx.replies_text()


def test_opting_out_removes_a_previous_opt_in():
    """The two lists must not disagree about the same user."""
    cog, ctx = setup()
    cog.config.optin.value = [42]
    run("aiagent optout", cog, ctx)
    assert 42 not in cog.config.optin.value
    assert 42 in cog.config.optout.value


def test_opting_in_removes_a_previous_opt_out():
    cog, ctx = setup()
    cog.config.optout.value = [42]
    run("aiagent optin", cog, ctx)
    assert 42 not in cog.config.optout.value
    assert 42 in cog.config.optin.value


def test_opt_in_by_default_is_refused_for_large_servers():
    """Consent by default stops being meaningful at scale."""
    cog, ctx = setup()
    ctx.guild.members = [fakes.Author(id=i) for i in range(151)]
    run("aiagent optinbydefault", cog, ctx)
    assert "cannot enable" in ctx.replies_text().lower()
    assert guild_value(cog, "optin_by_default") is False


def test_opt_in_by_default_toggles_for_small_servers():
    cog, ctx = setup()
    ctx.guild.members = [fakes.Author(id=i) for i in range(10)]
    run("aiagent optinbydefault", cog, ctx)
    assert guild_value(cog, "optin_by_default") is True
    assert cog.optindefault[ctx.guild.id] is True


# --- sampling parameters ----------------------------------------------------

def stored_parameters(cog):
    raw = guild_value(cog, "parameters")
    return json.loads(raw) if raw else {}


def test_temperature_is_stored():
    cog, ctx = setup()
    run("aiagent response temperature", cog, ctx, 0.8)
    assert stored_parameters(cog) == {"temperature": 0.8}


def test_temperature_out_of_range_is_refused():
    cog, ctx = setup()
    run("aiagent response temperature", cog, ctx, 9.0)
    assert stored_parameters(cog) == {}
    assert "must be" in ctx.replies_text()


def test_top_k_is_stored_as_an_integer():
    cog, ctx = setup()
    run("aiagent response top_k", cog, ctx, 40)
    assert stored_parameters(cog) == {"top_k": 40}


def test_negative_top_k_is_refused():
    cog, ctx = setup()
    run("aiagent response top_k", cog, ctx, -1)
    assert stored_parameters(cog) == {}


def test_repetition_penalty_is_stored_under_the_vllm_spelling():
    cog, ctx = setup()
    run("aiagent response repetitionpenalty", cog, ctx, 1.1)
    assert stored_parameters(cog) == {"repetition_penalty": 1.1}


def test_zero_repetition_penalty_is_refused():
    """The minimum is exclusive: 0 would divide by zero on most backends."""
    cog, ctx = setup()
    run("aiagent response repetitionpenalty", cog, ctx, 0.0)
    assert stored_parameters(cog) == {}


def test_omitting_the_value_clears_the_parameter():
    cog, ctx = setup(parameters=json.dumps({"temperature": 0.8, "top_k": 40}))
    run("aiagent response temperature", cog, ctx, None)
    assert stored_parameters(cog) == {"top_k": 40}


def test_clearing_the_last_parameter_stores_nothing_rather_than_empty_json():
    cog, ctx = setup(parameters=json.dumps({"temperature": 0.8}))
    run("aiagent response temperature", cog, ctx, None)
    assert guild_value(cog, "parameters") is None


def test_sampling_summary_lists_the_knobs():
    cog, ctx = setup(parameters=json.dumps({"temperature": 0.8, "min_p": 0.05}))
    run("aiagent response sampling", cog, ctx)
    text = ctx.replies_text()
    assert "Temperature" in text and "0.8" in text
    assert "min_p" in text  # unrecognised keys are still surfaced


# --- raw parameters ---------------------------------------------------------

def test_reserved_parameters_are_rejected():
    cog, ctx = setup()
    run("aiagent response parameters", cog, ctx, json_block='```{"model": "other"}```')
    assert "Invalid JSON" in ctx.replies_text()
    assert guild_value(cog, "parameters") is None


def test_malformed_json_is_rejected():
    cog, ctx = setup()
    run("aiagent response parameters", cog, ctx, json_block="```{not json}```")
    assert "Invalid JSON" in ctx.replies_text()


def test_parameters_without_a_code_block_are_rejected():
    cog, ctx = setup()
    run("aiagent response parameters", cog, ctx, json_block='{"temperature": 0.5}')
    assert "code block" in ctx.replies_text()


def test_parameters_reset_clears_the_blob():
    cog, ctx = setup(parameters=json.dumps({"temperature": 0.5}))
    run("aiagent response parameters", cog, ctx, json_block="reset")
    assert guild_value(cog, "parameters") is None


def test_valid_parameters_are_stored():
    cog, ctx = setup()
    run("aiagent response parameters", cog, ctx, json_block='```{"min_p": 0.05}```')
    assert stored_parameters(cog) == {"min_p": 0.05}


# --- removelist and ignore regex --------------------------------------------

def test_a_removelist_pattern_is_stored():
    cog, ctx = setup()
    run("aiagent response removelist add", cog, ctx, regex_pattern=r"^spoiler:")
    assert guild_value(cog, "removelist_regexes") == [r"^spoiler:"]


def test_a_catastrophic_removelist_pattern_is_refused():
    cog, ctx = setup()
    run("aiagent response removelist add", cog, ctx, regex_pattern=r"(a+)+$")
    assert guild_value(cog, "removelist_regexes") == []
    assert "exponential" in ctx.replies_text()


def test_removing_a_removelist_pattern_by_number():
    cog, ctx = setup(removelist_regexes=[r"one", r"two"])
    run("aiagent response removelist remove", cog, ctx, number=1)
    assert guild_value(cog, "removelist_regexes") == [r"two"]


def test_an_out_of_range_removelist_number_is_refused():
    cog, ctx = setup(removelist_regexes=[r"one"])
    run("aiagent response removelist remove", cog, ctx, number=5)
    assert "Invalid number" in ctx.replies_text()


def test_an_ignore_regex_is_compiled_into_the_cache():
    cog, ctx = setup()
    run("aiagent trigger ignore", cog, ctx, regex_pattern=r"^!")
    assert guild_value(cog, "ignore_regex") == r"^!"
    assert cog.ignore_regex[ctx.guild.id].pattern == r"^!"


def test_a_catastrophic_ignore_regex_is_refused():
    cog, ctx = setup()
    run("aiagent trigger ignore", cog, ctx, regex_pattern=r"([a-z]+)*$")
    assert guild_value(cog, "ignore_regex") is None
    assert ctx.guild.id not in cog.ignore_regex


def test_an_invalid_ignore_regex_is_refused():
    cog, ctx = setup()
    run("aiagent trigger ignore", cog, ctx, regex_pattern=r"(unclosed")
    assert guild_value(cog, "ignore_regex") is None


def test_clearing_the_ignore_regex():
    cog, ctx = setup(ignore_regex=r"^!")
    run("aiagent trigger ignore", cog, ctx, regex_pattern=None)
    assert guild_value(cog, "ignore_regex") is None
    assert cog.ignore_regex[ctx.guild.id] is None


# --- history ----------------------------------------------------------------

def test_backread_is_stored():
    cog, ctx = setup()
    run("aiagent history backread", cog, ctx, 25)
    assert guild_value(cog, "messages_backread") == 25


def test_history_time_is_stored():
    cog, ctx = setup()
    run("aiagent history time", cog, ctx, 120)
    assert guild_value(cog, "messages_backread_seconds") == 120


def test_custom_token_limit_is_stored_and_clearable():
    cog, ctx = setup()
    run("aiagent history customtokenlimit", cog, ctx, 32000)
    assert guild_value(cog, "custom_model_tokens_limit") == 32000
    run("aiagent history customtokenlimit", cog, ctx, None)
    assert guild_value(cog, "custom_model_tokens_limit") is None


# --- triggers ---------------------------------------------------------------

def test_minimum_length_is_stored():
    cog, ctx = setup()
    run("aiagent trigger minlength", cog, ctx, 15)
    assert guild_value(cog, "messages_min_length") == 15


def test_public_forget_toggles():
    cog, ctx = setup(public_forget=False)
    run("aiagent trigger public_forget", cog, ctx)
    assert guild_value(cog, "public_forget") is True


# --- owner settings ---------------------------------------------------------

def test_timeout_must_be_positive(monkeypatch):
    cog, ctx = setup()
    run("aiagentowner timeout", cog, ctx, 0)
    assert "positive integer" in ctx.replies_text()
    assert cog.config.llm_endpoint_request_timeout.value == 60


def test_timeout_is_stored_and_rebuilds_the_client(monkeypatch):
    rebuilt = []

    async def fake_setup(bot, config):
        rebuilt.append(True)
        return object()

    monkeypatch.setattr("aiagent.settings.owner.setup_llm_client", fake_setup)
    cog, ctx = setup()
    run("aiagentowner timeout", cog, ctx, 180)

    assert cog.config.llm_endpoint_request_timeout.value == 180
    assert rebuilt == [True]


def test_max_prompt_length_must_be_positive():
    cog, ctx = setup()
    run("aiagentowner maxpromptlength", cog, ctx, 0)
    assert "positive integer" in ctx.replies_text()


def test_endpoint_shows_the_current_value_when_called_bare():
    cog, ctx = setup()
    run("aiagentowner endpoint", cog, ctx, None)
    assert "localhost" in ctx.replies_text()


def test_an_unusable_endpoint_is_refused_before_anything_is_stored():
    cog, ctx = setup()
    run("aiagentowner endpoint", cog, ctx, "ftp://nope")
    assert cog.config.llm_endpoint.value == "http://localhost:11434/v1"


def test_an_unreachable_endpoint_is_rolled_back(monkeypatch):
    """The endpoint is probed before it is kept; a dead one must not strand the bot."""
    class DeadClient:
        class models:
            @staticmethod
            async def list():
                raise ConnectionError("nothing listening")

    async def fake_setup(bot, config):
        return DeadClient()

    monkeypatch.setattr("aiagent.settings.owner.setup_llm_client", fake_setup)

    cog, ctx = setup()
    ctx.message.add_reaction = _noop
    ctx.message.remove_reaction = _noop

    run("aiagentowner endpoint", cog, ctx, "http://192.168.1.99:9999/v1")

    assert cog.config.llm_endpoint.value == "http://localhost:11434/v1"
    assert "Could not reach" in ctx.replies_text()


async def _noop(*args, **kwargs):
    return None


# --- model ------------------------------------------------------------------

def test_model_command_refuses_when_there_is_no_client():
    cog, ctx = setup()
    cog.openai_client = None
    run("aiagent model", cog, ctx, "qwen3:8b")
    assert "No LLM endpoint" in ctx.replies_text()


def test_model_must_be_one_the_server_serves(monkeypatch):
    async def available(_client):
        return ["qwen3:8b"]

    monkeypatch.setattr("aiagent.settings.base.get_available_models", available)
    cog, ctx = setup()
    cog.openai_client = object()
    ctx.message.add_reaction = _noop
    ctx.message.remove_reaction = _noop

    run("aiagent model", cog, ctx, "gpt-4o")

    assert "Not a valid model" in ctx.replies_text()
    assert guild_value(cog, "model") == "qwen3:8b"


def test_a_served_model_is_stored(monkeypatch):
    async def available(_client):
        return ["qwen3:8b", "gpt-oss:20b"]

    monkeypatch.setattr("aiagent.settings.base.get_available_models", available)
    cog, ctx = setup()
    cog.openai_client = object()
    ctx.message.add_reaction = _noop
    ctx.message.remove_reaction = _noop

    run("aiagent model", cog, ctx, "gpt-oss:20b")

    assert guild_value(cog, "model") == "gpt-oss:20b"


# --- forget -----------------------------------------------------------------

class Permissions:
    def __init__(self, manage_messages):
        self.manage_messages = manage_messages


class PermissionChannel(fakes.Channel):
    def __init__(self, manage_messages):
        super().__init__()
        self._permissions = Permissions(manage_messages)

    def permissions_for(self, _member):
        return self._permissions


@pytest.mark.parametrize(
    "manage_messages,public_forget,expected",
    [(True, False, "✅"), (False, False, "❌"), (False, True, "✅")],
)
def test_forget_permission_matrix(manage_messages, public_forget, expected):
    cog, ctx = setup(public_forget=public_forget)
    ctx.channel = PermissionChannel(manage_messages)

    run("aiagent forget", cog, ctx)

    assert ctx.reactions == [expected]


def test_forget_records_a_cutoff_time():
    cog, ctx = setup(public_forget=True)
    ctx.channel = PermissionChannel(manage_messages=False)

    run("aiagent forget", cog, ctx)

    assert cog.override_prompt_start_time[ctx.guild.id] == ctx.message.created_at
