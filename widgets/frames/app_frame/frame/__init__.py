"""Main application frame UI construction package.

The :class:`AppFrame` itself owns the overall window state and orchestrates the
top-level layout, while each of the three column-builder mixins
(:mod:`left_panel`, :mod:`center_panel`, :mod:`right_panel`) is responsible for
constructing a specific section of the UI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

from utils.app_icon import apply_app_icon
from utils.constants import (
    APP_FRAME_SIZE,
    COLLAPSE_TOGGLE_WIDTH,
    DARK_BG,
    DARK_PANEL,
    LIGHT_TEXT,
    SPACE_MD,
    SPACE_SM,
    STATUS_BAR_UPDATE_FIELD_WIDTH,
)
from utils.i18n import SUPPORTED_LOCALES, translate
from utils.perf import timed
from widgets.frames.app_frame.frame.center_panel import CenterPanelBuilderMixin
from widgets.frames.app_frame.frame.left_panel import LeftPanelBuilderMixin
from widgets.frames.app_frame.frame.right_panel import RightPanelBuilderMixin
from widgets.frames.app_frame.handlers import (
    AppFrameHandlersMixin,
    CardInspectorPreviewHandlers,
    CardSelectionHandlers,
    CardShortcutHandlers,
    ChildWindowHandlers,
    DataLoadingHandlers,
    DeckContentHandlers,
    DeckResearchHandlers,
    SideboardGuideEntryHandlers,
    SideboardGuideImportExportHandlers,
    SideboardGuidePersistenceHandlers,
    SideboardGuideRecordHandlers,
    ZoneEditingHandlers,
)
from widgets.frames.app_frame.properties import AppFramePropertiesMixin
from widgets.frames.identify_opponent import MTGOpponentDeckSpy
from widgets.frames.mana_keyboard import ManaKeyboardFrame
from widgets.frames.match_history import MatchHistoryFrame
from widgets.frames.radar import RadarFrame
from widgets.frames.timer_alert import TimerAlertFrame
from widgets.frames.top_cards import TopCardsFrame
from widgets.mana_icon_factory import ManaIconFactory
from widgets.menu_bar import AppMenuBar
from widgets.panels.card_table_panel import CardTablePanel
from widgets.panels.deck_builder_panel import DeckBuilderPanel
from widgets.panels.deck_research_panel import DeckResearchPanel
from widgets.status_bar import ThemedStatusBar
from widgets.stylize import init_top_level_window, strip_native_button_frame

if TYPE_CHECKING:
    from controllers.app_controller import AppController
    from widgets.frames.metagame_analysis import MetagameAnalysisFrame


class AppFrame(
    AppFrameHandlersMixin,
    AppFramePropertiesMixin,
    DeckResearchHandlers,
    DeckContentHandlers,
    ChildWindowHandlers,
    DataLoadingHandlers,
    SideboardGuidePersistenceHandlers,
    SideboardGuideEntryHandlers,
    SideboardGuideImportExportHandlers,
    SideboardGuideRecordHandlers,
    ZoneEditingHandlers,
    CardShortcutHandlers,
    CardSelectionHandlers,
    CardInspectorPreviewHandlers,
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
        init_top_level_window(self)
        apply_app_icon(self)

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
        # Collapsible side panels (#small-screen support): the left sidebar and
        # the right card-inspector column can each be hidden to reclaim width
        # (and, for the inspector, height). State is restored from settings in
        # _apply_window_preferences and persisted on every toggle.
        self.left_panel_window: wx.Panel | None = None
        self.inspector_panel: wx.Panel | None = None
        self.left_toggle_btn: wx.Button | None = None
        self.inspector_toggle_btn: wx.Button | None = None
        self._left_collapsed: bool = False
        self._inspector_collapsed: bool = False
        # With both zones visible at once (#781) there is no "selected tab" to
        # tell which zone a searched card should be added to; track the last zone
        # the user interacted with instead (defaults to mainboard).
        self._active_deck_zone: str = "main"
        self._deck_sash_initialized: bool = False
        # Per-card printing selection for the loaded deck (issue #792): maps a
        # lower-cased card name to ``{"uuid", "set"}`` of the printing the board
        # art and inspector should show. Derived from the deck text on load and
        # updated as the user scrolls/saves printings in the inspector.
        self._printing_selections: dict[str, dict[str, Any]] = {}
        # Names whose printing changed on the latest load; the board's per-name
        # image cache must be force-refreshed for these (a plain set_cards reuses
        # the cached bitmap and would keep showing the previous printing).
        self._changed_printing_names: set[str] = set()
        # Sideboard-guide record mode (#782): state dict + floating control bar,
        # both None unless a record walk is in progress.
        self._guide_record: dict[str, Any] | None = None
        self._guide_record_bar: wx.MiniFrame | None = None

        self._save_timer: wx.Timer | None = None
        self._filter_debounce_timer: wx.Timer | None = None
        # Coalesced downloaded-image refreshes: completed downloads accumulate
        # here and the deck tables repaint in one pass per timer tick.
        self._pending_image_refresh_names: set[str] = set()
        self._image_refresh_timer: wx.Timer | None = None
        # PERF tracking (issue #951): deck-load → all-deck-images-local timing.
        # Set when a deck's zone prefetch is submitted; cleared when the last
        # of its images lands (or replaced by the next deck load).
        self._deck_image_perf: dict[str, Any] | None = None
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
        # Dedup state for the "Any" deck reload triggered on archetype load.
        # Archetype fetch uses stale-while-revalidate, which delivers results
        # twice (cached then background-refreshed); see _on_archetypes_loaded
        # and _load_decks for the two guards that collapse the redundant load.
        self._last_archetype_reload_sig: tuple[str, tuple[str, ...]] | None = None
        self._last_deck_load_sig: tuple[str, str, str] | None = None
        self._last_deck_load_time: float = 0.0

        self._build_ui()
        # Establish the structural minimum first, then size/place the window
        # within the available display (which may maximize and/or auto-collapse
        # the inspector on a small screen, and recompute the minimum to match).
        self._apply_min_size()
        self._apply_window_preferences()

        # Seed the card panel with the active format so the Stats tab can
        # render format-level totals before the user touches any selectors.
        if hasattr(self, "card_panel"):
            self.card_panel.update_format(getattr(self, "current_format", None))

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_SIZE, self.on_window_change)
        self.Bind(wx.EVT_MOVE, self.on_window_change)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_hotkey)

    @timed
    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_BG)

        # The frame owns a vertical sizer now: the content panel above, the status
        # strip below. Before phase 1 the frame had no sizer at all — wx auto-sized
        # its single child panel to the client area and CreateStatusBar reserved
        # the strip's height itself. A second child needs the layout spelled out.
        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(frame_sizer)

        # The menu bar spans the whole window, above both columns. It used to be
        # six buttons plus a gear inside the *right* column, which made the
        # right column's minimum width the greater of "the toolbar" and "the
        # content under it" -- and put a row of secondary actions inside the
        # deck workspace's own column, where it does not belong.
        self.menu_bar = AppMenuBar(self, self.menu_specs())
        frame_sizer.Add(self.menu_bar, 0, wx.EXPAND | wx.LEFT | wx.TOP, SPACE_SM)

        self.root_panel = wx.Panel(self)
        self.root_panel.SetBackgroundColour(DARK_BG)
        root_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.root_panel.SetSizer(root_sizer)
        frame_sizer.Add(self.root_panel, 1, wx.EXPAND)

        self._setup_status_bar()
        frame_sizer.Add(self.status_bar, 0, wx.EXPAND)

        # Each gap is applied by exactly one child. Giving all three wx.ALL put
        # SPACE_MD on both sides of every boundary, so the collapse gutter sat in
        # a 48px well and the window spent 80px of its minimum width on chrome.
        # Now: SPACE_MD at the two window edges, SPACE_SM either side of the
        # gutter. Same visual rhythm, 16px of minimum width back.
        self.left_panel_window = self._build_left_panel(self.root_panel)
        root_sizer.Add(
            self.left_panel_window, 0, wx.EXPAND | wx.LEFT | wx.TOP | wx.BOTTOM, SPACE_MD
        )

        # Thin full-height gutter button to collapse/expand the left sidebar.
        self.left_toggle_btn = self._build_collapse_toggle(
            self.root_panel,
            on_click=self.toggle_left_panel,
            tooltip=self._t("app.tooltip.toggle_left_panel"),
        )
        root_sizer.Add(self.left_toggle_btn, 0, wx.EXPAND | wx.ALL, SPACE_SM)

        right_container = self._build_right_container(self.root_panel)
        root_sizer.Add(right_container, 1, wx.EXPAND | wx.RIGHT | wx.TOP | wx.BOTTOM, SPACE_MD)

    def _build_collapse_toggle(self, parent: wx.Window, *, on_click, tooltip: str) -> wx.Button:
        """A narrow full-height button used to collapse/expand a side panel.

        The caret label is set by the owning toggle handler to point in the
        direction the panel will move when clicked.
        """
        btn = wx.Button(parent, label="◀", size=(COLLAPSE_TOGGLE_WIDTH, -1), style=wx.BU_EXACTFIT)
        btn.SetMinSize((COLLAPSE_TOGGLE_WIDTH, -1))
        btn.SetMaxSize((COLLAPSE_TOGGLE_WIDTH, -1))
        btn.SetBackgroundColour(DARK_PANEL)
        btn.SetForegroundColour(LIGHT_TEXT)
        # Phase 2 stripped wxMSW's 2px light-grey native button frame everywhere
        # it went through stylize_button; these two set their colours by hand and
        # kept theirs. They are full-height, so what survived was two 14:1
        # near-white rules running the entire height of the window -- the
        # brightest chrome left on the main window, and container chrome at that.
        strip_native_button_frame(btn)
        btn.SetToolTip(tooltip)
        btn.Bind(wx.EVT_BUTTON, lambda _evt: on_click())
        return btn

    def begin_active_marquee(self, screen_point: wx.Point, *, additive: bool = False) -> None:
        """Start a marquee on the visible deck view from a screen-space press.

        Called by the app-level event filter (see ``MetagameWxApp.FilterEvent``)
        when a press lands on a plain background surface anywhere in the window.
        The active deck tab's current card view hosts the rubber-band, so the
        selection box can be drawn from any non-interactive zone. A no-op unless
        that tab is a card panel with cards loaded.
        """
        # In the deck-tables split both zones share a page, so target whichever
        # zone the press landed over rather than the page (the splitter itself
        # has no marquee).
        for table in (getattr(self, "main_table", None), getattr(self, "side_table", None)):
            if table and table.IsShownOnScreen() and table.GetScreenRect().Contains(screen_point):
                table.begin_marquee_at_screen(screen_point, additive=additive)
                return
        page = self.deck_tabs.GetCurrentPage()
        begin = getattr(page, "begin_marquee_at_screen", None)
        if callable(begin):
            begin(screen_point, additive=additive)

    def _setup_status_bar(self) -> None:
        # Two fields: transient status text on the left (everything _set_status
        # writes), and a fixed-width slot on the right that stays empty unless
        # an update is available — see _on_update_available. Keeping them apart
        # means the passive update note can't be overwritten by the next status
        # message, and can't steal width from it either.
        #
        # An own-drawn strip rather than wx.StatusBar: wxMSW honours the status
        # bar's background colour and silently ignores its foreground, which left
        # the app's main feedback channel at 1.40:1. See widgets.status_bar.
        self.status_bar = ThemedStatusBar(self, 2)
        self.status_bar.SetStatusWidths([-1, STATUS_BAR_UPDATE_FIELD_WIDTH])
        self._set_status("app.status.ready")

    @timed
    def _build_right_container(self, parent: wx.Window) -> wx.Panel:
        """Compose the right side of the window: toolbar over (center | inspector)."""
        right_panel = wx.Panel(parent)
        right_panel.SetBackgroundColour(DARK_BG)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        right_panel.SetSizer(right_sizer)

        content_split = wx.BoxSizer(wx.HORIZONTAL)
        right_sizer.Add(content_split, 1, wx.EXPAND | wx.BOTTOM, SPACE_MD)

        # The deck workspace takes all leftover horizontal space (proportion 1)
        # so a wider window grows the workspace — and the grid view fits more
        # cards per row — rather than leaving empty background (issue #785). The
        # inspector column stays at its natural width (proportion 0) and can be
        # collapsed via the gutter button to hand its width to the workspace.
        deck_workspace = self._build_deck_workspace(right_panel)
        content_split.Add(deck_workspace, 1, wx.EXPAND | wx.RIGHT, SPACE_SM)

        self.inspector_toggle_btn = self._build_collapse_toggle(
            right_panel,
            on_click=self.toggle_inspector,
            tooltip=self._t("app.tooltip.toggle_inspector"),
        )
        content_split.Add(self.inspector_toggle_btn, 0, wx.EXPAND | wx.RIGHT, SPACE_SM)

        # Inspector column wrapped in a single panel so it can be shown/hidden as
        # a unit (collapsing reclaims its width and, importantly, its height —
        # the 360px card image is the tallest element in the layout).
        self.inspector_panel = wx.Panel(right_panel)
        self.inspector_panel.SetBackgroundColour(DARK_BG)
        inspector_column = wx.BoxSizer(wx.VERTICAL)
        self.inspector_panel.SetSizer(inspector_column)

        # One section card, not two (§4.6). Proportion 1 so the tabs inside it
        # grow with the window; the art block above them is fixed.
        inspector_box = self._build_card_inspector(self.inspector_panel)
        inspector_column.Add(inspector_box, 1, wx.EXPAND)

        content_split.Add(self.inspector_panel, 0, wx.EXPAND)

        return right_panel


__all__ = ["AppFrame"]
