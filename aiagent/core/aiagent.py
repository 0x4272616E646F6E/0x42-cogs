import logging
import re
from datetime import datetime

import discord
from openai import AsyncOpenAI
from redbot.core import Config, app_commands, commands
from redbot.core.bot import Red

from aiagent.config.defaults import (
    DEFAULT_CHANNEL,
    DEFAULT_GLOBAL,
    DEFAULT_GUILD,
    DEFAULT_MEMBER,
    DEFAULT_ROLE,
)
from aiagent.core.handlers import handle_message, handle_slash_command
from aiagent.core.random_message_task import RandomMessageTask
from aiagent.dashboard.base import DashboardIntegration
from aiagent.settings.base import Settings
from aiagent.types.abc import CompositeMetaClass

from .llm_client import API_TOKEN_SERVICE, setup_llm_client

logger = logging.getLogger("red.0x42_cogs.aiagent")
logging.getLogger("httpcore").setLevel(logging.WARNING)


class AIAgent(
    DashboardIntegration,
    Settings,
    RandomMessageTask,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
        Human-like Discord interactions powered by an LLM.

        Talks to any OpenAI-compatible endpoint you point it at — typically one
        you host yourself (Ollama, llama.cpp, vLLM, LM Studio, ...).
    """

    def __init__(self, bot):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=754070)
        self.openai_client: AsyncOpenAI = None
        # cached options
        self.optindefault: dict[int, bool] = {}
        self.channels_whitelist: dict[int, list[int]] = {}
        self.ignore_regex: dict[int, re.Pattern] = {}
        self.override_prompt_start_time: dict[int, datetime] = {}

        self.config.register_member(**DEFAULT_MEMBER)
        self.config.register_role(**DEFAULT_ROLE)
        self.config.register_channel(**DEFAULT_CHANNEL)
        self.config.register_guild(**DEFAULT_GUILD)
        self.config.register_global(**DEFAULT_GLOBAL)

    async def cog_load(self):
        self.openai_client = await setup_llm_client(self.bot, self.config)

        all_config = await self.config.all_guilds()

        for guild_id, config in all_config.items():
            self.optindefault[guild_id] = config["optin_by_default"]
            self.channels_whitelist[guild_id] = config["channels_whitelist"]
            pattern = config["ignore_regex"]

            self.ignore_regex[guild_id] = re.compile(pattern) if pattern else None

        self.random_message_trigger.start()

    async def cog_unload(self):
        if self.openai_client:
            await self.openai_client.close()
        self.random_message_trigger.cancel()

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if member:
                await self.config.member(member).clear()

        optin = await self.config.optin()
        if user_id in optin:
            optin.remove(user_id)
            await self.config.optin.set(optin)

        optout = await self.config.optout()
        if user_id in optout:
            optout.remove(user_id)
            await self.config.optout.set(optout)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, _):
        if service_name == API_TOKEN_SERVICE:
            self.openai_client = await setup_llm_client(self.bot, self.config)

    @app_commands.command(name="chat")
    @app_commands.describe(text="The prompt you want to send to the AI.")
    @app_commands.checks.cooldown(1, 30)
    @app_commands.checks.cooldown(1, 5, key=None)
    async def slash_command(
        self,
        inter: discord.Interaction,
        *,
        text: app_commands.Range[str, 1, 2000],
    ):
        """Talk directly to this bot's AI. Ask it anything you want!"""
        await handle_slash_command(self, inter, text)

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        await handle_message(self, message)
