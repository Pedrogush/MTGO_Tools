"""Pile view for CardTablePanel.

A custom-drawn panel that lays cards out as physical piles. Each pile is a
vertical stack of cards, with the bottom card fully rendered and the rest
shown as a thin slice at the top so the card name is visible.

Behaviour required by issue #440:

* Auto-sort piles by lands/nonlands then mana value (default), plus optional
  modes (color, type).
* Click a card to select it. Click an already-selected card to clear the
  selection.
* Rectangle multi-select: press-drag on the empty background draws a
  selection rectangle; cards intersected by the rectangle are selected.
* Drag-and-drop one or more selected cards into another pile; the dropped
  stack is inserted at the position closest to where the mouse was released.
* Hover behaves like the other views — when no card is selected or when more
  than one card is selected, hovering forwards the card under the mouse.

The pile view operates on a per-copy basis (4 Llanowar Elves becomes four
draggable items). Drag-drop only rearranges within the visual view; it does
not modify the underlying zone composition.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Thread
from typing import Any

import wx
from PIL import Image as PilImage

from utils.constants import (
    DARK_ACCENT,
    DARK_ALT,
    DARK_BG,
    DARK_PANEL,
    DECK_CARD_HEIGHT,
    DECK_CARD_WIDTH,
    LIGHT_TEXT,
    SUBDUED_TEXT,
)
from widgets.panels.card_table_panel.sorting import (
    PILE_SORT_MV,
    group_into_piles,
)

# Match the grid view's card size and inter-card gap so the two views feel
# visually consistent.
_CARD_WIDTH = DECK_CARD_WIDTH
_CARD_HEIGHT = DECK_CARD_HEIGHT
_NAME_STRIP_HEIGHT = 32  # visible portion of stacked-above cards
_PILE_GAP = 8  # gap between piles (matches grid view's GRID_GAP)
_PILE_TOP = 26  # space for pile header label
_PILE_PAD = 6  # padding inside a pile column


class _ImageCache:
    """Tiny LRU-ish cache of scaled card-image bitmaps keyed by name."""

    def __init__(self, max_entries: int = 256) -> None:
        self._cache: dict[str, wx.Bitmap | None] = {}
        self._max_entries = max_entries

    def get(self, name: str) -> wx.Bitmap | None:
        return self._cache.get(name)

    def has(self, name: str) -> bool:
        return name in self._cache

    def put(self, name: str, bitmap: wx.Bitmap | None) -> None:
        if len(self._cache) >= self._max_entries:
            # Drop an arbitrary entry — pile contents change infrequently.
            self._cache.pop(next(iter(self._cache)))
        self._cache[name] = bitmap


class DeckPileView(wx.ScrolledWindow):
    """A scrolled, custom-drawn pile view of the deck's cards."""

    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        get_metadata: Callable[[str], Any],
        get_card_image: Callable[[str, str], Path | None],
        on_select: Callable[[dict[str, Any] | None], None],
        on_hover: Callable[[dict[str, Any]], None] | None,
        get_sort_mode: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(parent, style=wx.HSCROLL | wx.VSCROLL)
        self.zone = zone
        self._get_metadata = get_metadata
        self._get_card_image = get_card_image
        self._on_select = on_select
        self._on_hover = on_hover
        self._get_sort_mode = get_sort_mode or (lambda: PILE_SORT_MV)

        self._cards: list[dict[str, Any]] = []
        # piles is a list of (label, [card_entries...]) — card_entries are
        # per-copy dicts ({"name", "qty": 1, "_uid"}). Selection/drag tracks
        # _uid so individual copies survive a re-sort.
        self._piles: list[tuple[str, list[dict[str, Any]]]] = []
        self._selected_uids: set[int] = set()
        self._hover_uid: int | None = None
        self._manual_overrides: bool = False

        # Rectangle selection state.
        self._rubber_start: wx.Point | None = None
        self._rubber_end: wx.Point | None = None

        # Drag state.
        self._drag_active = False
        self._drag_press: wx.Point | None = None
        self._drag_uids: list[int] = []
        self._drag_pos: wx.Point | None = None

        self._image_cache = _ImageCache()
        self._image_gen = 0

        self.SetBackgroundColour(DARK_PANEL)
        # AutoBufferedPaintDC requires the window to use BG_STYLE_PAINT so
        # wx skips its own erase-background draw and the custom _on_paint owns
        # the whole client area.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetScrollRate(20, 20)
        self.SetDoubleBuffered(True)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)

    # ----- public API consumed by CardTablePanel -----
    def set_cards(self, cards: list[dict[str, Any]]) -> None:
        self._cards = list(cards)
        self._manual_overrides = False
        self._rebuild_piles()

    def refresh_sort(self) -> None:
        """Called when the user changes the pile sort mode."""
        self._manual_overrides = False
        self._rebuild_piles()

    def set_selected(self, name: str | None) -> None:
        """Adopt a single-name selection from another view.

        We pick the first copy of ``name`` we find so the pile view shows the
        same card as the grid/table views.
        """
        self._selected_uids.clear()
        if name:
            for _label, members in self._piles:
                for entry in members:
                    if entry["name"].lower() == name.lower():
                        self._selected_uids.add(entry["_uid"])
                        break
                if self._selected_uids:
                    break
        self.Refresh()

    def get_selected_name(self) -> str | None:
        if len(self._selected_uids) != 1:
            return None
        target = next(iter(self._selected_uids))
        for _label, members in self._piles:
            for entry in members:
                if entry["_uid"] == target:
                    return entry["name"]
        return None

    # ----- pile layout -----
    def _rebuild_piles(self) -> None:
        grouped = group_into_piles(self._cards, self._get_metadata, self._get_sort_mode())
        self._piles = [(label, members) for (_order, label), members in grouped]
        self._selected_uids.clear()
        self._hover_uid = None
        self._update_virtual_size()
        self._prefetch_images()
        self.Refresh()

    def _pile_height(self, member_count: int) -> int:
        if member_count <= 0:
            return _CARD_HEIGHT
        return _CARD_HEIGHT + (member_count - 1) * _NAME_STRIP_HEIGHT

    def _update_virtual_size(self) -> None:
        if not self._piles:
            self.SetVirtualSize((100, 100))
            return
        max_members = max(len(members) for _, members in self._piles)
        height = _PILE_TOP + self._pile_height(max_members) + _PILE_PAD * 2
        width = (_CARD_WIDTH + _PILE_GAP) * len(self._piles) + _PILE_GAP
        self.SetVirtualSize((width, height))

    def _pile_x(self, pile_index: int) -> int:
        return _PILE_GAP + pile_index * (_CARD_WIDTH + _PILE_GAP)

    def _card_rect(self, pile_index: int, member_index: int, total: int) -> wx.Rect:
        x = self._pile_x(pile_index)
        # Bottom card sits at the bottom of the stack; cards higher in the
        # member list are visually above it (only their name strip showing).
        bottom_y = _PILE_TOP + self._pile_height(total) - _CARD_HEIGHT
        y = bottom_y - (total - 1 - member_index) * _NAME_STRIP_HEIGHT
        return wx.Rect(x, y, _CARD_WIDTH, _CARD_HEIGHT)

    def _hit_test(self, point: wx.Point) -> tuple[int, int, dict[str, Any]] | None:
        """Return (pile_index, member_index, entry) for the topmost card at point."""
        for pile_idx, (_label, members) in enumerate(self._piles):
            total = len(members)
            # Iterate from top of stack down so overlapping cards resolve correctly.
            for member_idx in range(total - 1, -1, -1):
                rect = self._card_rect(pile_idx, member_idx, total)
                # Only the visible portion of stacked-above cards is clickable.
                if member_idx < total - 1:
                    rect = wx.Rect(rect.x, rect.y, rect.width, _NAME_STRIP_HEIGHT)
                if rect.Contains(point):
                    return pile_idx, member_idx, members[member_idx]
        return None

    def _to_logical(self, screen_point: wx.Point) -> wx.Point:
        x, y = self.CalcUnscrolledPosition(screen_point)
        return wx.Point(x, y)

    # ----- image loading -----
    def _prefetch_images(self) -> None:
        seen: set[str] = set()
        for _label, members in self._piles:
            for entry in members:
                name = entry["name"]
                if name in seen or self._image_cache.has(name):
                    continue
                seen.add(name)
                self._image_cache.put(name, None)  # mark as loading
                self._image_gen += 1
                gen = self._image_gen
                Thread(target=self._image_worker, args=(gen, name), daemon=True).start()

    def _image_worker(self, gen: int, name: str) -> None:
        try:
            path = self._get_card_image(name, "normal")
            if not path or not path.exists():
                wx.CallAfter(self._image_loaded, name, None)
                return
            img = PilImage.open(str(path)).convert("RGB")
            w, h = img.size
            scale = min(_CARD_WIDTH / w, _CARD_HEIGHT / h)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), PilImage.LANCZOS)
            wx.CallAfter(self._image_loaded, name, img)
        except Exception:
            wx.CallAfter(self._image_loaded, name, None)

    def _image_loaded(self, name: str, pil_img: PilImage.Image | None) -> None:
        try:
            if not self:
                return
        except RuntimeError:
            return
        if pil_img is None:
            self._image_cache.put(name, None)
        else:
            w, h = pil_img.size
            wx_img = wx.Image(w, h)
            wx_img.SetData(pil_img.tobytes())
            self._image_cache.put(name, wx_img.ConvertToBitmap())
        self.Refresh()

    # ----- paint -----
    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        self.PrepareDC(dc)
        dc.SetBackground(wx.Brush(wx.Colour(*DARK_PANEL)))
        dc.Clear()

        for pile_idx, (label, members) in enumerate(self._piles):
            self._draw_pile(dc, pile_idx, label, members)

        if self._rubber_start and self._rubber_end:
            self._draw_rubber_band(dc)

        if self._drag_active and self._drag_pos:
            self._draw_drag_ghost(dc)

    def _draw_pile(
        self,
        dc: wx.DC,
        pile_idx: int,
        label: str,
        members: list[dict[str, Any]],
    ) -> None:
        x = self._pile_x(pile_idx)
        # Pile header label
        dc.SetTextForeground(wx.Colour(*SUBDUED_TEXT))
        dc.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        dc.DrawText(f"{label} ({len(members)})", x, _PILE_PAD)

        total = len(members)
        for member_idx, entry in enumerate(members):
            rect = self._card_rect(pile_idx, member_idx, total)
            is_bottom = member_idx == total - 1
            self._draw_card(dc, rect, entry, is_bottom)

    def _draw_card(
        self,
        dc: wx.DC,
        rect: wx.Rect,
        entry: dict[str, Any],
        is_bottom: bool,
    ) -> None:
        name = entry["name"]
        is_selected = entry["_uid"] in self._selected_uids
        is_hover = entry["_uid"] == self._hover_uid

        bitmap = self._image_cache.get(name)
        if is_bottom:
            if bitmap is not None:
                x = rect.x + (rect.width - bitmap.GetWidth()) // 2
                y = rect.y + (rect.height - bitmap.GetHeight()) // 2
                dc.DrawBitmap(bitmap, x, y, True)
            else:
                # Placeholder + name fallback while the image loads.
                dc.SetBrush(wx.Brush(wx.Colour(*DARK_ALT)))
                dc.SetPen(wx.Pen(wx.Colour(*DARK_BG), 1))
                dc.DrawRectangle(rect.x, rect.y, rect.width, rect.height)
                dc.SetTextForeground(wx.Colour(*LIGHT_TEXT))
                dc.SetFont(
                    wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
                )
                text = self._fit_text(dc, name, rect.width - 8)
                dc.DrawText(text, rect.x + 4, rect.y + 8)
        else:
            # Only the top strip of stacked-above cards is visible — draw the
            # full bitmap clipped to that strip so the actual card top (name +
            # mana cost in MTG card layout) shows through.
            strip = wx.Rect(rect.x, rect.y, rect.width, _NAME_STRIP_HEIGHT)
            if bitmap is not None:
                x = rect.x + (rect.width - bitmap.GetWidth()) // 2
                y = rect.y + (rect.height - bitmap.GetHeight()) // 2
                dc.SetClippingRegion(strip)
                dc.DrawBitmap(bitmap, x, y, True)
                dc.DestroyClippingRegion()
                dc.SetBrush(wx.TRANSPARENT_BRUSH)
                dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), 1))
                dc.DrawRectangle(strip)
            else:
                dc.SetBrush(wx.Brush(wx.Colour(*DARK_BG)))
                dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), 1))
                dc.DrawRectangle(strip)
                dc.SetTextForeground(wx.Colour(*LIGHT_TEXT))
                dc.SetFont(
                    wx.Font(8, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
                )
                text = self._fit_text(dc, name, rect.width - 6)
                dc.DrawText(text, strip.x + 3, strip.y + 4)

        # Highlight selection / hover.
        if is_selected:
            dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), 3))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRectangle(rect)
        elif is_hover:
            dc.SetPen(wx.Pen(wx.Colour(*SUBDUED_TEXT), 1, wx.PENSTYLE_DOT))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRectangle(rect)

    @staticmethod
    def _fit_text(dc: wx.DC, text: str, max_width: int) -> str:
        width, _ = dc.GetTextExtent(text)
        if width <= max_width:
            return text
        ellipsis = "…"
        while text and dc.GetTextExtent(text + ellipsis)[0] > max_width:
            text = text[:-1]
        return (text + ellipsis) if text else ""

    def _draw_rubber_band(self, dc: wx.DC) -> None:
        if not (self._rubber_start and self._rubber_end):
            return
        rect = wx.Rect(self._rubber_start, self._rubber_end)
        rect = rect.Normalize() if hasattr(rect, "Normalize") else rect
        dc.SetBrush(wx.Brush(wx.Colour(*DARK_ACCENT, 60)))
        dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), 1, wx.PENSTYLE_SHORT_DASH))
        dc.DrawRectangle(rect)

    def _draw_drag_ghost(self, dc: wx.DC) -> None:
        if not self._drag_pos:
            return
        offset = 0
        for uid in self._drag_uids:
            entry = self._find_entry(uid)
            if entry is None:
                continue
            bitmap = self._image_cache.get(entry["name"])
            x = self._drag_pos.x + 6 + offset
            y = self._drag_pos.y + 6 + offset
            if bitmap is not None:
                dc.DrawBitmap(bitmap, x, y, True)
            else:
                dc.SetBrush(wx.Brush(wx.Colour(*DARK_ALT)))
                dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), 2))
                dc.DrawRectangle(x, y, _CARD_WIDTH, _CARD_HEIGHT)
            offset += 4

    # ----- event handlers -----
    def _on_left_down(self, event: wx.MouseEvent) -> None:
        point = self._to_logical(event.GetPosition())
        hit = self._hit_test(point)

        if hit is None:
            # Empty space: start a rubber-band selection (clear previous unless shift).
            if not event.ShiftDown():
                self._selected_uids.clear()
                self._notify_selection_changed()
            self._rubber_start = point
            self._rubber_end = point
            if not self.HasCapture():
                self.CaptureMouse()
            self.Refresh()
            return

        _pile_idx, _member_idx, entry = hit
        uid = entry["_uid"]
        if event.ShiftDown() or event.ControlDown():
            if uid in self._selected_uids:
                self._selected_uids.discard(uid)
            else:
                self._selected_uids.add(uid)
            self._notify_selection_changed()
        else:
            if self._selected_uids == {uid}:
                # Second click on the only selected card clears the selection.
                self._selected_uids.clear()
                self._notify_selection_changed()
                self.Refresh()
                return
            if uid not in self._selected_uids:
                self._selected_uids = {uid}
                self._notify_selection_changed()

        # Prime a potential drag: the actual drag starts in motion handler.
        self._drag_press = point
        self._drag_uids = sorted(self._selected_uids)
        if not self.HasCapture():
            self.CaptureMouse()
        self.Refresh()

    def _on_motion(self, event: wx.MouseEvent) -> None:
        point = self._to_logical(event.GetPosition())
        if self._rubber_start is not None:
            self._rubber_end = point
            self._select_within_rubber()
            self.Refresh()
            return

        if self._drag_press and event.LeftIsDown():
            dx = abs(point.x - self._drag_press.x)
            dy = abs(point.y - self._drag_press.y)
            if not self._drag_active and (dx > 4 or dy > 4):
                self._drag_active = True
            if self._drag_active:
                self._drag_pos = point
                self.Refresh()
            return

        # Hover handling — only when no selection or multi-selection.
        if self._on_hover and len(self._selected_uids) <= 1 and not self._selected_uids:
            hit = self._hit_test(point)
            if hit is None:
                if self._hover_uid is not None:
                    self._hover_uid = None
                    self.Refresh()
                return
            _pile_idx, _member_idx, entry = hit
            if entry["_uid"] != self._hover_uid:
                self._hover_uid = entry["_uid"]
                self._on_hover({"name": entry["name"], "qty": 1})
                self.Refresh()

    def _on_left_up(self, event: wx.MouseEvent) -> None:
        if self.HasCapture():
            self.ReleaseMouse()
        point = self._to_logical(event.GetPosition())

        if self._rubber_start is not None:
            self._rubber_start = None
            self._rubber_end = None
            self.Refresh()
            return

        if self._drag_active:
            self._drop_at(point)
            self._drag_active = False
            self._drag_press = None
            self._drag_uids = []
            self._drag_pos = None
            self.Refresh()
            return

        self._drag_press = None
        self._drag_uids = []

    def _on_leave(self, _event: wx.MouseEvent) -> None:
        if self._hover_uid is not None:
            self._hover_uid = None
            self.Refresh()

    def _on_capture_lost(self, _event: wx.MouseCaptureLostEvent) -> None:
        self._rubber_start = None
        self._rubber_end = None
        self._drag_active = False
        self._drag_press = None
        self._drag_uids = []
        self._drag_pos = None
        self.Refresh()

    # ----- selection helpers -----
    def _select_within_rubber(self) -> None:
        if not (self._rubber_start and self._rubber_end):
            return
        rect = wx.Rect(self._rubber_start, self._rubber_end)
        # wx.Rect with two points may have negative width/height; normalise.
        x1, y1 = self._rubber_start
        x2, y2 = self._rubber_end
        rect = wx.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        chosen: set[int] = set()
        for pile_idx, (_label, members) in enumerate(self._piles):
            total = len(members)
            for member_idx, entry in enumerate(members):
                card_rect = self._card_rect(pile_idx, member_idx, total)
                if member_idx < total - 1:
                    card_rect = wx.Rect(
                        card_rect.x, card_rect.y, card_rect.width, _NAME_STRIP_HEIGHT
                    )
                if rect.Intersects(card_rect):
                    chosen.add(entry["_uid"])
        if chosen != self._selected_uids:
            self._selected_uids = chosen
            self._notify_selection_changed()

    def _notify_selection_changed(self) -> None:
        if len(self._selected_uids) == 1:
            uid = next(iter(self._selected_uids))
            entry = self._find_entry(uid)
            if entry:
                self._on_select({"name": entry["name"], "qty": 1})
                return
        # Multi or empty selection: clear the inspector selection so hover wins.
        self._on_select(None)

    def _find_entry(self, uid: int) -> dict[str, Any] | None:
        for _label, members in self._piles:
            for entry in members:
                if entry["_uid"] == uid:
                    return entry
        return None

    # ----- drop handling -----
    def _drop_at(self, point: wx.Point) -> None:
        """Move the dragged copies into the pile nearest ``point``.

        Insertion index inside the target pile is the member-index nearest to
        the y-coordinate of the release point.
        """
        if not self._drag_uids:
            return
        target_pile_idx = self._pile_index_at(point.x)
        if target_pile_idx is None:
            return
        target_label, target_members = self._piles[target_pile_idx]

        # Find drop position by y.
        total = max(1, len(target_members))
        rel_y = point.y - _PILE_TOP
        # Map y to member index based on stacked layout.
        pile_height = self._pile_height(total)
        if pile_height <= 0:
            insert_idx = len(target_members)
        else:
            # Members are drawn top-to-bottom, so y=0 → top → member 0.
            slot_height = _NAME_STRIP_HEIGHT if total > 1 else _CARD_HEIGHT
            insert_idx = max(0, min(len(target_members), int(rel_y // slot_height)))

        # Extract dragged entries (remove from current piles).
        moved: list[dict[str, Any]] = []
        for _pile_idx in range(len(self._piles)):
            label, members = self._piles[_pile_idx]
            kept: list[dict[str, Any]] = []
            for entry in members:
                if entry["_uid"] in self._drag_uids:
                    moved.append(entry)
                else:
                    kept.append(entry)
            self._piles[_pile_idx] = (label, kept)

        if not moved:
            return

        # Preserve the dragged order.
        order_index = {uid: i for i, uid in enumerate(self._drag_uids)}
        moved.sort(key=lambda e: order_index.get(e["_uid"], 0))

        # Re-fetch target (its members list may have shrunk).
        target_label, target_members = self._piles[target_pile_idx]
        insert_idx = min(insert_idx, len(target_members))
        new_members = target_members[:insert_idx] + moved + target_members[insert_idx:]
        self._piles[target_pile_idx] = (target_label, new_members)
        self._manual_overrides = True
        self._update_virtual_size()

    def _pile_index_at(self, logical_x: int) -> int | None:
        if not self._piles:
            return None
        # Snap to nearest pile column.
        best_idx = 0
        best_dist = abs(self._pile_x(0) + _CARD_WIDTH // 2 - logical_x)
        for idx in range(1, len(self._piles)):
            d = abs(self._pile_x(idx) + _CARD_WIDTH // 2 - logical_x)
            if d < best_dist:
                best_idx = idx
                best_dist = d
        return best_idx
