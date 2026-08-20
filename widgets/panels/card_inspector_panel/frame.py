"""UI construction for the card inspector panel.

Displays detailed card information: card image, metadata, oracle text, and
navigation through different printings.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx

from utils.constants import (
    CARD_IMAGE_COST_MIN_HEIGHT,
    CARD_IMAGE_DISPLAY_HEIGHT,
    CARD_IMAGE_DISPLAY_WIDTH,
    CARD_IMAGE_NAV_BUTTON_SIZE,
    CARD_IMAGE_PRINTING_LABEL_MIN_WIDTH,
    CARD_IMAGE_TEXT_MIN_HEIGHT,
    DARK_PANEL,
    LIGHT_TEXT,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    SUBDUED_TEXT,
)
from widgets.checkbox import DarkCheckBox
from widgets.mana_icon_factory import ManaIconFactory
from widgets.panels.card_image_display import CardImageDisplay
from widgets.panels.card_inspector_panel.handlers import CardInspectorPanelHandlersMixin
from widgets.panels.card_inspector_panel.properties import CardInspectorPanelPropertiesMixin
from widgets.panels.mana_rich_text_ctrl import ManaSymbolRichCtrl
from widgets.stylize import apply_type_level, stylize_button, stylize_checkbox

if TYPE_CHECKING:
    from repositories.card_repository import CardDataManager
    from services.image_service import CardImageRequest


class CardInspectorPanel(
    CardInspectorPanelHandlersMixin,
    CardInspectorPanelPropertiesMixin,
    wx.Panel,
):
    """Panel that displays detailed information about a selected card."""

    def __init__(
        self,
        parent: wx.Window,
        controller: Any,
        card_manager: CardDataManager | None = None,
        mana_icons: ManaIconFactory | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.controller = controller
        self.card_manager = card_manager
        self.mana_icons = mana_icons or ManaIconFactory()

        # State
        self.active_zone: str | None = None
        self.inspector_printings: list[dict[str, Any]] = []
        self.inspector_current_printing: int = 0
        self.inspector_current_card_name: str | None = None
        self.printing_label_width: int = 0
        self.image_cache = controller.get_image_cache()
        self.bulk_data_by_name: dict[str, list[dict[str, Any]]] | None = None
        self._image_available = False
        self._loading_printing = False
        self._image_request_handler: Callable[[CardImageRequest], None] | None = None
        self._selected_card_handler: Callable[[CardImageRequest | None], None] | None = None
        self._printings_request_handler: Callable[[str], None] | None = None
        self._printing_changed_handler: Callable[[dict[str, Any] | None], None] | None = None
        # Fired only on user-driven printing changes (prev/next/save) so the
        # board art + persistence follow the chosen printing (issue #792).
        self._printing_selected_handler: Callable[[dict[str, Any], bool], None] | None = None
        # The printing the focused card should open on (issue #792, part 1b).
        self.inspector_selection: dict[str, Any] | None = None
        # When True, every scrolled-to printing is persisted immediately; when
        # False the explicit "Save art" button persists the current printing.
        self._autosave_printing: bool = False
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
        sizer.Add(content, 1, wx.EXPAND | wx.ALL, SPACE_SM)

        # Left column: Card image and printing navigation
        self.image_column_panel = wx.Panel(self)
        self.image_column_panel.SetBackgroundColour(DARK_PANEL)
        image_column = wx.BoxSizer(wx.VERTICAL)
        self.image_column_panel.SetSizer(image_column)
        content.Add(self.image_column_panel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_MD)

        # Card image display
        self.card_image_display = CardImageDisplay(
            self.image_column_panel,
            width=CARD_IMAGE_DISPLAY_WIDTH,
            height=CARD_IMAGE_DISPLAY_HEIGHT,
        )
        image_column.Add(self.card_image_display, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, SPACE_XS)
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
        image_text_sizer.Add(self.image_text_ctrl, 1, wx.EXPAND | wx.ALL, SPACE_XS)
        image_column.Add(self.image_text_panel, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, SPACE_XS)
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
        self.nav_panel.SetMinSize((image_width, nav_btn_size.GetHeight() + SPACE_XS))
        self.nav_panel.SetMaxSize((image_width, -1))

        self.prev_btn = wx.Button(self.nav_panel, label="◀", size=nav_btn_size)
        # Pager arrows are navigation chrome sitting directly under the card art.
        # They are also the app's most-disabled buttons (most cards have one
        # printing), and a disabled accent fill was C-b in issue #962.
        stylize_button(self.prev_btn, kind="ghost", surface="panel")
        self.prev_btn.Bind(wx.EVT_BUTTON, self._on_prev_printing)
        nav_sizer.Add(self.prev_btn, 0, wx.RIGHT, SPACE_XS)

        self.printing_label_width = max(
            CARD_IMAGE_PRINTING_LABEL_MIN_WIDTH,
            image_width - (nav_btn_size.GetWidth() * 2) - (SPACE_MD),
        )
        self.printing_label = wx.StaticText(self.nav_panel, label="")
        self.printing_label.SetMinSize((self.printing_label_width, -1))
        self.printing_label.SetMaxSize((self.printing_label_width, -1))
        self.printing_label.SetForegroundColour(SUBDUED_TEXT)
        nav_sizer.Add(self.printing_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_CENTER)

        self.loading_label = wx.StaticText(self.nav_panel, label="Loading printing…")
        self.loading_label.SetForegroundColour(SUBDUED_TEXT)
        nav_sizer.Add(self.loading_label, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, SPACE_SM)
        self.loading_label.Hide()

        self.next_btn = wx.Button(self.nav_panel, label="▶", size=nav_btn_size)
        stylize_button(self.next_btn, kind="ghost", surface="panel")
        self.next_btn.Bind(wx.EVT_BUTTON, self._on_next_printing)
        nav_sizer.Add(self.next_btn, 0, wx.LEFT, SPACE_XS)

        image_column.Add(self.nav_panel, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, SPACE_SM)
        self.nav_panel.Hide()  # Hidden by default

        # Save-art controls (issue #792, part 2): an "auto-save" checkmark that
        # persists each scrolled-to printing, or an explicit "Save art" button
        # shown when auto-save is off. Only visible while a card has multiple
        # printings to choose between (mirrors nav_panel).
        self.save_panel = wx.Panel(self.image_column_panel)
        self.save_panel.SetBackgroundColour(DARK_PANEL)
        save_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.save_panel.SetSizer(save_sizer)

        self.autosave_checkbox = DarkCheckBox(self.save_panel, label="Auto-save art")
        stylize_checkbox(self.autosave_checkbox, surface="panel", tone="secondary")
        self.autosave_checkbox.SetToolTip("Persist each printing you scroll to for this card")
        self.autosave_checkbox.Bind(wx.EVT_CHECKBOX, self._on_autosave_toggle)
        save_sizer.Add(self.autosave_checkbox, 0, wx.ALIGN_CENTER_VERTICAL)

        self.save_art_btn = wx.Button(self.save_panel, label="Save art", style=wx.BU_EXACTFIT)
        stylize_button(self.save_art_btn, kind="secondary")
        self.save_art_btn.SetToolTip("Save the current printing as this card's art")
        self.save_art_btn.Bind(wx.EVT_BUTTON, self._on_save_printing)
        save_sizer.Add(self.save_art_btn, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, SPACE_SM)

        image_column.Add(self.save_panel, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, SPACE_XS)
        self.save_panel.Hide()  # Hidden until a card has printings to choose from

        # Right column: Card details
        self.details_panel = wx.Panel(self)
        self.details_panel.SetBackgroundColour(DARK_PANEL)
        details = wx.BoxSizer(wx.VERTICAL)
        self.details_panel.SetSizer(details)
        content.Add(self.details_panel, 1, wx.EXPAND)

        # Card name
        self.name_label = wx.StaticText(self.details_panel, label="Select a card to inspect.")
        # heading rather than title: the inspector column is ~260px wide and a
        # 15pt card name wraps to three lines there (that width problem is
        # phase 8's; this just does not make it worse).
        apply_type_level(self.name_label, "heading")
        self.name_label.SetForegroundColour(LIGHT_TEXT)
        details.Add(self.name_label, 0, wx.BOTTOM, SPACE_XS)

        # Mana cost container
        self.cost_container = wx.Panel(self.details_panel)
        self.cost_container.SetBackgroundColour(DARK_PANEL)
        self.cost_container.SetMinSize((-1, CARD_IMAGE_COST_MIN_HEIGHT))
        self.cost_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cost_container.SetSizer(self.cost_sizer)
        details.Add(self.cost_container, 0, wx.EXPAND | wx.BOTTOM, SPACE_XS)

        # Type line
        self.type_label = wx.StaticText(self.details_panel, label="")
        self.type_label.SetForegroundColour(SUBDUED_TEXT)
        details.Add(self.type_label, 0, wx.BOTTOM, SPACE_XS)

        # Stats (mana value, P/T, colors, zone)
        self.stats_label = wx.StaticText(self.details_panel, label="")
        self.stats_label.SetForegroundColour(LIGHT_TEXT)
        details.Add(self.stats_label, 0, wx.BOTTOM, SPACE_XS)

        # Oracle text
        self.text_ctrl = ManaSymbolRichCtrl(
            self.details_panel,
            self.mana_icons,
            readonly=True,
            multiline=True,
        )
        self.text_ctrl.SetMinSize((-1, CARD_IMAGE_TEXT_MIN_HEIGHT))
        details.Add(self.text_ctrl, 1, wx.EXPAND | wx.TOP, SPACE_XS)

        self._apply_fixed_sizing(image_width, nav_btn_size)

    def _apply_fixed_sizing(self, image_width: int, nav_btn_size: wx.Size) -> None:
        image_height = getattr(self.card_image_display, "image_height", CARD_IMAGE_DISPLAY_HEIGHT)
        nav_height = nav_btn_size.GetHeight() + SPACE_XS
        # Reserve room for the save-art controls (issue #792) so they aren't
        # clipped by the otherwise fixed-height image column.
        save_height = self.save_panel.GetBestSize().GetHeight() + SPACE_XS
        image_column_height = image_height + (SPACE_SM) + nav_height + save_height + SPACE_SM
        column_width = image_width + SPACE_MD + SPACE_SM

        self.image_column_panel.SetMinSize((column_width, image_column_height))
        self.image_column_panel.SetMaxSize((column_width, image_column_height))
        self.details_panel.SetMinSize((column_width + SPACE_SM, image_height))
        self.details_panel.SetMaxSize((column_width + SPACE_SM, -1))

        panel_width = column_width + SPACE_MD
        panel_height = image_column_height + SPACE_MD
        self.SetMinSize((panel_width, panel_height))
        self.SetMaxSize((panel_width, -1))
