"""Data-loading handlers: builder search, card data, collection, bulk index, radar."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

if TYPE_CHECKING:
    from repositories.card_repository import CardDataManager
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class DataLoadingHandlers(_Base):
    """Builder search, card-data loading, collection/bulk callbacks, background radar."""

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
                self.card_panel.clear()
            return
        meta = self.builder_panel.get_result_at_index(idx)
        if not meta:
            return
        self._clear_zone_selections()
        faux_card = {"name": meta.get("name", "Unknown"), "qty": 1}
        self.card_inspector_panel.update_card(faux_card, zone=None, meta=meta)
        self._push_card_panel(faux_card, meta)

    def ensure_card_data_loaded(self: AppFrame) -> None:
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

    # Collection / bulk-data callbacks
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

    # Radar background helpers
    def _on_radar_use_for_search(self: AppFrame, radar) -> None:
        if self.builder_panel:
            self.builder_panel.set_active_radar(radar)
        self._show_left_panel("builder")

    def _load_radar_in_background(self: AppFrame, archetype: dict[str, Any]) -> None:
        radar_service = self.controller.radar_service
        format_name = self.current_format

        def worker() -> None:
            try:
                radar = radar_service.calculate_radar(archetype, format_name)
            except Exception as exc:
                logger.exception(f"Background radar load failed: {exc}")
                return
            wx.CallAfter(self._apply_background_radar, radar)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_background_radar(self: AppFrame, radar) -> None:
        if self.builder_panel:
            self.builder_panel.set_active_radar(radar)
        self.card_panel.update_radar(radar)
