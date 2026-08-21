"""Regression guards for hand-made pile columns (issue #991).

The pile view snapped every drop to the *nearest existing* column, so dragging
a card off the right-hand edge put it straight back where it came from. A
physical deckbuilder pushes cards into a pile of their own the moment the
automatic grouping stops matching what they are thinking about, and the view had
no way to express that.

A column made that way carries no bucket heading -- "3" / "Lands" / "Red"
describe what ``group_into_piles`` decided, and a hand-made column is whatever
the person holding the cards decided -- but it still shows its copy count, which
is the number that means the same thing either way.
"""

from __future__ import annotations

from typing import Any

import pytest
import wx

from utils.i18n import current_locale, set_current_locale, translate_plural
from widgets.panels.card_table_panel.pile_view import (
    _CARD_WIDTH,
    _PILE_GAP,
    _PILE_PAD,
    _PILE_TOP,
    VIRTUAL_PILE_LABEL,
    DeckPileView,
)
from widgets.panels.card_table_panel.sorting import PILE_SORT_TYPE

_META: dict[str, dict[str, Any]] = {
    "lightning bolt": {"mana_value": 1, "type_line": "Instant", "colors": ["R"]},
    "grizzly bears": {"mana_value": 2, "type_line": "Creature — Bear", "colors": ["G"]},
    "forest": {"mana_value": 0, "type_line": "Basic Land — Forest", "colors": []},
}

# The deck every test starts from: three mana values, so three automatic piles
# ("1", "2", "Lands") of two copies each.
_DECK = [
    {"name": "Lightning Bolt", "qty": 2},
    {"name": "Grizzly Bears", "qty": 2},
    {"name": "Forest", "qty": 2},
]


def _get_metadata(name: str) -> dict[str, Any]:
    return _META.get(name.lower(), {})


@pytest.fixture()
def english_locale():
    """Pin the ambient locale the tooltips resolve against, then restore it."""
    previous = current_locale()
    set_current_locale("en-US")
    yield
    set_current_locale(previous)


class _RecordingDC:
    """A real DC for measurement, recording every string drawn through it.

    The headings are painted into the cached canvas, not laid out as widgets, so
    what reaches the screen is a ``DrawText`` call and there is no widget state
    to interrogate instead (and per docs/WXMSW_BEHAVIOUR.md, interrogating state
    would prove nothing about the screen anyway).
    """

    def __init__(self, dc: wx.DC) -> None:
        self._dc = dc
        self.texts: list[tuple[str, int, int]] = []

    def DrawText(self, text: str, x: int, y: int) -> None:  # noqa: N802 - wx API
        self.texts.append((text, x, y))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._dc, name)


def _make_view(frame: wx.Frame, sort_mode: str | None = None) -> DeckPileView:
    kwargs: dict[str, Any] = {}
    if sort_mode is not None:
        kwargs["get_sort_mode"] = lambda: sort_mode
    return DeckPileView(
        frame,
        "main",
        _get_metadata,
        lambda _name, _size: None,
        on_select=lambda _card: None,
        on_hover=None,
        **kwargs,
    )


def _column_centre_x(view: DeckPileView, index: int) -> int:
    """Logical x of column ``index``'s centre; ``len(piles)`` is the new slot."""
    return view._pile_x(index) + _CARD_WIDTH // 2


def _drop(view: DeckPileView, uids: list[int], point: wx.Point) -> None:
    """Release a drag of ``uids`` at ``point``, as ``_on_left_up`` does."""
    view._drag_uids = list(uids)
    view._drop_at(point)
    view._drag_uids = []


def _uid_of(view: DeckPileView, pile: int, member: int) -> int:
    return view._piles[pile][1][member]["_uid"]


def _labels(view: DeckPileView) -> list[str]:
    return [label for label, _members in view._piles]


def _counts(view: DeckPileView) -> list[int]:
    return [len(members) for _label, members in view._piles]


