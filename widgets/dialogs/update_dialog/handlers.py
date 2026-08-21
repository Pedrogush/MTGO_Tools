"""Phase switching and the download's UI-thread plumbing for the update dialog."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

import wx
from loguru import logger

from services.update_installer import UpdateCancelled, UpdateInstaller, UpdateNotDownloadable
from utils.i18n import t
from widgets.dialogs.update_dialog.properties import (
    PHASE_CONFIRM,
    PHASE_ERROR,
    PHASE_PROGRESS,
)
from widgets.wx_layout import relayout

if TYPE_CHECKING:
    from controllers.app_controller import AppController
    from services.update_service import UpdateInfo

#: The gauge's integer range. Finer than 100 so the bar moves smoothly on a
#: 175 MB transfer instead of stepping once every ~1.8 MB.
GAUGE_RANGE = 1000

#: How much has to arrive before an *indeterminate* transfer redraws. With no
#: Content-Length there is no percentage to change, so this is what keeps the
#: byte counter from being rewritten once per 256 KB chunk.
INDETERMINATE_STEP_BYTES = 1024 * 1024

#: Which widgets each phase shows. Every other widget in the union is hidden, so
#: adding a widget to one phase cannot leave it visible in another.
_PHASE_WIDGETS: dict[str, tuple[str, ...]] = {
    PHASE_CONFIRM: ("_notes_btn", "_later_btn", "_update_btn"),
    PHASE_PROGRESS: ("_gauge", "_status", "_cancel_btn"),
    PHASE_ERROR: ("_status", "_notes_btn", "_close_btn"),
}
_ALL_PHASE_WIDGETS: tuple[str, ...] = tuple(
    sorted({name for names in _PHASE_WIDGETS.values() for name in names})
)


class UpdateDialogHandlersMixin:
    """Button handlers, phase swapping, and the bridge from the download thread.

    The download itself belongs to
    :meth:`controllers.app_controller.updates.UpdateCheckMixin.apply_available_update`
    -- this mixin only starts it, renders what it reports, and can stop it.
    """

    controller: AppController
    info: UpdateInfo
    _panel: wx.Panel
    _gauge: wx.Gauge
    _status: wx.StaticText
    _notes_btn: wx.Button
    _later_btn: wx.Button
    _update_btn: wx.Button
    _cancel_btn: wx.Button
    _close_btn: wx.Button
    _installer: UpdateInstaller | None
    _last_step: int
    _phase: str
    _wrap_width: int
    _accepting_progress: bool

    # ------------------------------------------------------------------ phases
    def _show_phase(self, phase: str) -> None:
        wanted = _PHASE_WIDGETS[phase]
        for name in _ALL_PHASE_WIDGETS:
            getattr(self, name).Show(name in wanted)
        self._phase = phase
        # Fit before the repaint: the window grows when the gauge appears and
        # shrinks again when a one-line status replaces the wrapped error, and a
        # relayout inside a stale client size lays the row out against the wrong
        # width.
        self.Fit()
        relayout(self._panel)

    def _set_status(self, text: str, *, wrap: bool = False) -> None:
        """Write the line under the bar.

        ``wrap`` is off for progress ticks and on for the failure copy: ``Wrap``
        rewrites the label with newlines in it, which is right for a paragraph
        and pure cost several hundred times over for a single line that cannot
        overflow.
        """
        self._status.SetLabel(text)
        if wrap:
            self._status.Wrap(self._wrap_width)

    # ------------------------------------------------------------------ buttons
    def _on_update_clicked(self, _event: wx.CommandEvent) -> None:
        self._accepting_progress = True
        self._show_phase(PHASE_PROGRESS)
        self._set_status(t("app.update.progress.starting"))
        # Nothing is known about the size until the first response header, so the
        # bar starts indeterminate rather than sitting at a fake 0%.
        self._gauge.Pulse()
        # Safe to assign after the call returns: the controller's callbacks come
        # back through wx.CallAfter, which cannot be dispatched until this
        # handler has returned to the event loop.
        self._installer = self.controller.apply_available_update(
            on_progress=self._on_progress,
            on_launched=self._on_launched,
            on_failure=self._on_failure,
        )
        if self._installer is None:
            # The frame checks can_auto_update before opening this dialog, so
            # reaching here means the pending update changed underneath us.
            # Report it rather than leaving a bar that will never move.
            self._on_failure(
                UpdateNotDownloadable(f"Release v{self.info.version} has no installer asset")
            )

    def _on_later_clicked(self, _event: wx.CommandEvent) -> None:
        self.Close()

    def _on_close_clicked(self, _event: wx.CommandEvent) -> None:
        self.Close()

    def _on_cancel_clicked(self, _event: wx.CommandEvent) -> None:
        # Cancellation is cooperative and lands between chunks, so the dialog
        # stays up saying so instead of vanishing while the socket read finishes.
        # The button is disabled rather than hidden: a second press has nothing
        # left to ask for, and stylize_button repaints a disabled button itself.
        self._cancel_btn.Enable(False)
        self._set_status(t("app.update.progress.cancelling"))
        if self._installer is not None:
            self._installer.cancel()

    def _on_release_notes_clicked(self, _event: wx.CommandEvent) -> None:
        try:
            webbrowser.open(self.info.release_url)
        except Exception as exc:  # pragma: no cover - depends on the desktop
            logger.warning(f"Unable to open release page {self.info.release_url!r}: {exc}")

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        # Escape is routed through Close() so it goes through the same
        # cancel-then-destroy path as the window button. wxDialog's own escape
        # handling ends in EndDialog, which *hides* a modeless dialog -- that
        # would leave a 175 MB download running with nothing on screen owning it.
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()

    def _on_close(self, event: wx.CloseEvent) -> None:
        # Destroy explicitly for the same reason: the default handler hides a
        # modeless dialog, and a hidden one would keep taking progress callbacks.
        self._accepting_progress = False
        installer = self._installer
        self._installer = None
        if installer is not None:
            installer.cancel()
        self.Destroy()

    # ------------------------------------------------- download-thread bridge
    def _on_progress(self, done: int, total: int | None) -> None:
        """Called by :class:`UpdateInstaller` **on the download thread**.

        Two things happen here and nothing else: the tick is thrown away unless
        it would change what is on screen, and what survives is marshalled onto
        the UI thread. A 175 MB transfer in 256 KB chunks is ~700 callbacks, and
        wx widgets may not be touched from this thread at all.
        """
        step = (done * GAUGE_RANGE // total) if total else (done // INDETERMINATE_STEP_BYTES)
        if step == self._last_step:
            return
        self._last_step = step
        wx.CallAfter(self._render_progress, done, total)

    def _render_progress(self, done: int, total: int | None) -> None:
        if not self:
            # The dialog was destroyed while this tick sat in the queue.
            # ``bool(widget)`` is the one liveness test that does not itself
            # raise -- see docs/WXMSW_BEHAVIOUR.md.
            return
        if not self._accepting_progress:
            # Defensive, not load-bearing: as the code stands today this cannot
            # fire. Every tick is queued with wx.CallAfter from inside
            # ``UpdateInstaller.download`` on the worker thread, the completion
            # callback is queued by BackgroundWorker only after download()
            # returns, and wx dispatches pending calls in order -- so the last
            # tick is always drained before ``_on_launched`` or ``_on_failure``
            # runs.
            #
            # It is here because that argument is about the *whole* chain
            # holding, and every link in it is somebody else's to change: a
            # retry loop that re-enters download(), a progress callback fired
            # from a second thread, or a future wx that coalesces CallAfters
            # would each turn a late tick into "Installing the update..." being
            # overwritten by a byte counter for a transfer that already
            # finished -- with the app about to exit and no way to tell the
            # difference from a hang. Two cheap lines beat re-deriving the
            # ordering argument every time one of those changes.
            return
        if total:
            self._gauge.SetValue(min(GAUGE_RANGE, done * GAUGE_RANGE // total))
        else:
            self._gauge.Pulse()
        self._set_status(self._progress_text(done, total))

    def _on_launched(self) -> None:
        """The installer is running; the app is about to close behind this."""
        if not self:
            return
        self._accepting_progress = False
        self._installer = None
        self._cancel_btn.Enable(False)
        self._gauge.SetValue(GAUGE_RANGE)
        self._set_status(t("app.update.progress.installing"))
        # The frame's close is next in this same callback, and a deferred repaint
        # would never be painted -- so flush this last message to the screen.
        self._panel.Update()

    def _on_failure(self, exc: BaseException) -> None:
        if not self:
            return
        self._accepting_progress = False
        self._installer = None
        if isinstance(exc, UpdateCancelled):
            # The user asked for this; there is nothing to tell them about it.
            self.Close()
            return
        # Not logged here: the controller already logged this exception on its
        # way out, and a second line would only make the log look like two
        # failures.
        self._show_phase(PHASE_ERROR)
        self._set_status(self._failure_message(exc), wrap=True)
