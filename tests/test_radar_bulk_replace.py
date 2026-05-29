"""Tests for the single-transaction bulk path of :class:`RadarRepository`."""

from __future__ import annotations

import pytest

from repositories.radar_repository import RadarRepository


def _radar(*, fmt: str, href: str, name: str, decks: int, mb: list[dict] | None = None) -> dict:
    return {
        "format": fmt,
        "generated_at": "2026-05-01T00:00:00Z",
        "source": "test",
        "archetype": {"name": name, "href": href},
        "total_decks_analyzed": decks,
        "decks_failed": 0,
        "mainboard_cards": mb or [],
        "sideboard_cards": [],
    }


def _card(name: str, *, copies: int) -> dict:
    return {
        "card_name": name,
        "appearances": copies,
        "total_copies": copies * 2,
        "max_copies": 4,
        "avg_copies": 2.0,
        "inclusion_rate": 0.5,
        "expected_copies": 1.0,
        "copy_distribution": {"4": copies},
    }


@pytest.fixture
def repo(tmp_path):
    return RadarRepository(tmp_path / "radar_cache.db")


def test_bulk_replace_persists_all_entries(repo):
    entries = [
        _radar(
            fmt="modern", href="modern-burn", name="Burn", decks=10, mb=[_card("Bolt", copies=10)]
        ),
        _radar(fmt="modern", href="modern-prowess", name="Prowess", decks=20),
        _radar(fmt="legacy", href="legacy-control", name="Control", decks=5),
    ]

    replaced = repo.bulk_replace(entries)

    assert replaced == 3
    burn = repo.get_radar("modern", "modern-burn")
    assert burn is not None
    assert burn.total_decks_analyzed == 10
    assert [c.card_name for c in burn.mainboard_cards] == ["Bolt"]
    assert repo.get_total_decks("modern") == 30
    assert repo.get_total_decks("legacy") == 5


def test_bulk_replace_skips_invalid_entries(repo):
    entries = [
        _radar(fmt="modern", href="modern-burn", name="Burn", decks=10),
        {"format": "", "archetype": {"href": "x"}},  # missing format
        {"format": "modern", "archetype": {"href": ""}},  # missing href
        {"format": "modern", "archetype": "not-a-dict"},  # malformed archetype
    ]

    replaced = repo.bulk_replace(entries)

    assert replaced == 1
    assert repo.get_radar("modern", "modern-burn") is not None


def test_bulk_replace_overwrites_existing_snapshot(repo):
    repo.bulk_replace(
        [
            _radar(
                fmt="modern",
                href="modern-burn",
                name="Burn",
                decks=10,
                mb=[_card("Bolt", copies=4)],
            )
        ]
    )
    # Re-hydrate with new data for the same key.
    repo.bulk_replace(
        [
            _radar(
                fmt="modern",
                href="modern-burn",
                name="Burn",
                decks=99,
                mb=[_card("Bolt", copies=8)],
            )
        ]
    )

    burn = repo.get_radar("modern", "modern-burn")
    assert burn is not None
    assert burn.total_decks_analyzed == 99
    assert burn.mainboard_cards[0].appearances == 8


def test_bulk_replace_empty_returns_zero(repo):
    assert repo.bulk_replace([]) == 0
