"""Tests for the shared marquee machinery and per-view rubber-band selection.

Covers the surface-marker opt-in, the :class:`MarqueeController` lifecycle, and
that the grid and table views select the cards a rectangle covers — the contract
that lets a marquee be driven from any view (and started from any marked surface).
"""

from __future__ import annotations

from typing import Any

import pytest
import wx

from widgets.mana_icon_factory import ManaIconFactory
from widgets.panels.card_table_panel.grid_view import DeckGridView
from widgets.panels.card_table_panel.marquee import (
    MarqueeController,
    is_marquee_surface,
    mark_marquee_surfaces_recursively,
)
from widgets.panels.card_table_panel.table_view import DeckTableView

_BIG_RECT = wx.Rect(0, 0, 100_000, 100_000)

_META: dict[str, dict[str, Any]] = {
    "grizzly bears": {"mana_value": 2, "type_line": "Creature — Bear", "colors": ["G"]},
    "llanowar elves": {"mana_value": 1, "type_line": "Creature — Elf", "colors": ["G"]},
    "forest": {"mana_value": 0, "type_line": "Basic Land — Forest", "colors": []},
}


def _get_metadata(name: str) -> dict[str, Any]:
    return _META.get(name.lower(), {})


def _cards() -> list[dict[str, Any]]:
    return [
        {"name": "Grizzly Bears", "qty": 2},
        {"name": "Llanowar Elves", "qty": 4},
        {"name": "Forest", "qty": 6},
    ]


# ----- surface markers -----
@pytest.mark.usefixtures("wx_app")
def test_marker_roundtrips_and_recursion_filters_by_type():
    """Only vanilla panels/static chrome opt in; controls and subclasses don't."""
    frame = wx.Frame(None)
    try:
        plain = wx.Panel(frame)
        label = wx.StaticText(plain, label="hi")
        button = wx.Button(plain, label="go")

        class _SubPanel(wx.Panel):
            pass

        sub = _SubPanel(plain)

        assert not is_marquee_surface(plain)
        mark_marquee_surfaces_recursively(frame)

        assert is_marquee_surface(plain)  # vanilla wx.Panel
        assert is_marquee_surface(label)  # vanilla wx.StaticText
        assert not is_marquee_surface(button)  # a control
        assert not is_marquee_surface(sub)  # a wx.Panel subclass
        assert not is_marquee_surface(None)
    finally:
        frame.Destroy()


# ----- controller lifecycle -----
@pytest.mark.usefixtures("wx_app")
def test_controller_drives_begin_update_finish():
    frame = wx.Frame(None)
    try:
        window = wx.Window(frame)
        # Capture on a never-shown window is platform-fragile; neutralise it.
        window.CaptureMouse = lambda: None  # type: ignore[assignment]
        window.HasCapture = lambda: False  # type: ignore[assignment]
        window.ReleaseMouse = lambda: None  # type: ignore[assignment]

        events: list[Any] = []
        controller = MarqueeController(
            window,
            to_logical=lambda p: p,
            on_begin=lambda additive: events.append(("begin", additive)),
            on_select=lambda rect: events.append(("select", rect.GetWidth(), rect.GetHeight())),
            on_finish=lambda: events.append(("finish",)),
        )
        controller._update_overlay = lambda: None  # type: ignore[assignment]

        assert not controller.active
        controller.begin(wx.Point(5, 5), additive=True)
        assert controller.active
        controller.update(wx.Point(25, 35))
        controller.finish()

        assert not controller.active
        assert ("begin", True) in events
        assert ("finish",) in events
        # The post-update select reports a 20×30 rectangle.
        assert ("select", 20, 30) in events
    finally:
        frame.Destroy()


# ----- grid view -----
@pytest.mark.usefixtures("wx_app")
def test_grid_marquee_selects_covered_cards():
    frame = wx.Frame(None)
    try:
        view = DeckGridView(
            frame,
            "main",
            _get_metadata,
            lambda _n, _s: None,
            lambda _n, _q: ("owned", (0, 0, 0)),
            ManaIconFactory(icon_size=12),
            on_select=lambda _c: None,
            on_hover=None,
        )
        view.set_cards(_cards())

        view._marquee_begin(False)
        view._marquee_select(_BIG_RECT)

        assert view._selected_names == {"Grizzly Bears", "Llanowar Elves", "Forest"}
        assert view.get_selected_name() is None  # multi-select reports no single
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_grid_additive_marquee_unions_with_existing():
    frame = wx.Frame(None)
    try:
        view = DeckGridView(
            frame,
            "main",
            _get_metadata,
            lambda _n, _s: None,
            lambda _n, _q: ("owned", (0, 0, 0)),
            ManaIconFactory(icon_size=12),
            on_select=lambda _c: None,
            on_hover=None,
        )
        view.set_cards(_cards())
        view.set_selected("Forest")

        # A Shift-additive marquee keeps the prior selection and adds its hits.
        view._marquee_begin(True)
        view._marquee_select(_BIG_RECT)

        assert "Forest" in view._selected_names
        assert view._selected_names == {"Grizzly Bears", "Llanowar Elves", "Forest"}
    finally:
        frame.Destroy()


# ----- table view -----
@pytest.mark.usefixtures("wx_app")
def test_table_marquee_selects_covered_rows():
    frame = wx.Frame(None)
    try:
        view = DeckTableView(
            frame,
            "main",
            _get_metadata,
            on_select=lambda _c: None,
            on_hover=None,
            icon_factory=ManaIconFactory(icon_size=12),
        )
        view.set_cards(_cards())

        view._marquee_begin(False)
        view._marquee_select(_BIG_RECT)

        assert view._selected_names == {"Grizzly Bears", "Llanowar Elves", "Forest"}
        assert view.get_selected_name() is None
    finally:
        frame.Destroy()
