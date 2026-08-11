import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import discord
from redbot.core import checks, commands
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from aiagent.config.defaults import DEFAULT_ENDPOINT
from aiagent.core.llm_client import setup_llm_client, validate_endpoint
from aiagent.settings.utilities import get_tokens, truncate_prompt
from aiagent.types.abc import MixinMeta

logger = logging.getLogger("red.0x42_cogs.aiagent")


class OwnerSettings(MixinMeta):
    @commands.group(aliases=["ai_agentowner"])
    @checks.is_owner()
    async def aiagentowner(self, _):
        """For some settings that apply bot-wide."""
        pass

    @aiagentowner.command(name="maxpromptlength")
    async def max_prompt_length(self, ctx: commands.Context, length: int):
        """Sets the maximum character length of a prompt that can set by admins in any server.

            (Does not apply to already set prompts, only new ones)
        """
        if length < 1:
            return await ctx.send("Please enter a positive integer.")
        await self.config.max_prompt_length.set(length)
        embed = discord.Embed(
            title="The maximum prompt length is now:",
            description=f"{length}",
            color=await ctx.embed_color(),
        )
        return await ctx.send(embed=embed)

    @aiagentowner.command(name="maxtopiclength")
    async def max_random_prompt_length(self, ctx: commands.Context, length: int):
        """Sets the maximum character length of a random prompt that can set by any server.

            (Does not apply to already set prompts, only new ones)
        """
        if length < 1:
            return await ctx.send("Please enter a positive integer.")
        await self.config.max_random_prompt_length.set(length)
        embed = discord.Embed(
            title="The maximum topic length is now:",
            description=f"{length}",
            color=await ctx.embed_color(),
        )
        return await ctx.send(embed=embed)

    @aiagentowner.command()
    async def endpoint(self, ctx: commands.Context, url: Optional[str]):
        """Sets the URL of the OpenAI-compatible LLM server to use

        No API key is needed for a typical self-hosted server. If yours checks one,
        set it with `[p]set api aiagent api_key,<KEY>`.

        **Arguments:**
        - `url`: The url of your LLM server, eg. `http://localhost:11434/v1`
        OR
        - `reset`: Reset back to the default (`http://localhost:11434/v1`)

        Common endpoints:
        - Ollama: `http://localhost:11434/v1`
        - LM Studio: `http://localhost:1234/v1`
        - llama.cpp / llama-server: `http://localhost:8080/v1`
        - vLLM: `http://localhost:8000/v1`
        """
        if url in ["clear", "reset", "default"]:
            url = DEFAULT_ENDPOINT

        if not url:
            current = await self.config.llm_endpoint()
            embed = discord.Embed(
                title="The LLM endpoint is currently:",
                description=f"`{current}`",
                color=await ctx.embed_color(),
            )
            return await ctx.send(embed=embed)

        error = validate_endpoint(url)
        if error:
            return await ctx.send(f":warning: {error}")

        previous_url = await self.config.llm_endpoint()

        # Save the current per-server models before switching, so that switching
        # back to this endpoint later restores them.
        if previous_url:
            history = await self.config.endpoint_model_history()
            history[previous_url] = {
                str(guild_id): {"chat_model": await self.config.guild_from_id(guild_id).model()}
                for guild_id in await self.config.all_guilds()
            }
            await self.config.endpoint_model_history.set(history)

        await self.config.llm_endpoint.set(url)

        await ctx.message.add_reaction("🔄")
        try:
            self.openai_client = await setup_llm_client(self.bot, self.config)
            models = await self.openai_client.models.list()
        except Exception:
            logger.warning(f"Could not reach LLM endpoint {url}", exc_info=True)
            await self.config.llm_endpoint.set(previous_url)
            self.openai_client = await setup_llm_client(self.bot, self.config)
            return await ctx.send(
                f":warning: Could not reach `{url}`. Is your LLM server running?\n"
                "The endpoint has been left unchanged. See the logs for details."
            )
        finally:
            await ctx.message.remove_reaction("🔄", ctx.me)

        embed = discord.Embed(
            title="LLM endpoint",
            description=f"Endpoint set to `{url}`.",
            color=await ctx.embed_color(),
        )

        # Restore models previously used on this endpoint, otherwise fall back to
        # whatever the server offers first.
        saved_models = (await self.config.endpoint_model_history()).get(url, {})
        fallback_model = models.data[0].id if models.data else ""

        restored_count = 0
        guilds_with_parameters = []
        for guild_id in await self.config.all_guilds():
            guild_config = self.config.guild_from_id(guild_id)

            if str(guild_id) in saved_models:
                await guild_config.model.set(saved_models[str(guild_id)]["chat_model"])
                restored_count += 1
            else:
                await guild_config.model.set(fallback_model)

            if await guild_config.parameters():
                guild = self.bot.get_guild(guild_id)
                guilds_with_parameters.append(str(guild.name if guild else guild_id))

        total_guilds = len(await self.config.all_guilds())
        if restored_count:
            value = f"Restored previously set models on this endpoint for {restored_count} servers."
            if restored_count < total_guilds:
                value += f"\nA further {total_guilds - restored_count} servers were set to `{fallback_model}`."
            embed.add_field(name="🔄 Restored", value=value, inline=False)
        elif total_guilds:
            embed.add_field(
                name="🔄 Reset",
                value=f"All per-server models have been set to `{fallback_model}`.",
                inline=False,
            )

        if guilds_with_parameters:
            embed.add_field(
                name=":warning: Caution",
                value=f"Custom parameters have been set in the following servers: `{', '.join(guilds_with_parameters)}`\nThey may not work with the new endpoint!",
                inline=False,
            )

        embed.set_footer(text=f"{len(models.data)} models available. See [p]aiagent model list")
        await ctx.send(embed=embed)

    @aiagentowner.command()
    async def timeout(self, ctx: commands.Context, seconds: int):
        """ Sets the request timeout to the LLM endpoint

            Self-hosted models on modest hardware can be slow — raise this if
            responses are timing out.
        """

        if seconds < 1:
            return await ctx.send(":warning: Please enter a positive integer.")

        await self.config.llm_endpoint_request_timeout.set(seconds)
        self.openai_client = await setup_llm_client(self.bot, self.config)

        embed = discord.Embed(
            title="The request timeout is now:",
            description=f"`{seconds}` seconds",
            color=await ctx.embed_color(),
        )
        return await ctx.send(embed=embed)

    @aiagentowner.command(name="exportconfig")
    async def export_config(self, ctx: commands.Context):
        """Exports the current config to a json file

           :warning: JSON backend only
        """
        path = Path(cog_data_path(self) / "settings.json")

        if not path.exists():
            return await ctx.send(":warning: Export is only supported for json backends")

        await ctx.send(
            file=discord.File(path, filename="aiagent_config.json")
        )
        await ctx.tick()

    @aiagentowner.command(name="importconfig")
    async def import_config(self, ctx: commands.Context):
        """ Imports a config from json file (:warning: No checks are done)

            Make sure your new config is valid, and the old config is backed up.

           :warning: JSON backend only
        """
        if not ctx.message.attachments:
            return await ctx.send(":warning: No file was attached.")

        file = ctx.message.attachments[0]
        try:
            new_config = json.loads(await file.read())
        except json.JSONDecodeError:
            return await ctx.send(":warning: Invalid JSON format!")

        path = Path(cog_data_path(self) / "settings.json")

        if not path.exists():
            return await ctx.send(":warning: Import is only supported for json backends")

        embed = discord.Embed(
            title="Have you backed up your current config?",
            description=f":warning: This will overwrite the current config, and you will lose existing settings! \
                \n :warning: You may also break the cog or bot, if the config is invalid. \
                \n To fix, make sure you can access the config file: \n `{path}`",
            color=await ctx.embed_color())
        confirm = await ctx.send(embed=embed)
        start_adding_reactions(confirm, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(confirm, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", timeout=30.0, check=pred)
        except asyncio.TimeoutError:
            return await confirm.edit(embed=discord.Embed(title="Cancelled.", color=await ctx.embed_color()))
        if pred.result is False:
            return await confirm.edit(embed=discord.Embed(title="Cancelled.", color=await ctx.embed_color()))

        with path.open("w") as f:
            json.dump(new_config, f, indent=4)

        return await confirm.edit(embed=discord.Embed(
            title="Overwritten!",
            description="You will need to restart the bot for the changes to take effect.",
            color=await ctx.embed_color()))

    @aiagentowner.command(name="prompt")
    async def global_prompt(self, ctx: commands.Context, *, prompt: Optional[str]):
        """ Set the global default prompt for aiagent.

            Leave blank to delete the currently set global prompt, and use the build-in default prompt.

            **Arguments**
                - `prompt` The prompt to set.
        """
        if not prompt and ctx.message.attachments:
            if not ctx.message.attachments[0].filename.endswith(".txt"):
                return await ctx.send(":warning: Invalid attachment. Must be a `.txt` file.")
            prompt = (await ctx.message.attachments[0].read()).decode("utf-8")

        if not prompt:
            await self.config.custom_text_prompt.set(None)
            return await ctx.send("The global prompt is now reset to the default prompt")

        await self.config.custom_text_prompt.set(prompt)

        embed = discord.Embed(
            title="The global prompt is now changed to:",
            description=f"{truncate_prompt(prompt)}",
            color=await ctx.embed_color())
        embed.add_field(name="Tokens", value=await get_tokens(self.config, ctx, prompt))
        return await ctx.send(embed=embed)
