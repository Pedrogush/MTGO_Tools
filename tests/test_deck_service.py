from types import SimpleNamespace

import pytest

from services.deck_service import DeckService


@pytest.fixture
def deck_service():
    """DeckService that uses dummy repositories to avoid external dependencies."""
    return DeckService(deck_repository=SimpleNamespace(), metagame_repository=SimpleNamespace())


def test_deck_to_dictionary_preserves_fractional_counts(deck_service):
    deck_text = "2 Island\n" "0.5 Consider\n" "\n" "Sideboard\n" "1.25 Dismember\n"

    deck_dict = deck_service.deck_to_dictionary(deck_text)

    assert deck_dict["Island"] == 2.0
    assert deck_dict["Consider"] == pytest.approx(0.5)
    assert deck_dict["Sideboard Dismember"] == pytest.approx(1.25)


def test_deck_to_dictionary_handles_empty_lines(deck_service):
    deck_text = "1 Mountain\n\nSideboard\n2 Lightning Bolt\n\n"

    deck_dict = deck_service.deck_to_dictionary(deck_text)

    assert deck_dict["Mountain"] == 1.0
    assert deck_dict["Sideboard Lightning Bolt"] == 2.0


def test_deck_to_dictionary_skips_count_only_lines(deck_service):
    """A line with a count but no card name yields no entry."""
    # "4" has no name after the count; "5 " strips to "5" (same boundary).
    deck_text = "4\n5 \n2 Island\n"

    deck_dict = deck_service.deck_to_dictionary(deck_text)

    assert deck_dict == {"Island": 2.0}


def test_analyze_deck_skips_count_only_lines(deck_service):
    """analyze_deck drops count-only lines instead of creating empty-name entries."""
    deck_text = "4\n2 Island\n\nSideboard\n3\n1 Abrade\n"

    stats = deck_service.analyze_deck(deck_text)

    mainboard_dict = dict(stats["mainboard_cards"])
    sideboard_dict = dict(stats["sideboard_cards"])
    assert mainboard_dict == {"Island": 2}
    assert sideboard_dict == {"Abrade": 1}
    # No empty-name entry leaked into either zone.
    assert "" not in mainboard_dict
    assert "" not in sideboard_dict
    assert stats["unique_mainboard"] == 1
    assert stats["unique_sideboard"] == 1


def test_analyze_deck_blank_line_switches_to_sideboard_without_header(deck_service):
    """A blank line alone (no 'Sideboard' header) flips subsequent cards to the sideboard."""
    deck_text = "2 Island\n\n1 Abrade"

    stats = deck_service.analyze_deck(deck_text)

    assert dict(stats["mainboard_cards"]) == {"Island": 2}
    assert dict(stats["sideboard_cards"]) == {"Abrade": 1}


def test_leading_blank_line_diverges_between_to_dictionary_and_analyze(deck_service):
    """strip_input makes the two entry points treat a leading blank line differently.

    analyze_deck strips the input first, so the leading blank vanishes and every
    card stays in the mainboard. deck_to_dictionary keeps the raw input, so the
    leading blank is a (non-trailing) zone flip and every card lands in the
    sideboard.
    """
    deck_text = "\n2 Island\n1 Abrade"

    deck_dict = deck_service.deck_to_dictionary(deck_text)
    assert deck_dict == {"Sideboard Island": 2.0, "Sideboard Abrade": 1.0}

    stats = deck_service.analyze_deck(deck_text)
    assert dict(stats["mainboard_cards"]) == {"Island": 2, "Abrade": 1}
    assert stats["sideboard_cards"] == []


def test_analyze_deck_preserves_fractional_quantities(deck_service):
    """Test that analyze_deck preserves fractional quantities from average decks."""
    deck_text = (
        "4 Island\n"
        "2.5 Lightning Bolt\n"
        "1.33 Consider\n"
        "\n"
        "Sideboard\n"
        "3 Counterspell\n"
        "1.67 Dismember\n"
    )

    stats = deck_service.analyze_deck(deck_text)

    # Check mainboard cards preserve fractional quantities
    mainboard_dict = dict(stats["mainboard_cards"])
    assert mainboard_dict["Island"] == 4
    assert mainboard_dict["Lightning Bolt"] == 2.5
    assert mainboard_dict["Consider"] == pytest.approx(1.33)

    # Check sideboard cards preserve fractional quantities
    sideboard_dict = dict(stats["sideboard_cards"])
    assert sideboard_dict["Counterspell"] == 3
    assert sideboard_dict["Dismember"] == pytest.approx(1.67)

    # Check total counts
    assert stats["mainboard_count"] == pytest.approx(7.83)
    assert stats["sideboard_count"] == pytest.approx(4.67)
    assert stats["total_cards"] == pytest.approx(12.5)


