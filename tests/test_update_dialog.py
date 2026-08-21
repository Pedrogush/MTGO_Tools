"""The in-app update dialog: the copy it picks, and the routing that opens it.

Split by what actually needs a running toolkit. The message mapping and the byte
formatting are pure functions and are tested as such; the phase swap and Cancel
are tested on a real dialog because "the app is still usable afterwards" is a
claim about widgets. Nothing here downloads anything: the controller stub stands
in for :meth:`~controllers.app_controller.updates.UpdateCheckMixin.apply_available_update`,
whose own behaviour is pinned in ``tests/test_update_check_mixin.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from services.update_installer import (
    ChecksumMismatch,
    ChecksumUnavailable,
    DownloadFailed,
    LaunchBlocked,
    LaunchFailed,
    UpdateCancelled,
    UpdateNotDownloadable,
)
from services.update_service import UpdateInfo
from utils.i18n import MESSAGES
from widgets.dialogs.update_dialog.properties import (
    PHASE_CONFIRM,
    PHASE_ERROR,
    PHASE_PROGRESS,
    failure_message,
    format_bytes,
    progress_text,
)

wx = pytest.importorskip("wx")

from widgets.dialogs.update_dialog import UpdateDialog  # noqa: E402

APPLICABLE = UpdateInfo(
    version="1.0.3",
    release_url="https://example.test/release",
    installer_url="https://example.test/MTGOTools_Setup_v1.0.3.exe",
    checksum_url="https://example.test/MTGOTools_Setup_v1.0.3.exe.sha256",
    installer_name="MTGOTools_Setup_v1.0.3.exe",
)
BROWSER_ONLY = UpdateInfo(version="1.0.3", release_url="https://example.test/release")


# ---------------------------------------------------------------------------
# The copy
# ---------------------------------------------------------------------------


def test_every_failure_gets_its_own_sentence() -> None:
    """The installer types its failures so the user can act on them differently.

    A mapping that collapsed two of them would undo that at the last step, so
    this asserts distinctness rather than any particular wording.
    """
    messages = [
        failure_message(exc)
        for exc in (
            DownloadFailed("connection reset"),
            ChecksumUnavailable("sidecar 404"),
            ChecksumMismatch("integrity check failed"),
            LaunchFailed("access denied"),
            UpdateNotDownloadable("no installer asset"),
            RuntimeError("something else entirely"),
        )
    ]
    assert len(set(messages)) == len(messages)
    assert not any(message.startswith("app.update.") for message in messages), (
        "a missing i18n key falls back to the key itself, which would ship the "
        f"key name as the message: {messages}"
    )


def test_a_blocked_launch_reads_differently_per_reason_and_in_both_locales() -> None:
    """Three ways Windows can refuse the installer, three different fixes.

    Collapsing them would tell somebody whose antivirus quarantined the file to
    go turn off Smart App Control. The locale sweep is not decoration: the whole
    message here *is* the explanation (unlike the other failures, which carry an
    English detail inside translated framing), so an untranslated key would
    leave a pt-BR user with nothing readable -- and ``t`` falls back to the key
    name, which would ship "app.update.error..." as the message.
    """
    reasons = ("app_control", "group_policy", "antivirus")
    messages = [failure_message(LaunchBlocked("blocked", reason=r)) for r in reasons]
    assert len(set(messages)) == len(reasons)
    assert not any(m.startswith("app.update.") for m in messages)
    for locale, table in MESSAGES.items():
        for reason in reasons:
            key = f"app.update.error.launch_blocked.{reason}"
            assert key in table, f"{key} missing from {locale}"
    # It subclasses LaunchFailed; the generic launch copy must not shadow it.
    assert failure_message(LaunchBlocked("blocked", reason="app_control")) != failure_message(
        LaunchFailed("access denied")
    )


def test_an_unknown_block_reason_falls_back_instead_of_shipping_a_key() -> None:
    """A reason token added upstream without copy must degrade, not leak."""
    message = failure_message(LaunchBlocked("blocked", reason="something_new"))
    assert not message.startswith("app.update.")
    assert "blocked" in message


def test_a_checksum_mismatch_reads_as_a_refusal_rather_than_an_error() -> None:
    """The user is being protected, not merely told something went wrong.

    The file was deleted and nothing was executed; a message that read like a
    generic failure would leave them retrying it, or hunting for the file in
    %TEMP% to run by hand.
    """
    for locale, table in MESSAGES.items():
        message = table["app.update.error.checksum_mismatch"]
        assert "MTGO Tools" in message, locale
        assert "checksum" in message or "soma de verificação" in message, locale
        # Both locales say what became of the download and what did not happen.
        assert "delet" in message or "apagou" in message, locale


def test_a_failure_message_carries_the_underlying_detail() -> None:
    assert "connection reset" in failure_message(DownloadFailed("connection reset"))


def test_sizes_are_readable_at_every_magnitude() -> None:
    assert format_bytes(512) == "512 B"
    assert format_bytes(80 * 1024) == "80 KB"
    assert format_bytes(175 * 1024 * 1024) == "175.0 MB"


def test_progress_text_survives_a_missing_content_length() -> None:
    """``total`` is ``None`` for a chunked response; there is no percentage then.

    The bytes are still spelled out, because an indeterminate bar on its own
    says only that something is happening.
    """
    known = progress_text(90 * 1024 * 1024, 175 * 1024 * 1024)
    assert "90.0 MB" in known and "175.0 MB" in known and "51" in known

    unknown = progress_text(3 * 1024 * 1024, None)
    assert "3.0 MB" in unknown
    assert "%" not in unknown


# ---------------------------------------------------------------------------
# The routing that opens it
# ---------------------------------------------------------------------------


class _RoutingFrame:
    """Just enough ``self`` for ``AppFrameHandlersMixin._open_update``."""

    def __init__(self, update: UpdateInfo | None) -> None:
        self.controller = type("_C", (), {"get_available_update": lambda _self: update})()
        self.release_pages = 0

    def _open_release_page(self) -> None:
        self.release_pages += 1


def _route(monkeypatch, update: UpdateInfo | None) -> tuple[_RoutingFrame, list[Any]]:
    from widgets.frames.app_frame.handlers import app_frame as handlers

    opened: list[Any] = []
    monkeypatch.setattr(handlers, "show_update_dialog", lambda *args: opened.append(args) or None)
    frame = _RoutingFrame(update)
    handlers.AppFrameHandlersMixin._open_update(frame)
    return frame, opened


def test_an_installable_release_opens_the_updater(monkeypatch) -> None:
    frame, opened = _route(monkeypatch, APPLICABLE)
    assert len(opened) == 1
    assert opened[0][2] is APPLICABLE
    assert frame.release_pages == 0


def test_a_release_without_an_installer_still_reaches_the_user(monkeypatch) -> None:
    """The fallback is the whole reason ``can_auto_update`` returns a bool.

    A release with no installer/sidecar pair is a real update the user should
    still be told about — the browser hop this feature replaced stays valid for
    it, and hiding the update would be the one wrong answer.
    """
    frame, opened = _route(monkeypatch, BROWSER_ONLY)
    assert opened == []
    assert frame.release_pages == 1


def test_nothing_happens_when_there_is_no_update(monkeypatch) -> None:
    frame, opened = _route(monkeypatch, None)
    assert opened == []
    assert frame.release_pages == 0


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


class _StubInstallerHandle:
    def __init__(self) -> None:
        self.cancelled = 0

    def cancel(self) -> None:
        self.cancelled += 1


class _StubController:
    """Records the apply, hands back a cancellable handle, downloads nothing."""

    def __init__(self, *, handle: _StubInstallerHandle | None) -> None:
        self.handle = handle
        self.calls: list[dict[str, Any]] = []

    def apply_available_update(self, **kwargs: Any) -> _StubInstallerHandle | None:
        self.calls.append(kwargs)
        return self.handle


@pytest.fixture(scope="module")
def app() -> Iterator[object]:
    yield wx.App.Get() or wx.App()


@pytest.fixture
def parent(app: object) -> Iterator[Any]:
    frame = wx.Frame(None)
    yield frame
    frame.Destroy()


def _dialog(parent: Any, controller: _StubController) -> UpdateDialog:
    return UpdateDialog(parent, controller, APPLICABLE)


def test_the_dialog_opens_on_the_confirmation(parent: Any) -> None:
    dialog = _dialog(parent, _StubController(handle=_StubInstallerHandle()))
    try:
        assert dialog._phase == PHASE_CONFIRM
        assert dialog._update_btn.IsShown() and dialog._later_btn.IsShown()
        # The release notes stay reachable — the affordance the browser hop had.
        assert dialog._notes_btn.IsShown()
        assert not dialog._gauge.IsShown() and not dialog._cancel_btn.IsShown()
    finally:
        dialog.Destroy()


def test_confirming_starts_the_download_and_swaps_to_the_bar(parent: Any) -> None:
    controller = _StubController(handle=_StubInstallerHandle())
    dialog = _dialog(parent, controller)
    try:
        dialog._on_update_clicked(None)

        assert dialog._phase == PHASE_PROGRESS
        assert dialog._gauge.IsShown() and dialog._cancel_btn.IsShown()
        assert not dialog._update_btn.IsShown()
        assert len(controller.calls) == 1
        # The download is the controller's worker, not this thread.
        assert set(controller.calls[0]) == {"on_progress", "on_launched", "on_failure"}
    finally:
        dialog.Destroy()


def test_the_bar_tracks_a_known_total_and_pulses_without_one(parent: Any) -> None:
    dialog = _dialog(parent, _StubController(handle=_StubInstallerHandle()))
    try:
        dialog._on_update_clicked(None)
        dialog._render_progress(90 * 1024 * 1024, 175 * 1024 * 1024)
        assert dialog._gauge.GetValue() == pytest.approx(514, abs=2)
        assert "90.0 MB" in dialog._status.GetLabel()

        # No total: the value must not be moved at all (it would be a lie), and
        # the byte count carries the report instead.
        before = dialog._gauge.GetValue()
        dialog._render_progress(120 * 1024 * 1024, None)
        assert dialog._gauge.GetValue() == before
        assert "120.0 MB" in dialog._status.GetLabel()
    finally:
        dialog.Destroy()


def test_progress_ticks_that_change_nothing_never_reach_the_ui(parent: Any) -> None:
    """~700 callbacks arrive from the download thread for one 175 MB transfer.

    Also pins the marshalling itself: ``_on_progress`` runs on that thread and
    may not touch a widget, so what it does is queue a UI-thread call — which is
    why the ticks only show up here after the queue has been drained.
    """
    dialog = _dialog(parent, _StubController(handle=_StubInstallerHandle()))
    try:
        marshalled: list[tuple[int, int | None]] = []
        dialog._render_progress = lambda done, total: marshalled.append((done, total))
        total = 175 * 1024 * 1024

        # The opening tick always renders: it is what puts the size on screen
        # before the first byte arrives.
        dialog._on_progress(0, total)
        wx.YieldIfNeeded()
        assert marshalled == [(0, total)]

        for chunk in range(1, 40):
            dialog._on_progress(chunk * 1024, total)
        wx.YieldIfNeeded()
        assert marshalled == [(0, total)], "sub-permille ticks redraw nothing"

        dialog._on_progress(total // 2, total)
        wx.YieldIfNeeded()
        assert marshalled[-1] == (total // 2, total)
    finally:
        dialog.Destroy()


def test_cancel_stops_the_download_and_leaves_the_app_running(parent: Any) -> None:
    handle = _StubInstallerHandle()
    dialog = _dialog(parent, _StubController(handle=handle))
    try:
        dialog._on_update_clicked(None)
        dialog._on_cancel_clicked(None)

        assert handle.cancelled == 1
        # Cancellation lands between chunks, so the dialog says so rather than
        # vanishing mid-socket-read — and the button cannot be pressed twice.
        assert not dialog._cancel_btn.IsEnabled()
        assert dialog._status.GetLabel()
        assert bool(dialog) and bool(parent)

        # The UpdateCancelled that follows is not a failure to report.
        dialog._on_failure(UpdateCancelled("Update cancelled"))
        wx.YieldIfNeeded()
        assert not dialog
        assert bool(parent)
    finally:
        if dialog:
            dialog.Destroy()


def test_a_failure_replaces_the_bar_with_the_reason(parent: Any) -> None:
    dialog = _dialog(parent, _StubController(handle=_StubInstallerHandle()))
    try:
        dialog._on_update_clicked(None)
        dialog._on_failure(ChecksumMismatch("integrity check failed"))

        assert dialog._phase == PHASE_ERROR
        assert not dialog._gauge.IsShown() and not dialog._cancel_btn.IsShown()
        # Both ways out of a failure: read about it, or go and do it by hand.
        assert dialog._close_btn.IsShown() and dialog._notes_btn.IsShown()
        assert dialog._status.GetLabel()
    finally:
        dialog.Destroy()


def test_a_late_progress_tick_cannot_overwrite_the_handover_message(parent: Any) -> None:
    """The last thing on screen before the app exits must stay on screen.

    The queue ordering makes this unreachable today (every tick is queued before
    the completion callback is), so this pins the guard rather than a bug: if the
    chain ever changes, a stale byte counter replacing "Installing the update..."
    while the window closes is indistinguishable from a hang.
    """
    dialog = _dialog(parent, _StubController(handle=_StubInstallerHandle()))
    try:
        dialog._on_update_clicked(None)
        dialog._on_launched()
        handover = dialog._status.GetLabel()

        dialog._render_progress(90 * 1024 * 1024, 175 * 1024 * 1024)
        assert dialog._status.GetLabel() == handover

        # Same after a failure: the reason must not be replaced by a byte count.
        dialog._on_failure(DownloadFailed("connection reset"))
        reason = dialog._status.GetLabel()
        dialog._render_progress(120 * 1024 * 1024, 175 * 1024 * 1024)
        assert dialog._status.GetLabel() == reason
    finally:
        dialog.Destroy()


def test_a_release_that_stopped_being_installable_is_reported_not_hung(parent: Any) -> None:
    """``apply_available_update`` returning ``None`` must not leave a dead bar."""
    dialog = _dialog(parent, _StubController(handle=None))
    try:
        dialog._on_update_clicked(None)
        assert dialog._phase == PHASE_ERROR
        assert dialog._status.GetLabel()
    finally:
        dialog.Destroy()


def test_closing_the_window_cancels_whatever_is_still_downloading(parent: Any) -> None:
    handle = _StubInstallerHandle()
    dialog = _dialog(parent, _StubController(handle=handle))
    dialog._on_update_clicked(None)

    dialog.Close()
    wx.YieldIfNeeded()

    assert handle.cancelled == 1
    # Destroyed, not hidden: wxDialog's own close path ends in EndDialog, which
    # hides a modeless dialog and would leave it taking progress callbacks.
    assert not dialog
