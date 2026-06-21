"""Event handling, selection, marquee and drag-to-reorder for the grid view.

A thin view-collaborator mixin holding :class:`DeckGridView`'s interaction
layer: the raw wx mouse-event handlers, the click/selection state machine, the
rubber-band marquee glue and the drag-to-reorder gesture (including its ghost
and drop-indicator overlays, which are drawn live in ``_on_paint``).

Two contracts are easy to break and are preserved verbatim here:

* the ``_suppress_set_selected`` echo-guard around ``_notify_selection`` — the
  panel echoes our reported selection straight back via ``set_selected``, and a
  bare name can't represent a multi-card marquee set, so the echo is suppressed
  while we broadcast.
* the marquee multi-select round-trip — ``_marquee_select`` unions hits into the
  snapshot ``_marquee_base`` and reports one card / None exactly as the pile
  view does.
"""

from __future__ import annotations

from typing import Any

import wx

from utils.constants import (
    DARK_ACCENT,
    DECK_CARD_BADGE_PADDING,
    DECK_CARD_BASE_FONT_SIZE,
    LIGHT_TEXT,
)
from widgets.panels.card_table_panel.grid_layout import (
    _CARD_HEIGHT,
    _CARD_WIDTH,
    _CELL_HEIGHT,
    _CELL_WIDTH,
)
from widgets.panels.card_table_panel.marquee import RUBBER_AUTOSCROLL_PX
from widgets.panels.card_table_panel.scrolling import scroll_by_wheel


