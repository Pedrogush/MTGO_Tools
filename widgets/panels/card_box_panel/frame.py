"""UI construction for the card box panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx

from utils.constants import (
    DARK_ALT,
    DECK_CARD_BADGE_PADDING,
    DECK_CARD_BASE_FONT_SIZE,
    DECK_CARD_BUTTON_MARGIN,
    DECK_CARD_HEIGHT,
    DECK_CARD_WIDTH,
    LIGHT_TEXT,
)
from utils.mana_icon_factory import ManaIconFactory
from widgets.panels.card_box_panel.handlers import CardBoxPanelHandlersMixin
from widgets.panels.card_box_panel.properties import CardBoxPanelPropertiesMixin


class CardBoxPanel(CardBoxPanelHandlersMixin, CardBoxPanelPropertiesMixin, wx.Panel):
    _template_cache: dict[tuple[str, str, tuple[int, int, int]], wx.Bitmap] = {}

    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        card: dict[str, Any],
        icon_factory: ManaIconFactory,
        get_metadata: Callable[[str], dict[str, Any] | None],
        owned_status: Callable[[str, int], tuple[str, tuple[int, int, int]]],
        on_delta: Callable[[str, str, int], None],
        on_remove: Callable[[str, str], None],
        on_select: Callable[[str, dict[str, Any], CardBoxPanel], None],
        on_hover: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.zone = zone
        self.card = card
        self._icon_factory = icon_factory
        self._get_metadata = get_metadata
        self._owned_status = owned_status
        self._on_delta = on_delta
        self._on_remove = on_remove
        self._on_select = on_select
        self._on_hover = on_hover
        self._active = False
        self._mana_cost = ""
        self._card_color = ManaIconFactory.FALLBACK_COLORS["c"]
        self._mana_cost_bitmap: wx.Bitmap | None = None
        self._template_bitmap: wx.Bitmap | None = None
        self._card_bitmap: wx.Bitmap | None = None
        self._image_available = False
        self._image_attempted = False
        self._image_generation: int = 0
        self._image_name_candidates: list[str] = []

        self.SetBackgroundColour(DARK_ALT)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((DECK_CARD_WIDTH, DECK_CARD_HEIGHT))
        self.SetMaxSize((DECK_CARD_WIDTH, DECK_CARD_HEIGHT))
        self.Bind(wx.EVT_PAINT, self._on_paint)

        layout = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(layout)

        base_font = wx.Font(
            DECK_CARD_BASE_FONT_SIZE, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL
        )

        # Quantity label
        badge_row = wx.BoxSizer(wx.HORIZONTAL)
        self.qty_label = wx.StaticText(self, label=str(card["qty"]))
        self.qty_label.SetForegroundColour(LIGHT_TEXT)
        self.qty_label.SetFont(base_font)
        self.qty_label.SetBackgroundColour(DARK_ALT)
        badge_row.Add(self.qty_label, 0, wx.ALL, DECK_CARD_BADGE_PADDING)
        badge_row.AddStretchSpacer(1)
        layout.Add(badge_row, 0, wx.EXPAND)

        layout.AddStretchSpacer(1)

        # Button panel
        self.button_panel = wx.Panel(self)
        self.button_panel.SetBackgroundColour(DARK_ALT)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.button_panel.SetSizer(btn_sizer)
        add_btn = wx.Button(self.button_panel, label="+")
        self._style_action_button(add_btn)
        add_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_delta(self.zone, self.card["name"], 1))
        btn_sizer.Add(add_btn, 0)
        sub_btn = wx.Button(self.button_panel, label="−")
        self._style_action_button(sub_btn)
        sub_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_delta(self.zone, self.card["name"], -1))
        btn_sizer.Add(sub_btn, 0, wx.LEFT, 2)
        rem_btn = wx.Button(self.button_panel, label="×")
        self._style_action_button(rem_btn)
        rem_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_remove(self.zone, self.card["name"]))
        btn_sizer.Add(rem_btn, 0, wx.LEFT, 2)
        buttons_row = wx.BoxSizer(wx.HORIZONTAL)
        buttons_row.Add(self.button_panel, 0, wx.LEFT | wx.BOTTOM, DECK_CARD_BUTTON_MARGIN)
        buttons_row.AddStretchSpacer(1)
        layout.Add(buttons_row, 0, wx.EXPAND)
        self.button_panel.Hide()

        self._update_card_state(card)

        # Bind click events to all widgets so clicks anywhere on the card work
        self._bind_click_targets([self, self.qty_label])
        self._bind_hover_targets([self, self.qty_label, self.button_panel])
