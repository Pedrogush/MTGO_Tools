"""AppEvent Coordinator - Centralized event handling for AppFrame."""

from typing import TYPE_CHECKING

import wx

if TYPE_CHECKING:
    from controllers.app_controller import AppController
    from widgets.app_frame import AppFrame


class AppEventCoordinator:
    """Coordinates event handling between UI and business logic.

    Responsibilities:
    - Handling all user interactions from AppFrame widgets
    - Delegating to AppController for business logic
    - Updating UI state after operations
    - Coordinating complex workflows across multiple components

    This class does NOT:
    - Contain business logic (delegated to AppController)
    - Build UI (handled by AppFrameBuilder)
    - Manage state (handled by AppStateManager)
    """

    def __init__(self, frame: "AppFrame", controller: "AppController"):
        """Initialize the event coordinator.

        Args:
            frame: The AppFrame instance
            controller: The AppController instance
        """
        self.frame = frame
        self.controller = controller

    # Research Panel Events
    def on_format_changed(self, format_name: str) -> None:
        """Handle format selection change."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_archetype_filter(self, filter_text: str) -> None:
        """Handle archetype filter text change."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_archetype_selected(self, archetype: dict) -> None:
        """Handle archetype selection."""
        raise NotImplementedError("To be implemented in Step 8")

    def fetch_archetypes(self, force: bool = False) -> None:
        """Fetch archetypes for current format."""
        raise NotImplementedError("To be implemented in Step 8")

    # Deck Selection Events
    def on_deck_selected(self, event: wx.Event) -> None:
        """Handle deck selection from list."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_copy_clicked(self, event: wx.Event | None) -> None:
        """Handle copy deck button click."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_save_clicked(self, event: wx.Event | None) -> None:
        """Handle save deck button click."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_daily_average_clicked(self, event: wx.Event | None) -> None:
        """Handle daily average button click."""
        raise NotImplementedError("To be implemented in Step 8")

    # Window/Dialog Events
    def open_opponent_tracker(self) -> None:
        """Open opponent tracker window."""
        raise NotImplementedError("To be implemented in Step 8")

    def open_timer_alert(self) -> None:
        """Open timer alert window."""
        raise NotImplementedError("To be implemented in Step 8")

    def open_match_history(self) -> None:
        """Open match history window."""
        raise NotImplementedError("To be implemented in Step 8")

    def open_metagame_analysis(self) -> None:
        """Open metagame analysis window."""
        raise NotImplementedError("To be implemented in Step 8")

    # Builder Panel Events
    def on_builder_search(self) -> None:
        """Handle card search in builder panel."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_builder_clear(self) -> None:
        """Handle clear search in builder panel."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_builder_result_selected(self, card_name: str) -> None:
        """Handle card selection from search results."""
        raise NotImplementedError("To be implemented in Step 8")

    def open_radar_dialog(self) -> None:
        """Open radar chart dialog."""
        raise NotImplementedError("To be implemented in Step 8")

    # Card Table Events
    def handle_zone_delta(self, zone: str, card_name: str, delta: int) -> None:
        """Handle card quantity change in zone."""
        raise NotImplementedError("To be implemented in Step 8")

    def handle_zone_remove(self, zone: str, card_name: str) -> None:
        """Handle card removal from zone."""
        raise NotImplementedError("To be implemented in Step 8")

    def handle_zone_add(self, zone: str, card_name: str) -> None:
        """Handle adding card to zone."""
        raise NotImplementedError("To be implemented in Step 8")

    def handle_card_focus(self, card_name: str, card_data: dict) -> None:
        """Handle card focus (click) event."""
        raise NotImplementedError("To be implemented in Step 8")

    def handle_card_hover(self, card_name: str, card_data: dict) -> None:
        """Handle card hover event."""
        raise NotImplementedError("To be implemented in Step 8")

    # Sideboard Guide Events
    def on_add_guide_entry(self) -> None:
        """Handle add sideboard guide entry."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_edit_guide_entry(self, index: int) -> None:
        """Handle edit sideboard guide entry."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_remove_guide_entry(self, index: int) -> None:
        """Handle remove sideboard guide entry."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_edit_exclusions(self) -> None:
        """Handle edit sideboard exclusions."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_export_guide(self) -> None:
        """Handle export sideboard guide."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_import_guide(self) -> None:
        """Handle import sideboard guide."""
        raise NotImplementedError("To be implemented in Step 8")

    # Other Events
    def on_deck_source_changed(self, event: wx.Event) -> None:
        """Handle deck data source selection change."""
        raise NotImplementedError("To be implemented in Step 8")

    def ensure_card_data_loaded(self) -> None:
        """Ensure card data is loaded."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_close(self, event: wx.CloseEvent) -> None:
        """Handle window close event."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_window_change(self, event: wx.Event) -> None:
        """Handle window size/position change."""
        raise NotImplementedError("To be implemented in Step 8")

    def on_hotkey(self, event: wx.KeyEvent) -> None:
        """Handle keyboard shortcuts."""
        raise NotImplementedError("To be implemented in Step 8")