class GridInteractionMixin:
    """Mouse events, selection, marquee and drag-to-reorder for the grid view."""

    def _shows_actions(self, name: str) -> bool:
        lower = name.lower()
        if self._hover_name is not None and lower == self._hover_name.lower():
            return True
        # Only show the inline +/−/× on a lone selection; a marquee multi-select
        # shouldn't plaster controls across every chosen card.
        return len(self._selected_names) == 1 and name in self._selected_names

    # ----- event handlers -----
    def _on_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        old_cols = self._cols
        self._recompute_layout()
        if self._cols != old_cols:
            self.Refresh()

    def _on_left_down(self, event: wx.MouseEvent) -> None:
        point = self._to_logical(event.GetPosition())
        idx = self._hit_test(point)
        if idx is None:
            # Empty space: start a rubber-band selection (clear unless Shift).
            self._marquee.begin(event.GetPosition(), additive=event.ShiftDown())
            return
        card = self._cards[idx]
        name = card["name"]
        rect = self._card_rect(idx)

        if self._shows_actions(name):
            for slot, button_rect in enumerate(self._action_button_rects(rect)):
                if button_rect.Contains(point):
                    self._pressed = (name, slot)
                    self.Refresh()
                    self._fire_action(name, slot)
                    return

        if event.ShiftDown() or event.ControlDown():
            # Toggle this card's membership in the multi-selection.
            if name in self._selected_names:
                self._selected_names.discard(name)
            else:
                self._selected_names.add(name)
            self._notify_selection_for_set()
        elif self._selected_names == {name}:
            # Second click on the only selected card clears the selection and
            # does not start a drag.
            self._selected_names = set()
            self._notify_selection(None)
            self.Refresh()
            return
        elif name not in self._selected_names:
            self._selected_names = {name}
            self._notify_selection(card)

        # Prime a potential drag-to-reorder; it only begins once the pointer
        # moves past the threshold in _on_motion. Names are taken in visual
        # (grid) order so a multi-card drag keeps its relative arrangement.
        self._drag_press = point
        self._drag_names = self._names_in_visual_order(self._selected_names)
        if not self.HasCapture():
            self.CaptureMouse()
        self.Refresh()

    def begin_marquee_at_screen(self, screen_point: wx.Point, *, additive: bool = False) -> None:
        """Start a marquee from anywhere in the app (e.g. the frame background)."""
        self._marquee.begin_at_screen(screen_point, additive=additive)

    def _notify_selection(self, card: dict[str, Any] | None) -> None:
        """Report selection to the panel, guarding the set_selected echo."""
        self._suppress_set_selected = True
        try:
            self._on_select(card)
        finally:
            self._suppress_set_selected = False

    def _fire_action(self, name: str, slot: int) -> None:
        if slot == 0 and self._on_delta:
            self._on_delta(name, 1)
        elif slot == 1 and self._on_delta:
            self._on_delta(name, -1)
        elif slot == 2 and self._on_remove:
            self._on_remove(name)

    def _on_left_up(self, event: wx.MouseEvent) -> None:
        if self._marquee.active:
            self._marquee.finish()
            return
        if self.HasCapture():
            self.ReleaseMouse()
        if self._drag_active:
            # A drop over the other zone's pane moves the cards there; otherwise
            # it's a within-zone reorder.
            transferred = False
            if self._on_zone_transfer is not None:
                transferred = self._on_zone_transfer(
                    self._drag_names, self.ClientToScreen(event.GetPosition())
                )
            if not transferred:
                self._perform_drop(self._to_logical(event.GetPosition()))
            self._reset_drag()
            self.Refresh()
            return
        self._drag_press = None
        self._drag_names = []
        if self._pressed is not None:
            self._pressed = None
            self.Refresh()

    def _on_capture_lost(self, _event: wx.MouseCaptureLostEvent) -> None:
        self._marquee.cancel()
        self._reset_drag()
        self.Refresh()

    def _reset_drag(self) -> None:
        self._drag_press = None
        self._drag_active = False
        self._drag_names = []
        self._drag_pos = None
        self._drop_index = None

    def _on_motion(self, event: wx.MouseEvent) -> None:
        if self._marquee.active:
            self._marquee.update(event.GetPosition())
            return
        point = self._to_logical(event.GetPosition())

        if self._drag_press is not None and event.LeftIsDown():
            dx = abs(point.x - self._drag_press.x)
            dy = abs(point.y - self._drag_press.y)
            if not self._drag_active and (dx > 4 or dy > 4):
                self._drag_active = True
            if self._drag_active:
                self._drag_pos = point
                self._drop_index = self._drop_index_at(point)
                self.Refresh()
            return

        idx = self._hit_test(point)
        hovered = self._cards[idx]["name"] if idx is not None else None
        if hovered == self._hover_name:
            return
        self._hover_name = hovered
        if hovered and self._on_hover and idx is not None:
            self._on_hover(self._cards[idx])
        self.Refresh()

    def _on_wheel(self, event: wx.MouseEvent) -> None:
        # Shared with the pile view so both scroll identically (see scrolling.py).
        scroll_by_wheel(self, event)

    def _on_leave(self, _event: wx.MouseEvent) -> None:
        if self._hover_name is not None:
            self._hover_name = None
            self.Refresh()

    # ----- rubber-band marquee -----
    def _marquee_begin(self, additive: bool) -> None:
        if not additive and self._selected_names:
            self._selected_names = set()
            self._notify_selection(None)
        # Snapshot the (post-clear) selection so additive hits union into it.
        self._marquee_base = set(self._selected_names)
        # Hover controls would otherwise linger over the card the press started on.
        self._hover_name = None
        self.Refresh()

    def _marquee_select(self, rect: wx.Rect) -> None:
        chosen: set[str] = set(self._marquee_base or ())
        for idx, card in enumerate(self._cards):
            if rect.Intersects(self._card_rect(idx)):
                chosen.add(card["name"])
        if chosen != self._selected_names:
            self._selected_names = chosen
            # One card chosen reports that card; several (or none) report None so
            # the inspector falls back to hover, mirroring the pile view.
            if len(chosen) == 1:
                self._notify_selection(self._card_for(next(iter(chosen))))
            else:
                self._notify_selection(None)
            self.Refresh()

    def _marquee_finish(self) -> None:
        self._marquee_base = None
        self.Refresh()

    def _card_for(self, name: str) -> dict[str, Any] | None:
        for card in self._cards:
            if card["name"] == name:
                return card
        return None

    def _notify_selection_for_set(self) -> None:
        """Report a multi-selection: a lone card is forwarded, a set reports None
        so the inspector falls back to hover (mirrors the marquee path)."""
        if len(self._selected_names) == 1:
            self._notify_selection(self._card_for(next(iter(self._selected_names))))
        else:
            self._notify_selection(None)

    # ----- drag-to-reorder -----
    def _names_in_visual_order(self, names: set[str]) -> list[str]:
        """Return ``names`` in left-to-right, top-to-bottom grid order."""
        return [card["name"] for card in self._cards if card["name"] in names]

    def _perform_drop(self, point: wx.Point) -> None:
        """Move the dragged card cells to the insertion point.

        A pure visual rearrangement of ``self._cards`` — zone quantities are
        untouched, so nothing is reported upward. The new order persists until
        the next set_cards (a deck edit or reload re-sorts the zone).
        """
        if not self._drag_names:
            return
        insert_idx = self._drop_index if self._drop_index is not None else len(self._cards)
        dragged = set(self._drag_names)
        # Count how many dragged cells precede the insertion point so the index
        # stays correct once those cells are pulled out of the list.
        before = sum(1 for card in self._cards[:insert_idx] if card["name"] in dragged)
        insert_idx -= before
        moved = [card for card in self._cards if card["name"] in dragged]
        if not moved:
            return
        # Preserve the dragged cards' visual order.
        order = {name: i for i, name in enumerate(self._drag_names)}
        moved.sort(key=lambda c: order.get(c["name"], 0))
        kept = [card for card in self._cards if card["name"] not in dragged]
        insert_idx = max(0, min(len(kept), insert_idx))
        self._cards = kept[:insert_idx] + moved + kept[insert_idx:]
        self._manual_overrides = True
        self._recompute_layout()

    def _draw_drag_ghost(self, dc: wx.DC) -> None:
        """Render the dragged card near the cursor, with a count for multi-drag."""
        if not self._drag_pos or not self._drag_names:
            return
        name = self._drag_names[0]
        rect = wx.Rect(self._drag_pos.x + 8, self._drag_pos.y + 8, _CARD_WIDTH, _CARD_HEIGHT)
        bitmap = self._image_cache.get(name)
        if bitmap is not None:
            dc.DrawBitmap(bitmap, rect.x, rect.y, True)
        else:
            dc.DrawBitmap(self._template_for(name), rect.x, rect.y, True)
        if len(self._drag_names) > 1:
            badge = f"×{len(self._drag_names)}"
            dc.SetFont(
                wx.Font(
                    DECK_CARD_BASE_FONT_SIZE,
                    wx.FONTFAMILY_SWISS,
                    wx.FONTSTYLE_NORMAL,
                    wx.FONTWEIGHT_BOLD,
                )
            )
            tw, th = dc.GetTextExtent(badge)
            pad = DECK_CARD_BADGE_PADDING
            bx = rect.x + rect.width - tw - pad * 3
            by = rect.y + pad
            dc.SetBrush(wx.Brush(wx.Colour(*DARK_ACCENT)))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(bx, by, tw + pad * 2, th + pad)
            dc.SetTextForeground(wx.Colour(*LIGHT_TEXT))
            dc.DrawText(badge, bx + pad, by + pad // 2)

    def _draw_drop_indicator(self, dc: wx.DC) -> None:
        """Draw an insertion bar at the gap the drop would land in."""
        if self._drop_index is None or not self._cards:
            return
        cols = max(1, self._cols)
        idx = self._drop_index
        row, col = divmod(idx, cols)
        # An insertion past the last cell of the final row has no next row to
        # wrap into; render it at the right edge of that last cell instead.
        if idx == len(self._cards) and col == 0 and idx > 0:
            row, col = divmod(idx - 1, cols)
            col += 1
        x = col * _CELL_WIDTH
        y = row * _CELL_HEIGHT
        dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), 3))
        dc.DrawLine(x, y, x, y + _CARD_HEIGHT)

    def _autoscroll_towards(self, client_pos: wx.Point) -> None:
        """Scroll one step toward any viewport edge the pointer is held beyond."""
        client_h = self.GetClientSize().GetHeight()
        view_x, view_y = self.GetViewStart()
        new_y = view_y
        if client_pos.y < 0:
            new_y = max(0, view_y - RUBBER_AUTOSCROLL_PX)
        elif client_pos.y > client_h:
            new_y = view_y + RUBBER_AUTOSCROLL_PX
        if new_y != view_y:
            # Scroll clamps to the virtual bounds, so overshoot is harmless.
            self.Scroll(view_x, new_y)
