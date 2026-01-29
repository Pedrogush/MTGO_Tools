from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.card_data import CardDataManager
from utils.ui_helpers import open_child_window, widget_exists
from widgets.identify_opponent import MTGOpponentDeckSpy
from widgets.match_history import MatchHistoryFrame
from widgets.metagame_analysis import MetagameAnalysisFrame
from widgets.timer_alert import TimerAlertFrame

if TYPE_CHECKING:
    from widgets.app_frame import AppFrame


class AppEventHandlers:

    # ------------------------------------------------------------------ Properties for state delegation ---------------------------------------
    @property
    def current_format(self) -> str:
        return self.controller.current_format

    @current_format.setter
    def current_format(self, value: str) -> None:
        self.controller.current_format = value

    @property
    def archetypes(self) -> list[dict[str, Any]]:
        return self.controller.archetypes

    @archetypes.setter
    def archetypes(self, value: list[dict[str, Any]]) -> None:
        self.controller.archetypes = value

    @property
    def filtered_archetypes(self) -> list[dict[str, Any]]:
        return self.controller.filtered_archetypes

    @filtered_archetypes.setter
    def filtered_archetypes(self, value: list[dict[str, Any]]) -> None:
        self.controller.filtered_archetypes = value

    @property
    def zone_cards(self) -> dict[str, list[dict[str, Any]]]:
        return self.controller.zone_cards

    @zone_cards.setter
    def zone_cards(self, value: dict[str, list[dict[str, Any]]]) -> None:
        self.controller.zone_cards = value

    @property
    def left_mode(self) -> str:
        return self.controller.left_mode

    @left_mode.setter
    def left_mode(self, value: str) -> None:
        self.controller.left_mode = value

    @property
    def loading_archetypes(self) -> bool:
        return self.controller.loading_archetypes

    @loading_archetypes.setter
    def loading_archetypes(self, value: bool) -> None:
        self.controller.loading_archetypes = value

    @property
    def loading_decks(self) -> bool:
        return self.controller.loading_decks

    @loading_decks.setter
    def loading_decks(self, value: bool) -> None:
        self.controller.loading_decks = value

    @property
    def loading_daily_average(self) -> bool:
        return self.controller.loading_daily_average

    @loading_daily_average.setter
    def loading_daily_average(self, value: bool) -> None:
        self.controller.loading_daily_average = value

    @property
    def _loading_lock(self) -> threading.Lock:
        return self.controller._loading_lock

    @staticmethod
    def format_deck_name(deck: dict[str, Any]) -> str:
        date = deck.get("date", "")
        player = deck.get("player", "")
        event = deck.get("event", "")
        result = deck.get("result", "")
        return f"{date} | {player} — {event} [{result}]".strip()

    # UI Event Handlers
    def on_format_changed(self: AppFrame) -> None:
        self.current_format = self.research_panel.get_selected_format()
        self.fetch_archetypes(force=True)

    def on_archetype_filter(self: AppFrame) -> None:
        query = self.research_panel.get_search_query()
        if not query:
            self.filtered_archetypes = list(self.archetypes)
        else:
            self.filtered_archetypes = [
                entry for entry in self.archetypes if query in entry.get("name", "").lower()
            ]
        self._populate_archetype_list()

    def on_archetype_selected(self: AppFrame) -> None:
        with self._loading_lock:
            if self.loading_archetypes or self.loading_decks:
                return
        idx = self.research_panel.get_selected_archetype_index()
        if idx < 0:
            return
        archetype = self.filtered_archetypes[idx]
        self._load_decks_for_archetype(archetype)

    def on_deck_selected(self: AppFrame, _event: wx.CommandEvent) -> None:
        with self._loading_lock:
            if self.loading_decks:
                return
        idx = self.deck_list.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        deck = self.controller.deck_repo.get_decks_list()[idx]
        self.controller.deck_repo.set_current_deck(deck)
        self.copy_button.Disable()
        self.save_button.Disable()
        self._set_status(f"Loading deck {self.format_deck_name(deck)}…")
        self._show_left_panel("builder")
        self._download_and_display_deck(deck)
        self._schedule_settings_save()

    def on_daily_average_clicked(self: AppFrame, _event: wx.CommandEvent) -> None:
        with self._loading_lock:
            if self.loading_daily_average:
                return
        if not self.controller.deck_repo.get_decks_list():
            return
        self._start_daily_average_build()

    def on_copy_clicked(self: AppFrame, _event: wx.CommandEvent) -> None:
        deck_content = self.controller.build_deck_text(self.zone_cards).strip()
        if not deck_content:
            wx.MessageBox("No deck to copy.", "Copy Deck", wx.OK | wx.ICON_INFORMATION)
            return
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(deck_content))
            finally:
                wx.TheClipboard.Close()
            self._set_status("Deck copied to clipboard.")
        else:  # pragma: no cover
            wx.MessageBox("Could not access clipboard.", "Copy Deck", wx.OK | wx.ICON_WARNING)

    def on_save_clicked(self: AppFrame, _event: wx.CommandEvent) -> None:
        deck_content = self.controller.build_deck_text(self.zone_cards).strip()
        if not deck_content:
            wx.MessageBox("Load a deck first.", "Save Deck", wx.OK | wx.ICON_INFORMATION)
            return
        default_name = "saved_deck"
        current_deck = self.controller.deck_repo.get_current_deck()
        if current_deck:
            default_name = self.format_deck_name(current_deck).replace(" | ", "_")
        dlg = wx.TextEntryDialog(self, "Deck name:", "Save Deck", default_name=default_name)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        deck_name = dlg.GetValue().strip() or default_name
        dlg.Destroy()

        try:
            file_path, deck_id = self.controller.save_deck(
                deck_name=deck_name,
                deck_content=deck_content,
                format_name=self.current_format,
                deck=current_deck,
            )
        except OSError as exc:  # pragma: no cover
            wx.MessageBox(f"Failed to write deck file:\n{exc}", "Save Deck", wx.OK | wx.ICON_ERROR)
            return

        message = f"Deck saved to {file_path}"
        if deck_id:
            message += f"\nDatabase ID: {deck_id}"
        wx.MessageBox(message, "Deck Saved", wx.OK | wx.ICON_INFORMATION)
        self._set_status("Deck saved successfully.")

    def on_window_change(self: AppFrame, event: wx.Event) -> None:
        self._schedule_settings_save()
        event.Skip()

    def on_close(self: AppFrame, event: wx.CloseEvent) -> None:
        if self._save_timer and self._save_timer.IsRunning():
            self._save_timer.Stop()
        self._save_window_settings()
        # Close all managed dialogs
        self._dialog_manager.close_all()
        # Handle mana keyboard separately (not yet managed by dialog manager)
        if self.mana_keyboard_window and self.mana_keyboard_window.IsShown():
            self.mana_keyboard_window.Destroy()
            self.mana_keyboard_window = None
        self.controller.shutdown()
        event.Skip()

    # Async Callback Handlers
    def _on_archetypes_loaded(self: AppFrame, items: list[dict[str, Any]]) -> None:
        with self._loading_lock:
            self.loading_archetypes = False
        self.archetypes = sorted(items, key=lambda entry: entry.get("name", "").lower())
        self.filtered_archetypes = list(self.archetypes)
        self._populate_archetype_list()
        self.research_panel.enable_controls()
        count = len(self.archetypes)
        self._set_status(f"Loaded {count} archetypes for {self.current_format}.")
        self.summary_text.ChangeValue(
            f"Select an archetype to view decks.\nLoaded {count} archetypes."
        )

    def _on_archetypes_error(self: AppFrame, error: Exception) -> None:
        with self._loading_lock:
            self.loading_archetypes = False
        self.research_panel.set_error_state()
        self._set_status(f"Error: {error}")
        wx.MessageBox(
            f"Unable to load archetypes:\n{error}", "Archetype Error", wx.OK | wx.ICON_ERROR
        )

    def _on_decks_loaded(self: AppFrame, archetype_name: str, decks: list[dict[str, Any]]) -> None:
        with self._loading_lock:
            self.loading_decks = False
        self.controller.deck_repo.set_decks_list(decks)
        self.deck_list.Clear()
        if not decks:
            self.deck_list.Append("No decks found.")
            self.deck_list.Disable()
            self._set_status(f"No decks for {archetype_name}.")
            self.summary_text.ChangeValue(f"{archetype_name}\n\nNo deck data available.")
            return
        for deck in decks:
            self.deck_list.Append(self.format_deck_name(deck))
        self.deck_list.Enable()
        self.daily_average_button.Enable()
        self._present_archetype_summary(archetype_name, decks)
        self._set_status(
            f"Loaded {len(decks)} decks for {archetype_name}. Click a deck to load it."
        )

    def _on_decks_error(self: AppFrame, error: Exception) -> None:
        with self._loading_lock:
            self.loading_decks = False
        self.deck_list.Clear()
        self.deck_list.Append("Failed to load decks.")
        self._set_status(f"Error loading decks: {error}")
        wx.MessageBox(f"Failed to load deck lists:\n{error}", "Deck Error", wx.OK | wx.ICON_ERROR)

    def _on_deck_download_error(self: AppFrame, error: Exception) -> None:
        self.copy_button.Disable()
        self.save_button.Disable()
        self._set_status(f"Deck download failed: {error}")
        wx.MessageBox(f"Failed to download deck:\n{error}", "Deck Download", wx.OK | wx.ICON_ERROR)

    def _on_deck_content_ready(self: AppFrame, deck_text: str, source: str = "manual") -> None:
        self.controller.deck_repo.set_current_deck_text(deck_text)
        stats = self.controller.deck_service.analyze_deck(deck_text)
        self.zone_cards["main"] = sorted(
            [{"name": name, "qty": qty} for name, qty in stats["mainboard_cards"]],
            key=lambda card: card["name"].lower(),
        )
        self.zone_cards["side"] = sorted(
            [{"name": name, "qty": qty} for name, qty in stats["sideboard_cards"]],
            key=lambda card: card["name"].lower(),
        )
        self.zone_cards["out"] = self._load_outboard_for_current()
        self.main_table.set_cards(self.zone_cards["main"])
        self.side_table.set_cards(self.zone_cards["side"])
        if self.out_table:
            self.out_table.set_cards(self.zone_cards["out"])
        self._update_stats(deck_text)
        self.copy_button.Enable(True)
        self.save_button.Enable(True)
        self.deck_notes_panel.load_notes_for_current()
        self._load_guide_for_current()
        self._set_status(f"Deck ready ({source}).")
        self._show_left_panel("builder")
        self._schedule_settings_save()

    def _on_collection_fetched(self: AppFrame, filepath: Path, cards: list) -> None:
        if cards:
            try:
                info = self.controller.collection_service.load_from_card_list(cards, filepath)
                card_count = info["card_count"]
            except ValueError as exc:
                logger.error(f"Failed to load collection: {exc}")
                self.collection_status_label.SetLabel(f"Collection load failed: {exc}")
                return
        else:
            card_count = len(self.controller.collection_service.get_inventory())

        self.collection_status_label.SetLabel(f"Collection: {filepath.name} ({card_count} entries)")
        self._render_pending_deck()

    def _on_collection_fetch_failed(self: AppFrame, error_msg: str) -> None:
        self.controller.collection_service.clear_inventory()
        self.collection_status_label.SetLabel(f"Collection fetch failed: {error_msg}")
        logger.warning(f"Collection fetch failed: {error_msg}")

    def _on_bulk_data_loaded(
        self: AppFrame, by_name: dict[str, list[dict[str, Any]]], stats: dict[str, Any]
    ) -> None:
        self.controller.image_service.clear_printing_index_loading()
        self.controller.image_service.set_bulk_data(by_name)
        self.card_inspector_panel.set_bulk_data(by_name)
        self._set_status("Ready")
        logger.info(
            "Printings index ready: {unique} names / {total} printings",
            unique=stats.get("unique_names"),
            total=stats.get("total_printings"),
        )
        if self._builder_search_pending:
            self._builder_search_pending = False
            wx.CallAfter(self._on_builder_search)

    def _on_bulk_data_load_failed(self: AppFrame, error_msg: str) -> None:
        self.controller.image_service.clear_printing_index_loading()
        self._set_status("Ready")
        logger.warning(f"Card printings index load failed: {error_msg}")

    def _on_bulk_data_downloaded(self: AppFrame, msg: str) -> None:
        self._set_status("Card image database downloaded, indexing printings…")
        logger.info(f"Bulk data downloaded: {msg}")
        self.controller.load_bulk_data_into_memory(
            on_status=lambda status: wx.CallAfter(self._set_status, status),
            force=True,
        )

    def _on_bulk_data_failed(self: AppFrame, error_msg: str) -> None:
        self._set_status("Ready")
        logger.warning(f"Bulk data download failed: {error_msg}")

    # Builder Panel Handlers
    def _on_builder_search(self: AppFrame) -> None:
        card_manager = self.controller.card_repo.get_card_manager()
        if not card_manager or not self.controller.card_repo.is_card_data_loaded():
            if not self.controller.card_repo.is_card_data_loading():
                self.ensure_card_data_loaded()
            self._builder_search_pending = True
            if self.builder_panel and self.builder_panel.status_label:
                self.builder_panel.status_label.SetLabel(
                    "Loading card data… (search will run automatically)"
                )
            return

        self._builder_search_pending = False
        filters = self.builder_panel.get_filters()

        mv_value_text = filters.get("mv_value", "")
        if mv_value_text:
            try:
                float(mv_value_text)
            except ValueError:
                if self.builder_panel and self.builder_panel.status_label:
                    self.builder_panel.status_label.SetLabel("Mana value must be numeric.")
                return

        results = self.controller.search_service.search_with_builder_filters(filters, card_manager)
        self.builder_panel.update_results(results)

    def _on_builder_clear(self: AppFrame) -> None:
        self.builder_panel.clear_filters()

    def _on_builder_result_selected(self: AppFrame, idx: int) -> None:
        meta = self.builder_panel.get_result_at_index(idx)
        if not meta:
            return
        faux_card = {"name": meta.get("name", "Unknown"), "qty": 1}
        self.card_inspector_panel.update_card(faux_card, zone=None, meta=meta)

    def _on_deck_source_changed(self: AppFrame, _event: wx.CommandEvent | None) -> None:
        if not self.deck_source_choice:
            return
        selection = self.deck_source_choice.GetSelection()
        source_map = {0: "both", 1: "mtggoldfish", 2: "mtgo"}
        source = source_map.get(selection, "both")
        self.controller.set_deck_data_source(source)
        self._schedule_settings_save()

    def _on_daily_average_success(
        self, buffer: dict[str, float], deck_count: int, progress_dialog: wx.ProgressDialog
    ) -> None:
        self.daily_average_button.Enable()
        deck_text = self.controller.deck_service.render_average_deck(buffer, deck_count)
        self._on_deck_content_ready(deck_text, source="average")

        try:
            progress_dialog.Update(deck_count)
            progress_dialog.Close()
        except Exception as dialog_exc:
            logger.error(f"Error closing progress dialog: {dialog_exc}")

    def _on_daily_average_error(self, error: Exception, progress_dialog: wx.ProgressDialog) -> None:
        logger.error(f"Daily average error: {error}")
        try:
            progress_dialog.Close()
        except Exception as exc:
            logger.debug("Error closing progress dialog after failure: %s", exc)
        self.daily_average_button.Enable()
        wx.MessageBox(
            f"Failed to build daily average:\n{error}", "Daily Average", wx.OK | wx.ICON_ERROR
        )
        self._set_status(f"Daily average failed: {error}")

    def ensure_card_data_loaded(self) -> None:
        def on_success(manager: CardDataManager):
            # Update UI panels with card manager (marshalled to UI thread by controller)
            inspector = getattr(self, "card_inspector_panel", None)
            stats = getattr(self, "deck_stats_panel", None)

            def apply_card_data() -> None:
                if inspector:
                    inspector.set_card_manager(manager)
                if stats:
                    stats.set_card_manager(manager)
                self._render_pending_deck()

            wx.CallAfter(apply_card_data)

        def on_error(error: Exception):
            # Show error dialog on UI thread
            wx.CallAfter(
                wx.MessageBox,
                f"Failed to load card database:\n{error}",
                "Card Data Error",
                wx.OK | wx.ICON_ERROR,
            )

        def on_status(message: str):
            # Update status bar on UI thread
            wx.CallAfter(self._set_status, message)

        # Delegate business logic to controller
        self.controller.ensure_card_data_loaded(
            on_success=on_success, on_error=on_error, on_status=on_status
        )

    # ------------------------------------------------------------------ Helpers --------------------------------------------------------------
    def open_opponent_tracker(self) -> None:
        self._dialog_manager.open_window(
            "tracker_window",
            MTGOpponentDeckSpy,
            "Opponent Tracker",
        )

    def open_timer_alert(self) -> None:
        self._dialog_manager.open_window(
            "timer_window",
            TimerAlertFrame,
            "Timer Alert",
        )

    def open_match_history(self) -> None:
        self._dialog_manager.open_window(
            "history_window",
            MatchHistoryFrame,
            "Match History",
        )

    def open_metagame_analysis(self) -> None:
        self._dialog_manager.open_window(
            "metagame_window",
            MetagameAnalysisFrame,
            "Metagame Analysis",
        )

    def _start_daily_average_build(self) -> None:
        self.daily_average_button.Disable()

        progress_dialog = wx.ProgressDialog(
            "Daily Average",
            "Downloading decks…",
            maximum=100,
            parent=self,
            style=wx.PD_APP_MODAL | wx.PD_ELAPSED_TIME,
        )

        can_proceed, message = self.controller.build_daily_average_deck(
            on_success=lambda buffer, deck_count: wx.CallAfter(
                self._on_daily_average_success, buffer, deck_count, progress_dialog
            ),
            on_error=lambda error: wx.CallAfter(
                self._on_daily_average_error, error, progress_dialog
            ),
            on_status=lambda msg: wx.CallAfter(self._set_status, msg),
            on_progress=lambda current, total: wx.CallAfter(
                progress_dialog.Update, current, f"Processed {current}/{total} decks…"
            ),
        )

        if not can_proceed:
            progress_dialog.Close()
            self.daily_average_button.Enable()
            wx.MessageBox(message, "Daily Average", wx.OK | wx.ICON_INFORMATION)
            return

        progress_dialog.SetRange(int(message.split()[1]))

    def _download_and_display_deck(self, deck: dict[str, Any]) -> None:
        deck_number = deck.get("number")
        if not deck_number:
            wx.MessageBox("Deck identifier missing.", "Deck Error", wx.OK | wx.ICON_ERROR)
            return

        # Update UI state immediately
        self.copy_button.Disable()
        self.save_button.Disable()

        # Delegate to controller
        self.controller.download_and_display_deck(
            deck=deck,
            on_success=lambda content: wx.CallAfter(self._on_deck_download_success, content),
            on_error=lambda error: wx.CallAfter(self._on_deck_download_error, error),
            on_status=lambda msg: wx.CallAfter(self._set_status, msg),
        )

    def _present_archetype_summary(self, archetype_name: str, decks: list[dict[str, Any]]) -> None:
        by_date: dict[str, int] = {}
        for deck in decks:
            date = deck.get("date", "").lower()
            by_date[date] = by_date.get(date, 0) + 1
        latest_dates = sorted(by_date.items(), reverse=True)[:7]
        lines = [archetype_name, "", f"Total decks loaded: {len(decks)}", ""]
        if latest_dates:
            lines.append("Recent activity:")
            for day, count in latest_dates:
                lines.append(f"  {day}: {count} deck(s)")
        else:
            lines.append("No recent deck activity.")
        self.summary_text.ChangeValue("\n".join(lines))

    def _load_decks_for_archetype(self, archetype: dict[str, Any]) -> None:
        name = archetype.get("name", "Unknown")

        # Update UI state immediately
        self.deck_list.Clear()
        self.deck_list.Append("Loading…")
        self.deck_list.Disable()
        self.summary_text.ChangeValue(f"{name}\n\nFetching deck results…")

        # Delegate to controller
        self.controller.load_decks_for_archetype(
            archetype=archetype,
            on_success=lambda archetype_name, decks: wx.CallAfter(
                self._on_decks_loaded, archetype_name, decks
            ),
            on_error=lambda error: wx.CallAfter(self._on_decks_error, error),
            on_status=lambda msg: wx.CallAfter(self._set_status, msg),
        )
