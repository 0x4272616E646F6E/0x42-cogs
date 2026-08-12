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

**Tag the bot to talk to it.** In a whitelisted channel, mention it or reply to one of
its messages and it answers — every time, no dice roll:

```
@YourBot what is the discrete logarithm problem?
```

It never speaks unprompted. Anything that doesn't tag it is ignored, even in a
whitelisted channel.

Users must opt in (bot-wide) before their messages are used:

```
[p]aiagent optin
```

Admins can modify prompt settings with:

```
[p]aiagent prompt
```

See all settings with `[p]aiagent` and `[p]aiagentowner`. Some settings are bot owner only.

## Rate limits

To stop one person, or one busy moment, from saturating your GPU:

- each user waits **10 seconds** between mention-triggered responses
- the bot generates at most **2 responses at once**, bot-wide
- beyond that, requests **queue** — up to **5 per channel**

If the bot is busy you get an ⏳ and your message is answered when a slot frees.
You get a 💤 instead when the queue for that channel is full, or when the wait
would have made the answer too late to be useful: nothing older than **60 seconds**
is answered, because a reply arriving after the conversation moved on is worse
than no reply. `/chat` keeps its own cooldown on top of this.

The values live in `aiagent/core/throttle.py`.

## Context size

The cog estimates how much channel history fits in the model's context window from the
model's name (see `aiagent/config/models.py`). If the estimate is wrong for your
model, set it explicitly per server:

```
[p]aiagent history customtokenlimit 32000
```

Token counts shown by the cog are estimates — local models use their own tokenizers,
which the OpenAI API doesn't expose. The estimator deliberately runs high (roughly 1x–2.5x
a real tokenizer's count) so a long history can't overflow the model's context; see
`aiagent/utils/tokens.py`. The cog downloads nothing to do this.

## Sampling parameters

Set the common knobs directly (per server, admin only):

```
[p]aiagent response temperature 0.8
[p]aiagent response top_k 40
[p]aiagent response repetitionpenalty 1.1
[p]aiagent response sampling          # show what's set
```

Leave the value off to unset one, e.g. `[p]aiagent response top_k`.

`temperature` is part of the OpenAI API and is sent as a normal field. `top_k` and
`repetition_penalty` are not — they are sent as extra top-level JSON fields, which is
where llama.cpp, vLLM and LM Studio look for them. A server that doesn't recognise a
field either ignores it or replies 400, in which case the bot reacts ⚠️ and logs which
parameters were sent.

Anything else your server supports goes through the raw JSON command, and is routed the
same way:

```
[p]aiagent response parameters ```{"min_p": 0.05, "repeat_penalty": 1.1}```
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
| Installed by Downloader | `openai>=2.0,<3`, `pydantic>=2.7,<2.12`, `httpx>=0.27,<1` |

`discord.py` comes from Red itself, which pins it exactly (`discord-py==2.7.1`), so this
cog does not declare it.

### Why pydantic is capped

Do not remove `pydantic<2.12` while Red pins `typing-extensions==4.13.2`.

`openai` pulls in `pydantic`, and pydantic 2.12+ needs `typing-extensions>=4.14.1`
(its `pydantic_core` imports `Sentinel`, added in typing-extensions 4.15). Downloader
installs a new enough typing-extensions into its own `lib/` folder, but Red has already
imported the pinned 4.13.2 from its venv by the time a cog loads, so the venv copy wins
and the cog fails at import with:

```
ImportError: cannot import name 'Sentinel' from 'typing_extensions'
```

pydantic 2.11.x uses `pydantic-core` 2.33.x, which only needs `typing-extensions>=4.12.2`.
Once Red ships a newer typing-extensions, this cap can be raised.

## Privacy

Messages from opted-in users in whitelisted channels — plus recent channel history for
context — are sent to whatever endpoint is configured, so point it somewhere you trust.
Message content is not stored persistently by this cog; only opt-in/opt-out user IDs and
any prompt overrides an admin sets are saved.
