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


def test_bulk_replace_returns_count_and_persists_all(repo):
    # Multiple distinct formats: the return value is the number of entries
    # successfully replaced, and each snapshot must be persisted.
    replaced = repo.bulk_replace([_entry(), _entry("legacy")])
    assert replaced == 2
    assert repo.get_card_total("modern", "Lightning Bolt") == 40
    assert repo.get_card_total("legacy", "Lightning Bolt") == 40


def test_bulk_replace_skips_invalid_entries(repo):
    # A bad entry (missing format / non-list cards) is rejected by
    # replace_format_pool (returns False), so it is not counted and valid
    # entries still persist.
    replaced = repo.bulk_replace(
        [
            {},
            _entry(),
            {"format": "legacy", "cards": "notalist"},
        ]
    )
    assert replaced == 1
    assert repo.get_card_total("modern", "Lightning Bolt") == 40
    assert repo.get_summary("legacy") is None


def test_replace_format_pool_rejects_invalid_entries(repo):
    # Missing format, blank/whitespace format, and non-list cards are all
    # data-integrity guards on the write path and must return False without
    # persisting anything.
    assert repo.replace_format_pool({}) is False
    assert repo.replace_format_pool({"format": "   "}) is False
    assert repo.replace_format_pool({"format": "modern", "cards": "notalist"}) is False

    assert repo.get_summary("modern") is None
    assert repo.get_card_total("modern", "Lightning Bolt") is None


def test_list_formats_and_has_format_pool(repo):
    # No snapshots yet: list is empty and lookups are false.
    assert repo.list_formats() == []
    assert repo.has_format_pool("modern") is False

    repo.replace_format_pool(_entry("modern"))
    repo.replace_format_pool(_entry("legacy"))

    # list_formats is sorted ascending and contains exactly the stored formats.
    assert repo.list_formats() == ["legacy", "modern"]

    # has_format_pool is case-insensitive and whitespace-trimmed for present
    # formats, and false for absent ones.
    assert repo.has_format_pool("modern") is True
    assert repo.has_format_pool("  MODERN  ") is True
    assert repo.has_format_pool("pauper") is False


def test_has_format_pool_blank_input(repo):
    repo.replace_format_pool(_entry())
    assert repo.has_format_pool("") is False
    assert repo.has_format_pool("   ") is False


def test_get_card_names_semantics(repo):
    # get_card_names returns every tracked card (including never-played ones),
    # not just those with copies > 0.
    repo.replace_format_pool(_entry())
    assert repo.get_card_names("modern") == {"Lightning Bolt", "Brainstorm"}
    # Unknown format and blank input both return an empty set.
    assert repo.get_card_names("legacy") == set()
    assert repo.get_card_names("   ") == set()


def test_get_top_cards_semantics(repo):
    repo.replace_format_pool(
        _entry(
            cards=["Lightning Bolt", "Brainstorm", "Counterspell"],
            copy_totals=[
                {"card_name": "Lightning Bolt", "copies_played": 40},
                {"card_name": "Counterspell", "copies_played": 12},
                {"card_name": "Brainstorm", "copies_played": 0},
            ],
        )
    )

    top = repo.get_top_cards("modern")
    # Ordered by copies_played desc; never-played cards (0) are excluded.
    assert [(t.card_name, t.copies_played) for t in top] == [
        ("Lightning Bolt", 40),
        ("Counterspell", 12),
    ]

    # limit is honoured and floored to at least 1.
    assert [t.card_name for t in repo.get_top_cards("modern", limit=1)] == ["Lightning Bolt"]
    assert len(repo.get_top_cards("modern", limit=0)) == 1

    # Unknown format and blank input return an empty list.
    assert repo.get_top_cards("legacy") == []
    assert repo.get_top_cards("   ") == []


def test_read_path_blank_input_guards(repo):
    repo.replace_format_pool(_entry())
    # Blank/whitespace format short-circuits before touching the DB.
    assert repo.get_card_total("   ", "Lightning Bolt") is None
    assert repo.get_summary("   ") is None
    # Blank card name on get_card_total also returns None.
    assert repo.get_card_total("modern", "") is None


def test_copies_played_coercion_falls_back_to_zero(repo):
    # Non-numeric, None, and missing copies_played must coerce to 0 rather than
    # corrupting the stored total or raising.
    assert (
        repo.replace_format_pool(
            _entry(
                cards=["Lightning Bolt", "Brainstorm", "Counterspell"],
                copy_totals=[
                    {"card_name": "Lightning Bolt", "copies_played": "oops"},
                    {"card_name": "Brainstorm", "copies_played": None},
                    {"card_name": "Counterspell"},
                ],
            )
        )
        is True
    )

    assert repo.get_card_total("modern", "Lightning Bolt") == 0
    assert repo.get_card_total("modern", "Brainstorm") == 0
    assert repo.get_card_total("modern", "Counterspell") == 0
