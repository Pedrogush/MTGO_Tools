"""The goldfish table: a hand along the bottom, a play area above it.

One custom-drawn :class:`wx.Panel` -- no child widgets, no scrolling -- painting
:class:`~services.deck_service.goldfish.GoldfishTable`'s state. It owns the
mouse and nothing else: every gesture is turned into a call on the table object,
which is where the state lives.

The gestures, and why each is the one it is (#1045 asks for "a field to place the
cards in that lets cards get tapped", and nothing more):

* **click a card in hand** -- put it on the table. The player who just wants to
  see the board should not have to aim.
* **drag a card from hand** -- put it on the table *there*. Which is the same
  action, with the position supplied.
* **click a card on the table** -- tap or untap it. A click, not a double-click
  or a modifier: tapping is the only thing this feature does to a played card,
  so it gets the cheapest gesture.
* **drag a card on the table** -- move it. A press that travels more than
  ``GOLDFISH_DRAG_THRESHOLD`` is a drag rather than a click, so the tap toggle
  stays reachable with an unsteady hand.
* **drag a card from the table onto the hand strip** -- take it back to hand,
  untapped. The exact inverse of the gesture that put it down, which is what
  makes the table feel like a surface rather than a one-way drop: a card that
  can be dragged out of the hand should be draggable back into it.
* **right-click a card on the table** -- the same thing without the travel, for
  a card already sitting where it belongs.

There is no rules engine behind any of it, deliberately. Tapping is a marker the
player sets and nothing in the app reads.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from services.deck_service.goldfish import GoldfishTable
from utils.constants import GOLDFISH_DRAG_THRESHOLD, SPACE_SM
from utils.constants.theme import (
    BORDER_SUBTLE,
    SELECTION_BORDER,
    SELECTION_BORDER_WIDTH,
    SURFACE_BASE,
    SURFACE_PANEL,
    TEXT_SECONDARY,
)
from widgets.panels.deck_goldfish_panel.card_art import GoldfishArtCache
from widgets.panels.deck_goldfish_panel.layout import (
    Box,
    CardMetrics,
    auto_place_fraction,
    card_metrics,
    drop_fraction,
    hand_boxes,
    hit_test,
    split_regions,
    table_box,
)
from widgets.stylize import type_font

#: Which zone a press started in.
_FROM_HAND = "hand"
_FROM_TABLE = "table"


class GoldfishTableView(wx.Panel):
    """Paints a :class:`GoldfishTable` and turns mouse gestures into calls on it."""

    def __init__(
        self,
        parent: wx.Window,
        table: GoldfishTable,
        art: GoldfishArtCache,
        on_change: Callable[[], None],
        empty_text: str,
    ) -> None:
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        self._table = table
        self._art = art
        self._on_change = on_change
        self._empty_text = empty_text
        #: How many cards have been click-placed since the last deal, so
        #: successive clicks walk the auto-placement grid instead of stacking.
        self._auto_placed = 0
        #: ``(zone, index, press point)`` while the left button is down.
        self._press: tuple[str, int, wx.Point] | None = None
        self._dragging = False
        self._drag_point: wx.Point | None = None

        self.SetBackgroundColour(wx.Colour(*SURFACE_BASE))
        # AutoBufferedPaintDC owns the whole client area, so wx must not erase
        # it first -- without this the table flickers on every drag motion.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, lambda evt: (self.Refresh(), evt.Skip()))
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_RIGHT_DOWN, self._on_right_down)
        # Capture-lost only. Not EVT_LEAVE_WINDOW: a captured drag still reports
        # leaving the window the moment the pointer crosses the panel's edge,
        # and cancelling there would make a card dropped near an edge snap back.
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, lambda _evt: self._reset_press())

    # ----- public API -----
    def refresh_table(self) -> None:
        """Repaint after the panel changed the table under us (a deal, a draw)."""
        self._auto_placed = 0
        self._reset_press()
        self._art.prefetch(list(self._table.hand))
        self.Refresh()

    def on_art_ready(self, _name: str) -> None:
        """A decode landed. Repainting the whole table is cheaper than tracking
        which rectangle changed, at this card count.

        Reached from ``wx.CallAfter`` on a decode thread, so the window may be
        gone by the time it runs -- the same liveness check the deck grid's
        image pipeline makes for the same reason.
        """
        try:
            if not self:
                return
        except RuntimeError:
            return
        self.Refresh()

    # ----- geometry -----
    def _metrics(self) -> CardMetrics:
        """The card size this panel is currently drawing at.

        Recomputed per use rather than cached on resize: it is a handful of
        integer divisions, and a stale copy would put the hit boxes somewhere
        other than the cards.
        """
        size = self.GetClientSize()
        return card_metrics(size.GetWidth(), size.GetHeight())

    def _regions(self, metrics: CardMetrics) -> tuple[Box, Box]:
        size = self.GetClientSize()
        return split_regions(size.GetWidth(), size.GetHeight(), metrics)

    def _hand_boxes(self, region: Box, metrics: CardMetrics) -> list[Box]:
        return hand_boxes(len(self._table.hand), region, metrics)

    def _table_boxes(self, region: Box, metrics: CardMetrics) -> list[Box]:
        return [table_box(c.x, c.y, c.tapped, region, metrics) for c in self._table.table]

    # ----- painting -----
    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(*SURFACE_BASE)))
        dc.Clear()
        metrics = self._metrics()
        table_region, hand_region = self._regions(metrics)

        # The hand sits on the panel surface so the two zones read as two zones
        # without a caption on either.
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.SetBrush(wx.Brush(wx.Colour(*SURFACE_PANEL)))
        dc.DrawRectangle(hand_region.x, hand_region.y, hand_region.width, hand_region.height)
        dc.SetPen(wx.Pen(wx.Colour(*BORDER_SUBTLE)))
        dc.DrawLine(hand_region.x, hand_region.y, hand_region.x + hand_region.width, hand_region.y)

        if not self._table.has_dealt:
            self._draw_prompt(dc, table_region)
            return

        for card, box in zip(self._table.table, self._table_boxes(table_region, metrics)):
            self._draw_card(dc, box, card.name, metrics, tapped=card.tapped)
        for name, box in zip(self._table.hand, self._hand_boxes(hand_region, metrics)):
            self._draw_card(dc, box, name, metrics)
        if self._dragging and self._drag_point is not None:
            self._draw_drag_ghost(dc, metrics)

    def _draw_card(
        self, dc: wx.DC, box: Box, name: str, metrics: CardMetrics, *, tapped: bool = False
    ) -> None:
        dc.DrawBitmap(self._art.bitmap(name, metrics, tapped=tapped), box.x, box.y, True)
        if tapped:
            # A rotated card is only obviously rotated next to an upright one, and
            # a board of all-tapped cards has no such neighbour. The accent frame
            # says "tapped" on its own.
            dc.SetPen(wx.Pen(wx.Colour(*SELECTION_BORDER), SELECTION_BORDER_WIDTH))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRectangle(box.x, box.y, box.width, box.height)

    def _draw_drag_ghost(self, dc: wx.DC, metrics: CardMetrics) -> None:
        assert self._press is not None and self._drag_point is not None
        zone, index, _origin = self._press
        if zone == _FROM_HAND:
            hand = self._table.hand
            if not 0 <= index < len(hand):
                return
            name, tapped = hand[index], False
        else:
            cards = self._table.table
            if not 0 <= index < len(cards):
                return
            name, tapped = cards[index].name, cards[index].tapped
        bitmap = self._art.bitmap(name, metrics, tapped=tapped)
        dc.DrawBitmap(
            bitmap,
            self._drag_point.x - bitmap.GetWidth() // 2,
            self._drag_point.y - bitmap.GetHeight() // 2,
            True,
        )

    def _draw_prompt(self, dc: wx.DC, region: Box) -> None:
        dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
        dc.SetFont(type_font("body"))
        width, height = dc.GetTextExtent(self._empty_text)
        dc.DrawText(
            self._empty_text,
            region.x + max(SPACE_SM, (region.width - width) // 2),
            region.y + max(SPACE_SM, (region.height - height) // 2),
        )

    # ----- mouse -----
    def _on_left_down(self, event: wx.MouseEvent) -> None:
        point = event.GetPosition()
        metrics = self._metrics()
        table_region, hand_region = self._regions(metrics)
        index = hit_test(self._hand_boxes(hand_region, metrics), point.x, point.y)
        if index is not None:
            self._press = (_FROM_HAND, index, point)
        else:
            index = hit_test(self._table_boxes(table_region, metrics), point.x, point.y)
            if index is None:
                return
            self._press = (_FROM_TABLE, index, point)
        if not self.HasCapture():
            self.CaptureMouse()

    def _on_motion(self, event: wx.MouseEvent) -> None:
        if self._press is None or not event.Dragging():
            return
        _zone, _index, origin = self._press
        self._drag_point = event.GetPosition()
        if not self._dragging:
            travelled = max(abs(self._drag_point.x - origin.x), abs(self._drag_point.y - origin.y))
            if travelled < GOLDFISH_DRAG_THRESHOLD:
                return
            self._dragging = True
        self.Refresh()

    def _on_left_up(self, event: wx.MouseEvent) -> None:
        press, dragging = self._press, self._dragging
        point = event.GetPosition()
        self._reset_press()
        if press is None:
            return
        zone, index, _origin = press
        metrics = self._metrics()
        table_region, _hand_region = self._regions(metrics)
        if zone == _FROM_HAND:
            if not dragging:
                x, y = auto_place_fraction(self._auto_placed)
                self._auto_placed += 1
            elif table_region.contains(point.x, point.y):
                x, y = drop_fraction(point.x, point.y, table_region, metrics)
            else:
                # Dropped back onto the hand strip: the player changed their
                # mind, and the card stays where it was.
                self.Refresh()
                return
            self._table.play(index, x, y)
        elif dragging and not table_region.contains(point.x, point.y):
            # Dragged off the table and onto the hand strip: back to hand. The
            # inverse of the drag that played it, so a card put down by mistake
            # comes back the way it went.
            self._take_back(index)
        elif dragging:
            x, y = drop_fraction(point.x, point.y, table_region, metrics)
            self._table.move(index, x, y)
        else:
            self._table.toggle_tap(index)
        self._on_change()
        self.Refresh()

    def _on_right_down(self, event: wx.MouseEvent) -> None:
        metrics = self._metrics()
        table_region, _hand_region = self._regions(metrics)
        point = event.GetPosition()
        index = hit_test(self._table_boxes(table_region, metrics), point.x, point.y)
        if index is None:
            return
        self._take_back(index)
        self._on_change()
        self.Refresh()

    def _take_back(self, index: int) -> None:
        """Return the table card at ``index`` to hand, untapped."""
        self._table.return_to_hand(index)
        # The returned card is in hand again, so the next click-placed card
        # should not skip the slot it came from.
        self._auto_placed = max(0, self._auto_placed - 1)

    def _reset_press(self) -> None:
        self._press = None
        self._dragging = False
        self._drag_point = None
        if self.HasCapture():
            self.ReleaseMouse()
