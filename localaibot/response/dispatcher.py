# response/response_handler.py
import logging

from redbot.core import commands

from localaibot.messages_list.messages import create_messages_list
from localaibot.response.chat.response import create_chat_response
from localaibot.types.abc import MixinMeta

logger = logging.getLogger("red.0x42_cogs.aibot")


async def dispatch_response(cog: MixinMeta, ctx: commands.Context, messages_list=None):
    """ Respond to context with chat response """
    async with ctx.message.channel.typing():

        messages_list = messages_list or await create_messages_list(cog, ctx)
        return await create_chat_response(cog, ctx, messages_list)
