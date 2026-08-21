"""F7 — the pile columns carry their bucket's heading.

``group_into_piles`` has always returned ``((order, label), members)``, and
every consumer in ``pile_view`` destructured the label as ``_label`` and threw it
away. So "five stacks with no headings, and the grouping key discoverable only
through the ``⋯`` menu" was a rendering omission on top of data that already
existed — which is exactly the shape of defect that comes back, because dropping
the label again breaks nothing else.
"""

from __future__ import annotations

from typing import Any

import pytest
import wx

from utils.i18n import current_locale, set_current_locale, translate, translate_plural
from widgets.panels.card_table_panel.pile_view import (
    _PILE_FOOTER_HEIGHT,
    _PILE_HEADER_HEIGHT,
    _PILE_PAD,
    _PILE_TOP,
    DeckPileView,
)
from widgets.panels.card_table_panel.sorting import (
    PILE_SORT_COLOR,
    PILE_SORT_MV,
    PILE_SORT_TYPE,
)

_META: dict[str, dict[str, Any]] = {
    "grizzly bears": {"mana_value": 2, "type_line": "Creature — Bear", "colors": ["G"]},
    "lightning bolt": {"mana_value": 1, "type_line": "Instant", "colors": ["R"]},
    "forest": {"mana_value": 0, "type_line": "Basic Land — Forest", "colors": []},
}


def _get_metadata(name: str) -> dict[str, Any]:
    return _META.get(name.lower(), {})


def _make_view(frame: wx.Frame, sort_mode: str = PILE_SORT_MV) -> DeckPileView:
    return DeckPileView(
        frame,
        "main",
        _get_metadata,
        lambda _name, _size: None,
        on_select=lambda _card: None,
        on_hover=None,
        get_sort_mode=lambda: sort_mode,
    )


@pytest.fixture()
def english_locale():
    """Pin the ambient locale the tooltips resolve against, then restore it."""
    previous = current_locale()
    set_current_locale("en-US")
    yield
    set_current_locale(previous)


class _RecordingDC:
    """A real DC for measurement, recording where each string is drawn.

    ``_draw_pile_header``/``_draw_pile_footer`` centre their text by computing
    the x themselves and passing it to ``DrawText`` -- there is no alignment
    flag for wxMSW to accept and ignore (docs/WXMSW_BEHAVIOUR.md), so the
    coordinate this records is the coordinate that reaches the screen.
    """

    def __init__(self, dc: wx.DC) -> None:
        self._dc = dc
        self.texts: list[tuple[str, int, int]] = []

    def DrawText(self, text: str, x: int, y: int) -> None:  # noqa: N802 - wx API
        self.texts.append((text, x, y))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._dc, name)


def _draw_and_record(view: DeckPileView) -> tuple[_RecordingDC, list[list[tuple[str, int, int]]]]:
    """Draw every pile, returning the strings each one placed, in draw order.

    Per pile that is ``[heading, count, *card names]`` -- the placeholder card
    art draws the name too, and a bucket label can equal another pile's count
    ("2" cards of mana value 1), so the records are kept per pile rather than
    keyed by their text.
    """
    bitmap = wx.Bitmap(600, 800)
    dc = wx.MemoryDC(bitmap)
    recorder = _RecordingDC(dc)
    per_pile: list[list[tuple[str, int, int]]] = []
    for index, (label, members) in enumerate(view._piles):
        before = len(recorder.texts)
        view._draw_pile(recorder, index, label, members, None)
        per_pile.append(recorder.texts[before:])
    dc.SelectObject(wx.NullBitmap)
    return recorder, per_pile


