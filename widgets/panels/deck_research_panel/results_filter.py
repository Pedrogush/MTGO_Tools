"""Pure filter logic for deck results lists — no UI/wx dependency."""

from __future__ import annotations

import operator as _op
import re
from collections.abc import Callable
from datetime import date
from typing import Any

from utils.deck_dates import repair_future_date

PLACEMENT_OP_NONE = "-"
PLACEMENT_OPERATORS: tuple[str, ...] = (PLACEMENT_OP_NONE, ">", "≥", "≤", "<", "=")
PLACEMENT_FIELDS: tuple[str, ...] = ("Placement", "Wins")

#: The event-type filter's canonical values, in the order the choice lists them.
#: ``"All"`` is the catch-all this module compares against; the other four are
#: the labels :func:`_classify_event_type` produces.
#:
#: Both this and :data:`PLACEMENT_FIELDS` are **values, not labels**. They are
#: matched against here, persisted by
#: :class:`controllers.session_manager.DeckSelectorSessionManager`, and passed
#: across the automation protocol, so they stay English and stay stable. What
#: the user reads is looked up from the locale catalogue at the point the
#: ``wx.Choice`` is built -- see
#: ``widgets/panels/deck_research_panel/frame/filters.py``. Until phase 9 the
#: two were the same strings, which is why phase 7's translated ``Result``
#: label sat above two untranslated options in pt-BR.
EVENT_TYPE_VALUES: tuple[str, ...] = (
    "All",
    "Challenge",
    "League",
    "Showcase",
    "Last Chance",
)

_OPERATOR_FUNCS: dict[str, Callable[[int, int], bool]] = {
    ">": _op.gt,
    "≥": _op.ge,
    "≤": _op.le,
    "<": _op.lt,
    "=": _op.eq,
}

# Placement uses "better means smaller number" semantics: "> 8th" reads as
# "did better than 8th" (1st–7th), so flip comparator direction for that field.
_INVERTED_OPERATORS: dict[str, str] = {
    ">": "<",
    "≥": "≤",
    "≤": "≥",
    "<": ">",
    "=": "=",
}

_PLACEMENT_RE = re.compile(r"\b(?:top\s*)?(\d+)(?:st|nd|rd|th)?\b", re.IGNORECASE)
_WINS_RE = re.compile(r"\b(\d+)\s*-\s*\d+\b")


def _classify_event_type(event_str: str) -> str | None:
    """Return a canonical event type label for the given event string, or None."""
    lower = event_str.lower()
    if "last chance" in lower:
        return "Last Chance"
    if "showcase" in lower:
        return "Showcase"
    if "challenge" in lower:
        return "Challenge"
    if "league" in lower:
        return "League"
    return None


def _normalize_date(value: str, today: date | None = None) -> str:
    """Extract the first YYYY-MM-DD substring from *value*, or return *value* as-is.

    Extracted dates pass through :func:`repair_future_date`, so the UI never
    displays an impossible future date: upstream day/month transpositions are
    swapped back, and unrepairable future dates render blank.
    """
    if not value:
        return ""
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    return repair_future_date(match.group(0), today) if match else value


def parse_placement(result_str: str) -> int | None:
    """Extract a placement integer from a result string like ``"1st"`` or ``"Top 8"``.

    Returns None for record-style results (``"5-0"``) or unparseable strings
    (``"Winner"``).
    """
    if not result_str or "-" in result_str:
        return None
    match = _PLACEMENT_RE.search(result_str)
    if match is None:
        return None
    # The capture group is ``\d+``, so ``int()`` cannot raise here.
    return int(match.group(1))


def parse_wins(result_str: str) -> int | None:
    """Extract the wins count from a record-style result string like ``"5-0"``.

    Returns None for non-record results (``"1st"``, ``"Top 8"``).
    """
    if not result_str:
        return None
    match = _WINS_RE.search(result_str)
    if match is None:
        return None
    # The capture group is ``\d+``, so ``int()`` cannot raise here.
    return int(match.group(1))


def _placement_value_for_field(result_str: str, field: str) -> int | None:
    if field == "Placement":
        return parse_placement(result_str)
    if field == "Wins":
        return parse_wins(result_str)
    return None


def filter_decks(
    decks: list[dict[str, Any]],
    event_type: str = "All",
    placement_op: str = PLACEMENT_OP_NONE,
    placement_field: str = "Placement",
    placement_value: str = "",
    player_query: str = "",
    date_query: str = "",
) -> list[dict[str, Any]]:
    """Return the subset of *decks* that satisfy all active filters (AND logic).

    The placement filter is a numeric comparison on a value parsed from
    ``deck["result"]``. ``placement_field`` selects which value to parse
    (``"Placement"`` for ``"1st"`` / ``"Top 8"`` style results, ``"Wins"``
    for record-style ``"5-0"`` results). Decks whose result does not yield
    a parseable value for the chosen field are excluded when the filter
    is active. ``placement_op`` of ``"-"`` (or empty) skips the filter.
    For ``Placement``, comparator direction is inverted so ``">"`` reads
    as "better than" (smaller ordinal).
    """
    filtered = list(decks)
    if event_type != "All":
        filtered = [d for d in filtered if _classify_event_type(d.get("event", "")) == event_type]
    if placement_op and placement_op != PLACEMENT_OP_NONE and placement_value:
        effective_op = (
            _INVERTED_OPERATORS.get(placement_op, placement_op)
            if placement_field == "Placement"
            else placement_op
        )
        op_func = _OPERATOR_FUNCS.get(effective_op)
        try:
            target = int(placement_value)
        except ValueError:
            target = None
        if op_func is not None and target is not None and placement_field in PLACEMENT_FIELDS:
            filtered = [
                d
                for d in filtered
                if (val := _placement_value_for_field(d.get("result", ""), placement_field))
                is not None
                and op_func(val, target)
            ]
    if player_query:
        filtered = [d for d in filtered if player_query in d.get("player", "").lower()]
    if date_query:
        filtered = [
            d for d in filtered if _normalize_date(d.get("date", "")).startswith(date_query)
        ]
    return filtered
