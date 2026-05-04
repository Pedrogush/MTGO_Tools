"""Main application frame UI construction package.

The :class:`AppFrame` itself owns the overall window state and orchestrates the
top-level layout, while each of the three column-builder mixins
(:mod:`left_panel`, :mod:`center_panel`, :mod:`right_panel`) is responsible for
constructing a specific section of the UI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

from controllers.app_controller import get_deck_selector_controller
from utils.constants import (
    APP_FRAME_SIZE,
    DARK_BG,
    DARK_PANEL,
    LIGHT_TEXT,
    PADDING_LG,
    PADDING_MD,
)
from utils.i18n import SUPPORTED_LOCALES, translate
from utils.mana_icon_factory import ManaIconFactory
from widgets.frames.app_frame.frame.center_panel import CenterPanelBuilderMixin
from widgets.frames.app_frame.frame.left_panel import LeftPanelBuilderMixin
from widgets.frames.app_frame.frame.right_panel import RightPanelBuilderMixin
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
from widgets.panels.card_table_panel import CardTablePanel
from widgets.panels.deck_builder_panel import DeckBuilderPanel
from widgets.panels.deck_research_panel import DeckResearchPanel

if TYPE_CHECKING:
    from controllers.app_controller import AppController


class AppFrame(
    AppFrameHandlersMixin,
    AppFramePropertiesMixin,
    AppEventHandlers,
    SideboardGuideHandlers,
    CardTablesHandler,
    LeftPanelBuilderMixin,
    CenterPanelBuilderMixin,
    RightPanelBuilderMixin,
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

        # Seed the card panel with the active format so the Stats tab can
        # render format-level totals before the user touches any selectors.
        if hasattr(self, "card_panel"):
            self.card_panel.update_format(getattr(self, "current_format", None))

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_SIZE, self.on_window_change)
        self.Bind(wx.EVT_MOVE, self.on_window_change)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_hotkey)

    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_BG)
        self._setup_status_bar()

        self.root_panel = wx.Panel(self)
        self.root_panel.SetBackgroundColour(DARK_BG)
        root_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.root_panel.SetSizer(root_sizer)

        left_panel = self._build_left_panel(self.root_panel)
        root_sizer.Add(left_panel, 0, wx.EXPAND | wx.ALL, PADDING_LG)

        right_container = self._build_right_container(self.root_panel)
        root_sizer.Add(right_container, 1, wx.EXPAND | wx.ALL, PADDING_LG)

    def _setup_status_bar(self) -> None:
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetBackgroundColour(DARK_PANEL)
        self.status_bar.SetForegroundColour(LIGHT_TEXT)
        self._set_status("app.status.ready")

    def _build_right_container(self, parent: wx.Window) -> wx.Panel:
        """Compose the right side of the window: toolbar over (center | inspector)."""
        right_panel = wx.Panel(parent)
        right_panel.SetBackgroundColour(DARK_BG)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        right_panel.SetSizer(right_sizer)

        self.toolbar = self._build_toolbar(right_panel)
        right_sizer.Add(self.toolbar, 0, wx.EXPAND | wx.BOTTOM, PADDING_MD)

        content_split = wx.BoxSizer(wx.HORIZONTAL)
        right_sizer.Add(content_split, 1, wx.EXPAND | wx.BOTTOM, PADDING_LG)

        deck_workspace = self._build_deck_workspace(right_panel)
        content_split.Add(deck_workspace, 0, wx.EXPAND | wx.RIGHT, PADDING_LG)

        inspector_column = wx.BoxSizer(wx.VERTICAL)
        content_split.Add(inspector_column, 0, wx.EXPAND)

        inspector_box = self._build_card_inspector(right_panel)
        inspector_column.Add(inspector_box, 0, wx.EXPAND)

        card_panel_box = self._build_card_panel(right_panel)
        inspector_column.Add(card_panel_box, 1, wx.EXPAND | wx.TOP, PADDING_MD)

        return right_panel


def launch_app() -> None:
    app = wx.App(False)
    controller = get_deck_selector_controller()
    controller.frame.Show()
    app.MainLoop()


__all__ = ["AppFrame", "launch_app"]
