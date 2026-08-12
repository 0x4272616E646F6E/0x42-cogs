"""The opt-in / opt-out buttons on the consent embed.

This is the only consent surface a normal user touches, and it is two symmetric
handlers that both edit two lists. Getting a branch wrong here opts someone in
who pressed "Opt Out", so the tests assert both lists after every press.
"""

import asyncio

from aiagent.messages_list.opt_view import OptView

from . import fakes

USER = 42
SOMEONE_ELSE = 7


class Response:
    def __init__(self):
        self.messages = []

    async def send_message(self, content, **_kwargs):
        self.messages.append(content)


class Interaction:
    def __init__(self, user_id=USER):
        self.user = fakes.Author(id=user_id)
        self.response = Response()


def view_for(optin=(), optout=()):
    config = fakes.Config(optin=list(optin), optout=list(optout))
    return OptView(config), config


def press_opt_in(view, interaction):
    return asyncio.run(OptView.confirm(view, interaction, None))


def press_opt_out(view, interaction):
    return asyncio.run(OptView.cancel(view, interaction, None))


# --- opting in --------------------------------------------------------------

def test_opting_in_adds_the_user():
    view, config = view_for()
    interaction = Interaction()

    press_opt_in(view, interaction)

    assert USER in config.optin.value
    assert "now opted in" in interaction.response.messages[0]


def test_opting_in_clears_a_previous_opt_out():
    """The two lists must never both contain the same user."""
    view, config = view_for(optout=[USER])
    press_opt_in(view, Interaction())

    assert USER in config.optin.value
    assert USER not in config.optout.value


def test_opting_in_twice_changes_nothing():
    view, config = view_for(optin=[USER])
    interaction = Interaction()

    press_opt_in(view, interaction)

    assert config.optin.value.count(USER) == 1
    assert "already opted in" in interaction.response.messages[0]


def test_opting_in_leaves_other_users_alone():
    view, config = view_for(optin=[SOMEONE_ELSE], optout=[])
    press_opt_in(view, Interaction())

    assert SOMEONE_ELSE in config.optin.value
    assert USER in config.optin.value


# --- opting out -------------------------------------------------------------

def test_opting_out_adds_the_user():
    view, config = view_for()
    interaction = Interaction()

    press_opt_out(view, interaction)

    assert USER in config.optout.value
    assert "now opted out" in interaction.response.messages[0]


def test_opting_out_clears_a_previous_opt_in():
    view, config = view_for(optin=[USER])
    press_opt_out(view, Interaction())

    assert USER in config.optout.value
    assert USER not in config.optin.value


def test_opting_out_twice_changes_nothing():
    view, config = view_for(optout=[USER])
    interaction = Interaction()

    press_opt_out(view, interaction)

    assert config.optout.value.count(USER) == 1
    assert "already opted out" in interaction.response.messages[0]


def test_opting_out_does_not_opt_anyone_else_out():
    view, config = view_for(optin=[SOMEONE_ELSE])
    press_opt_out(view, Interaction())

    assert SOMEONE_ELSE in config.optin.value
    assert SOMEONE_ELSE not in config.optout.value


# --- the pair, together -----------------------------------------------------

def test_a_user_is_never_on_both_lists():
    """Whatever the sequence of presses, the two lists stay exclusive."""
    view, config = view_for()

    for press in (press_opt_in, press_opt_out, press_opt_in, press_opt_in, press_opt_out):
        press(view, Interaction())
        assert not (USER in config.optin.value and USER in config.optout.value)


def test_the_final_press_wins():
    view, config = view_for()

    press_opt_in(view, Interaction())
    press_opt_out(view, Interaction())

    assert USER in config.optout.value
    assert USER not in config.optin.value


def test_each_user_is_tracked_separately():
    view, config = view_for()

    press_opt_in(view, Interaction(user_id=USER))
    press_opt_out(view, Interaction(user_id=SOMEONE_ELSE))

    assert config.optin.value == [USER]
    assert config.optout.value == [SOMEONE_ELSE]


def test_both_buttons_are_present_on_the_view():
    view, _ = view_for()
    labels = {child.label for child in view.children}
    assert labels == {"Opt In", "Opt Out"}
