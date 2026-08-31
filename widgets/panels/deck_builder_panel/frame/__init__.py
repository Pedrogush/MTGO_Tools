"""Deck builder panel UI construction package.

The :class:`DeckBuilderPanel` itself owns the panel state and orchestrates the
top-to-bottom layout, while each builder mixin
(:mod:`basic_filters`, :mod:`advanced_filters`, :mod:`results_pane`) is
responsible for constructing a specific section of the UI.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx

from utils.constants import BUILDER_SCROLL_RATE_Y, DARK_PANEL
from widgets.checkbox import DarkCheckBox
from widgets.mana_icon_factory import ManaIconFactory
from widgets.panels.deck_builder_panel.frame.advanced_filters import AdvancedFiltersBuilderMixin
from widgets.panels.deck_builder_panel.frame.basic_filters import BasicFiltersBuilderMixin
from widgets.panels.deck_builder_panel.frame.results_pane import ResultsPaneBuilderMixin
from widgets.panels.deck_builder_panel.frame.search_results_view import _SearchResultsView
from widgets.panels.deck_builder_panel.handlers import DeckBuilderPanelHandlersMixin
from widgets.panels.deck_builder_panel.properties import DeckBuilderPanelPropertiesMixin
from widgets.stylize import stylize_scrollable

if TYPE_CHECKING:
    from services.radar_service import RadarData


class DeckBuilderPanel(
    DeckBuilderPanelHandlersMixin,
    DeckBuilderPanelPropertiesMixin,
    BasicFiltersBuilderMixin,
    AdvancedFiltersBuilderMixin,
    ResultsPaneBuilderMixin,
    wx.ScrolledWindow,
):
    """Panel for searching and filtering MTG cards by various properties.

    A ``wx.ScrolledWindow`` rather than a ``wx.Panel`` since phase 8. The panel
    is one long vertical column -- header, basic filters, the collapsible
    advanced block, action controls, results list, add buttons, status -- of
    which only the results list has a stretch proportion. Expanding the advanced
    filters adds 211px, and at the window's 680px floor that put the fixed items
    alone over the pane height: wxBoxSizer gave the one proportional item a
    negative share (clamped to 0, so the results list vanished) and laid the
    items *after* it out below the pane's bottom edge, so "Showing N cards."
    was simply not on screen. Nothing about that is visible from any single
    control -- it is the vertical twin of the silent row overflow phase 7
    measured.

    Scrolling makes the failure impossible rather than unlikely: a wxScrolled
    with a sizer lays out to ``max(client, virtual)``, so a tall pane behaves
    exactly as a plain panel did (no scrollbar, results list expands) and a
    short one keeps every control reachable.
    """

    def __init__(
        self,
        parent: wx.Window,
        controller: Any,
        mana_icons: ManaIconFactory,
        on_switch_to_research: Callable[[], None],
        on_ensure_card_data: Callable[[], None],
        open_mana_keyboard: Callable[[], None],
        on_search: Callable[[], None],
        on_clear: Callable[[], None],
        on_result_selected: Callable[[int | None], None],
        on_add_to_main: Callable[..., None] | None = None,
        on_add_to_side: Callable[..., None] | None = None,
        on_add_to_active_zone: Callable[[str], None] | None = None,
        on_prefetch_images: Callable[[list[str]], None] | None = None,
        locale: str | None = None,
    ) -> None:
        # wx.VSCROLL only -- the column never scrolls sideways. TAB_TRAVERSAL is
        # restated because passing `style` replaces wxPanel's default rather than
        # adding to it (phase 6c), and this panel's fields have to stay reachable
        # by Tab.
        super().__init__(parent, style=wx.VSCROLL | wx.TAB_TRAVERSAL)

        self._locale = locale
        self.controller = controller

        # Store dependencies
        self.mana_icons = mana_icons
        self._on_switch_to_research = on_switch_to_research
        self._on_ensure_card_data = on_ensure_card_data
        self._open_mana_keyboard = open_mana_keyboard
        self._on_search_callback = on_search
        self._on_clear_callback = on_clear
        self._on_result_selected_callback = on_result_selected
        self._on_add_to_main = on_add_to_main
        self._on_add_to_side = on_add_to_side
        self._on_add_to_active_zone = on_add_to_active_zone
        self._on_prefetch_images = on_prefetch_images

        # State variables
        self.inputs: dict[str, wx.TextCtrl] = {}
        self.mana_exact_cb: DarkCheckBox | None = None
        self.mv_comparator: wx.Choice | None = None
        self.mv_value: wx.TextCtrl | None = None
        self.format_choice: wx.Choice | None = None
        self.color_checks: dict[str, wx.ToggleButton] = {}
        self.color_mode_choice: wx.Choice | None = None
        self.text_mode_choice: wx.Choice | None = None
        self.results_ctrl: _SearchResultsView | None = None
        self.status_label: wx.StaticText | None = None
        self._add_main_btn: wx.Button | None = None
        self._add_side_btn: wx.Button | None = None
        self._adv_panel: wx.Panel | None = None
        self._adv_toggle_btn: wx.Button | None = None
        self.results_cache: list[dict[str, Any]] = []
        # Set while a sideboard guide is being recorded (issue #1027): every add
        # route out of this panel is refused and the column is greyed out, so a
        # deck edit can't be mistaken for a sideboarding decision.
        self.search_locked: bool = False
        self._status_before_lock: str = ""
        self._search_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_search_timer, self._search_timer)
        # Debounces image prefetch while the results list scrolls or refills.
        self._prefetch_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_prefetch_timer, self._prefetch_timer)

        # Radar state
        self.active_radar: RadarData | None = None
        self.radar_enabled: bool = False
        self.radar_zone: str = "both"  # "mainboard", "sideboard", or "both"
        self.format_pool_cb: DarkCheckBox | None = None

        # Build the UI
        self._build_ui()
        self.Bind(wx.EVT_SIZE, self._on_panel_resized)

    def _on_panel_resized(self, event: wx.SizeEvent) -> None:
        event.Skip()
        self.refit_scroll()

    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_PANEL)
        self.SetScrollRate(0, BUILDER_SCROLL_RATE_Y)
        stylize_scrollable(self, surface="panel")
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        self._build_header(sizer)
        self._build_basic_filters(sizer)
        self._build_advanced_filters(sizer)
        self._build_action_controls(sizer)
        self._build_results_list(sizer)
        self._build_add_zone_buttons(sizer)
        self._build_status_label(sizer)
        self.refit_scroll()

    def refit_scroll(self) -> None:
        """Re-derive the scrolled virtual size from the current layout.

        ``FitInside`` sets the virtual size to ``max(sizer minimum, client)``,
        which is what makes the scrollbar appear only when the column genuinely
        does not fit and keeps the results list stretching when it does. It has
        to be re-run whenever the column's height changes -- on resize and when
        the advanced filters are shown or hidden.
        """
        self.FitInside()


__all__ = ["DeckBuilderPanel"]
