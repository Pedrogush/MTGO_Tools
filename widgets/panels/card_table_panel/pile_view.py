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
from time import perf_counter
from typing import Any

import wx
from PIL import Image as PilImage

from utils.constants import (
    CARD_VIEW_SCROLL_RATE,
    DARK_ACCENT,
    DARK_ALT,
    DARK_BG,
    DARK_PANEL,
    DECK_CARD_CORNER_RADIUS,
    DECK_CARD_HEIGHT,
    DECK_CARD_WIDTH,
    LIGHT_TEXT,
    SUBDUED_TEXT,
)
from utils.image_effects import apply_rounded_corner_alpha
from widgets.panels.card_table_panel import scroll_perf
from widgets.panels.card_table_panel.scrolling import scroll_by_wheel
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
_PILE_PAD = 6  # padding inside a pile column
_PILE_TOP = _PILE_PAD  # top inset for the first card in a pile

# Above this virtual width/height (px) we skip the cached full-content bitmap
# and draw directly (culled), so a pathological pile can't allocate a huge
# canvas. Comfortably clears any real deck zone.
_MAX_CANVAS_PX = 20000


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
        on_remove: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, style=wx.HSCROLL | wx.VSCROLL)
        self.zone = zone
        self._get_metadata = get_metadata
        self._get_card_image = get_card_image
        self._on_select = on_select
        self._on_hover = on_hover
        self._get_sort_mode = get_sort_mode or (lambda: PILE_SORT_MV)
        self._on_remove = on_remove

        self._cards: list[dict[str, Any]] = []
        # piles is a list of (label, [card_entries...]) — card_entries are
        # per-copy dicts ({"name", "qty": 1, "_uid"}). Selection/drag tracks
        # _uid so individual copies survive a re-sort.
        self._piles: list[tuple[str, list[dict[str, Any]]]] = []
        self._selected_uids: set[int] = set()
        self._hover_uid: int | None = None
        self._manual_overrides: bool = False
        # While the pile view is reporting its own selection to the panel, the
        # panel echoes it back via set_selected(name). That round-trip is lossy
        # (a name can't name a specific copy, and multi-selection collapses to
        # None), so we suppress it to keep the per-copy selection we just made.
        self._suppress_set_selected: bool = False

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
        # Full-content bitmap of every pile (card art only). Scrolling blits a
        # sub-rect of this instead of re-drawing every copy's alpha bitmap, so a
        # wheel notch costs one viewport copy. Rebuilt on content change; the
        # affected pile is patched in place when a card image arrives.
        self._canvas: wx.Bitmap | None = None

        self.SetBackgroundColour(DARK_PANEL)
        # AutoBufferedPaintDC requires the window to use BG_STYLE_PAINT so
        # wx skips its own erase-background draw and the custom _on_paint owns
        # the whole client area.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        # 1px scroll units give the scrollbar thumb single-pixel granularity so
        # cards no longer snap in coarse jumps. The wheel scrolls a larger step
        # (see _on_wheel) since a notch would otherwise move only a few px.
        self.SetScrollRate(CARD_VIEW_SCROLL_RATE, CARD_VIEW_SCROLL_RATE)
        # No SetDoubleBuffered(True): AutoBufferedPaintDC in _on_paint already
        # gives flicker-free painting, and a window-level back-buffer would make
        # MSW repaint the whole client on every scroll instead of blitting the
        # old pixels and exposing only a thin strip (which is what keeps the
        # culled paint cheap).

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_RIGHT_DOWN, self._on_right_down)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
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

        Ignored while the pile view is broadcasting its own selection: the
        panel echoes that selection straight back here, and re-resolving it
        from a bare name would bounce a clicked copy to the first copy (and
        wipe any multi-copy rubber-band selection). The copies we just chose
        are authoritative, so keep them.
        """
        if self._suppress_set_selected:
            return
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
        # Pile contents/positions changed — the cached image is stale.
        self._invalidate_canvas()
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
            wx_img = apply_rounded_corner_alpha(wx_img, DECK_CARD_CORNER_RADIUS)
            self._image_cache.put(name, wx_img.ConvertToBitmap())
        # A single card's art changed — patch just the piles holding it.
        self._patch_card_on_canvas(name)

    # ----- paint -----
    def _on_paint(self, _event: wx.PaintEvent) -> None:
        t0 = perf_counter()
        dc = wx.AutoBufferedPaintDC(self)
        self.PrepareDC(dc)
        dc.SetBackground(wx.Brush(wx.Colour(*DARK_PANEL)))
        dc.Clear()

        canvas = self._ensure_canvas()
        if canvas is not None:
            # Cohesive image: copy just the visible window out of the prebuilt
            # full-content bitmap. One viewport blit per scroll, regardless of
            # how many copies the deck holds.
            view_x, view_y = self.GetViewStart()
            client_w, client_h = self.GetClientSize()
            # Clamp the copy to the canvas so we never read past its edge when
            # the content is shorter than the viewport; dc.Clear already filled
            # the remainder with the panel background.
            blit_w = min(client_w, canvas.GetWidth() - view_x)
            blit_h = min(client_h, canvas.GetHeight() - view_y)
            if blit_w > 0 and blit_h > 0:
                src = wx.MemoryDC(canvas)
                dc.Blit(view_x, view_y, blit_w, blit_h, src, view_x, view_y)
                src.SelectObject(wx.NullBitmap)
            self._draw_overlays(dc)
        else:
            # Oversized pile: draw directly, culled to the repaint region.
            dirty = self._dirty_logical_rect()
            for pile_idx, (_label, members) in enumerate(self._piles):
                self._draw_pile(dc, pile_idx, members, dirty)
            self._draw_overlays(dc, dirty)

        if self._rubber_start and self._rubber_end:
            self._draw_rubber_band(dc)

        if self._drag_active and self._drag_pos:
            self._draw_drag_ghost(dc)

        # Stamp the origin this paint just rendered (and how long it took) so the
        # wheel-latency harness can tell when the view caught up to the scroll
        # input (no-op unless the perf recorder is enabled).
        scroll_perf.record_paint(self, *self.GetViewStart(), dur_ms=(perf_counter() - t0) * 1000.0)

    def _dirty_logical_rect(self) -> wx.Rect | None:
        """The region wx asked us to repaint, in logical (scrolled) coords.

        ``None`` means repaint everything (empty update region, e.g. a full
        ``Refresh``), so nothing is dropped from a non-scroll repaint.
        """
        box = self.GetUpdateRegion().GetBox()
        if box.IsEmpty():
            return None
        top_left = self.CalcUnscrolledPosition(box.GetTopLeft())
        return wx.Rect(top_left.x, top_left.y, box.GetWidth(), box.GetHeight())

    # ----- cohesive cached canvas -----
    def _invalidate_canvas(self) -> None:
        """Drop the cached full-content bitmap so the next paint rebuilds it."""
        self._canvas = None

    def _ensure_canvas(self) -> wx.Bitmap | None:
        """Return the full-content bitmap, building it if stale.

        Returns ``None`` when there is nothing to draw or the virtual size is
        too large to cache, signalling the caller to draw directly.
        """
        vsize = self.GetVirtualSize()
        vw, vh = vsize.GetWidth(), vsize.GetHeight()
        if not self._piles or vw <= 0 or vh <= 0:
            return None
        if vw > _MAX_CANVAS_PX or vh > _MAX_CANVAS_PX:
            return None
        if self._canvas is not None and self._canvas.GetSize() == vsize:
            return self._canvas
        canvas = wx.Bitmap(vw, vh)
        mem = wx.MemoryDC(canvas)
        mem.SetBackground(wx.Brush(wx.Colour(*DARK_PANEL)))
        mem.Clear()
        for pile_idx, (_label, members) in enumerate(self._piles):
            self._draw_pile(mem, pile_idx, members, None)
        mem.SelectObject(wx.NullBitmap)
        self._canvas = canvas
        return canvas

    def _patch_card_on_canvas(self, name: str) -> None:
        """Redraw the piles holding ``name`` into the canvas and invalidate them.

        Cards in a pile overlap, with later members drawn on top, so from the
        first matching copy downward must be repainted to composite correctly.
        """
        if self._canvas is None:
            self.Refresh()
            return
        lname = name.lower()
        mem = wx.MemoryDC(self._canvas)
        mem.SetPen(wx.TRANSPARENT_PEN)
        view_x, view_y = self.GetViewStart()
        for pile_idx, (_label, members) in enumerate(self._piles):
            total = len(members)
            first = next((i for i, e in enumerate(members) if e["name"].lower() == lname), None)
            if first is None:
                continue
            top_rect = self._card_rect(pile_idx, first, total)
            bottom_rect = self._card_rect(pile_idx, total - 1, total)
            region = wx.Rect(
                top_rect.x,
                top_rect.y,
                _CARD_WIDTH,
                bottom_rect.GetBottom() - top_rect.y + 1,
            )
            mem.SetBrush(wx.Brush(wx.Colour(*DARK_PANEL)))
            mem.DrawRectangle(region)
            for member_idx in range(first, total):
                self._draw_card(
                    mem, self._card_rect(pile_idx, member_idx, total), members[member_idx]
                )
            self.RefreshRect(
                wx.Rect(region.x - view_x, region.y - view_y, region.width, region.height)
            )
        mem.SelectObject(wx.NullBitmap)

    def _draw_overlays(self, dc: wx.DC, dirty: wx.Rect | None = None) -> None:
        """Draw selection/hover borders over the blitted cards (live, not cached)."""
        if not self._selected_uids and self._hover_uid is None:
            return
        for pile_idx, (_label, members) in enumerate(self._piles):
            total = len(members)
            for member_idx, entry in enumerate(members):
                uid = entry["_uid"]
                is_selected = uid in self._selected_uids
                is_hover = uid == self._hover_uid
                if not (is_selected or is_hover):
                    continue
                rect = self._card_rect(pile_idx, member_idx, total)
                if dirty is not None and not dirty.Intersects(rect):
                    continue
                dc.SetBrush(wx.TRANSPARENT_BRUSH)
                if is_selected:
                    dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), 3))
                else:
                    dc.SetPen(wx.Pen(wx.Colour(*SUBDUED_TEXT), 1, wx.PENSTYLE_DOT))
                dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)

    def _draw_pile(
        self,
        dc: wx.DC,
        pile_idx: int,
        members: list[dict[str, Any]],
        dirty: wx.Rect | None = None,
    ) -> None:
        total = len(members)
        for member_idx, entry in enumerate(members):
            rect = self._card_rect(pile_idx, member_idx, total)
            if dirty is not None and not dirty.Intersects(rect):
                continue
            self._draw_card(dc, rect, entry)

    def _draw_card(
        self,
        dc: wx.DC,
        rect: wx.Rect,
        entry: dict[str, Any],
    ) -> None:
        # Only the scroll-invariant art is drawn here (and baked into the cached
        # canvas). Selection/hover borders are painted live by _draw_overlays so
        # selecting a card never invalidates the cached image.
        self._draw_card_art(dc, rect, entry)

    def _draw_card_art(
        self,
        dc: wx.DC,
        rect: wx.Rect,
        entry: dict[str, Any],
    ) -> None:
        """Render the full card art for ``entry`` at ``rect``.

        Cards are drawn in stack order from top of pile to bottom, so each
        successive draw paints over the body of the card beneath it, leaving
        only the visible top strip of earlier cards. There is no clipping —
        every card lays down its full bitmap.
        """
        name = entry["name"]
        bitmap = self._image_cache.get(name)
        if bitmap is not None:
            x = rect.x + (rect.width - bitmap.GetWidth()) // 2
            y = rect.y + (rect.height - bitmap.GetHeight()) // 2
            dc.DrawBitmap(bitmap, x, y, True)
            return

        dc.SetBrush(wx.Brush(wx.Colour(*DARK_ALT)))
        dc.SetPen(wx.Pen(wx.Colour(*DARK_BG), 1))
        dc.DrawRoundedRectangle(rect.x, rect.y, rect.width, rect.height, DECK_CARD_CORNER_RADIUS)
        dc.SetTextForeground(wx.Colour(*LIGHT_TEXT))
        dc.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        text = self._fit_text(dc, name, rect.width - 8)
        dc.DrawText(text, rect.x + 4, rect.y + 8)

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
        """Render the dragged cards as a real pile anchored near the cursor.

        The ghost mirrors how the source pile is laid out: cards stack with
        ``_NAME_STRIP_HEIGHT`` offsets, the last entry rendered full-height at
        the bottom and earlier entries showing only their top strip above it.
        Members are taken from ``_drag_uids`` in visual order (top-to-bottom
        as they appeared in the source pile).
        """
        if not self._drag_pos or not self._drag_uids:
            return
        total = len(self._drag_uids)
        origin_x = self._drag_pos.x + 6
        bottom_y = self._drag_pos.y + 6 + (total - 1) * _NAME_STRIP_HEIGHT
        for member_idx, uid in enumerate(self._drag_uids):
            entry = self._find_entry(uid)
            if entry is None:
                continue
            y = bottom_y - (total - 1 - member_idx) * _NAME_STRIP_HEIGHT
            rect = wx.Rect(origin_x, y, _CARD_WIDTH, _CARD_HEIGHT)
            self._draw_card_art(dc, rect, entry)

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
        # Drag uids are taken in visual top-to-bottom order so the ghost stack
        # matches the source pile and so dropped cards land in the same
        # relative order in the target pile.
        self._drag_press = point
        self._drag_uids = self._uids_in_visual_order(self._selected_uids)
        if not self.HasCapture():
            self.CaptureMouse()
        self.Refresh()

    def _on_right_down(self, event: wx.MouseEvent) -> None:
        """Right-click removes the card under the cursor from the deck zone.

        Removal is delegated to the panel's ``on_remove`` callback, which drops
        every copy of that card from the zone (mirroring the grid view's ``×``
        button); the pile view is then rebuilt by the resulting ``set_cards``.
        """
        if self._on_remove is None:
            event.Skip()
            return
        point = self._to_logical(event.GetPosition())
        hit = self._hit_test(point)
        if hit is None:
            event.Skip()
            return
        _pile_idx, _member_idx, entry = hit
        self._on_remove(entry["name"])

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

    def _on_wheel(self, event: wx.MouseEvent) -> None:
        # Shared with the grid view so both scroll identically (see scrolling.py).
        scroll_by_wheel(self, event)

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
        # The panel syncs the reported selection back into every view,
        # including this one. Guard that re-entrant set_selected so it can't
        # clobber the per-copy selection we're about to report.
        self._suppress_set_selected = True
        try:
            if len(self._selected_uids) == 1:
                uid = next(iter(self._selected_uids))
                entry = self._find_entry(uid)
                if entry:
                    self._on_select({"name": entry["name"], "qty": 1})
                    return
            # Multi or empty selection: clear the inspector selection so hover wins.
            self._on_select(None)
        finally:
            self._suppress_set_selected = False

    def _find_entry(self, uid: int) -> dict[str, Any] | None:
        for _label, members in self._piles:
            for entry in members:
                if entry["_uid"] == uid:
                    return entry
        return None

    def _uids_in_visual_order(self, uids: set[int]) -> list[int]:
        """Return ``uids`` in top-to-bottom-of-pile order across all piles."""
        ordered: list[int] = []
        for _label, members in self._piles:
            for entry in members:
                if entry["_uid"] in uids:
                    ordered.append(entry["_uid"])
        return ordered

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
