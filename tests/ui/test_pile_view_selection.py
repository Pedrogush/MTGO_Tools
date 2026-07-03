"""Regression tests for per-copy selection in the deck pile view.

The pile view tracks selection by ``_uid`` so each physical copy of a card is
independently selectable and draggable. The bug these tests guard against:
the panel collapses the pile view's selection to a bare card *name* and echoes
it back via ``set_selected(name)``. Re-resolving a name picks the *first* copy,
so a click on (or a rubber-band over) any other copy used to be bounced to the
first copy — taking the drag target with it.

These exercise the real round-trip: ``on_select`` here mirrors
``CardTablePanel._handle_view_select`` -> ``_sync_selection``.
"""

from __future__ import annotations

from typing import Any

import pytest
import wx

from utils.constants import CARD_VIEW_WHEEL_LINE_PX
from widgets.panels.card_table_panel.pile_view import _NAME_STRIP_HEIGHT, DeckPileView

# A standard mouse reports 3 lines per notch; one notch scrolls this many px.
_NOTCH_PX = 3 * CARD_VIEW_WHEEL_LINE_PX

_META: dict[str, dict[str, Any]] = {
    "grizzly bears": {"mana_value": 2, "type_line": "Creature — Bear", "colors": ["G"]},
}


def _get_metadata(name: str) -> dict[str, Any]:
    return _META.get(name.lower(), {})


def _get_card_image(_name: str, _size: str) -> None:
    return None


class _FakeMouseEvent:
    """Minimal stand-in for the wx.MouseEvent fields _on_left_down reads."""

    def __init__(self, pos: wx.Point, *, shift: bool = False, ctrl: bool = False) -> None:
        self._pos = pos
        self._shift = shift
        self._ctrl = ctrl

    def GetPosition(self) -> wx.Point:
        return self._pos

    def ShiftDown(self) -> bool:
        return self._shift

    def ControlDown(self) -> bool:
        return self._ctrl

    def LeftIsDown(self) -> bool:
        return False


class _FakeWheelEvent:
    """Minimal stand-in for the wx.MouseEvent fields scroll_by_wheel reads."""

    def __init__(
        self, rotation: int, *, axis: int = 0, shift: bool = False, lines: int = 3
    ) -> None:
        self._rotation = rotation
        self._axis = axis
        self._shift = shift
        self._lines = lines

    def GetWheelRotation(self) -> int:
        return self._rotation

    def GetWheelDelta(self) -> int:
        return 120

    def GetWheelAxis(self) -> int:
        return self._axis

    def GetLinesPerAction(self) -> int:
        return self._lines

    def ShiftDown(self) -> bool:
        return self._shift


def _make_view(frame: wx.Frame, on_select, *, on_hover=None):
    view = DeckPileView(
        frame,
        "main",
        _get_metadata,
        _get_card_image,
        on_select=on_select,
        on_hover=on_hover,
    )
    # Mouse capture on a never-shown window is platform-fragile and irrelevant
    # to selection logic; neutralise it.
    view.CaptureMouse = lambda: None  # type: ignore[assignment]
    view.HasCapture = lambda: True  # type: ignore[assignment]
    view.ReleaseMouse = lambda: None  # type: ignore[assignment]
    return view


