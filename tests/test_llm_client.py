"""How the cog connects to an LLM server, and what it sends with the request."""

import asyncio

import pytest

from aiagent.config.models import get_model_tokens_limit
from aiagent.core.llm_client import PLACEHOLDER_API_KEY, setup_llm_client, validate_endpoint


class FakeBot:
    """Stands in for Red. The API key is optional and unset by default."""

    def __init__(self, api_key=None):
        self._tokens = {"api_key": api_key} if api_key else {}

    async def get_shared_api_tokens(self, _service):
        return self._tokens


class FakeConfig:
    def __init__(self, endpoint, timeout=30):
        self._endpoint = endpoint
        self._timeout = timeout

    def llm_endpoint(self):
        async def get():
            return self._endpoint
        return get()

    def llm_endpoint_request_timeout(self):
        async def get():
            return self._timeout
        return get()


def build_client(endpoint, api_key=None):
    return asyncio.run(
        setup_llm_client(bot=FakeBot(api_key), config=FakeConfig(endpoint))
    )


# --- endpoint validation ----------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://192.168.1.50:8080/v1",
        "https://llm.example.com/v1",
        "https://api.openai.com/v1",  # any OpenAI-compatible URL is allowed
    ],
)
def test_usable_endpoints_are_accepted(url):
    assert validate_endpoint(url) is None


@pytest.mark.parametrize("url", ["", "ftp://localhost/v1", "http:///v1", "localhost:11434"])
def test_unusable_endpoints_are_rejected(url):
    assert validate_endpoint(url) is not None


# --- client construction ----------------------------------------------------

def test_no_client_without_an_endpoint():
    assert build_client("") is None


def test_client_is_built_without_any_api_key():
    client = build_client("http://localhost:11434/v1")
    assert client is not None
    assert client.api_key == PLACEHOLDER_API_KEY
    asyncio.run(client.close())


def test_configured_api_key_is_used():
    client = build_client("http://localhost:11434/v1", api_key="secret-123")
    assert client.api_key == "secret-123"
    asyncio.run(client.close())


def test_retries_are_disabled():
    """Red already rate-limits commands; silent retries would double a slow local run."""
    client = build_client("http://localhost:11434/v1")
    assert client.max_retries == 0
    asyncio.run(client.close())


# --- what actually goes over the wire ---------------------------------------

def test_request_carries_the_placeholder_key_and_reaches_the_right_path(fake_llm_server):
    base_url, _bodies = fake_llm_server

    async def send():
        client = await setup_llm_client(bot=FakeBot(), config=FakeConfig(base_url))
        await client.chat.completions.create(
            model="test-model", messages=[{"role": "user", "content": "hi"}]
        )
        await client.close()

    asyncio.run(send())


def test_models_are_listed_from_the_endpoint(fake_llm_server):
    base_url, _ = fake_llm_server

    async def listing():
        client = await setup_llm_client(bot=FakeBot(), config=FakeConfig(base_url))
        models = await client.models.list()
        await client.close()
        return sorted(model.id for model in models.data)

    assert asyncio.run(listing()) == ["gpt-oss:20b", "qwen3:8b"]


# --- context window estimates ------------------------------------------------

@pytest.mark.parametrize(
    "model,expected",
    [
        ("qwen3:8b", 39000),
        ("llama-3.1:70b", 123000),
        ("hf.co/x/mistral-7b:Q4", 31000),
        ("mymodel-32k", 31000),
        ("some-weird-model", 7000),
        ("", 7000),
    ],
)
def test_context_window_estimates(model, expected):
    assert get_model_tokens_limit(model) == expected


def test_longest_matching_prefix_wins():
    """llama-3.1 has a far larger window than llama-3; the table must not confuse them."""
    assert get_model_tokens_limit("llama-3.1:8b") > get_model_tokens_limit("llama-3:8b")
