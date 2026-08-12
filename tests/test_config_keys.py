"""Every config key the code reads must be registered in `config/defaults.py`.

Red's Config raises AttributeError for an unregistered key, and only at the
moment the line runs — so an unregistered key is a latent crash sitting in
whichever command nobody has tried yet. This walks the source instead of waiting
for that command to be run.

It also fails on the reverse: a registered key nothing reads is either a leftover
from removed functionality or a sign the reader was renamed.
"""

import ast
from pathlib import Path

import pytest

from aiagent.config import defaults

PACKAGE = Path(__file__).resolve().parent.parent / "aiagent"

REGISTERED = {
    "global": set(defaults.DEFAULT_GLOBAL),
    "guild": set(defaults.DEFAULT_GUILD),
    "channel": set(defaults.DEFAULT_CHANNEL),
    "role": set(defaults.DEFAULT_ROLE),
    "member": set(defaults.DEFAULT_MEMBER),
}

SCOPES = {"guild", "guild_from_id", "channel", "role", "member", "member_from_ids"}
SCOPE_ALIASES = {"guild_from_id": "guild", "member_from_ids": "member"}

# Methods on Config/Group that are not config keys.
CONFIG_API = {
    "get_raw", "set_raw", "clear", "clear_all", "set", "get_conf",
    "all_guilds", "all_roles", "all_members", "all_channels",
    "register_global", "register_guild", "register_channel",
    "register_role", "register_member", "items", "keys",
} | SCOPES


def source_files():
    return sorted(
        path for path in PACKAGE.rglob("*.py") if "__pycache__" not in path.parts
    )


def accesses():
    """Yield (path, line, scope, key) for every config key the package reads."""
    for path in source_files():
        tree = ast.parse(path.read_text())

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue

            key = node.attr
            if key in CONFIG_API or key.startswith("_"):
                continue

            value = node.value

            # <...>.config.guild(x).KEY
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr in SCOPES
                and isinstance(value.func.value, ast.Attribute)
                and value.func.value.attr == "config"
            ):
                scope = SCOPE_ALIASES.get(value.func.attr, value.func.attr)
                yield path, node.lineno, scope, key

            # <...>.config.KEY
            elif isinstance(value, ast.Attribute) and value.attr == "config":
                yield path, node.lineno, "global", key


ACCESSES = list(accesses())


def test_the_scan_found_something():
    """A silent zero would make the assertions below vacuous."""
    assert len(ACCESSES) > 20


@pytest.mark.parametrize(
    "path,line,scope,key",
    ACCESSES,
    ids=[f"{p.name}:{line}:{scope}.{key}" for p, line, scope, key in ACCESSES],
)
def test_key_is_registered(path, line, scope, key):
    assert key in REGISTERED[scope], (
        f"{path.relative_to(PACKAGE.parent)}:{line} reads {scope} key '{key}', "
        f"which is not registered in config/defaults.py — this raises AttributeError "
        f"at runtime the first time that line is reached."
    )


def test_no_registered_key_is_unread():
    """A key nothing reads is dead config or a renamed reader."""
    read = {(scope, key) for _path, _line, scope, key in ACCESSES}

    unread = [
        f"{scope}.{key}"
        for scope, keys in REGISTERED.items()
        for key in keys
        if (scope, key) not in read
    ]

    assert not unread, f"registered but never read: {sorted(unread)}"
