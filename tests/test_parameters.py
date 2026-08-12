import asyncio

import pytest
from openai import AsyncOpenAI

from aiagent.response.chat.parameters import (
    SAMPLING_PARAMETERS,
    SDK_PARAMETERS,
    split_parameters,
)


def test_sdk_parameters_are_introspected():
    assert "temperature" in SDK_PARAMETERS
    assert "extra_body" in SDK_PARAMETERS
    assert "top_k" not in SDK_PARAMETERS
    assert "self" not in SDK_PARAMETERS


def test_declared_parameters_stay_native():
    assert split_parameters({"temperature": 0.8}) == {"temperature": 0.8}


def test_unknown_parameters_are_routed_to_extra_body():
    assert split_parameters({"top_k": 40, "repetition_penalty": 1.1}) == {
        "extra_body": {"top_k": 40, "repetition_penalty": 1.1}
    }


def test_mixed_parameters_are_split():
    assert split_parameters({"temperature": 0.8, "top_k": 40}) == {
        "temperature": 0.8,
        "extra_body": {"top_k": 40},
    }


def test_explicit_extra_body_is_merged_and_wins():
    result = split_parameters({"top_k": 40, "extra_body": {"min_p": 0.05, "top_k": 20}})
    assert result == {"extra_body": {"top_k": 20, "min_p": 0.05}}


def test_no_extra_body_key_when_everything_is_declared():
    assert split_parameters({"temperature": 0.5, "seed": 7}) == {
        "temperature": 0.5,
        "seed": 7,
    }


def test_empty_parameters():
    assert split_parameters({}) == {}


def test_routed_parameters_reach_the_server(fake_llm_server):
    base_url, bodies = fake_llm_server

    async def send():
        client = AsyncOpenAI(api_key="test", base_url=base_url, max_retries=0)
        await client.chat.completions.create(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            **split_parameters(
                {"temperature": 0.8, "top_k": 40, "repetition_penalty": 1.1}
            ),
        )
        await client.close()

    asyncio.run(send())

    body = bodies[-1]
    assert body["temperature"] == 0.8
    assert body["top_k"] == 40
    assert body["repetition_penalty"] == 1.1
    assert "extra_body" not in body


@pytest.mark.parametrize(
    "value,is_valid",
    [(0.0, True), (1.0, True), (2.0, True), (-0.1, False), (2.1, False)],
)
def test_temperature_range(value, is_valid):
    assert (SAMPLING_PARAMETERS["temperature"].validate(value) is None) is is_valid


@pytest.mark.parametrize(
    "value,is_valid", [(0, True), (40, True), (-1, False), (1.5, False)]
)
def test_top_k_range(value, is_valid):
    assert (SAMPLING_PARAMETERS["top_k"].validate(value) is None) is is_valid


@pytest.mark.parametrize(
    "value,is_valid", [(0.0, False), (1.0, True), (2.0, True), (2.5, False)]
)
def test_repetition_penalty_range(value, is_valid):
    assert (SAMPLING_PARAMETERS["repetition_penalty"].validate(value) is None) is is_valid


def test_validation_error_names_the_range():
    message = SAMPLING_PARAMETERS["temperature"].validate(9.0)
    assert "2" in message and "temperature" in message


def test_sampling_commands_are_registered():
    from aiagent.core.aiagent import AIAgent

    names = {command.qualified_name for command in AIAgent.__cog_commands__}
    assert "aiagent response temperature" in names
    assert "aiagent response top_k" in names
    assert "aiagent response repetitionpenalty" in names
    assert "aiagent response sampling" in names


def test_clearing_a_parameter_removes_it():
    """A value of None drops the key, and an emptied blob is stored as None."""
    import json

    from aiagent.settings.response import ResponseSettings

    class RecordingValue:
        def __init__(self, value):
            self.value = value

        async def __call__(self):
            return self.value

        async def set(self, value):
            self.value = value

    class RecordingGuildConfig:
        def __init__(self, parameters):
            self.parameters = RecordingValue(parameters)

    class RecordingConfig:
        def __init__(self, parameters):
            self._guild = RecordingGuildConfig(parameters)

        def guild(self, _guild):
            return self._guild

    class Holder:
        def __init__(self, parameters):
            self.config = RecordingConfig(parameters)

    class Ctx:
        guild = object()

    holder = Holder(json.dumps({"temperature": 0.8, "top_k": 40}))
    asyncio.run(ResponseSettings._store_parameter(holder, Ctx(), "top_k", None))
    assert json.loads(holder.config._guild.parameters.value) == {"temperature": 0.8}

    asyncio.run(ResponseSettings._store_parameter(holder, Ctx(), "temperature", None))
    assert holder.config._guild.parameters.value is None
