import json
import logging
import random
from datetime import datetime, timedelta
from typing import List, Optional

import discord
from discord import Message
from redbot.core import commands

from aiagent.config.defaults import DEFAULT_PROMPT
from aiagent.config.models import get_model_tokens_limit
from aiagent.messages_list.converter.converter import MessageConverter
from aiagent.messages_list.entry import MessageEntry
from aiagent.messages_list.opt_view import OptView
from aiagent.types.abc import MixinMeta
from aiagent.utils import regex
from aiagent.utils.tokens import estimate_tokens
from aiagent.utils.utilities import format_variables

logger = logging.getLogger("red.0x42_cogs.aiagent")

OPTIN_EMBED_TITLE = ":information_source: AI Agent Opt-In / Opt-Out"

# Total messages pulled in by following replies, for one response. Each hop can
# cost a fetch_message API call, and add_msg recurses into the chain it collects,
# so this budget has to be shared across the whole assembly rather than being a
# local counter — a local one is reset by every recursive call and bounds nothing.
MAX_REPLY_CHAIN = 10


async def create_messages_list(cog: MixinMeta, ctx: commands.Context) -> "MessagesList":
    """Build the ChatML context for a response: the triggering message, the
    applicable prompt, and as much recent channel history as fits."""
    messages = MessagesList(cog, ctx)
    await messages._init()
    await messages.add_history()
    return messages


