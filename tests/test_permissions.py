"""Pins the cog's permission model.

The rule: anything that decides *where the bot is active* or spends the owner's
hardware is bot-owner only; per-server tuning is admin. Subcommands inherit their
group's gate at invocation time, so only commands carrying their own gate appear
here.
"""

from redbot.core.commands.requires import PrivilegeLevel

from aiagent.core.aiagent import AIAgent

# qualified name -> privilege level required, for every explicitly gated command.
EXPECTED_GATES = {
    # activation and bot-wide resources: owner only
    "aiagent add": PrivilegeLevel.BOT_OWNER,
    "aiagent remove": PrivilegeLevel.BOT_OWNER,
    "aiagent model": PrivilegeLevel.BOT_OWNER,
    "aiagentowner": PrivilegeLevel.BOT_OWNER,
    "aiagent response parameters": PrivilegeLevel.BOT_OWNER,
    # per-server tuning: admin
    "aiagent history": PrivilegeLevel.ADMIN,
    "aiagent prompt": PrivilegeLevel.ADMIN,
    "aiagent response": PrivilegeLevel.ADMIN,
    "aiagent trigger": PrivilegeLevel.ADMIN,
    "aiagent optinbydefault": PrivilegeLevel.ADMIN,
    "aiagent config": PrivilegeLevel.ADMIN,
}

GATES = {
    command.qualified_name: command.requires.privilege_level
    for command in AIAgent.__cog_commands__
    if command.requires.privilege_level is not PrivilegeLevel.NONE
}


def test_no_command_is_gated_unexpectedly():
    assert set(GATES) == set(EXPECTED_GATES)


def test_every_gate_is_at_the_expected_level():
    assert GATES == EXPECTED_GATES


def test_channel_whitelisting_is_symmetric():
    """A channel must not be removable by someone who cannot add it back."""
    assert GATES["aiagent add"] == GATES["aiagent remove"]


def test_context_tuning_matches_its_sibling_groups():
    """history is tuning, like prompt/response/trigger — not an activation switch."""
    assert (
        GATES["aiagent history"]
        == GATES["aiagent prompt"]
        == GATES["aiagent response"]
        == GATES["aiagent trigger"]
    )


def test_opt_in_and_opt_out_stay_open_to_everyone():
    for name in ("aiagent optin", "aiagent optout", "aiagent forget"):
        assert name not in GATES


def test_settings_listing_is_not_world_readable():
    """[p]aiagent config exposes whitelists and the endpoint host."""
    assert GATES["aiagent config"] == PrivilegeLevel.ADMIN
