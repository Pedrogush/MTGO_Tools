from typing import TYPE_CHECKING, Any

import wx
from loguru import logger
from wx.lib.agw import flatnotebook as fnb

from controllers.app_controller import get_deck_selector_controller

if TYPE_CHECKING:
    from controllers.app_controller import AppController

from utils.child_window_manager import ChildWindowManager
from utils.constants import (
    APP_FRAME_MIN_SIZE,
    APP_FRAME_SIZE,
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
from utils.window_persistence import WindowPersistenceManager
from widgets.buttons.deck_action_buttons import DeckActionButtons
from widgets.buttons.toolbar_buttons import ToolbarButtons
from widgets.dialogs.image_download_dialog import show_image_download_dialog
from widgets.handlers.app_event_handlers import AppEventHandlers
from widgets.handlers.card_table_panel_handler import CardTablePanelHandler
from widgets.handlers.sideboard_guide_handlers import SideboardGuideHandlers
from widgets.mana_keyboard import ManaKeyboardFrame, open_mana_keyboard
from widgets.panels.card_inspector_panel import CardInspectorPanel
from widgets.panels.card_table_panel import CardTablePanel
from widgets.panels.deck_builder_panel import DeckBuilderPanel
from widgets.panels.deck_notes_panel import DeckNotesPanel
from widgets.panels.deck_research_panel import DeckResearchPanel
from widgets.panels.deck_stats_panel import DeckStatsPanel
from widgets.panels.radar_panel import RadarDialog
from widgets.panels.sideboard_guide_panel import SideboardGuidePanel


class AppFrame(AppEventHandlers, SideboardGuideHandlers, CardTablePanelHandler, wx.Frame):
    """wxPython-based metagame research + deck builder UI."""

    def __init__(
        self,
        controller: "AppController",
        parent: wx.Window | None = None,
    ):
        super().__init__(parent, title="MTGO Deck Research & Builder", size=APP_FRAME_SIZE)

        # Store controller reference - ALL state and business logic goes through this
        self.controller: AppController = controller
        self.card_data_dialogs_disabled = False
        self._builder_search_pending = False

        self.sideboard_guide_entries: list[dict[str, str]] = []
        self.sideboard_exclusions: list[str] = []
        self.active_inspector_zone: str | None = None
        self.left_stack: wx.Simplebook | None = None
        self.research_panel: DeckResearchPanel | None = None
        self.builder_panel: DeckBuilderPanel | None = None
        self.out_table: CardTablePanel | None = None

        self.window_persistence = WindowPersistenceManager(self, self.controller)
        self.child_windows = ChildWindowManager(self)
        self.mana_icons = ManaIconFactory()
        self.mana_keyboard_window: ManaKeyboardFrame | None = None
        self._inspector_hover_timer: wx.Timer | None = None
        self._pending_hover: tuple[str, dict[str, Any]] | None = None
        self._pending_deck_restore: bool = False

        self._build_ui()
        self._apply_window_preferences()
        self.SetMinSize(APP_FRAME_MIN_SIZE)
        self.Centre(wx.BOTH)

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_SIZE, self.on_window_change)
        self.Bind(wx.EVT_MOVE, self.on_window_change)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_hotkey)

    # ------------------------------------------------------------------ UI ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Build the main UI structure."""
        self.SetBackgroundColour(DARK_BG)
        self._setup_status_bar()

        root_panel = wx.Panel(self)
        root_panel.SetBackgroundColour(DARK_BG)
        root_sizer = wx.BoxSizer(wx.HORIZONTAL)
        root_panel.SetSizer(root_sizer)

        # Build left and right panels
        left_panel = self._build_left_panel(root_panel)
        root_sizer.Add(left_panel, 0, wx.EXPAND | wx.ALL, PADDING_LG)

        right_panel = self._build_right_panel(root_panel)
        root_sizer.Add(right_panel, 1, wx.EXPAND | wx.ALL, PADDING_LG)

    def _setup_status_bar(self) -> None:
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetBackgroundColour(DARK_PANEL)
        self.status_bar.SetForegroundColour(LIGHT_TEXT)
        self._set_status("Ready")

    def _build_left_panel(self, parent: wx.Window) -> wx.Panel:
        left_panel, left_sizer = self._create_styled_panel(parent, DARK_PANEL)

        self.left_stack = wx.Simplebook(left_panel)
        self.left_stack.SetBackgroundColour(DARK_PANEL)
        left_sizer.Add(self.left_stack, 1, wx.EXPAND)

        self.research_panel = DeckResearchPanel(
            parent=self.left_stack,
            format_options=FORMAT_OPTIONS,
            initial_format=self.controller.current_format,
            on_format_changed=self.on_format_changed,
            on_archetype_filter=self.on_archetype_filter,
            on_archetype_selected=self.on_archetype_selected,
            on_reload_archetypes=lambda: self.fetch_archetypes(force=True),
        )
        self.left_stack.AddPage(self.research_panel, "Research")

        self.builder_panel = DeckBuilderPanel(
            parent=self.left_stack,
            mana_icons=self.mana_icons,
            on_switch_to_research=lambda: self._show_left_panel("research"),
            on_ensure_card_data=self.ensure_card_data_loaded,
            open_mana_keyboard=self._open_full_mana_keyboard,
            on_search=self._on_builder_search,
            on_clear=self._on_builder_clear,
            on_result_selected=self._on_builder_result_selected,
            on_open_radar_dialog=self._open_radar_dialog,
        )
        self.left_stack.AddPage(self.builder_panel, "Builder")
        self._show_left_panel(self.left_mode, force=True)

        return left_panel

    def _build_right_panel(self, parent: wx.Window) -> wx.Panel:
        right_panel, right_sizer = self._create_styled_panel(parent)

        # Toolbar
        self.toolbar = self._build_toolbar(right_panel)
        right_sizer.Add(self.toolbar, 0, wx.EXPAND | wx.BOTTOM, PADDING_MD)

        card_data_controls = self._build_card_data_controls(right_panel)
        right_sizer.Add(card_data_controls, 0, wx.EXPAND | wx.BOTTOM, PADDING_LG)

        content_split = wx.BoxSizer(wx.HORIZONTAL)
        right_sizer.Add(content_split, 1, wx.EXPAND | wx.BOTTOM, PADDING_LG)

        middle_column = wx.BoxSizer(wx.VERTICAL)
        content_split.Add(middle_column, 2, wx.EXPAND | wx.RIGHT, PADDING_LG)

        deck_workspace = self._build_deck_workspace(right_panel)
        middle_column.Add(deck_workspace, 1, wx.EXPAND)

        inspector_column = wx.BoxSizer(wx.VERTICAL)
        content_split.Add(inspector_column, 1, wx.EXPAND)

        inspector_box = self._build_card_inspector(right_panel)
        inspector_column.Add(inspector_box, 1, wx.EXPAND | wx.BOTTOM, PADDING_LG)

        deck_results = self._build_deck_results(right_panel)
        inspector_column.Add(deck_results, 1, wx.EXPAND)

        return right_panel

    def _create_notebook(self, parent: wx.Window) -> fnb.FlatNotebook:
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

    def _create_static_box_sizer(
        self, parent: wx.Window, label: str, orientation: int = wx.VERTICAL
    ) -> tuple[wx.StaticBoxSizer, wx.StaticBox]:
        """Create a styled static box sizer with consistent theming."""
        static_box = wx.StaticBox(parent, label=label)
        static_box.SetForegroundColour(LIGHT_TEXT)
        static_box.SetBackgroundColour(DARK_PANEL)
        sizer = wx.StaticBoxSizer(static_box, orientation)
        return sizer, static_box

    def _create_styled_panel(
        self, parent: wx.Window, color: wx.Colour = None
    ) -> tuple[wx.Panel, wx.BoxSizer]:
        """Create a panel with dark theme styling and vertical sizer."""
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(color or DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)
        return panel, sizer

    def _build_toolbar(self, parent: wx.Window) -> ToolbarButtons:
        return ToolbarButtons(
            parent,
            on_open_opponent_tracker=self.open_opponent_tracker,
            on_open_timer_alert=self.open_timer_alert,
            on_open_match_history=self.open_match_history,
            on_open_metagame_analysis=self.open_metagame_analysis,
            on_load_collection=lambda: self.controller.refresh_collection_from_bridge(force=True),
            on_download_card_images=lambda: show_image_download_dialog(
                self, self.image_cache, self.image_downloader, self._set_status
            ),
            on_update_card_database=lambda: self.controller.force_bulk_data_update(),
        )

    def _build_card_data_controls(self, parent: wx.Window) -> wx.Panel:
        panel, sizer = self._create_styled_panel(parent)
        sizer.SetOrientation(wx.HORIZONTAL)  # Override to horizontal

        source_label = wx.StaticText(panel, label="Deck data source:")
        source_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(source_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_SM)

        self.deck_source_choice = wx.Choice(panel, choices=["Both", "MTGGoldfish", "MTGO.com"])
        current_source = self.controller.get_deck_data_source()
        source_map = {"both": 0, "mtggoldfish": 1, "mtgo": 2}
        self.deck_source_choice.SetSelection(source_map.get(current_source, 0))
        self.deck_source_choice.Bind(wx.EVT_CHOICE, self._on_deck_source_changed)
        sizer.Add(self.deck_source_choice, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.AddStretchSpacer(1)
        return panel

    def _build_deck_results(self, parent: wx.Window) -> wx.StaticBoxSizer:
        deck_sizer, deck_box = self._create_static_box_sizer(parent, "Deck Results")

        self.summary_text = wx.TextCtrl(
            deck_box,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.NO_BORDER,
        )
        stylize_textctrl(self.summary_text, multiline=True)
        self.summary_text.SetMinSize((-1, APP_FRAME_SUMMARY_MIN_HEIGHT))
        deck_sizer.Add(self.summary_text, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        self.deck_list = wx.ListBox(deck_box, style=wx.LB_SINGLE)
        stylize_listbox(self.deck_list)
        self.deck_list.Bind(wx.EVT_LISTBOX, self.on_deck_selected)
        deck_sizer.Add(self.deck_list, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Deck action buttons
        self.deck_action_buttons = DeckActionButtons(
            deck_box,
            on_copy=lambda: self.on_copy_clicked(None),
            on_save=lambda: self.on_save_clicked(None),
            on_daily_average=lambda: self.on_daily_average_clicked(None),
        )
        deck_sizer.Add(
            self.deck_action_buttons,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            PADDING_MD,
        )

        # Keep references for backward compatibility
        self.daily_average_button = self.deck_action_buttons.daily_average_button
        self.copy_button = self.deck_action_buttons.copy_button
        self.save_button = self.deck_action_buttons.save_button

        return deck_sizer

    def _build_card_inspector(self, parent: wx.Window) -> wx.StaticBoxSizer:
        inspector_sizer, inspector_box = self._create_static_box_sizer(parent, "Card Inspector")

        self.card_inspector_panel = CardInspectorPanel(
            inspector_box,
            card_manager=self.controller.card_repo.get_card_manager(),
            mana_icons=self.mana_icons,
        )
        inspector_sizer.Add(self.card_inspector_panel, 1, wx.EXPAND)

        # Keep backward compatibility references (delegate to image service via controller)
        self.image_cache = self.controller.image_service.image_cache
        self.image_downloader = self.controller.image_service.image_downloader

        return inspector_sizer

    def _build_deck_workspace(self, parent: wx.Window) -> wx.StaticBoxSizer:
        detail_sizer, detail_box = self._create_static_box_sizer(parent, "Deck Workspace")

        self.deck_tabs = self._create_notebook(detail_box)
        detail_sizer.Add(self.deck_tabs, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Deck tables tab
        self._build_deck_tables_tab()

        # Stats, guide, and notes tabs
        self.deck_stats_panel = DeckStatsPanel(
            self.deck_tabs,
            card_manager=self.controller.card_repo.get_card_manager(),
            deck_service=self.controller.deck_service,
        )
        self.deck_tabs.AddPage(self.deck_stats_panel, "Stats")
        # Maintain compatibility with callers/tests that accessed the old label directly.
        self.stats_summary = self.deck_stats_panel.summary_label

        self.sideboard_guide_panel = SideboardGuidePanel(
            self.deck_tabs,
            on_add_entry=self._on_add_guide_entry,
            on_edit_entry=self._on_edit_guide_entry,
            on_remove_entry=self._on_remove_guide_entry,
            on_edit_exclusions=self._on_edit_exclusions,
            on_export_csv=self._on_export_guide,
            on_import_csv=self._on_import_guide,
        )
        self.deck_tabs.AddPage(self.sideboard_guide_panel, "Sideboard Guide")

        self.deck_notes_panel = DeckNotesPanel(
            self.deck_tabs,
            deck_repo=self.controller.deck_repo,
            store_service=self.controller.store_service,
            notes_store=self.controller.deck_notes_store,
            notes_store_path=self.controller.notes_store_path,
            on_status_update=self._set_status,
        )
        self.deck_tabs.AddPage(self.deck_notes_panel, "Deck Notes")
        return detail_sizer

    def _build_deck_tables_tab(self) -> None:
        self.deck_tables_page = wx.Panel(self.deck_tabs)
        self.deck_tabs.AddPage(self.deck_tables_page, "Deck Tables")
        tables_sizer = wx.BoxSizer(wx.VERTICAL)
        self.deck_tables_page.SetSizer(tables_sizer)

        self.zone_notebook = self._create_notebook(self.deck_tables_page)
        tables_sizer.Add(self.zone_notebook, 1, wx.EXPAND | wx.BOTTOM, PADDING_MD)

        # Create zone tables
        self.main_table = self._create_zone_table("main", "Mainboard")
        self.side_table = self._create_zone_table("side", "Sideboard")
        self.out_table = None

        # Collection status
        self.collection_status_label = wx.StaticText(
            self.deck_tables_page, label="Collection inventory not loaded."
        )
        self.collection_status_label.SetForegroundColour(SUBDUED_TEXT)
        tables_sizer.Add(
            self.collection_status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM
        )

    def _create_zone_table(
        self, zone: str, tab_name: str, owned_status_func=None
    ) -> CardTablePanel:
        if owned_status_func is None:
            owned_status_func = self.controller.collection_service.get_owned_status

        table = CardTablePanel(
            self.zone_notebook,
            zone,
            self.mana_icons,
            self.controller.card_repo.get_card_metadata,
            owned_status_func,
            self._handle_zone_delta,
            self._handle_zone_remove,
            self._handle_zone_add,
            self._handle_card_focus,
            self._handle_card_hover,
        )
        self.zone_notebook.AddPage(table, tab_name)
        return table

    # ------------------------------------------------------------------ Left panel helpers -------------------------------------------------
    def _show_left_panel(self, mode: str, force: bool = False) -> None:
        target = "builder" if mode == "builder" else "research"
        if self.left_stack:
            index = 1 if target == "builder" else 0
            if force or self.left_stack.GetSelection() != index:
                self.left_stack.ChangeSelection(index)
        if target == "builder":
            self.ensure_card_data_loaded()
        if force or self.left_mode != target:
            self.left_mode = target
            self._schedule_settings_save()

    def _open_full_mana_keyboard(self) -> None:
        self.mana_keyboard_window = open_mana_keyboard(
            self, self.mana_icons, self.mana_keyboard_window, self._on_mana_keyboard_closed
        )

    def _open_radar_dialog(self):
        """Open the Radar dialog for archetype card frequency analysis."""
        dialog = RadarDialog(
            parent=self,
            metagame_repo=self.controller.metagame_repo,
            format_name=self.current_format,
        )

        if dialog.ShowModal() == wx.ID_OK:
            radar = dialog.get_current_radar()
            dialog.Destroy()
            return radar

        dialog.Destroy()
        return None

    def _restore_session_state(self) -> None:
        state = self.controller.session_manager.restore_session_state(self.controller.zone_cards)

        # Restore left panel mode
        self._show_left_panel(state["left_mode"], force=True)

        has_saved_deck = bool(state.get("zone_cards"))

        # Restore zone cards
        if has_saved_deck:
            if self.controller.card_repo.is_card_data_ready():
                self._render_current_deck()
            else:
                self._pending_deck_restore = True
                self._set_status("Loading card database to restore saved deck...")
                self.ensure_card_data_loaded()

        # Restore deck text
        if (
            state.get("deck_text")
            and self.controller.card_repo.is_card_data_ready()
            and not has_saved_deck
        ):
            self._update_stats(state["deck_text"])
            self.copy_button.Enable(True)
            self.save_button.Enable(True)

    def _set_status(self, message: str) -> None:
        if self.status_bar:
            self.status_bar.SetStatusText(message)
        logger.info(message)

    # ------------------------------------------------------------------ Window persistence ---------------------------------------------------
    def _save_window_settings(self) -> None:
        self.window_persistence.save_now()

    def _apply_window_preferences(self) -> None:
        self.window_persistence.apply_saved_preferences()

    def _schedule_settings_save(self) -> None:
        self.window_persistence.schedule_save()

    def fetch_archetypes(self, force: bool = False) -> None:
        self.research_panel.set_loading_state()
        self.controller.deck_repo.clear_decks_list()
        self.deck_list.Clear()
        self._clear_deck_display()
        self.daily_average_button.Disable()
        self.copy_button.Disable()
        self.save_button.Disable()

        self.controller.fetch_archetypes(
            on_success=lambda archetypes: wx.CallAfter(self._on_archetypes_loaded, archetypes),
            on_error=lambda error: wx.CallAfter(self._on_archetypes_error, error),
            on_status=lambda msg: wx.CallAfter(self._set_status, msg),
            force=force,
        )

    def _clear_deck_display(self) -> None:
        self.controller.deck_repo.set_current_deck(None)
        self.summary_text.ChangeValue("Select an archetype to view decks.")
        self.zone_cards = {"main": [], "side": [], "out": []}
        self.main_table.set_cards([])
        self.side_table.set_cards([])
        if self.out_table:
            self.out_table.set_cards(self.zone_cards["out"])
        self.controller.deck_repo.set_current_deck_text("")
        self._update_stats("")
        self.deck_notes_panel.clear()
        self.sideboard_guide_panel.clear()
        self.card_inspector_panel.reset()

    def _render_current_deck(self) -> None:
        """Render the saved deck into the UI once card data is available."""
        self.main_table.set_cards(self.zone_cards["main"])
        self.side_table.set_cards(self.zone_cards["side"])
        if self.out_table:
            self.out_table.set_cards(self.zone_cards["out"])
        deck_text = self.controller.deck_repo.get_current_deck_text()
        if deck_text:
            self._update_stats(deck_text)
            self.copy_button.Enable(True)
            self.save_button.Enable(True)
        self._pending_deck_restore = False

    def _render_pending_deck(self) -> None:
        """Render a saved deck after card data finishes loading."""
        if not self.controller.card_repo.is_card_data_ready():
            return
        if self._pending_deck_restore or self._has_deck_loaded():
            self._render_current_deck()

    def _populate_archetype_list(self) -> None:
        archetype_names = [item.get("name", "Unknown") for item in self.filtered_archetypes]
        self.research_panel.populate_archetypes(archetype_names)

    def _on_deck_download_success(self, content: str) -> None:
        self._on_deck_content_ready(content, source="mtggoldfish")

    def _has_deck_loaded(self) -> bool:
        return bool(self.zone_cards["main"] or self.zone_cards["side"])

    def _update_stats(self, deck_text: str) -> None:
        self.deck_stats_panel.update_stats(deck_text, self.zone_cards)


def launch_app() -> None:
    app = wx.App(False)
    controller = get_deck_selector_controller()
    controller.frame.Show()
    app.MainLoop()


__all__ = ["AppFrame", "launch_app"]
