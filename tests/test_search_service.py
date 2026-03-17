"""Tests for SearchService business logic."""

from types import SimpleNamespace
from unittest.mock import Mock

from services.search_service import SearchService


def create_mock_card(
    name="Test Card",
    colors=None,
    type_line="Creature",
    mana_cost="{2}{G}",
    mana_value=3,
    oracle_text="Draw a card.",
):
    """Helper to create mock card data."""
    return {
        "name": name,
        "name_lower": name.lower(),
        "colors": colors or [],
        "color_identity": colors or [],
        "type_line": type_line,
        "mana_cost": mana_cost,
        "mana_value": mana_value,
        "cmc": mana_value,
        "oracle_text": oracle_text,
        "legalities": {},
    }


def test_search_cards_by_name_empty_query():
    """Test searching with empty query returns empty list."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    results = service.search_cards_by_name("")

    assert results == []


def test_search_cards_by_name_data_not_loaded():
    """Test searching when card data is not loaded."""
    mock_repo = SimpleNamespace()
    mock_repo.is_card_data_loaded = Mock(return_value=False)
    service = SearchService(card_repository=mock_repo)

    results = service.search_cards_by_name("Lightning Bolt")

    assert results == []


def test_search_cards_by_name_with_limit():
    """Test searching with limit."""
    mock_repo = SimpleNamespace()
    mock_repo.is_card_data_loaded = Mock(return_value=True)
    mock_repo.search_cards = Mock(
        return_value=[
            {"name": "Card 1"},
            {"name": "Card 2"},
            {"name": "Card 3"},
            {"name": "Card 4"},
            {"name": "Card 5"},
        ]
    )
    service = SearchService(card_repository=mock_repo)

    results = service.search_cards_by_name("Card", limit=3)

    assert len(results) == 3


# ============= Filter Tests =============


def test_filter_cards_by_colors_at_least():
    """Test filtering cards by colors with 'At least' mode."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Green Card", colors=["G"]),
        create_mock_card(name="Blue Green Card", colors=["U", "G"]),
        create_mock_card(name="Blue Card", colors=["U"]),
    ]

    filtered = service.filter_cards(cards, colors=["G"], color_mode="At least")

    assert len(filtered) == 2
    assert filtered[0]["name"] == "Green Card"
    assert filtered[1]["name"] == "Blue Green Card"


def test_filter_cards_by_colors_exactly():
    """Test filtering cards by colors with 'Exactly' mode."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Green Card", colors=["G"]),
        create_mock_card(name="Blue Green Card", colors=["U", "G"]),
        create_mock_card(name="Blue Card", colors=["U"]),
    ]

    filtered = service.filter_cards(cards, colors=["G"], color_mode="Exactly")

    assert len(filtered) == 1
    assert filtered[0]["name"] == "Green Card"


def test_filter_cards_by_colors_not_these():
    """Test filtering cards by colors with 'Not these' mode."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Green Card", colors=["G"]),
        create_mock_card(name="Blue Card", colors=["U"]),
        create_mock_card(name="Red Card", colors=["R"]),
    ]

    filtered = service.filter_cards(cards, colors=["G"], color_mode="Not these")

    assert len(filtered) == 2
    assert filtered[0]["name"] == "Blue Card"
    assert filtered[1]["name"] == "Red Card"


def test_filter_cards_by_type():
    """Test filtering cards by type."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Creature Card", type_line="Creature — Human"),
        create_mock_card(name="Instant Card", type_line="Instant"),
        create_mock_card(name="Sorcery Card", type_line="Sorcery"),
    ]

    filtered = service.filter_cards(cards, types=["Creature"])

    assert len(filtered) == 1
    assert filtered[0]["name"] == "Creature Card"


def test_filter_cards_by_multiple_types():
    """Test filtering cards by multiple types."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Creature Card", type_line="Creature — Human"),
        create_mock_card(name="Instant Card", type_line="Instant"),
        create_mock_card(name="Sorcery Card", type_line="Sorcery"),
    ]

    filtered = service.filter_cards(cards, types=["Instant", "Sorcery"])

    assert len(filtered) == 2


