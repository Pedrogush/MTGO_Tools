"""Unit tests for the pure deck-formatting helpers extracted from app_events.

These are wx-free module-level functions. They are loaded directly from the
source file so importing them does not trigger the ``widgets.frames.app_frame``
package ``__init__`` (which imports ``wx``, unavailable off-Windows).
"""

import importlib.util
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "widgets"
    / "frames"
    / "app_frame"
    / "handlers"
    / "deck_formatting.py"
)
_spec = importlib.util.spec_from_file_location("_deck_formatting_under_test", _MODULE_PATH)
deck_formatting = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deck_formatting)


# ---------------------------------------------------------------------------
# strip_extra_dates
# ---------------------------------------------------------------------------
def test_strip_extra_dates_empty():
    assert deck_formatting.strip_extra_dates("") == ""


def test_strip_extra_dates_no_date_returns_input():
    assert deck_formatting.strip_extra_dates("Modern Challenge") == "Modern Challenge"


def test_strip_extra_dates_removes_trailing_date():
    assert deck_formatting.strip_extra_dates("Modern Challenge 2024-01-02") == "Modern Challenge"


def test_strip_extra_dates_collapses_whitespace():
    assert deck_formatting.strip_extra_dates("Modern 2024-01-02 Challenge") == "Modern Challenge"


def test_strip_extra_dates_multiple_dates_with_pipe_separators():
    assert (
        deck_formatting.strip_extra_dates("Modern Challenge | 2024-01-02 | 2024-02-03")
        == "Modern Challenge"
    )


def test_strip_extra_dates_en_dash_separators():
    assert deck_formatting.strip_extra_dates("Modern–2024-01-02–Challenge") == "Modern Challenge"


def test_strip_extra_dates_em_dash_separators():
    assert deck_formatting.strip_extra_dates("Modern—2024-01-02—Challenge") == "Modern Challenge"


def test_strip_extra_dates_slash_separators():
    assert deck_formatting.strip_extra_dates("Modern/2024-01-02/Challenge") == "Modern Challenge"


def test_strip_extra_dates_hyphen_separators():
    assert deck_formatting.strip_extra_dates("Modern-2024-01-02-Challenge") == "Modern Challenge"


def test_strip_extra_dates_whole_string_is_date_returns_empty():
    assert deck_formatting.strip_extra_dates("2024-01-02") == ""


def test_strip_extra_dates_date_with_surrounding_pipes_returns_empty():
    assert deck_formatting.strip_extra_dates("| 2024-01-02 |") == ""


# ---------------------------------------------------------------------------
# format_deck_name
# ---------------------------------------------------------------------------
def test_format_deck_name_full():
    deck = {
        "player": "Bob",
        "result": "5-0",
        "date": "2024-01-02",
        "event": "Modern Challenge 2024-01-02",
    }
    assert deck_formatting.format_deck_name(deck) == "Bob, 5-0, 2024-01-02 | Modern Challenge"


def test_format_deck_name_normalizes_non_normalized_date():
    # ``date`` carries an embedded event string; normalize_date must extract
    # just the YYYY-MM-DD substring before it lands in line one.
    deck = {"player": "Bob", "date": "Modern Challenge 2024-01-02"}
    assert deck_formatting.format_deck_name(deck) == "Bob, 2024-01-02"


def test_format_deck_name_unknown_when_empty():
    assert deck_formatting.format_deck_name({}) == "Unknown"


def test_format_deck_name_no_event_strips_trailing_separator():
    deck = {"player": "Bob", "result": "5-0", "date": "2024-01-02"}
    assert deck_formatting.format_deck_name(deck) == "Bob, 5-0, 2024-01-02"


def test_format_deck_name_event_only_keeps_unknown_identity():
    # line_one always falls back to "Unknown", so the leading separator is not
    # stripped — only the trailing one is when the event is empty.
    assert (
        deck_formatting.format_deck_name({"event": "Modern Challenge"})
        == "Unknown | Modern Challenge"
    )


# ---------------------------------------------------------------------------
# format_deck_list_entry
# ---------------------------------------------------------------------------
def test_format_deck_list_entry_two_lines():
    deck = {"player": "Bob", "result": "5-0", "date": "2024-01-02", "event": "Modern Challenge"}
    assert deck_formatting.format_deck_list_entry(deck) == "Bob, 5-0, 2024-01-02\nModern Challenge"


def test_format_deck_list_entry_normalizes_non_normalized_date():
    deck = {"player": "Bob", "date": "Modern Challenge 2024-01-02"}
    assert deck_formatting.format_deck_list_entry(deck) == "Bob, 2024-01-02"


def test_format_deck_list_entry_with_mtggoldfish_source_prefix():
    deck = {"player": "Bob", "event": "Modern Challenge", "source": "mtggoldfish"}
    entry = deck_formatting.format_deck_list_entry(deck, show_source=True)
    assert entry == "🐠 Bob\nModern Challenge"


def test_format_deck_list_entry_with_non_mtggoldfish_source_prefix():
    deck = {"player": "Bob", "event": "Modern Challenge", "source": "aetherhub"}
    entry = deck_formatting.format_deck_list_entry(deck, show_source=True)
    assert entry == "🧙🏾‍♂️ Bob\nModern Challenge"


def test_format_deck_list_entry_missing_source_uses_wizard_emoji():
    deck = {"player": "Bob", "event": "Modern Challenge"}
    entry = deck_formatting.format_deck_list_entry(deck, show_source=True)
    assert entry == "🧙🏾‍♂️ Bob\nModern Challenge"


def test_format_deck_list_entry_empty_falls_back_to_unknown():
    assert deck_formatting.format_deck_list_entry({}) == "Unknown"


def test_format_deck_list_entry_empty_with_source_prepends_emoji_to_unknown():
    entry = deck_formatting.format_deck_list_entry({}, show_source=True)
    assert entry == "🧙🏾‍♂️ Unknown"


def test_format_deck_list_entry_event_only_keeps_unknown_identity():
    entry = deck_formatting.format_deck_list_entry({"event": "Modern Challenge"})
    assert entry == "Unknown\nModern Challenge"


# ---------------------------------------------------------------------------
# re-exports
# ---------------------------------------------------------------------------
def test_normalize_date_is_reexported():
    assert deck_formatting.normalize_date("Modern Challenge 2024-01-02") == "2024-01-02"


def test_classify_event_type_is_reexported():
    assert deck_formatting.classify_event_type("Modern Challenge") == "Challenge"
    assert deck_formatting.classify_event_type("Modern League") == "League"
    assert deck_formatting.classify_event_type("Friday Night") is None


# ---------------------------------------------------------------------------
# simple_summary_html
# ---------------------------------------------------------------------------
def test_simple_summary_html_escapes_and_breaks():
    html = deck_formatting.simple_summary_html("a<b>&\nc")
    assert "a&lt;b&gt;&amp;<br>c" in html
    assert html.startswith("<html>")


def test_simple_summary_html_full_template():
    assert deck_formatting.simple_summary_html("hi") == (
        '<html><body bgcolor="#22272E" text="#ECECEC">' '<font size="2">hi</font>' "</body></html>"
    )
