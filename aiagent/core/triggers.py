import discord

from aiagent.types.abc import MixinMeta


async def is_bot_mentioned_or_replied(cog: MixinMeta, message: discord.Message) -> bool:
    """The bot answers when it is tagged, or when someone replies to it."""
    if cog.bot.user in message.mentions:
        return True

    reference = message.reference
    if reference and isinstance(reference.resolved, discord.Message):
        return reference.resolved.author.id == cog.bot.user.id

    return False
