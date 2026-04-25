"""UI construction for the sideboard card selector panel."""

from __future__ import annotations

from typing import Any

import wx
import wx.lib.scrolledpanel as scrolled

from utils.constants import DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.constants.colors import FLEX_SLOT_HIGHLIGHT_COLOR
from widgets.panels.sideboard_card_selector.handlers import SideboardCardSelectorHandlersMixin
from widgets.panels.sideboard_card_selector.properties import (
    SideboardCardSelectorPropertiesMixin,
)


class SideboardCardSelector(
    SideboardCardSelectorHandlersMixin,
    SideboardCardSelectorPropertiesMixin,
    wx.Panel,
):
    """A panel that displays cards with quantity controls for sideboard planning."""

    def __init__(
        self,
        parent: wx.Window,
        title: str,
        available_cards: list[dict[str, Any]],
        flex_slots: list[str] | None = None,
        locale: str | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)
        self._locale = locale
        self.flex_slots: set[str] = set(flex_slots) if flex_slots else set()

        self.available_cards = available_cards
        self.selected_cards: dict[str, int] = {}

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        title_label = wx.StaticText(self, label=title)
        title_label.SetForegroundColour(LIGHT_TEXT)
        title_label.SetFont(title_label.GetFont().Bold())
        sizer.Add(title_label, 0, wx.ALL, 4)

        self.count_label = wx.StaticText(
            self, label=self._t("guide.selector.cards_selected", count=0)
        )
        self.count_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.count_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        self.scroll_panel = scrolled.ScrolledPanel(self, style=wx.VSCROLL)
        self.scroll_panel.SetBackgroundColour(DARK_ALT)
        self.scroll_panel.SetupScrolling(scroll_x=False, scroll_y=True)

        self.card_sizer = wx.BoxSizer(wx.VERTICAL)
        self.scroll_panel.SetSizer(self.card_sizer)
        sizer.Add(self.scroll_panel, 1, wx.EXPAND | wx.ALL, 4)

        self._build_card_list()

    def _build_card_list(self) -> None:
        self.card_sizer.Clear(delete_windows=True)
        self.card_widgets: dict[str, tuple[wx.StaticText, wx.Panel]] = {}

        for card in self.available_cards:
            card_name = card["name"]
            max_qty = card["qty"]
            is_flex = card_name in self.flex_slots

            row_panel = wx.Panel(self.scroll_panel)
            row_bg = wx.Colour(*FLEX_SLOT_HIGHLIGHT_COLOR) if is_flex else DARK_ALT
            row_panel.SetBackgroundColour(row_bg)
            row_sizer = wx.BoxSizer(wx.HORIZONTAL)
            row_panel.SetSizer(row_sizer)

            qty_label = wx.StaticText(row_panel, label="  0", size=(30, -1), style=wx.ALIGN_RIGHT)
            qty_label.SetForegroundColour(LIGHT_TEXT)
            row_sizer.Add(qty_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

            btn_panel = wx.Panel(row_panel)
            btn_panel.SetBackgroundColour(row_bg)
            btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
            btn_panel.SetSizer(btn_sizer)

            inc_btn = wx.Button(btn_panel, label="+", size=(28, 28))
            inc_btn.Bind(
                wx.EVT_BUTTON,
                lambda evt, name=card_name, max_q=max_qty: self._increment(name, max_q),
            )
            btn_sizer.Add(inc_btn, 0)

            dec_btn = wx.Button(btn_panel, label="−", size=(28, 28))
            dec_btn.Bind(wx.EVT_BUTTON, lambda evt, name=card_name: self._decrement(name))
            btn_sizer.Add(dec_btn, 0, wx.LEFT, 2)

            zero_btn = wx.Button(btn_panel, label="↓", size=(28, 28))
            zero_btn.SetToolTip("Set to 0")
            zero_btn.Bind(wx.EVT_BUTTON, lambda evt, name=card_name: self._set_zero(name))
            btn_sizer.Add(zero_btn, 0, wx.LEFT, 2)

            max_btn = wx.Button(btn_panel, label="↑", size=(28, 28))
            max_btn.SetToolTip(f"Set to max ({max_qty})")
            max_btn.Bind(
                wx.EVT_BUTTON, lambda evt, name=card_name, max_q=max_qty: self._set_max(name, max_q)
            )
            btn_sizer.Add(max_btn, 0, wx.LEFT, 2)

            row_sizer.Add(btn_panel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

            flex_tag = " [flex]" if is_flex else ""
            name_label = wx.StaticText(row_panel, label=f"{card_name} (max {max_qty}){flex_tag}")
            name_label.SetForegroundColour(LIGHT_TEXT)
            row_sizer.Add(name_label, 1, wx.ALIGN_CENTER_VERTICAL)

            self.card_sizer.Add(row_panel, 0, wx.EXPAND | wx.BOTTOM, 2)
            self.card_widgets[card_name] = (qty_label, row_panel)

        self.scroll_panel.Layout()
        self.scroll_panel.SetupScrolling(scroll_x=False, scroll_y=True)
        self._update_count()