# ---------------------------------------------------------------------------
# Making a column
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("wx_app")
def test_dropping_past_the_rightmost_pile_makes_a_new_column() -> None:
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        assert _labels(view) == ["1", "2", "Lands"]
        moved = _uid_of(view, 0, 0)

        _drop(view, [moved], wx.Point(_column_centre_x(view, 3), _PILE_TOP + 10))

        assert len(view._piles) == 4, "the drop should have opened a fourth column"
        label, members = view._piles[-1]
        assert label == VIRTUAL_PILE_LABEL
        assert [entry["_uid"] for entry in members] == [moved]
        # ...and it left the pile it came from.
        assert _counts(view) == [1, 2, 2, 1]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_a_hand_made_column_shows_its_count_and_no_heading() -> None:
    """The point of the whole feature: a count, but no claim about *why*."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        _drop(
            view,
            [_uid_of(view, 0, 0), _uid_of(view, 0, 1)],
            wx.Point(_column_centre_x(view, 3), _PILE_TOP + 10),
        )
        assert view._piles[-1][0] == VIRTUAL_PILE_LABEL

        bitmap = wx.Bitmap(800, 800)
        dc = wx.MemoryDC(bitmap)
        recorder = _RecordingDC(dc)
        try:
            # An automatic column captions itself twice: the bucket it groups
            # over the cards ("2" is the mana value), the copy count under them.
            view._draw_pile_header(recorder, 1, view._piles[1][0])
            view._draw_pile_footer(recorder, 1, len(view._piles[1][1]))
            assert [text for text, _x, _y in recorder.texts] == ["2", "2"]

            # The hand-made column draws the count and nothing above it. The
            # count sits in the same footer band, centred, as every other
            # column's -- #988's layout, not the header band it used to use.
            recorder.texts.clear()
            view._draw_pile_header(recorder, 3, view._piles[3][0])
            assert recorder.texts == [], "a hand-made column must draw no heading"

            view._draw_pile_footer(recorder, 3, len(view._piles[3][1]))
            assert len(recorder.texts) == 1, "...but it must still draw its count"
            text, x, y = recorder.texts[0]
            assert text == "2"
            footer = view._pile_footer_rect(3, len(view._piles[3][1]))
            width, height = recorder.GetTextExtent(text)
            assert x == footer.x + (footer.width - width) // 2
            assert y == footer.y + (footer.height - height) // 2
            # Below the pile, not up in the heading band it used to live in.
            assert footer.y > view._pile_header_rect(3).GetBottom()
        finally:
            dc.SelectObject(wx.NullBitmap)
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_each_drop_can_make_at_most_one_column() -> None:
    """There is one trailing slot, so a wild fling right cannot deal five piles."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        far_right = _column_centre_x(view, 3) + 40 * (_CARD_WIDTH + _PILE_GAP)

        _drop(view, [_uid_of(view, 0, 0)], wx.Point(far_right, _PILE_TOP + 10))
        assert len(view._piles) == 4

        _drop(view, [_uid_of(view, 0, 0)], wx.Point(far_right, _PILE_TOP + 10))
        assert len(view._piles) == 5
    finally:
        frame.Destroy()


