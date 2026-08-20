"""The Deck Stats tab's data path, and the card types it is allowed to name.

Two defects shipped together in the #962 redesign, with one visible shape --
"the charts are empty" -- and two different causes:

*Nothing renders.* ``DeckStatsPanel`` reads card metadata through the
``CardDataManager`` the app frame pushes into it, and the only place that push
happens is the ``on_success`` the frame hands to
``AppController.ensure_card_data_loaded``. That method returned early whenever
the index was already loaded *or* already loading, dropping the caller's
callbacks on the floor -- and ``initialize_app`` step 5 pre-loads the index with
``on_success=lambda _: None``, so on any start where the pre-load won the race
the panel kept ``card_manager = None`` for the life of the process. Mana curve
and colour share then produced no items at all ("No data"), card types produced
a row of zeros, and only the opening-hand chart -- the one that needs no
metadata -- still drew.

*An "Other" card type.* There is no such card type. Rule 205.2a of the
Comprehensive Rules names all fifteen, and the app ships a copy of the rules;
what used to land in "Other" was every card the type-line match missed, which in
the state above was the whole deck. A card the database cannot describe is a
fact about the database, so it is now counted and stated as one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from controllers.app_controller.card_data import CardDataMixin
from repositories.card_repository.schemas import CardEntry
from services.comp_rules_service import parse_card_types
from utils.constants import COMP_RULES_TXT_FILE
from widgets.panels.deck_stats_panel.properties import DeckStatsPanelPropertiesMixin
from widgets.panels.deck_stats_panel.stats_constants import (
    CARD_TYPES,
    DECK_CARD_TYPES,
    card_types_in,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeCardManager:
    """The read surface ``DeckStatsPanel`` uses, over real ``CardEntry`` rows."""

    def __init__(self, cards: dict[str, dict[str, Any]], *, is_loaded: bool = True) -> None:
        self._cards = {
            name.lower(): CardEntry(
                name=name,
                name_lower=name.lower(),
                aliases=[],
                colors=list(fields.get("color_identity", [])),
                color_identity=list(fields.get("color_identity", [])),
                legalities={},
                mana_value=fields.get("mana_value"),
                type_line=fields.get("type_line"),
            )
            for name, fields in cards.items()
        }
        self._is_loaded = is_loaded

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def get_card(self, name: str) -> CardEntry | None:
        return self._cards.get(name.lower())


class _StatsPanel(DeckStatsPanelPropertiesMixin):
    """The panel's data getters over plain state.

    The mixin carries no ``__init__`` of its own precisely so the panel owns its
    state, which lets the item helpers be exercised without a wx window.
    """

    def __init__(self, main: list[dict[str, Any]], card_manager: Any) -> None:
        self.zone_cards = {"main": main, "side": [], "out": []}
        self.card_manager = card_manager


class _FakeCardService:
    """``CardService``'s loading-lifecycle surface, with real flag semantics."""

    def __init__(self, *, manager: Any = None, loading: bool = False) -> None:
        self._manager = manager
        self._loading = loading
        self._ready = manager is not None

    def is_card_data_loaded(self) -> bool:
        return self._manager is not None and self._manager.is_loaded

    def is_card_data_loading(self) -> bool:
        return self._loading

    def set_card_data_loading(self, loading: bool) -> None:
        self._loading = loading

    def set_card_data_ready(self, ready: bool) -> None:
        self._ready = ready

    def get_card_manager(self) -> Any:
        return self._manager

    def set_card_manager(self, manager: Any) -> None:
        self._manager = manager

    def ensure_card_data_loaded(self, force: bool = False) -> Any:
        return self._manager


class _DeferredWorker:
    """Holds the submitted job so the test can land it when it chooses.

    The real ``BackgroundWorker`` runs the job on a thread and marshals the
    callbacks back through ``wx.CallAfter``; what matters here is only that the
    callbacks arrive *later*, which is the window the dropped-callback bug lived
    in.
    """

    def __init__(self) -> None:
        self.pending: list[tuple[Any, Any, Any]] = []

    def submit(self, func: Any, on_success: Any = None, on_error: Any = None) -> None:
        self.pending.append((func, on_success, on_error))

    def land(self, result: Any) -> None:
        _func, on_success, _on_error = self.pending.pop()
        on_success(result)

    def fail(self, error: Exception) -> None:
        _func, _on_success, on_error = self.pending.pop()
        on_error(error)


