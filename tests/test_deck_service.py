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
