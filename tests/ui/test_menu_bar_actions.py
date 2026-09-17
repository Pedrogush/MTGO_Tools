"""Action titles on the menu bar (#1034): built like menu titles, clicked like buttons.

``Save`` and ``Load`` sit on the bar beside ``File Tools Help`` and must be
indistinguishable from them at rest and on hover -- the same ``wx.Button``, the
same ``flat``/``ghost`` styling -- while a click runs the action instead of
popping a menu up.
"""

from __future__ import annotations

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from widgets.menu_bar import AppMenuBar, MenuEntry, MenuSpec

BUTTON_KIND_ATTR = "_mtgo_button_kind"


def _kinds(bar: AppMenuBar) -> dict[str, str]:
    return {
        child.GetLabel(): getattr(child, BUTTON_KIND_ATTR)[0]
        for child in bar.GetChildren()
        if isinstance(child, wx.Button)
    }


@pytest.fixture(name="bar_and_calls")
def fixture_bar_and_calls(wx_app: wx.App, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    popups: list[str] = []
    frame = wx.Frame(None)
    sizer = wx.BoxSizer(wx.VERTICAL)
    frame.SetSizer(sizer)
    specs = [
        MenuSpec("File", lambda: [MenuEntry(label="File item")]),
        MenuSpec("Save", on_activate=lambda: calls.append("save")),
        MenuSpec("Load", on_activate=lambda: calls.append("load")),
    ]
    bar = AppMenuBar(frame, specs)
    sizer.Add(bar, 0, wx.EXPAND)
    frame.Layout()

    def fake_popup(self, menu, pos=wx.DefaultPosition):  # noqa: ANN001, ARG001
        popups.append("popup")
        return True

    monkeypatch.setattr(wx.Window, "PopupMenu", fake_popup)
    # Park the pointer well away from the bar so the post-action highlight is
    # decided by the rule, not by wherever the test machine's mouse happens to be.
    monkeypatch.setattr(wx, "GetMousePosition", lambda: wx.Point(-10_000, -10_000))
    yield bar, calls, popups
    frame.Destroy()
    pump_ui_events(wx_app)


def _click(bar: AppMenuBar, title: str) -> None:
    button = bar._button_for(title)
    assert button is not None
    event = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
    event.SetEventObject(button)
    button.ProcessEvent(event)


def test_action_titles_are_on_the_bar_in_order(bar_and_calls) -> None:
    bar, _calls, _popups = bar_and_calls
    assert bar.titles() == ["File", "Save", "Load"]
    assert [bar.is_action(t) for t in bar.titles()] == [False, True, True]
    assert list(bar.entries("Save")) == []


def test_action_titles_rest_in_the_same_style_as_menu_titles(bar_and_calls) -> None:
    bar, _calls, _popups = bar_and_calls
    assert _kinds(bar) == {"File": "flat", "Save": "flat", "Load": "flat"}


def test_clicking_an_action_title_runs_it_and_pops_nothing_up(bar_and_calls) -> None:
    bar, calls, popups = bar_and_calls
    _click(bar, "Save")
    _click(bar, "Load")
    assert calls == ["save", "load"]
    assert popups == []


def test_clicking_a_menu_title_still_pops_its_menu(bar_and_calls) -> None:
    bar, calls, popups = bar_and_calls
    _click(bar, "File")
    assert popups == ["popup"]
    assert calls == []


def test_hover_lights_an_action_title_like_a_menu_title(bar_and_calls) -> None:
    bar, _calls, _popups = bar_and_calls
    for title in ("File", "Save"):
        button = bar._button_for(title)
        button.ProcessEvent(wx.MouseEvent(wx.wxEVT_ENTER_WINDOW))
    assert _kinds(bar) == {"File": "ghost", "Save": "ghost", "Load": "flat"}


def test_the_highlight_is_dropped_after_the_action_once_the_pointer_has_left(
    bar_and_calls,
) -> None:
    bar, _calls, _popups = bar_and_calls
    bar._button_for("Save").ProcessEvent(wx.MouseEvent(wx.wxEVT_ENTER_WINDOW))
    _click(bar, "Save")
    assert _kinds(bar)["Save"] == "flat"


def test_the_highlight_stays_while_the_pointer_is_still_on_the_title(
    bar_and_calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    bar, _calls, _popups = bar_and_calls
    button = bar._button_for("Load")
    monkeypatch.setattr(wx, "GetMousePosition", lambda: button.GetScreenRect().GetTopLeft())
    _click(bar, "Load")
    assert _kinds(bar)["Load"] == "ghost"


def test_an_action_that_rebuilds_the_bar_does_not_touch_a_dead_button(wx_app: wx.App) -> None:
    frame = wx.Frame(None)
    try:
        holder: dict[str, AppMenuBar] = {}

        def rebuild() -> None:
            holder["bar"].set_menus([MenuSpec("Salvar", on_activate=lambda: None)])

        bar = AppMenuBar(frame, [MenuSpec("Save", on_activate=rebuild)])
        holder["bar"] = bar
        assert bar.run_action("Save") is True  # would raise on a stale wrapper
        assert bar.titles() == ["Salvar"]
    finally:
        frame.Destroy()
        pump_ui_events(wx_app)
