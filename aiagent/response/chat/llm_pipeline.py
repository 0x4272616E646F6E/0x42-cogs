import json
import logging
from typing import Any, Dict, Optional

import httpx
import openai
from openai.types.chat import ChatCompletion
from redbot.core import Config, commands

from aiagent.config.constants import RESERVED_PARAMETERS
from aiagent.messages_list.messages import MessagesList
from aiagent.types.abc import MixinMeta

logger = logging.getLogger("red.0x42_cogs.aiagent")


class LLMPipeline:
    def __init__(self, cog: MixinMeta, ctx: commands.Context, messages: MessagesList):
        self.ctx: commands.Context = ctx
        self.config: Config = cog.config
        self.bot = cog.bot
        self.msg_list = messages
        self.model = messages.model
        self.can_reply = messages.can_reply
        self.openai_client = cog.openai_client
        self.completion: Optional[str] = None

    async def get_custom_parameters(self) -> Dict[str, Any]:
        custom_parameters = await self.config.guild(self.ctx.guild).parameters()
        kwargs = json.loads(custom_parameters) if custom_parameters else {}

        for reserved in RESERVED_PARAMETERS:
            kwargs.pop(reserved, None)

        return kwargs

    async def create_completion(self) -> Optional[str]:
        if not self.model:
            logger.error(
                f"No model set for {self.ctx.guild.name}. Set one with [p]aiagent model <MODEL>"
            )
            return None

        kwargs = await self.get_custom_parameters()

        response: ChatCompletion = await self.openai_client.chat.completions.create(
            model=self.model, messages=self.msg_list.get_json(), **kwargs
        )

        self.completion = response.choices[0].message.content

        logger.debug(f'Generated response in {self.ctx.guild.name}: "{self.completion}"')
        return self.completion

    async def run(self) -> Optional[str]:
        try:
            return await self.create_completion()
        except (httpx.ReadTimeout, openai.APITimeoutError):
            logger.error("Failed request to LLM endpoint. Timed out.")
            await self.ctx.react_quietly("💤", message="`aiagent` request timed out")
        except openai.APIConnectionError:
            logger.error(
                f"Could not reach the LLM endpoint at {self.openai_client.base_url}. Is it running?"
            )
            await self.ctx.react_quietly("🔌", message="`aiagent` could not reach the LLM server")
        except openai.RateLimitError:
            await self.ctx.react_quietly("💤", message="`aiagent` request ratelimited")
        except openai.NotFoundError:
            logger.error(
                f'Model "{self.model}" not found on the LLM endpoint. '
                "See [p]aiagent model list for available models."
            )
            await self.ctx.react_quietly("⚠️", message="`aiagent` model not found on the LLM server")
        except Exception:
            logger.exception("Failed request to LLM endpoint")
            await self.ctx.react_quietly("⚠️", message="`aiagent` request failed")
        return None
