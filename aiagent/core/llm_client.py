import json
import logging
from typing import Optional
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI
from redbot.core import Config
from redbot.core.bot import Red

logger = logging.getLogger("red.0x42_cogs.aiagent")

# Most self-hosted servers ignore it, but the openai library requires *something*.
# For an endpoint that does check (eg. vLLM's --api-key, or an auth proxy), set one
# with: [p]set api aiagent api_key,<KEY>
API_TOKEN_SERVICE = "aiagent"
PLACEHOLDER_API_KEY = "sk-no-key-needed"


def validate_endpoint(url: str) -> Optional[str]:
    """Returns an error message if `url` is unusable as an endpoint, else None."""
    if not url:
        return "No endpoint set."

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return "The endpoint must start with `http://` or `https://`."

    if not parsed.hostname:
        return "The endpoint has no hostname."

    return None


async def setup_llm_client(
    bot: Red,
    config: Config,
) -> Optional[AsyncOpenAI]:
    """Build the client used to talk to the configured LLM server.

    Returns None if no usable endpoint is configured.
    """
    base_url = await config.llm_endpoint()

    error = validate_endpoint(base_url)
    if error:
        logger.error(
            f"No usable LLM endpoint set for `aiagent`: {error} "
            "Set one with: [p]aiagentowner endpoint <URL>"
        )
        return None

    timeout = await config.llm_endpoint_request_timeout()

    # Optional: only needed if your endpoint actually checks it.
    api_key = (await bot.get_shared_api_tokens(API_TOKEN_SERVICE)).get("api_key")

    http_client = httpx.AsyncClient(
        event_hooks={"request": [log_request_prompt]},
        timeout=timeout,
    )

    return AsyncOpenAI(
        api_key=api_key or PLACEHOLDER_API_KEY,
        base_url=base_url,
        timeout=timeout,
        max_retries=0,
        http_client=http_client,
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
