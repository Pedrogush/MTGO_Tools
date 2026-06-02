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

from widgets.panels.card_table_panel.pile_view import _NAME_STRIP_HEIGHT, DeckPileView

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


def _make_view(frame: wx.Frame, on_select):
    view = DeckPileView(
        frame,
        "main",
        _get_metadata,
        _get_card_image,
        on_select=on_select,
        on_hover=None,
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
