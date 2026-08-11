
from discord import Message

from aiagent.messages_list.converter.embed.youtube import format_youtube_embed
from aiagent.types.abc import MixinMeta
from aiagent.utils.utilities import contains_youtube_link


async def format_embed_content(cog: MixinMeta, message: Message):
    yt_api_key = (await cog.bot.get_shared_api_tokens("youtube")).get("api_key")
    if yt_api_key and contains_youtube_link(message.content):
        return await format_youtube_embed(yt_api_key, message)

    if not message.embeds:
        # eg. a YouTube link whose embed never arrived
        return None

    return f'User "{message.author.display_name}" sent: [Embed with title "{message.embeds[0].title}" and description "{message.embeds[0].description}"]'
