"""UI construction for the main application frame."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx
from wx.lib.agw import flatnotebook as fnb

from controllers.app_controller import get_deck_selector_controller

if TYPE_CHECKING:
    from controllers.app_controller import AppController

from utils.constants import (
    APP_FRAME_SIZE,
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
from utils.i18n import SUPPORTED_LOCALES, translate
from utils.mana_icon_factory import ManaIconFactory
from widgets.buttons.toolbar_buttons import ToolbarButtons
from widgets.frames.app_frame.handlers import (
    AppEventHandlers,
    AppFrameHandlersMixin,
    CardTablesHandler,
    SideboardGuideHandlers,
)
from widgets.frames.app_frame.properties import AppFramePropertiesMixin
from widgets.frames.identify_opponent import MTGOpponentDeckSpy
from widgets.frames.mana_keyboard import ManaKeyboardFrame
from widgets.frames.match_history import MatchHistoryFrame
from widgets.frames.metagame_analysis import MetagameAnalysisFrame
from widgets.frames.radar import RadarFrame
from widgets.frames.timer_alert import TimerAlertFrame
from widgets.frames.top_cards import TopCardsFrame
from widgets.panels.card_inspector_panel import CardInspectorPanel
from widgets.panels.card_table_panel import CardTablePanel
from widgets.panels.deck_builder_panel import DeckBuilderPanel
from widgets.panels.deck_notes_panel import DeckNotesPanel
from widgets.panels.deck_research_panel import DeckResearchPanel
from widgets.panels.deck_stats_panel import DeckStatsPanel
from widgets.panels.mana_rich_text_ctrl import ManaSymbolRichCtrl
from widgets.panels.sideboard_guide_panel import SideboardGuidePanel


class AppFrame(
    AppFrameHandlersMixin,
    AppFramePropertiesMixin,
    AppEventHandlers,
    SideboardGuideHandlers,
    CardTablesHandler,
    wx.Frame,
):
    """wxPython-based metagame research + deck builder UI."""

    def __init__(
        self,
        controller: AppController,
        parent: wx.Window | None = None,
    ):
        super().__init__(
            parent,
            title=translate(controller.get_language(), "app.title.main_frame"),
            size=APP_FRAME_SIZE,
        )

        # Store controller reference - ALL state and business logic goes through this
        self.controller: AppController = controller
        self.card_data_dialogs_disabled = False
        self._builder_search_pending = False
        self._search_seq = 0
        self.locale = self.controller.get_language()
        self._deck_source_values = ["both", "mtggoldfish", "mtgo"]
        self._language_values = list(SUPPORTED_LOCALES)
        self.deck_source_choice: wx.Choice | None = None
        self.language_choice: wx.Choice | None = None

        self.sideboard_guide_entries: list[dict[str, str]] = []
        self.sideboard_exclusions: list[str] = []
        self.sideboard_flex_slots: list[str] = []
        self.active_inspector_zone: str | None = None
        self.left_stack: wx.Simplebook | None = None
        self.research_panel: DeckResearchPanel | None = None
        self.builder_panel: DeckBuilderPanel | None = None
        self.out_table: CardTablePanel | None = None
        self.root_panel: wx.Panel | None = None

        self._save_timer: wx.Timer | None = None
        self._filter_debounce_timer: wx.Timer | None = None
        self.mana_icons = ManaIconFactory()
        self.tracker_window: MTGOpponentDeckSpy | None = None
        self.timer_window: TimerAlertFrame | None = None
        self.history_window: MatchHistoryFrame | None = None
        self.metagame_window: MetagameAnalysisFrame | None = None
        self.top_cards_window: TopCardsFrame | None = None
        self.radar_window: RadarFrame | None = None
        self.mana_keyboard_window: ManaKeyboardFrame | None = None
        self._inspector_hover_timer: wx.Timer | None = None
        self._pending_hover: tuple[str, dict[str, Any]] | None = None
        self._pending_deck_restore: bool = False
        self._is_first_deck_load: bool = True
        self._all_loaded_decks: list[dict[str, Any]] = []

        self._build_ui()
        self._apply_window_preferences()
        self._apply_min_size()
        self.Centre(wx.BOTH)

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_SIZE, self.on_window_change)
        self.Bind(wx.EVT_MOVE, self.on_window_change)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_hotkey)

    # ------------------------------------------------------------------ UI ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_BG)
        self._setup_status_bar()

        self.root_panel = wx.Panel(self)
        self.root_panel.SetBackgroundColour(DARK_BG)
        root_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.root_panel.SetSizer(root_sizer)

        # Build left and right panels
        left_panel = self._build_left_panel(self.root_panel)
        root_sizer.Add(left_panel, 0, wx.EXPAND | wx.ALL, PADDING_LG)

        right_panel = self._build_right_panel(self.root_panel)
        root_sizer.Add(right_panel, 1, wx.EXPAND | wx.ALL, PADDING_LG)

    def _setup_status_bar(self) -> None:
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetBackgroundColour(DARK_PANEL)
        self.status_bar.SetForegroundColour(LIGHT_TEXT)
        self._set_status("app.status.ready")

    def _build_left_panel(self, parent: wx.Window) -> wx.Panel:
        left_panel = wx.Panel(parent)
        left_panel.SetBackgroundColour(DARK_PANEL)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        left_panel.SetSizer(left_sizer)

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
            on_switch_to_builder=lambda: self._show_left_panel("builder"),
            on_deck_selected=self.on_deck_selected,
            on_copy=lambda: self.on_copy_clicked(None),
            on_save=lambda: self.on_save_clicked(None),
            on_daily_average=lambda: self.on_daily_average_clicked(None),
            on_load=self.on_load_deck_clicked,
            on_event_type_filter=self.on_event_type_filter_changed,
            on_placement_filter=self.on_placement_filter_changed,
            on_player_name_filter=self.on_player_name_filter_changed,
            on_date_filter=self.on_date_filter_changed,
            labels={
                "format": self._t("research.format"),
                "archetype": self._t("research.archetype"),
                "event": self._t("research.event"),
                "player_name": self._t("research.player_name"),
                "placement": self._t("research.placement"),
                "placement_hint": self._t("research.placement_hint"),
                "date": self._t("research.date"),
                "info": self._t("research.info"),
                "search_hint": self._t("research.search_hint"),
                "loading_archetypes": self._t("research.loading_archetypes"),
                "failed_archetypes": self._t("research.failed_archetypes"),
                "no_archetypes": self._t("research.no_archetypes"),
                "switch_to_builder": self._t("research.switch_to_builder"),
                "format_tooltip": self._t("research.tooltip.format"),
                "search_tooltip": self._t("research.tooltip.search"),
                "archetypes_tooltip": self._t("research.tooltip.archetypes"),
                "daily_average": self._t("deck_actions.daily_average"),
                "copy": self._t("deck_actions.copy"),
                "load_deck": self._t("deck_actions.load_deck"),
                "save_deck": self._t("deck_actions.save_deck"),
                "daily_average_tooltip": self._t("deck_actions.tooltip.daily_average"),
                "copy_tooltip": self._t("deck_actions.tooltip.copy"),
                "load_deck_tooltip": self._t("deck_actions.tooltip.load_deck"),
                "save_deck_tooltip": self._t("deck_actions.tooltip.save_deck"),
            },
        )
        self.left_stack.AddPage(self.research_panel, self._t("app.label.left_panel.research"))

        self.builder_panel = DeckBuilderPanel(
            parent=self.left_stack,
            mana_icons=self.mana_icons,
            on_switch_to_research=lambda: self._show_left_panel("research"),
            on_ensure_card_data=self.ensure_card_data_loaded,
            open_mana_keyboard=self._open_full_mana_keyboard,
            on_search=self._on_builder_search,
            on_clear=self._on_builder_clear,
            on_result_selected=self._on_builder_result_selected,
            on_add_to_main=lambda name: self._handle_zone_delta("main", name, 1),
            on_add_to_side=lambda name: self._handle_zone_delta("side", name, 1),
            on_add_to_active_zone=self._add_search_card_to_active_zone,
            locale=self.locale,
        )
        self.left_stack.AddPage(self.builder_panel, self._t("app.label.left_panel.builder"))
        self._show_left_panel(self.left_mode, force=True)

        return left_panel

    def _build_right_panel(self, parent: wx.Window) -> wx.Panel:
        right_panel = wx.Panel(parent)
        right_panel.SetBackgroundColour(DARK_BG)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        right_panel.SetSizer(right_sizer)

        # Toolbar
        self.toolbar = self._build_toolbar(right_panel)
        right_sizer.Add(self.toolbar, 0, wx.EXPAND | wx.BOTTOM, PADDING_MD)

        content_split = wx.BoxSizer(wx.HORIZONTAL)
        right_sizer.Add(content_split, 1, wx.EXPAND | wx.BOTTOM, PADDING_LG)

        middle_column = wx.BoxSizer(wx.VERTICAL)
        content_split.Add(middle_column, 0, wx.EXPAND | wx.RIGHT, PADDING_LG)

        deck_workspace = self._build_deck_workspace(right_panel)
        middle_column.Add(deck_workspace, 1, wx.EXPAND)

        inspector_column = wx.BoxSizer(wx.VERTICAL)
        content_split.Add(inspector_column, 0, wx.EXPAND)

        inspector_box = self._build_card_inspector(right_panel)
        inspector_column.Add(inspector_box, 0, wx.EXPAND)

        oracle_box = self._build_oracle_text_panel(right_panel)
        inspector_column.Add(oracle_box, 1, wx.EXPAND | wx.TOP, PADDING_MD)

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

    def _build_toolbar(self, parent: wx.Window) -> ToolbarButtons:
        return ToolbarButtons(
            parent,
            on_open_opponent_tracker=self.open_opponent_tracker,
            on_open_timer_alert=self.open_timer_alert,
            on_open_match_history=self.open_match_history,
            on_open_metagame_analysis=self.open_metagame_analysis,
            on_open_top_cards=self.open_top_cards,
            on_open_radar=self.open_radar,
            on_open_settings_menu=self._open_toolbar_settings_menu,
            labels={
                "opponent_tracker": self._t("toolbar.opponent_tracker"),
                "timer_alert": self._t("toolbar.timer_alert"),
                "match_history": self._t("toolbar.match_history"),
                "metagame_analysis": self._t("toolbar.metagame_analysis"),
                "top_cards": self._t("toolbar.top_cards"),
                "radar": self._t("toolbar.radar"),
                "settings": "\u2699",
                "settings_tooltip": self._t("toolbar.settings"),
                "opponent_tracker_tooltip": self._t("toolbar.tooltip.opponent_tracker"),
                "timer_alert_tooltip": self._t("toolbar.tooltip.timer_alert"),
                "match_history_tooltip": self._t("toolbar.tooltip.match_history"),
                "metagame_analysis_tooltip": self._t("toolbar.tooltip.metagame_analysis"),
                "top_cards_tooltip": self._t("toolbar.tooltip.top_cards"),
                "radar_tooltip": self._t("toolbar.tooltip.radar"),
            },
        )

    def _build_card_inspector(self, parent: wx.Window) -> wx.StaticBoxSizer:
        inspector_box = wx.StaticBox(parent, label=self._t("app.label.card_inspector"))
        inspector_box.SetForegroundColour(LIGHT_TEXT)
        inspector_box.SetBackgroundColour(DARK_PANEL)
        inspector_sizer = wx.StaticBoxSizer(inspector_box, wx.VERTICAL)

        self.card_inspector_panel = CardInspectorPanel(
            inspector_box,
            card_manager=self.controller.card_repo.get_card_manager(),
            mana_icons=self.mana_icons,
        )
        self.card_inspector_panel.set_image_request_handlers(
            on_request=lambda request: self.controller.image_service.queue_card_image_download(
                request, prioritize=True
            ),
            on_selected=self.controller.image_service.set_selected_card_request,
        )
        self.card_inspector_panel.set_printings_request_handler(
            self.controller.image_service.fetch_printings_by_name_async
        )
        self.controller.image_service.set_image_download_callback(self._handle_image_downloaded)
        self.controller.image_service.set_printings_loaded_callback(
            self.card_inspector_panel.handle_printings_loaded
        )
        inspector_sizer.Add(self.card_inspector_panel, 1, wx.EXPAND)
        inspector_sizer.Layout()
        inspector_min_size = inspector_sizer.GetMinSize()
        inspector_box.SetMinSize(inspector_min_size)

        # Keep backward compatibility references (delegate to image service via controller)
        self.image_cache = self.controller.image_service.image_cache
        self.image_downloader = self.controller.image_service.image_downloader

        return inspector_sizer

    def _build_oracle_text_panel(self, parent: wx.Window) -> wx.StaticBoxSizer:
        oracle_box = wx.StaticBox(parent, label=self._t("app.label.oracle_text"))
        oracle_box.SetForegroundColour(LIGHT_TEXT)
        oracle_box.SetBackgroundColour(DARK_PANEL)
        oracle_sizer = wx.StaticBoxSizer(oracle_box, wx.VERTICAL)

        self.oracle_text_ctrl = ManaSymbolRichCtrl(
            oracle_box,
            self.mana_icons,
            readonly=True,
            multiline=True,
        )
        self.oracle_text_ctrl.SetMinSize((-1, 200))

        oracle_sizer.Add(self.oracle_text_ctrl, 1, wx.EXPAND | wx.ALL, PADDING_SM)
        return oracle_sizer

    def _build_deck_workspace(self, parent: wx.Window) -> wx.StaticBoxSizer:
        detail_box = wx.StaticBox(parent, label=self._t("app.label.deck_workspace"))
        detail_box.SetForegroundColour(LIGHT_TEXT)
        detail_box.SetBackgroundColour(DARK_PANEL)
        detail_sizer = wx.StaticBoxSizer(detail_box, wx.VERTICAL)

        self.deck_tabs = self._create_notebook(detail_box)
        detail_sizer.Add(self.deck_tabs, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Mainboard and Sideboard as top-level tabs
        self._build_deck_tables_tab()
        deck_tabs_width = CardTablePanel.grid_width()
        self.deck_tabs.SetMinSize((deck_tabs_width, -1))
        self.deck_tabs.SetMaxSize((deck_tabs_width, -1))
        detail_box_width = deck_tabs_width + (PADDING_MD * 2)
        detail_box.SetMinSize((detail_box_width, -1))
        detail_box.SetMaxSize((detail_box_width, -1))

        # Collection status label below the tabs
        self.collection_status_label = wx.StaticText(
            detail_box, label=self._t("app.status.collection_not_loaded")
        )
        self.collection_status_label.SetForegroundColour(SUBDUED_TEXT)
        detail_sizer.Add(
            self.collection_status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM
        )

        # Sideboard Guide and Notes tabs
        self.sideboard_guide_panel = SideboardGuidePanel(
            self.deck_tabs,
            on_add_entry=self._on_add_guide_entry,
            on_edit_entry=self._on_edit_guide_entry,
            on_remove_entry=self._on_remove_guide_entry,
            on_edit_exclusions=self._on_edit_exclusions,
            on_export_csv=self._on_export_guide,
            on_import_csv=self._on_import_guide,
            on_pin_guide=self._on_pin_guide,
            on_edit_flex_slots=self._on_edit_flex_slots,
            locale=self.locale,
        )
        self.sideboard_guide_panel.SetToolTip(self._t("tabs.tooltip.sideboard_guide"))
        self.deck_tabs.AddPage(self.sideboard_guide_panel, self._t("tabs.sideboard_guide"))

        self.deck_notes_panel = DeckNotesPanel(
            self.deck_tabs,
            deck_repo=self.controller.deck_repo,
            store_service=self.controller.store_service,
            notes_store=self.controller.deck_notes_store,
            notes_store_path=self.controller.notes_store_path,
            on_status_update=self._set_status,
            locale=self.locale,
        )
        self.deck_notes_panel.SetToolTip(self._t("tabs.tooltip.deck_notes"))
        self.deck_tabs.AddPage(self.deck_notes_panel, self._t("tabs.deck_notes"))

        # Stats panel kept hidden; stats_summary preserved for callers.
        self.deck_stats_panel = DeckStatsPanel(
            detail_box,
            card_manager=self.controller.card_repo.get_card_manager(),
            deck_service=self.controller.deck_service,
        )
        self.deck_stats_panel.Hide()
        self.stats_summary = self.deck_stats_panel.summary_label
        return detail_sizer

    def _build_deck_tables_tab(self) -> None:
        self.zone_notebook = None
        self.main_table = self._create_zone_table("main", self._t("tabs.mainboard"))
        self.main_table.SetToolTip(self._t("tabs.tooltip.mainboard"))
        self.side_table = self._create_zone_table("side", self._t("tabs.sideboard"))
        self.side_table.SetToolTip(self._t("tabs.tooltip.sideboard"))
        self.out_table = None

    def _create_zone_table(
        self, zone: str, tab_name: str, owned_status_func=None
    ) -> CardTablePanel:
        if owned_status_func is None:
            owned_status_func = self.controller.collection_service.get_owned_status

        table = CardTablePanel(
            self.deck_tabs,
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
        self.deck_tabs.AddPage(table, tab_name)
        return table


def launch_app() -> None:
    app = wx.App(False)
    controller = get_deck_selector_controller()
    controller.frame.Show()
    app.MainLoop()


__all__ = ["AppFrame", "launch_app"]
