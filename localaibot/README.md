# How to use

The bot will generate responses in whitelisted channels. Bot owners can add a channel to a server's whitelist using:

```bash
[p]aibot add <CHANNEL>
```

Bot owners can change the percentage of eligible messages to reply to:

```bash
[p]aibot percent <PERCENT>
```

Users will also have to opt-in (bot-wide) into having their messages used:

```bash
[p]aibot optin
```

Admins can modify prompt settings in:

```bash
[p]aibot prompt
```

Bot owners can also manage/enable function calling (eg. opening links or performing Google searches) using:

```bash
[p]aibot functions
```

Some additional settings are restricted to bot owner only.
See other settings using:

```bash
[p]aibot
[p]aibotowner
```

---

## Prompt/Topics Dynamic Variables

Prompts and topics can include certain dynamic variables by including one of the following strings:

- `{botname}` - the bot's current nickname or username
- `{botowner}` - the bot owner's username
- `{authorname}` - the author of the message the bot is activated on
- `{authortoprole}` - the author's highest role
- `{authormention}` - the author's mention in string format
- `{serveremojis}` - all of the server emojis, in a string format (eg. `<:emoji:12345> <:emoji2:78912>`)
- `{servername}` - the server name
- `{channelname}` - the current channel name
- `{channeltopic}` - the current channel description/topic
- `{currentdate}` - the current date eg. 2023/08/31 (based on host timezone)
- `{currentweekday}` - the current weekday eg. Monday (based on host timezone)
- `{currenttime}` - the current 24-hour time eg. 21:59 (based on host timezone)
- `{randomnumber}` - a random number between 0 - 100

Remove list regex patterns only support `{authorname}` (will use authors of last 10 messages) and `{botname}` placeholders.

---

### Custom OpenAI endpoint

OpenAI-Compatible API endpoints can be used. (eg. `llamacpp`, `ollama`, `vllm`)

Compatibility may vary and is not guaranteed.

Bot owners can set this globally using:

```bash
[p]aibotowner endpoint <ENDPOINT>
```

```bash
[p]aibot response parameters
```
