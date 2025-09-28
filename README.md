# 0x42 Cogs

![Nix](https://img.shields.io/badge/Nix%2025.05-5277C3?style=flat-square&logo=nixos&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)

Discord Red Bot Cogs

This repository contains a collection of small, focused cogs (plugins) for the Discord Red bot framework. The cogs aim to provide utilities and experiment-driven integrations such as a local AI assistant.

## List of Cogs

- [Local AI Bot](./aibot/README.md)

## How to Install Cogs (for Red)

Install from a Red repo mirror (replace with your repo URL if different):

```bash
repo add 0x42-cogs https://github.com/0x4272616E646F6E/0x42-cogs
cog install 0x42-cogs <cog>
```

Example:

```bash
cog install 0x42-cogs aibot
```

## Development

This project includes a Nix flake to make development environments reproducible. If you use Nix, you can enter the dev shell and run tests using the included environment.

Quick start with Nix (requires Nix installed):

```bash
# enter the development shell (this may build dependencies the first time)
nix develop

# once inside the shell you can run python tooling, for example:
python -m pip install -e .
pytest -q
```

If you don't use Nix, set up a Python 3.11 virtual environment and install the project requirements. A minimal example:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools
python -m pip install -e .
pytest -q
```

## Running Locally

- Place the cog folders into your Red bot's cogs directory or use `cog install` with the repo URL.
- Configure each cog through Red's cog management UI or via the command line.

## Contributing

Contributions are welcome. Please open issues for bugs or feature requests, and use pull requests for code contributions. Keep changes well-scoped and include tests where possible.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
