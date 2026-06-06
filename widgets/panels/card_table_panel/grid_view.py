"""Grid view for CardTablePanel.

A single custom-drawn :class:`wx.ScrolledWindow` that lays the deck's cards out
in a wrapping grid and paints every card in one buffered paint pass — the same
canvas model :class:`DeckPileView` uses, but with a grid layout instead of
piles.

It replaces the previous architecture, where the grid was a pool of native
``CardBoxPanel`` cells (each a ``wx.Panel`` holding a ``StaticText`` and three
``wx.Button``s). That created ~5 native window handles per card — ~200 OS
handles for a 40-card deck — and a deck load dispatched ~40 separate paint
events on ``Thaw``. The canvas has no child widgets, so a deck load is bitmap
blits plus layout math in one paint.

Behaviour kept at parity with the old grid cells:

* Click a card to select it; click the selected card again to clear it. The
  selection is mirrored across the table/pile views by ``CardTablePanel``.
* Hover forwards the card under the mouse to the inspector.
* Each card's quantity is drawn top-left, coloured by owned status.
* Inline ``+`` / ``−`` / ``×`` controls are drawn (not native buttons) as
  hit-zones on the hovered/selected card, hit-tested on click — the same
  drawn-control model the table view's actions column uses.
* When a card image hasn't loaded yet, a placeholder template (card-colour
  background, mana-cost badge, wrapped name) is drawn, exactly as before.
"""

from __future__ import annotations

import atexit
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Any

import wx
from PIL import Image as PilImage

from utils.constants import (
    CARD_VIEW_SCROLL_RATE,
    DARK_ACCENT,
    DARK_ALT,
    DARK_PANEL,
    DECK_CARD_ACTION_BUTTON_FG,
    DECK_CARD_ACTION_BUTTON_SIZE,
    DECK_CARD_ACTIVE_BORDER_WIDTH,
    DECK_CARD_BADGE_PADDING,
    DECK_CARD_BASE_FONT_SIZE,
    DECK_CARD_BUTTON_MARGIN,
    DECK_CARD_CORNER_RADIUS,
    DECK_CARD_HEIGHT,
    DECK_CARD_IMAGE_BG,
    DECK_CARD_NAME_FONT_SIZE,
    DECK_CARD_TEMPLATE_BORDER_ALPHA,
    DECK_CARD_TEMPLATE_BORDER_WIDTH,
    DECK_CARD_WIDTH,
    LIGHT_TEXT,
)
from utils.image_effects import apply_rounded_corner_alpha
from widgets.mana_icon_factory import ManaIconFactory
from widgets.panels.card_table_panel import scroll_perf
from widgets.panels.card_table_panel.card_render import (
    build_image_name_candidates,
    resolve_card_color,
)
from widgets.panels.card_table_panel.marquee import RUBBER_AUTOSCROLL_PX, MarqueeController
from widgets.panels.card_table_panel.pile_view import _ImageCache
from widgets.panels.card_table_panel.scrolling import scroll_by_wheel

# Match the grid sizer's old geometry: DECK_CARD_WIDTH×HEIGHT cells with a
# GRID_GAP (== CardTablePanel.GRID_GAP) right/bottom margin between them.
_CARD_WIDTH = DECK_CARD_WIDTH
_CARD_HEIGHT = DECK_CARD_HEIGHT
_GAP = 8
_CELL_WIDTH = _CARD_WIDTH + _GAP
_CELL_HEIGHT = _CARD_HEIGHT + _GAP

_ACTION_GLYPHS = ("+", "−", "×")
_ACTION_SPACING = 2  # px gap between the drawn +/−/× hit-zones
_ACTION_BUTTON_RADIUS = 4

# Fallback column count before the window has a real client width to wrap to.
_DEFAULT_COLUMNS = 4

# Above this virtual width/height (px) we skip the cached full-content bitmap
# and fall back to direct culled drawing, so a pathologically large deck can't
# allocate a multi-hundred-MB canvas. Comfortably clears any real deck zone.
_MAX_CANVAS_PX = 20000

