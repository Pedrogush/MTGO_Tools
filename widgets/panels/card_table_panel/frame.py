"""UI construction for the card table panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx
import wx.lib.scrolledpanel as scrolled

from utils.constants import DARK_PANEL, SUBDUED_TEXT
from utils.mana_icon_factory import ManaIconFactory
from widgets.panels.card_box_panel import CardBoxPanel
from widgets.panels.card_table_panel.handlers import CardTablePanelHandlersMixin
from widgets.panels.card_table_panel.properties import CardTablePanelPropertiesMixin

_EMPTY_STATE_HEADING_SIZE = 13
_EMPTY_STATE_HINT_SIZE = 10
_EMPTY_STATE_HEADING_GAP = 6

_ZONE_EMPTY_HEADING = {
    "main": "No deck loaded",
    "side": "Sideboard is empty",
    "out": "No cards out",
}
_ZONE_EMPTY_HINT = {
    "main": "Select a deck from the list, or load one from file",
}


class CardTablePanel(CardTablePanelHandlersMixin, CardTablePanelPropertiesMixin, wx.Panel):
    GRID_COLUMNS = 4
    GRID_GAP = 8
    POOL_SIZE = 60

    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        icon_factory: ManaIconFactory,
        get_metadata: Callable[[str], dict[str, Any] | None],
        owned_status: Callable[[str, int], tuple[str, tuple[int, int, int]]],
        on_delta: Callable[[str, str, int], None],
        on_remove: Callable[[str, str], None],
        on_add: Callable[[str], None],
        on_select: Callable[[str, dict[str, Any] | None], None],
        on_hover: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.zone = zone
        self.icon_factory = icon_factory
        self._get_metadata = get_metadata
        self._owned_status = owned_status
        self._on_delta = on_delta
        self._on_remove = on_remove
        self._on_add = on_add
        self._on_select = on_select
        self._on_hover = on_hover
        self.cards: list[dict[str, Any]] = []
        self.card_widgets: list[CardBoxPanel] = []
        self._pool: list[CardBoxPanel] = []
        self.active_panel: CardBoxPanel | None = None
        self.selected_name: str | None = None

        self.SetBackgroundColour(DARK_PANEL)
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        header = wx.BoxSizer(wx.HORIZONTAL)
        self.count_label = wx.StaticText(self, label="0 cards")
        self.count_label.SetForegroundColour(SUBDUED_TEXT)
        header.Add(self.count_label, 0, wx.ALIGN_CENTER_VERTICAL)
        header.AddStretchSpacer(1)
        outer.Add(header, 0, wx.EXPAND | wx.BOTTOM, 4)

        # Content area switches between an empty-state hint and the card grid.
        self._content_book = wx.Simplebook(self)
        self._content_book.SetBackgroundColour(DARK_PANEL)

        self._empty_state = self._build_empty_state(self._content_book, zone)
        self._content_book.AddPage(self._empty_state, "empty")

        self.scroller = scrolled.ScrolledPanel(self._content_book, style=wx.VSCROLL)
        self.scroller.SetBackgroundColour(DARK_PANEL)
        self.grid_sizer = wx.WrapSizer(wx.HORIZONTAL)

        # Pre-create POOL_SIZE panels. Visible panels show cards; hidden panels
        # are excluded from layout via sizer.Show(panel, False).
        for _ in range(self.POOL_SIZE):
            cell = CardBoxPanel(
                self.scroller,
                zone,
                {"name": "", "qty": 0},
                icon_factory,
                get_metadata,
                owned_status,
                on_delta,
                on_remove,
                self._handle_card_click,
                on_hover,
            )
            self.grid_sizer.Add(cell, 0, wx.RIGHT | wx.BOTTOM, self.GRID_GAP)
            self.grid_sizer.Show(cell, False)
            self._pool.append(cell)

        self.scroller.SetSizer(self.grid_sizer)
        self.scroller.SetupScrolling(scroll_x=False, scroll_y=True, rate_x=5, rate_y=5)
        self._content_book.AddPage(self.scroller, "cards")

        self._loading_state = self._build_loading_state(self._content_book)
        self._content_book.AddPage(self._loading_state, "loading")

        outer.Add(self._content_book, 1, wx.EXPAND)

    @staticmethod
    def _build_loading_state(parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        sizer.AddStretchSpacer(2)
        label = wx.StaticText(panel, label="")
        label.SetForegroundColour(wx.Colour(*SUBDUED_TEXT))
        label.SetFont(
            wx.Font(
                _EMPTY_STATE_HEADING_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        sizer.Add(label, 0, wx.ALIGN_CENTER_HORIZONTAL)
        sizer.AddStretchSpacer(3)
        panel._label = label  # type: ignore[attr-defined]
        return panel

    @staticmethod
    def _build_empty_state(parent: wx.Window, zone: str) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        heading_text = _ZONE_EMPTY_HEADING.get(zone, "")
        hint_text = _ZONE_EMPTY_HINT.get(zone, "")

        sizer.AddStretchSpacer(2)

        if heading_text:
            heading = wx.StaticText(panel, label=heading_text)
            heading.SetForegroundColour(wx.Colour(*SUBDUED_TEXT))
            heading_font = wx.Font(
                _EMPTY_STATE_HEADING_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
            heading.SetFont(heading_font)
            sizer.Add(
                heading,
                0,
                wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM,
                _EMPTY_STATE_HEADING_GAP,
            )

        if hint_text:
            hint = wx.StaticText(panel, label=hint_text)
            hint.SetForegroundColour(wx.Colour(*(max(c - 40, 0) for c in SUBDUED_TEXT)))
            hint_font = wx.Font(
                _EMPTY_STATE_HINT_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
            hint.SetFont(hint_font)
            sizer.Add(hint, 0, wx.ALIGN_CENTER_HORIZONTAL)

        sizer.AddStretchSpacer(3)
        return panel
