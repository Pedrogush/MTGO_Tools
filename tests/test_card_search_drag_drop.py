"""Drag a card-search result onto a deck zone (issue #1033) -- the decision logic.

Two layers own the gesture's outcome, and each is pinned here without a display:

* ``AppFrame`` -- ``_zone_at_screen_point`` is the one drop-target test, shared
  by cards dragged across from the other zone (#781) and results dragged in from
  the search; ``_handle_search_drop`` adds the copy through
  ``_add_search_card_to_zone``, the method every search add funnels through, so
  the sideboard-guide record lock (#1027) holds for a drop too.
* ``DeckBuilderPanel`` -- a locked panel neither starts a drag nor hands a drop
  on, and a press on the selected row waits to learn whether it is a click or a
  drag instead of clearing the selection straight away.

The gesture itself, through real widgets in a shown frame, is covered by
``tests/ui/test_card_search_drag_drop.py``. ``wx`` is not importable in the WSL
dev environment, so the stub + load-by-path pattern of
``tests/test_card_search_double_click.py`` is used.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest


class _WxStub(types.ModuleType):
    """A permissive ``wx`` stand-in fabricating unique constants on demand."""

    _PINNED = {"NOT_FOUND": -1}

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._counter = 1000

    def __getattr__(self, item: str) -> Any:
        if item in self._PINNED:
            value: Any = self._PINNED[item]
        else:
            self._counter += 1
            value = self._counter
        setattr(self, item, value)
        return value


def _install_wx_stub() -> types.ModuleType:
    """Install the stub only when real ``wx`` is unavailable (CI runs on Windows)."""
    try:
        import wx as real_wx  # noqa: F401

        return sys.modules["wx"]
    except Exception:
        pass
    existing = sys.modules.get("wx")
    if isinstance(existing, _WxStub):
        return existing
    stub = _WxStub("wx")
    sys.modules["wx"] = stub
    return stub


def _load(module_name: str, *parts: str) -> types.ModuleType:
    """Import a source file directly, bypassing its package ``__init__``."""
    path = Path(__file__).resolve().parent.parent.joinpath(*parts)
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_install_wx_stub()
DeckBuilderPanelHandlersMixin = _load(
    "_builder_handlers_for_drag",
    "widgets",
    "panels",
    "deck_builder_panel",
    "handlers.py",
).DeckBuilderPanelHandlersMixin
ZoneEditingHandlers = _load(
    "_zone_editing_for_drag",
    "widgets",
    "frames",
    "app_frame",
    "handlers",
    "zone_editing.py",
).ZoneEditingHandlers
CardSelectionHandlers = _load(
    "_card_selection_for_drag",
    "widgets",
    "frames",
    "app_frame",
    "handlers",
    "card_selection.py",
).CardSelectionHandlers


# ===================== the frame =====================


class _Point:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


class _Rect:
    def __init__(self, x: int, y: int, w: int, h: int) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h

    def Contains(self, point: _Point) -> bool:
        return self.x <= point.x < self.x + self.w and self.y <= point.y < self.y + self.h


class _Pane:
    """A zone table as the drop test sees it: a screen rectangle, maybe on screen."""

    def __init__(self, rect: _Rect, *, shown: bool = True) -> None:
        self._rect = rect
        self.shown = shown

    def GetScreenRect(self) -> _Rect:
        return self._rect

    def IsShownOnScreen(self) -> bool:
        return self.shown


# The mainboard over the sideboard, the way the deck split lays them out.
_IN_MAIN = _Point(150, 100)
_IN_SIDE = _Point(150, 450)
_IN_NEITHER = _Point(20, 100)


class _Frame(CardSelectionHandlers, ZoneEditingHandlers):
    """The frame's drop surface, with the view-side steps faked."""

    def __init__(self, *, recording: bool = False) -> None:
        self.zone_cards: dict[str, list[dict[str, Any]]] = {
            "main": [{"name": "Island", "qty": 4}],
            "side": [{"name": "Pyroblast", "qty": 2}],
            "out": [],
        }
        self._guide_record = {"archetypes": ["Izzet Murktide"], "index": 0} if recording else None
        self._active_deck_zone = "main"
        self.main_table = _Pane(_Rect(100, 0, 300, 400))
        self.side_table = _Pane(_Rect(100, 408, 300, 150))
        self.out_table = None
        self.focused: list[tuple[str, str]] = []
        self.statuses: list[str] = []
        self.search_adds: list[tuple[str, str, int]] = []

    # --- faked View surface ---
    def _after_zone_change(self, zone: str) -> None:
        pass

    def _focus_card_in_zone(self, zone: str, card_name: str) -> None:
        self.focused.append((zone, card_name))

    def _set_status(self, key: str, **_kwargs: object) -> None:
        self.statuses.append(key)

    def _add_search_card_to_zone(self, zone: str, name: str, count: int = 1) -> bool:
        # Spy on the one funnel, then run the real thing.
        self.search_adds.append((zone, name, count))
        return super()._add_search_card_to_zone(zone, name, count)

    def qty(self, zone: str, name: str) -> int:
        return sum(e["qty"] for e in self.zone_cards[zone] if e["name"] == name)


