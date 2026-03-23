"""Tests for search filter utility functions."""

from utils.search_filters import matches_color_filter, matches_mana_cost, matches_mana_value

# ============= Mana Cost Tests =============


def test_matches_mana_cost_exact_match():
    """Test exact mana cost matching."""
    card_cost = "{2}{G}{G}"
    query = "{2}{G}{G}"

    assert matches_mana_cost(card_cost, query, "exact") is True


def test_matches_mana_cost_exact_different_order():
    """Test exact matching with different symbol order."""
    card_cost = "{G}{G}{2}"
    query = "{2}{G}{G}"

    # Order doesn't matter for exact matching
    assert matches_mana_cost(card_cost, query, "exact") is True


def test_matches_mana_cost_exact_different():
    """Test exact matching with different costs."""
    card_cost = "{2}{G}{G}"
    query = "{3}{G}"

    assert matches_mana_cost(card_cost, query, "exact") is False


def test_matches_mana_cost_contains_mode():
    """Test 'at least' (contains) mode."""
    card_cost = "{2}{G}{G}{U}"
    query = "{G}{G}"

    # Card has at least 2 green, so should match
    assert matches_mana_cost(card_cost, query, "contains") is True


def test_matches_mana_cost_contains_insufficient():
    """Test 'at least' mode when card has insufficient symbols."""
    card_cost = "{2}{G}"
    query = "{G}{G}"

    # Card has only 1 green but query needs 2
    assert matches_mana_cost(card_cost, query, "contains") is False


def test_matches_mana_cost_empty_query():
    """Test that empty query matches any card."""
    card_cost = "{2}{G}{G}"
    query = ""

    assert matches_mana_cost(card_cost, query, "exact") is True
    assert matches_mana_cost(card_cost, query, "contains") is True


def test_matches_mana_cost_hybrid_mana():
    """Test matching with hybrid mana symbols."""
    card_cost = "{G/U}{G/U}"
    query = "{G/U}{G/U}"

    assert matches_mana_cost(card_cost, query, "exact") is True


def test_matches_mana_cost_phyrexian_mana():
    """Test matching with Phyrexian mana symbols."""
    card_cost = "{G/P}{G/P}"
    query = "{G/P}{G/P}"

    assert matches_mana_cost(card_cost, query, "exact") is True


def test_matches_mana_cost_colorless():
    """Test matching colorless mana costs."""
    card_cost = "{3}"
    query = "{3}"

    assert matches_mana_cost(card_cost, query, "exact") is True


def test_matches_mana_cost_zero_cost():
    """Test matching zero mana cost cards."""
    card_cost = ""
    query = ""

    assert matches_mana_cost(card_cost, query, "exact") is True


# ============= Mana Value Tests =============


def test_matches_mana_value_equals():
    """Test mana value equality comparison."""
    assert matches_mana_value(3, 3, "=") is True
    assert matches_mana_value(3, 2, "=") is False
    assert matches_mana_value(3.5, 3.5, "=") is True


def test_matches_mana_value_less_than():
    """Test mana value less than comparison."""
    assert matches_mana_value(2, 3, "<") is True
    assert matches_mana_value(3, 3, "<") is False
    assert matches_mana_value(4, 3, "<") is False


def test_matches_mana_value_less_than_or_equal():
    """Test mana value less than or equal comparison."""
    assert matches_mana_value(2, 3, "≤") is True
    assert matches_mana_value(3, 3, "≤") is True
    assert matches_mana_value(4, 3, "≤") is False


def test_matches_mana_value_greater_than():
    """Test mana value greater than comparison."""
    assert matches_mana_value(4, 3, ">") is True
    assert matches_mana_value(3, 3, ">") is False
    assert matches_mana_value(2, 3, ">") is False


def test_matches_mana_value_greater_than_or_equal():
    """Test mana value greater than or equal comparison."""
    assert matches_mana_value(4, 3, "≥") is True
    assert matches_mana_value(3, 3, "≥") is True
    assert matches_mana_value(2, 3, "≥") is False


