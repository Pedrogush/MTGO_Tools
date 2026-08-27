"""Double-click in the card search, and the lock that closes it (issue #1027).

Two behaviours, at the two layers that own them:

* ``DeckBuilderPanel`` — a double-click (or Enter) on a result row activates it,
  which adds one copy to the active deck zone, and every add route out of the
  panel refuses to fire while the panel is locked.
* ``AppFrame`` — while a sideboard guide is being recorded, the search is locked.
  That walk derives each matchup's plan by diffing the current mainboard against
  the base 75 (see ``sideboard_guide_record``), so a card added from the search
  mid-walk is recorded as "bring this in" for a card that is nowhere in the 75.
  ``test_regression_*`` below is the guard for that; it fails on the commit
  before this one, where the search stayed live for the whole walk.

``wx`` is not importable in the WSL dev environment, so a minimal stub is
installed before loading the modules under test by file path — the pattern
established by ``tests/test_deck_builder_hotkeys.py``.
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
    "_builder_handlers_under_test",
    "widgets",
    "panels",
    "deck_builder_panel",
    "handlers.py",
).DeckBuilderPanelHandlersMixin
ZoneEditingHandlers = _load(
    "_zone_editing_for_search_lock",
    "widgets",
    "frames",
    "app_frame",
    "handlers",
    "zone_editing.py",
).ZoneEditingHandlers
CardSelectionHandlers = _load(
    "_card_selection_under_test",
    "widgets",
    "frames",
    "app_frame",
    "handlers",
    "card_selection.py",
).CardSelectionHandlers


# ===================== the search panel =====================


class _ListEvent:
    """Stand-in for the ``wx.ListEvent`` a row activation carries."""

    def __init__(self, index: int) -> None:
        self._index = index

    def GetIndex(self) -> int:
        return self._index


class _Label:
    """Stand-in for the panel's status ``wx.StaticText``."""

    def __init__(self, label: str = "") -> None:
        self._label = label

    def GetLabel(self) -> str:
        return self._label

    def SetLabel(self, label: str) -> None:
        self._label = label


class _Button:
    def __init__(self) -> None:
        self.enabled = True

    def Enable(self, enable: bool = True) -> None:
        self.enabled = bool(enable)


class _Panel(DeckBuilderPanelHandlersMixin):
    """The builder panel's add/lock surface with fake widgets for the View."""

    def __init__(
        self,
        results: dict[int, dict[str, Any]] | None = None,
        selected: dict[str, Any] | None = None,
    ) -> None:
        self._results = results or {}
        self._selected = selected
        self.search_locked = False
        self._status_before_lock = ""
        self.status_label = _Label("Showing 2 cards.")
        self._add_main_btn = _Button()
        self._add_side_btn = _Button()
        self.enabled = True
        self.active_zone_calls: list[str] = []
        self.main_calls: list[tuple[str, int]] = []
        self.side_calls: list[tuple[str, int]] = []
        self._on_add_to_active_zone = self.active_zone_calls.append
        self._on_add_to_main = lambda name, count=1: self.main_calls.append((name, count))
        self._on_add_to_side = lambda name, count=1: self.side_calls.append((name, count))

    # --- faked View surface ---
    def Enable(self, enable: bool = True) -> None:
        self.enabled = bool(enable)

    def _t(self, key: str, **_kwargs: object) -> str:
        return {
            "builder.locked.recording": "Card search is locked while a sideboard "
            "guide is being recorded.",
            "builder.status.results": "Results update automatically as you type.",
        }[key]

    def get_result_at_index(self, idx: int) -> dict[str, Any] | None:
        return self._results.get(idx)

    def get_selected_result(self) -> dict[str, Any] | None:
        return self._selected


def test_activating_a_result_adds_one_copy_to_the_active_zone() -> None:
    """A double-click (or Enter) on a result row is one copy into the deck."""
    panel = _Panel(results={1: {"name": "Lightning Bolt"}})
    panel._on_result_activated(_ListEvent(1))
    assert panel.active_zone_calls == ["Lightning Bolt"]


def test_activating_a_result_uses_the_row_that_was_double_clicked() -> None:
    """The clicked row wins, not whatever happened to be selected before it."""
    panel = _Panel(
        results={0: {"name": "Island"}, 3: {"name": "Brainstorm"}},
        selected={"name": "Island"},
    )
    panel._on_result_activated(_ListEvent(3))
    assert panel.active_zone_calls == ["Brainstorm"]


def test_activating_an_empty_row_adds_nothing() -> None:
    panel = _Panel(results={})
    panel._on_result_activated(_ListEvent(7))
    assert panel.active_zone_calls == []


def test_activating_a_result_is_refused_while_the_search_is_locked() -> None:
    panel = _Panel(results={1: {"name": "Lightning Bolt"}})
    panel.set_search_locked(True)
    panel._on_result_activated(_ListEvent(1))
    assert panel.active_zone_calls == []


def test_the_add_buttons_are_refused_while_the_search_is_locked() -> None:
    """The lock has to hold the programmatic route too, not just the greying."""
    panel = _Panel(selected={"name": "Pyroblast"})
    panel.set_search_locked(True)
    panel._on_add_to_zone("main", 4)
    panel._on_add_to_zone("side", 2)
    assert panel.main_calls == []
    assert panel.side_calls == []


