"""Background check for a newer published release, surfaced passively (issue #142)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from controllers.app_controller.protocol import AppControllerProto
    from services.update_service import UpdateInfo

    _Base = AppControllerProto
else:
    _Base = object


class UpdateCheckMixin(_Base):
    """Runs the release check off the UI thread and holds onto its answer."""

    def check_for_update(self) -> None:
        """Start the (throttled) release check in the background.

        Fire-and-forget. The UI is notified only when an update actually exists,
        so the overwhelmingly common "already current" outcome touches nothing.
        """
        if not self.get_update_check_enabled():
            logger.debug("Update check skipped — disabled in settings")
            return

        def _check() -> UpdateInfo | None:
            from services.update_service import get_update_service

            return get_update_service().check()

        def _on_done(info: UpdateInfo | None) -> None:
            if info is None:
                return
            self._available_update = info
            logger.info(f"Update available: v{info.version} ({info.release_url})")
            callbacks = self._ui_callbacks
            if callbacks:
                callbacks.on_update_available(info)

        def _on_error(exc: Exception) -> None:
            # UpdateService.check() absorbs its own failures, so reaching here
            # means something genuinely unforeseen — which still must not reach
            # the user for a feature they never invoked.
            logger.debug(f"Update check failed: {exc}")

        self._worker.submit(_check, on_success=_on_done, on_error=_on_error)

    def get_available_update(self) -> UpdateInfo | None:
        """The newer release found this session, if any. No I/O — safe on the UI thread."""
        return self._available_update