class _Controller(CardDataMixin):
    """``AppController``'s card-data mixin over the doubles above."""

    def __init__(self, card_service: _FakeCardService) -> None:
        self.card_service = card_service
        self._worker = _DeferredWorker()
        self._card_data_waiters: list[Any] = []


def _panel(
    cards: dict[str, dict[str, Any]], deck: dict[str, int], *, with_card_data: bool
) -> _StatsPanel:
    main = [{"name": name, "qty": qty} for name, qty in deck.items()]
    return _StatsPanel(main, _FakeCardManager(cards) if with_card_data else None)


_DECK = {
    "Lightning Bolt": {"type_line": "Instant", "mana_value": 1, "color_identity": ["R"]},
    "Mountain": {"type_line": "Basic Land — Mountain", "mana_value": 0, "color_identity": []},
    "Goblin Guide": {
        "type_line": "Creature — Goblin Scout",
        "mana_value": 1,
        "color_identity": ["R"],
    },
    "Wrenn and Six": {
        "type_line": "Legendary Planeswalker — Wrenn",
        "mana_value": 2,
        "color_identity": ["R", "G"],
    },
}
_QUANTITIES = {"Lightning Bolt": 4, "Mountain": 20, "Goblin Guide": 4, "Wrenn and Six": 2}


# ---------------------------------------------------------------------------
# The charts get real data
# ---------------------------------------------------------------------------


def test_a_card_manager_that_lands_mid_load_still_reaches_its_caller() -> None:
    """The exact startup shape that emptied the tab.

    Step 5 of ``initialize_app`` starts the pre-load with a no-op ``on_success``;
    the app frame asks a moment later, on behalf of the stats panel and the card
    inspector. Before the fix the second call saw ``is_card_data_loading()`` and
    returned, so nothing was ever handed to the panel.
    """
    service = _FakeCardService()
    controller = _Controller(service)
    delivered: list[Any] = []

    controller.ensure_card_data_loaded(
        on_success=lambda _manager: None,  # the pre-load, as lifecycle.py writes it
        on_error=lambda _exc: None,
        on_status=lambda *_a, **_kw: None,
    )
    controller.ensure_card_data_loaded(
        on_success=delivered.append,  # the frame, on behalf of the stats panel
        on_error=lambda _exc: None,
        on_status=lambda *_a, **_kw: None,
    )
    assert delivered == [], "nothing can be delivered while the load is still in flight"

    manager = _FakeCardManager({})
    controller._worker.land(manager)

    assert delivered == [manager]
    assert controller._card_data_waiters == []


def test_a_card_manager_that_already_landed_is_handed_over_immediately() -> None:
    """The other half of the early return: asking after the load has finished."""
    manager = _FakeCardManager({})
    controller = _Controller(_FakeCardService(manager=manager))
    delivered: list[Any] = []

    controller.ensure_card_data_loaded(
        on_success=delivered.append,
        on_error=lambda _exc: None,
        on_status=lambda *_a, **_kw: None,
    )

    assert delivered == [manager]
    assert controller._worker.pending == [], "an already-loaded index must not be reloaded"


def test_a_failed_load_reaches_every_caller_waiting_on_it() -> None:
    """A dropped ``on_error`` is the same silent failure as a dropped success."""
    controller = _Controller(_FakeCardService())
    failures: list[Exception] = []

    controller.ensure_card_data_loaded(
        on_success=lambda _manager: None,
        on_error=lambda _exc: None,
        on_status=lambda *_a, **_kw: None,
    )
    controller.ensure_card_data_loaded(
        on_success=lambda _manager: None,
        on_error=failures.append,
        on_status=lambda *_a, **_kw: None,
    )

    error = RuntimeError("card index unreadable")
    controller._worker.fail(error)

    assert failures == [error]
    assert controller.card_service.is_card_data_loading() is False


