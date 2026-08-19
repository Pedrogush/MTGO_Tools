"""F2 — the mode switch names the mode you are *in*.

The control it replaces was a full-width ``wx.Button`` labelled with the
destination: in Deck Research it said "Deck Builder". These pin the two
properties that fixed it, because both are the kind of thing a later refactor
inverts without anything failing: the **selected** chip is the current mode, and
re-selecting it is a no-op rather than a toggle.
"""

from __future__ import annotations

import pytest

wx = pytest.importorskip("wx")

from widgets.mode_switch import ModeSwitch  # noqa: E402
from widgets.stylize import init_top_level_window  # noqa: E402

MODES = (("research", "Research"), ("builder", "Builder"))


@pytest.fixture(name="switch_frame")
def fixture_switch_frame(wx_app):
    frame = wx.Frame(None)
    init_top_level_window(frame)
    yield frame
    frame.Destroy()


def _click(button: wx.Button) -> None:
    event = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
    event.SetEventObject(button)
    button.ProcessEvent(event)


def _buttons(switch: ModeSwitch) -> dict[str, wx.Button]:
    return {b.GetLabel(): b for b in switch.GetChildren() if isinstance(b, wx.Button)}


def test_both_modes_are_named_and_the_current_one_is_the_selected_chip(switch_frame) -> None:
    chosen: list[str] = []
    switch = ModeSwitch(
        switch_frame, modes=MODES, current="research", on_select=chosen.append
    )
    labels = _buttons(switch)
    assert set(labels) == {"Research", "Builder"}
    # The selection idiom is a *bold* label (stylize_button's toggle+selected
    # branch), which is the only part of it a headless assertion can see -- the
    # fill is a colour and GetBackgroundColour is not an oracle for those.
    assert labels["Research"].GetFont().GetWeight() == wx.FONTWEIGHT_BOLD
    assert labels["Builder"].GetFont().GetWeight() != wx.FONTWEIGHT_BOLD
    assert chosen == []


def test_clicking_the_other_chip_selects_it(switch_frame) -> None:
    chosen: list[str] = []
    switch = ModeSwitch(
        switch_frame, modes=MODES, current="research", on_select=chosen.append
    )
    _click(_buttons(switch)["Builder"])
    assert chosen == ["builder"]


def test_clicking_the_current_chip_does_nothing(switch_frame) -> None:
    # A segmented control is a selection, not a toggle: the old full-width button
    # switched modes on every press, which is why its label had to name the
    # destination in the first place.
    chosen: list[str] = []
    switch = ModeSwitch(
        switch_frame, modes=MODES, current="builder", on_select=chosen.append
    )
    _click(_buttons(switch)["Builder"])
    assert chosen == []


def test_set_current_moves_the_selection_without_firing(switch_frame) -> None:
    chosen: list[str] = []
    switch = ModeSwitch(
        switch_frame, modes=MODES, current="research", on_select=chosen.append
    )
    switch.set_current("builder")
    labels = _buttons(switch)
    assert switch.current == "builder"
    assert labels["Builder"].GetFont().GetWeight() == wx.FONTWEIGHT_BOLD
    assert labels["Research"].GetFont().GetWeight() != wx.FONTWEIGHT_BOLD
    assert chosen == []


def test_the_chips_keep_one_width_as_the_selection_moves(switch_frame) -> None:
    # size_compact_button measures the bold face whatever the current weight, so
    # a row of chips must not reflow when the bold one changes.
    switch = ModeSwitch(
        switch_frame, modes=MODES, current="research", on_select=lambda _v: None
    )
    before = {label: b.GetMinSize().GetWidth() for label, b in _buttons(switch).items()}
    switch.set_current("builder")
    after = {label: b.GetMinSize().GetWidth() for label, b in _buttons(switch).items()}
    assert before == after
