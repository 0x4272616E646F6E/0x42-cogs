# handlers.py

import asyncio
import logging
import math
import random

import discord
from redbot.core import commands

from aiagent.config.constants import URL_PATTERN
from aiagent.config.defaults import DEFAULT_REPLY_PERCENT
from aiagent.core.triggers import check_triggers
from aiagent.core.validators import is_valid_message
from aiagent.response.dispatcher import dispatch_response
from aiagent.types.abc import MixinMeta
from aiagent.utils.utilities import is_embed_valid

logger = logging.getLogger("red.0x42_cogs.aiagent")


async def handle_slash_command(cog: MixinMeta, inter: discord.Interaction, text: str):
    """Handle /chat slash command interactions"""
    await inter.response.defer()

    ctx = await commands.Context.from_interaction(inter)
    ctx.message.content = text

    if not (await is_valid_message(cog, ctx)):
        return await ctx.send(
            "You're not allowed to use this command here.", ephemeral=True
        )

    percentage = await get_percentage(cog, ctx)
    # Treat values very close to 1.0 as full-percentage to avoid float equality checks
    if not math.isclose(percentage, 1.0, rel_tol=1e-9):
        if not (await cog.config.guild(ctx.guild).reply_to_mentions_replies()):
            return await ctx.send("This command is not enabled.", ephemeral=True)

    try:
        await dispatch_response(cog, ctx)
    except Exception:
        logger.exception("Error in generating response for slash command")
        await ctx.send(":warning: Error in generating response!", ephemeral=True)


async def handle_message(cog: MixinMeta, message: discord.Message):
    """Handle regular message events"""
    ctx: commands.Context = await cog.bot.get_context(message)

    if not (await is_valid_message(cog, ctx)):
        return

    if not await check_triggers(cog, ctx, message) and random.random() > await get_percentage(cog, ctx):
        return

    if URL_PATTERN.search(ctx.message.content):
        ctx = await wait_for_embed(ctx)

    await dispatch_response(cog, ctx)


async def get_percentage(cog: MixinMeta, ctx: commands.Context) -> float:
    """Get reply percentage based on member/role/channel/guild settings"""
    role_percent = None
    author = ctx.author

    for role in author.roles:
        if role.id in (await cog.config.all_roles()):
            role_percent = await cog.config.role(role).reply_percent()
            break

    percentage = await cog.config.member(author).reply_percent()
    if percentage is None:
        percentage = role_percent
    if percentage is None:
        percentage = await cog.config.channel(ctx.channel).reply_percent()
    if percentage is None:
        percentage = await cog.config.guild(ctx.guild).reply_percent()
    if percentage is None:
        percentage = DEFAULT_REPLY_PERCENT
    return percentage


async def wait_for_embed(ctx: commands.Context) -> commands.Context:
    """Wait for possible embed to be valid"""
    start_time = asyncio.get_event_loop().time()
    while not is_embed_valid(ctx.message):
        ctx.message = await ctx.channel.fetch_message(ctx.message.id)
        if asyncio.get_event_loop().time() - start_time >= 3:
            break
        await asyncio.sleep(1)
    return ctx