@pytest.mark.parametrize(("point", "zone"), [(_IN_MAIN, "main"), (_IN_SIDE, "side")])
def test_the_drop_target_is_the_zone_pane_under_the_pointer(point: _Point, zone: str) -> None:
    assert _Frame()._zone_at_screen_point(point) == zone


def test_a_point_outside_both_panes_is_no_zone() -> None:
    assert _Frame()._zone_at_screen_point(_IN_NEITHER) is None


def test_a_pane_that_is_not_on_screen_is_not_a_drop_target() -> None:
    """Another workspace tab in front leaves the panes' rectangles where they
    were; the zone under them is not somewhere the user can see a card land."""
    frame = _Frame()
    frame.main_table.shown = False
    assert frame._zone_at_screen_point(_IN_MAIN) is None


@pytest.mark.parametrize(("point", "zone"), [(_IN_MAIN, "main"), (_IN_SIDE, "side")])
def test_a_search_drop_adds_one_copy_to_that_zone(point: _Point, zone: str) -> None:
    frame = _Frame()
    assert frame._handle_search_drop("Lightning Bolt", point) is True
    assert frame.qty(zone, "Lightning Bolt") == 1
    assert frame.focused == [(zone, "Lightning Bolt")]
    assert frame._active_deck_zone == zone


def test_a_search_drop_goes_through_the_one_search_add_route() -> None:
    frame = _Frame()
    frame._handle_search_drop("Lightning Bolt", _IN_SIDE)
    assert frame.search_adds == [("side", "Lightning Bolt", 1)]


def test_a_search_drop_outside_the_zones_changes_nothing() -> None:
    frame = _Frame()
    assert frame._handle_search_drop("Lightning Bolt", _IN_NEITHER) is False
    assert frame.search_adds == []
    assert frame.zone_cards["main"] == [{"name": "Island", "qty": 4}]


@pytest.mark.parametrize("point", [_IN_MAIN, _IN_SIDE])
def test_regression_a_search_drop_is_refused_while_recording_a_guide(point: _Point) -> None:
    """Regression guard for #1033 against #1027's lock.

    A card dropped in from the search mid-walk would be recorded as "bring this
    in" for a card that is nowhere in the base 75. Refused, not scrolled to, and
    the user is told why -- the same answer as every other search add.
    """
    frame = _Frame(recording=True)
    assert frame._handle_search_drop("Lightning Bolt", point) is False
    assert frame.qty("main", "Lightning Bolt") == 0
    assert frame.qty("side", "Lightning Bolt") == 0
    assert frame.focused == []
    assert frame.statuses == ["builder.locked.recording"]
    assert frame._active_deck_zone == "main"


def test_a_zone_to_zone_drag_moves_a_copy_over_the_other_pane() -> None:
    frame = _Frame()
    assert frame._handle_zone_transfer("main", ["Island"], _IN_SIDE) is True
    assert frame.qty("main", "Island") == 3
    assert frame.qty("side", "Island") == 1


def test_a_zone_to_zone_drag_released_over_its_own_pane_is_not_a_transfer() -> None:
    frame = _Frame()
    assert frame._handle_zone_transfer("main", ["Island"], _IN_MAIN) is False
    assert frame.qty("main", "Island") == 4


