"""Tests for the wx-independent bulk-populate logic of the deck results list.

These cover :meth:`DeckResultsListHandlersMixin.set_decks`, the batched
populate that replaces the per-row ``SetItemCount``/``Refresh`` calls so the
916-row deck list triggers exactly one layout/scrollbar recomputation. ``wx`` is
not importable in the WSL dev environment, so a minimal stub module is injected
before importing the handler module by file path.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


class _WxStub(types.ModuleType):
    """A permissive ``wx`` stand-in fabricating attributes on demand.

    The handlers module only references ``wx`` for type annotations at import
    time, so any attribute access can return a harmless placeholder.
    """

    def __getattr__(self, name: str) -> Any:  # noqa: D401 - simple stub
        value: Any = type(name, (), {})
        setattr(self, name, value)
        return value


def _install_wx_stub() -> types.ModuleType:
    """Install a ``wx`` stub only when the real module is unavailable."""
    try:
        import wx as real_wx  # noqa: F401

        return sys.modules["wx"]
    except Exception:
        pass
    stub = _WxStub("wx")
    sys.modules["wx"] = stub
    return stub


def _load_module(filename: str, internal_name: str) -> types.ModuleType:
    """Import a deck results list module directly by file path."""
    path = (
        Path(__file__).resolve().parent.parent
        / "widgets"
        / "lists"
        / "deck_results_list"
        / filename
    )
    spec = importlib.util.spec_from_file_location(internal_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_install_wx_stub()
DeckResultsListHandlersMixin = _load_module(
    "handlers.py", "_drl_handlers_under_test"
).DeckResultsListHandlersMixin
DeckResultsListPropertiesMixin = _load_module(
    "properties.py", "_drl_properties_under_test"
).DeckResultsListPropertiesMixin


class _FakeDC:
    """A minimal ``wx.DC`` stand-in where text width equals character count.

    ``_truncate_to_width`` only calls :meth:`GetTextExtent`, so reporting one
    pixel per character makes ``max_width`` behave like a maximum length and
    keeps the truncation branches exercisable without ``wx``.
    """

    def GetTextExtent(self, text: str) -> tuple[int, int]:
        return len(text), 1


class _FakeList(DeckResultsListPropertiesMixin, DeckResultsListHandlersMixin):
    """Concrete mixin host recording the wx base-class calls under test."""

    # Mirror the sizing constants defined on the real frame so the wx-free
    # ``OnMeasureItem`` height formula can be exercised without wx.
    _ITEM_MARGIN = 6
    _CARD_PADDING = 8

    def __init__(self) -> None:
        self._items: list[tuple[bool, tuple]] = []
        self.set_item_count_calls: list[int] = []
        self.refresh_calls = 0
        self.freeze_calls = 0
        self.thaw_calls = 0
        self._char_height = 14

    def GetCharHeight(self) -> int:
        return self._char_height

    def SetItemCount(self, count: int) -> None:
        self.set_item_count_calls.append(count)

    def Refresh(self) -> None:
        self.refresh_calls += 1

    def Freeze(self) -> None:
        self.freeze_calls += 1

    def Thaw(self) -> None:
        self.thaw_calls += 1


def _make_rows(n: int) -> list[tuple[str, str, str, str, str, str]]:
    return [("", f"player{i}", f"arch{i}", f"event{i}", f"result{i}", f"date{i}") for i in range(n)]


def test_set_decks_single_layout_pass() -> None:
    lst = _FakeList()
    rows = _make_rows(916)

    lst.set_decks(rows)

    # Exactly one SetItemCount + Refresh regardless of row count.
    assert lst.set_item_count_calls == [916]
    assert lst.refresh_calls == 1
    # Wrapped in a single Freeze/Thaw pair.
    assert lst.freeze_calls == 1
    assert lst.thaw_calls == 1


def test_set_decks_appends_structured_rows() -> None:
    lst = _FakeList()
    rows = _make_rows(3)

    lst.set_decks(rows)

    assert len(lst._items) == 3
    for (is_structured, data), row in zip(lst._items, rows):
        assert is_structured is True
        assert data == row


def test_set_decks_appends_after_existing_items() -> None:
    lst = _FakeList()
    lst._items.append((False, ("", "preexisting", "")))

    lst.set_decks(_make_rows(2))

    assert len(lst._items) == 3
    assert lst.set_item_count_calls == [3]


def test_set_decks_empty_still_single_pass() -> None:
    lst = _FakeList()

    lst.set_decks([])

    assert lst.set_item_count_calls == [0]
    assert lst.refresh_calls == 1
    assert lst.freeze_calls == 1
    assert lst.thaw_calls == 1


def test_set_decks_thaws_on_exception() -> None:
    """A malformed row must not leave the control permanently frozen.

    The populate loop unpacks each row into six fields; a wrong-arity row raises
    ``ValueError`` mid-loop. The ``try/finally`` guarantees :meth:`Thaw` still
    runs, so a regression moving Thaw out of the finally block would fail here.
    """
    lst = _FakeList()

    try:
        lst.set_decks([("only", "two")])  # type: ignore[list-item]
        raise AssertionError("expected ValueError from malformed row unpack")
    except ValueError:
        pass

    assert lst.freeze_calls == 1
    assert lst.thaw_calls == 1


def test_append_deck_single_row_field_order() -> None:
    """AppendDeck stores fields in the same order set_decks does and bumps once."""
    lst = _FakeList()

    lst.AppendDeck(
        "player0",
        "event0",
        "result0",
        "date0",
        emoji="*",
        archetype="arch0",
    )

    assert lst._items[-1] == (True, ("*", "player0", "arch0", "event0", "result0", "date0"))
    assert lst.set_item_count_calls == [1]
    assert lst.refresh_calls == 1


def test_append_deck_after_existing_items() -> None:
    lst = _FakeList()
    lst._items.append((False, ("", "preexisting", "")))

    lst.AppendDeck("p", "e", "r", "d")

    assert len(lst._items) == 2
    assert lst._items[-1] == (True, ("", "p", "", "e", "r", "d"))
    assert lst.set_item_count_calls == [2]


def test_append_single_line_plain_row() -> None:
    """Append stores an unstructured row and bumps the count/refresh once."""
    lst = _FakeList()

    lst.Append("just one line")

    assert lst._items == [(False, ("", "just one line", ""))]
    assert lst.set_item_count_calls == [1]
    assert lst.refresh_calls == 1


def test_append_splits_two_lines_and_emoji_prefix() -> None:
    """Multi-line text splits into line one/two with the emoji prefix peeled off."""
    lst = _FakeList()

    lst.Append("✨ winner name\nthe event")

    is_structured, (emoji_prefix, line_one, line_two) = lst._items[-1]
    assert is_structured is False
    assert emoji_prefix == "✨ "
    assert line_one == "winner name"
    assert line_two == "the event"


def test_append_after_existing_items() -> None:
    lst = _FakeList()
    lst._items.append((True, ("", "pre", "", "e", "r", "d")))

    lst.Append("second")

    assert len(lst._items) == 2
    assert lst._items[-1] == (False, ("", "second", ""))
    assert lst.set_item_count_calls == [2]


def test_clear_resets_items_and_count() -> None:
    """Clear drops all rows and resets the virtual item count to zero."""
    lst = _FakeList()
    lst.set_decks(_make_rows(5))

    lst.Clear()

    assert lst._items == []
    assert lst.set_item_count_calls[-1] == 0
    assert lst.refresh_calls == 2  # one from set_decks, one from Clear


def test_clear_on_empty_list_is_safe() -> None:
    lst = _FakeList()

    lst.Clear()

    assert lst._items == []
    assert lst.set_item_count_calls == [0]
    assert lst.refresh_calls == 1


def test_truncate_empty_text_returned_unchanged() -> None:
    lst = _FakeList()

    assert lst._truncate_to_width(_FakeDC(), "", 10) == ""


def test_truncate_text_that_fits_is_unchanged() -> None:
    lst = _FakeList()

    assert lst._truncate_to_width(_FakeDC(), "short", 10) == "short"


def test_truncate_breaks_on_word_boundary() -> None:
    """Overlong multi-word text drops trailing words and appends an ellipsis."""
    lst = _FakeList()

    # "alpha beta gamma" is 16 chars; width 8 forces dropping words. After
    # "alpha beta..." (13) and "alpha..." (8) it fits.
    result = lst._truncate_to_width(_FakeDC(), "alpha beta gamma", 8)

    assert result == "alpha..."
    assert len(result) <= 8


def test_truncate_single_word_returns_after_one_cut_even_if_still_too_wide() -> None:
    """The single-word branch returns immediately, *without* re-checking width.

    "abcdefgh" (8 wide) with ``max_width=5`` is cut once to "abcdefg..." (10
    wide under the one-pixel-per-char fake) and returned as-is: the branch does
    not loop, so the result can still exceed ``max_width``. This asserts that
    early-return invariant rather than the (unmet) width constraint.
    """
    lst = _FakeList()

    result = lst._truncate_to_width(_FakeDC(), "abcdefgh", 5)

    assert result == "abcdefg..."  # single-word branch returns on first cut
    # Documents the no-loop behaviour: the cut result is wider than max_width.
    assert len(result) > 5


def test_truncate_collapses_existing_ellipsis() -> None:
    """A word already ending in ``...`` shortens before re-adding the ellipsis."""
    lst = _FakeList()

    result = lst._truncate_to_width(_FakeDC(), "abcd...", 5)

    assert result == "abc..."


def test_truncate_collapses_to_bare_ellipsis_when_tiny() -> None:
    """A word of exactly ``...`` plus one char collapses to a bare ellipsis."""
    lst = _FakeList()

    result = lst._truncate_to_width(_FakeDC(), "a...", 2)

    assert result == "..."


# ---------------------------------------------------------------------------
# GetString — structured/plain/out-of-range data shaping
# ---------------------------------------------------------------------------


def test_get_string_structured_full_row_with_emoji_and_event() -> None:
    """A structured row joins player/archetype/result/date and appends the event line."""
    lst = _FakeList()
    lst.AppendDeck(
        "player0",
        "event0",
        "result0",
        "date0",
        emoji="*",
        archetype="arch0",
    )

    assert lst.GetString(0) == "* player0, arch0, result0, date0\nevent0"


def test_get_string_structured_no_archetype_no_emoji_no_event() -> None:
    """Empty emoji/archetype/event drop their fragments rather than leaving separators."""
    lst = _FakeList()
    lst.AppendDeck("player0", "", "result0", "date0")

    assert lst.GetString(0) == "player0, result0, date0"


def test_get_string_plain_row_with_emoji_and_second_line() -> None:
    """A plain (unstructured) row prefixes the emoji and appends the second line."""
    lst = _FakeList()
    lst.Append("✨ winner name\nthe event")

    assert lst.GetString(0) == "✨ winner name\nthe event"


def test_get_string_plain_row_single_line_no_emoji() -> None:
    """A single-line plain row returns just the first line."""
    lst = _FakeList()
    lst.Append("just one line")

    assert lst.GetString(0) == "just one line"


def test_get_string_out_of_range_returns_empty() -> None:
    """Indices below zero or past the end return an empty string, never raise."""
    lst = _FakeList()
    lst.Append("only row")

    assert lst.GetString(-1) == ""
    assert lst.GetString(1) == ""
    assert lst.GetString(99) == ""


# ---------------------------------------------------------------------------
# _split_lines / _split_emoji_prefix edge branches
# ---------------------------------------------------------------------------


def test_split_lines_three_lines_joins_tail() -> None:
    """Three or more lines collapse into line one plus a space-joined remainder."""
    lst = _FakeList()

    assert lst._split_lines("one\ntwo\nthree") == ("one", "two three")


def test_split_lines_blank_only_returns_empty_pair() -> None:
    """Whitespace-only input yields two empty strings."""
    lst = _FakeList()

    assert lst._split_lines("   \n\t\n  ") == ("", "")


def test_split_lines_single_line_has_empty_second() -> None:
    lst = _FakeList()

    assert lst._split_lines("solo") == ("solo", "")


def test_split_emoji_prefix_no_space_treats_whole_as_prefix() -> None:
    """A leading non-ASCII run with no space becomes the prefix, leaving no body."""
    lst = _FakeList()

    assert lst._split_emoji_prefix("✨winner") == ("✨winner", "")


def test_split_emoji_prefix_ascii_start_has_no_prefix() -> None:
    lst = _FakeList()

    assert lst._split_emoji_prefix("winner name") == ("", "winner name")


def test_split_emoji_prefix_empty_string() -> None:
    lst = _FakeList()

    assert lst._split_emoji_prefix("") == ("", "")


# ---------------------------------------------------------------------------
# GetCount and OnMeasureItem (wx-free sizing)
# ---------------------------------------------------------------------------


def test_get_count_tracks_mutations() -> None:
    """GetCount reflects appends and the reset performed by Clear."""
    lst = _FakeList()
    assert lst.GetCount() == 0

    lst.set_decks(_make_rows(4))
    assert lst.GetCount() == 4

    lst.Append("extra")
    assert lst.GetCount() == 5

    lst.Clear()
    assert lst.GetCount() == 0


def test_on_measure_item_height_formula() -> None:
    """Row height is two char rows + 2px gap plus margin and padding on both sides."""
    lst = _FakeList()
    lst._char_height = 14

    # 14*2 + 2 (content) + 6*2 (margins) + 8*2 (padding) = 58
    assert lst.OnMeasureItem(0) == 58


def test_on_measure_item_independent_of_row_index() -> None:
    """Every row measures the same fixed two-line height regardless of index."""
    lst = _FakeList()
    lst.set_decks(_make_rows(3))

    assert lst.OnMeasureItem(0) == lst.OnMeasureItem(2)
