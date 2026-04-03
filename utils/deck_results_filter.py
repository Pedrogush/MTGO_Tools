"""Pure filter logic for deck results lists — no UI/wx dependency."""

from __future__ import annotations

import re
from typing import Any


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


def _normalize_date(value: str) -> str:
    """Extract the first YYYY-MM-DD substring from *value*, or return *value* as-is."""
    if not value:
        return ""
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    return match.group(0) if match else value


def filter_decks(
    decks: list[dict[str, Any]],
    event_type: str = "All",
    result_query: str = "",
    player_query: str = "",
    date_query: str = "",
) -> list[dict[str, Any]]:
    """Return the subset of *decks* that satisfy all active filters (AND logic).

    Parameters
    ----------
    decks:
        Full list of deck dicts, each optionally containing keys
        ``"event"``, ``"result"``, ``"player"``, and ``"date"``.
    event_type:
        Canonical event type to keep (``"Challenge"``, ``"League"``,
        ``"Showcase"``, ``"Last Chance"``), or ``"All"`` to skip this filter.
    result_query:
        Lowercase partial-match string against ``deck["result"]``.
    player_query:
        Lowercase partial-match string against ``deck["player"]``.
    date_query:
        Prefix string matched against the normalised ``YYYY-MM-DD`` date.
    """
    filtered = list(decks)
    if event_type != "All":
        filtered = [d for d in filtered if _classify_event_type(d.get("event", "")) == event_type]
    if result_query:
        filtered = [d for d in filtered if result_query in d.get("result", "").lower()]
    if player_query:
        filtered = [d for d in filtered if player_query in d.get("player", "").lower()]
    if date_query:
        filtered = [
            d for d in filtered if _normalize_date(d.get("date", "")).startswith(date_query)
        ]
    return filtered
