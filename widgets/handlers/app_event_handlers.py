from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.card_data import CardDataManager
from utils.constants import LOGS_DIR
from utils.deck import sanitize_filename
from utils.deck_results_filter import _classify_event_type, _normalize_date, filter_decks
from utils.ui_helpers import open_child_window, widget_exists
from widgets.dialogs.feedback_dialog import show_feedback_dialog
from widgets.identify_opponent import MTGOpponentDeckSpy
from widgets.match_history import MatchHistoryFrame
from widgets.metagame_analysis import MetagameAnalysisFrame
from widgets.timer_alert import TimerAlertFrame
from widgets.top_cards import TopCardsFrame

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
    def _normalize_date(value: str) -> str:
        return _normalize_date(value)

    @staticmethod
    def _strip_extra_dates(value: str) -> str:
        if not value:
            return ""
        matches = list(re.finditer(r"\d{4}-\d{2}-\d{2}", value))
        if not matches:
            return value
        result = value
        for match in reversed(matches):
            start, end = match.span()
            prefix_start = start
            while prefix_start > 0 and result[prefix_start - 1] in " -–—|/":
                prefix_start -= 1
            suffix_end = end
            while suffix_end < len(result) and result[suffix_end] in " -–—|/":
                suffix_end += 1
            result = f"{result[:prefix_start].rstrip()} {result[suffix_end:].lstrip()}"
        return " ".join(result.split())

    @staticmethod
    def format_deck_name(deck: dict[str, Any]) -> str:
        date = AppEventHandlers._normalize_date(deck.get("date", ""))
        player = deck.get("player", "")
        event = AppEventHandlers._strip_extra_dates(deck.get("event", ""))
        result = deck.get("result", "")
        line_parts = [part for part in (player, result, date) if part]
        line_one = ", ".join(line_parts) if line_parts else "Unknown"
        line_two = event
        return f"{line_one} | {line_two}".strip(" |")

    @staticmethod
    def format_deck_list_entry(deck: dict[str, Any], show_source: bool = False) -> str:
        date = AppEventHandlers._normalize_date(deck.get("date", ""))
        player = deck.get("player", "")
        event = AppEventHandlers._strip_extra_dates(deck.get("event", ""))
        result = deck.get("result", "")
        line_parts = [part for part in (player, result, date) if part]
        line_one = ", ".join(line_parts) if line_parts else "Unknown"
        if show_source:
            source = deck.get("source", "")
            emoji = "🐠" if source == "mtggoldfish" else "🧙🏾‍♂️"
            line_one = f"{emoji} {line_one}"
        line_two = event
        return f"{line_one}\n{line_two}".strip()

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

    def on_event_type_filter_changed(self: AppFrame) -> None:
        self._apply_deck_filters()

    def on_result_filter_changed(self: AppFrame) -> None:
        self._apply_deck_filters()

    def on_player_name_filter_changed(self: AppFrame) -> None:
        self._apply_deck_filters()

    def on_date_filter_changed(self: AppFrame) -> None:
        self._apply_deck_filters()

    @staticmethod
    def _classify_event_type(event_str: str) -> str | None:
        """Return a canonical event type label for the given event string, or None."""
        return _classify_event_type(event_str)

    def _apply_deck_filters(self: AppFrame) -> None:
        """Filter the displayed deck list based on all active filters (AND logic)."""
        event_type = self.research_panel.get_event_type_filter()
        result_query = self.research_panel.get_result_filter()
        player_query = self.research_panel.get_player_name_filter()
        date_query = self.research_panel.get_date_filter()

        self.controller.session_manager.update_deck_event_type_filter(event_type)
        self.controller.session_manager.update_deck_result_filter(result_query)
        self.controller.session_manager.update_deck_player_filter(player_query)
        self.controller.session_manager.update_deck_date_filter(date_query)
        self._schedule_settings_save()

        filtered = filter_decks(
            list(self._all_loaded_decks), event_type, result_query, player_query, date_query
        )
        self.controller.deck_repo.set_decks_list(filtered)
        self.deck_list.Clear()
        if not filtered:
            self.deck_list.Append(self._t("deck_results.no_decks"))
            self.deck_list.Disable()
            return
        show_source = self.controller.get_deck_data_source() == "both"
        for deck in filtered:
            self.deck_list.AppendDeck(
                player=deck.get("player", "Unknown"),
                event=AppEventHandlers._strip_extra_dates(deck.get("event", "")),
                result=deck.get("result", ""),
                date=AppEventHandlers._normalize_date(deck.get("date", "")),
                emoji=(
                    ("🐠" if deck.get("source") == "mtggoldfish" else "🧙🏾‍♂️")
                    if show_source
                    else ""
                ),
            )
        self.deck_list.Enable()

    def on_deck_selected(self: AppFrame, _event: wx.CommandEvent | None = None) -> None:
        with self._loading_lock:
            if self.loading_decks:
                return
        idx = self.deck_list.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        deck = self.controller.deck_repo.get_decks_list()[idx]
        self.controller.deck_repo.set_current_deck(deck)
        self.deck_notes_panel.load_notes_for_current()
        self.copy_button.Disable()
        self.save_button.Disable()
        self._set_status("app.status.loading_deck", name=self.format_deck_name(deck))
        loading_label = self._t("deck.loading")
        self.main_table.show_loading(loading_label)
        self.side_table.show_loading(loading_label)
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

    def on_load_deck_clicked(self: AppFrame) -> None:
        save_dir = self.controller.deck_save_dir
        default_dir = str(save_dir) if save_dir.exists() else str(Path.home())
        logger.info("Load Deck button clicked")
        with wx.FileDialog(
            self,
            "Load Deck",
            defaultDir=default_dir,
            wildcard="Text files (*.txt)|*.txt|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                logger.info("Load Deck cancelled")
                return
            file_path = dlg.GetPath()

        file_ref = Path(file_path)
        deck_key = sanitize_filename(file_ref.stem, fallback="manual").lower()
        self.controller.deck_repo.set_current_deck(
            {
                "href": deck_key,
                "name": file_ref.stem,
                "path": str(file_ref),
                "source": "file",
            }
        )
        logger.info(f"Load Deck selected: {file_path} (deck_key={deck_key})")

        try:
            deck_text = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            logger.error(f"Failed to read deck file '{file_path}': {exc}")
            wx.MessageBox(f"Failed to read deck file:\n{exc}", "Load Deck", wx.OK | wx.ICON_ERROR)
            return

        self._on_deck_content_ready(deck_text, source="file")

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
            self._set_status("app.status.deck_copied")
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
        dlg = wx.TextEntryDialog(self, "Deck name:", "Save Deck", default_name)
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
        self._set_status("app.status.deck_saved")

    def on_window_change(self: AppFrame, event: wx.Event) -> None:
        self._schedule_settings_save()
        event.Skip()

    def on_close(self: AppFrame, event: wx.CloseEvent) -> None:
        if self._save_timer and self._save_timer.IsRunning():
            self._save_timer.Stop()
        self._save_window_settings()
        for attr in ("tracker_window", "timer_window", "history_window"):
            window = getattr(self, attr)
            if widget_exists(window):
                window.Destroy()
                setattr(self, attr, None)
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
        self._set_status("app.research.archetypes_loaded", count=count, format=self.current_format)
        # Skip overwriting the deck summary if a deck is already displayed — this handler
        # may be called a second time by the background stale-while-revalidate refresh.
        if not self._has_deck_loaded():
            self.summary_text.ChangeValue(
                self._t("app.research.select_archetype_loaded", count=count)
            )

    def _on_archetypes_error(self: AppFrame, error: Exception) -> None:
        with self._loading_lock:
            self.loading_archetypes = False
        self.research_panel.set_error_state()
        self._set_status("app.status.archetypes_error", error=error)
        wx.MessageBox(
            f"Unable to load archetypes:\n{error}", "Archetype Error", wx.OK | wx.ICON_ERROR
        )

    def _on_decks_loaded(self: AppFrame, archetype_name: str, decks: list[dict[str, Any]]) -> None:
        with self._loading_lock:
            self.loading_decks = False
        self._all_loaded_decks = decks
        if self._is_first_deck_load:
            self._is_first_deck_load = False
            sm = self.controller.session_manager
            self.research_panel.set_event_type_filter(sm.get_deck_event_type_filter())
            self.research_panel.set_result_filter(sm.get_deck_result_filter())
            self.research_panel.set_player_name_filter(sm.get_deck_player_filter())
            self.research_panel.set_date_filter(sm.get_deck_date_filter())
        else:
            self.research_panel.reset_event_type_filter()
            self.research_panel.reset_result_filter()
            self.research_panel.reset_player_name_filter()
            self.research_panel.reset_date_filter()
        if not decks:
            self.controller.deck_repo.set_decks_list([])
            self.deck_list.Clear()
            self.deck_list.Append(self._t("deck_results.no_decks"))
            self.deck_list.Disable()
            self._set_status("deck_results.no_decks_for", archetype=archetype_name)
            self.summary_text.ChangeValue(f"{archetype_name}\n\nNo deck data available.")
            return
        self._apply_deck_filters()
        self.daily_average_button.Enable()
        self._present_archetype_summary(archetype_name, decks)
        self._set_status(
            "deck_results.status.loaded_decks", count=len(decks), archetype=archetype_name
        )

    def _on_decks_error(self: AppFrame, error: Exception) -> None:
        with self._loading_lock:
            self.loading_decks = False
        self.deck_list.Clear()
        self.deck_list.Append(self._t("deck_results.failed_load"))
        self._set_status("app.status.decks_error", error=error)
        wx.MessageBox(f"Failed to load deck lists:\n{error}", "Deck Error", wx.OK | wx.ICON_ERROR)

    def _on_deck_download_error(self: AppFrame, error: Exception) -> None:
        self.copy_button.Disable()
        self.save_button.Disable()
        self._set_status("app.status.deck_download_error", error=error)
        wx.MessageBox(f"Failed to download deck:\n{error}", "Deck Download", wx.OK | wx.ICON_ERROR)

    def _on_deck_content_ready(self: AppFrame, deck_text: str, source: str = "manual") -> None:
        if source in {"manual", "automation", "average"}:
            self.controller.deck_repo.set_current_deck(None)
        logger.info(
            "Deck content ready: source={} current_deck={} deck_key={}",
            source,
            self.controller.deck_repo.get_current_deck(),
            self.controller.deck_repo.get_current_deck_key(),
        )
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
        logger.info("Triggering deck notes reload for source={}", source)
        self.deck_notes_panel.load_notes_for_current()
        self._load_guide_for_current()
        self._set_status("app.status.deck_ready", source=source)
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
        self._set_status("app.status.ready")
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
        self._set_status("app.status.ready")
        logger.warning(f"Card printings index load failed: {error_msg}")

    def _on_bulk_data_downloaded(self: AppFrame, msg: str) -> None:
        self._set_status("bulk.status.downloaded_indexing")
        logger.info(f"Bulk data downloaded: {msg}")
        self.controller.load_bulk_data_into_memory(
            on_status=lambda *a, **kw: wx.CallAfter(self._set_status, *a, **kw),
            force=True,
        )

    def _on_bulk_data_failed(self: AppFrame, error_msg: str) -> None:
        self._set_status("app.status.ready")
        logger.warning(f"Bulk data download failed: {error_msg}")

    def _on_mana_keyboard_closed(self: AppFrame, event: wx.CloseEvent) -> None:
        self.mana_keyboard_window = None
        event.Skip()

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

        self._search_seq += 1
        seq = self._search_seq
        search_service = self.controller.search_service

        def _run_search() -> list:
            return search_service.search_with_builder_filters(filters, card_manager)

        def _on_results(results: list) -> None:
            if seq != self._search_seq:
                return
            self.builder_panel.update_results(results)

        self.controller._worker.submit(_run_search, on_success=_on_results)

    def _on_builder_clear(self: AppFrame) -> None:
        self.builder_panel.clear_filters()

    def _on_builder_result_selected(self: AppFrame, idx: int | None) -> None:
        if idx is None:
            if self.card_inspector_panel.active_zone is None:
                self.card_inspector_panel.reset()
            return
        meta = self.builder_panel.get_result_at_index(idx)
        if not meta:
            return
        self._clear_zone_selections()
        faux_card = {"name": meta.get("name", "Unknown"), "qty": 1}
        self.card_inspector_panel.update_card(faux_card, zone=None, meta=meta)

    def _on_daily_average_success(self, deck_text: str) -> None:
        self.daily_average_button.Enable()
        self._on_deck_content_ready(deck_text, source="average")

    def _on_daily_average_error(self, error: Exception) -> None:
        logger.error(f"Daily average error: {error}")
        self.daily_average_button.Enable()
        wx.MessageBox(
            f"Failed to build daily average:\n{error}", "Daily Average", wx.OK | wx.ICON_ERROR
        )
        self._set_status("app.status.daily_average_error", error=error)

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

        def on_status(key: str, **kwargs: object) -> None:
            # Update status bar on UI thread
            wx.CallAfter(self._set_status, key, **kwargs)

        # Delegate business logic to controller
        self.controller.ensure_card_data_loaded(
            on_success=on_success,
            on_error=on_error,
            on_status=on_status,
        )

    # ------------------------------------------------------------------ Helpers --------------------------------------------------------------
    def open_opponent_tracker(self) -> None:
        existing = getattr(self, "tracker_window", None)
        if widget_exists(existing):
            existing.Raise()
            return

        def on_tracker_close(evt: wx.CloseEvent, attr: str) -> None:
            self._handle_child_close(evt, attr)
            self.Show()
            self.Raise()

        window = open_child_window(
            self,
            "tracker_window",
            MTGOpponentDeckSpy,
            "Opponent Tracker",
            on_tracker_close,
            locale=self.locale,
        )
        if window is not None:
            self.Hide()

    def open_timer_alert(self) -> None:
        open_child_window(
            self,
            "timer_window",
            TimerAlertFrame,
            "Timer Alert",
            self._handle_child_close,
            locale=self.locale,
        )

    def open_match_history(self) -> None:
        open_child_window(
            self,
            "history_window",
            MatchHistoryFrame,
            "Match History",
            self._handle_child_close,
            locale=self.locale,
        )

    def open_metagame_analysis(self) -> None:
        open_child_window(
            self,
            "metagame_window",
            MetagameAnalysisFrame,
            "Metagame Analysis",
            self._handle_child_close,
            locale=self.locale,
        )

    def open_top_cards(self) -> None:
        open_child_window(
            self,
            "top_cards_window",
            TopCardsFrame,
            "Top Cards",
            self._handle_child_close,
            locale=self.locale,
        )

    def _open_feedback_dialog(self) -> None:
        show_feedback_dialog(
            self,
            LOGS_DIR,
            event_logging_enabled=self.controller.get_event_logging_enabled(),
            on_event_logging_changed=self.controller.set_event_logging_enabled,
        )

    def _handle_child_close(self, event: wx.CloseEvent, attr: str) -> None:
        setattr(self, attr, None)
        event.Skip()

    def _start_daily_average_build(self) -> None:
        self.daily_average_button.Disable()

        can_proceed, message = self.controller.build_daily_average_deck(
            on_success=lambda deck_text: wx.CallAfter(self._on_daily_average_success, deck_text),
            on_error=lambda error: wx.CallAfter(self._on_daily_average_error, error),
            on_status=lambda *a, **kw: wx.CallAfter(self._set_status, *a, **kw),
            on_progress=lambda current, total: wx.CallAfter(
                self._set_status, "app.status.building_average", current=current, total=total
            ),
        )

        if not can_proceed:
            self.daily_average_button.Enable()
            wx.MessageBox(message, "Daily Average", wx.OK | wx.ICON_INFORMATION)
            return

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
            on_status=lambda *a, **kw: wx.CallAfter(self._set_status, *a, **kw),
        )

    def _present_archetype_summary(self, archetype_name: str, decks: list[dict[str, Any]]) -> None:
        by_date: dict[str, int] = {}
        for deck in decks:
            date = deck.get("date", "").lower()
            by_date[date] = by_date.get(date, 0) + 1
        latest_dates = sorted(by_date.items(), reverse=True)[:7]
        lines = [archetype_name, "", self._t("deck_results.total_loaded", count=len(decks)), ""]
        if latest_dates:
            lines.append(self._t("deck_results.recent_activity"))
            for day, count in latest_dates:
                lines.append(f"  {day}: {count} deck(s)")
        else:
            lines.append(self._t("deck_results.no_activity"))
        self.summary_text.ChangeValue("\n".join(lines))

    def _load_decks_for_archetype(self, archetype: dict[str, Any]) -> None:
        name = archetype.get("name", "Unknown")
        self._all_loaded_decks = []
        if not self._is_first_deck_load:
            self.research_panel.reset_event_type_filter()
            self.research_panel.reset_result_filter()
            self.research_panel.reset_player_name_filter()
            self.research_panel.reset_date_filter()

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
            on_status=lambda *a, **kw: wx.CallAfter(self._set_status, *a, **kw),
        )
