"""Shared ``self`` contract that the :class:`AppFrame` mixins assume."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import wx
import wx.lib.agw.flatnotebook as fnb

from utils.mana_icon_factory import ManaIconFactory
from widgets.buttons.toolbar_buttons import ToolbarButtons
from widgets.panels.card_inspector_panel import CardInspectorPanel
from widgets.panels.card_panel import CardPanel
from widgets.panels.card_table_panel import CardTablePanel
from widgets.panels.deck_notes_panel import DeckNotesPanel
from widgets.panels.deck_stats_panel import DeckStatsPanel
from widgets.panels.sideboard_guide_panel import SideboardGuidePanel

if TYPE_CHECKING:
    from controllers.app_controller import AppController
    from widgets.frames.mana_keyboard import ManaKeyboardFrame


class AppFrameProto(Protocol):
    """Cross-mixin ``self`` surface for ``AppFrame``."""

    # Root/control state
    controller: AppController
    card_data_dialogs_disabled: bool
    locale: str | None
    status_bar: wx.StatusBar | None
    root_panel: wx.Panel | None
    mana_icons: ManaIconFactory

    # Persistent / session-mirrored state delegated to controller
    zone_cards: dict[str, list[Any]]
    filtered_archetypes: list[dict[str, Any]]
    left_mode: str

    # Sideboard guide aggregates
    sideboard_guide_entries: list[dict[str, str]]
    sideboard_exclusions: list[str]
    sideboard_flex_slots: list[str]
    active_inspector_zone: str | None

    # Top-level UI containers and toggles
    left_stack: wx.Simplebook | None
    research_panel: Any
    builder_panel: Any
    out_table: CardTablePanel | None
    toolbar: ToolbarButtons
    zone_notebook: fnb.FlatNotebook | None
    deck_source_choice: wx.Choice | None
    language_choice: wx.Choice | None
    _deck_source_values: list[str]
    _language_values: list[str]

    # Deck/zone widgets created by the builder mixins
    deck_tabs: fnb.FlatNotebook
    main_table: CardTablePanel
    side_table: CardTablePanel
    card_inspector_panel: CardInspectorPanel
    deck_stats_panel: DeckStatsPanel
    deck_notes_panel: DeckNotesPanel
    sideboard_guide_panel: SideboardGuidePanel
    card_panel: CardPanel
    collection_status_label: wx.StaticText
    stats_summary: wx.StaticText

    # Image / printing-index plumbing surfaced for sub-panels
    image_cache: Any
    image_downloader: Any

    # Buttons accessed via delegation properties
    copy_button: wx.Button
    save_button: wx.Button
    daily_average_button: wx.Button

    # Timers and pending state
    _save_timer: wx.Timer | None
    _filter_debounce_timer: wx.Timer | None
    _inspector_hover_timer: wx.Timer | None
    _pending_hover: tuple[str, dict[str, Any]] | None
    _pending_deck_restore: bool
    _is_first_deck_load: bool
    _all_loaded_decks: list[dict[str, Any]]
    _builder_search_pending: bool
    _search_seq: int

    # Auxiliary windows
    mana_keyboard_window: ManaKeyboardFrame | None

    # Cross-mixin methods
    def _t(self, key: str, **kwargs: object) -> str: ...
    def _set_status(self, key: str, **kwargs: object) -> None: ...
    def _has_deck_loaded(self) -> bool: ...
