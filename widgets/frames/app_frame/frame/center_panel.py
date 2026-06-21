"""Center column construction (deck workspace, tables, sideboard guide, notes, stats)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from wx.lib.agw import flatnotebook as fnb

from utils.constants import (
    DARK_ACCENT,
    DARK_BG,
    DARK_PANEL,
    LIGHT_TEXT,
    PADDING_MD,
    PADDING_SM,
    SUBDUED_TEXT,
)
from utils.perf import timed
from widgets.panels.card_table_panel import CardTablePanel
from widgets.panels.deck_notes_panel import DeckNotesPanel
from widgets.panels.deck_stats_panel import DeckStatsPanel
from widgets.panels.sideboard_guide_panel import SideboardGuidePanel

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class CenterPanelBuilderMixin(_Base):
    """Builds the center column: deck tables notebook, sideboard guide, notes, stats.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

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

    @timed
    def _build_deck_workspace(self, parent: wx.Window) -> wx.StaticBoxSizer:
        detail_box = wx.StaticBox(parent, label=self._t("app.label.deck_workspace"))
        detail_box.SetForegroundColour(LIGHT_TEXT)
        detail_box.SetBackgroundColour(DARK_PANEL)
        detail_sizer = wx.StaticBoxSizer(detail_box, wx.VERTICAL)

        self.deck_tabs = self._create_notebook(detail_box)
        detail_sizer.Add(self.deck_tabs, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Mainboard and Sideboard as top-level tabs
        self._build_deck_tables_tab()
        # The workspace keeps a *minimum* width that fits GRID_COLUMNS cards
        # across, but is no longer locked to it (issue #785): all leftover
        # horizontal space is given to the workspace (see `_build_right_container`
        # where it is added with a stretch proportion), and each card view fits
        # as many cards per row as the allotted width allows — the grid view
        # recomputes its column count on resize.
        deck_tabs_width = CardTablePanel.grid_width()
        self.deck_tabs.SetMinSize((deck_tabs_width, -1))
        detail_box.SetMinSize((deck_tabs_width + (PADDING_MD * 2), -1))

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
            on_record_guide=self._on_record_guide,
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

        # Stats panel kept hidden; avoid starting WebView2 just to maintain
        # the compatibility summary label.
        self.deck_stats_panel = DeckStatsPanel(
            detail_box,
            controller=self.controller,
            card_manager=self.controller.card_repo.get_card_manager(),
            create_webview=False,
        )
        self.deck_stats_panel.Hide()
        self.stats_summary = self.deck_stats_panel.summary_label
        return detail_sizer

    def _build_deck_tables_tab(self) -> None:
        """Build the mainboard/sideboard zones as a single vertical split page.

        Both zones are shown at once (mainboard on top, sideboard below) in a
        draggable :class:`wx.SplitterWindow` so the user can see both and move
        cards between them, replacing the old one-zone-at-a-time tabs (#781).
        """
        self.zone_notebook = None
        self.deck_split = wx.SplitterWindow(
            self.deck_tabs, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH | wx.SP_NO_XP_THEME
        )
        self.deck_split.SetBackgroundColour(DARK_PANEL)
        self.deck_split.SetMinimumPaneSize(80)
        # Mainboard absorbs more of any extra height on resize.
        self.deck_split.SetSashGravity(0.6)

        self.main_table = self._create_zone_table(self.deck_split, "main")
        self.main_table.SetToolTip(self._t("tabs.tooltip.mainboard"))
        self.side_table = self._create_zone_table(self.deck_split, "side")
        self.side_table.SetToolTip(self._t("tabs.tooltip.sideboard"))
        self.out_table = None

        saved_sash = self.controller.session_manager.get_deck_sash_position()
        self._deck_sash_initialized = saved_sash > 0
        self.deck_split.SplitHorizontally(self.main_table, self.side_table, saved_sash)
        self.deck_split.Bind(wx.EVT_SPLITTER_SASH_POS_CHANGED, self._on_deck_sash_changed)
        # The real height isn't known at construction; place the default sash
        # (mainboard ~60%) once the splitter is first sized, unless restored.
        self.deck_split.Bind(wx.EVT_SIZE, self._on_deck_split_size)

        self.deck_tabs.AddPage(self.deck_split, self._t("tabs.deck_tables"))

    def _on_deck_split_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        if self._deck_sash_initialized:
            return
        height = self.deck_split.GetClientSize().GetHeight()
        if height > 160:
            self.deck_split.SetSashPosition(int(height * 0.6))
            self._deck_sash_initialized = True

    def _on_deck_sash_changed(self, event: wx.SplitterEvent) -> None:
        self._deck_sash_initialized = True
        self.controller.session_manager.update_deck_sash_position(self.deck_split.GetSashPosition())
        self._schedule_settings_save()
        event.Skip()

    def _create_zone_table(
        self, parent: wx.Window, zone: str, owned_status_func=None
    ) -> CardTablePanel:
        if owned_status_func is None:
            owned_status_func = self.controller.collection_service.get_owned_status

        session = self.controller.session_manager
        return CardTablePanel(
            parent,
            zone,
            self.mana_icons,
            self.controller.card_repo.get_card_metadata,
            owned_status_func,
            self._handle_zone_delta,
            self._handle_zone_remove,
            self._handle_zone_add,
            self._handle_card_focus,
            self.controller.get_card_image,
            self._handle_card_hover,
            locale=self.locale,
            initial_view_mode=session.get_deck_view_mode(zone),
            initial_pile_sort=session.get_pile_sort_mode(zone),
            on_view_mode_change=self._persist_deck_view_mode,
            on_pile_sort_change=self._persist_pile_sort_mode,
            on_zone_transfer=self._handle_zone_transfer,
            # The printing-selection dropdown re-pricks art for the whole
            # decklist, so it only belongs on the mainboard header (issue #792).
            on_printing_mode=(self._handle_printing_mode if zone == "main" else None),
        )

    def _persist_deck_view_mode(self, zone: str, mode: str) -> None:
        self.controller.session_manager.update_deck_view_mode(zone, mode)
        self._schedule_settings_save()

    def _persist_pile_sort_mode(self, zone: str, sort_mode: str) -> None:
        self.controller.session_manager.update_pile_sort_mode(zone, sort_mode)
        self._schedule_settings_save()

    def _handle_printing_mode(self, mode: str, when: str | None = None) -> None:
        """Re-pick every card's printing for the loaded deck (issue #792, part 3).

        Applies the chosen mode to the current deck text via the printing index
        and re-renders. The ``"reprint"`` source is intentionally outside the
        set that resets the current-deck identity, so the loaded deck stays
        selected. If the printing index has not loaded yet there is nothing we
        can resolve against, so we just tell the user to retry.
        """
        index = getattr(self.controller.image_service, "bulk_data_by_name", None)
        if not index:
            from utils.i18n import translate

            wx.MessageBox(
                translate(self.locale, "tabs.view.printing.no_index"),
                translate(self.locale, "tabs.view.printing"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        deck_text = self.controller.deck_repo.get_current_deck_text()
        if not deck_text or not deck_text.strip():
            return
        new_text = self.controller.deck_service.apply_printing_mode(deck_text, index, mode, when)
        self._on_deck_content_ready(new_text, source="reprint")