class MessagesList:
    def __init__(
        self,
        cog: MixinMeta,
        ctx: commands.Context,
    ):
        self.bot = cog.bot
        self.config = cog.config
        self.ctx = ctx
        self.converter = MessageConverter(cog)
        self.init_message = ctx.message
        self.guild = ctx.guild
        self.ignore_regex = cog.ignore_regex.get(self.guild.id, None)
        self.start_time = cog.override_prompt_start_time.get(
            self.guild.id)
        self.messages: List[MessageEntry] = []
        self.messages_ids = set()
        self.tokens = 0
        self.model = None
        self.can_reply = True

    def __len__(self):
        return len(self.messages)

    def __repr__(self) -> str:
        return json.dumps(self.get_json(), indent=4)

    async def _init(self):
        self.model = await self.config.guild(self.guild).model()
        self.token_limit = await self.config.guild(self.guild).custom_model_tokens_limit() or get_model_tokens_limit(self.model)

        # Consent state is read once and reused for every message considered for
        # this response. Previously check_if_add re-read all three per message,
        # so a backread of 10 cost 30 config lookups to answer the same question.
        self._optin = set(await self.config.optin())
        self._optout = set(await self.config.optout())
        self._optin_by_default = await self.config.guild(self.guild).optin_by_default()
        self._allowed_authors = {}
        self._reply_chain_budget = MAX_REPLY_CHAIN
        await self.add_msg(self.init_message)
        await self.add_system(
            await format_variables(self.ctx, await self._pick_prompt())
        )

    async def _pick_prompt(self):
        author = self.init_message.author
        role_prompt = None

        for role in author.roles:
            if role.id in (await self.config.all_roles()):
                role_prompt = await self.config.role(role).custom_text_prompt()
                break

        return (await self.config.member(self.init_message.author).custom_text_prompt()
                or role_prompt
                or await self.config.channel(self.init_message.channel).custom_text_prompt()
                or await self.config.guild(self.guild).custom_text_prompt()
                or await self.config.custom_text_prompt()
                or DEFAULT_PROMPT)

    async def check_if_add(self, message: Message, force: bool = False):
        if self.tokens > self.token_limit:
            return False

        if message.id in self.messages_ids and not force:
            logger.debug(
                f"Skipping duplicate message in {message.guild.name} when creating context"
            )
            return False

        if self.ignore_regex and regex.search(self.ignore_regex, message.content):
            return False

        author_id = message.author.id

        if author_id in self._optout:
            return False

        if (
            author_id != self.bot.user.id
            and author_id not in self._optin
            and not self._optin_by_default
        ):
            return False

        if author_id not in self._allowed_authors:
            self._allowed_authors[author_id] = await self.bot.allowed_by_whitelist_blacklist(
                message.author
            )

        return self._allowed_authors[author_id]

    async def add_msg(self, message: Message, index: Optional[int] = None, force: bool = False):
        if not await self.check_if_add(message, force):
            return

        converted = await self.converter.convert(message)

        if not converted:
            return

        for entry in converted:
            if self.tokens > self.token_limit:
                return

            self.messages.insert(index or 0, entry)
            self.messages_ids.add(message.id)

            if isinstance(entry.content, list):
                for item in entry.content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "text":
                        await self._add_tokens(item.get("text"))
            else:
                await self._add_tokens(entry.content)

        if message.reference and message.author.id != self.bot.user.id:
            chain = []
            ref = message.reference

            # attempt to resolve or fetch the referenced message
            try:
                referenced = ref.resolved if isinstance(ref.resolved, discord.Message) else await self.bot.get_channel(ref.channel_id).fetch_message(ref.message_id)
            except Exception:
                referenced = None

            # walk up the reply chain, collecting messages to add, avoiding bot messages and duplicates
            while (
                referenced
                and isinstance(referenced, discord.Message)
                and referenced.author.id != self.bot.user.id
                and referenced.id not in self.messages_ids
                and self._reply_chain_budget > 0
            ):
                chain.append(referenced)
                self._reply_chain_budget -= 1

                if not referenced.reference:
                    break

                # resolve/fetch the next referenced message in the chain
                try:
                    next_ref = referenced.reference
                    referenced = next_ref.resolved if isinstance(next_ref.resolved, discord.Message) else await self.bot.get_channel(next_ref.channel_id).fetch_message(next_ref.message_id)
                except Exception:
                    break

            # `chain` runs newest -> oldest, and each add_msg inserts at the front,
            # so walking it in collected order leaves the oldest reply at the front.
            # Reversing here (as this used to) inverts the conversation instead.
            for msg in chain:
                await self.add_msg(msg, index=0, force=force)

    async def add_system(self, content: str, index: Optional[int] = None):
        if self.tokens > self.token_limit:
            return
        entry = MessageEntry("system", content)
        self.messages.insert(index or 0, entry)
        await self._add_tokens(content)

    async def add_assistant(self, content: str = "", index: Optional[int] = None):
        if self.tokens > self.token_limit:
            return
        entry = MessageEntry("assistant", content)
        self.messages.insert(index or 0, entry)
        await self._add_tokens(content)

    async def add_history(self):
        limit = await self.config.guild(self.guild).messages_backread()
        max_seconds_gap = await self.config.guild(self.guild).messages_backread_seconds()
        start_time: datetime = (
            self.start_time - timedelta(seconds=1) if self.start_time else None
        )

        past_messages = await self._get_past_messages(limit, start_time)
        if not past_messages:
            return

        if not await self._is_valid_time_gap(self.init_message, past_messages[0], max_seconds_gap):
            return

        users = await self._get_unopted_users(past_messages[:10])

        await self._process_past_messages(past_messages, max_seconds_gap)

        if (
            users
            and not await self.config.guild(self.guild).optin_disable_embed()
            and ((random.random() <= 0.33) or (len(users) > 3))
        ):
            await self._send_optin_embed(users)

    async def _get_past_messages(self, limit, start_time):
        return [
            message
            async for message in self.init_message.channel.history(
                limit=limit + 1,
                before=self.init_message,
                after=start_time,
                oldest_first=False,
            )
        ]

    async def _get_unopted_users(self, messages):
        """Authors who have made no choice yet, so they can be prompted once."""
        users = set()

        if self._optin_by_default:
            return users

        # The consent lists were read once in _init; re-reading them per message
        # cost up to 20 config lookups per response for the same two answers.
        for message in messages:
            author = message.author
            if (
                not author.bot
                and author.id not in self._optin
                and author.id not in self._optout
            ):
                users.add(author)

        return users

    async def _process_past_messages(self, past_messages, max_seconds_gap):
        for i in range(len(past_messages) - 1):
            if self.tokens > self.token_limit:
                return logger.debug(f"{self.tokens} tokens used - nearing limit, stopping context creation for message {self.init_message.id}")
            if (past_messages[i].author.id == self.bot.user.id) and (past_messages[i].embeds and past_messages[i].embeds[0].title == OPTIN_EMBED_TITLE):
                continue
            if await self._is_valid_time_gap(past_messages[i], past_messages[i + 1], max_seconds_gap):
                await self.add_msg(past_messages[i])
            else:
                await self.add_msg(past_messages[i])
                break

    async def _send_optin_embed(self, users):
        users = ", ".join([user.mention for user in users])
        embed = discord.Embed(
            title=OPTIN_EMBED_TITLE,
            color=await self.bot.get_embed_color(self.init_message),
        )
        view = OptView(self.config)
        embed.description = f"{users}\nPlease choose whether to allow a subset of your Discord messages from any server with the bot, to be sent to the LLM endpoint configured by the bot owner.\nThis will allow the bot to reply to your messages or use your messages.\nThis message will disappear if all current chatters have made a choice."
        await self.init_message.channel.send(embed=embed, view=view)

    def get_json(self):
        return [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in self.messages
        ]

    async def _add_tokens(self, content):
        self.tokens += estimate_tokens(str(content))

    @staticmethod
    async def _is_valid_time_gap(message: discord.Message, next_message: discord.Message, max_seconds_gap: int) -> bool:
        seconds_diff = abs(message.created_at - next_message.created_at).total_seconds()
        return seconds_diff <= max_seconds_gap