def test_a_zone_to_zone_drag_still_works_while_recording() -> None:
    """Moving cards between the zones *is* the record walk; only the search locks."""
    frame = _Frame(recording=True)
    assert frame._handle_zone_transfer("side", ["Pyroblast"], _IN_MAIN) is True
    assert frame.qty("main", "Pyroblast") == 1


# ===================== the search panel =====================


class _ListEvent:
    def __init__(self, index: int) -> None:
        self._index = index

    def GetIndex(self) -> int:
        return self._index


class _MouseEvent:
    def __init__(self, x: int = 5, y: int = 5) -> None:
        self._pos = _Point(x, y)
        self.skipped = False

    def GetPosition(self) -> _Point:
        return self._pos

    def Skip(self) -> None:
        self.skipped = True


class _Results:
    """The results list as the press handler reads it."""

    def __init__(self, selected: int | None) -> None:
        self.selected = selected

    def HitTest(self, _pos: _Point) -> tuple[int, int]:
        return (0, 0)

    def IsSelected(self, idx: int) -> bool:
        return idx == self.selected

    def GetFirstSelected(self) -> int:
        return -1 if self.selected is None else self.selected

    def Select(self, idx: int, on: int = 1) -> None:
        self.selected = idx if on else None


class _Drag:
    """Records what the panel asks of the drag controller."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.active = False
        self.primed = False

    def begin(self, index: int) -> bool:
        self.calls.append(("begin", index))
        return True

    def prime(self, index: int, _point: _Point) -> None:
        self.calls.append(("prime", index))


class _Panel(DeckBuilderPanelHandlersMixin):
    def __init__(self, *, selected: int | None = 0, wired: bool = True) -> None:
        self.search_locked = False
        self._status_before_lock = ""
        self.status_label = None
        self._add_main_btn = None
        self._add_side_btn = None
        self.results_ctrl = _Results(selected)
        self._result_drag = _Drag()
        self.drops: list[tuple[str, _Point]] = []
        self._on_drop_result = (
            (lambda name, point: self.drops.append((name, point)) or True) if wired else None
        )
        self._drop_zone_at = None
        self.result_selected: list[int | None] = []
        self._on_result_selected_callback = self.result_selected.append

    def Enable(self, enable: bool = True) -> None:
        pass

    def _t(self, key: str, **_kwargs: object) -> str:
        return key

    def get_selected_result(self) -> dict[str, Any] | None:
        return None


def test_a_locked_panel_does_not_start_a_drag() -> None:
    panel = _Panel()
    panel.set_search_locked(True)
    panel._on_results_begin_drag(_ListEvent(0))
    assert panel._result_drag.calls == []


def test_an_unlocked_panel_starts_the_drag_the_list_detected() -> None:
    panel = _Panel()
    panel._on_results_begin_drag(_ListEvent(2))
    assert panel._result_drag.calls == [("begin", 2)]


def test_a_locked_panel_hands_no_drop_to_the_frame() -> None:
    panel = _Panel()
    panel.set_search_locked(True)
    assert panel._drop_result("Lightning Bolt", _Point(1, 1)) is False
    assert panel.drops == []


def test_a_press_on_the_selected_row_waits_for_click_or_drag() -> None:
    panel = _Panel(selected=0)
    event = _MouseEvent()
    panel._on_results_left_down(event)
    assert panel._result_drag.calls == [("prime", 0)]
    assert panel.results_ctrl.selected == 0  # not cleared on the press
    assert not event.skipped


def test_the_released_click_on_the_selected_row_clears_it() -> None:
    panel = _Panel(selected=0)
    panel._deselect_result(0)
    assert panel.results_ctrl.selected is None
    assert panel.result_selected == [None]


def test_without_a_drop_route_the_selected_row_clears_on_the_press_as_before() -> None:
    panel = _Panel(selected=0, wired=False)
    panel._on_results_left_down(_MouseEvent())
    assert panel._result_drag.calls == []
    assert panel.results_ctrl.selected is None


def test_a_press_on_an_unselected_row_is_left_to_the_native_list() -> None:
    panel = _Panel(selected=None)
    event = _MouseEvent()
    panel._on_results_left_down(event)
    assert event.skipped
    assert panel._result_drag.calls == []
