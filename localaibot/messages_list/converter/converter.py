import logging

from discord import Message
from redbot.core import commands

from localaibot.types.abc import MixinMeta
from localaibot.utils.utilities import contains_youtube_link, is_embed_valid
from localaibot.messages_list.converter.embed.formatter import format_embed_content
from localaibot.messages_list.converter.helpers import (format_embed_text_content,
                                                    format_sticker_content,
                                                    format_text_content)
from localaibot.messages_list.entry import MessageEntry

logger = logging.getLogger("red.0x42_cogs.aibot")


class MessageConverter():
    def __init__(self, cog: MixinMeta, ctx: commands.Context):
        self.cog = cog
        self.config = cog.config
        self.bot_id = cog.bot.user.id
        self.init_msg = ctx.message
        self.message_cache = cog.cached_messages
        self.ctx = ctx

    async def convert(self, message: Message):
        """Converts a Discord message to ChatML format message(s)"""
        res = []
        role = "user" if message.author.id != self.bot_id else "assistant"
        if message.attachments:
            self.handle_attachment(message, res, role)
        elif message.stickers:
            content = await format_sticker_content(message)
            self.add_entry(content, res, role)
        elif (len(message.embeds) > 0 and is_embed_valid(message)) or contains_youtube_link(message.content):
            await self.handle_embed(message, res, role)
        else:
            content = format_text_content(message)
            self.add_entry(content, res, role)

        return res or None

    def handle_attachment(self, message: Message, res, role):
        attachment = message.attachments[0]
        # Treat all attachments generically. Do not perform any image detection or scanning.
        content = f'User "{message.author.display_name}" sent: [Attachment: "{attachment.filename}"]'
        self.add_entry(content, res, role)
        # always include text content after handling attachments
        content = format_text_content(message)
        self.add_entry(content, res, role)

    async def handle_embed(self, message: Message, res, role):
        content = await format_embed_content(self.cog, message)
        if not content:
            content = format_text_content(message)
            self.add_entry(content, res, role)
        else:
            self.add_entry(content, res, role)
            content = format_embed_text_content(message)
            self.add_entry(content, res, role)

    def add_entry(self, content, res, role):
        if not content:
            return
        res.append(MessageEntry(role, content))
