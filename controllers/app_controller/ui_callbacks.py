"""UI wiring helpers that marshal controller callbacks onto the wx UI thread."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from controllers.app_controller import AppController
    from widgets.app_frame import AppFrame


@dataclass
class UICallbacks:
    on_status: Callable[[str], None]
    on_archetypes_success: Callable[..., None]
    on_archetypes_error: Callable[..., None]
    on_collection_loaded: Callable[[dict[str, Any]], None]
    on_collection_not_found: Callable[[], None]
    on_collection_refresh_success: Callable[..., None]
    on_collection_failed: Callable[[str], None]
    on_bulk_download_needed: Callable[[str], None]
    on_bulk_download_complete: Callable[[str], None]
    on_bulk_download_failed: Callable[[str], None]


class AppControllerUIHelpers:
    def __init__(self, controller: AppController, frame: AppFrame) -> None:
        self._controller = controller
        self._frame = frame

    def build_callbacks(self) -> UICallbacks:
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

        return UICallbacks(
            on_archetypes_success=lambda archetypes: wx.CallAfter(
                frame._on_archetypes_loaded, archetypes
            ),
            on_archetypes_error=lambda error: wx.CallAfter(frame._on_archetypes_error, error),
            on_collection_loaded=_on_collection_loaded,
            on_collection_not_found=lambda: wx.CallAfter(
                frame.collection_status_label.SetLabel,
                frame._t("app.collection.not_found"),
            ),
            on_collection_refresh_success=lambda filepath, cards: wx.CallAfter(
                frame._on_collection_fetched, filepath, cards
            ),
            on_collection_failed=lambda msg: wx.CallAfter(frame._on_collection_fetch_failed, msg),
            on_status=lambda *a, **kw: wx.CallAfter(frame._set_status, *a, **kw),
            on_bulk_download_needed=lambda reason: logger.info(f"Bulk data needs update: {reason}"),
            on_bulk_download_complete=lambda msg: wx.CallAfter(frame._on_bulk_data_downloaded, msg),
            on_bulk_download_failed=lambda msg: wx.CallAfter(frame._on_bulk_data_failed, msg),
        )
