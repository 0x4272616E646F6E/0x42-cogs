import logging
import random
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import tasks

from aiagent.messages_list.messages import create_messages_list
from aiagent.response.dispatcher import dispatch_response
from aiagent.types.abc import MixinMeta

logger = logging.getLogger("red.0x42_cogs.aiagent")

# A channel must have been quiet for this long before an unprompted message.
QUIET_PERIOD_SECONDS = 60 * 60

RANDOM_MESSAGE_PROMPT = (
    "You are {{botname}}. You are in a Discord text channel. "
    "Start a conversation with a short message about the following topic, "
    "as if you thought of it yourself. Do not mention that you were prompted.\n"
    "Topic: {topic}"
)


class RandomMessageTask(MixinMeta):
    @tasks.loop(minutes=33)
    async def random_message_trigger(self):
        """Occasionally start a conversation in a quiet whitelisted channel."""
        if not self.openai_client:
            return

        for guild_id, whitelist in self.channels_whitelist.items():
            if not whitelist:
                continue

            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            try:
                await self._maybe_send_random_message(guild, whitelist)
            except Exception:
                logger.exception(f"Error sending random message in {guild.name}")

    @random_message_trigger.before_loop
    async def before_random_message_trigger(self):
        await self.bot.wait_until_red_ready()

    async def _maybe_send_random_message(self, guild: discord.Guild, whitelist: list):
        if not await self.config.guild(guild).random_messages_enabled():
            return
        if random.random() > await self.config.guild(guild).random_messages_percent():
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return

        prompts = await self.config.guild(guild).random_messages_prompts()
        if not prompts:
            return

        channel = guild.get_channel(random.choice(whitelist))
        if not isinstance(channel, discord.abc.Messageable):
            return
        if not channel.permissions_for(guild.me).send_messages:
            return

        last_message = await self._get_last_message(channel)
        if not last_message:
            return
        if last_message.author.id == self.bot.user.id:
            return
        if last_message.created_at > datetime.now(tz=timezone.utc) - timedelta(seconds=QUIET_PERIOD_SECONDS):
            return

        ctx = await self.bot.get_context(last_message)
        topic = random.choice(prompts)

        logger.debug(f'Sending random message in {guild.name} with topic: "{topic}"')

        messages_list = await create_messages_list(
            self, ctx, prompt=RANDOM_MESSAGE_PROMPT.format(topic=topic), history=False
        )
        messages_list.can_reply = False

        await dispatch_response(self, ctx, messages_list)

    @staticmethod
    async def _get_last_message(channel) -> discord.Message:
        async for message in channel.history(limit=1):
            return message
        return None
