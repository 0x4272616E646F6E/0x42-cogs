# 0x42 Cogs

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![Red-DiscordBot](https://img.shields.io/badge/Red--DiscordBot-3.5.1%2B-red?style=flat-square)

Discord Red Bot Cogs

This repository contains a collection of small, focused cogs (plugins) for the Discord Red bot framework.

## List of Cogs

- [AI Agent](./aiagent/README.md) — an AI chat bot backed by any OpenAI-compatible endpoint, built for a local LLM server.

## How to Install Cogs (for Red)

```bash
[p]repo add 0x42-cogs https://github.com/0x4272616E646F6E/0x42-cogs
[p]cog install 0x42-cogs aiagent
[p]load aiagent
```

## Development

Red-DiscordBot requires `>=3.8.1,<3.12`, so **Python 3.11 is the newest supported
version** — use it:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install "Red-DiscordBot>=3.5.1" "openai>=2.0,<3" "pydantic>=2.7,<2.12" "httpx>=0.27,<1" "tiktoken>=0.7" "tenacity>=8.2.3"
```

`aiohttp` and `discord.py` are intentionally not listed: Red pins them exactly
(`aiohttp==3.9.5`, `discord-py==2.7.1`), and installing different versions alongside
it breaks the bot. `pydantic` is capped below 2.12 for the same reason — see
[the cog README](./aiagent/README.md#why-pydantic-is-capped).

To work on a cog against a running bot, add the checkout as a local repo:

```bash
[p]repo add local /path/to/0xBrandon-cogs
```

## Contributing

Contributions are welcome. Please open issues for bugs or feature requests, and use pull requests for code contributions. Keep changes well-scoped.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
