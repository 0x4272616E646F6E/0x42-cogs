import json
import logging
import random
from datetime import timedelta
from typing import Optional

import httpx
from discord.ext import commands
from openai import AsyncOpenAI
from redbot.core import Config
from redbot.core.bot import Red

logger = logging.getLogger("red.0x42_cogs.aibot")


async def setup_openai_client(
    bot: Red,
    config: Config,
    ctx: Optional[commands.Context] = None
) -> Optional[AsyncOpenAI]:
    """Initialize the OpenAI client with appropriate configuration.

    Args:
        bot: The Red bot instance
        config: The cog's Config instance
        ctx: Optional context for error messaging

    Returns:
        AsyncOpenAI client if successful, None otherwise
    """
    base_url = await config.custom_openai_endpoint()
    api_type = "openai"
    api_key = None
    headers = None

    if base_url:
        api_key = (await bot.get_shared_api_tokens("openai")).get("api_key")

    if not api_key:
        if ctx:
            error_message = (
                f"{api_type} API key not set for `aibot`. "
                f"Please set it with `{ctx.clean_prefix}set api {api_type} api_key,[API_KEY_HERE]`"
            )
            await ctx.send(error_message)
            return None
        else:
            logger.error(
                f'{api_type} API key not set for "aibot" yet! '
                f'Please set it with: [p]set api {api_type} api_key,[API_KEY_HERE]'
            )
            return None

    timeout = await config.openai_endpoint_request_timeout()
    client = httpx.AsyncClient(
        event_hooks={
            "request": [log_request_prompt],
            "response": [config]
        }
    )

    return AsyncOpenAI(
        api_key=api_key or "sk-placeholderkey",
        base_url=base_url,
        timeout=timeout,
        default_headers=headers,
        http_client=client
    )


async def log_request_prompt(request: httpx.Request) -> None:
    """Log the request prompt for debugging purposes."""
    if not logger.isEnabledFor(logging.DEBUG):
        return

    endpoint = request.url.path.split("/")[-1]
    if endpoint != "completions":
        return

    try:
        _bytes = await request.aread()
        request_data = json.loads(_bytes.decode('utf-8'))
        messages = request_data.get("messages", {})
        if not messages:
            return

        logger.debug(f"Sending request with prompt: \n{json.dumps(messages, indent=4)}")
    except Exception as e:
        logger.debug(f"Error logging request prompt: {e}")


def extract_time_delta(time_str: Optional[str]) -> timedelta:
    """Extract timedelta from OpenAI's ratelimit time format.

    Args:
        time_str: Time string in OpenAI format (e.g., "1d", "2h", "30m", "45s")

    Returns:
        timedelta object representing the time
    """
    if not time_str:
        return timedelta(seconds=5)

    days, hours, minutes, seconds = 0, 0, 0, 0

    if time_str.endswith("ms"):
        time_str = time_str[:-2]
        seconds += 1

    components = time_str.split("d")
    if len(components) > 1:
        days = float(components[0])
        time_str = components[1]

    components = time_str.split("h")
    if len(components) > 1:
        hours = float(components[0])
        time_str = components[1]

    components = time_str.split("m")
    if len(components) > 1:
        minutes = float(components[0])
        time_str = components[1]

    components = time_str.split("s")
    if len(components) > 1:
        seconds = float(components[0])

    seconds += random.randint(2, 3)

    return timedelta(
        days=days,
        hours=hours,
        minutes=minutes,
        seconds=seconds
    )