# ---------------------------------------------------------------------------
# ...without breaking the drops that already worked
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("wx_app")
def test_dropping_onto_an_existing_column_still_lands_there() -> None:
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        moved = _uid_of(view, 0, 0)

        _drop(view, [moved], wx.Point(_column_centre_x(view, 2), _PILE_TOP + 10))

        assert _labels(view) == ["1", "2", "Lands"], "no column should have been added"
        assert moved in [entry["_uid"] for entry in view._piles[2][1]]
        assert _counts(view) == [1, 2, 3]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_a_drop_beside_the_last_column_still_joins_it() -> None:
    """The new slot is scored by the same nearest-centre rule as any column.

    A drop that clears the last column's edge but not the midpoint between it
    and the slot beyond joins that column -- exactly as a drop between any two
    columns has always joined the nearer one. Reaching for a *new* column is
    the same reach as moving to the next one.
    """
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        last = len(view._piles) - 1
        midpoint = (_column_centre_x(view, last) + _column_centre_x(view, last + 1)) // 2

        _drop(view, [_uid_of(view, 0, 0)], wx.Point(midpoint - 4, _PILE_TOP + 10))
        assert len(view._piles) == 3, "short of the midpoint is still the last column"

        _drop(view, [_uid_of(view, 0, 0)], wx.Point(midpoint + 4, _PILE_TOP + 10))
        assert len(view._piles) == 4, "past the midpoint is the new column"
    finally:
        frame.Destroy()


# ---------------------------------------------------------------------------
# Emptying a column, and losing one
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("wx_app")
def test_a_hand_made_column_closes_up_when_its_last_card_leaves() -> None:
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        moved = _uid_of(view, 0, 0)
        _drop(view, [moved], wx.Point(_column_centre_x(view, 3), _PILE_TOP + 10))
        assert len(view._piles) == 4

        _drop(view, [moved], wx.Point(_column_centre_x(view, 0), _PILE_TOP + 10))

        assert _labels(view) == ["1", "2", "Lands"]
        assert _counts(view) == [2, 2, 2]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_an_emptied_automatic_column_is_kept() -> None:
    """Its heading still names a real bucket of the grouping, so it stays put."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        both = [_uid_of(view, 0, 0), _uid_of(view, 0, 1)]

        _drop(view, both, wx.Point(_column_centre_x(view, 3), _PILE_TOP + 10))

        assert _labels(view) == ["1", "2", "Lands", VIRTUAL_PILE_LABEL]
        assert _counts(view) == [0, 2, 2, 2]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_regrouping_deals_the_deck_again_and_drops_hand_made_columns() -> None:
    """Choosing a new grouping asks for a fresh deal, ad-hoc columns included."""
    frame = wx.Frame(None)
    sort_mode = {"value": "mv"}
    try:
        view = _make_view(frame, sort_mode=None)
        view._get_sort_mode = lambda: sort_mode["value"]
        view.set_cards(_DECK)
        _drop(view, [_uid_of(view, 0, 0)], wx.Point(_column_centre_x(view, 3), _PILE_TOP + 10))
        assert VIRTUAL_PILE_LABEL in _labels(view)

        sort_mode["value"] = PILE_SORT_TYPE
        view.refresh_sort()

        assert VIRTUAL_PILE_LABEL not in _labels(view)
        assert _labels(view) == ["Creature", "Instant", "Land"]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_editing_the_zone_deals_the_deck_again_too() -> None:
    """``set_cards`` runs on every +/- edit; the arrangement is in-session only."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        _drop(view, [_uid_of(view, 0, 0)], wx.Point(_column_centre_x(view, 3), _PILE_TOP + 10))
        assert VIRTUAL_PILE_LABEL in _labels(view)

        view.set_cards(_DECK)

        assert _labels(view) == ["1", "2", "Lands"]
    finally:
        frame.Destroy()


# ---------------------------------------------------------------------------
# Seeing where the drop will go
# ---------------------------------------------------------------------------


def _begin_drag(view: DeckPileView, uids: list[int], logical_x: int) -> None:
    view._drag_active = True
    view._drag_uids = list(uids)
    view._drag_pos = wx.Point(logical_x, _PILE_TOP + 10)


