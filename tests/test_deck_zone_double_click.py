"""Double-click on a deck-zone card (issue #1027).

The gesture is deliberately mode-dependent, and these tests pin both meanings:

* **normal deck editing** — one copy comes out of the zone that was clicked;
* **sideboard-guide recording** — one copy crosses to the other zone instead,
  because that walk records the mainboard's diff against the base 75 as the
  matchup plan (:mod:`widgets.frames.app_frame.handlers.sideboard_guide_record`)
  and a plain removal would record a change no player can make between games.

The logic under test is the frame's, not the views': all three card views
(grid/table/pile) hit-test the double-click and report the card name, and
``CardTablePanel`` tags it with its zone, so ``_handle_zone_activate`` is the one
place the behaviour is decided.

``wx`` is not importable in the WSL dev environment, so a minimal stub is
installed before loading ``zone_editing.py`` by file path (the pattern used by
``tests/test_deck_builder_hotkeys.py``). The module only reads ``wx`` for the
dialogs on the zone-*add* path, which these tests never take.
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

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._counter = 1000

    def __getattr__(self, item: str) -> Any:
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


def _load_zone_editing() -> types.ModuleType:
    """Import ``zone_editing.py`` directly, bypassing the handlers package.

    The package ``__init__`` pulls in every app-frame handler (and through them
    real widget classes); this module needs only ``wx`` and ``utils.constants``.
    """
    path = (
        Path(__file__).resolve().parent.parent
        / "widgets"
        / "frames"
        / "app_frame"
        / "handlers"
        / "zone_editing.py"
    )
    spec = importlib.util.spec_from_file_location("_zone_editing_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_install_wx_stub()
ZoneEditingHandlers = _load_zone_editing().ZoneEditingHandlers


class _Frame(ZoneEditingHandlers):
    """The zone-editing surface of ``AppFrame`` with the re-render step faked.

    ``_after_zone_change`` is the humble edge: it repaints tables, rebuilds the
    deck text and writes session state. Recording which zones it was asked to
    re-render is enough to prove the mutation was reported.
    """

    def __init__(
        self,
        main: list[dict[str, Any]] | None = None,
        side: list[dict[str, Any]] | None = None,
        out: list[dict[str, Any]] | None = None,
        *,
        recording: bool = False,
    ) -> None:
        self.zone_cards: dict[str, list[dict[str, Any]]] = {
            "main": [dict(c) for c in main or []],
            "side": [dict(c) for c in side or []],
            "out": [dict(c) for c in out or []],
        }
        self._guide_record = {"archetypes": ["Izzet Murktide"], "index": 0} if recording else None
        self._active_deck_zone = "main"
        self.rendered: list[str] = []

    def _after_zone_change(self, zone: str) -> None:
        self.rendered.append(zone)

    def qty(self, zone: str, name: str) -> int:
        for entry in self.zone_cards[zone]:
            if entry["name"] == name:
                return entry["qty"]
        return 0


# ----- normal deck editing: a double-click takes one copy out -----


def test_double_click_removes_one_copy_from_the_mainboard() -> None:
    frame = _Frame(main=[{"name": "Lightning Bolt", "qty": 4}])
    frame._handle_zone_activate("main", "Lightning Bolt")
    assert frame.qty("main", "Lightning Bolt") == 3
    assert frame.rendered == ["main"]


def test_double_click_removes_one_copy_from_the_sideboard() -> None:
    frame = _Frame(side=[{"name": "Pyroblast", "qty": 2}])
    frame._handle_zone_activate("side", "Pyroblast")
    assert frame.qty("side", "Pyroblast") == 1
    assert frame.zone_cards["main"] == []


def test_double_clicking_the_last_copy_drops_the_card_from_the_zone() -> None:
    frame = _Frame(main=[{"name": "Island", "qty": 1}, {"name": "Mountain", "qty": 3}])
    frame._handle_zone_activate("main", "Island")
    assert [c["name"] for c in frame.zone_cards["main"]] == ["Mountain"]


def test_double_click_does_not_move_the_card_when_not_recording() -> None:
    """The removal branch must not touch the sibling zone."""
    frame = _Frame(main=[{"name": "Ragavan, Nimble Pilferer", "qty": 4}])
    frame._handle_zone_activate("main", "Ragavan, Nimble Pilferer")
    assert frame.zone_cards["side"] == []


def test_double_click_on_a_card_the_zone_no_longer_holds_changes_nothing() -> None:
    frame = _Frame(main=[{"name": "Island", "qty": 4}])
    frame._handle_zone_activate("main", "Brainstorm")
    assert frame.zone_cards["main"] == [{"name": "Island", "qty": 4}]
    assert frame.zone_cards["side"] == []


def test_double_click_tracks_the_zone_as_the_active_one() -> None:
    """The zone last acted on is where the search's '+' / double-click adds."""
    frame = _Frame(side=[{"name": "Pyroblast", "qty": 2}])
    frame._handle_zone_activate("side", "Pyroblast")
    assert frame._active_deck_zone == "side"