def test_filter_cards_by_mana_value():
    """Test filtering cards by mana value."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Cheap Card", mana_value=1),
        create_mock_card(name="Medium Card", mana_value=3),
        create_mock_card(name="Expensive Card", mana_value=6),
    ]

    filtered = service.filter_cards(cards, mana_value=3, mana_value_comparator="≤")

    assert len(filtered) == 2
    assert filtered[0]["name"] == "Cheap Card"
    assert filtered[1]["name"] == "Medium Card"


def test_filter_cards_by_text_contains():
    """Test filtering cards by text content."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Draw Card", oracle_text="Draw a card."),
        create_mock_card(name="Damage Card", oracle_text="Deal 3 damage."),
        create_mock_card(name="Exile Card", oracle_text="Exile target creature."),
    ]

    filtered = service.filter_cards(cards, text_contains="draw")

    assert len(filtered) == 1
    assert filtered[0]["name"] == "Draw Card"


def test_filter_cards_multiple_criteria():
    """Test filtering cards with multiple criteria."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(
            name="Green Creature",
            colors=["G"],
            type_line="Creature — Elf",
            mana_value=2,
            oracle_text="Draw a card.",
        ),
        create_mock_card(
            name="Blue Instant",
            colors=["U"],
            type_line="Instant",
            mana_value=2,
            oracle_text="Draw two cards.",
        ),
        create_mock_card(
            name="Red Sorcery",
            colors=["R"],
            type_line="Sorcery",
            mana_value=3,
            oracle_text="Deal damage.",
        ),
    ]

    filtered = service.filter_cards(
        cards,
        types=["Creature", "Instant"],
        mana_value=2,
        mana_value_comparator="=",
        text_contains="draw",
    )

    assert len(filtered) == 2


# ============= Suggestion Tests =============


def test_get_card_suggestions_short_query():
    """Test that short queries return no suggestions."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    suggestions = service.get_card_suggestions("L")

    assert suggestions == []


def test_get_card_suggestions_success():
    """Test getting card suggestions."""
    mock_repo = SimpleNamespace()
    mock_repo.is_card_data_loaded = Mock(return_value=True)
    mock_repo.search_cards = Mock(
        return_value=[
            {"name": "Lightning Bolt"},
            {"name": "Lightning Strike"},
            {"name": "Lightning Helix"},
        ]
    )
    service = SearchService(card_repository=mock_repo)

    suggestions = service.get_card_suggestions("Light")

    assert len(suggestions) == 3
    assert "Lightning Bolt" in suggestions


# ============= Deck Search Tests =============


def test_find_cards_in_deck():
    """Test finding cards in deck by search term."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    deck_text = """4 Lightning Bolt
4 Lightning Strike
20 Island
4 Counterspell"""

    results = service.find_cards_in_deck(deck_text, "Lightning")

    assert len(results) == 2
    assert ("Lightning Bolt", 4) in results
    assert ("Lightning Strike", 4) in results


def test_find_cards_in_deck_case_insensitive():
    """Test that deck search is case insensitive."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    deck_text = """4 Lightning Bolt
4 Island"""

    results = service.find_cards_in_deck(deck_text, "LIGHTNING")

    assert len(results) == 1
    assert results[0] == ("Lightning Bolt", 4)


def test_find_cards_in_deck_no_matches():
    """Test finding cards when there are no matches."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    deck_text = """4 Island
4 Mountain"""

    results = service.find_cards_in_deck(deck_text, "Lightning")

    assert len(results) == 0


# ============= Grouping Tests =============


def test_group_cards_by_type():
    """Test grouping cards by type."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Creature 1", type_line="Creature — Human"),
        create_mock_card(name="Creature 2", type_line="Creature — Elf"),
        create_mock_card(name="Instant 1", type_line="Instant"),
        create_mock_card(name="Land 1", type_line="Land — Island"),
        create_mock_card(name="Enchantment 1", type_line="Enchantment"),
    ]

    grouped = service.group_cards_by_type(cards)

    assert len(grouped["Creature"]) == 2
    assert len(grouped["Instant"]) == 1
    assert len(grouped["Land"]) == 1
    assert len(grouped["Enchantment"]) == 1