@pytest.mark.usefixtures("wx_app")
def test_every_pile_draws_its_label_and_its_copy_count() -> None:
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        labels: list[str] = []
        counts: list[int] = []
        view._draw_pile_header = lambda _dc, _idx, label: labels.append(label)
        view._draw_pile_footer = lambda _dc, _idx, count: counts.append(count)
        view.set_cards(
            [
                {"name": "Lightning Bolt", "qty": 4},
                {"name": "Grizzly Bears", "qty": 2},
                {"name": "Forest", "qty": 8},
            ]
        )
        dc = wx.MemoryDC(wx.Bitmap(400, 400))
        for index, (label, members) in enumerate(view._piles):
            view._draw_pile(dc, index, label, members, None)
        dc.SelectObject(wx.NullBitmap)

        assert labels == ["1", "2", "Lands"]
        assert counts == [4, 2, 8]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_first_card_starts_below_the_heading_band() -> None:
    """The heading needs its own space, not the top of the first card."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards([{"name": "Lightning Bolt", "qty": 1}])
        header = view._pile_header_rect(0)
        card = view._card_rect(0, 0, 1)
        assert header.height == _PILE_HEADER_HEIGHT
        assert header.y == _PILE_PAD
        assert card.y >= header.GetBottom()
        assert card.x == header.x
    finally:
        frame.Destroy()


# ---------------------------------------------------------------------------
# #988 -- the two numbers a pile column shows
# ---------------------------------------------------------------------------
# The bucket label sat flush left in the header band and the copy count flush
# right in the same band, so the pair read as two unrelated figures floating
# over the column rather than as a heading and a total. Both are centred on the
# column now, the count in its own band under the pile's last card.


@pytest.mark.usefixtures("wx_app")
def test_the_pile_label_is_centred_over_its_column() -> None:
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(
            [
                {"name": "Lightning Bolt", "qty": 4},
                {"name": "Grizzly Bears", "qty": 2},
                {"name": "Forest", "qty": 8},
            ]
        )
        recorder, per_pile = _draw_and_record(view)
        for index, (label, _members) in enumerate(view._piles):
            rect = view._pile_header_rect(index)
            text, x, _y = per_pile[index][0]
            assert text == label
            width, _height = recorder.GetTextExtent(label)
            assert x == rect.x + (rect.width - width) // 2, label
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_count_sits_under_its_own_pile_centred_whatever_the_pile_height() -> None:
    """A short pile captions itself; it does not share the tall pile's baseline."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards(
            [
                {"name": "Lightning Bolt", "qty": 2},
                {"name": "Grizzly Bears", "qty": 1},
                {"name": "Forest", "qty": 9},
            ]
        )
        counts = [len(members) for _label, members in view._piles]
        assert counts == [2, 1, 9], "fixture must give the piles different heights"

        recorder, per_pile = _draw_and_record(view)
        footer_tops: list[int] = []
        for index, (_label, members) in enumerate(view._piles):
            total = len(members)
            footer = view._pile_footer_rect(index, total)
            # Below this pile's own last card, not below the tallest column.
            last_card = view._card_rect(index, total - 1, total)
            assert footer.y >= last_card.GetBottom()
            assert footer.y == _PILE_TOP + view._pile_height(total) + _PILE_PAD
            assert footer.height == _PILE_FOOTER_HEIGHT
            assert footer.x == view._pile_header_rect(index).x

            text, x, y = per_pile[index][1]
            assert text == str(total)
            width, height = recorder.GetTextExtent(text)
            assert x == footer.x + (footer.width - width) // 2
            assert y == footer.y + (footer.height - height) // 2
            footer_tops.append(footer.y)

        # Distinct heights must produce distinct baselines -- a shared footer row
        # would collapse these to one value.
        assert len(set(footer_tops)) == 3
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_tallest_pile_s_count_fits_inside_the_scrollable_content() -> None:
    """The count band must be reachable by scrolling, not clipped off the canvas."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards([{"name": "Forest", "qty": 12}, {"name": "Lightning Bolt", "qty": 1}])
        tallest = max(len(members) for _label, members in view._piles)
        index = next(i for i, (_l, m) in enumerate(view._piles) if len(m) == tallest)
        footer = view._pile_footer_rect(index, tallest)
        assert footer.GetBottom() < view.scroll_content_height()
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app", "english_locale")
@pytest.mark.parametrize(
    "sort_mode,key",
    [
        (PILE_SORT_MV, "tabs.view.pile.tooltip.mv"),
        (PILE_SORT_COLOR, "tabs.view.pile.tooltip.color"),
        (PILE_SORT_TYPE, "tabs.view.pile.tooltip.type"),
    ],
)
def test_the_heading_explains_what_the_piles_are_grouped_by(sort_mode: str, key: str) -> None:
    frame = wx.Frame(None)
    try:
        view = _make_view(frame, sort_mode)
        view.set_cards([{"name": "Lightning Bolt", "qty": 3}])
        header = view._pile_header_rect(0)
        tip = view.tooltip_at(wx.Point(header.x + header.width // 2, header.y + 2))
        assert tip == translate("en-US", key)
        assert tip != key, "the tooltip must be a translated string, not a bare key"
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app", "english_locale")
def test_the_count_explains_that_it_counts_this_pile() -> None:
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards([{"name": "Lightning Bolt", "qty": 3}, {"name": "Ponder", "qty": 1}])
        for index, (_label, members) in enumerate(view._piles):
            footer = view._pile_footer_rect(index, len(members))
            tip = view.tooltip_at(
                wx.Point(footer.x + footer.width // 2, footer.y + footer.height // 2)
            )
            assert tip == translate_plural("en-US", "tabs.view.pile.tooltip.count", len(members))
            assert str(len(members)) in tip
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app", "english_locale")
def test_a_card_carries_no_tooltip_and_moving_onto_one_drops_the_previous() -> None:
    """The window owns one tooltip; leaving a number must clear it, not strand it."""
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        view.set_cards([{"name": "Lightning Bolt", "qty": 3}])
        header = view._pile_header_rect(0)
        view._update_tooltip(wx.Point(header.x + header.width // 2, header.y + 2))
        tip = view.GetToolTip()
        assert tip is not None and tip.GetTip() == translate("en-US", "tabs.view.pile.tooltip.mv")

        card = view._card_rect(0, 2, 3)
        assert view.tooltip_at(wx.Point(card.x + card.width // 2, card.y + card.height // 2)) == ""
        view._update_tooltip(wx.Point(card.x + card.width // 2, card.y + card.height // 2))
        assert view.GetToolTip() is None
    finally:
        frame.Destroy()
