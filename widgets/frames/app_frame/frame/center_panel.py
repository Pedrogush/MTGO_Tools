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