def test_group_cards_by_type_multi_type():
    """Test grouping cards with multiple types."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Artifact Creature", type_line="Artifact Creature — Golem"),
    ]

    grouped = service.group_cards_by_type(cards)

    # Should be assigned to first matching category (Creature)
    assert "Artifact Creature" in [c["name"] for c in grouped.get("Creature", [])]


def test_group_cards_by_type_unknown():
    """Test grouping cards with unknown types."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Weird Card", type_line="Scheme"),
    ]

    grouped = service.group_cards_by_type(cards)

    assert "Weird Card" in [c["name"] for c in grouped.get("Other", [])]


# ============= Oracle Text Mode Tests =============


def test_matches_text_filter_all_mode_phrase_match():
    """'all' mode matches when the full phrase is present."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)
    card = create_mock_card(oracle_text="Draw a card. Then discard a card.")
    assert service._matches_text_filter(card, "draw a card", "all")


def test_matches_text_filter_all_mode_phrase_no_match():
    """'all' mode does not match when only some words are present."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)
    card = create_mock_card(oracle_text="Destroy target artifact.")
    assert not service._matches_text_filter(card, "draw card", "all")


def test_matches_text_filter_any_mode_all_words_present():
    """'any' mode matches when all query words appear in the text (any order)."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)
    card = create_mock_card(oracle_text="Tap two untapped artifacts you control.")
    assert service._matches_text_filter(card, "tap untapped", "any")


def test_matches_text_filter_any_mode_partial_words_no_match():
    """'any' mode returns False when not all query words are present."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)
    card = create_mock_card(oracle_text="Tap target creature.")
    assert not service._matches_text_filter(card, "tap untapped", "any")


def test_matches_text_filter_any_mode_no_match():
    """'any' mode returns False when no query words match."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)
    card = create_mock_card(oracle_text="Destroy target artifact.")
    assert not service._matches_text_filter(card, "tap untapped", "any")


def test_filter_cards_text_mode_any():
    """filter_cards 'any' mode requires all words present, not just one."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)
    cards = [
        create_mock_card(name="Both Words", oracle_text="Tap two untapped artifacts."),
        create_mock_card(name="Only Tap", oracle_text="Tap target creature."),
        create_mock_card(name="Neither", oracle_text="Destroy target creature."),
    ]
    results = service.filter_cards(cards, text_contains="tap untapped", text_mode="any")
    names = [c["name"] for c in results]
    assert "Both Words" in names
    assert "Only Tap" not in names
    assert "Neither" not in names


def test_search_with_builder_filters_text_mode_any():
    """search_with_builder_filters 'any' mode requires all words to appear."""
    from utils.card_data import CardDataManager

    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    clock = create_mock_card(
        name="Clock of Omens",
        oracle_text="Tap two untapped artifacts you control: Untap target artifact.",
    )
    tap_only = create_mock_card(name="Tap Card", oracle_text="Tap target creature.")
    other_card = create_mock_card(name="Other Card", oracle_text="Destroy target creature.")

    mock_manager = Mock(spec=CardDataManager)
    mock_manager.search_cards.return_value = [clock, tap_only, other_card]

    filters = {"text": "tap untapped", "text_mode": "any"}
    results = service.search_with_builder_filters(filters, mock_manager)
    names = [c["name"] for c in results]
    assert "Clock of Omens" in names
    assert "Tap Card" not in names
    assert "Other Card" not in names


