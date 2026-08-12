import logging

import discord
from discord import AllowedMentions
from redbot.core import Config, commands

from aiagent.messages_list.messages import MessagesList
from aiagent.response.chat.llm_pipeline import LLMPipeline
from aiagent.types.abc import MixinMeta
from aiagent.utils import regex

logger = logging.getLogger("red.0x42_cogs.aiagent")

MESSAGE_LENGTH_LIMIT = 2000

# A runaway generation should not turn one mention into a wall of messages.
MAX_RESPONSE_CHUNKS = 3
TRUNCATION_NOTICE = " […truncated]"

async def remove_patterns_from_response(ctx: commands.Context, config: Config, response: str) -> str:
    # Get patterns from config and replace "{botname}".
    patterns = await config.guild(ctx.guild).removelist_regexes()
    botname = ctx.message.guild.me.nick or ctx.bot.user.display_name
    patterns = [p.replace(r'{botname}', botname) for p in patterns]

    # Expanding "{authorname}" needs recent authors, which costs an API call.
    # Only pay for it when a pattern actually uses the placeholder.
    authors = set()
    if any('{authorname}' in pattern for pattern in patterns):
        authors = {
            msg.author.display_name async for msg in ctx.channel.history(limit=10)
            if msg.author != ctx.guild.me
        }

    expanded_patterns = []
    for pattern in patterns:
        if '{authorname}' in pattern:
            for author in authors:
                expanded_patterns.append(pattern.replace(r'{authorname}', author))
        else:
            expanded_patterns.append(pattern)

    # Apply each pattern sequentially.
    cleaned = response.strip(' \n')
    for pattern in expanded_patterns:
        cleaned = regex.sub(pattern, cleaned)
    return cleaned

def split_response(response: str) -> list:
    """Split into Discord-sized chunks, capped so one runaway reply can't flood a channel.

    A local model with no `max_tokens` set can generate for a very long time; without
    a cap that arrives as an unbounded burst of messages. Set `max_tokens` via
    `[p]aiagent response parameters` to bound it at the source instead.
    """
    chunks = [
        response[index:index + MESSAGE_LENGTH_LIMIT]
        for index in range(0, len(response), MESSAGE_LENGTH_LIMIT)
    ]

    if len(chunks) <= MAX_RESPONSE_CHUNKS:
        return chunks

    kept = chunks[:MAX_RESPONSE_CHUNKS]
    dropped = len(chunks) - MAX_RESPONSE_CHUNKS
    logger.warning(
        f"Response was {len(response)} characters; sent "
        f"{MAX_RESPONSE_CHUNKS} messages and dropped {dropped}."
    )
    kept[-1] = kept[-1][:MESSAGE_LENGTH_LIMIT - len(TRUNCATION_NOTICE)] + TRUNCATION_NOTICE
    return kept


async def send_response(ctx: commands.Context, response: str, can_reply: bool) -> bool:
    allowed = AllowedMentions(everyone=False, roles=False, users=[ctx.message.author])
    chunks = split_response(response)

    if ctx.interaction:
        for chunk in chunks:
            await ctx.interaction.followup.send(chunk, allowed_mentions=allowed)
        return True

    # Reply to the message that summoned us so threads stay legible. If it has been
    # deleted, Discord rejects the reply and a plain send is the fallback — cheaper
    # than fetching the message first to find out.
    if can_reply:
        try:
            await ctx.message.reply(
                chunks[0], mention_author=False, allowed_mentions=allowed
            )
            chunks = chunks[1:]
        except discord.HTTPException:
            logger.debug("Could not reply to the triggering message; sending instead.")

    for chunk in chunks:
        await ctx.send(chunk, allowed_mentions=allowed)
    return True

async def create_chat_response(cog: MixinMeta, ctx: commands.Context, messages_list: MessagesList) -> bool:
    pipeline = LLMPipeline(cog, ctx, messages=messages_list)
    response = await pipeline.run()
    if not response:
        return False

    cleaned_response = await remove_patterns_from_response(ctx, cog.config, response)
    if not cleaned_response:
        return False

    return await send_response(ctx, cleaned_response, messages_list.can_reply)
