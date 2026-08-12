import logging
import random
from datetime import datetime

import discord
from discord import Message
from redbot.core import commands

logger = logging.getLogger("red.0x42_cogs.aiagent")

async def format_variables(ctx: commands.Context, text: str):
    """
    Insert supported variables into string if they are present
    """
    botname = ctx.message.guild.me.nick or ctx.bot.user.display_name

    # application_info() is an API round trip. Prefer discord.py's cached
    # application, and skip it entirely unless the prompt asks for the owner.
    botowner = ""
    if "{botowner}" in text:
        app_info = ctx.bot.application or await ctx.bot.application_info()
        botowner = app_info.owner.name if app_info and app_info.owner else "the bot owner"
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

    serveremojis = ""
    if "{serveremojis}" in text:
        emojis = [str(e) for e in ctx.message.guild.emojis]
        random.shuffle(emojis)
        serveremojis = ' '.join(emojis)

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
    return bool(
        message.embeds
        and message.embeds[0].title
        and message.embeds[0].description
    )