def test_group_cards_by_type_removes_empty_groups():
    """Test that empty groups are removed."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Creature 1", type_line="Creature — Human"),
    ]

    grouped = service.group_cards_by_type(cards)

    assert "Creature" in grouped
    assert "Instant" not in grouped
    assert "Sorcery" not in grouped


# ============= Private Method Tests =============


def test_matches_color_filter():
    """Test color filter matching."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    card = create_mock_card(colors=["G", "U"])

    assert service._matches_color_filter(card, ["G"], "At least") is True
    assert service._matches_color_filter(card, ["R"], "At least") is False
    assert service._matches_color_filter(card, ["G", "U"], "Exactly") is True


def test_matches_type_filter():
    """Test type filter matching."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    card = create_mock_card(type_line="Creature — Human Wizard")

    assert service._matches_type_filter(card, ["Creature"]) is True
    assert service._matches_type_filter(card, ["Human"]) is True
    assert service._matches_type_filter(card, ["Instant"]) is False


def test_matches_mana_value_filter():
    """Test mana value filter matching."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    card = create_mock_card(mana_value=3)

    assert service._matches_mana_value_filter(card, 3, "=") is True
    assert service._matches_mana_value_filter(card, 3, "≤") is True
    assert service._matches_mana_value_filter(card, 2, ">") is True
    assert service._matches_mana_value_filter(card, 5, "<") is True
    assert service._matches_mana_value_filter(card, 2, "=") is False


def test_matches_text_filter():
    """Test text filter matching."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    card = create_mock_card(oracle_text="Draw a card, then discard a card.")

    assert service._matches_text_filter(card, "draw") is True
    assert service._matches_text_filter(card, "DRAW") is True
    assert service._matches_text_filter(card, "discard") is True
    assert service._matches_text_filter(card, "destroy") is False


def test_matches_text_filter_no_text():
    """Test text filter with card that has no text."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    card = create_mock_card(oracle_text="")

    assert service._matches_text_filter(card, "anything") is False


# ============= Land Colorless Tests =============


def create_mock_land(name="Forest", color_identity=None, type_line="Basic Land — Forest"):
    """Helper to create a mock land card."""
    return {
        "name": name,
        "name_lower": name.lower(),
        "colors": [],
        "color_identity": color_identity or ["G"],
        "type_line": type_line,
        "mana_cost": "",
        "mana_value": 0,
        "cmc": 0,
        "oracle_text": "",
        "legalities": {},
    }


def test_lands_treated_as_colorless_in_color_filter():
    """Lands should be treated as colorless regardless of color_identity."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    forest = create_mock_land(name="Forest", color_identity=["G"])

    # Forest should NOT match a green color filter
    assert service._matches_color_filter(forest, ["G"], "At least") is False
    assert service._matches_color_filter(forest, ["G"], "Exactly") is False

    # Forest SHOULD match a colorless filter
    assert service._matches_color_filter(forest, ["C"], "At least") is True
    assert service._matches_color_filter(forest, ["C"], "Exactly") is True

    # Forest should pass "Not these" for any color (it's colorless)
    assert service._matches_color_filter(forest, ["G", "U", "R"], "Not these") is True


def test_filter_cards_lands_excluded_from_color_filter():
    """Lands should not appear in color-filtered results for non-colorless colors."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Llanowar Elves", colors=["G"], type_line="Creature — Elf Druid"),
        create_mock_land(name="Forest", color_identity=["G"]),
        create_mock_land(
            name="Breeding Pool", color_identity=["G", "U"], type_line="Land — Forest Island"
        ),
    ]

    # Filtering for green should only return the creature, not lands
    filtered = service.filter_cards(cards, colors=["G"], color_mode="At least")

    assert len(filtered) == 1
    assert filtered[0]["name"] == "Llanowar Elves"


def test_filter_cards_lands_appear_in_colorless_filter():
    """Lands should appear when filtering for colorless."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Llanowar Elves", colors=["G"], type_line="Creature — Elf Druid"),
        create_mock_land(name="Forest", color_identity=["G"]),
    ]

    filtered = service.filter_cards(cards, colors=["C"], color_mode="At least")

    assert len(filtered) == 1
    assert filtered[0]["name"] == "Forest"
