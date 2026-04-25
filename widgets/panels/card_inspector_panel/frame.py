"""UI construction for the card inspector panel.

Displays detailed card information: card image, metadata, oracle text, and
navigation through different printings.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx

from utils.card_data import CardDataManager
from utils.card_images import CardImageRequest, get_cache
from utils.constants import (
    CARD_IMAGE_COST_MIN_HEIGHT,
    CARD_IMAGE_DISPLAY_HEIGHT,
    CARD_IMAGE_DISPLAY_WIDTH,
    CARD_IMAGE_NAV_BUTTON_SIZE,
    CARD_IMAGE_PRINTING_LABEL_MIN_WIDTH,
    CARD_IMAGE_TEXT_MIN_HEIGHT,
    DARK_PANEL,
    LIGHT_TEXT,
    PADDING_BASE,
    PADDING_MD,
    PADDING_SM,
    PADDING_XL,
    SUBDUED_TEXT,
)
from utils.mana_icon_factory import ManaIconFactory
from utils.stylize import stylize_button
from widgets.panels.card_image_display import CardImageDisplay
from widgets.panels.card_inspector_panel.handlers import CardInspectorPanelHandlersMixin
from widgets.panels.card_inspector_panel.properties import CardInspectorPanelPropertiesMixin
from widgets.panels.mana_rich_text_ctrl import ManaSymbolRichCtrl


class CardInspectorPanel(
    CardInspectorPanelHandlersMixin,
    CardInspectorPanelPropertiesMixin,
    wx.Panel,
):
    """Panel that displays detailed information about a selected card."""

    def __init__(
        self,
        parent: wx.Window,
        card_manager: CardDataManager | None = None,
        mana_icons: ManaIconFactory | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.card_manager = card_manager
        self.mana_icons = mana_icons or ManaIconFactory()

        # State
        self.active_zone: str | None = None
        self.inspector_printings: list[dict[str, Any]] = []
        self.inspector_current_printing: int = 0
        self.inspector_current_card_name: str | None = None
        self.printing_label_width: int = 0
        self.image_cache = get_cache()
        self.bulk_data_by_name: dict[str, list[dict[str, Any]]] | None = None
        self._image_available = False
        self._loading_printing = False
        self._image_request_handler: Callable[[CardImageRequest], None] | None = None
        self._selected_card_handler: Callable[[CardImageRequest | None], None] | None = None
        self._printings_request_handler: Callable[[str], None] | None = None
        self._printings_request_inflight: str | None = None
        self._has_selection = False
        self._failed_image_requests: set[tuple[str, str]] = set()
        self._image_request_name: str | None = None
        self._image_lookup_gen: int = 0

        self._build_ui()
        self.reset()

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        content = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(content, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Left column: Card image and printing navigation
        self.image_column_panel = wx.Panel(self)
        self.image_column_panel.SetBackgroundColour(DARK_PANEL)
        image_column = wx.BoxSizer(wx.VERTICAL)
        self.image_column_panel.SetSizer(image_column)
        content.Add(self.image_column_panel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_XL)

        # Card image display
        self.card_image_display = CardImageDisplay(
            self.image_column_panel,
            width=CARD_IMAGE_DISPLAY_WIDTH,
            height=CARD_IMAGE_DISPLAY_HEIGHT,
        )
        image_column.Add(
            self.card_image_display, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, PADDING_SM
        )
        self.image_text_panel = wx.Panel(self.image_column_panel)
        self.image_text_panel.SetBackgroundColour(DARK_PANEL)
        self.image_text_panel.SetMinSize((CARD_IMAGE_DISPLAY_WIDTH, CARD_IMAGE_DISPLAY_HEIGHT))
        image_text_sizer = wx.BoxSizer(wx.VERTICAL)
        self.image_text_panel.SetSizer(image_text_sizer)
        self.image_text_ctrl = ManaSymbolRichCtrl(
            self.image_text_panel,
            self.mana_icons,
            readonly=True,
            multiline=True,
        )
        image_text_sizer.Add(self.image_text_ctrl, 1, wx.EXPAND | wx.ALL, PADDING_SM)
        image_column.Add(self.image_text_panel, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, PADDING_SM)
        self.image_text_panel.Hide()

        # Printing navigation panel
        self.nav_panel = wx.Panel(self.image_column_panel)
        self.nav_panel.SetBackgroundColour(DARK_PANEL)
        nav_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.nav_panel.SetSizer(nav_sizer)

        try:
            nav_btn_size = self.FromDIP(wx.Size(*CARD_IMAGE_NAV_BUTTON_SIZE))
        except AttributeError:
            nav_btn_size = wx.Size(*CARD_IMAGE_NAV_BUTTON_SIZE)

        # Keep the navigation rail aligned with the card image width so buttons don't jump
        image_width = getattr(self.card_image_display, "image_width", CARD_IMAGE_DISPLAY_WIDTH)
        self.nav_panel.SetMinSize((image_width, nav_btn_size.GetHeight() + PADDING_SM))
        self.nav_panel.SetMaxSize((image_width, -1))

        self.prev_btn = wx.Button(self.nav_panel, label="◀", size=nav_btn_size)
        stylize_button(self.prev_btn)
        self.prev_btn.Bind(wx.EVT_BUTTON, self._on_prev_printing)
        nav_sizer.Add(self.prev_btn, 0, wx.RIGHT, PADDING_SM)

        self.printing_label_width = max(
            CARD_IMAGE_PRINTING_LABEL_MIN_WIDTH,
            image_width - (nav_btn_size.GetWidth() * 2) - (PADDING_BASE * 2),
        )
        self.printing_label = wx.StaticText(self.nav_panel, label="")
        self.printing_label.SetMinSize((self.printing_label_width, -1))
        self.printing_label.SetMaxSize((self.printing_label_width, -1))
        self.printing_label.SetForegroundColour(SUBDUED_TEXT)
        nav_sizer.Add(self.printing_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_CENTER)

        self.loading_label = wx.StaticText(self.nav_panel, label="Loading printing…")
        self.loading_label.SetForegroundColour(SUBDUED_TEXT)
        nav_sizer.Add(self.loading_label, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, PADDING_MD)
        self.loading_label.Hide()

        self.next_btn = wx.Button(self.nav_panel, label="▶", size=nav_btn_size)
        stylize_button(self.next_btn)
        self.next_btn.Bind(wx.EVT_BUTTON, self._on_next_printing)
        nav_sizer.Add(self.next_btn, 0, wx.LEFT, PADDING_SM)

        image_column.Add(self.nav_panel, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, PADDING_MD)
        self.nav_panel.Hide()  # Hidden by default

        # Right column: Card details
        self.details_panel = wx.Panel(self)
        self.details_panel.SetBackgroundColour(DARK_PANEL)
        details = wx.BoxSizer(wx.VERTICAL)
        self.details_panel.SetSizer(details)
        content.Add(self.details_panel, 1, wx.EXPAND)

        # Card name
        self.name_label = wx.StaticText(self.details_panel, label="Select a card to inspect.")
        name_font = self.name_label.GetFont()
        name_font.SetPointSize(name_font.GetPointSize() + 2)
        name_font.MakeBold()
        self.name_label.SetFont(name_font)
        self.name_label.SetForegroundColour(LIGHT_TEXT)
        details.Add(self.name_label, 0, wx.BOTTOM, PADDING_SM)

        # Mana cost container
        self.cost_container = wx.Panel(self.details_panel)
        self.cost_container.SetBackgroundColour(DARK_PANEL)
        self.cost_container.SetMinSize((-1, CARD_IMAGE_COST_MIN_HEIGHT))
        self.cost_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cost_container.SetSizer(self.cost_sizer)
        details.Add(self.cost_container, 0, wx.EXPAND | wx.BOTTOM, PADDING_SM)

        # Type line
        self.type_label = wx.StaticText(self.details_panel, label="")
        self.type_label.SetForegroundColour(SUBDUED_TEXT)
        details.Add(self.type_label, 0, wx.BOTTOM, PADDING_SM)

        # Stats (mana value, P/T, colors, zone)
        self.stats_label = wx.StaticText(self.details_panel, label="")
        self.stats_label.SetForegroundColour(LIGHT_TEXT)
        details.Add(self.stats_label, 0, wx.BOTTOM, PADDING_SM)

        # Oracle text
        self.text_ctrl = ManaSymbolRichCtrl(
            self.details_panel,
            self.mana_icons,
            readonly=True,
            multiline=True,
        )
        self.text_ctrl.SetMinSize((-1, CARD_IMAGE_TEXT_MIN_HEIGHT))
        details.Add(self.text_ctrl, 1, wx.EXPAND | wx.TOP, PADDING_SM)

        self._apply_fixed_sizing(image_width, nav_btn_size)

    def _apply_fixed_sizing(self, image_width: int, nav_btn_size: wx.Size) -> None:
        image_height = getattr(self.card_image_display, "image_height", CARD_IMAGE_DISPLAY_HEIGHT)
        nav_height = nav_btn_size.GetHeight() + PADDING_SM
        image_column_height = image_height + (PADDING_SM * 2) + nav_height + PADDING_MD
        column_width = image_width + PADDING_XL + PADDING_MD

        self.image_column_panel.SetMinSize((column_width, image_column_height))
        self.image_column_panel.SetMaxSize((column_width, image_column_height))
        self.details_panel.SetMinSize((column_width + PADDING_MD, image_height))
        self.details_panel.SetMaxSize((column_width + PADDING_MD, -1))

        panel_width = column_width + PADDING_XL
        panel_height = image_column_height + PADDING_XL
        self.SetMinSize((panel_width, panel_height))
        self.SetMaxSize((panel_width, -1))
