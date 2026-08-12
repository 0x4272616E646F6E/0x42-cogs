# handlers.py

import asyncio
import logging

import discord
from redbot.core import commands

from aiagent.config.constants import URL_PATTERN
from aiagent.core.throttle import SlotOutcome, delay_budget
from aiagent.core.triggers import is_bot_mentioned_or_replied
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

    # The slash command carries its own cooldown, but the concurrency cap and
    # queue are bot-wide: without them, twenty /chat calls still swamp the server.
    outcome = await cog.throttle.acquire_slot(
        ctx.channel.id, wait_budget=delay_budget(ctx.message.created_at)
    )
    if outcome is not SlotOutcome.GRANTED:
        return await ctx.send(
            ":zzz: This bot is generating as much as it can at once. Try again shortly.",
            ephemeral=True,
        )

    try:
        await dispatch_response(cog, ctx)
    except Exception:
        logger.exception("Error in generating response for slash command")
        await ctx.send(":warning: Error in generating response!", ephemeral=True)
    finally:
        cog.throttle.release_slot()


async def handle_message(cog: MixinMeta, message: discord.Message):
    """Handle regular message events"""
    # Cheapest check first. This one is pure in-memory, while get_context parses
    # prefixes and is_valid_message reads config and may build the LLM client.
    # Most traffic in a whitelisted channel is not addressed to the bot.
    if not await is_bot_mentioned_or_replied(cog, message):
        return

    ctx: commands.Context = await cog.bot.get_context(message)

    if not (await is_valid_message(cog, ctx)):
        return

    waiting = cog.throttle.seconds_remaining(ctx.author.id)
    if waiting > 0:
        logger.debug(f"{ctx.author.id} is {waiting:.0f}s into a cooldown")
        await ctx.react_quietly("💤", message="`aiagent` is cooling down, try again shortly")
        return

    # Tell them they are in line rather than leaving them looking at silence.
    if cog.throttle.busy:
        await ctx.react_quietly("⏳", message="`aiagent` is busy; you're in the queue")

    outcome = await cog.throttle.acquire_slot(
        ctx.channel.id, wait_budget=delay_budget(ctx.message.created_at)
    )

    if outcome is SlotOutcome.QUEUE_FULL:
        logger.debug(f"Queue for channel {ctx.channel.id} is full")
        await ctx.react_quietly("💤", message="`aiagent` has too many requests waiting")
        return

    if outcome is SlotOutcome.TOO_SLOW:
        # Answering now would drop a reply into a conversation that has moved on.
        logger.debug("Gave up waiting for a slot; the message is too old to answer")
        await ctx.react_quietly("💤", message="`aiagent` couldn't get to this in time")
        return

    try:
        cog.throttle.record(ctx.author.id)

        if URL_PATTERN.search(ctx.message.content):
            ctx = await wait_for_embed(ctx)

        await dispatch_response(cog, ctx)
    finally:
        cog.throttle.release_slot()


async def wait_for_embed(ctx: commands.Context) -> commands.Context:
    """Wait for possible embed to be valid"""
    start_time = asyncio.get_event_loop().time()
    while not is_embed_valid(ctx.message):
        ctx.message = await ctx.channel.fetch_message(ctx.message.id)
        if asyncio.get_event_loop().time() - start_time >= 3:
            break
        await asyncio.sleep(1)
    return ctx
