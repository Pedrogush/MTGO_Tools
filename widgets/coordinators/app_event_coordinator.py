"""AppEvent Coordinator - Centralized event handling for AppFrame.

NOTE: In this refactoring step, the coordinator acts as a facade that delegates
to the existing mixin methods in AppFrame. Steps 10-11 will move the actual
implementation logic from the mixins into this coordinator.
"""

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

    Current implementation: Facade that delegates to AppFrame's existing mixin methods.
    Future: Will contain the actual event handling logic (Steps 10-11).
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
    def on_format_changed(self) -> None:
        """Handle format selection change."""
        self.frame.on_format_changed()

    def on_archetype_filter(self) -> None:
        """Handle archetype filter text change."""
        self.frame.on_archetype_filter()

    def on_archetype_selected(self) -> None:
        """Handle archetype selection."""
        self.frame.on_archetype_selected()

    def fetch_archetypes(self, force: bool = False) -> None:
        """Fetch archetypes for current format."""
        self.frame.fetch_archetypes(force=force)

    # Deck Selection Events
    def on_deck_selected(self, event: wx.Event) -> None:
        """Handle deck selection from list."""
        self.frame.on_deck_selected(event)

    def on_copy_clicked(self, event: wx.Event | None) -> None:
        """Handle copy deck button click."""
        self.frame.on_copy_clicked(event)

    def on_save_clicked(self, event: wx.Event | None) -> None:
        """Handle save deck button click."""
        self.frame.on_save_clicked(event)

    def on_daily_average_clicked(self, event: wx.Event | None) -> None:
        """Handle daily average button click."""
        self.frame.on_daily_average_clicked(event)

    # Window/Dialog Events
    def open_opponent_tracker(self) -> None:
        """Open opponent tracker window."""
        self.frame.open_opponent_tracker()

    def open_timer_alert(self) -> None:
        """Open timer alert window."""
        self.frame.open_timer_alert()

    def open_match_history(self) -> None:
        """Open match history window."""
        self.frame.open_match_history()

    def open_metagame_analysis(self) -> None:
        """Open metagame analysis window."""
        self.frame.open_metagame_analysis()

    # Builder Panel Events
    def on_builder_search(self) -> None:
        """Handle card search in builder panel."""
        self.frame._on_builder_search()

    def on_builder_clear(self) -> None:
        """Handle clear search in builder panel."""
        self.frame._on_builder_clear()

    def on_builder_result_selected(self, card_name: str) -> None:
        """Handle card selection from search results."""
        self.frame._on_builder_result_selected(card_name)

    def open_radar_dialog(self) -> None:
        """Open radar chart dialog."""
        self.frame._open_radar_dialog()

    # Card Table Events
    def handle_zone_delta(self, zone: str, card_name: str, delta: int) -> None:
        """Handle card quantity change in zone."""
        self.frame._handle_zone_delta(zone, card_name, delta)

    def handle_zone_remove(self, zone: str, card_name: str) -> None:
        """Handle card removal from zone."""
        self.frame._handle_zone_remove(zone, card_name)

    def handle_zone_add(self, zone: str, card_name: str) -> None:
        """Handle adding card to zone."""
        self.frame._handle_zone_add(zone, card_name)

    def handle_card_focus(self, card_name: str, card_data: dict) -> None:
        """Handle card focus (click) event."""
        self.frame._handle_card_focus(card_name, card_data)

    def handle_card_hover(self, card_name: str, card_data: dict) -> None:
        """Handle card hover event."""
        self.frame._handle_card_hover(card_name, card_data)

    # Sideboard Guide Events
    def on_add_guide_entry(self) -> None:
        """Handle add sideboard guide entry."""
        self.frame._on_add_guide_entry()

    def on_edit_guide_entry(self, index: int) -> None:
        """Handle edit sideboard guide entry."""
        self.frame._on_edit_guide_entry(index)

    def on_remove_guide_entry(self, index: int) -> None:
        """Handle remove sideboard guide entry."""
        self.frame._on_remove_guide_entry(index)

    def on_edit_exclusions(self) -> None:
        """Handle edit sideboard exclusions."""
        self.frame._on_edit_exclusions()

    def on_export_guide(self) -> None:
        """Handle export sideboard guide."""
        self.frame._on_export_guide()

    def on_import_guide(self) -> None:
        """Handle import sideboard guide."""
        self.frame._on_import_guide()

    # Other Events
    def on_deck_source_changed(self, event: wx.Event) -> None:
        """Handle deck data source selection change."""
        self.frame._on_deck_source_changed(event)

    def ensure_card_data_loaded(self) -> None:
        """Ensure card data is loaded."""
        self.frame.ensure_card_data_loaded()

    def on_close(self, event: wx.CloseEvent) -> None:
        """Handle window close event."""
        self.frame.on_close(event)

    def on_window_change(self, event: wx.Event) -> None:
        """Handle window size/position change."""
        self.frame.on_window_change(event)

    def on_hotkey(self, event: wx.KeyEvent) -> None:
        """Handle keyboard shortcuts."""
        self.frame._on_hotkey(event)