def test_matches_mana_value_invalid_value():
    """Test mana value comparison with invalid card value."""
    assert matches_mana_value(None, 3, "=") is False
    assert matches_mana_value("invalid", 3, "=") is False


def test_matches_mana_value_string_convertible():
    """Test mana value comparison with string that can be converted."""
    assert matches_mana_value("3", 3, "=") is True
    assert matches_mana_value("3.5", 3.5, "=") is True


def test_matches_mana_value_unknown_comparator():
    """Test mana value with unknown comparator defaults to True."""
    assert matches_mana_value(3, 5, "unknown") is True


def test_matches_mana_value_fractional():
    """Test mana value comparison with fractional values."""
    assert matches_mana_value(2.5, 3, "<") is True
    assert matches_mana_value(3.5, 3, ">") is True


# ============= Color Filter Tests =============


def test_matches_color_filter_any_mode():
    """Test color filter with '-' mode (no filtering)."""
    assert matches_color_filter(["G"], ["R", "U"], "-") is True
    assert matches_color_filter([], ["W"], "-") is True


def test_matches_color_filter_empty_selected():
    """Test color filter with no selected colors."""
    assert matches_color_filter(["G", "U"], [], "≥") is True
    assert matches_color_filter(["G", "U"], [], "=") is True


def test_matches_color_filter_at_least_single():
    """Test '≥' (at least) mode with single color."""
    assert matches_color_filter(["G"], ["G"], "≥") is True
    assert matches_color_filter(["G", "U"], ["G"], "≥") is True
    assert matches_color_filter(["U"], ["G"], "≥") is False


def test_matches_color_filter_at_least_multiple():
    """Test '≥' (at least) mode with multiple colors."""
    assert matches_color_filter(["G", "U"], ["G", "U"], "≥") is True
    assert matches_color_filter(["W", "U", "B", "R", "G"], ["G", "U"], "≥") is True
    assert matches_color_filter(["G"], ["G", "U"], "≥") is False


def test_matches_color_filter_exactly_single():
    """Test '=' (exactly) mode with single color."""
    assert matches_color_filter(["G"], ["G"], "=") is True
    assert matches_color_filter(["G", "U"], ["G"], "=") is False
    assert matches_color_filter(["U"], ["G"], "=") is False


def test_matches_color_filter_exactly_multiple():
    """Test '=' (exactly) mode with multiple colors."""
    assert matches_color_filter(["G", "U"], ["G", "U"], "=") is True
    assert matches_color_filter(["U", "G"], ["G", "U"], "=") is True
    assert matches_color_filter(["G", "U", "R"], ["G", "U"], "=") is False
    assert matches_color_filter(["G"], ["G", "U"], "=") is False


def test_matches_color_filter_not_these():
    """Test '≠' (not these) mode."""
    assert matches_color_filter(["R"], ["G", "U"], "≠") is True
    assert matches_color_filter(["G"], ["G", "U"], "≠") is False
    assert matches_color_filter(["G", "U"], ["G"], "≠") is False
    assert matches_color_filter(["W", "B"], ["R", "G"], "≠") is True


def test_matches_color_filter_colorless():
    """Test color filter with colorless cards."""
    # Empty color list should be treated as colorless "C"
    assert matches_color_filter([], ["C"], "≥") is True
    assert matches_color_filter([], ["C"], "=") is True
    assert matches_color_filter([], ["G"], "≠") is True


def test_matches_color_filter_case_insensitive():
    """Test that color filter is case insensitive."""
    assert matches_color_filter(["g"], ["G"], "≥") is True
    assert matches_color_filter(["G"], ["g"], "≥") is True
    assert matches_color_filter(["g", "u"], ["G", "U"], "=") is True


def test_matches_color_filter_colorless_not_these():
    """Test '≠' mode with colorless."""
    # Colorless card should not match any color
    assert matches_color_filter([], ["G"], "≠") is True
    assert matches_color_filter([], ["W", "U", "B", "R", "G"], "≠") is True


def test_matches_color_filter_unknown_mode():
    """Test color filter with unknown mode defaults to True."""
    assert matches_color_filter(["G"], ["U"], "UnknownMode") is True