@pytest.mark.usefixtures("wx_app")
def test_no_drop_indicator_when_nothing_is_being_dragged() -> None:
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        assert view.drop_indicator_rect() is None
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_drop_indicator_steps_off_the_last_column_onto_the_new_slot() -> None:
    """The affordance: the outline the drag follows moves onto empty canvas."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        uid = _uid_of(view, 0, 0)

        _begin_drag(view, [uid], _column_centre_x(view, 1))
        over_column = view.drop_indicator_rect()
        assert over_column is not None
        assert over_column.x == view._pile_x(1)

        _begin_drag(view, [uid], _column_centre_x(view, 3))
        over_slot = view.drop_indicator_rect()
        assert over_slot is not None
        assert over_slot.x == view._pile_x(3)
        # Past every pile there is: this is the column that does not exist yet.
        assert over_slot.x >= view._pile_x(len(view._piles) - 1) + _CARD_WIDTH
        assert over_slot.width == _CARD_WIDTH
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_view_can_scroll_to_the_new_slot_only_while_a_drag_is_running() -> None:
    """The slot is past the content, so it needs scroll range that is not there.

    Reserved for the drag and handed back after it, so a resting pile view never
    scrolls into a column-wide strip of nothing.
    """
    frame = wx.Frame(None, size=(300, 400))
    try:
        view = _make_view(frame)
        view.SetSize((300, 400))
        view.set_cards(_DECK)
        content = view.scroll_content_width()
        assert content > 300, "fixture must be wider than the viewport to scroll at all"
        assert view.GetVirtualSize().GetWidth() == content

        view._drag_active = True
        view._apply_drag_slot()
        assert view.GetVirtualSize().GetWidth() == content + _CARD_WIDTH + _PILE_GAP
        assert view.scroll_content_width() == content, "the canvas must not grow"

        view._drag_active = False
        view._apply_drag_slot()
        assert view.GetVirtualSize().GetWidth() == content
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app", "english_locale")
def test_a_hand_made_column_explains_its_count_but_not_a_grouping() -> None:
    """#988 gave both numbers a tooltip; only one of them still has anything to say.

    "Mana value -- each pile holds the cards of that mana value" describes what
    ``group_into_piles`` dealt. A column the user made by hand was not dealt by
    anything, so its heading band says nothing (it draws nothing there either).
    The count means the same on both kinds of column, so it keeps its tooltip.
    """
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        _drop(view, [_uid_of(view, 0, 0)], wx.Point(_column_centre_x(view, 3), _PILE_TOP + 10))
        assert view._piles[-1][0] == VIRTUAL_PILE_LABEL

        header = view._pile_header_rect(3)
        assert view.tooltip_at(wx.Point(header.x + header.width // 2, header.y + 2)) == ""

        # ...while an automatic column's heading still explains the grouping.
        auto = view._pile_header_rect(1)
        assert view.tooltip_at(wx.Point(auto.x + auto.width // 2, auto.y + 2)) != ""

        footer = view._pile_footer_rect(3, 1)
        tip = view.tooltip_at(wx.Point(footer.x + footer.width // 2, footer.y + footer.height // 2))
        assert tip == translate_plural("en-US", "tabs.view.pile.tooltip.count", 1)
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_drop_indicator_encloses_the_count_band_too() -> None:
    """#988 moved the count below the pile, so the outline has to reach it.

    Stopping at the last card would leave the number it captions sitting just
    outside the outline that is meant to say "the cards land in this column".
    """
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(_DECK)
        _begin_drag(view, [_uid_of(view, 0, 0)], _column_centre_x(view, 1))

        rect = view.drop_indicator_rect()
        assert rect is not None
        footer = view._pile_footer_rect(1, len(view._piles[1][1]))
        assert rect.y == _PILE_PAD, "the outline still starts at the heading band"
        assert rect.GetBottom() == footer.GetBottom()
        assert rect.Contains(footer), "the whole count band is inside the outline"
        # ...and the same on the slot that does not exist yet, sized to the
        # pile being carried.
        _begin_drag(view, [_uid_of(view, 0, 0)], _column_centre_x(view, 3))
        slot = view.drop_indicator_rect()
        assert slot is not None
        assert slot.GetBottom() == view._pile_footer_rect(3, 1).GetBottom()
    finally:
        frame.Destroy()
