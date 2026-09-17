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


# ------------------------------------------------------------------ path (#1034)


class _FakeDirDialog:
    chosen: str | None = None
    opened_at: list[str] = []

    def __init__(self, parent, message="", defaultPath="", style=0):  # noqa: ANN001
        _FakeDirDialog.opened_at.append(defaultPath)

    def __enter__(self):
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def ShowModal(self) -> int:  # noqa: N802 - wx API
        return wx.ID_OK if _FakeDirDialog.chosen else wx.ID_CANCEL

    def GetPath(self) -> str:  # noqa: N802 - wx API
        return _FakeDirDialog.chosen or ""


@pytest.fixture(name="path_dialog")
def fixture_path_dialog(wx_app, monkeypatch: pytest.MonkeyPatch):
    seen: list[str] = []
    _FakeDirDialog.chosen = None
    _FakeDirDialog.opened_at = []
    monkeypatch.setattr(wx, "DirDialog", _FakeDirDialog)
    groups = [
        PreferenceGroup(
            title="Deck data",
            items=(
                Preference(
                    key="default_deck_save_path",
                    kind="path",
                    label="Default deck folder",
                    help="Where Save Deck and Load Deck open.",
                    value="",
                    placeholder="Not set (Documents)",
                    on_path=seen.append,
                ),
            ),
        )
    ]
    dlg = PreferencesDialog(None, groups)
    yield dlg, seen
    dlg.Destroy()


def _press(button: wx.Button) -> None:
    event = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
    event.SetEventObject(button)
    button.ProcessEvent(event)


def test_an_unset_folder_shows_the_placeholder_and_cannot_be_cleared(path_dialog) -> None:
    dlg, _seen = path_dialog
    assert dlg.control_for("default_deck_save_path").GetLabel() == "Not set (Documents)"
    _browse, clear = dlg.path_buttons_for("default_deck_save_path")
    assert not clear.IsEnabled()


def test_browse_picks_a_folder_and_writes_it_through(path_dialog, tmp_path) -> None:
    dlg, seen = path_dialog
    _FakeDirDialog.chosen = str(tmp_path)
    browse, clear = dlg.path_buttons_for("default_deck_save_path")

    _press(browse)

    assert seen == [str(tmp_path)]
    assert dlg.control_for("default_deck_save_path").GetLabel() == str(tmp_path)
    assert clear.IsEnabled()

    # Browsing again starts from the folder already chosen.
    _FakeDirDialog.chosen = None
    _press(browse)
    assert _FakeDirDialog.opened_at == ["", str(tmp_path)]
    assert seen == [str(tmp_path)]  # cancelled: nothing written


def test_clear_unsets_the_folder(path_dialog, tmp_path) -> None:
    dlg, seen = path_dialog
    _FakeDirDialog.chosen = str(tmp_path)
    browse, clear = dlg.path_buttons_for("default_deck_save_path")
    _press(browse)

    _press(clear)

    assert seen == [str(tmp_path), ""]
    assert dlg.control_for("default_deck_save_path").GetLabel() == "Not set (Documents)"
    assert not clear.IsEnabled()
