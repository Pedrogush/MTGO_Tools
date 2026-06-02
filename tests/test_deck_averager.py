"""Tests for DeckAverager Karsten and arithmetic averaging methods."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from services.deck_service.averager import DeckAverager


@pytest.fixture()
def averager():
    return DeckAverager()


# ──────────────────────────── Karsten buffer ────────────────────────────────


def test_add_deck_to_karsten_buffer_single_deck(averager):
    buf = averager.add_deck_to_karsten_buffer({}, "4 Lightning Bolt\n2 Island")
    # 4 copies → keys #1-#4
    assert buf["Lightning Bolt\x001"] == 1
    assert buf["Lightning Bolt\x004"] == 1
    assert buf["Island\x001"] == 1
    assert buf["Island\x002"] == 1
    assert "Island\x003" not in buf


def test_add_deck_to_karsten_buffer_accumulates(averager):
    buf: dict[str, int] = {}
    buf = averager.add_deck_to_karsten_buffer(buf, "4 Mountain")
    buf = averager.add_deck_to_karsten_buffer(buf, "3 Mountain")
    # Mountain#1-#3 appear in both decks
    assert buf["Mountain\x001"] == 2
    assert buf["Mountain\x003"] == 2
    # Mountain#4 only in first deck
    assert buf["Mountain\x004"] == 1


def test_add_deck_to_karsten_buffer_sideboard(averager):
    buf = averager.add_deck_to_karsten_buffer({}, "1 Counterspell\n\n2 Duress")
    assert buf["Sideboard Duress\x001"] == 1
    assert buf["Sideboard Duress\x002"] == 1
    assert "Sideboard Duress\x003" not in buf


# ──────────────────────────── Karsten render ────────────────────────────────


def test_render_karsten_deck_basic(averager):
    buf: dict[str, int] = {}
    for _ in range(3):
        buf = averager.add_deck_to_karsten_buffer(buf, "4 Island\n2 Mountain")
    text = averager.render_karsten_deck(buf, main_size=6, side_size=15)
    lines = text.splitlines()
    assert "4 Island" in lines
    assert "2 Mountain" in lines


def test_render_karsten_deck_top_n_selection(averager):
    # Deck 1: 3 Forest; Deck 2: 3 Forest; Deck 3: 1 Forest
    buf: dict[str, int] = {}
    buf = averager.add_deck_to_karsten_buffer(buf, "3 Forest")
    buf = averager.add_deck_to_karsten_buffer(buf, "3 Forest")
    buf = averager.add_deck_to_karsten_buffer(buf, "1 Forest")
    # Forest#1: 3, Forest#2: 2, Forest#3: 2
    # Top-2 → Forest#1 (3) + Forest#2 (2) → "2 Forest"
    text = averager.render_karsten_deck(buf, main_size=2, side_size=0)
    assert text.strip() == "2 Forest"


def test_render_karsten_deck_empty(averager):
    assert averager.render_karsten_deck({}) == ""


def test_render_karsten_deck_sideboard_section(averager):
    buf = averager.add_deck_to_karsten_buffer({}, "2 Thoughtseize\n\n1 Disdainful Stroke")
    text = averager.render_karsten_deck(buf, main_size=60, side_size=15)
    lines = text.splitlines()
    assert "" in lines
    sep = lines.index("")
    main_part = lines[:sep]
    side_part = lines[sep + 1 :]
    assert any("Thoughtseize" in ln for ln in main_part)
    assert any("Disdainful Stroke" in ln for ln in side_part)


def test_render_karsten_deck_respects_main_size_cap(averager):
    # Build a deck with many different cards, check we cap at main_size
    cards = "\n".join(f"1 Card{i}" for i in range(10))
    buf = averager.add_deck_to_karsten_buffer({}, cards)
    text = averager.render_karsten_deck(buf, main_size=5, side_size=0)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) == 5


# ──────────────────────────── Arithmetic buffer & render ────────────────────


def test_add_deck_to_buffer_accumulates(averager):
    buf: dict[str, float] = {}
    buf = averager.add_deck_to_buffer(buf, "4 Lightning Bolt")
    buf = averager.add_deck_to_buffer(buf, "2 Lightning Bolt")
    assert buf["Lightning Bolt"] == 6.0


def test_render_average_deck_integer(averager):
    buf = {"Forest": 4.0}
    text = averager.render_average_deck(buf, 1)
    assert text.strip() == "4 Forest"


def test_render_average_deck_fractional(averager):
    buf = {"Plains": 3.0}
    text = averager.render_average_deck(buf, 2)
    assert "1.50 Plains" in text


def test_render_average_deck_empty(averager):
    assert averager.render_average_deck({}, 5) == ""
    assert averager.render_average_deck({"x": 1.0}, 0) == ""


def test_render_average_deck_sideboard_section(averager):
    # A "\n\n" separator marks the start of the sideboard; the parser keys
    # sideboard cards as "Sideboard {name}".
    buf = averager.add_deck_to_buffer({}, "4 Lightning Bolt\n\n2 Duress")
    text = averager.render_average_deck(buf, 1)
    lines = text.splitlines()

    # A blank-line separator splits mainboard from sideboard.
    assert "" in lines
    sep = lines.index("")
    main_part = lines[:sep]
    side_part = lines[sep + 1 :]

    # Mainboard card stays in the mainboard section.
    assert "4 Lightning Bolt" in main_part
    # Sideboard card lands after the separator with the "Sideboard " prefix stripped.
    assert "2 Duress" in side_part
    assert all("Sideboard" not in ln for ln in lines)


def test_render_average_deck_sorts_sideboard_last(averager):
    # Sideboard cards must sort after every mainboard card regardless of name.
    buf = averager.add_deck_to_buffer({}, "4 Zealous Conscripts\n\n2 Abrade")
    text = averager.render_average_deck(buf, 1)
    lines = text.splitlines()

    sep = lines.index("")
    assert lines[:sep] == ["4 Zealous Conscripts"]
    assert lines[sep + 1 :] == ["2 Abrade"]


# ──────────────────────────── filter_today_decks ────────────────────────────


def test_filter_today_decks_matches_and_excludes(averager):
    decks = [
        {"date": "2026-06-01", "name": "today"},
        {"date": "2026-05-31", "name": "yesterday"},
    ]
    result = averager.filter_today_decks(decks, today="2026-06-01")
    assert [deck["name"] for deck in result] == ["today"]


def test_filter_today_decks_case_insensitive_substring(averager):
    decks = [{"date": "Decks 2026-06-01 EVENT", "name": "match"}]
    result = averager.filter_today_decks(decks, today="2026-06-01")
    assert [deck["name"] for deck in result] == ["match"]


def test_filter_today_decks_missing_date_excluded(averager):
    decks = [
        {"name": "no-date-key"},
        {"date": None, "name": "none-date"},
        {"date": "2026-06-01", "name": "match"},
    ]
    result = averager.filter_today_decks(decks, today="2026-06-01")
    assert [deck["name"] for deck in result] == ["match"]


def test_filter_today_decks_defaults_to_current_date(averager):
    decks = [
        {"date": "today-fixed-date", "name": "match"},
        {"date": "some-other-date", "name": "no-match"},
    ]
    with patch.object(time, "strftime", return_value="today-fixed-date"):
        result = averager.filter_today_decks(decks)
    assert [deck["name"] for deck in result] == ["match"]
