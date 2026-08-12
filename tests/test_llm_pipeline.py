import asyncio
import json

from openai import AsyncOpenAI

from aiagent.response.chat.llm_pipeline import LLMPipeline


class FakeValue:
    def __init__(self, value):
        self.value = value

    async def __call__(self):
        return self.value


class FakeGuildConfig:
    def __init__(self, parameters):
        self.parameters = FakeValue(parameters)


class FakeConfig:
    def __init__(self, parameters=None):
        self._guild = FakeGuildConfig(parameters)

    def guild(self, _guild):
        return self._guild


class FakeGuild:
    name = "TestGuild"


class FakeCtx:
    guild = FakeGuild()

    def __init__(self):
        self.reactions = []
        self.reaction_messages = []

    async def react_quietly(self, emoji, message=None):
        self.reactions.append(emoji)
        self.reaction_messages.append(message or "")


class FakeMessages:
    def __init__(self, model="test-model"):
        self.model = model
        self.can_reply = True

    def get_json(self):
        return [{"role": "user", "content": "hi"}]


class FakeCog:
    def __init__(self, config, client):
        self.config = config
        self.bot = None
        self.openai_client = client


def run_pipeline(base_url, parameters, model="test-model"):
    config = FakeConfig(parameters)
    ctx = FakeCtx()

    async def go():
        client = AsyncOpenAI(api_key="test", base_url=base_url, max_retries=0)
        pipeline = LLMPipeline(FakeCog(config, client), ctx, FakeMessages(model))
        result = await pipeline.run()
        await client.close()
        return result

    return asyncio.run(go()), ctx


def test_sampling_parameters_reach_the_server(fake_llm_server):
    base_url, bodies = fake_llm_server
    parameters = json.dumps(
        {"temperature": 0.8, "top_k": 40, "repetition_penalty": 1.1}
    )

    result, ctx = run_pipeline(base_url, parameters)

    assert result == "ok"
    body = bodies[-1]
    assert body["temperature"] == 0.8
    assert body["top_k"] == 40
    assert body["repetition_penalty"] == 1.1
    assert ctx.reactions == []


def test_reserved_parameters_are_stripped(fake_llm_server):
    base_url, bodies = fake_llm_server
    parameters = json.dumps(
        {"model": "hacked", "messages": [], "stream": True, "top_k": 5}
    )

    run_pipeline(base_url, parameters)

    body = bodies[-1]
    assert body["model"] == "test-model"
    assert len(body["messages"]) == 1
    assert "stream" not in body
    assert body["top_k"] == 5


def test_no_parameters_sends_no_extras(fake_llm_server):
    base_url, bodies = fake_llm_server

    run_pipeline(base_url, None)

    assert set(bodies[-1]) == {"model", "messages"}


def test_a_rejected_parameter_is_reported_as_such(fake_llm_server):
    """A 400 means the server refused a parameter, not that the bot broke.

    This used to land in the generic handler, which told the user nothing.
    """
    fake_llm_server.status = 400

    result, ctx = run_pipeline(fake_llm_server.url, json.dumps({"top_k": 40}))

    assert result is None
    assert ctx.reactions == ["\u26a0\ufe0f"]
    assert "custom parameters" in ctx.reaction_messages[0]


def test_a_rejected_parameter_is_distinguished_from_a_missing_model(fake_llm_server):
    """Both react with a warning, so the fallback text has to say which happened."""
    fake_llm_server.status = 400
    _result, rejected = run_pipeline(fake_llm_server.url, None)

    fake_llm_server.status = 404
    _result, missing = run_pipeline(fake_llm_server.url, None)

    assert rejected.reaction_messages[0] != missing.reaction_messages[0]
    assert "model not found" in missing.reaction_messages[0]


def test_a_server_error_still_produces_no_response(fake_llm_server):
    fake_llm_server.status = 500
    result, ctx = run_pipeline(fake_llm_server.url, None)

    assert result is None
    assert ctx.reactions == ["\u26a0\ufe0f"]
