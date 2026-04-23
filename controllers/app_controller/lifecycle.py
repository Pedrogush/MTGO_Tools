"""Startup orchestration, frame construction, and shutdown for :class:`AppController`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from utils.constants import MTGO_BRIDGE_SHUTDOWN_TIMEOUT_SECONDS

if TYPE_CHECKING:
    import wx

    from widgets.app_frame import AppFrame


class LifecycleMixin:
    """Initial-load orchestration, frame factory, and background-worker shutdown."""

    def run_initial_loads(self, deck_save_dir: Path, force_archetypes: bool = False) -> None:
        callbacks = self._ui_callbacks

        # Step 1: Start archetype fetch immediately from local cache (optimistic
        # load), and run the bundle download in parallel.  If apply() returns
        # True the caches were updated, so trigger a silent background re-fetch
        # to refresh the list.
        self.fetch_archetypes(
            on_success=callbacks.on_archetypes_success if callbacks else None,
            on_error=callbacks.on_archetypes_error if callbacks else None,
            on_status=callbacks.on_status if callbacks else None,
            force=force_archetypes,
        )

        def _apply_bundle() -> bool:
            from services.bundle_snapshot_client import get_bundle_snapshot_client

            return get_bundle_snapshot_client().apply()

        def _on_bundle_done(result: tuple[bool, dict[str, list[dict[str, Any]]] | None]) -> None:
            updated, archetypes_by_format = result
            if updated and archetypes_by_format:
                fmt_archetypes = archetypes_by_format.get(self.current_format.lower())
                if fmt_archetypes is not None:
                    # Archetypes already in memory from bundle — skip the disk read.
                    self.archetypes = fmt_archetypes
                    self.filtered_archetypes = fmt_archetypes
                    if callbacks:
                        callbacks.on_archetypes_success(fmt_archetypes)
                    return
            self.fetch_archetypes(
                on_success=callbacks.on_archetypes_success if callbacks else None,
                on_error=callbacks.on_archetypes_error if callbacks else None,
                on_status=callbacks.on_status if callbacks else None,
                force=force_archetypes,
            )

        def _on_bundle_error(exc: Exception) -> None:
            logger.warning(f"Remote bundle apply failed: {exc}")

        self._worker.submit(_apply_bundle, on_success=_on_bundle_done, on_error=_on_bundle_error)

        # Step 3: Load collection from cache (background thread)
        def _load_collection():
            return self.load_collection_from_cache(deck_save_dir)

        def _on_collection_load_done(result: tuple[bool, dict[str, Any] | None]):
            success, info = result
            if success and info:
                if callbacks:
                    callbacks.on_collection_loaded(info)
            else:
                if callbacks:
                    callbacks.on_collection_not_found()

        self._worker.submit(_load_collection, on_success=_on_collection_load_done)

        # Step 4: Check and download bulk data if needed (non-blocking)
        self.check_and_download_bulk_data()

        # Step 5: Pre-load 59 MB card index in the background so it is ready
        # before the user first types in the builder search box.
        self.ensure_card_data_loaded(
            on_success=lambda _: None,
            on_error=lambda exc: logger.warning(f"Background card data pre-load failed: {exc}"),
            on_status=callbacks.on_status if callbacks else lambda *a, **kw: None,
        )

    def create_frame(self, parent: wx.Window | None = None) -> AppFrame:
        import wx

        from controllers.app_controller.ui_callbacks import AppControllerUIHelpers
        from widgets.app_frame import AppFrame

        frame = AppFrame(controller=self, parent=parent)
        self._ui_callbacks = AppControllerUIHelpers(self, frame).build_callbacks()

        wx.CallAfter(frame._restore_session_state)

        wx.CallAfter(
            lambda: self.run_initial_loads(
                deck_save_dir=self.deck_save_dir,
            )
        )

        return frame

    def shutdown(self, timeout: float = MTGO_BRIDGE_SHUTDOWN_TIMEOUT_SECONDS) -> None:
        logger.info("Shutting down AppController background workers...")
        self.image_service.shutdown()
        self._worker.shutdown(timeout=timeout)
