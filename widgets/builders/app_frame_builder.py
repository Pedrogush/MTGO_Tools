"""AppFrame Builder - Responsible for UI construction."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Any

import wx
from wx.lib.agw import flatnotebook as fnb

if TYPE_CHECKING:
    from controllers.app_controller import AppController

from utils.constants import (
    APP_FRAME_SUMMARY_MIN_HEIGHT,
    DARK_ACCENT,
    DARK_BG,
    DARK_PANEL,
    FORMAT_OPTIONS,
    LIGHT_TEXT,
    PADDING_LG,
    PADDING_MD,
    PADDING_SM,
    SUBDUED_TEXT,
)
from utils.mana_icon_factory import ManaIconFactory
from utils.stylize import stylize_listbox, stylize_textctrl
from widgets.buttons.deck_action_buttons import DeckActionButtons
from widgets.buttons.toolbar_buttons import ToolbarButtons
from widgets.dialogs.image_download_dialog import show_image_download_dialog
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
        callbacks: dict[str, Callable],
    ):
        """Initialize the builder.

        Args:
            frame: The parent frame to build UI into
            controller: Application controller for callbacks
            mana_icons: Factory for mana symbol icons
            callbacks: Dict of callback functions from frame/coordinator
        """
        self.frame = frame
        self.controller = controller
        self.mana_icons = mana_icons
        self.callbacks = callbacks

    def build_all(self) -> AppFrameWidgets:
        """Build the complete UI and return all widget references.

        Returns:
            AppFrameWidgets containing all constructed components
        """
        # Set frame background
        self.frame.SetBackgroundColour(DARK_BG)

        # Build status bar
        status_bar = self.build_status_bar()

        # Create root panel
        root_panel = wx.Panel(self.frame)
        root_panel.SetBackgroundColour(DARK_BG)
        root_sizer = wx.BoxSizer(wx.HORIZONTAL)
        root_panel.SetSizer(root_sizer)

        # Build left panel
        left_panel_result = self.build_left_panel(root_panel)
        left_panel, left_stack, research_panel, builder_panel = left_panel_result
        root_sizer.Add(left_panel, 0, wx.EXPAND | wx.ALL, PADDING_LG)

        # Build right panel (returns the fully constructed widgets)
        right_widgets = self.build_right_panel(root_panel)
        root_sizer.Add(right_widgets["panel"], 1, wx.EXPAND | wx.ALL, PADDING_LG)

        # Construct and return the widget container
        return AppFrameWidgets(
            status_bar=status_bar,
            left_stack=left_stack,
            research_panel=research_panel,
            builder_panel=builder_panel,
            toolbar=right_widgets["toolbar"],
            deck_source_choice=right_widgets["deck_source_choice"],
            zone_notebook=right_widgets["zone_notebook"],
            main_table=right_widgets["main_table"],
            side_table=right_widgets["side_table"],
            out_table=right_widgets["out_table"],
            deck_tabs=right_widgets["deck_tabs"],
            deck_stats_panel=right_widgets["deck_stats_panel"],
            sideboard_guide_panel=right_widgets["sideboard_guide_panel"],
            deck_notes_panel=right_widgets["deck_notes_panel"],
            card_inspector_panel=right_widgets["card_inspector_panel"],
            summary_text=right_widgets["summary_text"],
            deck_list=right_widgets["deck_list"],
            deck_action_buttons=right_widgets["deck_action_buttons"],
            collection_status_label=right_widgets["collection_status_label"],
            daily_average_button=right_widgets["deck_action_buttons"].daily_average_button,
            copy_button=right_widgets["deck_action_buttons"].copy_button,
            save_button=right_widgets["deck_action_buttons"].save_button,
            stats_summary=right_widgets["deck_stats_panel"].summary_label,
            deck_tables_page=right_widgets["deck_tables_page"],
        )

    def build_status_bar(self) -> wx.StatusBar:
        """Build and configure the status bar."""
        status_bar = self.frame.CreateStatusBar()
        status_bar.SetBackgroundColour(DARK_PANEL)
        status_bar.SetForegroundColour(LIGHT_TEXT)
        return status_bar

    def build_left_panel(
        self, parent: wx.Window
    ) -> tuple[wx.Panel, wx.Simplebook, DeckResearchPanel, DeckBuilderPanel]:
        """Build the left panel with research and builder modes."""
        left_panel = wx.Panel(parent)
        left_panel.SetBackgroundColour(DARK_PANEL)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        left_panel.SetSizer(left_sizer)

        left_stack = wx.Simplebook(left_panel)
        left_stack.SetBackgroundColour(DARK_PANEL)
        left_sizer.Add(left_stack, 1, wx.EXPAND)

        research_panel = DeckResearchPanel(
            parent=left_stack,
            format_options=FORMAT_OPTIONS,
            initial_format=self.controller.current_format,
            on_format_changed=self.callbacks["on_format_changed"],
            on_archetype_filter=self.callbacks["on_archetype_filter"],
            on_archetype_selected=self.callbacks["on_archetype_selected"],
            on_reload_archetypes=self.callbacks["on_reload_archetypes"],
        )
        left_stack.AddPage(research_panel, "Research")

        builder_panel = DeckBuilderPanel(
            parent=left_stack,
            mana_icons=self.mana_icons,
            on_switch_to_research=self.callbacks["on_switch_to_research"],
            on_ensure_card_data=self.callbacks["on_ensure_card_data"],
            open_mana_keyboard=self.callbacks["open_mana_keyboard"],
            on_search=self.callbacks["on_builder_search"],
            on_clear=self.callbacks["on_builder_clear"],
            on_result_selected=self.callbacks["on_builder_result_selected"],
            on_open_radar_dialog=self.callbacks["on_open_radar_dialog"],
        )
        left_stack.AddPage(builder_panel, "Builder")

        return left_panel, left_stack, research_panel, builder_panel

    def build_right_panel(self, parent: wx.Window) -> dict[str, Any]:
        """Build the right panel with deck workspace and inspector.

        Returns:
            Dict containing the panel and all its child widgets
        """
        right_panel = wx.Panel(parent)
        right_panel.SetBackgroundColour(DARK_BG)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        right_panel.SetSizer(right_sizer)

        # Toolbar
        toolbar = self.build_toolbar(right_panel)
        right_sizer.Add(toolbar, 0, wx.EXPAND | wx.BOTTOM, PADDING_MD)

        # Card data controls
        card_data_panel, deck_source_choice = self.build_card_data_controls(right_panel)
        right_sizer.Add(card_data_panel, 0, wx.EXPAND | wx.BOTTOM, PADDING_LG)

        # Content split
        content_split = wx.BoxSizer(wx.HORIZONTAL)
        right_sizer.Add(content_split, 1, wx.EXPAND | wx.BOTTOM, PADDING_LG)

        # Middle column (deck workspace)
        middle_column = wx.BoxSizer(wx.VERTICAL)
        content_split.Add(middle_column, 2, wx.EXPAND | wx.RIGHT, PADDING_LG)

        workspace_result = self.build_deck_workspace(right_panel)
        middle_column.Add(workspace_result["sizer"], 1, wx.EXPAND)

        # Inspector column
        inspector_column = wx.BoxSizer(wx.VERTICAL)
        content_split.Add(inspector_column, 1, wx.EXPAND)

        inspector_result = self.build_card_inspector(right_panel)
        inspector_column.Add(inspector_result["sizer"], 1, wx.EXPAND | wx.BOTTOM, PADDING_LG)

        deck_results = self.build_deck_results(right_panel)
        inspector_column.Add(deck_results["sizer"], 1, wx.EXPAND)

        # Combine all widgets into result dict
        return {
            "panel": right_panel,
            "toolbar": toolbar,
            "deck_source_choice": deck_source_choice,
            **workspace_result,
            **inspector_result,
            **deck_results,
        }

    def build_toolbar(self, parent: wx.Window) -> ToolbarButtons:
        """Build the toolbar with action buttons."""
        return ToolbarButtons(
            parent,
            on_open_opponent_tracker=self.callbacks["open_opponent_tracker"],
            on_open_timer_alert=self.callbacks["open_timer_alert"],
            on_open_match_history=self.callbacks["open_match_history"],
            on_open_metagame_analysis=self.callbacks["open_metagame_analysis"],
            on_load_collection=lambda: self.controller.refresh_collection_from_bridge(force=True),
            on_download_card_images=self.callbacks["on_download_card_images"],
            on_update_card_database=lambda: self.controller.force_bulk_data_update(),
        )

    def build_card_data_controls(self, parent: wx.Window) -> tuple[wx.Panel, wx.Choice]:
        """Build card data source selection controls."""
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel.SetSizer(sizer)

        source_label = wx.StaticText(panel, label="Deck data source:")
        source_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(source_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_SM)

        deck_source_choice = wx.Choice(panel, choices=["Both", "MTGGoldfish", "MTGO.com"])
        current_source = self.controller.get_deck_data_source()
        source_map = {"both": 0, "mtggoldfish": 1, "mtgo": 2}
        deck_source_choice.SetSelection(source_map.get(current_source, 0))
        deck_source_choice.Bind(wx.EVT_CHOICE, self.callbacks["on_deck_source_changed"])
        sizer.Add(deck_source_choice, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.AddStretchSpacer(1)
        return panel, deck_source_choice

    def build_deck_workspace(self, parent: wx.Window) -> dict[str, Any]:
        """Build the main deck workspace with tabs."""
        detail_box = wx.StaticBox(parent, label="Deck Workspace")
        detail_box.SetForegroundColour(LIGHT_TEXT)
        detail_box.SetBackgroundColour(DARK_PANEL)
        detail_sizer = wx.StaticBoxSizer(detail_box, wx.VERTICAL)

        deck_tabs = self.create_notebook(detail_box)
        detail_sizer.Add(deck_tabs, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Build deck tables tab
        tables_result = self.build_deck_tables_tab(deck_tabs)

        # Stats tab
        deck_stats_panel = DeckStatsPanel(
            deck_tabs,
            card_manager=self.controller.card_repo.get_card_manager(),
            deck_service=self.controller.deck_service,
        )
        deck_tabs.AddPage(deck_stats_panel, "Stats")

        # Sideboard guide tab
        sideboard_guide_panel = SideboardGuidePanel(
            deck_tabs,
            on_add_entry=self.callbacks["on_add_guide_entry"],
            on_edit_entry=self.callbacks["on_edit_guide_entry"],
            on_remove_entry=self.callbacks["on_remove_guide_entry"],
            on_edit_exclusions=self.callbacks["on_edit_exclusions"],
            on_export_csv=self.callbacks["on_export_guide"],
            on_import_csv=self.callbacks["on_import_guide"],
        )
        deck_tabs.AddPage(sideboard_guide_panel, "Sideboard Guide")

        # Deck notes tab
        deck_notes_panel = DeckNotesPanel(
            deck_tabs,
            deck_repo=self.controller.deck_repo,
            store_service=self.controller.store_service,
            notes_store=self.controller.deck_notes_store,
            notes_store_path=self.controller.notes_store_path,
            on_status_update=self.callbacks["set_status"],
        )
        deck_tabs.AddPage(deck_notes_panel, "Deck Notes")

        return {
            "sizer": detail_sizer,
            "deck_tabs": deck_tabs,
            "deck_stats_panel": deck_stats_panel,
            "sideboard_guide_panel": sideboard_guide_panel,
            "deck_notes_panel": deck_notes_panel,
            **tables_result,
        }

    def build_card_inspector(self, parent: wx.Window) -> dict[str, Any]:
        """Build the card inspector panel."""
        inspector_box = wx.StaticBox(parent, label="Card Inspector")
        inspector_box.SetForegroundColour(LIGHT_TEXT)
        inspector_box.SetBackgroundColour(DARK_PANEL)
        inspector_sizer = wx.StaticBoxSizer(inspector_box, wx.VERTICAL)

        card_inspector_panel = CardInspectorPanel(
            inspector_box,
            card_manager=self.controller.card_repo.get_card_manager(),
            mana_icons=self.mana_icons,
        )
        card_inspector_panel.set_image_request_handlers(
            on_request=lambda request: self.controller.image_service.queue_card_image_download(
                request, prioritize=True
            ),
            on_selected=self.controller.image_service.set_selected_card_request,
        )
        card_inspector_panel.set_printings_request_handler(
            self.controller.image_service.fetch_printings_by_name_async
        )
        self.controller.image_service.set_image_download_callback(
            card_inspector_panel.handle_image_downloaded
        )
        self.controller.image_service.set_printings_loaded_callback(
            card_inspector_panel.handle_printings_loaded
        )
        inspector_sizer.Add(card_inspector_panel, 1, wx.EXPAND)

        return {
            "sizer": inspector_sizer,
            "card_inspector_panel": card_inspector_panel,
        }

    def build_deck_results(self, parent: wx.Window) -> dict[str, Any]:
        """Build the deck results panel with list and buttons."""
        deck_box = wx.StaticBox(parent, label="Deck Results")
        deck_box.SetForegroundColour(LIGHT_TEXT)
        deck_box.SetBackgroundColour(DARK_PANEL)
        deck_sizer = wx.StaticBoxSizer(deck_box, wx.VERTICAL)

        summary_text = wx.TextCtrl(
            deck_box,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.NO_BORDER,
        )
        stylize_textctrl(summary_text, multiline=True)
        summary_text.SetMinSize((-1, APP_FRAME_SUMMARY_MIN_HEIGHT))
        deck_sizer.Add(summary_text, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        deck_list = wx.ListBox(deck_box, style=wx.LB_SINGLE)
        stylize_listbox(deck_list)
        deck_list.Bind(wx.EVT_LISTBOX, self.callbacks["on_deck_selected"])
        deck_sizer.Add(deck_list, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Deck action buttons
        deck_action_buttons = DeckActionButtons(
            deck_box,
            on_copy=self.callbacks["on_copy_clicked"],
            on_save=self.callbacks["on_save_clicked"],
            on_daily_average=self.callbacks["on_daily_average_clicked"],
        )
        deck_sizer.Add(
            deck_action_buttons,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            PADDING_MD,
        )

        return {
            "sizer": deck_sizer,
            "summary_text": summary_text,
            "deck_list": deck_list,
            "deck_action_buttons": deck_action_buttons,
        }

    def build_deck_tables_tab(
        self, deck_tabs: fnb.FlatNotebook
    ) -> dict[str, Any]:
        """Build the deck tables tab with zone notebooks."""
        deck_tables_page = wx.Panel(deck_tabs)
        deck_tabs.AddPage(deck_tables_page, "Deck Tables")
        tables_sizer = wx.BoxSizer(wx.VERTICAL)
        deck_tables_page.SetSizer(tables_sizer)

        zone_notebook = self.create_notebook(deck_tables_page)
        tables_sizer.Add(zone_notebook, 1, wx.EXPAND | wx.BOTTOM, PADDING_MD)

        # Create zone tables
        main_table = self.create_zone_table(zone_notebook, "main", "Mainboard")
        side_table = self.create_zone_table(zone_notebook, "side", "Sideboard")
        out_table = None

        # Collection status
        collection_status_label = wx.StaticText(
            deck_tables_page, label="Collection inventory not loaded."
        )
        collection_status_label.SetForegroundColour(SUBDUED_TEXT)
        tables_sizer.Add(
            collection_status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM
        )

        return {
            "deck_tables_page": deck_tables_page,
            "zone_notebook": zone_notebook,
            "main_table": main_table,
            "side_table": side_table,
            "out_table": out_table,
            "collection_status_label": collection_status_label,
        }

    def create_zone_table(
        self, zone_notebook: fnb.FlatNotebook, zone: str, tab_name: str
    ) -> CardTablePanel:
        """Create a zone table (mainboard, sideboard, outboard)."""
        owned_status_func = self.controller.collection_service.get_owned_status

        table = CardTablePanel(
            zone_notebook,
            zone,
            self.mana_icons,
            self.controller.card_repo.get_card_metadata,
            owned_status_func,
            self.callbacks["handle_zone_delta"],
            self.callbacks["handle_zone_remove"],
            self.callbacks["handle_zone_add"],
            self.callbacks["handle_card_focus"],
            self.callbacks["handle_card_hover"],
        )
        zone_notebook.AddPage(table, tab_name)
        return table

    def create_notebook(self, parent: wx.Window) -> fnb.FlatNotebook:
        """Create a styled FlatNotebook."""
        notebook = fnb.FlatNotebook(
            parent,
            agwStyle=(
                fnb.FNB_FANCY_TABS
                | fnb.FNB_SMART_TABS
                | fnb.FNB_NO_X_BUTTON
                | fnb.FNB_NO_NAV_BUTTONS
            ),
        )
        notebook.SetTabAreaColour(DARK_PANEL)
        notebook.SetActiveTabColour(DARK_ACCENT)
        notebook.SetNonActiveTabTextColour(SUBDUED_TEXT)
        notebook.SetActiveTabTextColour(wx.Colour(12, 14, 18))
        notebook.SetBackgroundColour(DARK_BG)
        notebook.SetForegroundColour(LIGHT_TEXT)
        return notebook