# Shared, bounded pool for decoding deck-cell card images off the UI thread.
# One shared pool makes dispatch a near-free submit() and caps the number of
# concurrent PIL decodes so 40 LANCZOS resizes don't thrash the GIL. Threads
# idle out, so the pool costs nothing between deck loads.
_IMAGE_DECODE_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="card-img-decode")
# Don't let the executor's atexit join block app shutdown on in-flight decodes.
atexit.register(_IMAGE_DECODE_POOL.shutdown, wait=False, cancel_futures=True)


class DeckGridView(wx.ScrolledWindow):
    """A scrolled, custom-drawn grid view of the deck's cards."""

    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        get_metadata: Callable[[str], Any],
        get_card_image: Callable[[str, str], Path | None],
        owned_status: Callable[[str, int], tuple[str, tuple[int, int, int]]],
        icon_factory: ManaIconFactory,
        on_select: Callable[[dict[str, Any] | None], None],
        on_hover: Callable[[dict[str, Any]], None] | None,
        on_delta: Callable[[str, int], None] | None = None,
        on_remove: Callable[[str], None] | None = None,
        on_zone_transfer: Callable[[list[str], wx.Point], bool] | None = None,
    ) -> None:
        super().__init__(parent, style=wx.VSCROLL)
        self.zone = zone
        self._get_metadata = get_metadata
        self._get_card_image = get_card_image
        self._owned_status = owned_status
        self._icon_factory = icon_factory
        self._on_select = on_select
        self._on_hover = on_hover
        self._on_delta = on_delta
        self._on_remove = on_remove
        self._on_zone_transfer = on_zone_transfer

        self._cards: list[dict[str, Any]] = []
        # Multi-selection by card name (a single click selects exactly one).
        # Marquee can select several; the highlight covers every name in the set.
        self._selected_names: set[str] = set()
        self._hover_name: str | None = None
        self._pressed: tuple[str, int] | None = None
        self._cols: int = _DEFAULT_COLUMNS
        # See pile view: the panel echoes our reported selection back via
        # set_selected(); suppress that round-trip while we report a multi-select
        # marquee so the echoed None can't wipe the set we just built.
        self._suppress_set_selected: bool = False
        self._marquee = MarqueeController(
            self,
            to_logical=self._to_logical,
            on_begin=self._marquee_begin,
            on_select=self._marquee_select,
            on_finish=self._marquee_finish,
            autoscroll=self._autoscroll_towards,
        )
        self._marquee_base: set[str] | None = None

        # Drag-to-reorder state. The grid lays out one cell per distinct card
        # (quantity shown as a badge), so a reorder rearranges card *names*, not
        # individual copies — the natural model for this layout (see issue #780).
        # A reorder is a visual rearrangement only: it never changes zone
        # quantities, so it stays inside the view and is not reported upward.
        self._drag_press: wx.Point | None = None
        self._drag_active = False
        self._drag_names: list[str] = []
        self._drag_pos: wx.Point | None = None
        # Insertion index the current drag would drop into (None when no drag).
        self._drop_index: int | None = None
        # Set once the user manually reorders; like the pile view, the arranged
        # order survives until the next set_cards (a deck edit / reload re-sorts).
        self._manual_overrides = False

        self._image_cache = _ImageCache()
        # Per-name load generation so a stale in-flight decode (e.g. of an old
        # image after refresh_image re-downloads) can't overwrite a newer one.
        self._load_gen: dict[str, int] = {}
        # Placeholder bitmaps keyed by name; built lazily, reused across loads.
        self._template_cache: dict[str, wx.Bitmap] = {}
        # Full-content bitmap of every card (art + quantity badge). Scrolling
        # blits a sub-rect of this instead of re-drawing each card's alpha
        # bitmap, so a wheel notch costs one viewport-sized copy. Rebuilt on
        # layout/content change; patched per-card when an image arrives.
        self._canvas: wx.Bitmap | None = None

        self.SetBackgroundColour(DARK_PANEL)
        # AutoBufferedPaintDC requires BG_STYLE_PAINT so wx skips its own
        # erase-background draw and _on_paint owns the whole client area.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        # 1px scroll units (shared with the pile view) give the scrollbar thumb
        # single-pixel granularity; the wheel handler then scrolls a larger
        # per-notch step so the wheel still moves a useful distance.
        self.SetScrollRate(CARD_VIEW_SCROLL_RATE, CARD_VIEW_SCROLL_RATE)
        # No SetDoubleBuffered(True): AutoBufferedPaintDC in _on_paint already
        # gives flicker-free painting, and a window-level back-buffer would make
        # MSW repaint the whole client on every scroll instead of blitting the
        # old pixels and exposing only a thin strip (which is what keeps the
        # culled paint cheap).

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)

    # ----- public API consumed by CardTablePanel -----
    def set_cards(self, cards: list[dict[str, Any]], preserve_scroll: bool = False) -> None:
        self._cards = list(cards)
        # An in-place edit (preserve_scroll) — e.g. a +/−/× click — leaves the
        # cursor over the same card, so keep its hovered +/−/× controls drawn.
        # Clearing hover here is what made the buttons vanish after every click
        # and blocked rapid clicking. A fresh load / deck switch (not
        # preserve_scroll) moves focus elsewhere, so drop stale hover/press.
        if not preserve_scroll:
            self._hover_name = None
            self._pressed = None
        # A reorder is local to the view; any incoming set_cards (deck edit or
        # reload) supersedes the manual arrangement, so drop the override and any
        # in-flight drag.
        self._manual_overrides = False
        self._reset_drag()
        self._recompute_layout()
        self._prefetch_images()
        if not preserve_scroll:
            self.Scroll(0, 0)
        self.Refresh()

    def set_selected(self, name: str | None) -> None:
        # Ignored while we broadcast our own (possibly multi-) selection: the
        # panel echoes it straight back and a bare name can't represent a set.
        if self._suppress_set_selected:
            return
        self._selected_names = {name} if name else set()
        self.Refresh()

    def get_selected_name(self) -> str | None:
        if len(self._selected_names) != 1:
            return None
        return next(iter(self._selected_names))

    def get_selected_card(self) -> dict[str, Any] | None:
        name = self.get_selected_name()
        if not name:
            return None
        for card in self._cards:
            if card["name"].lower() == name.lower():
                return card
        return None

    def focus_card(self, name: str) -> bool:
        """Select ``name`` and scroll it into view. Returns True if found."""
        if not name:
            return False
        for idx, card in enumerate(self._cards):
            if card["name"].lower() == name.lower():
                self._selected_names = {card["name"]}
                self._ensure_visible(self._card_rect(idx))
                self.Refresh()
                return True
        return False

    def count_loaded_images(self) -> tuple[int, int]:
        """Return (loaded, total) over the distinct cards currently shown.

        A card counts as loaded once its art bitmap is in the cache (a cached
        ``None`` means in-flight or image-missing, like the old per-cell
        ``_card_bitmap`` being unset). Used by the automation harness.
        """
        names = {card["name"] for card in self._cards}
        loaded = sum(1 for name in names if self._image_cache.get(name) is not None)
        return loaded, len(names)

    def refresh_image(self, name: str) -> None:
        """Drop ``name``'s cached art and reload it (image re-downloaded)."""
        if any(c["name"].lower() == name.lower() for c in self._cards):
            # Match against the deck's stored casing so the cache key lines up.
            for card in self._cards:
                if card["name"].lower() == name.lower():
                    self._start_image_load(card["name"])
            self.Refresh()

    # ----- layout -----
    def _recompute_layout(self) -> None:
        client_w = self.GetClientSize().GetWidth()
        cols = max(1, client_w // _CELL_WIDTH) if client_w > 0 else self._cols
        self._cols = cols
        n = len(self._cards)
        rows = ceil(n / cols) if n else 0
        self.SetVirtualSize((cols * _CELL_WIDTH, rows * _CELL_HEIGHT))
        # Layout (column count / card count) changed — the cached image no
        # longer matches; rebuild it on the next paint.
        self._invalidate_canvas()

    def _card_rect(self, index: int) -> wx.Rect:
        cols = max(1, self._cols)
        row, col = divmod(index, cols)
        return wx.Rect(col * _CELL_WIDTH, row * _CELL_HEIGHT, _CARD_WIDTH, _CARD_HEIGHT)

    def _hit_test(self, point: wx.Point) -> int | None:
        cols = max(1, self._cols)
        if point.x < 0 or point.y < 0:
            return None
        col = point.x // _CELL_WIDTH
        row = point.y // _CELL_HEIGHT
        if col >= cols:
            return None
        idx = row * cols + col
        if 0 <= idx < len(self._cards) and self._card_rect(idx).Contains(point):
            return idx
        return None

    def _to_logical(self, screen_point: wx.Point) -> wx.Point:
        x, y = self.CalcUnscrolledPosition(screen_point)
        return wx.Point(x, y)

    def _ensure_visible(self, rect: wx.Rect) -> None:
        _ppu_x, ppu_y = self.GetScrollPixelsPerUnit()
        if ppu_y <= 0:
            return
        view_y = self.GetViewStart()[1] * ppu_y
        client_h = self.GetClientSize().GetHeight()
        if rect.y < view_y:
            self.Scroll(-1, rect.y // ppu_y)
        elif rect.y + rect.height > view_y + client_h:
            self.Scroll(-1, (rect.y + rect.height - client_h) // ppu_y + 1)

    # ----- action (+/−/×) hit-zones -----
    def _action_button_rects(self, card_rect: wx.Rect) -> list[wx.Rect]:
        btn_w, btn_h = DECK_CARD_ACTION_BUTTON_SIZE
        x = card_rect.x + DECK_CARD_BUTTON_MARGIN
        y = card_rect.y + card_rect.height - DECK_CARD_BUTTON_MARGIN - btn_h
        return [
            wx.Rect(x + i * (btn_w + _ACTION_SPACING), y, btn_w, btn_h)
            for i in range(len(_ACTION_GLYPHS))
        ]

    def _shows_actions(self, name: str) -> bool:
        lower = name.lower()
        if self._hover_name is not None and lower == self._hover_name.lower():
            return True
        # Only show the inline +/−/× on a lone selection; a marquee multi-select
        # shouldn't plaster controls across every chosen card.
        return len(self._selected_names) == 1 and name in self._selected_names

    # ----- image loading -----
    def _prefetch_images(self) -> None:
        seen: set[str] = set()
        for card in self._cards:
            name = card["name"]
            if name in seen or self._image_cache.has(name):
                continue
            seen.add(name)
            self._start_image_load(name)

    def _start_image_load(self, name: str) -> None:
        gen = self._load_gen.get(name, 0) + 1
        self._load_gen[name] = gen
        # Mark as in-flight so _prefetch_images won't double-submit; the cache
        # returning None for a known key falls back to the placeholder template.
        self._image_cache.put(name, None)
        meta = self._get_metadata(name) or {}
        candidates = build_image_name_candidates({"name": name}, meta)
        _IMAGE_DECODE_POOL.submit(self._image_worker, name, gen, candidates)

    def _image_worker(self, name: str, gen: int, candidates: list[str]) -> None:
        image_path: Path | None = None
        for candidate in candidates:
            path = self._get_card_image(candidate, "normal")
            if path and path.exists():
                image_path = path
                break
        if image_path is None:
            wx.CallAfter(self._image_loaded, name, gen, None)
            return
        try:
            img = PilImage.open(str(image_path)).convert("RGB")
            w, h = img.size
            scale = min(_CARD_WIDTH / w, _CARD_HEIGHT / h)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), PilImage.LANCZOS)
            wx.CallAfter(self._image_loaded, name, gen, img)
        except Exception:
            wx.CallAfter(self._image_loaded, name, gen, None)

    def _image_loaded(self, name: str, gen: int, pil_img: PilImage.Image | None) -> None:
        try:
            if not self:
                return
        except RuntimeError:
            return
        if self._load_gen.get(name) != gen:
            return  # superseded by a newer load for this card
        if pil_img is None:
            self._image_cache.put(name, None)  # keep placeholder
        else:
            w, h = pil_img.size
            wx_img = wx.Image(w, h)
            wx_img.SetData(pil_img.tobytes())
            wx_img = apply_rounded_corner_alpha(wx_img, DECK_CARD_CORNER_RADIUS)
            self._image_cache.put(name, wx_img.ConvertToBitmap())
        # A single card's art changed — patch just its cell in the cached image.
        self._patch_card_on_canvas(name)

    # ----- placeholder template -----
    def _template_for(self, name: str) -> wx.Bitmap:
        cached = self._template_cache.get(name)
        if cached is not None:
            return cached
        meta = self._get_metadata(name) or {}
        bitmap = self._build_template_bitmap(name, meta)
        self._template_cache[name] = bitmap
        return bitmap

    def _build_template_bitmap(self, name: str, meta: dict[str, Any]) -> wx.Bitmap:
        color = resolve_card_color(meta)
        mana_cost = meta.get("mana_cost") or ""
        bitmap = wx.Bitmap(_CARD_WIDTH, _CARD_HEIGHT)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.Colour(*color)))
        dc.Clear()
        rect = wx.Rect(0, 0, _CARD_WIDTH, _CARD_HEIGHT)
        dc.SetPen(
            wx.Pen(
                wx.Colour(*DECK_CARD_IMAGE_BG, DECK_CARD_TEMPLATE_BORDER_ALPHA),
                DECK_CARD_TEMPLATE_BORDER_WIDTH,
            )
        )
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)
        self._draw_placeholder_details(dc, rect, name, mana_cost)
        dc.SelectObject(wx.NullBitmap)
        rounded = apply_rounded_corner_alpha(bitmap.ConvertToImage(), DECK_CARD_CORNER_RADIUS)
        return rounded.ConvertToBitmap()

    def _draw_placeholder_details(
        self, dc: wx.DC, rect: wx.Rect, name: str, mana_cost: str
    ) -> None:
        cost_bitmap = self._icon_factory.bitmap_for_cost(mana_cost) if mana_cost else None
        if cost_bitmap:
            cost_x = rect.x + rect.width - cost_bitmap.GetWidth() - DECK_CARD_BADGE_PADDING
            cost_y = rect.y + DECK_CARD_BADGE_PADDING
            dc.DrawBitmap(cost_bitmap, cost_x, cost_y, True)
        elif mana_cost:
            dc.SetTextForeground(wx.Colour(*LIGHT_TEXT))
            dc.DrawText(
                mana_cost,
                rect.x + rect.width - (DECK_CARD_BADGE_PADDING * 6),
                rect.y + DECK_CARD_BADGE_PADDING,
            )

        dc.SetTextForeground(wx.Colour(0, 0, 0))
        dc.SetFont(
            wx.Font(
                DECK_CARD_NAME_FONT_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_BOLD,
            )
        )
        name_lines = self._wrap_text(dc, name, rect.width - (DECK_CARD_BADGE_PADDING * 2))
        line_height = dc.GetTextExtent("Ag")[1]
        total_height = line_height * len(name_lines)
        start_y = rect.y + (rect.height - total_height) // 2
        for line in name_lines:
            text_width = dc.GetTextExtent(line)[0]
            dc.DrawText(line, rect.x + (rect.width - text_width) // 2, start_y)
            start_y += line_height

    @staticmethod
    def _wrap_text(dc: wx.DC, text: str, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return [text]
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if dc.GetTextExtent(test)[0] <= max_width or not current:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

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
            # full-content bitmap. Cost is one viewport blit, independent of how
            # many cards the deck has or how far we've scrolled.
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
            # Oversized deck: draw directly, culled to the repaint region.
            for idx in self._visible_card_indices():
                self._draw_card(dc, self._card_rect(idx), self._cards[idx])
        if self._drag_active:
            self._draw_drop_indicator(dc)
            self._draw_drag_ghost(dc)
        # Stamp the origin this paint just rendered (and how long it took) so the
        # wheel-latency harness can tell when the view caught up to the scroll
        # input (no-op unless the perf recorder is enabled).
        scroll_perf.record_paint(self, *self.GetViewStart(), dur_ms=(perf_counter() - t0) * 1000.0)

    def _visible_card_indices(self) -> range:
        """Indices of the cards overlapping the current repaint region.

        Used only by the oversized-deck fallback. Falls back to every card when
        the update region is empty (e.g. a full ``Refresh``).
        """
        n = len(self._cards)
        if n == 0:
            return range(0)
        cols = max(1, self._cols)
        box = self.GetUpdateRegion().GetBox()
        if box.IsEmpty():
            top, bottom = 0, self.GetClientSize().GetHeight()
        else:
            top, bottom = box.GetTop(), box.GetBottom()
        # Region is in device coords; shift by the scroll origin to get logical y.
        view_y = self.GetViewStart()[1]
        first_row = max(0, (top + view_y) // _CELL_HEIGHT)
        last_row = (bottom + view_y) // _CELL_HEIGHT
        return range(first_row * cols, min(n, (last_row + 1) * cols))

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
        if not self._cards or vw <= 0 or vh <= 0:
            return None
        if vw > _MAX_CANVAS_PX or vh > _MAX_CANVAS_PX:
            return None
        if self._canvas is not None and self._canvas.GetSize() == vsize:
            return self._canvas
        canvas = wx.Bitmap(vw, vh)
        mem = wx.MemoryDC(canvas)
        mem.SetBackground(wx.Brush(wx.Colour(*DARK_PANEL)))
        mem.Clear()
        for idx, card in enumerate(self._cards):
            self._draw_card_static(mem, self._card_rect(idx), card)
        mem.SelectObject(wx.NullBitmap)
        self._canvas = canvas
        return canvas

    def _patch_card_on_canvas(self, name: str) -> None:
        """Redraw just ``name``'s cell(s) into the canvas and invalidate them.

        Called when a card's art finishes loading so a single image swap repaints
        only that card rather than rebuilding or re-blitting the whole view.
        """
        if self._canvas is None:
            self.Refresh()
            return
        mem = wx.MemoryDC(self._canvas)
        mem.SetBackground(wx.Brush(wx.Colour(*DARK_PANEL)))
        view_x, view_y = self.GetViewStart()
        for idx, card in enumerate(self._cards):
            if card["name"].lower() != name.lower():
                continue
            rect = self._card_rect(idx)
            mem.SetBrush(wx.Brush(wx.Colour(*DARK_PANEL)))
            mem.SetPen(wx.TRANSPARENT_PEN)
            mem.DrawRectangle(rect)
            self._draw_card_static(mem, rect, card)
            self.RefreshRect(wx.Rect(rect.x - view_x, rect.y - view_y, rect.width, rect.height))
        mem.SelectObject(wx.NullBitmap)

    def _draw_overlays(self, dc: wx.DC) -> None:
        """Draw selection border, accent badge and +/−/× over the blitted cards."""
        sel = self._selected_names
        hov = self._hover_name
        if not sel and not hov:
            return
        for idx, card in enumerate(self._cards):
            name = card["name"]
            is_selected = name in sel
            is_hover = hov is not None and name.lower() == hov.lower()
            if not (is_selected or is_hover):
                continue
            rect = self._card_rect(idx)
            if is_selected:
                self._draw_qty(dc, rect, card, True)
                dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), DECK_CARD_ACTIVE_BORDER_WIDTH))
                dc.SetBrush(wx.TRANSPARENT_BRUSH)
                dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)
            if self._shows_actions(name):
                self._draw_actions(dc, rect, name)

    def _draw_card_static(self, dc: wx.DC, rect: wx.Rect, card: dict[str, Any]) -> None:
        """Draw a card's scroll-invariant content (art + base quantity badge).

        This is what gets baked into the cached canvas. Selection accent, active
        border and the +/−/× controls are deliberately left out — they change
        without the card itself changing, so they are painted live as overlays.
        """
        name = card["name"]
        bitmap = self._image_cache.get(name)
        if bitmap is not None:
            x = rect.x + (rect.width - bitmap.GetWidth()) // 2
            y = rect.y + (rect.height - bitmap.GetHeight()) // 2
            dc.DrawBitmap(bitmap, x, y, True)
        else:
            dc.DrawBitmap(self._template_for(name), rect.x, rect.y, True)
        self._draw_qty(dc, rect, card, False)

    def _draw_card(self, dc: wx.DC, rect: wx.Rect, card: dict[str, Any]) -> None:
        """Draw a card in full (static content + live overlays).

        Used by the oversized-deck fallback path that bypasses the canvas.
        """
        name = card["name"]
        is_selected = name in self._selected_names
        self._draw_card_static(dc, rect, card)
        if is_selected:
            self._draw_qty(dc, rect, card, True)
            dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), DECK_CARD_ACTIVE_BORDER_WIDTH))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)

        if self._shows_actions(name):
            self._draw_actions(dc, rect, name)

    def _draw_qty(self, dc: wx.DC, rect: wx.Rect, card: dict[str, Any], is_selected: bool) -> None:
        qty_value = card["qty"]
        qty_for_check = int(qty_value) if isinstance(qty_value, float) else qty_value
        _, owned_rgb = self._owned_status(card["name"], qty_for_check)
        text = str(qty_value)
        dc.SetFont(
            wx.Font(
                DECK_CARD_BASE_FONT_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        tw, th = dc.GetTextExtent(text)
        pad = DECK_CARD_BADGE_PADDING
        badge_bg = DARK_ACCENT if is_selected else DARK_ALT
        dc.SetBrush(wx.Brush(wx.Colour(*badge_bg)))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect.x + pad, rect.y + pad, tw + pad * 2, th + pad)
        dc.SetTextForeground(wx.Colour(*owned_rgb))
        dc.DrawText(text, rect.x + pad * 2, rect.y + pad + (th + pad) // 2 - th // 2)

    def _draw_actions(self, dc: wx.DC, rect: wx.Rect, name: str) -> None:
        dc.SetFont(
            wx.Font(
                DECK_CARD_BASE_FONT_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_BOLD,
            )
        )
        for idx, (button_rect, glyph) in enumerate(
            zip(self._action_button_rects(rect), _ACTION_GLYPHS)
        ):
            pressed = self._pressed == (name, idx)
            bg = tuple(max(0, c - 40) for c in DARK_ACCENT) if pressed else DARK_ACCENT
            dc.SetBrush(wx.Brush(wx.Colour(*bg)))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRoundedRectangle(button_rect, _ACTION_BUTTON_RADIUS)
            dc.SetTextForeground(wx.Colour(*DECK_CARD_ACTION_BUTTON_FG))
            gw, gh = dc.GetTextExtent(glyph)
            dc.DrawText(
                glyph,
                button_rect.x + (button_rect.width - gw) // 2,
                button_rect.y + (button_rect.height - gh) // 2,
            )

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

    def _drop_index_at(self, point: wx.Point) -> int:
        """Insertion index in ``self._cards`` for a drop at ``point``.

        Cards snap to the nearest cell gap: the x within a cell decides whether
        the drop lands before or after that column, so dropping on the right
        half of a cell inserts after it.
        """
        cols = max(1, self._cols)
        n = len(self._cards)
        if n == 0:
            return 0
        row = max(0, point.y // _CELL_HEIGHT)
        col_f = point.x / _CELL_WIDTH
        col = int(max(0, min(cols, round(col_f))))
        idx = int(row) * cols + col
        return max(0, min(n, idx))

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
