"""Unit tests for the pure deck results filter logic in utils.deck_results_filter."""

from utils.deck_results_filter import _classify_event_type, _normalize_date, filter_decks

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
# filter_decks — result filter
# ---------------------------------------------------------------------------


def test_result_filter_exact_value():
    result = filter_decks(DECKS, result_query="1st")
    assert len(result) == 1
    assert result[0]["player"] == "PlayerAlpha"
    assert result[0]["event"] == "Modern Challenge"


def test_result_filter_partial_match():
    result = filter_decks(DECKS, result_query="top")
    assert len(result) == 1
    assert result[0]["result"] == "Top 8"


def test_result_filter_query_must_be_lowercased():
    # The caller (UI) is responsible for lowercasing; uppercase query won't match
    result = filter_decks(DECKS, result_query="TOP 8")
    assert len(result) == 0


def test_result_filter_no_match():
    result = filter_decks(DECKS, result_query="99th")
    assert result == []


def test_result_filter_empty_string_no_filter():
    result = filter_decks(DECKS, result_query="")
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


def test_combined_event_type_and_result():
    result = filter_decks(DECKS, event_type="League", result_query="5-0")
    assert len(result) == 1
    assert result[0]["player"] == "PlayerBeta"


def test_combined_event_type_and_date():
    result = filter_decks(DECKS, event_type="Challenge", date_query="2024-03")
    assert len(result) == 1
    assert result[0]["event"] == "Modern Challenge"


def test_combined_player_and_result():
    result = filter_decks(DECKS, player_query="alpha", result_query="1st")
    assert len(result) == 1
    assert result[0]["event"] == "Modern Challenge"


def test_combined_all_filters():
    result = filter_decks(
        DECKS,
        event_type="Challenge",
        result_query="1st",
        player_query="alpha",
        date_query="2024-03",
    )
    assert len(result) == 1
    assert result[0]["event"] == "Modern Challenge"


def test_combined_filters_no_match():
    result = filter_decks(
        DECKS, event_type="League", result_query="1st", player_query="alpha", date_query="2024"
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


def test_result_filter_on_deck_missing_result_field():
    decks = [{"event": "Challenge", "player": "P", "date": "2024-01-01"}]
    result = filter_decks(decks, result_query="1st")
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
