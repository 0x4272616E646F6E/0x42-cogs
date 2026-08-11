# AI Agent

Human-like Discord chat powered by an LLM **you** run.

There is one setting for the backend: the URL of any OpenAI-compatible endpoint. The cog
has no provider-specific configuration and needs no API key by default — it's built for
a local LLM server, and anything else that speaks the same API works the same way.

## Setup

1. Run a local LLM server that speaks the OpenAI API. Any of these work:

   | Server | Default endpoint |
   |---|---|
   | [Ollama](https://ollama.com) | `http://localhost:11434/v1` |
   | [LM Studio](https://lmstudio.ai) | `http://localhost:1234/v1` |
   | [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`) | `http://localhost:8080/v1` |
   | [vLLM](https://github.com/vllm-project/vllm) | `http://localhost:8000/v1` |

2. Point the cog at it (defaults to Ollama's endpoint, so this is optional if you use Ollama on the same host):

   ```
   [p]aiagentowner endpoint http://localhost:11434/v1
   ```

   The endpoint is tested before it's saved; if the server can't be reached, the old
   value is kept.

3. Pick a model. Only models your server actually serves are accepted:

   ```
   [p]aiagent model list
   [p]aiagent model gpt-oss:20b
   ```

4. Whitelist a channel and opt in:

   ```
   [p]aiagent add #general
   [p]aiagent optin
   ```

If your hardware is slow, raise the request timeout (default 60s):

```
[p]aiagentowner timeout 180
```

If your endpoint requires an API key (eg. vLLM started with `--api-key`, or an auth
proxy in front of it), set one — otherwise skip this entirely:

```
[p]set api aiagent api_key,<KEY>
```

## Usage

The bot generates responses in whitelisted channels. Bot owners can change the
percentage of eligible messages it replies to:

```
[p]aiagent percent <PERCENT>
```

Users must opt in (bot-wide) before their messages are used:

```
[p]aiagent optin
```

Admins can modify prompt settings with:

```
[p]aiagent prompt
```

See all settings with `[p]aiagent` and `[p]aiagentowner`. Some settings are bot owner only.

## Context size

The cog estimates how much channel history fits in the model's context window from the
model's name (see `aiagent/config/models.py`). If the estimate is wrong for your
model, set it explicitly per server:

```
[p]aiagent history customtokenlimit 32000
```

Token counts shown by the cog are estimates — local models use their own tokenizers,
which the OpenAI API doesn't expose.

## Sampling parameters

Whatever your server accepts (`temperature`, `top_p`, `max_tokens`, `stop`, `seed`, ...):

```
[p]aiagent response parameters ```{"temperature": 0.8, "max_tokens": 200}```
```

`model`, `messages` and `stream` are set by the cog and can't be overridden.

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

## Requirements

| | |
|---|---|
| Python | 3.11 (Red supports `>=3.8.1,<3.12`, so this is the newest usable) |
| Red-DiscordBot | 3.5.1 or newer |
| Installed by Downloader | `openai>=2.0,<3`, `httpx>=0.27,<1`, `tiktoken>=0.7`, `tenacity>=8.2.3` |

`aiohttp` and `discord.py` come from Red itself, which pins them exactly, so this cog
does not declare them.

## Privacy

Messages from opted-in users in whitelisted channels — plus recent channel history for
context — are sent to whatever endpoint is configured, so point it somewhere you trust.
Message content is not stored persistently by this cog; only opt-in/opt-out user IDs and
any prompt overrides an admin sets are saved.
