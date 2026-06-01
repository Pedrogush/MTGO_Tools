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


def test_format_deck_name_unknown_when_empty():
    assert deck_formatting.format_deck_name({}) == "Unknown"


# ---------------------------------------------------------------------------
# format_deck_list_entry
# ---------------------------------------------------------------------------
def test_format_deck_list_entry_two_lines():
    deck = {"player": "Bob", "result": "5-0", "date": "2024-01-02", "event": "Modern Challenge"}
    assert deck_formatting.format_deck_list_entry(deck) == "Bob, 5-0, 2024-01-02\nModern Challenge"


def test_format_deck_list_entry_with_source_prefix():
    deck = {"player": "Bob", "event": "Modern Challenge", "source": "mtggoldfish"}
    entry = deck_formatting.format_deck_list_entry(deck, show_source=True)
    assert entry.startswith("🐠 Bob")


# ---------------------------------------------------------------------------
# simple_summary_html
# ---------------------------------------------------------------------------
def test_simple_summary_html_escapes_and_breaks():
    html = deck_formatting.simple_summary_html("a<b>&\nc")
    assert "a&lt;b&gt;&amp;<br>c" in html
    assert html.startswith("<html>")
