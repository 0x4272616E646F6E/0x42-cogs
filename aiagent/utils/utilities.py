import asyncio
import functools
import logging
import random
from datetime import datetime
from typing import Callable, Coroutine

import discord
import tiktoken
from discord import Message
from redbot.core import commands

from aiagent.config.constants import YOUTUBE_URL_PATTERN

logger = logging.getLogger("red.0x42_cogs.aiagent")

# Local models ship their own tokenizers, and no local endpoint exposes one over
# the API. This encoding is only used to *estimate* how much context fits, so a
# single general-purpose encoding is good enough.
TOKENIZER_ENCODING = "cl100k_base"


def get_encoding() -> tiktoken.Encoding:
    """Encoding used to estimate token counts for any model."""
    return tiktoken.get_encoding(TOKENIZER_ENCODING)


def to_thread(timeout=300):
    def decorator(func: Callable) -> Coroutine:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, func, *args, **kwargs), timeout
            )
            return result

        return wrapper

    return decorator


async def format_variables(ctx: commands.Context, text: str):
    """
    Insert supported variables into string if they are present
    """
    botname = ctx.message.guild.me.nick or ctx.bot.user.display_name
    app_info = await ctx.bot.application_info()
    botowner = app_info.owner.name
    authorname = ctx.message.author.display_name
    authortoprole = ctx.message.author.top_role.name
    authormention = ctx.message.author.mention

    servername = ctx.guild.name
    channelname = ctx.message.channel.name
    currentdate = datetime.today().strftime("%Y/%m/%d")
    currentweekday = datetime.today().strftime("%A")
    currenttime = datetime.today().strftime("%H:%M")

    randomnumber = random.randint(0, 100)

    if isinstance(ctx.message.channel, discord.Thread):
        channeltopic = ctx.message.channel.parent.topic
    else:
        channeltopic = ctx.message.channel.topic

    serveremojis = [str(e) for e in ctx.message.guild.emojis]
    random.shuffle(serveremojis)
    serveremojis = ' '.join(serveremojis)

    try:
        res = text.format(
            botname=botname,
            botowner=botowner,
            authorname=authorname,
            authortoprole=authortoprole,
            authormention=authormention,
            servername=servername,
            serveremojis=serveremojis,
            channelname=channelname,
            channeltopic=channeltopic,
            currentdate=currentdate,
            currentweekday=currentweekday,
            currenttime=currenttime,
            randomnumber=randomnumber,
        )
        return res
    except KeyError:
        logger.exception("Invalid key in message", exc_info=True)
        return text


def is_embed_valid(message: Message):
    if (
        (len(message.embeds) == 0)
        or (not message.embeds[0].title)
        or (not message.embeds[0].description)
    ):
        return False
    return True


def contains_youtube_link(content):
    match = YOUTUBE_URL_PATTERN.search(content)
    return bool(match)
