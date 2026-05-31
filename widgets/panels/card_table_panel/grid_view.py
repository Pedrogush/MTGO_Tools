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
from typing import Any

import wx
from PIL import Image as PilImage

from utils.constants import (
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
from widgets.panels.card_table_panel.card_render import (
    build_image_name_candidates,
    resolve_card_color,
)
from widgets.panels.card_table_panel.pile_view import _ImageCache

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

        self._cards: list[dict[str, Any]] = []
        self._selected_name: str | None = None
        self._hover_name: str | None = None
        self._pressed: tuple[str, int] | None = None
        self._cols: int = _DEFAULT_COLUMNS

        self._image_cache = _ImageCache()
        # Per-name load generation so a stale in-flight decode (e.g. of an old
        # image after refresh_image re-downloads) can't overwrite a newer one.
        self._load_gen: dict[str, int] = {}
        # Placeholder bitmaps keyed by name; built lazily, reused across loads.
        self._template_cache: dict[str, wx.Bitmap] = {}

        self.SetBackgroundColour(DARK_PANEL)
        # AutoBufferedPaintDC requires BG_STYLE_PAINT so wx skips its own
        # erase-background draw and _on_paint owns the whole client area.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetScrollRate(20, 20)
        self.SetDoubleBuffered(True)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    # ----- public API consumed by CardTablePanel -----
    def set_cards(self, cards: list[dict[str, Any]], preserve_scroll: bool = False) -> None:
        self._cards = list(cards)
        self._hover_name = None
        self._pressed = None
        self._recompute_layout()
        self._prefetch_images()
        if not preserve_scroll:
            self.Scroll(0, 0)
        self.Refresh()

    def set_selected(self, name: str | None) -> None:
        self._selected_name = name
        self.Refresh()

    def get_selected_name(self) -> str | None:
        return self._selected_name

    def get_selected_card(self) -> dict[str, Any] | None:
        if not self._selected_name:
            return None
        for card in self._cards:
            if card["name"].lower() == self._selected_name.lower():
                return card
        return None

    def focus_card(self, name: str) -> bool:
        """Select ``name`` and scroll it into view. Returns True if found."""
        if not name:
            return False
        for idx, card in enumerate(self._cards):
            if card["name"].lower() == name.lower():
                self._selected_name = card["name"]
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
        return (self._hover_name is not None and lower == self._hover_name.lower()) or (
            self._selected_name is not None and lower == self._selected_name.lower()
        )

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
        self.Refresh()

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
        dc = wx.AutoBufferedPaintDC(self)
        self.PrepareDC(dc)
        dc.SetBackground(wx.Brush(wx.Colour(*DARK_PANEL)))
        dc.Clear()
        for idx, card in enumerate(self._cards):
            self._draw_card(dc, self._card_rect(idx), card)

    def _draw_card(self, dc: wx.DC, rect: wx.Rect, card: dict[str, Any]) -> None:
        name = card["name"]
        bitmap = self._image_cache.get(name)
        if bitmap is not None:
            x = rect.x + (rect.width - bitmap.GetWidth()) // 2
            y = rect.y + (rect.height - bitmap.GetHeight()) // 2
            dc.DrawBitmap(bitmap, x, y, True)
        else:
            dc.DrawBitmap(self._template_for(name), rect.x, rect.y, True)

        is_selected = (
            self._selected_name is not None and name.lower() == self._selected_name.lower()
        )
        self._draw_qty(dc, rect, card, is_selected)

        if is_selected:
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

        if self._selected_name and name.lower() == self._selected_name.lower():
            self._on_select(None)
        else:
            self._on_select(card)

    def _fire_action(self, name: str, slot: int) -> None:
        if slot == 0 and self._on_delta:
            self._on_delta(name, 1)
        elif slot == 1 and self._on_delta:
            self._on_delta(name, -1)
        elif slot == 2 and self._on_remove:
            self._on_remove(name)

    def _on_left_up(self, _event: wx.MouseEvent) -> None:
        if self._pressed is not None:
            self._pressed = None
            self.Refresh()

    def _on_motion(self, event: wx.MouseEvent) -> None:
        point = self._to_logical(event.GetPosition())
        idx = self._hit_test(point)
        hovered = self._cards[idx]["name"] if idx is not None else None
        if hovered == self._hover_name:
            return
        self._hover_name = hovered
        if hovered and self._on_hover and idx is not None:
            self._on_hover(self._cards[idx])
        self.Refresh()

    def _on_leave(self, _event: wx.MouseEvent) -> None:
        if self._hover_name is not None:
            self._hover_name = None
            self.Refresh()
