"""Drag a card-search result onto the mainboard or sideboard (issue #1033).

Driven through the real widgets of a real, shown ``AppFrame``: events go into
the results list's own event handler -- the same binding table a physical mouse
reaches -- and the assertion is on ``zone_cards``, i.e. on what the deck now
holds, not on which helper was called.

What wx events cannot reach is the native half of the gesture: comctl32's own
drag detection that turns a press-and-move on an unselected row into
``LVN_BEGINDRAG``. These tests post the ``EVT_LIST_BEGIN_DRAG`` that notification
becomes; the notification itself was verified with physical Win32 input on the
running app (see the PR for #1033).

Mouse capture is neutralised on the windows that take it: capture on a window
the test process does not own the pointer for is platform-fragile (the pattern
from ``test_marquee_selection``), and nothing asserted here depends on it.
"""

from __future__ import annotations

from typing import Any

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from widgets.panels.deck_builder_panel.result_drag import system_drag_threshold

_DECK_TEXT = "4 Mountain\n4 Island\n\nSideboard\n2 Dispel\n"
_RESULTS = [
    {"name": "Lightning Bolt", "mana_cost": "{R}"},
    {"name": "Counterspell", "mana_cost": "{U}{U}"},
    {"name": "Pyroblast", "mana_cost": "{R}"},
]


def _neutralise_capture(window: wx.Window) -> None:
    window.CaptureMouse = lambda: None  # type: ignore[method-assign]
    window.HasCapture = lambda: False  # type: ignore[method-assign]
    window.ReleaseMouse = lambda: None  # type: ignore[method-assign]


@pytest.fixture(name="frame")
def fixture_frame(shared_frame, wx_app):
    """A shown frame: a deck in both zones, the builder's results on screen.

    The window is the module's (see ``shared_app_frame``); every test starts
    from this same scene rebuilt on it, which is what these tests are about --
    none of them is about a freshly constructed window.
    """
    frame = shared_frame
    # The record-mode lock some tests turn on; off again for the next one.
    frame._guide_record = None
    frame.builder_panel.set_search_locked(False)
    frame._on_deck_content_ready(_DECK_TEXT, source="automation")
    frame._show_left_panel("builder", force=True)
    frame._show_deck_tables_tab()
    frame.builder_panel.update_results([dict(card) for card in _RESULTS])
    frame.Show()
    frame.Raise()
    frame.Layout()
    pump_ui_events(wx_app)
    _neutralise_capture(frame.builder_panel.results_ctrl)
    try:
        yield frame
    finally:
        timer = getattr(frame, "_save_timer", None)
        if timer is not None and timer.IsRunning():
            timer.Stop()
        pump_ui_events(wx_app)


def _qty(frame, zone: str, name: str) -> int:
    return sum(c["qty"] for c in frame.zone_cards.get(zone, []) if c["name"] == name)


