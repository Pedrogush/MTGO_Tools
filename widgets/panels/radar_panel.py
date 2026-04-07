"""
Radar Panel - Displays archetype card frequency analysis.

Shows mainboard and sideboard card frequencies with inclusion rates and expected copies.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx
import wx.dataview as dv
from loguru import logger

from services.radar_service import CardFrequency, RadarData, RadarService, get_radar_service
from utils.atomic_io import atomic_write_text
from utils.background_worker import BackgroundWorker
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


class RadarDialog(wx.Dialog):
    """Dialog for generating and viewing archetype radars."""

    def __init__(
        self,
        parent: wx.Window,
        metagame_repo,
        format_name: str,
        radar_service: RadarService | None = None,
        locale: str | None = None,
    ):
        super().__init__(
            parent,
            title=f"Archetype Radar - {format_name}",
            size=(900, 700),
        )
        self.SetBackgroundColour(DARK_PANEL)
        self._locale = locale

        self.metagame_repo = metagame_repo
        self.format_name = format_name
        self.radar_service = radar_service or get_radar_service()
        self.archetypes: list[dict[str, Any]] = []
        self.current_radar: RadarData | None = None
        self.worker_thread: threading.Thread | None = None
        self._worker = BackgroundWorker(thread_name_prefix="radar-dialog")
        self.cancel_requested = False

        self.Bind(wx.EVT_CLOSE, self._on_close)
        self._build_ui()
        self._load_archetypes()

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Archetype selection
        selection_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(selection_sizer, 0, wx.EXPAND | wx.ALL, 10)

        label = wx.StaticText(self, label=self._t("radar.dialog.select_archetype"))
        label.SetForegroundColour(LIGHT_TEXT)
        selection_sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        self.archetype_choice = wx.Choice(self)
        self.archetype_choice.SetBackgroundColour(DARK_ALT)
        self.archetype_choice.SetForegroundColour(LIGHT_TEXT)
        selection_sizer.Add(self.archetype_choice, 1, wx.RIGHT, 6)

        self.generate_btn = wx.Button(self, label=self._t("radar.dialog.generate"))
        self.generate_btn.Bind(wx.EVT_BUTTON, self._on_generate_clicked)
        selection_sizer.Add(self.generate_btn, 0, wx.RIGHT, 6)

        self.cancel_btn = wx.Button(self, label=self._t("radar.btn.cancel"))
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel_clicked)
        self.cancel_btn.Enable(False)
        selection_sizer.Add(self.cancel_btn, 0)

        # Progress gauge
        self.progress = wx.Gauge(self, range=100)
        sizer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.progress_label = wx.StaticText(self, label="")
        self.progress_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.progress_label, 0, wx.ALL, 10)

        # Radar panel
        self.radar_panel = RadarPanel(
            self,
            radar_service=self.radar_service,
            on_export=self._export_radar,
            on_use_for_search=self._use_radar_for_search,
            locale=self._locale,
        )
        sizer.Add(self.radar_panel, 1, wx.EXPAND | wx.ALL, 10)

        # Close button
        close_btn = wx.Button(self, wx.ID_CLOSE, self._t("radar.btn.close"))
        close_btn.Bind(wx.EVT_BUTTON, self._on_close)
        sizer.Add(close_btn, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

    def _load_archetypes(self) -> None:
        try:
            self.archetypes = self.metagame_repo.get_archetypes_for_format(self.format_name)
            archetype_names = [arch.get("name", "Unknown") for arch in self.archetypes]
            self.archetype_choice.Set(archetype_names)

            if archetype_names:
                self.archetype_choice.SetSelection(0)

        except Exception as exc:
            logger.exception(f"Failed to load archetypes: {exc}")

    def _on_generate_clicked(self, event: wx.Event) -> None:
        selection = self.archetype_choice.GetSelection()
        if selection == wx.NOT_FOUND:
            logger.error("No archetype selected for radar generation")
            return

        archetype = self.archetypes[selection]

        # Update UI state
        self.generate_btn.Enable(False)
        self.cancel_btn.Enable(True)
        self.archetype_choice.Enable(False)
        self.progress.SetValue(0)
        self.progress_label.SetLabel("Starting radar generation...")
        self.cancel_requested = False

        # Start worker thread
        self.worker_thread = self._worker.submit(
            self._generate_radar_worker,
            archetype,
            name="radar-dialog-generate",
        )

    def _on_cancel_clicked(self, event: wx.Event) -> None:
        self.cancel_requested = True
        self._worker.call_after(self.progress_label.SetLabel, "Cancelling...")
        self._worker.call_after(self.cancel_btn.Enable, False)

    def _generate_radar_worker(self, archetype: dict[str, Any]) -> None:
        try:
            # Progress callback - safely updates UI from worker thread
            def update_progress(current: int, total: int, deck_name: str) -> None:
                if self.cancel_requested:
                    raise InterruptedError("Radar generation cancelled by user")

                percent = int((current / total) * 100) if total > 0 else 0
                self._worker.call_after(self.progress.SetValue, percent)
                self._worker.call_after(
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
                self._worker.call_after(self._display_generated_radar, radar)
                self._worker.call_after(
                    self.progress_label.SetLabel,
                    "Radar generated successfully!",
                )

        except InterruptedError as exc:
            # User cancelled
            self._worker.call_after(self.progress_label.SetLabel, f"Cancelled: {exc}")
            self._worker.call_after(self.progress.SetValue, 0)

        except Exception as exc:
            # Error occurred
            logger.exception(f"Failed to generate radar: {exc}")
            self._worker.call_after(self.progress_label.SetLabel, "Failed to generate radar.")
            self._worker.call_after(self.progress.SetValue, 0)

        finally:
            # Re-enable UI controls
            self._worker.call_after(self.generate_btn.Enable, True)
            self._worker.call_after(self.cancel_btn.Enable, False)
            self._worker.call_after(self.archetype_choice.Enable, True)
            if not self.cancel_requested:
                self._worker.call_after(self.progress.SetValue, 0)
            self.worker_thread = None

    def _display_generated_radar(self, radar: RadarData) -> None:
        self.current_radar = radar
        self.radar_panel.display_radar(radar)

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
        if self.IsModal():
            self.EndModal(wx.ID_OK)
        else:
            self.Close()

    def get_current_radar(self) -> RadarData | None:
        return self.current_radar

    def _on_close(self, event: wx.Event) -> None:
        is_close_event = isinstance(event, wx.CloseEvent)
        # If worker is running, request cancellation
        if self.worker_thread and self.worker_thread.is_alive():
            response = wx.MessageBox(
                "Radar generation is in progress. Are you sure you want to close?",
                "Close Dialog",
                wx.YES_NO | wx.ICON_QUESTION,
            )
            if response == wx.NO:
                return

            # Cancel the worker
            self.cancel_requested = True
            self._worker.shutdown(timeout=2.0)
            self.worker_thread = None
        else:
            self._worker.shutdown(timeout=0.2)

        if self.IsModal():
            self.EndModal(wx.ID_OK)
        elif is_close_event:
            event.Skip()
        else:
            self.Close()
