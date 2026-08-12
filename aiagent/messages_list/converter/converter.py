import logging

from discord import Message

from aiagent.types.abc import MixinMeta
from aiagent.utils.utilities import is_embed_valid
from aiagent.messages_list.converter.helpers import (format_embed_content,
                                                    format_embed_text_content,
                                                    format_sticker_content,
                                                    format_text_content)
from aiagent.messages_list.entry import MessageEntry

logger = logging.getLogger("red.0x42_cogs.aiagent")


class MessageConverter():
    """Turns Discord messages into ChatML entries, from the bot's point of view."""

    def __init__(self, cog: MixinMeta):
        self.bot_id = cog.bot.user.id

    async def convert(self, message: Message):
        """Converts a Discord message to ChatML format message(s)"""
        res = []
        role = "user" if message.author.id != self.bot_id else "assistant"
        if message.attachments:
            self.handle_attachment(message, res, role)
        elif message.stickers:
            content = await format_sticker_content(message)
            self.add_entry(content, res, role)
        elif len(message.embeds) > 0 and is_embed_valid(message):
            self.handle_embed(message, res, role)
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

    def handle_embed(self, message: Message, res, role):
        content = format_embed_content(message)
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