def _pane_centre(frame, zone: str) -> wx.Point:
    rect = getattr(frame, f"{zone}_table").GetScreenRect()
    return wx.Point(rect.x + rect.width // 2, rect.y + rect.height // 2)


def _row_centre(results: wx.ListCtrl, index: int) -> wx.Point:
    rect = results.GetItemRect(index)
    return wx.Point(rect.x + rect.width // 2, rect.y + rect.height // 2)


def _send_mouse(window: wx.Window, event_type: int, client: wx.Point, *, left_down: bool) -> None:
    event = wx.MouseEvent(event_type)
    event.SetPosition(client)
    event.SetLeftDown(left_down)
    event.SetEventObject(window)
    window.GetEventHandler().ProcessEvent(event)


def _begin_native_drag(results: wx.ListCtrl, index: int) -> None:
    """Post what comctl32's ``LVN_BEGINDRAG`` becomes for a press on ``index``."""
    event = wx.ListEvent(wx.wxEVT_LIST_BEGIN_DRAG, results.GetId())
    event.SetIndex(index)
    event.SetEventObject(results)
    results.GetEventHandler().ProcessEvent(event)


def _release_over(results: wx.ListCtrl, screen_point: wx.Point) -> None:
    _send_mouse(results, wx.wxEVT_LEFT_UP, results.ScreenToClient(screen_point), left_down=False)


def _drag_row_to_zone(frame, index: int, zone: str) -> None:
    results = frame.builder_panel.results_ctrl
    target = _pane_centre(frame, zone)
    _begin_native_drag(results, index)
    _send_mouse(results, wx.wxEVT_MOTION, results.ScreenToClient(target), left_down=True)
    _release_over(results, target)


def _start_recording(frame) -> None:
    """The state ``_record_start`` leaves the frame in, minus its floating bar."""
    frame._guide_record = {
        "archetypes": ["Izzet Murktide"],
        "index": 0,
        "base_main": [dict(c) for c in frame.zone_cards["main"]],
        "base_side": [dict(c) for c in frame.zone_cards["side"]],
    }


# ----- the drop adds one copy, in every view -----
@pytest.mark.parametrize("view_mode", ["grid", "table", "pile"])
@pytest.mark.parametrize("zone", ["main", "side"])
def test_dropping_a_result_on_a_zone_adds_one_copy(frame, wx_app, view_mode: str, zone: str):
    for table in (frame.main_table, frame.side_table):
        table.set_view_mode(view_mode, persist=False)
    pump_ui_events(wx_app)
    other = "side" if zone == "main" else "main"
    before_other = [dict(c) for c in frame.zone_cards[other]]

    _drag_row_to_zone(frame, 1, zone)

    assert _qty(frame, zone, "Counterspell") == 1
    assert frame.zone_cards[other] == before_other
    assert frame._active_deck_zone == zone


def test_dropping_the_same_result_again_adds_another_copy(frame):
    _drag_row_to_zone(frame, 0, "main")
    _drag_row_to_zone(frame, 0, "main")
    assert _qty(frame, "main", "Lightning Bolt") == 2


def test_a_drop_outside_both_zones_adds_nothing(frame):
    results = frame.builder_panel.results_ctrl
    before = {zone: [dict(c) for c in cards] for zone, cards in frame.zone_cards.items()}
    _begin_native_drag(results, 0)
    # Back over the search list itself.
    _release_over(results, results.ClientToScreen(_row_centre(results, 2)))
    assert frame.zone_cards == before


def test_a_drop_on_a_zone_that_is_not_on_screen_adds_nothing(frame, wx_app):
    """With another workspace tab in front the panes keep their rectangles; a
    drop there must not land in a zone the user cannot see."""
    target = _pane_centre(frame, "main")
    for index in range(frame.deck_tabs.GetPageCount()):
        if frame.deck_tabs.GetPage(index) is not frame.deck_split:
            frame.deck_tabs.SetSelection(index)
            break
    pump_ui_events(wx_app)
    results = frame.builder_panel.results_ctrl
    _begin_native_drag(results, 0)
    _release_over(results, target)
    assert _qty(frame, "main", "Lightning Bolt") == 0


def test_escape_abandons_the_drag(frame):
    results = frame.builder_panel.results_ctrl
    _begin_native_drag(results, 0)
    key = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
    key.SetKeyCode(wx.WXK_ESCAPE)
    key.SetEventObject(results)
    results.GetEventHandler().ProcessEvent(key)
    _release_over(results, _pane_centre(frame, "main"))
    assert _qty(frame, "main", "Lightning Bolt") == 0


# ----- the record-mode lock (issue #1027) holds for a drop -----
@pytest.mark.parametrize("zone", ["main", "side"])
def test_regression_a_drop_is_refused_while_recording_a_guide(frame, zone: str):
    """Regression guard: the drop goes through ``_add_search_card_to_zone``.

    Only the frame's recording state is set -- the panel is deliberately left
    unlocked -- so this holds only if the drop is routed through the one method
    every search add funnels through. A drop that called ``_handle_zone_delta``
    directly would put the card in the deck mid-walk and have it recorded as
    "bring this in" for a card that is not in the 75.
    """
    _start_recording(frame)
    before = {z: [dict(c) for c in cards] for z, cards in frame.zone_cards.items()}
    _drag_row_to_zone(frame, 2, zone)
    assert frame.zone_cards == before


def test_a_locked_search_does_not_start_a_drag(frame):
    """The walk also locks the panel itself; a drag must not even begin."""
    _start_recording(frame)
    frame.builder_panel.set_search_locked(True)
    results = frame.builder_panel.results_ctrl
    _begin_native_drag(results, 0)
    assert not frame.builder_panel._result_drag.active
    _release_over(results, _pane_centre(frame, "main"))
    assert _qty(frame, "main", "Lightning Bolt") == 0


def test_drops_work_again_once_the_walk_is_over(frame):
    _start_recording(frame)
    frame.builder_panel.set_search_locked(True)
    _drag_row_to_zone(frame, 0, "main")
    frame._guide_record = None
    frame.builder_panel.set_search_locked(False)
    _drag_row_to_zone(frame, 0, "main")
    assert _qty(frame, "main", "Lightning Bolt") == 1


# ----- the already-selected row: click stays a click, a drag is a drag -----
def _press_selected_row(frame, index: int) -> tuple[wx.ListCtrl, wx.Point]:
    results = frame.builder_panel.results_ctrl
    results.Select(index)
    assert results.IsSelected(index)
    press = _row_centre(results, index)
    _send_mouse(results, wx.wxEVT_LEFT_DOWN, press, left_down=True)
    return results, press


def test_clicking_the_selected_row_still_clears_the_selection(frame):
    results, press = _press_selected_row(frame, 1)
    _send_mouse(results, wx.wxEVT_LEFT_UP, press, left_down=False)
    assert not results.IsSelected(1)
    assert frame.zone_cards["main"] == [
        {"name": "Island", "qty": 4},
        {"name": "Mountain", "qty": 4},
    ]


def test_a_wobble_inside_the_drag_threshold_is_still_a_click(frame):
    limit_x, limit_y = system_drag_threshold()
    results, press = _press_selected_row(frame, 1)
    wobble = wx.Point(press.x + limit_x, press.y + limit_y)
    _send_mouse(results, wx.wxEVT_MOTION, wobble, left_down=True)
    assert not frame.builder_panel._result_drag.active
    _send_mouse(results, wx.wxEVT_LEFT_UP, wobble, left_down=False)
    assert not results.IsSelected(1)
    assert _qty(frame, "main", "Counterspell") == 0


def test_the_selected_row_can_be_dragged_onto_a_zone(frame):
    results, _press = _press_selected_row(frame, 1)
    target = _pane_centre(frame, "side")
    _send_mouse(results, wx.wxEVT_MOTION, results.ScreenToClient(target), left_down=True)
    assert frame.builder_panel._result_drag.dragged_name == "Counterspell"
    _release_over(results, target)
    assert _qty(frame, "side", "Counterspell") == 1


# ----- the existing zone-to-zone drag shares the drop test and still works -----
def test_dragging_a_card_between_zones_still_moves_it(frame, wx_app):
    for table in (frame.main_table, frame.side_table):
        table.set_view_mode("grid", persist=False)
    pump_ui_events(wx_app)
    grid = frame.main_table.grid_view
    _neutralise_capture(grid)
    first: dict[str, Any] = grid._cards[0]
    rect = grid._card_rect(0)
    press = grid.CalcScrolledPosition(wx.Point(rect.x + rect.width // 2, rect.y + 20))
    target = grid.ScreenToClient(_pane_centre(frame, "side"))

    _send_mouse(grid, wx.wxEVT_LEFT_DOWN, press, left_down=True)
    _send_mouse(grid, wx.wxEVT_MOTION, target, left_down=True)
    _send_mouse(grid, wx.wxEVT_LEFT_UP, target, left_down=False)

    assert _qty(frame, "main", first["name"]) == 3
    assert _qty(frame, "side", first["name"]) == 1
