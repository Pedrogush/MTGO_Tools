"""Tests for the shared marquee machinery and per-view rubber-band selection.

Covers the background-surface classifier the app-level filter uses to decide
which presses originate a marquee, the :class:`MarqueeController` lifecycle, and
that the grid and table views select the cards a rectangle covers — the contract
that lets a marquee be driven from any view (and started from any background).
"""

from __future__ import annotations

from typing import Any

import pytest
import wx

from widgets.mana_icon_factory import ManaIconFactory
from widgets.panels.card_table_panel.grid_view import DeckGridView
from widgets.panels.card_table_panel.marquee import (
    MarqueeController,
    is_background_window,
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


# ----- background classifier -----
@pytest.mark.usefixtures("wx_app")
def test_background_window_classifies_by_exact_type():
    """Only vanilla panels/static chrome are marquee backgrounds; controls and
    subclasses (incl. the card views) keep their own press handling."""
    frame = wx.Frame(None)
    try:
        plain = wx.Panel(frame)
        label = wx.StaticText(plain, label="hi")
        line = wx.StaticLine(plain)
        button = wx.Button(plain, label="go")

        class _SubPanel(wx.Panel):
            pass

        sub = _SubPanel(plain)

        assert is_background_window(plain)  # vanilla wx.Panel
        assert is_background_window(label)  # vanilla wx.StaticText
        assert is_background_window(line)  # vanilla wx.StaticLine
        assert not is_background_window(button)  # a control
        assert not is_background_window(sub)  # a wx.Panel subclass
        assert not is_background_window(None)
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


@pytest.mark.usefixtures("wx_app")
def test_controller_double_begin_is_a_no_op():
    """A second begin while a marquee is active must not re-fire on_begin or
    clobber the existing rectangle (the active-guard at marquee.py:114)."""
    frame = wx.Frame(None)
    try:
        window = wx.Window(frame)
        window.CaptureMouse = lambda: None  # type: ignore[assignment]
        window.HasCapture = lambda: False  # type: ignore[assignment]
        window.ReleaseMouse = lambda: None  # type: ignore[assignment]

        begins: list[bool] = []
        controller = MarqueeController(
            window,
            to_logical=lambda p: p,
            on_begin=lambda additive: begins.append(additive),
            on_select=lambda rect: None,
            on_finish=lambda: None,
        )
        controller._update_overlay = lambda: None  # type: ignore[assignment]

        controller.begin(wx.Point(5, 5), additive=True)
        controller.begin(wx.Point(99, 99), additive=False)

        assert begins == [True]  # second begin was ignored
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_controller_update_and_finish_before_begin_do_nothing():
    """update()/finish() while idle are no-ops (the active-guards at
    marquee.py:138 and :146): neither selects nor fires on_finish."""
    frame = wx.Frame(None)
    try:
        window = wx.Window(frame)
        window.CaptureMouse = lambda: None  # type: ignore[assignment]
        window.HasCapture = lambda: False  # type: ignore[assignment]
        window.ReleaseMouse = lambda: None  # type: ignore[assignment]

        events: list[str] = []
        controller = MarqueeController(
            window,
            to_logical=lambda p: p,
            on_begin=lambda additive: events.append("begin"),
            on_select=lambda rect: events.append("select"),
            on_finish=lambda: events.append("finish"),
        )
        controller._update_overlay = lambda: None  # type: ignore[assignment]

        controller.update(wx.Point(10, 10))
        controller.finish()

        assert events == []
        assert not controller.active
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_controller_cancel_fires_finish_only_when_active():
    """cancel() tears down and fires on_finish when active, but its was_active
    guard (marquee.py:153-156) keeps a cancel-while-idle silent."""
    frame = wx.Frame(None)
    try:
        window = wx.Window(frame)
        window.CaptureMouse = lambda: None  # type: ignore[assignment]
        window.HasCapture = lambda: False  # type: ignore[assignment]
        window.ReleaseMouse = lambda: None  # type: ignore[assignment]

        finishes: list[int] = []
        controller = MarqueeController(
            window,
            to_logical=lambda p: p,
            on_begin=lambda additive: None,
            on_select=lambda rect: None,
            on_finish=lambda: finishes.append(1),
        )
        controller._update_overlay = lambda: None  # type: ignore[assignment]

        controller.cancel()  # idle: guarded, no on_finish
        assert finishes == []

        controller.begin(wx.Point(5, 5), additive=False)
        controller.cancel()  # active: tears down and notifies
        assert not controller.active
        assert finishes == [1]
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
def test_grid_marquee_geometry_selects_only_swept_card():
    """A rectangle that covers exactly one card's cell selects only that card,
    reports it as the single selection, and a rect that misses every cell
    selects nothing — exercising the real _card_rect geometry rather than the
    all-covering _BIG_RECT."""
    chosen: list[Any] = []
    frame = wx.Frame(None)
    try:
        view = DeckGridView(
            frame,
            "main",
            _get_metadata,
            lambda _n, _s: None,
            lambda _n, _q: ("owned", (0, 0, 0)),
            ManaIconFactory(icon_size=12),
            on_select=lambda card: chosen.append(card),
            on_hover=None,
        )
        view.set_cards(_cards())

        # Sweep exactly the second card's cell; only that card is hit.
        target = view._card_rect(1)
        expected = view._cards[1]["name"]

        view._marquee_begin(False)
        view._marquee_select(target)

        assert view._selected_names == {expected}
        # A lone marquee hit is forwarded as the single selection.
        assert chosen and chosen[-1] is not None
        assert chosen[-1]["name"] == expected
        assert view.get_selected_name() == expected

        # A rectangle in the gutter far below every cell selects nothing.
        view._marquee_begin(False)
        view._marquee_select(wx.Rect(5_000, 5_000, 1, 1))
        assert view._selected_names == set()
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


@pytest.mark.usefixtures("wx_app")
def test_table_marquee_geometry_selects_only_swept_row():
    """A rectangle spanning exactly one row's vertical extent selects only that
    row and reports it as the single selection; a rect above every row selects
    nothing — exercising the real CellToRect vertical-overlap test instead of
    the all-covering _BIG_RECT."""
    chosen: list[Any] = []
    frame = wx.Frame(None)
    try:
        view = DeckTableView(
            frame,
            "main",
            _get_metadata,
            on_select=lambda card: chosen.append(card),
            on_hover=None,
            icon_factory=ManaIconFactory(icon_size=12),
        )
        view.set_cards(_cards())

        # Span exactly the second row's vertical extent (the column is
        # irrelevant for full-row selection).
        row_rect = view.grid.CellToRect(1, 0)
        expected = view._rows[1]["name"]
        band = wx.Rect(
            row_rect.GetLeft(), row_rect.GetTop() + 1, row_rect.GetWidth(), row_rect.GetHeight() - 2
        )

        view._marquee_begin(False)
        view._marquee_select(band)

        assert view._selected_names == {expected}
        assert chosen and chosen[-1] is not None
        assert chosen[-1]["name"] == expected
        assert view.get_selected_name() == expected

        # A zero-height rect above the first row overlaps no row's span.
        top = view.grid.CellToRect(0, 0).GetTop()
        view._marquee_begin(False)
        view._marquee_select(wx.Rect(0, top - 10, 1, 1))
        assert view._selected_names == set()
    finally:
        frame.Destroy()
