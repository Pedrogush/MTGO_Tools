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

from widgets.panels.card_table_panel.pile_view import (
    _PILE_HEADER_HEIGHT,
    _PILE_PAD,
    DeckPileView,
)

_META: dict[str, dict[str, Any]] = {
    "grizzly bears": {"mana_value": 2, "type_line": "Creature — Bear", "colors": ["G"]},
    "lightning bolt": {"mana_value": 1, "type_line": "Instant", "colors": ["R"]},
    "forest": {"mana_value": 0, "type_line": "Basic Land — Forest", "colors": []},
}


def _get_metadata(name: str) -> dict[str, Any]:
    return _META.get(name.lower(), {})


def _make_view(frame: wx.Frame) -> DeckPileView:
    return DeckPileView(
        frame,
        "main",
        _get_metadata,
        lambda _name, _size: None,
        on_select=lambda _card: None,
        on_hover=None,
    )


@pytest.mark.usefixtures("wx_app")
def test_every_pile_draws_its_label_and_its_copy_count() -> None:
    frame = wx.Frame(None)
    try:
        view = _make_view(frame)
        drawn: list[tuple[str, int]] = []
        view._draw_pile_header = lambda _dc, _idx, label, count: drawn.append((label, count))
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

        assert drawn == [("1", 4), ("2", 2), ("Lands", 8)]
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
