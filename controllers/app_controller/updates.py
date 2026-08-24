"""Finding a newer published release, and applying it in-app (issue #142).

Two halves, and the split matters: :meth:`UpdateCheckMixin.check_for_update` is
fire-and-forget background work the user never asked for, while
:meth:`UpdateCheckMixin.apply_available_update` runs only after they said yes in
:class:`widgets.dialogs.update_dialog.UpdateDialog` and ends by closing the app.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path

    from controllers.app_controller.protocol import AppControllerProto
    from services.update_installer import ProgressCallback, ReleaseUnavailable, UpdateInstaller
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

    def apply_available_update(
        self,
        *,
        on_progress: ProgressCallback | None = None,
        on_launched: Callable[[], None] | None = None,
        on_failure: Callable[[BaseException], None] | None = None,
    ) -> UpdateInstaller | None:
        """Download the pending update, run its installer, and close the app.

        Returns the :class:`~services.update_installer.UpdateInstaller` driving
        the transfer so the caller can :meth:`~services.update_installer.UpdateInstaller.cancel`
        it, or ``None`` when the pending release carries nothing installable —
        which is not a failure, it is the release-page fallback's cue.

        The three callbacks divide by thread, and getting that wrong is the bug
        this docstring exists to prevent. ``on_progress`` is handed straight to
        the installer and therefore fires **on the download thread**: it must not
        touch a widget without marshalling first. ``on_launched`` and
        ``on_failure`` come back through :class:`~utils.background_worker.BackgroundWorker`,
        which routes them through ``wx.CallAfter``, so those two are on the UI
        thread.

        There is no success callback beyond ``on_launched`` because there is no
        "after" to report to: the installer is already running, and the next
        thing this method does is close the window the caller lives in.
        """
        from services.update_installer import (
            ReleaseUnavailable,
            UpdateInstaller,
            can_auto_update,
        )

        info = self._available_update
        if info is None or not can_auto_update(info):
            logger.info("No in-app update to apply — release page fallback applies")
            return None

        installer = UpdateInstaller(info)
        # Held so shutdown() can cancel a transfer the user walked away from by
        # closing the app; see LifecycleMixin.shutdown.
        self._update_installer = installer

        def _fail(exc: BaseException) -> None:
            self._update_installer = None
            if isinstance(exc, ReleaseUnavailable):
                # Adopt what the re-check below found (or None, when the answer
                # is that nothing newer is published any more). Done here rather
                # than on the worker thread that produced it because everything
                # else reads this attribute from the UI thread, and _fail is
                # already on it -- BackgroundWorker routes on_error through
                # wx.CallAfter.
                self._available_update = exc.replacement
            logger.info(f"In-app update failed: {type(exc).__name__}: {exc}")
            if on_failure is not None:
                on_failure(exc)

        def _download() -> Path:
            try:
                return installer.download(on_progress)
            except ReleaseUnavailable as exc:
                raise self._recheck_after_missing_release(info, exc) from exc

        def _on_downloaded(_path: Path) -> None:
            self._update_installer = None
            try:
                installer.launch()
            except Exception as exc:
                # Nothing started, so the 175 MB in temp is now litter rather
                # than a running process's working directory — the one moment
                # after a successful download where cleanup() is still allowed.
                installer.cleanup()
                _fail(exc)
                return
            if on_launched is not None:
                on_launched()
            self._exit_for_update()

        self._worker.submit(_download, on_success=_on_downloaded, on_error=_fail)
        return installer

    def _recheck_after_missing_release(
        self, missing: UpdateInfo, exc: ReleaseUnavailable
    ) -> ReleaseUnavailable:
        """Ask GitHub again after being sent to a release that is gone.

        The user clicked update on an answer that was true when it was cached
        and is not any more: the release was unpublished, or pruned by
        ``scripts/prune_releases.py``, between the check and the click. Retrying
        the download cannot fix that, and neither can waiting for the stamp to
        expire on its own — up to a day of every launch offering the same dead
        release.

        So the stamp is dropped and one fresh check is made, and the result is
        attached to the error the caller is about to see. Returns that error
        rather than raising it, so the ``raise ... from exc`` at the call site
        reads as the single place the failure leaves this method.

        Runs on the download thread (it is called from inside ``_download``),
        which is where :meth:`UpdateService.check` belongs anyway — it is the
        same network-and-disk work the background check does. It cannot raise:
        ``check`` absorbs its own failures and returns ``None``, which lands
        here as "nothing to offer instead" and is the honest answer when the
        re-check could not be made either.
        """
        from services.update_installer import ReleaseUnavailable
        from services.update_service import get_update_service

        logger.info(
            f"Update: v{missing.version} is no longer published; "
            "dropping the cached check and asking again"
        )
        service = get_update_service()
        service.forget()
        replacement = service.check()
        if replacement is None:
            logger.info("Update: no newer release is published any more")
        else:
            logger.info(f"Update: v{replacement.version} is the newest release now")
        return ReleaseUnavailable(str(exc), replacement=replacement)

    def _exit_for_update(self) -> None:
        """Close the app so the installer can replace the files it has open.

        Through the frame's ordinary close path — ``AppFrame.on_close`` stops the
        timers, saves the window settings, closes the child windows and calls
        :meth:`~controllers.app_controller.lifecycle.LifecycleMixin.shutdown` —
        because an update must not be the one exit that skips saving the session.
        ``Close(True)`` rather than ``Close()``: the installer is already running
        and there is no longer a state in which staying open is correct, so the
        close is not offered for veto.
        """
        frame = self.frame
        if frame is None:
            # No frame to close (headless, or the update was applied before one
            # was attached). The installer is running either way; leaving the
            # process up would only have it overwritten underneath itself.
            logger.warning("Update installer launched with no frame to close")
            return
        logger.info("Update installer launched — closing MTGO Tools")
        frame.Close(True)