def test_the_three_metadata_charts_carry_counts_once_the_manager_is_there() -> None:
    """The visible assertion: bars and counts, not "No data"."""
    panel = _panel(_DECK, _QUANTITIES, with_card_data=True)

    curve = panel._curve_items()
    colors = panel._color_items()
    types = {label: count for label, count, _max, _colour, _tip in panel._type_items()}

    assert [label for label, *_rest in curve] == ["0", "1", "2"]
    assert [value for _label, value, *_rest in curve] == ["20", "8", "2"]
    assert [label for label, *_rest in colors] == ["Colorless", "R", "G"]
    assert types["Land"] == 20
    assert types["Creature"] == 4
    assert types["Instant"] == 4
    assert types["Planeswalker"] == 2
    assert panel._unclassified_count() == 0


def test_without_card_data_the_type_chart_invents_nothing() -> None:
    """The pre-fix rendering put all 30 cards in an "Other" bar.

    Empty is the honest answer here, and the count of cards the database could
    not describe is reported beside the summary instead.
    """
    panel = _panel(_DECK, _QUANTITIES, with_card_data=False)

    assert panel._curve_items() == []
    assert panel._color_items() == []
    assert {count for _label, count, *_rest in panel._type_items()} == {0}
    assert panel._unclassified_count() == sum(_QUANTITIES.values())


# ---------------------------------------------------------------------------
# ...and only rules card types
# ---------------------------------------------------------------------------


def test_no_chart_row_is_labelled_with_something_that_is_not_a_card_type() -> None:
    """Whatever the data does, every row this chart draws is a rule 205.2a type."""
    for with_card_data in (True, False):
        panel = _panel(_DECK, _QUANTITIES, with_card_data=with_card_data)
        labels = [label for label, *_rest in panel._type_items()]
        assert "Other" not in labels
        assert set(labels) <= set(CARD_TYPES)


def test_the_rarer_card_types_get_a_row_only_when_the_deck_has_one() -> None:
    """Six of the fifteen types cannot appear in a constructed deck.

    They are still real card types and still classified; they just do not each
    take a permanently-empty row in a chart about a 60-card decklist.
    """
    plain = _panel(_DECK, _QUANTITIES, with_card_data=True)
    assert [label for label, *_rest in plain._type_items()] == list(DECK_CARD_TYPES)

    cards = dict(_DECK) | {"Tazeem": {"type_line": "Plane — Zendikar", "color_identity": []}}
    with_plane = _panel(cards, _QUANTITIES | {"Tazeem": 1}, with_card_data=True)
    rows = {label: count for label, count, _max, _colour, _tip in with_plane._type_items()}
    assert rows["Plane"] == 1
    assert rows["Planeswalker"] == 2, "'Plane' is a prefix of 'Planeswalker', not the same type"


@pytest.mark.parametrize(
    ("type_line", "expected"),
    [
        ("Instant", {"Instant"}),
        ("Basic Snow Land — Forest", {"Land"}),
        ("Legendary Artifact Creature — Golem", {"Artifact", "Creature"}),
        ("Instant // Sorcery", {"Instant", "Sorcery"}),
        ("Kindred Instant — Elf", {"Kindred", "Instant"}),
        # Subtypes are not card types: this is a creature, not a dungeon.
        ("Creature — Human Dungeon", {"Creature"}),
        ("", set()),
        (None, set()),
    ],
)
def test_card_types_are_read_off_the_type_line_as_words(
    type_line: str | None, expected: set[str]
) -> None:
    assert card_types_in(type_line) == expected


def test_the_type_list_is_the_one_the_comprehensive_rules_defines() -> None:
    """Rule 205.2a, read out of the copy of the rules the app itself ships.

    Skipped rather than failed when the cache is absent (a fresh checkout
    downloads it in the background at first launch); the parser itself is
    covered against a fixture in ``tests/test_comp_rules_service.py``.
    """
    rules = Path(COMP_RULES_TXT_FILE)
    if not rules.exists():
        pytest.skip(f"no cached Comprehensive Rules at {rules}")

    from_rules = parse_card_types(rules.read_text(encoding="utf-8"))

    assert from_rules, "205.2a not found in the cached rules"
    assert set(CARD_TYPES) == set(from_rules)
    assert "Other" not in from_rules
    assert set(DECK_CARD_TYPES) <= set(from_rules)