def test_unlocking_restores_the_add_routes() -> None:
    panel = _Panel(results={0: {"name": "Island"}}, selected={"name": "Island"})
    panel.set_search_locked(True)
    panel.set_search_locked(False)
    panel._on_result_activated(_ListEvent(0))
    panel._on_add_to_zone("main", 2)
    assert panel.active_zone_calls == ["Island"]
    assert panel.main_calls == [("Island", 2)]


def test_locking_greys_the_panel_and_says_why() -> None:
    panel = _Panel(selected={"name": "Island"})
    panel.set_search_locked(True)
    assert panel.enabled is False
    assert "locked" in panel.status_label.GetLabel()
    assert panel._add_main_btn.enabled is False
    assert panel._add_side_btn.enabled is False


def test_unlocking_restores_the_panel_and_its_result_count() -> None:
    panel = _Panel(selected={"name": "Island"})
    panel.set_search_locked(True)
    panel.set_search_locked(False)
    assert panel.enabled is True
    assert panel.status_label.GetLabel() == "Showing 2 cards."
    assert panel._add_main_btn.enabled is True


def test_unlocking_leaves_the_add_buttons_greyed_with_no_selection() -> None:
    """Re-enabling the column must not present the add buttons as usable when
    there is nothing selected to add."""
    panel = _Panel(selected=None)
    panel.set_search_locked(True)
    panel.set_search_locked(False)
    assert panel._add_main_btn.enabled is False
    assert panel._add_side_btn.enabled is False


def test_locking_twice_keeps_the_original_status_line() -> None:
    """A redundant lock must not save the lock message as the text to restore."""
    panel = _Panel()
    panel.set_search_locked(True)
    panel.set_search_locked(True)
    panel.set_search_locked(False)
    assert panel.status_label.GetLabel() == "Showing 2 cards."


# ===================== the frame =====================


class _Frame(CardSelectionHandlers, ZoneEditingHandlers):
    """The frame's search-add surface, with the view-side steps faked."""

    def __init__(self, *, recording: bool = False) -> None:
        self.zone_cards: dict[str, list[dict[str, Any]]] = {"main": [], "side": [], "out": []}
        self._guide_record = {"archetypes": ["Izzet Murktide"], "index": 0} if recording else None
        self._active_deck_zone = "main"
        self.focused: list[tuple[str, str]] = []
        self.statuses: list[str] = []

    # --- faked View surface ---
    def _after_zone_change(self, zone: str) -> None:
        pass

    def _focus_card_in_zone(self, zone: str, card_name: str) -> None:
        self.focused.append((zone, card_name))

    def _set_status(self, key: str, **_kwargs: object) -> None:
        self.statuses.append(key)

    def qty(self, zone: str, name: str) -> int:
        for entry in self.zone_cards[zone]:
            if entry["name"] == name:
                return entry["qty"]
        return 0


def test_search_add_puts_a_copy_in_the_active_zone_and_scrolls_to_it() -> None:
    frame = _Frame()
    frame._active_deck_zone = "side"
    frame._add_search_card_to_active_zone("Pyroblast")
    assert frame.qty("side", "Pyroblast") == 1
    assert frame.focused == [("side", "Pyroblast")]


def test_search_add_to_a_named_zone_honours_the_copy_count() -> None:
    frame = _Frame()
    assert frame._add_search_card_to_zone("main", "Lightning Bolt", 4) is True
    assert frame.qty("main", "Lightning Bolt") == 4


def test_regression_search_add_is_refused_while_recording_a_guide() -> None:
    """Regression guard for #1027.

    Before this change the search stayed live during a record walk, so a
    double-click (or an add button, or a 1-4 hotkey) put a card into the
    mainboard mid-matchup and ``_record_diff`` stored it as "bring this in" for
    a card that is not in the base 75. This assertion fails on the previous
    commit, where the card was added.
    """
    frame = _Frame(recording=True)
    frame._add_search_card_to_active_zone("Lightning Bolt")
    assert frame.zone_cards["main"] == []
    assert frame.zone_cards["side"] == []


def test_a_refused_search_add_does_not_scroll_the_deck_to_the_card() -> None:
    frame = _Frame(recording=True)
    frame._add_search_card_to_active_zone("Lightning Bolt")
    assert frame.focused == []


def test_a_refused_search_add_tells_the_user_why() -> None:
    frame = _Frame(recording=True)
    frame._add_search_card_to_active_zone("Lightning Bolt")
    assert frame.statuses == ["builder.locked.recording"]


@pytest.mark.parametrize("zone", ["main", "side"])
def test_regression_the_add_buttons_are_refused_while_recording(zone: str) -> None:
    """The Add to Main / Add to Side route is the one the panel's buttons and
    the 1-4 hotkeys take; it goes through the same lock."""
    frame = _Frame(recording=True)
    assert frame._add_search_card_to_zone(zone, "Pyroblast", 3) is False
    assert frame.zone_cards[zone] == []


def test_search_adds_resume_once_the_walk_is_over() -> None:
    frame = _Frame(recording=True)
    frame._add_search_card_to_active_zone("Lightning Bolt")
    frame._guide_record = None
    frame._add_search_card_to_active_zone("Lightning Bolt")
    assert frame.qty("main", "Lightning Bolt") == 1
