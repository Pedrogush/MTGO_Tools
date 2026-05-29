"""Tests for FormatCardPoolRepository read caching and connection reuse.

Covers issue #522: reads share a persistent SQLite connection and memoize the
hover/selection hot path (``get_card_total`` / ``get_summary``), and writes
invalidate that state so the next read sees the new snapshot.
"""

from __future__ import annotations

import pytest

from repositories.format_card_pool_repository import FormatCardPoolRepository


@pytest.fixture
def repo(tmp_path):
    return FormatCardPoolRepository(db_path=tmp_path / "format_card_pool.db")


def _entry(format_name="modern", cards=None, copy_totals=None):
    return {
        "format": format_name,
        "generated_at": "2026-05-29",
        "source": "test",
        "total_decks_analyzed": 10,
        "decks_failed": 0,
        "cards": cards if cards is not None else ["Lightning Bolt", "Brainstorm"],
        "copy_totals": (
            copy_totals
            if copy_totals is not None
            else [{"card_name": "Lightning Bolt", "copies_played": 40}]
        ),
    }


def test_get_card_total_and_summary_basic(repo):
    assert repo.replace_format_pool(_entry()) is True

    assert repo.get_card_total("modern", "Lightning Bolt") == 40
    # tracked but never played -> 0, not None
    assert repo.get_card_total("modern", "Brainstorm") == 0
    # absent from snapshot -> None
    assert repo.get_card_total("modern", "Nonexistent Card") is None

    summary = repo.get_summary("modern")
    assert summary is not None
    assert summary.unique_cards == 2
    assert summary.total_decks_analyzed == 10


def test_read_connection_is_persistent(repo):
    repo.replace_format_pool(_entry())
    repo.get_card_total("modern", "Lightning Bolt")
    first = repo._read_conn_obj
    assert first is not None
    repo.get_summary("modern")
    assert repo._read_conn_obj is first


def test_card_total_is_memoized(repo):
    repo.replace_format_pool(_entry())
    repo.get_card_total("modern", "Lightning Bolt")
    assert ("modern", "Lightning Bolt") in repo._card_total_cache
    # Mutate the row directly via a separate connection; the memoized value
    # must persist until an explicit invalidation.
    with repo._connect() as conn:
        conn.execute(
            "UPDATE format_card_pool_cards SET copies_played = 999 "
            "WHERE format_name = ? AND card_name = ?",
            ("modern", "Lightning Bolt"),
        )
        conn.commit()
    assert repo.get_card_total("modern", "Lightning Bolt") == 40


def test_summary_negative_lookup_is_cached(repo):
    assert repo.get_summary("legacy") is None
    assert "legacy" in repo._summary_cache
    assert repo._summary_cache["legacy"] is None


def test_write_invalidates_read_caches(repo):
    repo.replace_format_pool(_entry())
    assert repo.get_card_total("modern", "Lightning Bolt") == 40
    assert repo.get_summary("modern").unique_cards == 2
    prev_conn = repo._read_conn_obj

    # New snapshot for the same format with different data.
    repo.replace_format_pool(
        _entry(
            cards=["Lightning Bolt"],
            copy_totals=[{"card_name": "Lightning Bolt", "copies_played": 7}],
        )
    )

    assert repo._card_total_cache == {}
    assert repo._summary_cache == {}
    assert repo._read_conn_obj is None or repo._read_conn_obj is not prev_conn

    assert repo.get_card_total("modern", "Lightning Bolt") == 7
    assert repo.get_card_total("modern", "Brainstorm") is None
    assert repo.get_summary("modern").unique_cards == 1


def test_bulk_replace_invalidates(repo):
    repo.replace_format_pool(_entry())
    assert repo.get_card_total("modern", "Lightning Bolt") == 40
    repo.bulk_replace(
        [
            _entry(
                copy_totals=[{"card_name": "Lightning Bolt", "copies_played": 3}],
            )
        ]
    )
    assert repo.get_card_total("modern", "Lightning Bolt") == 3
