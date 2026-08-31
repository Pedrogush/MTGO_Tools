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
* Each card's copy count is drawn as a stack of filled dots in a thin strip
  down its left edge, coloured by owned status (#987); counts too high to
  read as dots fall back to a numeral chip.
* Inline ``+`` / ``−`` / ``×`` controls are drawn (not native buttons) as
  hit-zones on the hovered/selected card, hit-tested on click — the same
  drawn-control model the table view's actions column uses.
* When a card image hasn't loaded yet, a placeholder template (card-colour
  background, mana-cost badge, wrapped name) is drawn, exactly as before.

The view is assembled in the package's view-collaborator style: ``DeckGridView``
holds all instance state and the public ``CardTablePanel``-facing API, and mixes
in four thin collaborators for the distinct bands — geometry
(:mod:`grid_layout`), the async image/template pipeline (:mod:`grid_images`), the
cached canvas + drawing primitives (:mod:`grid_render`) and the event/selection/
drag interaction layer (:mod:`grid_interaction`). ``wx.ScrolledWindow`` is kept
last in the MRO and every attribute the mixins read is declared here in
``__init__`` on the concrete class.
"""

from __future__ import annotations

from collections.abc import Callable
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Any

import wx

from utils.constants import CARD_VIEW_SCROLL_RATE, DARK_PANEL
from widgets.mana_icon_factory import ManaIconFactory
from widgets.panels.card_table_panel import edge_fade, scroll_perf, scroll_snap
from widgets.panels.card_table_panel.grid_images import GridImagesMixin
from widgets.panels.card_table_panel.grid_interaction import GridInteractionMixin
from widgets.panels.card_table_panel.grid_layout import (
    _CELL_HEIGHT,
    _DEFAULT_COLUMNS,
    GridLayoutMixin,
)
from widgets.panels.card_table_panel.grid_render import GridRenderMixin
from widgets.panels.card_table_panel.marquee import MarqueeController
from widgets.panels.card_table_panel.pile_view import _ImageCache
from widgets.stylize import stylize_scrollable


class DeckGridView(
    GridLayoutMixin,
    GridImagesMixin,
    GridRenderMixin,
    GridInteractionMixin,
    wx.ScrolledWindow,
):
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
        get_printing_image: Callable[[str], Path | None] | None = None,
        on_activate: Callable[[str], None] | None = None,
    ) -> None:
        # FULL_REPAINT_ON_RESIZE puts this window on wx's CS_HREDRAW|CS_VREDRAW
        # class, so MSW invalidates the whole client on a resize instead of
        # keeping the bits it can. Without it a live sash drag resizes the view
        # faster than it can repaint and every skipped repaint leaves another
        # edge-fade band behind, which is the solid dark wash of #983.
        super().__init__(parent, style=wx.VSCROLL | wx.FULL_REPAINT_ON_RESIZE)
        self.zone = zone
        self._get_metadata = get_metadata
        self._get_card_image = get_card_image
        # Optional printing-aware image resolver (issue #792): when a card has a
        # chosen printing, this returns that printing's image path (and may queue
        # its download); ``None`` means "no specific printing — use the default".
        self._get_printing_image = get_printing_image
        self._owned_status = owned_status
        self._icon_factory = icon_factory
        self._on_select = on_select
        self._on_hover = on_hover
        self._on_delta = on_delta
        self._on_remove = on_remove
        self._on_zone_transfer = on_zone_transfer
        # Double-click on a card (issue #1027). What it *means* is decided by
        # the frame -- take a copy out in normal editing, move a copy across
        # zones while a sideboard guide is being recorded -- so the view only
        # reports which card was activated.
        self._on_activate = on_activate

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
        stylize_scrollable(self)
        # AutoBufferedPaintDC requires BG_STYLE_PAINT so wx skips its own
        # erase-background draw and _on_paint owns the whole client area.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        # 1px scroll units (shared with the pile view) give the scrollbar thumb
        # single-pixel granularity; the wheel handler then scrolls a larger
        # per-notch step so the wheel still moves a useful distance.
        self.SetScrollRate(CARD_VIEW_SCROLL_RATE, CARD_VIEW_SCROLL_RATE)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_left_dclick)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)
        # A thumb drag / arrow / page moves the origin without going through the
        # wheel handler, so it settles onto a row boundary here instead (S5).
        self.Bind(wx.EVT_SCROLLWIN, self._on_scrollwin)

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

    # ----- scroll snapping (S5) -----
    def scroll_snap_step(self) -> tuple[int, int]:
        """One grid row -- card plus the gap under it -- starting at the top."""
        return _CELL_HEIGHT, 0

    def scroll_content_height(self) -> int:
        """The laid-out content height.

        Not ``GetVirtualSize``: wx inflates that to the client size, which would
        make a one-row deck report content past the bottom edge and draw a fade
        over nothing.
        """
        return ceil(len(self._cards) / max(1, self._cols)) * _CELL_HEIGHT

    def Scroll(self, *args: Any) -> None:
        """Move the origin without wx's scroll blit -- **every** caller (#983).

        Overriding ``Scroll`` rather than asking call sites to use
        :func:`scroll_snap.scroll_viewport` is deliberate. The blit strands the
        edge fade, and the callers that move this view's origin are spread wide:
        the wheel, the scrollbar, drag-reorder and marquee autoscroll,
        scroll-into-view, the reset in ``set_cards`` -- plus the automation
        harness, which parks the origin before a measured burst. Every one of
        them is a way to reintroduce the bug, and a rule that lives at the call
        site is a rule that the next call site will not know about.

        wx itself still reaches ``wxScrollHelper::DoScroll`` from C++ for a
        scrollbar thumb drag and for ``ScrollLines``; that path cannot be
        intercepted from Python (``ScrollWindow`` is not virtual through the
        wxPython bindings -- measured), and it is what
        :func:`edge_fade.begin_viewport_paint` is the backstop for.
        """
        if len(args) == 1:
            point = args[0]
            x, y = point[0], point[1]
        else:
            x, y = args
        scroll_snap.scroll_viewport(self, x, y)

    def _on_scrollwin(self, event: wx.ScrollWinEvent) -> None:
        # Shared with the pile view so both settle identically (see scroll_snap).
        scroll_snap.handle_scrollwin(self, event)

    # ----- paint orchestration -----
    def _on_paint(self, _event: wx.PaintEvent) -> None:
        t0 = perf_counter()
        # Must run before the PaintDC exists: it is what widens this paint's
        # clip to the whole client when the viewport has moved under the edge
        # fade (#983). Its result says the update region can no longer be
        # trusted to cull with.
        whole_client = edge_fade.begin_viewport_paint(self)
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
            for idx in self._visible_card_indices(whole_client):
                self._draw_card(dc, self._card_rect(idx), self._cards[idx])
        if self._drag_active:
            self._draw_drop_indicator(dc)
            self._draw_drag_ghost(dc)
        # S5: dissolve whichever edge has content past it, so the partial row
        # reads as "there is more" instead of as a clipped render.
        edge_fade.draw_edge_fades(self, dc, DARK_PANEL)
        # Stamp the origin this paint just rendered (and how long it took) so the
        # wheel-latency harness can tell when the view caught up to the scroll
        # input (no-op unless the perf recorder is enabled).
        scroll_perf.record_paint(self, *self.GetViewStart(), dur_ms=(perf_counter() - t0) * 1000.0)
