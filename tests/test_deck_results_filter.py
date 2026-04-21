"""Unit tests for the pure deck results filter logic in utils.deck_results_filter."""

from utils.deck_results_filter import (
    _classify_event_type,
    _normalize_date,
    filter_decks,
    parse_placement,
    parse_wins,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DECKS = [
    {"event": "Modern Challenge", "result": "1st", "player": "PlayerAlpha", "date": "2024-03-01"},
    {"event": "Modern League", "result": "5-0", "player": "PlayerBeta", "date": "2024-03-05"},
    {
        "event": "Modern Showcase Challenge",
        "result": "Top 8",
        "player": "PlayerGamma",
        "date": "2024-04-10",
    },
    {"event": "Modern Last Chance", "result": "7th", "player": "PlayerDelta", "date": "2024-04-15"},
    {"event": "Legacy Challenge", "result": "2nd", "player": "PlayerAlpha", "date": "2024-05-20"},
    {"event": "Legacy League", "result": "4-1", "player": "PlayerEpsilon", "date": "2024-05-25"},
    {"event": "Special Event", "result": "Winner", "player": "PlayerZeta", "date": "2024-06-01"},
]


# ---------------------------------------------------------------------------
# _classify_event_type
# ---------------------------------------------------------------------------


def test_classify_challenge():
    assert _classify_event_type("Modern Challenge") == "Challenge"


def test_classify_league():
    assert _classify_event_type("Legacy League") == "League"


def test_classify_showcase():
    assert _classify_event_type("Modern Showcase Challenge") == "Showcase"


def test_classify_last_chance():
    assert _classify_event_type("Modern Last Chance Qualifier") == "Last Chance"


def test_classify_last_chance_takes_priority_over_challenge():
    # "last chance" must beat "challenge" (checked first in the function)
    assert _classify_event_type("Last Chance Challenge") == "Last Chance"


def test_classify_showcase_takes_priority_over_challenge():
    # "showcase" must beat "challenge"
    assert _classify_event_type("Modern Showcase Challenge") == "Showcase"


def test_classify_unknown_returns_none():
    assert _classify_event_type("Special Event") is None


def test_classify_empty_string_returns_none():
    assert _classify_event_type("") is None


def test_classify_case_insensitive():
    assert _classify_event_type("MODERN CHALLENGE") == "Challenge"
    assert _classify_event_type("modern league") == "League"


# ---------------------------------------------------------------------------
# _normalize_date
# ---------------------------------------------------------------------------


def test_normalize_date_plain():
    assert _normalize_date("2024-03-01") == "2024-03-01"


def test_normalize_date_embedded():
    assert _normalize_date("Some text 2024-03-01 more text") == "2024-03-01"


def test_normalize_date_empty():
    assert _normalize_date("") == ""


def test_normalize_date_no_date_returns_as_is():
    assert _normalize_date("no date here") == "no date here"


def test_normalize_date_extracts_first_date():
    assert _normalize_date("2024-03-01 to 2024-03-10") == "2024-03-01"


# ---------------------------------------------------------------------------
# parse_placement
# ---------------------------------------------------------------------------


def test_parse_placement_ordinals():
    assert parse_placement("1st") == 1
    assert parse_placement("2nd") == 2
    assert parse_placement("3rd") == 3
    assert parse_placement("7th") == 7
    assert parse_placement("11th") == 11


def test_parse_placement_top_n():
    assert parse_placement("Top 8") == 8
    assert parse_placement("Top 16") == 16
    assert parse_placement("top32") == 32


def test_parse_placement_record_returns_none():
    # Record-style results are not placements
    assert parse_placement("5-0") is None
    assert parse_placement("4-1") is None


def test_parse_placement_unparseable_returns_none():
    assert parse_placement("Winner") is None
    assert parse_placement("") is None


# ---------------------------------------------------------------------------
# parse_wins
# ---------------------------------------------------------------------------


def test_parse_wins_record():
    assert parse_wins("5-0") == 5
    assert parse_wins("4-1") == 4
    assert parse_wins("0-3") == 0


def test_parse_wins_non_record_returns_none():
    assert parse_wins("1st") is None
    assert parse_wins("Top 8") is None
    assert parse_wins("Winner") is None
    assert parse_wins("") is None


# ---------------------------------------------------------------------------
# filter_decks — no filters (all results returned)
# ---------------------------------------------------------------------------


def test_no_filters_returns_all():
    result = filter_decks(DECKS)
    assert result == DECKS


def test_no_filters_empty_list():
    assert filter_decks([]) == []


# ---------------------------------------------------------------------------
# filter_decks — event type filter
# ---------------------------------------------------------------------------


def test_event_type_challenge():
    result = filter_decks(DECKS, event_type="Challenge")
    assert all(_classify_event_type(d["event"]) == "Challenge" for d in result)
    assert len(result) == 2  # Modern Challenge, Legacy Challenge


def test_event_type_league():
    result = filter_decks(DECKS, event_type="League")
    assert all(_classify_event_type(d["event"]) == "League" for d in result)
    assert len(result) == 2  # Modern League, Legacy League


def test_event_type_showcase():
    result = filter_decks(DECKS, event_type="Showcase")
    assert len(result) == 1
    assert result[0]["event"] == "Modern Showcase Challenge"


def test_event_type_last_chance():
    result = filter_decks(DECKS, event_type="Last Chance")
    assert len(result) == 1
    assert result[0]["event"] == "Modern Last Chance"


def test_event_type_all_returns_everything():
    result = filter_decks(DECKS, event_type="All")
    assert result == DECKS


def test_event_type_no_matches():
    result = filter_decks(DECKS, event_type="Showcase")
    # Verify none of them is a plain "League" deck
    assert not any(_classify_event_type(d["event"]) == "League" for d in result)


# ---------------------------------------------------------------------------
# filter_decks — placement filter (operator + field + value)
# ---------------------------------------------------------------------------


def test_placement_filter_eq_placement_value():
    # placement = 1 → only "1st"
    result = filter_decks(DECKS, placement_op="=", placement_field="placement", placement_value="1")
    assert len(result) == 1
    assert result[0]["result"] == "1st"


def test_placement_filter_ge_placement_includes_top_8():
    # placement >= 8 → Top 8 (placement=8); 1st, 2nd, 7th excluded
    result = filter_decks(
        DECKS, placement_op=">=", placement_field="placement", placement_value="8"
    )
    placements = [d["result"] for d in result]
    assert placements == ["Top 8"]


def test_placement_filter_lt_placement_excludes_top_8():
    # placement < 8 → 1st, 2nd, 7th
    result = filter_decks(DECKS, placement_op="<", placement_field="placement", placement_value="8")
    placements = [d["result"] for d in result]
    assert placements == ["1st", "7th", "2nd"]


def test_placement_filter_gt_wins_4():
    # wins > 4 → 5-0
    result = filter_decks(DECKS, placement_op=">", placement_field="wins", placement_value="4")
    assert len(result) == 1
    assert result[0]["result"] == "5-0"


def test_placement_filter_ge_wins_4():
    # wins >= 4 → 5-0 and 4-1
    result = filter_decks(DECKS, placement_op=">=", placement_field="wins", placement_value="4")
    results = sorted(d["result"] for d in result)
    assert results == ["4-1", "5-0"]


def test_placement_filter_excludes_decks_without_parseable_value():
    # placement filter against "wins" excludes "1st", "2nd", "Top 8", "7th", "Winner"
    result = filter_decks(DECKS, placement_op=">=", placement_field="wins", placement_value="0")
    assert len(result) == 2  # Only 5-0 and 4-1 have wins data


def test_placement_filter_no_op_skips_filter():
    result = filter_decks(DECKS, placement_op="", placement_field="placement", placement_value="1")
    assert result == DECKS


def test_placement_filter_no_value_skips_filter():
    result = filter_decks(DECKS, placement_op=">", placement_field="placement", placement_value="")
    assert result == DECKS


def test_placement_filter_invalid_value_skips_filter():
    result = filter_decks(
        DECKS, placement_op=">", placement_field="placement", placement_value="abc"
    )
    assert result == DECKS


def test_placement_filter_unknown_field_skips_filter():
    result = filter_decks(DECKS, placement_op=">", placement_field="unknown", placement_value="1")
    assert result == DECKS


def test_placement_filter_unknown_op_skips_filter():
    result = filter_decks(
        DECKS, placement_op="!=", placement_field="placement", placement_value="1"
    )
    assert result == DECKS


# ---------------------------------------------------------------------------
# filter_decks — player name filter
# ---------------------------------------------------------------------------


def test_player_filter_exact():
    result = filter_decks(DECKS, player_query="playerbeta")
    assert len(result) == 1
    assert result[0]["player"] == "PlayerBeta"


def test_player_filter_partial():
    result = filter_decks(DECKS, player_query="alpha")
    assert len(result) == 2
    assert all("Alpha" in d["player"] for d in result)


def test_player_filter_query_must_be_lowercased():
    # The caller (UI) is responsible for lowercasing; uppercase query won't match
    result = filter_decks(DECKS, player_query="PLAYERBETA")
    assert len(result) == 0


def test_player_filter_no_match():
    result = filter_decks(DECKS, player_query="nobody")
    assert result == []


def test_player_filter_empty_string_no_filter():
    result = filter_decks(DECKS, player_query="")
    assert result == DECKS


# ---------------------------------------------------------------------------
# filter_decks — date filter
# ---------------------------------------------------------------------------


def test_date_filter_full_date():
    result = filter_decks(DECKS, date_query="2024-03-01")
    assert len(result) == 1
    assert result[0]["event"] == "Modern Challenge"


def test_date_filter_year_month_prefix():
    result = filter_decks(DECKS, date_query="2024-04")
    assert len(result) == 2
    dates = {d["date"] for d in result}
    assert dates == {"2024-04-10", "2024-04-15"}


def test_date_filter_year_prefix():
    result = filter_decks(DECKS, date_query="2024")
    assert len(result) == len(DECKS)  # all decks are in 2024


def test_date_filter_no_match():
    result = filter_decks(DECKS, date_query="2099")
    assert result == []


def test_date_filter_empty_string_no_filter():
    result = filter_decks(DECKS, date_query="")
    assert result == DECKS


def test_date_filter_with_embedded_date_in_field():
    decks = [{"event": "E", "result": "1st", "player": "P", "date": "Modern Challenge 2024-03-01"}]
    result = filter_decks(decks, date_query="2024-03")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# filter_decks — combined filters (AND logic)
# ---------------------------------------------------------------------------


def test_combined_event_type_and_player():
    result = filter_decks(DECKS, event_type="Challenge", player_query="alpha")
    assert len(result) == 2  # Modern Challenge (PlayerAlpha) + Legacy Challenge (PlayerAlpha)


def test_combined_event_type_and_placement():
    result = filter_decks(
        DECKS,
        event_type="League",
        placement_op="=",
        placement_field="wins",
        placement_value="5",
    )
    assert len(result) == 1
    assert result[0]["player"] == "PlayerBeta"


def test_combined_event_type_and_date():
    result = filter_decks(DECKS, event_type="Challenge", date_query="2024-03")
    assert len(result) == 1
    assert result[0]["event"] == "Modern Challenge"


def test_combined_player_and_placement():
    result = filter_decks(
        DECKS,
        player_query="alpha",
        placement_op="=",
        placement_field="placement",
        placement_value="1",
    )
    assert len(result) == 1
    assert result[0]["event"] == "Modern Challenge"


def test_combined_all_filters():
    result = filter_decks(
        DECKS,
        event_type="Challenge",
        placement_op="=",
        placement_field="placement",
        placement_value="1",
        player_query="alpha",
        date_query="2024-03",
    )
    assert len(result) == 1
    assert result[0]["event"] == "Modern Challenge"


def test_combined_filters_no_match():
    result = filter_decks(
        DECKS,
        event_type="League",
        placement_op="=",
        placement_field="placement",
        placement_value="1",
        player_query="alpha",
        date_query="2024",
    )
    # PlayerAlpha has no League entries
    assert result == []


# ---------------------------------------------------------------------------
# filter_decks — missing fields / edge cases
# ---------------------------------------------------------------------------


def test_deck_missing_all_fields():
    decks = [{}]
    # No filters active — should pass through
    assert filter_decks(decks) == [{}]


def test_event_filter_on_deck_missing_event_field():
    decks = [{"result": "1st", "player": "P", "date": "2024-01-01"}]
    result = filter_decks(decks, event_type="Challenge")
    assert result == []


def test_placement_filter_on_deck_missing_result_field():
    decks = [{"event": "Challenge", "player": "P", "date": "2024-01-01"}]
    result = filter_decks(decks, placement_op="=", placement_field="placement", placement_value="1")
    assert result == []


def test_player_filter_on_deck_missing_player_field():
    decks = [{"event": "Challenge", "result": "1st", "date": "2024-01-01"}]
    result = filter_decks(decks, player_query="anyone")
    assert result == []


def test_date_filter_on_deck_missing_date_field():
    decks = [{"event": "Challenge", "result": "1st", "player": "P"}]
    result = filter_decks(decks, date_query="2024")
    assert result == []


def test_preserves_order():
    result = filter_decks(DECKS, event_type="Challenge")
    events = [d["event"] for d in result]
    assert events == ["Modern Challenge", "Legacy Challenge"]
