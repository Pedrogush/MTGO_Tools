"""Tests for impossible-future deck-date repair (utils.deck_dates).

Regression context: MTGGoldfish served a paper Store Qualifier played on
2026-04-11 with the day/month-transposed date ``2026-11-04``. Both fields
are <= 12, so the string parses cleanly as YYYY-MM-DD and the existing
YYYY-DD-MM fallback in ``_parse_deck_date`` never fires — the deck showed
up "from the future" at the top of the Modern deck list.
"""

from datetime import date, timedelta

from repositories.metagame_repository.date_utils import _parse_deck_date
from utils.deck_dates import repair_future_date

TODAY = date(2026, 7, 24)


# ---------------------------------------------------------------------------
# repair_future_date
# ---------------------------------------------------------------------------
def test_ambiguous_day_month_swap_is_repaired():
    # The real-world regression: April 11 published as 2026-11-04.
    assert repair_future_date("2026-11-04", today=TODAY) == "2026-04-11"


def test_past_dates_are_untouched():
    assert repair_future_date("2026-04-11", today=TODAY) == "2026-04-11"
    assert repair_future_date("2019-12-31", today=TODAY) == "2019-12-31"


def test_today_and_tomorrow_are_untouched():
    assert repair_future_date("2026-07-24", today=TODAY) == "2026-07-24"
    # A source clock running ahead can legitimately stamp tomorrow.
    assert repair_future_date("2026-07-25", today=TODAY) == "2026-07-25"


def test_unrepairable_future_date_is_blanked():
    # Swap would need month 25 — invalid, so the date is unknown.
    assert repair_future_date("2026-12-25", today=TODAY) == ""
    # Swap is valid but still in the future.
    assert repair_future_date("2027-01-02", today=TODAY) == ""


def test_non_iso_strings_pass_through():
    assert repair_future_date("", today=TODAY) == ""
    assert repair_future_date("04/15/2026", today=TODAY) == "04/15/2026"
    assert repair_future_date("2026-25-03", today=TODAY) == "2026-25-03"
    assert repair_future_date("not a date", today=TODAY) == "not a date"


# ---------------------------------------------------------------------------
# _parse_deck_date sort keys
# ---------------------------------------------------------------------------
def test_sort_key_uses_true_date_for_transposed_future_date():
    assert _parse_deck_date("2026-11-04", today=TODAY) == (2026, 4, 11)


def test_sort_key_sends_unrepairable_future_date_to_the_bottom():
    assert _parse_deck_date("2027-01-02", today=TODAY) == (0, 0, 0)


def test_sort_key_normal_forms_still_parse():
    assert _parse_deck_date("2026-07-20", today=TODAY) == (2026, 7, 20)
    assert _parse_deck_date("07/20/2026", today=TODAY) == (2026, 7, 20)
    # Issue #475 fallback: unambiguous YYYY-DD-MM still parses.
    assert _parse_deck_date("2026-25-03", today=TODAY) == (2026, 3, 25)


def test_future_deck_no_longer_sorts_to_the_top():
    decks = [
        {"date": "2026-11-04"},  # actually 2026-04-11
        {"date": "2026-07-20"},
        {"date": "2026-05-01"},
    ]
    decks.sort(key=lambda d: _parse_deck_date(d.get("date", ""), today=TODAY), reverse=True)
    assert [d["date"] for d in decks] == ["2026-07-20", "2026-05-01", "2026-11-04"]


# ---------------------------------------------------------------------------
# Regression: the UI display path never shows a date from the future
# ---------------------------------------------------------------------------
def test_ui_never_displays_a_future_date():
    from widgets.panels.deck_research_panel.results_filter import _normalize_date

    horizon = TODAY + timedelta(days=1)
    samples = [
        "2026-11-04",  # the regression itself
        "2026-12-25",  # unrepairable transposition
        "2027-01-02",
        "9999-12-31",
        "2026-07-24",
        "2026-07-25",
        "2019-12-31",
        "Modern Challenge 2026-11-04",  # date embedded in an event string
        "",
    ]
    for value in samples:
        shown = _normalize_date(value, today=TODAY)
        try:
            shown_date = date.fromisoformat(shown)
        except ValueError:
            continue  # non-date display values are out of scope here
        assert shown_date <= horizon, f"UI would display future date {shown!r} for {value!r}"


def test_ui_never_displays_a_future_date_with_real_clock():
    # The UI calls _normalize_date without a `today` argument; make sure the
    # default-clock path also repairs. 9999-12-31 is future on any clock.
    from widgets.panels.deck_research_panel.results_filter import _normalize_date

    assert _normalize_date("9999-12-31") == ""