@pytest.mark.usefixtures("wx_app")
def test_selecting_a_copy_survives_panel_name_round_trip():
    """A reported single-copy selection must not be bounced to the first copy."""
    frame = wx.Frame(None)
    reported = {"name": "__unset__"}

    def panel_round_trip(card):
        # Mirror CardTablePanel: collapse to a name, then sync it back.
        reported["name"] = card["name"] if card else None
        view.set_selected(reported["name"])

    view = _make_view(frame, panel_round_trip)
    try:
        view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
        ((_label, members),) = view._piles
        assert len(members) == 4
        third_uid = members[2]["_uid"]

        # As _on_left_down does: set the clicked copy, then report it.
        view._selected_uids = {third_uid}
        view._notify_selection_changed()

        assert view._selected_uids == {third_uid}
        assert reported["name"] == "Grizzly Bears"
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_clicking_a_copy_selects_it_and_primes_drag_with_it():
    """Clicking the third copy selects *that* copy and primes a drag of it."""
    frame = wx.Frame(None)

    def panel_round_trip(card):
        view.set_selected(card["name"] if card else None)

    view = _make_view(frame, panel_round_trip)
    try:
        view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
        ((_label, members),) = view._piles
        third_uid = members[2]["_uid"]

        # The third copy is stacked above the bottom card, so only its top
        # name strip is clickable.
        rect = view._card_rect(0, 2, len(members))
        point = wx.Point(rect.x + rect.width // 2, rect.y + _NAME_STRIP_HEIGHT // 2)
        view._on_left_down(_FakeMouseEvent(point))

        assert view._selected_uids == {third_uid}
        # Drag must operate on the clicked copy, not the first copy.
        assert view._drag_uids == [third_uid]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_multi_copy_selection_survives_round_trip():
    """A rubber-band multi-select must not be wiped by the name round-trip.

    Multi-selection collapses to ``None`` for the inspector (hover wins), and
    the panel's echo of that ``None`` previously cleared every selected copy.
    """
    frame = wx.Frame(None)
    reported = {"name": "__unset__"}

    def panel_round_trip(card):
        reported["name"] = card["name"] if card else None
        view.set_selected(reported["name"])

    view = _make_view(frame, panel_round_trip)
    try:
        view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
        ((_label, members),) = view._piles
        chosen = {members[0]["_uid"], members[2]["_uid"]}

        view._selected_uids = set(chosen)
        view._notify_selection_changed()

        assert view._selected_uids == chosen
        assert reported["name"] is None
    finally:
        frame.Destroy()


def _hover_point(view) -> wx.Point:
    """A point over the top copy of the (single) pile, usable for hover hits."""
    ((_label, members),) = view._piles
    rect = view._card_rect(0, 0, len(members))
    return wx.Point(rect.x + rect.width // 2, rect.y + _NAME_STRIP_HEIGHT // 2)


@pytest.mark.usefixtures("wx_app")
def test_hover_reports_card_when_nothing_is_selected():
    """With no selection, moving over a copy reports it via on_hover."""
    frame = wx.Frame(None)
    hovered: list = []
    view = _make_view(frame, lambda _card: None, on_hover=hovered.append)
    try:
        view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
        assert not view._selected_uids
        ((_label, members),) = view._piles
        top_uid = members[0]["_uid"]

        view._on_motion(_FakeMouseEvent(_hover_point(view)))

        assert view._hover_uid == top_uid
        assert hovered == [{"name": "Grizzly Bears", "qty": 1}]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_hover_suppressed_with_exactly_one_selected_copy():
    """A single selected copy stays the active card; hover must not override it."""
    frame = wx.Frame(None)
    hovered: list = []
    view = _make_view(frame, lambda _card: None, on_hover=hovered.append)
    try:
        view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
        ((_label, members),) = view._piles
        view._selected_uids = {members[0]["_uid"]}

        view._on_motion(_FakeMouseEvent(_hover_point(view)))

        assert view._hover_uid is None
        assert hovered == []
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_hover_reports_card_with_multi_selection():
    """'Hover wins' when more than one copy is selected: on_hover still fires."""
    frame = wx.Frame(None)
    hovered: list = []
    view = _make_view(frame, lambda _card: None, on_hover=hovered.append)
    try:
        view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
        ((_label, members),) = view._piles
        view._selected_uids = {members[1]["_uid"], members[2]["_uid"]}
        top_uid = members[0]["_uid"]

        view._on_motion(_FakeMouseEvent(_hover_point(view)))

        assert view._hover_uid == top_uid
        assert hovered == [{"name": "Grizzly Bears", "qty": 1}]
    finally:
        frame.Destroy()


def _wheel_view(frame: wx.Frame, start: tuple[int, int]):
    """A pile view whose Scroll calls are captured and view origin is fixed."""
    view = _make_view(frame, lambda _card: None)
    view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
    calls: list[tuple[int, int]] = []
    view.GetViewStart = lambda: start  # type: ignore[assignment]
    view.Scroll = lambda x, y: calls.append((x, y))  # type: ignore[assignment]
    return view, calls


@pytest.mark.usefixtures("wx_app")
def test_wheel_scrolls_vertical_by_lines_per_notch():
    """One notch moves lines_per_action * line_px, not the few px the 1px rate gives."""
    frame = wx.Frame(None)
    try:
        view, calls = _wheel_view(frame, (0, 200))
        view._on_wheel(_FakeWheelEvent(120))  # one notch up
        assert calls == [(0, 200 - _NOTCH_PX)]

        calls.clear()
        view._on_wheel(_FakeWheelEvent(-120))  # one notch down
        assert calls == [(0, 200 + _NOTCH_PX)]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_wheel_honors_os_lines_per_action():
    """A larger OS lines-per-action scrolls proportionally further per notch."""
    frame = wx.Frame(None)
    try:
        view, calls = _wheel_view(frame, (0, 500))
        view._on_wheel(_FakeWheelEvent(120, lines=5))
        assert calls == [(0, 500 - 5 * CARD_VIEW_WHEEL_LINE_PX)]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_sub_notch_rotation_accumulates_until_a_full_notch():
    """High-res wheels: partial rotations are carried, not fired one repaint each.

    This is the responsiveness fix — without accumulation every micro-event
    would Scroll + repaint and the queue would backlog.
    """
    frame = wx.Frame(None)
    try:
        view, calls = _wheel_view(frame, (0, 200))
        view._on_wheel(_FakeWheelEvent(60))  # half a notch — no scroll yet
        assert calls == []
        view._on_wheel(_FakeWheelEvent(60))  # completes the notch — scrolls once
        assert calls == [(0, 200 - _NOTCH_PX)]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_wheel_clamps_at_top():
    frame = wx.Frame(None)
    try:
        view, calls = _wheel_view(frame, (0, _NOTCH_PX // 2))
        view._on_wheel(_FakeWheelEvent(120))  # scroll up past the top
        assert calls == [(0, 0)]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_shift_wheel_scrolls_horizontal():
    frame = wx.Frame(None)
    try:
        view, calls = _wheel_view(frame, (200, 50))
        view._on_wheel(_FakeWheelEvent(120, shift=True))
        assert calls == [(200 - _NOTCH_PX, 50)]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_rubber_band_past_canvas_selects_every_card():
    """A box dragged beyond the canvas bounds still selects everything inside.

    The marquee endpoint follows the cursor unclamped (so it can grow past the
    canvas), so an end point well outside the virtual size must still resolve to
    "all cards under the box", not drop the edge copies.
    """
    frame = wx.Frame(None)
    try:
        view = _make_view(frame, lambda _card: None)
        view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
        ((_label, members),) = view._piles
        all_uids = {entry["_uid"] for entry in members}

        # A rectangle far past the canvas, applied through the marquee callback.
        view._marquee_select(wx.Rect(0, 0, 10_000, 10_000))

        assert view._selected_uids == all_uids
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_begin_marquee_at_screen_starts_a_selection_from_outside():
    """A marquee can be initiated from outside the widget (frame background)."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame, lambda _card: None)
        view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
        # Don't spawn the real overlay popup for a never-shown test window.
        view._marquee._update_overlay = lambda: None  # type: ignore[assignment]

        view.begin_marquee_at_screen(wx.Point(500, 500))

        assert view._marquee.active
        view._marquee.cancel()
        assert not view._marquee.active
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_autoscroll_steps_toward_edges_the_pointer_is_held_past():
    """Holding the marquee past a viewport edge scrolls one step that way."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame, lambda _card: None)
        view.set_cards([{"name": "Grizzly Bears", "qty": 4}])
        calls: list[tuple[int, int]] = []
        view.GetClientSize = lambda: (200, 200)  # type: ignore[assignment]
        view.GetViewStart = lambda: (50, 50)  # type: ignore[assignment]
        view.Scroll = lambda x, y: calls.append((x, y))  # type: ignore[assignment]

        # Past the right/bottom edges: step forward on that axis.
        view._autoscroll_towards(wx.Point(250, 100))
        assert calls == [(50 + 24, 50)]

        calls.clear()
        view._autoscroll_towards(wx.Point(100, 250))
        assert calls == [(50, 50 + 24)]

        # Before the origin: step back, clamped at 0.
        calls.clear()
        view.GetViewStart = lambda: (10, 10)  # type: ignore[assignment]
        view._autoscroll_towards(wx.Point(-5, -5))
        assert calls == [(0, 0)]

        # Pointer inside the viewport: no scroll.
        calls.clear()
        view._autoscroll_towards(wx.Point(100, 100))
        assert calls == []
    finally:
        frame.Destroy()
