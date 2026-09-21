"""Center column construction (deck workspace, tables, sideboard guide, notes, stats)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger
from wx.lib.agw import flatnotebook as fnb

from utils.constants import (
    DARK_PANEL,
    DECK_ZONE_MIN_PANE_HEIGHT,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    STATUS_LABEL_MIN_WIDTH,
    SUBDUED_TEXT,
)
from utils.perf import timed
from widgets.notebook import DEFAULT_AGW_STYLE, make_flat_notebook
from widgets.panels.card_table_panel import CardTablePanel
from widgets.panels.deck_baseline_panel import DeckBaselinePanel
from widgets.panels.deck_history_panel import DeckHistoryPanel
from widgets.panels.deck_notes_panel import DeckNotesPanel
from widgets.panels.deck_patterns_panel import DeckPatternsPanel
from widgets.panels.deck_stats_panel import DeckStatsPanel
from widgets.panels.sideboard_guide_panel import SideboardGuidePanel
from widgets.section import SectionPanel
from widgets.splitter import DarkSplitter

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
        # FNB_SMART_TABS on top of the shared default: the Ctrl+Tab overlay earns
        # its keep in the multi-tab deck workspace and nowhere else.
        return make_flat_notebook(parent, agw_style=DEFAULT_AGW_STYLE | fnb.FNB_SMART_TABS)

    @timed
    def _build_deck_workspace(self, parent: wx.Window) -> SectionPanel:
        # G2: the review found three levels of container chrome stacked on one
        # content region -- a StaticBox wrapping a FlatNotebook wrapping a panel
        # that drew its own border. The innermost border went with phase 5's
        # table rebuild; this drops the heading, because the notebook's own tab
        # strip already names every region inside it and "Deck Workspace" above
        # "Deck Tables | Sideboard Guide | Deck Notes | Deck Stats" was a label
        # for a label. What is left is one card: a flat fill, a 1px border, and
        # the tabs.
        section = SectionPanel(parent, title=None, padding=SPACE_SM)
        detail_box = section.body

        self.deck_tabs = self._create_notebook(detail_box)
        section.sizer.Add(self.deck_tabs, 1, wx.EXPAND)
        # A tab that defers work until it is visible needs telling when that
        # happens. Nothing else in the app binds page-changed, so without this
        # the Patterns tab never computes what it deferred and the Baseline tab
        # never enables its button -- both of their ``on_shown`` methods were
        # simply never called.
        self.deck_tabs.Bind(fnb.EVT_FLATNOTEBOOK_PAGE_CHANGED, self._on_deck_tab_changed)

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
        detail_box.SetMinSize((deck_tabs_width + SPACE_MD, -1))

        # Collection status label below the tabs.
        #
        # F8 ellipsised the same defect in three other windows in phase 4 and
        # missed this one. Measured at the deck workspace's own floor: the
        # en-US string wants 389px and the pt-BR one 491px in a 353px panel, so
        # it has been running off the right edge mid-word ("...to fetch from")
        # in both locales at every window width below ~1400. All three
        # ingredients are needed together and none works alone -- the ellipsize
        # style is only read from the **constructor**, ST_NO_AUTORESIZE stops
        # SetLabel resizing the control back to its own text, and wx.EXPAND is
        # what gives it a box narrower than that text to ellipsise into.
        self.collection_status_label = wx.StaticText(
            detail_box,
            label=self._t("app.status.collection_not_loaded"),
            style=wx.ST_ELLIPSIZE_END | wx.ST_NO_AUTORESIZE,
        )
        self.collection_status_label.SetMinSize((STATUS_LABEL_MIN_WIDTH, -1))
        self.collection_status_label.SetForegroundColour(SUBDUED_TEXT)
        self.collection_status_label.SetBackgroundColour(wx.Colour(*DARK_PANEL))
        section.sizer.Add(self.collection_status_label, 0, wx.EXPAND | wx.TOP, SPACE_XS)

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

        # Phase 5: the stats panel is a real tab. It was constructed with
        # create_webview=False and immediately Hide()n, so a whole package
        # rendered nothing and the only surviving artefact was summary_label.
        # DeckStatsPanel picks its own backend (WebView2, else wxHTML), so this
        # site does not have to know whether the runtime is present.
        self.deck_stats_panel = DeckStatsPanel(
            self.deck_tabs,
            controller=self.controller,
            card_manager=self.controller.card_repo.get_card_manager(),
            locale=self.locale,
        )
        self.deck_stats_panel.SetToolTip(self._t("tabs.tooltip.deck_stats"))
        self.deck_tabs.AddPage(self.deck_stats_panel, self._t("tabs.deck_stats"))
        self.stats_summary = self.deck_stats_panel.summary_label

        # The version graph. It reads the deck's history rather than the loaded
        # zones, so it is refreshed when the tab is shown and after any action
        # that moves HEAD -- not on every card edit.
        self.deck_history_panel = DeckHistoryPanel(
            self.deck_tabs,
            deck_repo=self.controller.deck_repo,
            on_checkout=self._on_history_checkout,
            on_status_update=self._set_status,
            locale=self.locale,
        )
        self.deck_history_panel.SetToolTip(self._t("tabs.tooltip.deck_history"))
        self.deck_tabs.AddPage(self.deck_history_panel, self._t("tabs.deck_history"))

        # The capability explorer. It reads the loaded zones, so the frame feeds
        # it on every deck change; the analysis itself runs on the controller's
        # background worker rather than on this thread.
        self.deck_patterns_panel = DeckPatternsPanel(
            self.deck_tabs,
            card_manager=self.controller.card_repo.get_card_manager(),
            worker=getattr(self.controller, "_worker", None),
            locale=self.locale,
        )
        self.deck_patterns_panel.SetToolTip(self._t("tabs.tooltip.deck_patterns"))
        self.deck_tabs.AddPage(self.deck_patterns_panel, self._t("tabs.deck_patterns"))

        # The archetype baseline. It measures the *research* selection, not the
        # loaded deck, so it reads that selection through providers rather than
        # carrying a second pair of format/archetype pickers that could drift
        # out of step with the ones in the research panel.
        self.deck_baseline_panel = DeckBaselinePanel(
            self.deck_tabs,
            worker=getattr(self.controller, "_worker", None),
            archetype_provider=self._selected_research_archetype,
            format_provider=lambda: self.controller.current_format,
            on_status_update=self._set_status,
            locale=self.locale,
        )
        self.deck_baseline_panel.SetToolTip(self._t("tabs.tooltip.deck_baseline"))
        self.deck_tabs.AddPage(self.deck_baseline_panel, self._t("tabs.deck_baseline"))
        return section

    def _on_deck_tab_changed(self, event: wx.CommandEvent) -> None:
        """Tell the newly selected deck tab that it is on screen.

        Best effort and never blocking the tab change: a page that raises while
        waking up must not leave the notebook wedged on the old tab.
        """
        event.Skip()
        page = self.deck_tabs.GetPage(event.GetSelection())
        on_shown = getattr(page, "on_shown", None)
        if on_shown is None:
            return
        try:
            on_shown()
        except Exception as exc:  # noqa: BLE001 - a tab must not die on becoming visible
            logger.warning(f"Deck tab failed to refresh on becoming visible: {exc}")

    def notify_deck_tab_shown(self) -> None:
        """Wake the deck tab that is currently on screen.

        The page-changed event only fires when the *selection* moves, so state
        that changes underneath an already-open tab (picking an archetype in the
        research list while the Baseline tab is showing) needs this instead.
        """
        tabs = getattr(self, "deck_tabs", None)
        if tabs is None:
            return
        selection = tabs.GetSelection()
        if selection == wx.NOT_FOUND:
            return
        on_shown = getattr(tabs.GetPage(selection), "on_shown", None)
        if on_shown is None:
            return
        try:
            on_shown()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Deck tab failed to refresh: {exc}")

    def _selected_research_archetype(self) -> dict | None:
        """The archetype currently selected in the research panel, if any.

        Index 0 is the "Any" row, which is a request for every cached deck
        rather than an archetype -- there is no single archetype to measure
        then, so it reads as no selection.
        """
        panel = getattr(self, "research_panel", None)
        if panel is None:
            return None
        index = panel.get_selected_archetype_index()
        archetypes = getattr(self, "filtered_archetypes", [])
        if index <= 0 or index > len(archetypes):
            return None
        return archetypes[index - 1]

    def _build_deck_tables_tab(self) -> None:
        """Build the mainboard/sideboard zones as a single vertical split page.

        Both zones are shown at once (mainboard on top, sideboard below) in a
        draggable :class:`wx.SplitterWindow` so the user can see both and move
        cards between them, replacing the old one-zone-at-a-time tabs (#781).
        """
        self.zone_notebook = None
        # DarkSplitter, not wx.SplitterWindow: the native sash is a 6px
        # #F0F0F0/#FFFFFF band the full width of the workspace, and no colour
        # call reaches it. Same style flags, so the saved sash position and the
        # 7px metrics are unchanged.
        self.deck_split = DarkSplitter(self.deck_tabs)
        self.deck_split.SetMinimumPaneSize(DECK_ZONE_MIN_PANE_HEIGHT)
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
            # Double-click a card in this zone (issue #1027): one copy out in
            # normal editing, one copy across zones while recording a guide.
            on_activate=self._handle_zone_activate,
            # The printing-selection dropdown re-pricks art for the whole
            # decklist, so it only belongs on the mainboard header (issue #792).
            on_printing_mode=(self._handle_printing_mode if zone == "main" else None),
            # All zones resolve a card's chosen printing image the same way so
            # board art tracks the inspector selection (issue #792, part 1).
            get_printing_image=self._get_printing_image,
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
