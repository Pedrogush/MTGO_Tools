"""The preferences dialog renders the spec, and writes through on change.

Apply-on-change is a deliberate departure from the OK/Cancel dialog: the five
settings already applied live from the ``Settings`` menu this replaces, and
``Language`` re-translates the running UI the moment it is set, so a Cancel would
have to unwind a re-translation. That makes "changing a control calls the
preference's handler" the dialog's whole contract.
"""

from __future__ import annotations

import pytest
import wx

from widgets.preferences import Preference, PreferenceGroup, PreferencesDialog


def _groups(seen: list[object]) -> list[PreferenceGroup]:
    return [
        PreferenceGroup(
            title="Application",
            items=(
                Preference(
                    key="language",
                    label="Language",
                    help="Applies to menus and labels immediately.",
                    options=(("en-US", "English"), ("pt-BR", "Português (Brasil)")),
                    current="pt-BR",
                    on_select=lambda value: seen.append(("lang", value)),
                ),
                Preference(
                    key="check_for_updates",
                    kind="toggle",
                    label="Check for updates",
                    help="Look for a newer release on launch.",
                    checked=False,
                    on_toggle=lambda value: seen.append(("updates", value)),
                ),
            ),
        )
    ]


@pytest.fixture(name="dialog")
def fixture_dialog(wx_app):
    seen: list[object] = []
    dlg = PreferencesDialog(None, _groups(seen))
    yield dlg, seen
    dlg.Destroy()


def test_controls_open_on_the_current_value(dialog) -> None:
    dlg, _seen = dialog
    assert dlg.control_for("language").GetStringSelection() == "Português (Brasil)"
    assert dlg.control_for("check_for_updates").GetValue() is False


def test_choosing_an_option_writes_through_immediately(dialog) -> None:
    dlg, seen = dialog
    choice = dlg.control_for("language")
    choice.SetSelection(0)
    event = wx.CommandEvent(wx.wxEVT_CHOICE, choice.GetId())
    event.SetEventObject(choice)
    event.SetInt(0)
    choice.ProcessEvent(event)
    assert seen == [("lang", "en-US")]


def test_ticking_a_toggle_writes_through_immediately(dialog) -> None:
    dlg, seen = dialog
    check = dlg.control_for("check_for_updates")
    check.SetValue(True)
    event = wx.CommandEvent(wx.wxEVT_CHECKBOX, check.GetId())
    event.SetEventObject(check)
    event.SetInt(1)
    check.ProcessEvent(event)
    assert seen == [("updates", True)]


def test_the_dialog_builds_no_bare_wx_controls_the_guards_forbid(dialog) -> None:
    """A new surface is where raw wx creeps back in; five guards say it must not."""
    dlg, _seen = dialog
    forbidden = (wx.StaticBox, wx.Notebook, wx.StaticLine, wx.SplitterWindow, wx.TextCtrl)
    found: list[str] = []

    def walk(win: wx.Window) -> None:
        for child in win.GetChildren():
            if isinstance(child, forbidden):
                found.append(type(child).__name__)
            walk(child)

    walk(dlg)
    assert found == []


def test_the_only_button_is_the_close_button(dialog) -> None:
    dlg, _seen = dialog
    buttons: list[wx.Button] = []

    def walk(win: wx.Window) -> None:
        for child in win.GetChildren():
            if isinstance(child, wx.Button):
                buttons.append(child)
            walk(child)

    walk(dlg)
    assert [b.GetId() for b in buttons] == [wx.ID_CANCEL]
