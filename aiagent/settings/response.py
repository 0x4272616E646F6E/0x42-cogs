import asyncio
import json
import logging
import re

import discord
from redbot.core import checks, commands
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.menus import SimpleMenu, start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from aiagent.config.constants import RESERVED_PARAMETERS
from aiagent.config.defaults import DEFAULT_REMOVE_PATTERNS
from aiagent.types.abc import MixinMeta, aiagent

logger = logging.getLogger("red.0x42_cogs.aiagent")


class ResponseSettings(MixinMeta):

    @aiagent.group(name="response")
    @checks.admin_or_permissions(manage_guild=True)
    async def response(self, _):
        """ Change settings used for generated responses

            (All subcommands are per server)
        """
        pass

    @response.group(name="removelist")
    async def removelist(self, _):
        """ Manage the list of regex patterns to remove from responses
        """

    @removelist.command(name="add")
    async def removelist_add(self, ctx: commands.Context, *, regex_pattern: str):
        """Add a regex pattern to the list of patterns to remove from responses"""
        try:
            re.compile(regex_pattern)
        except re.error:
            return await ctx.send("Sorry, but that regex pattern seems to be invalid.")

        removelist_regexes = await self.config.guild(ctx.guild).removelist_regexes()

        if regex_pattern not in removelist_regexes:
            removelist_regexes.append(regex_pattern)
            await self.config.guild(ctx.guild).removelist_regexes.set(removelist_regexes)
            await ctx.send(f"The regex pattern `{regex_pattern}` has been added to the list.")
        else:
            await ctx.send(f"The regex pattern `{regex_pattern}` is already in the list of regex patterns.")

    @removelist.command(name="remove")
    async def removelist_remove(self, ctx: commands.Context, *, number: int):
        """Remove a regex pattern (by number) from the list"""
        removelist_regexes = await self.config.guild(ctx.guild).removelist_regexes()
        if not (1 <= number <= len(removelist_regexes)):
            return await ctx.send("Invalid number.")
        removed_regex = removelist_regexes.pop(number - 1)
        await self.config.guild(ctx.guild).removelist_regexes.set(removelist_regexes)
        await ctx.send(f"The regex pattern `{removed_regex}` has been removed from the list.")

    @removelist.command(name="show")
    async def removelist_show(self, ctx: commands.Context):
        """Show the current regex patterns of strings to removed from responses """
        removelist_regexes = await self.config.guild(ctx.guild).removelist_regexes()
        if not removelist_regexes:
            return await ctx.send("The list of regex patterns is empty.")

        pages = []

        formatted_list = [f"{i+1}. {pattern}" for i, pattern in enumerate(removelist_regexes)]
        formatted_list = "\n".join(formatted_list)
        for text in pagify(formatted_list, page_length=888):
            page = discord.Embed(
                title=f"List of regexes patterns to remove in bot responses in {ctx.guild.name}",
                description=box(text),
                color=await ctx.embed_color())
            pages.append(page)

        if len(pages) == 1:
            return await ctx.send(embed=pages[0])

        for i, page in enumerate(pages):
            page.set_footer(text=f"Page {i+1} of {len(pages)}")

        return await SimpleMenu(pages).start(ctx)

    @removelist.command(name="reset")
    async def removelist_reset(self, ctx: commands.Context):
        """Reset the list of regexes to default """
        embed = discord.Embed(
            title="Are you sure?",
            description="This will reset this server's removelist to default.",
            color=await ctx.embed_color())
        confirm = await ctx.send(embed=embed)
        start_adding_reactions(confirm, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(confirm, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", timeout=10.0, check=pred)
        except asyncio.TimeoutError:
            return await confirm.edit(embed=discord.Embed(title="Cancelled.", color=await ctx.embed_color()))
        if pred.result is False:
            return await confirm.edit(embed=discord.Embed(title="Cancelled.", color=await ctx.embed_color()))
        else:
            await self.config.guild(ctx.guild).removelist_regexes.set(DEFAULT_REMOVE_PATTERNS)
            return await confirm.edit(embed=discord.Embed(title="Removelist reset.", color=await ctx.embed_color()))

    @response.command(name="toggleoptinembed")
    async def toggle_optin_embed(self, ctx):
        """Toggles warning embed about opt-in on or off"""
        current = await self.config.guild(ctx.guild).optin_disable_embed()
        await self.config.guild(ctx.guild).optin_disable_embed.set(not current)

        embed = discord.Embed(title="Senting Opt-in Warning Embed", color=await ctx.embed_color())
        embed.description = f"{current}"
        if not current:
            embed.add_field(
                name=":warning: Warning :warning:",
                value="Users not yet opt-in/out will be unaware their messages are not being processed",
                inline=False
            )

        await ctx.send(embed=embed)

    @response.command(name="parameters")
    @checks.is_owner()
    async def set_custom_parameters(self, ctx: commands.Context, *, json_block: str):
        """ Set custom parameters for an endpoint using a JSON code block

            To reset parameters to default, use `[p]aiagent response parameters reset`
            To show current parameters, use `[p]aiagent response parameters show`

            Example command:
            `[p]aiagent response parameters ```{"frequency_penalty": 2.0, "max_tokens": 200}``` `

            Which parameters are accepted depends on your LLM server
            (eg. `temperature`, `top_p`, `max_tokens`, `stop`, `seed`).
            `model`, `messages` and `stream` are set by the cog and cannot be overridden.
        """
        if json_block in ['reset', 'clear']:
            await self.config.guild(ctx.guild).parameters.set(None)
            return await ctx.send("Parameters reset to default")

        embed = discord.Embed(title="Custom Parameters", color=await ctx.embed_color())
        parameters = await self.config.guild(ctx.guild).parameters()
        data = {} if parameters is None else json.loads(parameters)

        if json_block not in ['show', 'list']:
            if not json_block.startswith("```"):
                return await ctx.send(":warning: Please use a code block (`` eg. ```json ``)")

            json_block = json_block.replace("```json", "").replace("```", "")

            try:
                data = json.loads(json_block)
            except json.JSONDecodeError:
                return await ctx.channel.send(":warning: Invalid JSON format!")

            invalid_keys = [key for key in data.keys() if key in RESERVED_PARAMETERS]
            if invalid_keys:
                invalid_keys_str = ", ".join([f"`{key}`" for key in invalid_keys])
                return await ctx.send(f":warning: Invalid JSON! Please remove \"{invalid_keys_str}\" key from your JSON.")

            await self.config.guild(ctx.guild).parameters.set(json.dumps(data))

        if not data:
            embed.description = "No custom parameters set."
        else:
            embed.add_field(
                name=":warning: Warning :warning:",
                value="No checks were done to see if parameters were compatible\n----------------------------------------",
                inline=False
            )
            for key, value in data.items():
                embed.add_field(name=key, value=f"```{json.dumps(value, indent=4)}```", inline=False)

        await ctx.send(embed=embed)
