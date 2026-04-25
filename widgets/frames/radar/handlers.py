"""Event and worker callbacks for the radar widget."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx
import wx.dataview as dv
from loguru import logger

from services.radar_service import CardFrequency, RadarData, RadarService
from utils.atomic_io import atomic_write_text


class RadarPanelHandlersMixin:
    """Callbacks, tooltip tracking, and list mutation for :class:`RadarPanel`."""

    radar_service: RadarService
    on_export: Callable[[RadarData], None] | None
    on_use_for_search: Callable[[RadarData], None] | None
    current_radar: RadarData | None
    archetype_label: wx.StaticText
    summary_label: wx.StaticText
    export_btn: wx.Button
    use_search_btn: wx.Button
    mainboard_list: dv.DataViewListCtrl
    sideboard_list: dv.DataViewListCtrl

    def display_radar(self, radar: RadarData) -> None:
        self.current_radar = radar

        self.archetype_label.SetLabel(f"{radar.archetype_name} - {radar.format_name} Radar")

        summary = (
            f"Analyzed {radar.total_decks_analyzed} decks  |  "
            f"{len(radar.mainboard_cards)} unique mainboard cards  |  "
            f"{len(radar.sideboard_cards)} unique sideboard cards"
        )
        if radar.decks_failed > 0:
            summary += f"  |  {radar.decks_failed} decks failed"
        self.summary_label.SetLabel(summary)

        self.export_btn.Enable(True)
        self.use_search_btn.Enable(True)

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

    def _on_export_clicked(self, event: wx.Event) -> None:
        if self.current_radar and self.on_export:
            self.on_export(self.current_radar)

    def _on_use_search_clicked(self, event: wx.Event) -> None:
        if self.current_radar and self.on_use_for_search:
            self.on_use_for_search(self.current_radar)


class RadarFrameHandlersMixin:
    """Archetype loading, generation worker, export, and close for :class:`RadarFrame`."""

    metagame_repo: Any
    format_name: str
    radar_service: RadarService
    archetypes: list[dict[str, Any]]
    current_radar: RadarData | None
    worker_thread: threading.Thread | None
    cancel_requested: bool
    _on_use_for_search_cb: Callable[[RadarData], None] | None
    archetype_choice: wx.Choice
    generate_btn: wx.Button
    cancel_btn: wx.Button
    progress: wx.Gauge
    progress_label: wx.StaticText
    radar_panel: Any

    def _load_archetypes(self) -> None:
        try:
            self.archetypes = self.metagame_repo.get_archetypes_for_format(self.format_name)
            archetype_names = [arch.get("name", "Unknown") for arch in self.archetypes]
            self.archetype_choice.Set(archetype_names)

            if archetype_names:
                self.archetype_choice.SetSelection(0)

        except Exception as exc:
            logger.exception(f"Failed to load archetypes: {exc}")

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

    def _on_generate_clicked(self, event: wx.Event) -> None:
        selection = self.archetype_choice.GetSelection()
        if selection == wx.NOT_FOUND:
            logger.error("No archetype selected for radar generation")
            return

        self._start_generation(self.archetypes[selection])

    def _start_generation(self, archetype: dict[str, Any]) -> None:
        self.generate_btn.Enable(False)
        self.cancel_btn.Enable(True)
        self.archetype_choice.Enable(False)
        self.progress.SetValue(0)
        self.progress_label.SetLabel("Starting radar generation...")
        self.cancel_requested = False

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

            def update_progress(current: int, total: int, deck_name: str) -> None:
                if self.cancel_requested:
                    raise InterruptedError("Radar generation cancelled by user")

                percent = int((current / total) * 100) if total > 0 else 0
                wx.CallAfter(self.progress.SetValue, percent)
                wx.CallAfter(
                    self.progress_label.SetLabel,
                    f"Analyzing deck {current}/{total}: {deck_name}",
                )

            radar = self.radar_service.calculate_radar(
                archetype,
                self.format_name,
                progress_callback=update_progress,
            )

            if not self.cancel_requested:
                wx.CallAfter(self.radar_panel.display_radar, radar)
                wx.CallAfter(self.progress_label.SetLabel, "Radar generated successfully!")
                self.current_radar = radar

        except InterruptedError as exc:
            wx.CallAfter(self.progress_label.SetLabel, f"Cancelled: {exc}")
            wx.CallAfter(self.progress.SetValue, 0)

        except Exception as exc:
            logger.exception(f"Failed to generate radar: {exc}")
            wx.CallAfter(self.progress_label.SetLabel, "Failed to generate radar.")
            wx.CallAfter(self.progress.SetValue, 0)

        finally:
            wx.CallAfter(self.generate_btn.Enable, True)
            wx.CallAfter(self.cancel_btn.Enable, False)
            wx.CallAfter(self.archetype_choice.Enable, True)
            if not self.cancel_requested:
                wx.CallAfter(self.progress.SetValue, 0)
            self.worker_thread = None

    def _export_radar(self, radar: RadarData) -> None:
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

                decklist = self.radar_service.export_radar_as_decklist(
                    radar, min_expected_copies=min_expected
                )

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

    def _on_close(self, event: wx.CloseEvent) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            response = wx.MessageBox(
                "Radar generation is in progress. Are you sure you want to close?",
                "Close Radar",
                wx.YES_NO | wx.ICON_QUESTION,
            )
            if response == wx.NO:
                event.Veto()
                return

            self.cancel_requested = True
            if self.worker_thread:
                self.worker_thread.join(timeout=2.0)

        event.Skip()
