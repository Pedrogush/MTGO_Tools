"""Phase names, byte formatting and failure copy for the update dialog.

Deliberately free of ``wx``: everything here is a pure function of an integer or
an exception, which is the part of this dialog worth testing on its own (see
``tests/test_update_dialog.py``). The mixin exists so the dialog can call them as
methods, matching the package shape of the other dialogs.
"""

from __future__ import annotations

from services.update_installer import (
    ChecksumMismatch,
    ChecksumUnavailable,
    DownloadFailed,
    LaunchFailed,
    UpdateNotDownloadable,
)
from utils.i18n import t

#: The dialog is one window with three faces rather than three windows: the
#: confirmation, the transfer it starts, and whatever stopped it are one
#: continuous action from the user's side, and re-opening a second window over
#: the first would lose that thread.
PHASE_CONFIRM = "confirm"
PHASE_PROGRESS = "progress"
PHASE_ERROR = "error"

_KIB = 1024
_MIB = 1024 * 1024

#: One entry per outcome :mod:`services.update_installer` distinguishes. The
#: point of that module typing its failures is lost if they all arrive here as
#: "the update failed", so the mapping is exhaustive and the generic key below
#: is reserved for exceptions that are not ``UpdateError`` at all.
#:
#: Ordered most-specific-first and matched with ``isinstance`` so a future
#: subclass of one of these still gets the closest message rather than falling
#: through to the generic one.
_FAILURE_KEYS: tuple[tuple[type[BaseException], str], ...] = (
    (ChecksumMismatch, "app.update.error.checksum_mismatch"),
    (ChecksumUnavailable, "app.update.error.checksum_unavailable"),
    (UpdateNotDownloadable, "app.update.error.unavailable"),
    (LaunchFailed, "app.update.error.launch"),
    (DownloadFailed, "app.update.error.download"),
)


def format_bytes(value: int) -> str:
    """A size a person can compare against their connection, not an exact count.

    Untranslated units: ``MB``/``KB``/``B`` are written the same way in both
    locales, and a size is the one thing in this dialog that must read
    identically in a bug report and on screen.
    """
    if value >= _MIB:
        return f"{value / _MIB:.1f} MB"
    if value >= _KIB:
        return f"{value / _KIB:.0f} KB"
    return f"{value} B"


def progress_text(done: int, total: int | None) -> str:
    """The line under the bar. ``total`` is ``None`` when the server sent no length.

    That case is not hypothetical padding — :meth:`UpdateInstaller.download`
    reports ``None`` for a chunked or compressed response — and it is the reason
    the bytes are spelled out here at all rather than left to the bar: an
    indeterminate gauge says "something is happening", and this says how much of
    it has happened.
    """
    if total:
        percent = min(100, done * 100 // total)
        return t(
            "app.update.progress.downloading",
            done=format_bytes(done),
            total=format_bytes(total),
            percent=percent,
        )
    return t("app.update.progress.downloading_unknown", done=format_bytes(done))


def failure_message(exc: BaseException) -> str:
    """The sentence shown in place of the progress bar when the update stops.

    Every one of them ends by saying nothing was installed, because the state the
    user actually needs to know after a failed update is what happened to the app
    they are still running -- and a checksum mismatch says *why* the file was
    thrown away, since "MTGO Tools refused to run this" is the outcome and not a
    generic error.
    """
    for kind, key in _FAILURE_KEYS:
        if isinstance(exc, kind):
            return t(key, error=str(exc))
    return t("app.update.error.generic", error=str(exc))


class UpdateDialogPropertiesMixin:
    """Formatting accessors for :class:`UpdateDialog`."""

    def _format_bytes(self, value: int) -> str:
        return format_bytes(value)

    def _progress_text(self, done: int, total: int | None) -> str:
        return progress_text(done, total)

    def _failure_message(self, exc: BaseException) -> str:
        return failure_message(exc)
