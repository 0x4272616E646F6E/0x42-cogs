import discord

from aiagent.dashboard.decorator import dashboard_page
from aiagent.settings.utilities import get_available_models
from aiagent.types.abc import MixinMeta

@dashboard_page(name="bot_owner_per_server_settings", description="Some bot owner-only settings per server", methods=("GET", "POST"), is_owner=True)
async def bot_owner_server_config(self: MixinMeta, guild: discord.Guild, **kwargs):
    import wtforms

    class Form(kwargs["Form"]):
        def __init__(self):
            super().__init__(prefix="bot_owner_server_config_")

        model: wtforms.SelectFieldBase = wtforms.SelectField(
            "LLM (used as the server-wide response model if no more specific model is set)", choices=[], validators=[
                wtforms.validators.InputRequired()])
        whitelist = wtforms.SelectMultipleField(
            "Whitelisted Channels", choices=[(channel.id, channel.name) for channel in guild.text_channels])
        messages_backread = wtforms.IntegerField("History Backread / Message Context Size (Larger contexts are slower to generate)",
                                                 validators=[
                                                     wtforms.validators.InputRequired(),
                                                     wtforms.validators.NumberRange(min=0)
                                                 ])
        messages_backread_seconds = wtforms.IntegerField("History / Context Cutoff Time in Seconds (If messages are spaced further apart, history stops accumulating)",
                                                         description="Time in seconds.",
                                                         validators=[
                                                             wtforms.validators.InputRequired(),
                                                             wtforms.validators.NumberRange(min=0)
                                                         ])

        submit: wtforms.SubmitField = wtforms.SubmitField("Save Changes")

    form: Form = Form()

    form.messages_backread.default = await self.config.guild(guild).messages_backread()
    form.messages_backread_seconds.default = await self.config.guild(guild).messages_backread_seconds()
    form.whitelist.default = [str(id) for id in await self.config.guild(guild).channels_whitelist()]
    models = await get_available_models(self.openai_client)
    form.model.default = await self.config.guild(guild).model()
    form.model.choices = [(model, model) for model in models]


    if form.validate_on_submit():
        model = form.model.data
        new_whitelist = [int(id) for id in form.whitelist.data]
        messages_backread = form.messages_backread.data
        messages_backread_seconds = form.messages_backread_seconds.data
        try:
            await self.config.guild(guild).model.set(model)
            await self.config.guild(guild).channels_whitelist.set(new_whitelist)
            await self.config.guild(guild).messages_backread.set(messages_backread)
            await self.config.guild(guild).messages_backread_seconds.set(messages_backread_seconds)
            self.channels_whitelist[guild.id] = new_whitelist
        except Exception:
            return {
                "status": 1,
                "notifications": [{"message": "Something went wrong while saving the config!", "category": "error"}],
            }
        return {
            "status": 0,
            "notifications": [{"message": "Saved config!", "category": "success"}],
            "redirect_url": kwargs["request_url"],
        }

    source = """<p>Only a subset of available settings. See Discord cog commands for all available settings.</p>{{ form|safe }}"""

    return {
        "status": 0,
        "web_content": {"source": source, "form": form},
    }
