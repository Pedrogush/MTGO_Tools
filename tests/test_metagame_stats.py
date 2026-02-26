from datetime import datetime, timedelta
from typing import Any

try:
    from datetime import UTC
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from datetime import timezone

    UTC = timezone.utc  # noqa: F811,UP017

from utils.metagame_stats import (
    _filter_decks,
    count_decks_by_archetype,
    count_decks_by_event,
    count_decks_by_player,
)


def _deck(publish_offset_days: int, fmt: str, archetype: str, player: str, event_name: str) -> dict:
    publish = (datetime.now(UTC) - timedelta(days=publish_offset_days)).isoformat()
    return {
        "publish_date": publish,
        "format": fmt,
        "archetype": archetype,
        "deck_name": archetype,
        "player": player,
        "event_name": event_name,
        "mainboard": [],
        "sideboard": [],
    }


def sample_decks() -> list[dict[str, Any]]:
    return [
        _deck(1, "Modern", "Temur Rhinos", "Alice", "Modern Challenge 64"),
        _deck(2, "Modern", "Temur Rhinos", "Bob", "Modern Challenge 64"),
        _deck(3, "Modern", "Amulet Titan", "Charlie", "Modern Challenge 32"),
        _deck(4, "Modern", "Modern Challenge 32", "Dana", "Modern Challenge 32"),
        _deck(5, "Pioneer", "Rakdos Midrange", "Evan", "Pioneer Challenge"),
    ]


def test_filter_decks_respects_format_and_days():
    filtered = _filter_decks(sample_decks(), fmt="Modern", days=3)
    assert len(filtered) == 3  # only modern decks within 3 days
    assert all(d["format"].lower() == "modern" for d in filtered)


def test_count_functions_group_expected_fields():
    modern_decks = _filter_decks(sample_decks(), fmt="Modern", days=7)
    archetypes = count_decks_by_archetype(modern_decks, fmt="Modern", days=7)
    assert archetypes[0] == ("Temur Rhinos", 2)

    players = count_decks_by_player(modern_decks, fmt="Modern", days=7)
    assert ("Alice", 1) in players
    assert ("Dana", 1) in players

    events = count_decks_by_event(modern_decks, fmt="Modern", days=7)
    assert events[0][0].startswith("Modern Challenge")
    assert sum(count for _, count in events) == len(modern_decks)
