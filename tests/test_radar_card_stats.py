"""Tests for cross-archetype card-usage aggregation in :class:`RadarService`."""

from __future__ import annotations

import pytest

from repositories.radar_repository import RadarRepository
from services.radar_service import RadarService
from services.radar_service.card_stats import CardUsageStats


def _radar(
    *,
    fmt: str,
    href: str,
    name: str,
    decks: int,
    mb: list[dict] | None = None,
    sb: list[dict] | None = None,
) -> dict:
    return {
        "format": fmt,
        "generated_at": "2026-05-01T00:00:00Z",
        "source": "test",
        "archetype": {"name": name, "href": href},
        "total_decks_analyzed": decks,
        "decks_failed": 0,
        "mainboard_cards": mb or [],
        "sideboard_cards": sb or [],
    }


def _card(
    name: str,
    *,
    appearances: int,
    total_copies: int,
    avg_copies: float,
    expected_copies: float,
    inclusion_rate: float = 0.0,
    max_copies: int = 4,
) -> dict:
    return {
        "card_name": name,
        "appearances": appearances,
        "total_copies": total_copies,
        "max_copies": max_copies,
        "avg_copies": avg_copies,
        "inclusion_rate": inclusion_rate,
        "expected_copies": expected_copies,
        "copy_distribution": {},
    }


@pytest.fixture
def populated_repo(tmp_path):
    repo = RadarRepository(tmp_path / "radar_cache.db")
    # Modern: Bolt mainboard in two archetypes, Counterspell in sideboard of one
    repo.replace_radar(
        _radar(
            fmt="modern",
            href="modern-burn",
            name="Burn",
            decks=10,
            mb=[
                _card(
                    "Lightning Bolt",
                    appearances=10,
                    total_copies=40,
                    avg_copies=4.0,
                    expected_copies=4.0,
                ),
            ],
        )
    )
    repo.replace_radar(
        _radar(
            fmt="modern",
            href="modern-prowess",
            name="Prowess",
            decks=20,
            mb=[
                _card(
                    "Lightning Bolt",
                    appearances=15,
                    total_copies=45,
                    avg_copies=3.0,
                    expected_copies=2.25,
                ),
            ],
            sb=[
                _card(
                    "Counterspell",
                    appearances=4,
                    total_copies=8,
                    avg_copies=2.0,
                    expected_copies=0.4,
                ),
            ],
        )
    )
    # Legacy: only Counterspell mainboard
    repo.replace_radar(
        _radar(
            fmt="legacy",
            href="legacy-control",
            name="Control",
            decks=5,
            mb=[
                _card(
                    "Counterspell",
                    appearances=5,
                    total_copies=20,
                    avg_copies=4.0,
                    expected_copies=4.0,
                ),
            ],
        )
    )
    return repo


def test_get_card_aggregates_rolls_up_archetypes(populated_repo):
    aggregates = populated_repo.get_card_aggregates(
        "modern", ["Lightning Bolt", "Counterspell", "Nonsense"]
    )

    bolt = aggregates["Lightning Bolt"]
    assert bolt.mainboard_archetypes == 2
    assert bolt.sideboard_archetypes == 0
    assert bolt.mainboard_copies == 85
    assert bolt.mainboard_appearances == 25

    counter = aggregates["Counterspell"]
    assert counter.mainboard_archetypes == 0
    assert counter.sideboard_archetypes == 1
    assert counter.sideboard_copies == 8
    assert counter.sideboard_appearances == 4

    # Cards not in any archetype still get a zero-filled entry so the UI can render.
    nonsense = aggregates["Nonsense"]
    assert nonsense.mainboard_copies == 0
    assert nonsense.mainboard_appearances == 0


def test_get_total_decks_sums_across_archetypes(populated_repo):
    assert populated_repo.get_total_decks("modern") == 30
    assert populated_repo.get_total_decks("legacy") == 5
    assert populated_repo.get_total_decks("unknown") == 0


def test_get_formats_for_cards_lists_only_formats_with_appearances(populated_repo):
    legalities = populated_repo.get_formats_for_cards(["Lightning Bolt", "Counterspell"])
    assert legalities["Lightning Bolt"] == ["modern"]
    # Counterspell shows up in both modern (sideboard) and legacy (mainboard).
    assert legalities["Counterspell"] == ["legacy", "modern"]


def test_card_usage_stats_derived_averages(populated_repo):
    service = RadarService(radar_repository=populated_repo)
    usage = service.get_card_usage_stats("modern", ["Lightning Bolt", "Counterspell"])

    bolt: CardUsageStats = usage["Lightning Bolt"]
    assert bolt.total_decks == 30
    # Karsten = total copies / decks containing the card
    assert bolt.mainboard_avg_karsten == pytest.approx(85 / 25)
    # Arithmetic = total copies / every deck in the format
    assert bolt.mainboard_avg_arithmetic == pytest.approx(85 / 30)
    # Card never seen in sideboard → averages collapse to None for stable rendering
    assert bolt.sideboard_avg_karsten is None

    counter = usage["Counterspell"]
    assert counter.sideboard_avg_karsten == pytest.approx(8 / 4)
    assert counter.sideboard_avg_arithmetic == pytest.approx(8 / 30)


def test_card_usage_stats_handles_unknown_card(populated_repo):
    service = RadarService(radar_repository=populated_repo)
    usage = service.get_card_usage_stats("modern", ["Truly Nonexistent"])
    stats = usage["Truly Nonexistent"]
    assert stats.mainboard_archetypes == 0
    assert stats.mainboard_avg_karsten is None
    assert stats.mainboard_avg_arithmetic == 0.0
