"""Tests for printing-aware decklist parsing and conversion helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from loguru import logger

from services.deck_service import DeckService, printing
from services.deck_service.printing import (
    decklist_with_full_art_printings,
    decklist_with_newest_printings,
    decklist_with_newest_printings_by,
    decklist_with_oldest_printings,
    decklist_with_printings_after,
    decklist_with_printings_to_agnostic,
    format_decklist_on_load,
    parse_printed_decklist,
)


@pytest.fixture
def warnings():
    """Capture loguru WARNING messages (loguru does not feed pytest's caplog)."""
    messages: list[str] = []
    sink_id = logger.add(lambda msg: messages.append(str(msg)), level="WARNING")
    try:
        yield messages
    finally:
        logger.remove(sink_id)


# Printings are intentionally NOT sorted by date here so the helpers are forced
# to compute oldest/newest from ``released_at`` rather than list position.
INDEX = {
    "lightning bolt": [
        {"id": "bolt-2xm", "set": "2XM", "released_at": "2020-08-07", "full_art": True},
        {"id": "bolt-m10", "set": "M10", "released_at": "2009-07-17", "full_art": False},
        {"id": "bolt-lea", "set": "LEA", "released_at": "1993-08-05", "full_art": False},
    ],
    "island": [
        {"id": "isl-ust", "set": "UST", "released_at": "2017-12-08", "full_art": True},
        {"id": "isl-lea", "set": "LEA", "released_at": "1993-08-05", "full_art": False},
    ],
    "llanowar elves": [
        {"id": "elf-m19", "set": "M19", "released_at": "2018-07-13", "full_art": False},
        {"id": "elf-lea", "set": "LEA", "released_at": "1993-08-05", "full_art": False},
    ],
    "modern card": [
        {"id": "mod-2015", "set": "ORI", "released_at": "2015-07-17", "full_art": False},
    ],
}


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def test_parse_strips_pointers_and_accepts_nx():
    text = "4 Lightning Bolt bolt-lea\n2x Llanowar Elves M19\n3 Island"
    cards = parse_printed_decklist(text, INDEX)
    assert [(c.count, c.name, c.is_sideboard) for c in cards] == [
        (4.0, "Lightning Bolt", False),
        (2.0, "Llanowar Elves", False),
        (3.0, "Island", False),
    ]


def test_parse_skips_unknown_card_with_warning(warnings):
    text = "4 Lightning Bolt\n1 Totally Made Up Card"
    cards = parse_printed_decklist(text, INDEX)
    assert [c.name for c in cards] == ["Lightning Bolt"]
    assert "Totally Made Up Card" in "".join(warnings)


def test_parse_tracks_sideboard_zone():
    text = "4 Lightning Bolt\n\nSideboard\n2 Island"
    cards = parse_printed_decklist(text, INDEX)
    assert cards[0].is_sideboard is False
    assert cards[1].is_sideboard is True


# ---------------------------------------------------------------------------
# format_decklist_on_load: most-restrictive-format-that-fits
# ---------------------------------------------------------------------------


def test_load_keeps_printing_ids_when_all_valid():
    text = "4 Lightning Bolt bolt-lea\n2 Island isl-lea"
    assert format_decklist_on_load(text, INDEX) == "4 Lightning Bolt bolt-lea\n2 Island isl-lea"


def test_load_one_invalid_pointer_downgrades_whole_list_to_agnostic():
    # bolt has a valid printing id but island's pointer resolves to nothing, so
    # the *whole* decklist collapses to agnostic.
    text = "4 Lightning Bolt bolt-lea\n4 Island invalidpointer"
    assert format_decklist_on_load(text, INDEX) == "4 Lightning Bolt\n4 Island"


def test_load_mixed_id_and_edition_downgrades_to_edition():
    # bolt is a printing id, island is an edition -> render both at edition,
    # downgrading the printing id to its own set code (LEA).
    text = "4 Lightning Bolt bolt-lea\n2 Island UST"
    assert format_decklist_on_load(text, INDEX) == "4 Lightning Bolt LEA\n2 Island UST"


def test_load_keeps_editions_when_all_editions():
    text = "4 Lightning Bolt M10\n2 Island UST"
    assert format_decklist_on_load(text, INDEX) == "4 Lightning Bolt M10\n2 Island UST"


def test_load_preserves_sideboard_structure():
    text = "4 Lightning Bolt\n\nSideboard\n2 Island"
    assert format_decklist_on_load(text, INDEX) == "4 Lightning Bolt\n\nSideboard\n2 Island"


def test_load_drops_unknown_card_lines():
    text = "4 Lightning Bolt\n1 Bogus Card"
    assert format_decklist_on_load(text, INDEX) == "4 Lightning Bolt"


def test_load_empty_when_no_valid_cards():
    assert format_decklist_on_load("1 Bogus Card", INDEX) == ""


# ---------------------------------------------------------------------------
# oldest / newest / full-art
# ---------------------------------------------------------------------------


def test_oldest_printing_selected_by_date_not_position():
    assert decklist_with_oldest_printings("1 Lightning Bolt", INDEX) == "1 Lightning Bolt bolt-lea"


def test_newest_printing_selected_by_date_not_position():
    assert decklist_with_newest_printings("1 Lightning Bolt", INDEX) == "1 Lightning Bolt bolt-2xm"


def test_full_art_picks_newest_full_art_printing():
    assert decklist_with_full_art_printings("1 Island", INDEX) == "1 Island isl-ust"


def test_full_art_falls_back_to_agnostic_with_warning(warnings):
    result = decklist_with_full_art_printings("1 Llanowar Elves", INDEX)
    assert result == "1 Llanowar Elves"
    assert "full-art" in "".join(warnings)


def test_unknown_card_kept_agnostic_in_conversion(warnings):
    result = decklist_with_newest_printings("1 Bogus Card", INDEX)
    assert result == "1 Bogus Card"
    assert "Bogus Card" in "".join(warnings)


# ---------------------------------------------------------------------------
# newest-by(date)
# ---------------------------------------------------------------------------


def test_newest_by_date_picks_newest_on_or_before():
    assert (
        decklist_with_newest_printings_by("1 Lightning Bolt", INDEX, "2010-01-01")
        == "1 Lightning Bolt bolt-m10"
    )


def test_newest_by_accepts_date_object():
    assert (
        decklist_with_newest_printings_by("1 Lightning Bolt", INDEX, date(2010, 1, 1))
        == "1 Lightning Bolt bolt-m10"
    )


def test_newest_by_before_1993_returns_agnostic(warnings):
    result = decklist_with_newest_printings_by("1 Lightning Bolt", INDEX, "1992-01-01")
    assert result == "1 Lightning Bolt"
    assert "1993" in "".join(warnings)


def test_newest_by_invalid_date_returns_agnostic(warnings):
    result = decklist_with_newest_printings_by("1 Lightning Bolt", INDEX, "not-a-date")
    assert result == "1 Lightning Bolt"
    assert "Invalid date" in "".join(warnings)


def test_newest_by_returns_agnostic_when_any_card_has_no_printing_by_date(warnings):
    text = "1 Lightning Bolt\n1 Modern Card"
    result = decklist_with_newest_printings_by(text, INDEX, "2000-01-01")
    # Modern Card's earliest printing is 2015, so the whole list goes agnostic.
    assert result == "1 Lightning Bolt\n1 Modern Card"
    assert "Modern Card" in "".join(warnings)


# ---------------------------------------------------------------------------
# printings-after(date)
# ---------------------------------------------------------------------------


def test_printings_after_picks_oldest_strictly_after():
    assert (
        decklist_with_printings_after("1 Lightning Bolt", INDEX, "1995-01-01")
        == "1 Lightning Bolt bolt-m10"
    )


def test_printings_after_excludes_exact_date():
    # The 2009-07-17 printing is excluded; the next one after is 2020 (2XM).
    assert (
        decklist_with_printings_after("1 Lightning Bolt", INDEX, "2009-07-17")
        == "1 Lightning Bolt bolt-2xm"
    )


def test_printings_after_returns_agnostic_when_none_after(warnings):
    result = decklist_with_printings_after("1 Lightning Bolt", INDEX, "2025-01-01")
    assert result == "1 Lightning Bolt"
    assert "after" in "".join(warnings)


def test_printings_after_invalid_date_returns_agnostic(warnings):
    result = decklist_with_printings_after("1 Lightning Bolt", INDEX, "garbage")
    assert result == "1 Lightning Bolt"
    assert "Invalid date" in "".join(warnings)


# ---------------------------------------------------------------------------
# to-agnostic + misc
# ---------------------------------------------------------------------------


def test_to_agnostic_strips_pointers():
    text = "4 Lightning Bolt bolt-lea\n2 Island UST"
    assert decklist_with_printings_to_agnostic(text, INDEX) == "4 Lightning Bolt\n2 Island"


def test_fractional_counts_preserved():
    assert decklist_with_printings_to_agnostic("2.5 Lightning Bolt", INDEX) == "2.5 Lightning Bolt"


def test_sideboard_preserved_through_conversion():
    text = "4 Lightning Bolt\n\nSideboard\n2 Island"
    result = decklist_with_newest_printings(text, INDEX)
    assert result == "4 Lightning Bolt bolt-2xm\n\nSideboard\n2 Island isl-ust"


# ---------------------------------------------------------------------------
# DeckService delegation + real fixture shape
# ---------------------------------------------------------------------------


def test_deck_service_exposes_printing_helpers():
    service = DeckService(deck_repository=object(), metagame_repository=object())
    assert (
        service.decklist_with_newest_printings("1 Lightning Bolt", INDEX)
        == "1 Lightning Bolt bolt-2xm"
    )
    assert service.format_decklist_on_load("1 Bogus", INDEX) == ""


def test_helpers_work_against_real_fixture_index():
    fixture = Path(__file__).parent / "fixtures" / "card_art_selection" / "printings_index.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))["data"]
    name = next(iter(data))
    line = f"1 {name}"
    # Agnostic round-trips the name unchanged.
    assert decklist_with_printings_to_agnostic(line, data) == line
    # Newest selection appends a real printing id from the fixture.
    newest = decklist_with_newest_printings(line, data)
    ids = {p["id"] for p in data[name.lower()]}
    assert newest.split(" ")[-1] in ids


def test_module_all_is_importable():
    for symbol in printing.__all__:
        assert hasattr(printing, symbol)


# ---------------------------------------------------------------------------
# apply_printing_mode: the dropdown dispatcher
# ---------------------------------------------------------------------------


def test_apply_printing_mode_matches_underlying_helpers():
    text = "1 Lightning Bolt"
    assert printing.apply_printing_mode(text, INDEX, printing.MODE_AGNOSTIC) == text
    assert (
        printing.apply_printing_mode(text, INDEX, printing.MODE_OLDEST)
        == "1 Lightning Bolt bolt-lea"
    )
    assert (
        printing.apply_printing_mode(text, INDEX, printing.MODE_NEWEST)
        == "1 Lightning Bolt bolt-2xm"
    )
    assert (
        printing.apply_printing_mode("1 Island", INDEX, printing.MODE_FULL_ART)
        == "1 Island isl-ust"
    )


def test_apply_printing_mode_date_modes_use_when():
    assert (
        printing.apply_printing_mode(
            "1 Lightning Bolt", INDEX, printing.MODE_NEWEST_BY, "2010-01-01"
        )
        == "1 Lightning Bolt bolt-m10"
    )
    assert (
        printing.apply_printing_mode("1 Lightning Bolt", INDEX, printing.MODE_AFTER, "1995-01-01")
        == "1 Lightning Bolt bolt-m10"
    )


def test_apply_printing_mode_rejects_unknown_mode():
    with pytest.raises(ValueError):
        printing.apply_printing_mode("1 Island", INDEX, "nonsense")


def test_apply_printing_mode_exposed_on_deck_service():
    service = DeckService(deck_repository=object(), metagame_repository=object())
    assert (
        service.apply_printing_mode("1 Lightning Bolt", INDEX, printing.MODE_NEWEST)
        == "1 Lightning Bolt bolt-2xm"
    )


def test_all_printing_modes_are_dispatchable():
    # Every advertised mode must dispatch without raising (date modes need a date).
    for mode in printing.PRINTING_MODES:
        when = "2010-01-01" if mode in printing.DATE_MODES else None
        result = printing.apply_printing_mode("1 Lightning Bolt", INDEX, mode, when)
        assert result.startswith("1 Lightning Bolt")
