"""Pure pile-layout geometry for the deck pile view.

These are widget-free, DC-free functions over plain integers/lists so the pile
view's spatial math is unit-testable without a live ``wx`` window. ``DeckPileView``
imports them and the module-level constants below; the math is identical to the
inline methods it previously carried (issue #799).

A pile is a vertical stack: the bottom card is drawn full-height and each card
above it shows only a ``_NAME_STRIP_HEIGHT`` slice at the top. Pile x-positions
are width-independent (they depend only on the pile index), so a pure resize
never moves a card horizontally.
"""

from __future__ import annotations

from typing import Any

import wx

from utils.constants import DECK_CARD_HEIGHT, DECK_CARD_WIDTH

# Match the grid view's card size and inter-card gap so the two views feel
# visually consistent.
_CARD_WIDTH = DECK_CARD_WIDTH
_CARD_HEIGHT = DECK_CARD_HEIGHT
_NAME_STRIP_HEIGHT = 32  # visible portion of stacked-above cards
_PILE_GAP = 8  # gap between piles (matches grid view's GRID_GAP)
_PILE_PAD = 6  # padding inside a pile column
_PILE_TOP = _PILE_PAD  # top inset for the first card in a pile


def pile_height(member_count: int) -> int:
    if member_count <= 0:
        return _CARD_HEIGHT
    return _CARD_HEIGHT + (member_count - 1) * _NAME_STRIP_HEIGHT


def pile_x(pile_index: int) -> int:
    return _PILE_GAP + pile_index * (_CARD_WIDTH + _PILE_GAP)


def card_rect(pile_index: int, member_index: int, total: int) -> wx.Rect:
    x = pile_x(pile_index)
    # Bottom card sits at the bottom of the stack; cards higher in the
    # member list are visually above it (only their name strip showing).
    bottom_y = _PILE_TOP + pile_height(total) - _CARD_HEIGHT
    y = bottom_y - (total - 1 - member_index) * _NAME_STRIP_HEIGHT
    return wx.Rect(x, y, _CARD_WIDTH, _CARD_HEIGHT)


def content_size(piles: list[tuple[str, list[dict[str, Any]]]]) -> wx.Size:
    """The true content extent of ``piles`` (NOT the wx-inflated virtual size)."""
    if not piles:
        return wx.Size(100, 100)
    max_members = max(len(members) for _, members in piles)
    height = _PILE_TOP + pile_height(max_members) + _PILE_PAD * 2
    width = (_CARD_WIDTH + _PILE_GAP) * len(piles) + _PILE_GAP
    return wx.Size(width, height)


def pile_index_at(piles: list[tuple[str, list[dict[str, Any]]]], logical_x: int) -> int | None:
    if not piles:
        return None
    # Snap to nearest pile column.
    best_idx = 0
    best_dist = abs(pile_x(0) + _CARD_WIDTH // 2 - logical_x)
    for idx in range(1, len(piles)):
        d = abs(pile_x(idx) + _CARD_WIDTH // 2 - logical_x)
        if d < best_dist:
            best_idx = idx
            best_dist = d
    return best_idx
