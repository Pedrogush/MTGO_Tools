"""
Radar widget - Archetype card frequency analysis window.

Contains both the inner RadarPanel (used here and in CompactRadarPanel callers)
and RadarFrame, the standalone window the user opens via the toolbar or by
selecting an archetype in the research panel.
"""

# ruff: noqa: E402

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import wx
import wx.dataview as dv
from loguru import logger

from services.radar_service import CardFrequency, RadarData, RadarService, get_radar_service
from utils.atomic_io import atomic_write_text
from utils.constants import DARK_ALT, DARK_PANEL, LIGHT_TEXT
from utils.i18n import translate


class RadarPanel(wx.Panel):
    """Panel that displays archetype radar (card frequency analysis)."""

    def __init__(
        self,
        parent: wx.Window,
        radar_service: RadarService | None = None,
        on_export: Callable[[RadarData], None] | None = None,
        on_use_for_search: Callable[[RadarData], None] | None = None,
        locale: str | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)
        self._locale = locale

        self.radar_service = radar_service or get_radar_service()
        self.on_export = on_export
        self.on_use_for_search = on_use_for_search
        self.current_radar: RadarData | None = None

        self._build_ui()

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Header with archetype info and controls
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 6)

        # Archetype name label
        self.archetype_label = wx.StaticText(self, label=self._t("radar.label.no_radar"))
        self.archetype_label.SetForegroundColour(LIGHT_TEXT)
        font = self.archetype_label.GetFont()
        font.PointSize += 2
        font = font.Bold()
        self.archetype_label.SetFont(font)
        header_sizer.Add(self.archetype_label, 1, wx.ALIGN_CENTER_VERTICAL)

        # Export button
        self.export_btn = wx.Button(self, label=self._t("radar.btn.export"))
        self.export_btn.Enable(False)
        self.export_btn.Bind(wx.EVT_BUTTON, self._on_export_clicked)
        header_sizer.Add(self.export_btn, 0, wx.LEFT, 6)

        # Use for search button
        self.use_search_btn = wx.Button(self, label=self._t("radar.btn.use_search"))
        self.use_search_btn.Enable(False)
        self.use_search_btn.Bind(wx.EVT_BUTTON, self._on_use_search_clicked)
        header_sizer.Add(self.use_search_btn, 0, wx.LEFT, 6)

        # Summary statistics
        self.summary_label = wx.StaticText(self, label="")
        self.summary_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.summary_label, 0, wx.ALL, 6)

        # Split view for mainboard and sideboard
        split_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(split_sizer, 1, wx.EXPAND | wx.ALL, 6)

        # Mainboard section
        mainboard_box = wx.StaticBox(self, label=self._t("radar.box.mainboard"))
        mainboard_box.SetForegroundColour(LIGHT_TEXT)
        mainboard_box_sizer = wx.StaticBoxSizer(mainboard_box, wx.VERTICAL)
        split_sizer.Add(mainboard_box_sizer, 1, wx.EXPAND | wx.RIGHT, 6)

        self.mainboard_list = dv.DataViewListCtrl(self)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.card"), width=200)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.inclusion"), width=90)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.expected"), width=120)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.avg"), width=90)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.max"), width=60)
        self.mainboard_list.SetBackgroundColour(DARK_ALT)
        self.mainboard_list.SetForegroundColour(LIGHT_TEXT)
        self._bind_tooltip_handlers(self.mainboard_list)
        mainboard_box_sizer.Add(self.mainboard_list, 1, wx.EXPAND | wx.ALL, 6)

        # Sideboard section
        sideboard_box = wx.StaticBox(self, label=self._t("radar.box.sideboard"))
        sideboard_box.SetForegroundColour(LIGHT_TEXT)
        sideboard_box_sizer = wx.StaticBoxSizer(sideboard_box, wx.VERTICAL)
        split_sizer.Add(sideboard_box_sizer, 1, wx.EXPAND)

        self.sideboard_list = dv.DataViewListCtrl(self)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.card"), width=200)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.inclusion"), width=90)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.expected"), width=120)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.avg"), width=90)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.max"), width=60)
        self.sideboard_list.SetBackgroundColour(DARK_ALT)
        self.sideboard_list.SetForegroundColour(LIGHT_TEXT)
        self._bind_tooltip_handlers(self.sideboard_list)
        sideboard_box_sizer.Add(self.sideboard_list, 1, wx.EXPAND | wx.ALL, 6)

    # ============= Public API =============

    def display_radar(self, radar: RadarData) -> None:
        self.current_radar = radar

        # Update header
        self.archetype_label.SetLabel(f"{radar.archetype_name} - {radar.format_name} Radar")

        # Update summary
        summary = (
            f"Analyzed {radar.total_decks_analyzed} decks  |  "
            f"{len(radar.mainboard_cards)} unique mainboard cards  |  "
            f"{len(radar.sideboard_cards)} unique sideboard cards"
        )
        if radar.decks_failed > 0:
            summary += f"  |  {radar.decks_failed} decks failed"
        self.summary_label.SetLabel(summary)

        # Enable buttons
        self.export_btn.Enable(True)
        self.use_search_btn.Enable(True)

        # Populate lists
        self._populate_card_list(self.mainboard_list, radar.mainboard_cards)
        self._populate_card_list(self.sideboard_list, radar.sideboard_cards)

    def clear(self) -> None:
        self.current_radar = None
        self.archetype_label.SetLabel(self._t("radar.label.no_radar"))
        self.summary_label.SetLabel("")
        self.mainboard_list.DeleteAllItems()
        self.sideboard_list.DeleteAllItems()
        self.export_btn.Enable(False)
        self.use_search_btn.Enable(False)

    # ============= Private Methods =============

    def _populate_card_list(
        self, list_ctrl: dv.DataViewListCtrl, cards: list[CardFrequency]
    ) -> None:
        list_ctrl.DeleteAllItems()

        for card in cards:
            list_ctrl.AppendItem(
                [
                    card.card_name,
                    f"{card.inclusion_rate:.1f}%",
                    f"{card.expected_copies:.2f}",
                    f"{card.avg_copies:.2f}",
                    str(card.max_copies),
                ]
            )

    def _bind_tooltip_handlers(self, list_ctrl: dv.DataViewListCtrl) -> None:
        list_ctrl.Bind(wx.EVT_MOTION, lambda event: self._on_list_mouse_move(list_ctrl, event))
        list_ctrl.Bind(wx.EVT_LEAVE_WINDOW, lambda event: self._clear_tooltip(list_ctrl, event))

    def _on_list_mouse_move(self, list_ctrl: dv.DataViewListCtrl, event: wx.MouseEvent) -> None:
        if not self.current_radar:
            self._clear_tooltip(list_ctrl, event)
            return

        hit = list_ctrl.HitTest(event.GetPosition())
        if not hit or len(hit) < 2:
            self._clear_tooltip(list_ctrl, event)
            return

        item = hit[0]
        if not item or not item.IsOk():
            self._clear_tooltip(list_ctrl, event)
            return

        row = list_ctrl.ItemToRow(item)
        if row == wx.NOT_FOUND:
            self._clear_tooltip(list_ctrl, event)
            return

        cards = (
            self.current_radar.mainboard_cards
            if list_ctrl is self.mainboard_list
            else self.current_radar.sideboard_cards
        )
        if row >= len(cards):
            self._clear_tooltip(list_ctrl, event)
            return

        tooltip_text = self._format_distribution_tooltip(
            cards[row],
            self.current_radar.total_decks_analyzed,
        )
        current_tip = list_ctrl.GetToolTipText() if list_ctrl.GetToolTip() else ""
        if tooltip_text and tooltip_text != current_tip:
            list_ctrl.SetToolTip(tooltip_text)
        elif not tooltip_text and current_tip:
            list_ctrl.SetToolTip("")

        event.Skip()

    def _clear_tooltip(self, list_ctrl: dv.DataViewListCtrl, event: wx.Event | None = None) -> None:
        if list_ctrl.GetToolTip():
            list_ctrl.SetToolTip("")
        if event:
            event.Skip()

    def _format_distribution_tooltip(self, card: CardFrequency, total_decks: int) -> str:
        if total_decks <= 0:
            return ""

        lines = [f"{total_decks} decks analyzed"]
        for copies, deck_count in card.copy_distribution.items():
            copy_label = "copy" if copies == 1 else "copies"
            lines.append(f"{deck_count} decks use {copies} {copy_label}")

        return "\n".join(lines)

    def _on_export_clicked(self, event: wx.Event) -> None:
        if self.current_radar and self.on_export:
            self.on_export(self.current_radar)

    def _on_use_search_clicked(self, event: wx.Event) -> None:
        if self.current_radar and self.on_use_for_search:
            self.on_use_for_search(self.current_radar)


