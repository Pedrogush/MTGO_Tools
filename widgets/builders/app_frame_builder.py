"""AppFrame Builder - Responsible for UI construction."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import wx
from wx.lib.agw import flatnotebook as fnb

if TYPE_CHECKING:
    from controllers.app_controller import AppController

from utils.mana_icon_factory import ManaIconFactory
from widgets.buttons.deck_action_buttons import DeckActionButtons
from widgets.buttons.toolbar_buttons import ToolbarButtons
from widgets.panels.card_inspector_panel import CardInspectorPanel
from widgets.panels.card_table_panel import CardTablePanel
from widgets.panels.deck_builder_panel import DeckBuilderPanel
from widgets.panels.deck_notes_panel import DeckNotesPanel
from widgets.panels.deck_research_panel import DeckResearchPanel
from widgets.panels.deck_stats_panel import DeckStatsPanel
from widgets.panels.sideboard_guide_panel import SideboardGuidePanel


@dataclass
class AppFrameWidgets:
    """Container for all widgets created by AppFrameBuilder.

    This dataclass holds references to all UI components, making it easy to
    pass them to event coordinators and other components.
    """

    status_bar: wx.StatusBar
    left_stack: wx.Simplebook
    research_panel: DeckResearchPanel
    builder_panel: DeckBuilderPanel
    toolbar: ToolbarButtons
    deck_source_choice: wx.Choice
    zone_notebook: fnb.FlatNotebook
    main_table: CardTablePanel
    side_table: CardTablePanel
    out_table: CardTablePanel | None
    deck_tabs: fnb.FlatNotebook
    deck_stats_panel: DeckStatsPanel
    sideboard_guide_panel: SideboardGuidePanel
    deck_notes_panel: DeckNotesPanel
    card_inspector_panel: CardInspectorPanel
    summary_text: wx.TextCtrl
    deck_list: wx.ListBox
    deck_action_buttons: DeckActionButtons
    collection_status_label: wx.StaticText
    # Additional convenience references
    daily_average_button: wx.Button
    copy_button: wx.Button
    save_button: wx.Button
    stats_summary: wx.StaticText
    deck_tables_page: wx.Panel


class AppFrameBuilder:
    """Builds the complete UI for AppFrame.

    Responsibilities:
    - Constructing all panels, widgets, and controls
    - Setting up layout and styling
    - Wiring up callbacks to controller/coordinator
    - Creating notebook tabs and organizing workspace

    This class does NOT handle:
    - Event binding (handled by AppEventCoordinator)
    - State persistence (handled by AppStateManager)
    - Business logic (handled by AppController)
    """

    def __init__(
        self,
        frame: wx.Frame,
        controller: "AppController",
        mana_icons: ManaIconFactory,
    ):
        """Initialize the builder.

        Args:
            frame: The parent frame to build UI into
            controller: Application controller for callbacks
            mana_icons: Factory for mana symbol icons
        """
        self.frame = frame
        self.controller = controller
        self.mana_icons = mana_icons

    def build_all(self) -> AppFrameWidgets:
        """Build the complete UI and return all widget references.

        Returns:
            AppFrameWidgets containing all constructed components
        """
        raise NotImplementedError("To be implemented in Step 5")

    def build_status_bar(self) -> wx.StatusBar:
        """Build and configure the status bar."""
        raise NotImplementedError("To be implemented in Step 5")

    def build_left_panel(self, parent: wx.Window) -> tuple[wx.Panel, wx.Simplebook, DeckResearchPanel, DeckBuilderPanel]:
        """Build the left panel with research and builder modes."""
        raise NotImplementedError("To be implemented in Step 5")

    def build_right_panel(self, parent: wx.Window) -> wx.Panel:
        """Build the right panel with deck workspace and inspector."""
        raise NotImplementedError("To be implemented in Step 5")

    def build_toolbar(self, parent: wx.Window) -> ToolbarButtons:
        """Build the toolbar with action buttons."""
        raise NotImplementedError("To be implemented in Step 5")

    def build_card_data_controls(self, parent: wx.Window) -> wx.Panel:
        """Build card data source selection controls."""
        raise NotImplementedError("To be implemented in Step 5")

    def build_deck_workspace(self, parent: wx.Window) -> wx.StaticBoxSizer:
        """Build the main deck workspace with tabs."""
        raise NotImplementedError("To be implemented in Step 5")

    def build_card_inspector(self, parent: wx.Window) -> wx.StaticBoxSizer:
        """Build the card inspector panel."""
        raise NotImplementedError("To be implemented in Step 5")

    def build_deck_results(self, parent: wx.Window) -> wx.StaticBoxSizer:
        """Build the deck results panel with list and buttons."""
        raise NotImplementedError("To be implemented in Step 5")

    def build_deck_tables_tab(self, deck_tabs: fnb.FlatNotebook) -> tuple[wx.Panel, fnb.FlatNotebook, CardTablePanel, CardTablePanel, wx.StaticText]:
        """Build the deck tables tab with zone notebooks."""
        raise NotImplementedError("To be implemented in Step 5")

    def create_zone_table(
        self, zone_notebook: fnb.FlatNotebook, zone: str, tab_name: str
    ) -> CardTablePanel:
        """Create a zone table (mainboard, sideboard, outboard)."""
        raise NotImplementedError("To be implemented in Step 5")

    def create_notebook(self, parent: wx.Window) -> fnb.FlatNotebook:
        """Create a styled FlatNotebook."""
        raise NotImplementedError("To be implemented in Step 5")
