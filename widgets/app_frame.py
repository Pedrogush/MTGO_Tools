from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from controllers.app_controller import get_deck_selector_controller

if TYPE_CHECKING:
    from controllers.app_controller import AppController

from utils.constants import APP_FRAME_MIN_SIZE, APP_FRAME_SIZE
from utils.mana_icon_factory import ManaIconFactory
from widgets.builders.app_frame_builder import AppFrameBuilder
from widgets.coordinators.app_event_coordinator import AppEventCoordinator
from widgets.dialogs.image_download_dialog import show_image_download_dialog
from widgets.handlers.app_event_handlers import AppEventHandlers
from widgets.handlers.card_table_panel_handler import CardTablePanelHandler
from widgets.handlers.sideboard_guide_handlers import SideboardGuideHandlers
from widgets.identify_opponent import MTGOpponentDeckSpy
from widgets.mana_keyboard import ManaKeyboardFrame, open_mana_keyboard
from widgets.managers.dialog_manager import DialogManager
from widgets.match_history import MatchHistoryFrame
from widgets.metagame_analysis import MetagameAnalysisFrame
from widgets.panels.card_table_panel import CardTablePanel
from widgets.panels.deck_builder_panel import DeckBuilderPanel
from widgets.panels.deck_research_panel import DeckResearchPanel
from widgets.panels.radar_panel import RadarDialog
from widgets.timer_alert import TimerAlertFrame


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

        self._save_timer: wx.Timer | None = None
        self.mana_icons = ManaIconFactory()
        self._dialog_manager = DialogManager(self)
        self._event_coordinator = AppEventCoordinator(self, controller)
        self.mana_keyboard_window: ManaKeyboardFrame | None = None
        self._inspector_hover_timer: wx.Timer | None = None
        self._pending_hover: tuple[str, dict[str, Any]] | None = None
        self._pending_deck_restore: bool = False

        # Build UI using AppFrameBuilder
        self._build_ui()
        self._apply_window_preferences()
        self.SetMinSize(APP_FRAME_MIN_SIZE)
        self.Centre(wx.BOTH)

        # Bind events (routed through coordinator)
        self.Bind(wx.EVT_CLOSE, self._event_coordinator.on_close)
        self.Bind(wx.EVT_SIZE, self._event_coordinator.on_window_change)
        self.Bind(wx.EVT_MOVE, self._event_coordinator.on_window_change)
        self.Bind(wx.EVT_CHAR_HOOK, self._event_coordinator.on_hotkey)

    # Backward compatibility properties for dialog windows
    @property
    def tracker_window(self) -> MTGOpponentDeckSpy | None:
        return self._dialog_manager.get_window("tracker_window")

    @property
    def timer_window(self) -> TimerAlertFrame | None:
        return self._dialog_manager.get_window("timer_window")

    @property
    def history_window(self) -> MatchHistoryFrame | None:
        return self._dialog_manager.get_window("history_window")

    @property
    def metagame_window(self) -> MetagameAnalysisFrame | None:
        return self._dialog_manager.get_window("metagame_window")

    # ------------------------------------------------------------------ UI ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Build the main UI structure using AppFrameBuilder."""
        # Create callbacks dict for builder
        callbacks = self._create_builder_callbacks()

        # Build UI via builder
        builder = AppFrameBuilder(self, self.controller, self.mana_icons, callbacks)
        widgets = builder.build_all()

        # Store widget references
        self.status_bar = widgets.status_bar
        self.left_stack = widgets.left_stack
        self.research_panel = widgets.research_panel
        self.builder_panel = widgets.builder_panel
        self.toolbar = widgets.toolbar
        self.deck_source_choice = widgets.deck_source_choice
        self.zone_notebook = widgets.zone_notebook
        self.main_table = widgets.main_table
        self.side_table = widgets.side_table
        self.out_table = widgets.out_table
        self.deck_tabs = widgets.deck_tabs
        self.deck_stats_panel = widgets.deck_stats_panel
        self.sideboard_guide_panel = widgets.sideboard_guide_panel
        self.deck_notes_panel = widgets.deck_notes_panel
        self.card_inspector_panel = widgets.card_inspector_panel
        self.summary_text = widgets.summary_text
        self.deck_list = widgets.deck_list
        self.deck_action_buttons = widgets.deck_action_buttons
        self.collection_status_label = widgets.collection_status_label
        self.daily_average_button = widgets.daily_average_button
        self.copy_button = widgets.copy_button
        self.save_button = widgets.save_button
        self.stats_summary = widgets.stats_summary
        self.deck_tables_page = widgets.deck_tables_page

        # Keep backward compatibility references for image service
        self.image_cache = self.controller.image_service.image_cache
        self.image_downloader = self.controller.image_service.image_downloader

        # Set initial status
        self._set_status("Ready")

        # Show initial left panel mode
        self._show_left_panel(self.left_mode, force=True)

    def _create_builder_callbacks(self) -> dict[str, Any]:
        """Create callbacks dict for AppFrameBuilder.

        Routes all callbacks through the event coordinator for centralized handling.
        """
        return {
            # Research panel callbacks
            "on_format_changed": self._event_coordinator.on_format_changed,
            "on_archetype_filter": self._event_coordinator.on_archetype_filter,
            "on_archetype_selected": self._event_coordinator.on_archetype_selected,
            "on_reload_archetypes": lambda: self._event_coordinator.fetch_archetypes(force=True),
            # Builder panel callbacks
            "on_switch_to_research": lambda: self._show_left_panel("research"),
            "on_ensure_card_data": self._event_coordinator.ensure_card_data_loaded,
            "open_mana_keyboard": self._open_full_mana_keyboard,
            "on_builder_search": self._event_coordinator.on_builder_search,
            "on_builder_clear": self._event_coordinator.on_builder_clear,
            "on_builder_result_selected": self._event_coordinator.on_builder_result_selected,
            "on_open_radar_dialog": self._event_coordinator.open_radar_dialog,
            # Toolbar callbacks
            "open_opponent_tracker": self._event_coordinator.open_opponent_tracker,
            "open_timer_alert": self._event_coordinator.open_timer_alert,
            "open_match_history": self._event_coordinator.open_match_history,
            "open_metagame_analysis": self._event_coordinator.open_metagame_analysis,
            "on_download_card_images": lambda: show_image_download_dialog(
                self, self.controller.image_service.image_cache,
                self.controller.image_service.image_downloader, self._set_status
            ),
            # Deck source callback
            "on_deck_source_changed": self._event_coordinator.on_deck_source_changed,
            # Deck results callbacks
            "on_deck_selected": self._event_coordinator.on_deck_selected,
            "on_copy_clicked": lambda: self._event_coordinator.on_copy_clicked(None),
            "on_save_clicked": lambda: self._event_coordinator.on_save_clicked(None),
            "on_daily_average_clicked": lambda: self._event_coordinator.on_daily_average_clicked(None),
            # Sideboard guide callbacks
            "on_add_guide_entry": self._event_coordinator.on_add_guide_entry,
            "on_edit_guide_entry": self._event_coordinator.on_edit_guide_entry,
            "on_remove_guide_entry": self._event_coordinator.on_remove_guide_entry,
            "on_edit_exclusions": self._event_coordinator.on_edit_exclusions,
            "on_export_guide": self._event_coordinator.on_export_guide,
            "on_import_guide": self._event_coordinator.on_import_guide,
            # Zone table callbacks
            "handle_zone_delta": self._event_coordinator.handle_zone_delta,
            "handle_zone_remove": self._event_coordinator.handle_zone_remove,
            "handle_zone_add": self._event_coordinator.handle_zone_add,
            "handle_card_focus": self._event_coordinator.handle_card_focus,
            "handle_card_hover": self._event_coordinator.handle_card_hover,
            # Status callback
            "set_status": self._set_status,
        }


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
        # Note: Mana keyboard uses a different opening pattern, integrate later
        self.mana_keyboard_window = open_mana_keyboard(
            self, self.mana_icons, self.mana_keyboard_window, self._on_mana_keyboard_closed
        )

    def _on_mana_keyboard_closed(self, event: wx.CloseEvent) -> None:
        self.mana_keyboard_window = None
        event.Skip()

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
        pos = self.GetPosition()
        size = self.GetSize()
        self.controller.save_settings(
            window_size=(size.width, size.height), screen_pos=(pos.x, pos.y)
        )

    def _apply_window_preferences(self) -> None:
        state = self.controller.session_manager.restore_session_state(self.controller.zone_cards)

        # Apply window size
        if "window_size" in state:
            try:
                width, height = state["window_size"]
                self.SetSize(wx.Size(int(width), int(height)))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid saved window size")

        # Apply window position
        if "screen_pos" in state:
            try:
                x, y = state["screen_pos"]
                self.SetPosition(wx.Point(int(x), int(y)))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid saved window position")

    def _schedule_settings_save(self) -> None:
        if self._save_timer is None:
            self._save_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_pending_settings, self._save_timer)
        if self._save_timer.IsRunning():
            self._save_timer.Stop()
        self._save_timer.StartOnce(600)

    def _flush_pending_settings(self, _event: wx.TimerEvent) -> None:
        self._save_window_settings()

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
