import json
import logging
from urllib.parse import urlparse

import discord
from redbot.core import checks, commands
from redbot.core.utils.menus import SimpleMenu

from aiagent.settings.history import HistorySettings
from aiagent.settings.owner import OwnerSettings
from aiagent.settings.prompt import PromptSettings
from aiagent.settings.response import ResponseSettings
from aiagent.settings.triggers import TriggerSettings
from aiagent.settings.utilities import get_available_models
from aiagent.types.abc import MixinMeta
from aiagent.types.types import COMPATIBLE_CHANNELS

logger = logging.getLogger("red.0x42_cogs.aiagent")
NO_VALUE = "`None`"

class Settings(
    PromptSettings,
    HistorySettings,
    ResponseSettings,
    TriggerSettings,
    OwnerSettings,
    MixinMeta,
):
    @commands.group(aliases=["ai_agent"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    @commands.guild_only()
    async def aiagent(self, _):
        """Utilize a local LLM to reply to messages in approved channels and by opt-in users"""
        pass

    @aiagent.command(aliases=["lobotomize"])
    async def forget(self, ctx: commands.Context):
        """Forces the bot to forget the current conversation up to this point

        This is useful if the LLM is stuck doing unwanted behaviour or giving undesirable results.
        See `[p]aiagent triggers public_forget` to allow non-admins to use this command.
        """
        if (
            not ctx.channel.permissions_for(ctx.author).manage_messages
            and not await self.config.guild(ctx.guild).public_forget()
        ):
            return await ctx.react_quietly("❌")

        self.override_prompt_start_time[ctx.guild.id] = ctx.message.created_at
        await ctx.react_quietly("✅")

    @aiagent.command(aliases=["settings", "showsettings"])
    @checks.admin_or_permissions(manage_guild=True)
    async def config(self, ctx: commands.Context):
        """Returns current config

        Admin only: this lists whitelisted members and roles, and the host the
        bot sends messages to.

        (Current config per server)
        """
        config = await self.config.guild(ctx.guild).get_raw()
        glob_config = await self.config.get_raw()
        whitelist = await self.config.guild(ctx.guild).channels_whitelist()
        channels = [f"<#{channel_id}>" for channel_id in whitelist]
        embeds = []

        main_embed = discord.Embed(
            title="AI Agent Settings", color=await ctx.embed_color()
        )

        main_embed.add_field(name="Model", inline=True, value=f"`{config['model']}`")
        main_embed.add_field(
            name="Opt In By Default", inline=True, value=f"`{config['optin_by_default']}`"
        )
        main_embed.add_field(
            name="Max History Size",
            inline=True,
            value=f"`{config['messages_backread']}` messages",
        )
        main_embed.add_field(
            name="Max History Gap",
            inline=True,
            value=f"`{config['messages_backread_seconds']}` seconds",
        )
        main_embed.add_field(
            name="Whitelisted Channels",
            inline=True,
            value=" ".join(channels) if channels else NO_VALUE,
        )

        # Host only: the full URL can carry a port, path or credentials, and this
        # embed is visible to every admin in the server. [p]aiagentowner endpoint
        # shows the whole thing to the bot owner.
        endpoint_host = urlparse(str(glob_config["llm_endpoint"] or "")).hostname
        main_embed.add_field(
            name="LLM Endpoint",
            inline=True,
            value=f"`{endpoint_host}`" if endpoint_host else NO_VALUE,
        )

        whitelisted_trigger = bool(
            config["members_whitelist"] or config["roles_whitelist"])

        main_embed.add_field(
            name="Only Whitelist Trigger",
            inline=True,
            value=f"`{whitelisted_trigger}`",
        )
        main_embed.add_field(
            name="Whitelisted Members",
            inline=True,
            value=" ".join(
                [f"<@{member_id}>" for member_id in config["members_whitelist"]]
            ) or NO_VALUE,
        )
        main_embed.add_field(
            name="Whitelisted Roles",
            inline=True,
            value=" ".join(
                [f"<@&{role_id}>" for role_id in config["roles_whitelist"]]
            ) or NO_VALUE,
        )

        removelist_regexes = config["removelist_regexes"]
        regexes_num = 0
        if removelist_regexes is not None:
            regexes_num = len(removelist_regexes)
        main_embed.add_field(
            name="Remove list", value=f"`{regexes_num}` regexes set"
        )
        main_embed.add_field(name="Ignore Regex",
                             value=f"`{config['ignore_regex']}`")
        main_embed.add_field(
            name="Public Forget Command", inline=True, value=f"`{config['public_forget']}`"
        )
        embeds.append(main_embed)

        parameters = config["parameters"]
        if parameters is not None:
            parameters = json.loads(parameters)
            parameters_embed = discord.Embed(
                title="Custom Parameters to Endpoint", color=await ctx.embed_color()
            )
            for key, value in parameters.items():
                parameters_embed.add_field(
                    name=key, value=f"```{json.dumps(value, indent=4)}```", inline=False
                )
            embeds.append(parameters_embed)

        for embed in embeds:
            await ctx.send(embed=embed)


    @aiagent.command()
    @checks.is_owner()
    async def add(
        self,
        ctx: commands.Context,
        channel: COMPATIBLE_CHANNELS,
    ):
        """Adds a channel to the whitelist

        **Arguments**
            - `channel` A mention of the channel
        """
        if not channel:
            return await ctx.send("Invalid channel")
        new_whitelist = await self.config.guild(ctx.guild).channels_whitelist()
        if channel.id in new_whitelist:
            return await ctx.send("Channel already in whitelist")
        new_whitelist.append(channel.id)
        await self.config.guild(ctx.guild).channels_whitelist.set(new_whitelist)
        self.channels_whitelist[ctx.guild.id] = new_whitelist
        embed = discord.Embed(
            title="The server whitelist is now:", color=await ctx.embed_color()
        )
        channels = [f"<#{channel_id}>" for channel_id in new_whitelist]
        embed.description = "\n".join(channels) if channels else "None"
        return await ctx.send(embed=embed)

    @aiagent.command()
    @checks.is_owner()
    async def remove(
        self,
        ctx: commands.Context,
        channel: COMPATIBLE_CHANNELS,
    ):
        """Remove a channel from the whitelist

        **Arguments**
            - `channel` A mention of the channel
        """
        if not channel:
            return await ctx.send("Invalid channel")
        new_whitelist = await self.config.guild(ctx.guild).channels_whitelist()
        if channel.id not in new_whitelist:
            return await ctx.send("Channel not in whitelist")
        new_whitelist.remove(channel.id)
        await self.config.guild(ctx.guild).channels_whitelist.set(new_whitelist)
        self.channels_whitelist[ctx.guild.id] = new_whitelist
        embed = discord.Embed(
            title="The server whitelist is now:", color=await ctx.embed_color()
        )
        channels = [f"<#{channel_id}>" for channel_id in new_whitelist]
        embed.description = "\n".join(channels) if channels else "None"
        return await ctx.send(embed=embed)

    @aiagent.command()
    @checks.is_owner()
    async def model(self, ctx: commands.Context, model: str):
        """Changes chat completion model

         Only models your LLM server actually serves can be selected.
         To see a list of available models, use `[p]aiagent model list`
         (Setting is per server)

        **Arguments**
            - `model` The model to use eg. `gpt-oss:20b`
        """
        if not self.openai_client:
            return await ctx.send(
                f":warning: No LLM endpoint reachable. Set one with `{ctx.clean_prefix}aiagentowner endpoint <URL>`"
            )

        await ctx.message.add_reaction("🔄")
        try:
            models = await get_available_models(self.openai_client)
        except Exception:
            logger.warning("Could not list models from the LLM endpoint", exc_info=True)
            return await ctx.send(
                ":warning: Could not reach your LLM server. Is it running?"
            )
        finally:
            await ctx.message.remove_reaction("🔄", ctx.me)

        if model == "list":
            return await self._paginate_models(ctx, models)

        if model not in models:
            await ctx.send(":warning: Not a valid model!")
            return await self._paginate_models(ctx, models)

        await self.config.guild(ctx.guild).model.set(model)
        embed = discord.Embed(
            title="This server's chat model is now set to:",
            description=model,
            color=await ctx.embed_color(),
        )

        return await ctx.send(embed=embed)

    async def _paginate_models(self, ctx, models):
        pagified_models = [models[i: i + 10]
                           for i in range(0, len(models), 10)]
        menu_pages = []

        for models_page in pagified_models:
            embed = discord.Embed(
                title="Available Models",
                color=await ctx.embed_color(),
            )
            embed.description = "\n".join(
                [f"`{model}`" for model in models_page])
            menu_pages.append(embed)

        if len(menu_pages) == 1:
            return await ctx.send(embed=menu_pages[0])
        for i, page in enumerate(menu_pages):
            page.set_footer(text=f"Page {i+1} of {len(menu_pages)}")
        return (await SimpleMenu(menu_pages).start(ctx))

    @aiagent.command()
    async def optin(self, ctx: commands.Context):
        """Opt in to having your messages sent to the bot owner's local LLM (bot-wide)

        This will allow the bot to reply to your messages or use your messages.
        """
        optin = await self.config.optin()
        if ctx.author.id in await self.config.optin():
            return await ctx.send("You are already opted in.")
        optout = await self.config.optout()
        if ctx.author.id in optout:
            optout.remove(ctx.author.id)
            await self.config.optout.set(optout)
        optin.append(ctx.author.id)
        await self.config.optin.set(optin)
        await ctx.send("You are now opted in bot-wide")

    @aiagent.command()
    async def optout(self, ctx: commands.Context):
        """Opt out of having your messages sent to the bot owner's local LLM (bot-wide)

        This will prevent the bot from replying to your messages or using your messages.
        """
        optout = await self.config.optout()
        if ctx.author.id in optout:
            return await ctx.send("You are already opted out.")
        optin = await self.config.optin()
        if ctx.author.id in optin:
            optin.remove(ctx.author.id)
            await self.config.optin.set(optin)
        optout.append(ctx.author.id)
        await self.config.optout.set(optout)
        await ctx.send("You are now opted out bot-wide")

    @aiagent.command(name="optinbydefault", alias=["optindefault"])
    @checks.admin_or_permissions(manage_guild=True)
    async def optin_by_default(self, ctx: commands.Context):
        """Toggles whether users are opted in by default in this server

        This command is disabled for servers with more than 150 members.
        """
        if len(ctx.guild.members) > 150:
            # if you STILL want to enable this for a server with more than 150 members
            # add the line below to the specific guild in the cog's settings.json:
            # "optin_by_default": true
            # insert concern about user privacy and getting user consent here
            return await ctx.send(
                "You cannot enable this setting for servers with more than 150 members."
            )
        value = not await self.config.guild(ctx.guild).optin_by_default()
        self.optindefault[ctx.guild.id] = value
        await self.config.guild(ctx.guild).optin_by_default.set(value)
        embed = discord.Embed(
            title="Users are now opted in by default in this server:",
            description=f"{value}",
            color=await ctx.embed_color(),
        )
        return await ctx.send(embed=embed)
