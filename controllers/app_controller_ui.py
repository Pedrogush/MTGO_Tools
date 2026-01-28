"""UI wiring helpers for AppController."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from controllers.app_controller import AppController
    from widgets.app_frame import AppFrame


class AppControllerUIBindings:
    def __init__(self, controller: AppController, frame: AppFrame) -> None:
        self._controller = controller
        self._frame = frame

    def build_callbacks(self) -> dict[str, Callable[..., Any]]:
        import wx

        frame = self._frame

        def _format_collection_label(info: dict[str, Any]) -> str:
            filepath = info["filepath"]
            card_count = info["card_count"]
            age_hours = info["age_hours"]
            age_str = f"{age_hours}h ago" if age_hours > 0 else "recent"
            return f"Collection: {filepath.name} ({card_count} entries, {age_str})"

        def _on_collection_loaded(info: dict[str, Any]) -> None:
            wx.CallAfter(
                frame.collection_status_label.SetLabel,
                _format_collection_label(info),
            )
            wx.CallAfter(frame._render_pending_deck)

        # Define UI callback functions that marshal to UI thread
        return {
            "on_archetypes_success": lambda archetypes: wx.CallAfter(
                frame._on_archetypes_loaded, archetypes
            ),
            "on_archetypes_error": lambda error: wx.CallAfter(frame._on_archetypes_error, error),
            "on_collection_loaded": _on_collection_loaded,
            "on_collection_not_found": lambda: wx.CallAfter(
                frame.collection_status_label.SetLabel,
                "No collection found. Click 'Refresh Collection' to fetch from MTGO.",
            ),
            "on_collection_refresh_success": lambda filepath, cards: wx.CallAfter(
                frame._on_collection_fetched, filepath, cards
            ),
            "on_collection_failed": lambda msg: wx.CallAfter(
                frame._on_collection_fetch_failed, msg
            ),
            "on_status": lambda message: wx.CallAfter(frame._set_status, message),
            "on_bulk_download_needed": lambda reason: logger.info(
                f"Bulk data needs update: {reason}"
            ),
            "on_bulk_download_complete": lambda msg: wx.CallAfter(
                frame._on_bulk_data_downloaded, msg
            ),
            "on_bulk_download_failed": lambda msg: wx.CallAfter(frame._on_bulk_data_failed, msg),
            "on_mtgo_status_change": lambda ready: wx.CallAfter(
                frame.toolbar.enable_mtgo_buttons, ready
            ),
        }
