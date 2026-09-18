"""Geometry and hit-testing for the goldfish table. Pure -- no ``wx`` in here.

The table view is one custom-drawn canvas (the same model the deck grid and pile
views use), so every rectangle on screen is arithmetic rather than a widget. That
arithmetic is the part with the bugs in it -- where a seven-card hand fans to,
which card a click at (x, y) landed on, where a card dropped mid-drag comes to
rest -- and it is also the part that needs no display to check, so it lives here
and is tested in ``tests/test_goldfish.py`` rather than driven through a window.

Two conventions the rest of the package relies on:

* a played card's stored position is the fraction of the table its **centre**
  sits at, not its top-left corner. Tapping rotates a card about its centre, so
  anchoring anywhere else would make a card jump sideways as it taps;
* the placeable area is inset by ``GOLDFISH_CARD_SPAN`` -- the card's *long* edge
  -- in both axes, so a card at the far corner is fully on the table whichever
  way round it is.
"""

from __future__ import annotations

from dataclasses import dataclass

from utils.constants import (
    GOLDFISH_AUTO_PLACE_COLUMNS,
    GOLDFISH_CARD_HEIGHT,
    GOLDFISH_CARD_SPAN,
    GOLDFISH_CARD_WIDTH,
    GOLDFISH_HAND_MIN_STEP,
    SPACE_SM,
)


@dataclass(frozen=True)
class Box:
    """An axis-aligned rectangle in client coordinates."""

    x: int
    y: int
    width: int
    height: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


#: Height of the hand strip along the bottom edge: one card plus a ring of
#: breathing room above and below it.
HAND_STRIP_HEIGHT = GOLDFISH_CARD_HEIGHT + SPACE_SM * 2


def split_regions(width: int, height: int) -> tuple[Box, Box]:
    """Divide the canvas into ``(table, hand)``.

    The hand keeps its full height until the panel is shorter than two cards,
    after which both halves shrink together rather than the hand eating the
    table -- a tab dragged short should show less of both, not none of one.
    """
    hand_height = min(HAND_STRIP_HEIGHT, max(0, height // 2))
    return (
        Box(0, 0, width, max(0, height - hand_height)),
        Box(0, max(0, height - hand_height), width, hand_height),
    )


def hand_boxes(count: int, region: Box) -> list[Box]:
    """Where each card in hand is drawn, left to right and centred in ``region``.

    The hand fans at a full card's width while it fits and overlaps once it does
    not -- never tighter than :data:`GOLDFISH_HAND_MIN_STEP`, which keeps a
    readable sliver of every card's title showing. A hand can grow well past
    seven here (nothing stops the player drawing), so "it no longer fits" is the
    normal case rather than the edge one.
    """
    if count <= 0:
        return []
    top = region.y + (region.height - GOLDFISH_CARD_HEIGHT) // 2
    step = GOLDFISH_CARD_WIDTH + SPACE_SM
    if count > 1:
        available = region.width - SPACE_SM * 2 - GOLDFISH_CARD_WIDTH
        step = max(GOLDFISH_HAND_MIN_STEP, min(step, available // (count - 1)))
    span = step * (count - 1) + GOLDFISH_CARD_WIDTH
    left = region.x + max(SPACE_SM, (region.width - span) // 2)
    return [
        Box(left + i * step, top, GOLDFISH_CARD_WIDTH, GOLDFISH_CARD_HEIGHT) for i in range(count)
    ]


def card_size(tapped: bool) -> tuple[int, int]:
    """A card's footprint. Tapped is the same card turned ninety degrees."""
    if tapped:
        return GOLDFISH_CARD_HEIGHT, GOLDFISH_CARD_WIDTH
    return GOLDFISH_CARD_WIDTH, GOLDFISH_CARD_HEIGHT


def table_box(x: float, y: float, tapped: bool, region: Box) -> Box:
    """The rectangle a played card at fractional position ``(x, y)`` occupies."""
    centre_x, centre_y = _centre(x, y, region)
    width, height = card_size(tapped)
    return Box(centre_x - width // 2, centre_y - height // 2, width, height)


def drop_fraction(px: int, py: int, region: Box) -> tuple[float, float]:
    """The fractional position a card whose centre is dropped at ``(px, py)`` takes.

    The inverse of :func:`table_box`'s anchor, clamped to ``0..1`` by
    :class:`~services.deck_service.goldfish.GoldfishTable` rather than here --
    this reports where the pointer was, and the table decides what is on it.
    """
    span_x = max(1, region.width - GOLDFISH_CARD_SPAN)
    span_y = max(1, region.height - GOLDFISH_CARD_SPAN)
    half = GOLDFISH_CARD_SPAN // 2
    return (
        (px - region.x - half) / span_x,
        (py - region.y - half) / span_y,
    )


def auto_place_fraction(played: int) -> tuple[float, float]:
    """Where the ``played``-th click-placed card goes.

    A click (as opposed to a drag) does not say where on the table the player
    wants the card, so successive clicks walk a coarse grid instead of stacking
    every card on the same pixel. Wraps rather than running off the bottom: a
    goldfish board that deep is already overlapping.
    """
    columns = GOLDFISH_AUTO_PLACE_COLUMNS
    column = played % columns
    row = (played // columns) % columns
    denominator = max(1, columns - 1)
    return column / denominator, min(1.0, row / denominator)


def hit_test(boxes: list[Box], px: int, py: int) -> int | None:
    """Index of the topmost box under ``(px, py)``, or ``None``.

    Last drawn is topmost, so the search runs backwards -- both the hand fan and
    a crowded table overlap, and the card whose title is covered is not the one
    the player is pointing at.
    """
    for index in range(len(boxes) - 1, -1, -1):
        if boxes[index].contains(px, py):
            return index
    return None


def _centre(x: float, y: float, region: Box) -> tuple[int, int]:
    half = GOLDFISH_CARD_SPAN // 2
    span_x = max(0, region.width - GOLDFISH_CARD_SPAN)
    span_y = max(0, region.height - GOLDFISH_CARD_SPAN)
    return (
        region.x + half + int(x * span_x),
        region.y + half + int(y * span_y),
    )