def test_analyze_deck_merges_duplicate_entries(deck_service):
    deck_text = (
        "2 Lightning Bolt\n"
        "1 Lightning Bolt\n"
        "3 Island\n"
        "\n"
        "Sideboard\n"
        "1 Abrade\n"
        "2 Abrade\n"
    )

    stats = deck_service.analyze_deck(deck_text)

    mainboard_dict = dict(stats["mainboard_cards"])
    assert mainboard_dict["Lightning Bolt"] == 3
    assert mainboard_dict["Island"] == 3
    assert stats["unique_mainboard"] == 2

    sideboard_dict = dict(stats["sideboard_cards"])
    assert sideboard_dict["Abrade"] == 3
    assert stats["unique_sideboard"] == 1
    assert stats["total_cards"] == 9


def test_analyze_deck_estimates_lands_from_mainboard(deck_service):
    """estimated_lands sums mainboard cards whose name matches a land keyword."""
    deck_text = "4 Island\n" "3 Mountain\n" "4 Lightning Bolt\n" "\n" "Sideboard\n" "2 Swamp\n"

    stats = deck_service.analyze_deck(deck_text)

    # Only mainboard lands count; the sideboard Swamp is excluded.
    assert stats["estimated_lands"] == 7


def test_analyze_deck_counts_multi_keyword_land_once(deck_service):
    """A card matching several land keywords is counted once, not per keyword."""
    # "Island" matches both the "island" and "land" keywords.
    deck_text = "4 Island\n"

    stats = deck_service.analyze_deck(deck_text)

    assert stats["estimated_lands"] == 4


def test_analyze_deck_skips_malformed_lines(deck_service):
    """Lines without a numeric count or a card name are skipped, not errors."""
    deck_text = "Deck\n" "Burn\n" "x Lightning Bolt\n" "2 Island\n" "1.5 Consider\n"

    stats = deck_service.analyze_deck(deck_text)

    mainboard_dict = dict(stats["mainboard_cards"])
    # The valid lines are parsed; malformed ones are dropped.
    assert ("Island", 2) in stats["mainboard_cards"]
    assert ("Consider", pytest.approx(1.5)) in stats["mainboard_cards"]
    # "Burn", "x Lightning Bolt", and "Deck" produce no entries.
    assert "Burn" not in mainboard_dict
    assert "Lightning Bolt" not in mainboard_dict
    assert "Deck" not in mainboard_dict
    assert stats["unique_mainboard"] == 2


def test_build_card_list_narrows_integers_to_int(deck_service):
    """Whole-number totals are returned as int, fractional totals stay float."""
    deck_text = "4 Island\n2.5 Lightning Bolt\n"

    stats = deck_service.analyze_deck(deck_text)
    mainboard_dict = dict(stats["mainboard_cards"])

    assert isinstance(mainboard_dict["Island"], int)
    assert isinstance(mainboard_dict["Lightning Bolt"], float)


def test_analyze_deck_strips_trailing_printing_id_pointer(deck_service):
    """A decklist carrying per-card printing ids (issue #792) parses by name.

    The printing-selection helpers render lines as ``N NAME <scryfall-uuid>``;
    name-based analysis must drop that trailing id rather than fold it into the
    card name.
    """
    uuid_a = "e3285e6b-3e79-4d7c-bf96-d920f973b122"
    uuid_b = "a1b2c3d4-5e6f-4a8b-9c0d-1e2f3a4b5c6d"
    deck_text = f"4 Lightning Bolt {uuid_a}\n2 Island {uuid_b}\n"

    stats = deck_service.analyze_deck(deck_text)
    mainboard_dict = dict(stats["mainboard_cards"])

    assert mainboard_dict == {"Lightning Bolt": 4, "Island": 2}


def test_analyze_deck_keeps_names_that_merely_look_pointer_ish(deck_service):
    """Only a real Scryfall-shaped uuid is stripped; ordinary names are intact."""
    deck_text = "1 Look at Me, I'm the DCI\n3 R&D's Secret Lair\n"

    stats = deck_service.analyze_deck(deck_text)
    mainboard_dict = dict(stats["mainboard_cards"])

    assert mainboard_dict == {"Look at Me, I'm the DCI": 1, "R&D's Secret Lair": 3}


def test_analyze_deck_strips_uppercase_printing_id_but_not_mid_string(deck_service):
    """The printing-id suffix match is case-insensitive and anchored to the end.

    An upper-case uuid trailing the name is stripped; a uuid embedded mid-name
    (with text after it) is left untouched, so it stays part of the card name.
    """
    deck_text = (
        "1 Foo E3285E6B-3E79-4D7C-BF96-D920F973B122\n"
        "2 Foo e3285e6b-3e79-4d7c-bf96-d920f973b122 Bar\n"
    )

    stats = deck_service.analyze_deck(deck_text)
    mainboard_dict = dict(stats["mainboard_cards"])

    assert mainboard_dict == {
        "Foo": 1,
        "Foo e3285e6b-3e79-4d7c-bf96-d920f973b122 Bar": 2,
    }


def test_build_card_list_narrows_summed_fractions_to_int(deck_service):
    """Fractional counts that sum to a whole number are narrowed to int."""
    deck_text = "0.5 Bolt\n0.5 Bolt\n"

    stats = deck_service.analyze_deck(deck_text)

    assert stats["mainboard_cards"] == [("Bolt", 1)]
    assert isinstance(stats["mainboard_cards"][0][1], int)
