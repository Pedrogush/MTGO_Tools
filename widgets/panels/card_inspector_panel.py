"""
Card Inspector Panel - Displays detailed card information.

Shows card image, metadata, oracle text, and allows navigation through different printings.
"""

from collections.abc import Callable
from typing import Any

import wx
from loguru import logger

from utils.card_data import CardDataManager
from utils.card_images import BULK_DATA_CACHE, CardImageRequest, get_cache, get_card_image
from utils.constants import (
    CARD_IMAGE_COST_MIN_HEIGHT,
    CARD_IMAGE_DISPLAY_HEIGHT,
    CARD_IMAGE_DISPLAY_WIDTH,
    CARD_IMAGE_NAV_BUTTON_SIZE,
    CARD_IMAGE_PRINTING_LABEL_MIN_WIDTH,
    CARD_IMAGE_TEXT_MIN_HEIGHT,
    DARK_PANEL,
    LIGHT_TEXT,
    SUBDUED_TEXT,
    ZONE_TITLES,
)
from utils.mana_icon_factory import ManaIconFactory
from utils.stylize import stylize_button, stylize_textctrl
from widgets.card_image_display import CardImageDisplay


class CardInspectorPanel(wx.Panel):
    """Panel that displays detailed information about a selected card."""

    def __init__(
        self,
        parent: wx.Window,
        card_manager: CardDataManager | None = None,
        mana_icons: ManaIconFactory | None = None,
    ):
        """
        Initialize the card inspector panel.

        Args:
            parent: Parent window
            card_manager: Card data manager for metadata lookups
            mana_icons: Mana icon factory for rendering mana costs
        """
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

        self._build_ui()
        self.reset()

    def _build_ui(self) -> None:
        """Build the panel UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        content = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(content, 1, wx.EXPAND | wx.ALL, 6)

        # Left column: Card image and printing navigation
        self.image_column_panel = wx.Panel(self)
        self.image_column_panel.SetBackgroundColour(DARK_PANEL)
        image_column = wx.BoxSizer(wx.VERTICAL)
        self.image_column_panel.SetSizer(image_column)
        content.Add(self.image_column_panel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)

        # Card image display
        self.card_image_display = CardImageDisplay(
            self.image_column_panel,
            width=CARD_IMAGE_DISPLAY_WIDTH,
            height=CARD_IMAGE_DISPLAY_HEIGHT,
        )
        image_column.Add(self.card_image_display, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 4)

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
        self.nav_panel.SetMinSize((image_width, nav_btn_size.GetHeight() + 4))
        self.nav_panel.SetMaxSize((image_width, -1))

        self.prev_btn = wx.Button(self.nav_panel, label="◀", size=nav_btn_size)
        stylize_button(self.prev_btn)
        self.prev_btn.Bind(wx.EVT_BUTTON, self._on_prev_printing)
        nav_sizer.Add(self.prev_btn, 0, wx.RIGHT, 4)

        self.printing_label_width = max(
            CARD_IMAGE_PRINTING_LABEL_MIN_WIDTH,
            image_width - (nav_btn_size.GetWidth() * 2) - 16,
        )
        self.printing_label = wx.StaticText(self.nav_panel, label="")
        self.printing_label.SetMinSize((self.printing_label_width, -1))
        self.printing_label.SetMaxSize((self.printing_label_width, -1))
        self.printing_label.SetForegroundColour(SUBDUED_TEXT)
        nav_sizer.Add(self.printing_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_CENTER)

        self.loading_label = wx.StaticText(self.nav_panel, label="Loading printing…")
        self.loading_label.SetForegroundColour(SUBDUED_TEXT)
        nav_sizer.Add(self.loading_label, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        self.loading_label.Hide()

        self.next_btn = wx.Button(self.nav_panel, label="▶", size=nav_btn_size)
        stylize_button(self.next_btn)
        self.next_btn.Bind(wx.EVT_BUTTON, self._on_next_printing)
        nav_sizer.Add(self.next_btn, 0, wx.LEFT, 4)

        image_column.Add(self.nav_panel, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 6)
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
        details.Add(self.name_label, 0, wx.BOTTOM, 4)

        # Mana cost container
        self.cost_container = wx.Panel(self.details_panel)
        self.cost_container.SetBackgroundColour(DARK_PANEL)
        self.cost_container.SetMinSize((-1, CARD_IMAGE_COST_MIN_HEIGHT))
        self.cost_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cost_container.SetSizer(self.cost_sizer)
        details.Add(self.cost_container, 0, wx.EXPAND | wx.BOTTOM, 4)

        # Type line
        self.type_label = wx.StaticText(self.details_panel, label="")
        self.type_label.SetForegroundColour(SUBDUED_TEXT)
        details.Add(self.type_label, 0, wx.BOTTOM, 4)

        # Stats (mana value, P/T, colors, zone)
        self.stats_label = wx.StaticText(self.details_panel, label="")
        self.stats_label.SetForegroundColour(LIGHT_TEXT)
        details.Add(self.stats_label, 0, wx.BOTTOM, 4)

        # Oracle text
        self.text_ctrl = wx.TextCtrl(
            self.details_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.NO_BORDER,
        )
        stylize_textctrl(self.text_ctrl, multiline=True)
        self.text_ctrl.SetMinSize((-1, CARD_IMAGE_TEXT_MIN_HEIGHT))
        details.Add(self.text_ctrl, 1, wx.EXPAND | wx.TOP, 4)

        self._apply_fixed_sizing(image_width, nav_btn_size)

    def _apply_fixed_sizing(self, image_width: int, nav_btn_size: wx.Size) -> None:
        image_height = getattr(self.card_image_display, "image_height", CARD_IMAGE_DISPLAY_HEIGHT)
        nav_height = nav_btn_size.GetHeight() + 4
        image_column_height = image_height + 8 + nav_height + 6

        self.image_column_panel.SetMinSize((image_width, image_column_height))
        self.image_column_panel.SetMaxSize((image_width, image_column_height))
        self.details_panel.SetMinSize((image_width, image_height))
        self.details_panel.SetMaxSize((image_width, image_height))

        panel_width = (image_width * 2) + 24
        panel_height = image_column_height + 12
        self.SetMinSize((panel_width, panel_height))
        self.SetMaxSize((panel_width, panel_height))

    # ============= Public API =============

    def reset(self) -> None:
        """Reset the inspector to default state."""
        self.active_zone = None
        self.name_label.SetLabel("Select a card to inspect.")
        self.type_label.SetLabel("")
        self.stats_label.SetLabel("")
        self.text_ctrl.ChangeValue("Select a card to inspect.")
        self._render_mana_cost("")
        self.card_image_display.show_placeholder("Select a card")
        self.nav_panel.Hide()
        self.inspector_printings = []
        self.inspector_current_printing = 0
        self.inspector_current_card_name = None
        self._printings_request_inflight = None
        self._loading_printing = False
        self._has_selection = False
        self._set_display_mode(False, show_image_column=True)

    def update_card(
        self, card: dict[str, Any], zone: str | None = None, meta: dict[str, Any] | None = None
    ) -> None:
        """
        Update the inspector to show a specific card.

        Args:
            card: Card dictionary with 'name' and 'qty' keys
            zone: Zone the card is from (e.g., 'main', 'side', 'out')
            meta: Optional pre-fetched metadata
        """
        self.active_zone = zone
        self._has_selection = True
        zone_title = ZONE_TITLES.get(zone, zone.title()) if zone else "Card Search"
        header = f"{card['name']}  ×{card['qty']}  ({zone_title})"
        self.name_label.SetLabel(header)

        # Get or use metadata
        if meta is None and self.card_manager:
            meta = self.card_manager.get_card(card["name"]) or {}
        else:
            meta = meta or {}

        # Render mana cost
        mana_cost = meta.get("mana_cost", "")
        self._render_mana_cost(mana_cost)

        # Type line
        type_line = meta.get("type_line") or "Type data unavailable."
        self.type_label.SetLabel(type_line)

        # Stats line
        stats_bits: list[str] = []
        if meta.get("mana_value") is not None:
            stats_bits.append(f"MV {meta['mana_value']}")
        if meta.get("power") or meta.get("toughness"):
            stats_bits.append(f"P/T {meta.get('power', '?')}/{meta.get('toughness', '?')}")
        if meta.get("loyalty"):
            stats_bits.append(f"Loyalty {meta['loyalty']}")
        colors = meta.get("color_identity", [])
        stats_bits.append(f"Colors: {'/'.join(colors) if colors else 'Colorless'}")
        stats_bits.append(f"Zone: {zone_title}")
        self.stats_label.SetLabel("  |  ".join(stats_bits))

        # Oracle text
        oracle_text = meta.get("oracle_text") or ""
        self.text_ctrl.ChangeValue(oracle_text)

        # Load image and printings
        self._load_card_image_and_printings(card["name"])

    def set_card_manager(self, card_manager: CardDataManager) -> None:
        """Set the card data manager for metadata lookups."""
        self.card_manager = card_manager

    def set_bulk_data(self, bulk_data_by_name: dict[str, list[dict[str, Any]]]) -> None:
        """Set the bulk data index for fast printing lookups."""
        self.bulk_data_by_name = bulk_data_by_name
        if self.inspector_current_card_name:
            self._load_card_image_and_printings(self.inspector_current_card_name)

    def set_image_request_handlers(
        self,
        *,
        on_request: Callable[[CardImageRequest], None] | None,
        on_selected: Callable[[CardImageRequest | None], None] | None,
    ) -> None:
        """Register callbacks for missing image requests and selection updates."""
        self._image_request_handler = on_request
        self._selected_card_handler = on_selected

    def set_printings_request_handler(self, handler: Callable[[str], None] | None) -> None:
        """Register callback to request printings for a card name."""
        self._printings_request_handler = handler

    def handle_image_downloaded(self, request: CardImageRequest) -> None:
        """Refresh the display if the downloaded image matches the current selection."""
        if not self.inspector_current_card_name:
            return
        if not self._request_matches_current(request):
            return
        self._load_current_printing_image()

    def handle_printings_loaded(self, card_name: str, printings: list[dict[str, Any]]) -> None:
        """Update printings list when background fetch completes."""
        if not self.inspector_current_card_name:
            return
        if card_name.lower() != self.inspector_current_card_name.lower():
            return
        self._printings_request_inflight = None
        if not printings:
            return
        self.inspector_printings = printings
        self.inspector_current_printing = 0
        self._load_current_printing_image()

    # ============= Private Methods =============

    def _render_mana_cost(self, mana_cost: str) -> None:
        """Render mana cost symbols."""
        self.cost_sizer.Clear(delete_windows=True)
        if mana_cost:
            panel = self.mana_icons.render(self.cost_container, mana_cost)
            panel.SetMinSize((max(32, panel.GetBestSize().width), 32))
        else:
            panel = wx.StaticText(self.cost_container, label="—")
            panel.SetForegroundColour(SUBDUED_TEXT)
        self.cost_sizer.Add(panel, 0)
        self.cost_container.Layout()

    def _load_card_image_and_printings(self, card_name: str) -> None:
        """Load card image and populate printings list."""
        self.inspector_current_card_name = card_name
        self.inspector_printings = []
        self.inspector_current_printing = 0
        self._printings_request_inflight = None
        self._loading_printing = False

        # Query in-memory bulk data for all printings
        if self.bulk_data_by_name:
            printings = self.bulk_data_by_name.get(card_name.lower(), [])
            self.inspector_printings = printings
        elif BULK_DATA_CACHE.exists():
            logger.debug(f"Bulk data not loaded yet for {card_name}")

        # Load the image
        self._load_current_printing_image()

    def _load_current_printing_image(self) -> None:
        """Load and display the current printing's image."""
        image_available = False
        active_request: CardImageRequest | None = None
        if not self.inspector_printings:
            # No printings found, try to load any cached image
            image_path = get_card_image(self.inspector_current_card_name, "normal")
            if image_path and image_path.exists():
                self.card_image_display.show_image(image_path)
                image_available = True
                self.nav_panel.Hide()
            else:
                self.card_image_display.show_placeholder("Not cached")
                self.nav_panel.Hide()
                if self.inspector_current_card_name:
                    active_request = CardImageRequest(
                        card_name=self.inspector_current_card_name,
                        uuid=None,
                        set_code=None,
                        collector_number=None,
                        size="normal",
                    )
                    if (
                        self._printings_request_handler
                        and self._printings_request_inflight
                        != self.inspector_current_card_name.lower()
                    ):
                        self._printings_request_inflight = self.inspector_current_card_name.lower()
                        self._printings_request_handler(self.inspector_current_card_name)
                        self._loading_printing = True
            self._notify_selection(active_request)
            self._set_display_mode(image_available, show_image_column=image_available)
            if not image_available and active_request:
                self._request_missing_image(active_request)
            return

        # Get current printing
        printing = self.inspector_printings[self.inspector_current_printing]
        uuid = printing.get("id")
        active_request = CardImageRequest(
            card_name=self.inspector_current_card_name or "",
            uuid=uuid,
            set_code=printing.get("set"),
            collector_number=printing.get("collector_number"),
            size="normal",
        )

        # Try to load from cache (printing-specific)
        image_paths = self.image_cache.get_image_paths_by_uuid(uuid, "normal")

        if image_paths:
            if len(image_paths) > 1:
                self.card_image_display.show_images(image_paths)
            else:
                self.card_image_display.show_image(image_paths[0])
            image_available = True
            self._loading_printing = False
        else:
            set_code = active_request.set_code if active_request else None
            name_printing_path = None
            if set_code:
                name_printing_path = self.image_cache.get_image_path_for_printing(
                    active_request.card_name, set_code, active_request.size
                )
            if name_printing_path and name_printing_path.exists():
                self.card_image_display.show_image(name_printing_path)
                image_available = True
                self._loading_printing = False
            else:
                self.card_image_display.show_placeholder("Not cached")
                self._loading_printing = True

        # Update navigation controls
        if len(self.inspector_printings) > 1:
            set_code = printing.get("set", "").upper()
            set_name = printing.get("set_name", "")
            printing_info = (
                f"{self.inspector_current_printing + 1} of {len(self.inspector_printings)}"
            )
            if set_code:
                printing_info += f" - {set_code}"
            if set_name:
                printing_info += f" ({set_name})"
            self._set_printing_label(printing_info)
            self.prev_btn.Enable(self.inspector_current_printing > 0)
            self.next_btn.Enable(
                self.inspector_current_printing < len(self.inspector_printings) - 1
            )
            self.nav_panel.Show()
        else:
            self.nav_panel.Hide()

        self._notify_selection(active_request)
        self._set_display_mode(image_available, show_image_column=image_available)

        if not image_available:
            self._request_missing_image(active_request)

    def _on_prev_printing(self, _event: wx.Event) -> None:
        """Navigate to previous printing."""
        if self.inspector_current_printing > 0:
            self.inspector_current_printing -= 1
            self._load_current_printing_image()

    def _on_next_printing(self, _event: wx.Event) -> None:
        """Navigate to next printing."""
        if self.inspector_current_printing < len(self.inspector_printings) - 1:
            self.inspector_current_printing += 1
            self._load_current_printing_image()

    def _set_printing_label(self, text: str) -> None:
        """Update the printing label while keeping the navigation width stable."""
        self.printing_label.SetLabel(text)
        if self.printing_label_width:
            self.printing_label.Wrap(self.printing_label_width)
        self.nav_panel.Layout()

    def _set_display_mode(
        self, image_available: bool, *, show_image_column: bool | None = None
    ) -> None:
        """Toggle between image-only and text fallback views."""
        self._image_available = image_available
        if show_image_column is None:
            show_image_column = image_available or bool(self.inspector_printings)
        self.image_column_panel.Show(show_image_column)
        if self._loading_printing:
            self.loading_label.Show()
        else:
            self.loading_label.Hide()
        show_details = self._has_selection and (not image_available or self._loading_printing)
        self.details_panel.Show(show_details)
        self.Layout()

    def _notify_selection(self, request: CardImageRequest | None) -> None:
        if self._selected_card_handler:
            self._selected_card_handler(request)

    def _request_missing_image(self, request: CardImageRequest | None) -> None:
        if request is None or not self._image_request_handler:
            return
        self._image_request_handler(request)

    def _request_matches_current(self, request: CardImageRequest) -> bool:
        if self.inspector_current_card_name is None:
            return False
        if request.card_name == self.inspector_current_card_name:
            return True
        if not self.inspector_printings:
            return False
        printing = self.inspector_printings[self.inspector_current_printing]
        uuid = printing.get("id")
        return bool(uuid and request.uuid and uuid == request.uuid)