class RadarFrame(wx.Frame):
    """Standalone window for generating and viewing archetype radars."""

    def __init__(
        self,
        parent: wx.Window | None = None,
        metagame_repo: Any = None,
        format_name: str = "",
        radar_service: RadarService | None = None,
        on_use_for_search: Callable[[RadarData], None] | None = None,
        locale: str | None = None,
    ):
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(
            parent,
            title=translate(locale, "window.title.radar", format=format_name),
            size=(900, 700),
            style=style,
        )
        self.SetBackgroundColour(DARK_PANEL)
        self._locale = locale

        self.metagame_repo = metagame_repo
        self.format_name = format_name
        self.radar_service = radar_service or get_radar_service()
        self._on_use_for_search_cb = on_use_for_search
        self.archetypes: list[dict[str, Any]] = []
        self.current_radar: RadarData | None = None
        self.worker_thread: threading.Thread | None = None
        self.cancel_requested = False

        self._build_ui()
        self._load_archetypes()
        self.Centre(wx.BOTH)

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Archetype selection
        selection_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(selection_sizer, 0, wx.EXPAND | wx.ALL, 10)

        label = wx.StaticText(panel, label=self._t("radar.dialog.select_archetype"))
        label.SetForegroundColour(LIGHT_TEXT)
        selection_sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        self.archetype_choice = wx.Choice(panel)
        self.archetype_choice.SetBackgroundColour(DARK_ALT)
        self.archetype_choice.SetForegroundColour(LIGHT_TEXT)
        selection_sizer.Add(self.archetype_choice, 1, wx.RIGHT, 6)

        self.generate_btn = wx.Button(panel, label=self._t("radar.dialog.generate"))
        self.generate_btn.Bind(wx.EVT_BUTTON, self._on_generate_clicked)
        selection_sizer.Add(self.generate_btn, 0, wx.RIGHT, 6)

        self.cancel_btn = wx.Button(panel, label=self._t("radar.btn.cancel"))
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel_clicked)
        self.cancel_btn.Enable(False)
        selection_sizer.Add(self.cancel_btn, 0)

        # Progress gauge
        self.progress = wx.Gauge(panel, range=100)
        sizer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.progress_label = wx.StaticText(panel, label="")
        self.progress_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.progress_label, 0, wx.ALL, 10)

        # Radar panel
        self.radar_panel = RadarPanel(
            panel,
            radar_service=self.radar_service,
            on_export=self._export_radar,
            on_use_for_search=self._use_radar_for_search,
            locale=self._locale,
        )
        sizer.Add(self.radar_panel, 1, wx.EXPAND | wx.ALL, 10)

        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _load_archetypes(self) -> None:
        try:
            self.archetypes = self.metagame_repo.get_archetypes_for_format(self.format_name)
            archetype_names = [arch.get("name", "Unknown") for arch in self.archetypes]
            self.archetype_choice.Set(archetype_names)

            if archetype_names:
                self.archetype_choice.SetSelection(0)

        except Exception as exc:
            logger.exception(f"Failed to load archetypes: {exc}")

    # ============= Public API =============

    def generate_for_archetype(self, archetype_name: str) -> bool:
        """Select the named archetype in the choice widget and start generation.

        Returns True if the archetype was found and generation was started.
        """
        for idx, arch in enumerate(self.archetypes):
            if arch.get("name") == archetype_name:
                self.archetype_choice.SetSelection(idx)
                self._start_generation(arch)
                return True
        logger.debug(f"Archetype '{archetype_name}' not found for radar generation")
        return False

    # ============= Private Methods =============

    def _on_generate_clicked(self, event: wx.Event) -> None:
        selection = self.archetype_choice.GetSelection()
        if selection == wx.NOT_FOUND:
            logger.error("No archetype selected for radar generation")
            return

        self._start_generation(self.archetypes[selection])

    def _start_generation(self, archetype: dict[str, Any]) -> None:
        # Update UI state
        self.generate_btn.Enable(False)
        self.cancel_btn.Enable(True)
        self.archetype_choice.Enable(False)
        self.progress.SetValue(0)
        self.progress_label.SetLabel("Starting radar generation...")
        self.cancel_requested = False

        # Start worker thread
        self.worker_thread = threading.Thread(
            target=self._generate_radar_worker,
            args=(archetype,),
            daemon=True,
        )
        self.worker_thread.start()

    def _on_cancel_clicked(self, event: wx.Event) -> None:
        self.cancel_requested = True
        wx.CallAfter(self.progress_label.SetLabel, "Cancelling...")
        wx.CallAfter(self.cancel_btn.Enable, False)

    def _generate_radar_worker(self, archetype: dict[str, Any]) -> None:
        try:
            # Progress callback - safely updates UI from worker thread
            def update_progress(current: int, total: int, deck_name: str) -> None:
                if self.cancel_requested:
                    raise InterruptedError("Radar generation cancelled by user")

                percent = int((current / total) * 100) if total > 0 else 0
                wx.CallAfter(self.progress.SetValue, percent)
                wx.CallAfter(
                    self.progress_label.SetLabel,
                    f"Analyzing deck {current}/{total}: {deck_name}",
                )

            # Calculate radar (this is the I/O heavy operation)
            radar = self.radar_service.calculate_radar(
                archetype,
                self.format_name,
                progress_callback=update_progress,
            )

            # Display results on UI thread
            if not self.cancel_requested:
                wx.CallAfter(self.radar_panel.display_radar, radar)
                wx.CallAfter(self.progress_label.SetLabel, "Radar generated successfully!")
                self.current_radar = radar

        except InterruptedError as exc:
            # User cancelled
            wx.CallAfter(self.progress_label.SetLabel, f"Cancelled: {exc}")
            wx.CallAfter(self.progress.SetValue, 0)

        except Exception as exc:
            # Error occurred
            logger.exception(f"Failed to generate radar: {exc}")
            wx.CallAfter(self.progress_label.SetLabel, "Failed to generate radar.")
            wx.CallAfter(self.progress.SetValue, 0)

        finally:
            # Re-enable UI controls
            wx.CallAfter(self.generate_btn.Enable, True)
            wx.CallAfter(self.cancel_btn.Enable, False)
            wx.CallAfter(self.archetype_choice.Enable, True)
            if not self.cancel_requested:
                wx.CallAfter(self.progress.SetValue, 0)
            self.worker_thread = None

    def _export_radar(self, radar: RadarData) -> None:
        # Ask for minimum expected copies threshold
        dlg = wx.TextEntryDialog(
            self,
            "Enter minimum expected copies (0-4):\n"
            "Expected copies represent the average copies per deck in the sample.",
            "Export Radar as Decklist",
            "0",
        )

        if dlg.ShowModal() == wx.ID_OK:
            try:
                min_expected = float(dlg.GetValue())
                if min_expected < 0 or min_expected > 4:
                    raise ValueError("Must be between 0 and 4")

                # Generate deck list
                decklist = self.radar_service.export_radar_as_decklist(
                    radar, min_expected_copies=min_expected
                )

                # Save to file
                with wx.FileDialog(
                    self,
                    "Save Radar Decklist",
                    wildcard="Text files (*.txt)|*.txt",
                    style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                ) as fileDialog:
                    if fileDialog.ShowModal() == wx.ID_OK:
                        path = fileDialog.GetPath()
                        atomic_write_text(Path(path), decklist)
                        logger.info(f"Radar exported to {path}")

            except ValueError as exc:
                logger.exception(f"Invalid expected copies value: {exc}")

        dlg.Destroy()

    def _use_radar_for_search(self, radar: RadarData) -> None:
        logger.info("Radar used as search filter")
        if self._on_use_for_search_cb:
            self._on_use_for_search_cb(radar)

    def get_current_radar(self) -> RadarData | None:
        return self.current_radar

    def _on_close(self, event: wx.CloseEvent) -> None:
        # If worker is running, request cancellation
        if self.worker_thread and self.worker_thread.is_alive():
            response = wx.MessageBox(
                "Radar generation is in progress. Are you sure you want to close?",
                "Close Radar",
                wx.YES_NO | wx.ICON_QUESTION,
            )
            if response == wx.NO:
                event.Veto()
                return

            # Cancel the worker and give it a moment to clean up
            self.cancel_requested = True
            if self.worker_thread:
                self.worker_thread.join(timeout=2.0)

        event.Skip()
