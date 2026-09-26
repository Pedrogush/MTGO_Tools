"""Geometry and hit-testing for the goldfish table. Pure -- no ``wx`` in here.

The table view is one custom-drawn canvas (the same model the deck grid and pile
views use), so every rectangle on screen is arithmetic rather than a widget. That
arithmetic is the part with the bugs in it -- where a seven-card hand fans to,
which card a click at (x, y) landed on, where a card dropped mid-drag comes to
rest -- and it is also the part that needs no display to check, so it lives here
and is tested in ``tests/test_goldfish.py`` rather than driven through a window.

Three conventions the rest of the package relies on:

* **the card is measured from the panel, not fixed.** :func:`card_metrics` picks
  a width such that a full opening hand spans the tab edge to edge, and derives
  the height from :data:`GOLDFISH_CARD_ASPECT` alone -- width is chosen, height
  follows, so no arithmetic in here can stretch a card. Everything else takes
  the resulting :class:`CardMetrics` rather than reading a constant, which is
  what makes the whole surface resize;
* a played card's stored position is the fraction of the table its **centre**
  sits at, not its top-left corner. Tapping rotates a card about its centre, so
  anchoring anywhere else would make a card jump sideways as it taps;
* the placeable area is inset by ``metrics.span`` -- the card's *long* edge -- in
  both axes, so a card at the far corner is fully on the table whichever way
  round it is.
"""

from __future__ import annotations

from dataclasses import dataclass

from utils.constants import (
    GOLDFISH_AUTO_PLACE_COLUMNS,
    GOLDFISH_CARD_ASPECT,
    GOLDFISH_CARD_MAX_WIDTH,
    GOLDFISH_CARD_MIN_WIDTH,
    GOLDFISH_HAND_HEIGHT_PCT,
    GOLDFISH_HAND_MIN_STEP,
    GOLDFISH_HAND_REFERENCE,
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


@dataclass(frozen=True)
class CardMetrics:
    """How big a card is on a panel of a given size, and how tall its strip is.

    ``height`` is always ``width`` times the real card's aspect -- never rounded
    to some convenient number and never computed from the space left over -- so
    the art scaled into it is never squashed.
    """

    width: int
    height: int

    @property
    def span(self) -> int:
        """The card's long edge: the square both orientations fit inside."""
        return max(self.width, self.height)

    @property
    def strip_height(self) -> int:
        """The hand strip: one card plus a ring of breathing room."""
        return self.height + SPACE_SM * 2


def card_metrics(width: int, height: int) -> CardMetrics:
    """The card size for a panel of ``width`` x ``height`` pixels.

    Sized from the width first: :data:`GOLDFISH_HAND_REFERENCE` cards across the
    panel with nothing to spare, so an opening hand reaches both edges instead of
    floating as a small fan with unresolved space either side of it. The height
    only ever shrinks that -- the hand strip is capped at
    :data:`GOLDFISH_HAND_HEIGHT_PCT`% of the panel, because the table is what the
    tab is for and the hand is the smaller half of it.

    Clamped at both ends: a tab dragged narrow shows small cards rather than
    illegible ones, and a maximised window shows a readable card rather than a
    poster.
    """
    from_width = max(0, width) // GOLDFISH_HAND_REFERENCE
    strip = max(0, height) * GOLDFISH_HAND_HEIGHT_PCT // 100 - SPACE_SM * 2
    from_height = int(max(0, strip) / GOLDFISH_CARD_ASPECT)
    card_width = min(from_width, from_height)
    card_width = max(GOLDFISH_CARD_MIN_WIDTH, min(GOLDFISH_CARD_MAX_WIDTH, card_width))
    return CardMetrics(card_width, round(card_width * GOLDFISH_CARD_ASPECT))


def split_regions(width: int, height: int, metrics: CardMetrics) -> tuple[Box, Box]:
    """Divide the canvas into ``(table, hand)``.

    The hand keeps its full height until the panel is shorter than two cards,
    after which both halves shrink together rather than the hand eating the
    table -- a tab dragged short should show less of both, not none of one.
    """
    hand_height = min(metrics.strip_height, max(0, height // 2))
    return (
        Box(0, 0, width, max(0, height - hand_height)),
        Box(0, max(0, height - hand_height), width, hand_height),
    )


def hand_boxes(count: int, region: Box, metrics: CardMetrics) -> list[Box]:
    """Where each card in hand is drawn, spanning ``region`` edge to edge.

    The fan always reaches both sides of the strip: the first card's left edge is
    the region's, the last card's right edge is too. What varies is the step
    between them -- cards touch at :data:`GOLDFISH_HAND_REFERENCE`, separate
    below it and overlap above it, never tighter than
    :data:`GOLDFISH_HAND_MIN_STEP`, which keeps a readable sliver of every card's
    title showing. A hand can grow well past seven here (nothing stops the player
    drawing), so overlapping is the normal case rather than the edge one.

    A single card is the exception: there is no fan to span, so it is centred.
    """
    if count <= 0:
        return []
    top = region.y + (region.height - metrics.height) // 2
    if count == 1:
        left = region.x + max(0, (region.width - metrics.width) // 2)
        return [Box(left, top, metrics.width, metrics.height)]
    step = (region.width - metrics.width) / (count - 1)
    if step >= GOLDFISH_HAND_MIN_STEP:
        # Positions are rounded off the float step rather than walked in whole
        # pixels: an integer step drops its remainder, and the remainder is
        # exactly the gap that would be left at the right-hand edge.
        left = region.x
    else:
        step = float(GOLDFISH_HAND_MIN_STEP)
        span = step * (count - 1) + metrics.width
        left = region.x + max(0, int(region.width - span) // 2)
    return [Box(left + round(i * step), top, metrics.width, metrics.height) for i in range(count)]


def card_size(tapped: bool, metrics: CardMetrics) -> tuple[int, int]:
    """A card's footprint. Tapped is the same card turned ninety degrees."""
    if tapped:
        return metrics.height, metrics.width
    return metrics.width, metrics.height


def table_box(x: float, y: float, tapped: bool, region: Box, metrics: CardMetrics) -> Box:
    """The rectangle a played card at fractional position ``(x, y)`` occupies."""
    centre_x, centre_y = _centre(x, y, region, metrics)
    width, height = card_size(tapped, metrics)
    return Box(centre_x - width // 2, centre_y - height // 2, width, height)


def drop_fraction(px: int, py: int, region: Box, metrics: CardMetrics) -> tuple[float, float]:
    """The fractional position a card whose centre is dropped at ``(px, py)`` takes.

    The inverse of :func:`table_box`'s anchor, clamped to ``0..1`` by
    :class:`~services.deck_service.goldfish.GoldfishTable` rather than here --
    this reports where the pointer was, and the table decides what is on it.
    """
    span_x = max(1, region.width - metrics.span)
    span_y = max(1, region.height - metrics.span)
    half = metrics.span // 2
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


def _centre(x: float, y: float, region: Box, metrics: CardMetrics) -> tuple[int, int]:
    half = metrics.span // 2
    span_x = max(0, region.width - metrics.span)
    span_y = max(0, region.height - metrics.span)
    return (
        region.x + half + int(x * span_x),
        region.y + half + int(y * span_y),
    )