# ----- record mode: a double-click crosses zones -----


def test_recording_double_click_moves_a_mainboard_copy_to_the_sideboard() -> None:
    frame = _Frame(main=[{"name": "Lightning Bolt", "qty": 4}], recording=True)
    frame._handle_zone_activate("main", "Lightning Bolt")
    assert frame.qty("main", "Lightning Bolt") == 3
    assert frame.qty("side", "Lightning Bolt") == 1
    assert frame.rendered == ["main", "side"]


def test_recording_double_click_moves_a_sideboard_copy_to_the_mainboard() -> None:
    frame = _Frame(
        main=[{"name": "Lightning Bolt", "qty": 3}],
        side=[{"name": "Lightning Bolt", "qty": 1}],
        recording=True,
    )
    frame._handle_zone_activate("side", "Lightning Bolt")
    assert frame.qty("main", "Lightning Bolt") == 4
    assert frame.qty("side", "Lightning Bolt") == 0


def test_recording_double_click_adds_to_an_existing_destination_stack() -> None:
    frame = _Frame(
        main=[{"name": "Pyroblast", "qty": 2}],
        side=[{"name": "Pyroblast", "qty": 1}],
        recording=True,
    )
    frame._handle_zone_activate("main", "Pyroblast")
    assert frame.qty("main", "Pyroblast") == 1
    assert frame.qty("side", "Pyroblast") == 2


def test_recording_double_click_moves_exactly_one_copy_per_gesture() -> None:
    frame = _Frame(main=[{"name": "Lightning Bolt", "qty": 4}], recording=True)
    for _ in range(3):
        frame._handle_zone_activate("main", "Lightning Bolt")
    assert frame.qty("main", "Lightning Bolt") == 1
    assert frame.qty("side", "Lightning Bolt") == 3


def test_recording_double_click_on_an_absent_card_conjures_nothing() -> None:
    """A gesture aimed at a card the source zone doesn't hold must not create
    a copy in the destination — that would be recorded as "bring this in"."""
    frame = _Frame(main=[{"name": "Island", "qty": 4}], recording=True)
    frame._handle_zone_activate("main", "Force of Negation")
    assert frame.zone_cards["side"] == []
    assert frame.zone_cards["main"] == [{"name": "Island", "qty": 4}]
    assert frame.rendered == []


def test_recording_double_click_follows_the_card_to_the_destination_zone() -> None:
    frame = _Frame(main=[{"name": "Lightning Bolt", "qty": 4}], recording=True)
    frame._handle_zone_activate("main", "Lightning Bolt")
    assert frame._active_deck_zone == "side"


def test_recording_leaves_the_active_zone_alone_when_nothing_moved() -> None:
    frame = _Frame(side=[{"name": "Pyroblast", "qty": 1}], recording=True)
    frame._active_deck_zone = "side"
    frame._handle_zone_activate("side", "Not In The Deck")
    assert frame._active_deck_zone == "side"


@pytest.mark.parametrize("recording", [False, True])
def test_double_click_in_a_zone_with_no_sibling_always_removes(recording: bool) -> None:
    """The outboard has nothing to swap with, so it removes in both modes."""
    frame = _Frame(out=[{"name": "Wrenn and Six", "qty": 2}], recording=recording)
    frame._handle_zone_activate("out", "Wrenn and Six")
    assert frame.qty("out", "Wrenn and Six") == 1
    assert frame.zone_cards["main"] == []
    assert frame.zone_cards["side"] == []


# ----- the recording predicate the two branches hinge on -----


def test_recording_is_detected_only_while_a_walk_is_in_flight() -> None:
    frame = _Frame()
    assert frame._is_recording_guide() is False
    frame._guide_record = {"archetypes": ["Burn"], "index": 0}
    assert frame._is_recording_guide() is True
    frame._guide_record = None
    assert frame._is_recording_guide() is False


# ----- the shared move helper (also the drag-and-drop transfer path, #781) -----


def test_move_zone_copy_reports_whether_a_copy_was_actually_moved() -> None:
    frame = _Frame(main=[{"name": "Island", "qty": 1}])
    assert frame._move_zone_copy("main", "side", "Island") is True
    assert frame._move_zone_copy("main", "side", "Island") is False
    assert frame.qty("side", "Island") == 1


def test_move_zone_copy_matches_card_names_case_insensitively() -> None:
    frame = _Frame(main=[{"name": "Lightning Bolt", "qty": 2}])
    assert frame._move_zone_copy("main", "side", "lightning bolt") is True
    assert frame.qty("main", "Lightning Bolt") == 1
