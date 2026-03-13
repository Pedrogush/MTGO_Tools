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


# ============= Name Match Mode Tests =============


def _make_builder_filters(**kwargs) -> dict:
    """Create a minimal builder filters dict with defaults."""
    defaults = {
        "name": "",
        "name_match": "contains",
        "type": "",
        "text": "",
        "mana": "",
        "mana_exact": False,
        "mv_comparator": "Any",
        "mv_value": "",
        "formats": [],
        "color_mode": "Any",
        "selected_colors": [],
        "radar_enabled": False,
        "radar_cards": set(),
    }
    defaults.update(kwargs)
    return defaults


def _make_card_manager_mock(cards: list[dict]) -> Mock:
    manager = Mock()
    manager.search_cards = Mock(return_value=cards)
    return manager


def test_name_match_contains_finds_substring():
    """Default 'contains' mode matches the whole query as a substring."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Clock of Omens"),
        create_mock_card(name="Lightning Bolt"),
    ]
    manager = _make_card_manager_mock(cards)
    for c in cards:
        c["name_lower"] = c["name"].lower()

    filters = _make_builder_filters(name="clock of omens")
    results = service.search_with_builder_filters(filters, manager)
    assert len(results) == 1
    assert results[0]["name"] == "Clock of Omens"


def test_name_match_contains_rejects_non_substring():
    """Default 'contains' mode rejects queries that aren't exact substrings."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [create_mock_card(name="Clock of Omens")]
    manager = _make_card_manager_mock(cards)
    for c in cards:
        c["name_lower"] = c["name"].lower()

    # "clock omens" skips "of", so it's not a substring of "clock of omens"
    filters = _make_builder_filters(name="clock omens")
    results = service.search_with_builder_filters(filters, manager)
    assert results == []


def test_name_match_any_word_finds_card_by_partial_name():
    """'any_word' mode finds 'Clock of Omens' when any typed word appears in the name."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Clock of Omens"),
        create_mock_card(name="Lightning Bolt"),
    ]
    manager = _make_card_manager_mock(cards)
    for c in cards:
        c["name_lower"] = c["name"].lower()

    # "clock omens" — both words appear in "clock of omens"
    filters = _make_builder_filters(name="clock omens", name_match="any_word")
    results = service.search_with_builder_filters(filters, manager)
    assert any(r["name"] == "Clock of Omens" for r in results)


def test_name_match_any_word_or_logic():
    """'any_word' mode returns cards matching ANY of the typed words."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [
        create_mock_card(name="Clock of Omens"),
        create_mock_card(name="Lightning Bolt"),
        create_mock_card(name="Island"),
    ]
    manager = _make_card_manager_mock(cards)
    for c in cards:
        c["name_lower"] = c["name"].lower()

    # "clock lightning" matches both Clock of Omens and Lightning Bolt
    filters = _make_builder_filters(name="clock lightning", name_match="any_word")
    results = service.search_with_builder_filters(filters, manager)
    names = {r["name"] for r in results}
    assert "Clock of Omens" in names
    assert "Lightning Bolt" in names
    assert "Island" not in names


def test_name_match_any_word_case_insensitive():
    """'any_word' mode is case-insensitive."""
    mock_repo = SimpleNamespace()
    service = SearchService(card_repository=mock_repo)

    cards = [create_mock_card(name="Clock of Omens")]
    manager = _make_card_manager_mock(cards)
    for c in cards:
        c["name_lower"] = c["name"].lower()

    filters = _make_builder_filters(name="CLOCK", name_match="any_word")
    results = service.search_with_builder_filters(filters, manager)
    assert len(results) == 1


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
