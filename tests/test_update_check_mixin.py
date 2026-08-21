"""Tests for the controller-side wiring of the update check (issue #142).

The mixin is exercised against a stub ``self`` rather than a real
``AppController``: the whole point of the mixin split is that it only touches
the handful of attributes declared on ``AppControllerProto``, and standing up
the full controller would drag in services and wx for no added coverage.

The second half covers applying an update, where the stub ``self`` earns its
keep twice over: the real path ends by closing the main frame, so a test that
built a real controller would be testing whether wx can shut an app down.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from controllers.app_controller.updates import UpdateCheckMixin
from services.update_installer import (
    ChecksumMismatch,
    DownloadFailed,
    LaunchFailed,
    UpdateCancelled,
)
from services.update_service import UpdateInfo


class _StubWorker:
    """Runs submitted work inline so the test doesn't have to join a thread."""

    def __init__(self) -> None:
        self.submitted = 0
        self.shutdowns = 0

    def submit(self, func, *args, on_success=None, on_error=None, **kwargs) -> None:
        self.submitted += 1
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            if on_error:
                on_error(exc)
            return
        if on_success:
            on_success(result)

    def shutdown(self, timeout: float = 0.0) -> None:
        self.shutdowns += 1


class _StubCallbacks:
    def __init__(self) -> None:
        self.updates: list[UpdateInfo] = []

    def on_update_available(self, info: UpdateInfo) -> None:
        self.updates.append(info)


class _StubFrame:
    """Records the close the update path is supposed to go through."""

    def __init__(self) -> None:
        self.closes: list[bool] = []

    def Close(self, force: bool = False) -> bool:  # noqa: N802 - wx spelling
        self.closes.append(force)
        return True


class _Controller(UpdateCheckMixin):
    def __init__(self, *, enabled: bool = True, result: UpdateInfo | None = None) -> None:
        self._enabled = enabled
        self._result = result
        self._worker = _StubWorker()
        self._ui_callbacks = _StubCallbacks()
        self._available_update: UpdateInfo | None = None
        self._update_installer = None
        self.frame = _StubFrame()

    def get_update_check_enabled(self) -> bool:
        return self._enabled


def _patch_service(monkeypatch, result: UpdateInfo | None) -> dict[str, Any]:
    """Stub the service singleton and record whether ``check()`` was reached."""
    import services.update_service as update_service

    seen = {"checks": 0}

    class _StubService:
        def check(self) -> UpdateInfo | None:
            seen["checks"] += 1
            return result

    monkeypatch.setattr(update_service, "get_update_service", lambda: _StubService())
    return seen


def test_an_available_update_reaches_the_ui(monkeypatch) -> None:
    info = UpdateInfo(version="1.0.3", release_url="https://example.test/release")
    _patch_service(monkeypatch, info)
    controller = _Controller()

    controller.check_for_update()

    assert controller._ui_callbacks.updates == [info]
    assert controller.get_available_update() == info


def test_no_update_means_the_ui_is_never_touched(monkeypatch) -> None:
    _patch_service(monkeypatch, None)
    controller = _Controller()

    controller.check_for_update()

    assert controller._ui_callbacks.updates == []
    assert controller.get_available_update() is None


def test_the_disable_setting_prevents_the_check_entirely(monkeypatch) -> None:
    seen = _patch_service(monkeypatch, UpdateInfo(version="9.9.9", release_url="https://x.test"))
    controller = _Controller(enabled=False)

    controller.check_for_update()

    # Not merely "no UI notification" — no background work and no request.
    assert controller._worker.submitted == 0
    assert seen["checks"] == 0
    assert controller.get_available_update() is None


def test_a_headless_controller_still_records_the_update(monkeypatch) -> None:
    # run_initial_loads can fire before a frame is attached; the result must not
    # be dropped just because there is nothing to notify yet.
    info = UpdateInfo(version="1.0.3", release_url="https://example.test/release")
    _patch_service(monkeypatch, info)
    controller = _Controller()
    controller._ui_callbacks = None

    controller.check_for_update()

    assert controller.get_available_update() == info


def test_an_unexpected_failure_is_swallowed(monkeypatch) -> None:
    import services.update_service as update_service

    class _ExplodingService:
        def check(self) -> UpdateInfo | None:
            raise RuntimeError("boom")

    monkeypatch.setattr(update_service, "get_update_service", lambda: _ExplodingService())
    controller = _Controller()

    controller.check_for_update()

    assert controller.get_available_update() is None


# ---------------------------------------------------------------------------
# Applying an update
# ---------------------------------------------------------------------------

APPLICABLE = UpdateInfo(
    version="1.0.3",
    release_url="https://example.test/release",
    installer_url="https://example.test/MTGOTools_Setup_v1.0.3.exe",
    checksum_url="https://example.test/MTGOTools_Setup_v1.0.3.exe.sha256",
    installer_name="MTGOTools_Setup_v1.0.3.exe",
)


class _StubInstaller:
    """The real installer's surface, minus the network and the subprocess."""

    def __init__(
        self,
        info: UpdateInfo,
        *,
        download_error: Exception | None = None,
        launch_error: Exception | None = None,
        ticks: tuple[tuple[int, int | None], ...] = (),
    ) -> None:
        self.info = info
        self.download_error = download_error
        self.launch_error = launch_error
        self.ticks = ticks
        self.launched = 0
        self.cancelled = 0
        self.cleaned = 0

    def download(self, progress=None) -> Path:
        for done, total in self.ticks:
            if progress is not None:
                progress(done, total)
        if self.download_error is not None:
            raise self.download_error
        return Path("MTGOTools_Setup_v1.0.3.exe")

    def launch(self) -> None:
        self.launched += 1
        if self.launch_error is not None:
            raise self.launch_error

    def cancel(self) -> None:
        self.cancelled += 1

    def cleanup(self) -> None:
        self.cleaned += 1


class _Outcome:
    """Whatever the caller (the dialog, in production) was told."""

    def __init__(self) -> None:
        self.progress: list[tuple[int, int | None]] = []
        self.launched = 0
        self.failures: list[BaseException] = []

    def on_progress(self, done: int, total: int | None) -> None:
        self.progress.append((done, total))

    def on_launched(self) -> None:
        self.launched += 1

    def on_failure(self, exc: BaseException) -> None:
        self.failures.append(exc)


def _patch_installer(monkeypatch, **kwargs: Any) -> list[_StubInstaller]:
    """Swap the installer class for a stub factory; returns what it builds."""
    import services.update_installer as update_installer

    built: list[_StubInstaller] = []

    def _factory(info: UpdateInfo, **_ignored: Any) -> _StubInstaller:
        installer = _StubInstaller(info, **kwargs)
        built.append(installer)
        return installer

    monkeypatch.setattr(update_installer, "UpdateInstaller", _factory)
    return built


def _apply(controller: _Controller, outcome: _Outcome):
    return controller.apply_available_update(
        on_progress=outcome.on_progress,
        on_launched=outcome.on_launched,
        on_failure=outcome.on_failure,
    )


def test_applying_an_update_launches_the_installer_and_closes_the_app(monkeypatch) -> None:
    built = _patch_installer(monkeypatch)
    controller = _Controller()
    controller._available_update = APPLICABLE
    outcome = _Outcome()

    handle = _apply(controller, outcome)

    assert handle is built[0]
    assert built[0].launched == 1
    assert outcome.launched == 1
    assert outcome.failures == []
    # Forced, and through the frame's own close: an update must not be the one
    # exit that skips saving the session.
    assert controller.frame.closes == [True]
    assert controller._update_installer is None


def test_progress_reaches_the_caller_including_an_unknown_total(monkeypatch) -> None:
    # The opening (0, total) tick and a None total are both contractual — the
    # dialog's bar has to start indeterminate rather than assume a percentage.
    _patch_installer(monkeypatch, ticks=((0, None), (512, None)))
    controller = _Controller()
    controller._available_update = APPLICABLE
    outcome = _Outcome()

    _apply(controller, outcome)

    assert outcome.progress == [(0, None), (512, None)]


def test_a_release_with_no_installer_assets_is_never_downloaded(monkeypatch) -> None:
    # The release-page fallback's cue. Not a failure: nothing is reported to the
    # caller and no work is submitted, the caller just gets None back.
    built = _patch_installer(monkeypatch)
    controller = _Controller()
    controller._available_update = UpdateInfo(version="1.0.3", release_url="https://x.test")
    outcome = _Outcome()

    assert _apply(controller, outcome) is None
    assert built == []
    assert controller._worker.submitted == 0
    assert outcome.failures == []
    assert controller.frame.closes == []


def test_nothing_to_apply_when_no_update_was_found(monkeypatch) -> None:
    built = _patch_installer(monkeypatch)
    controller = _Controller()
    outcome = _Outcome()

    assert _apply(controller, outcome) is None
    assert built == []


@pytest.mark.parametrize(
    "error",
    [
        DownloadFailed("the download failed: connection reset"),
        ChecksumMismatch("The downloaded installer failed its integrity check"),
    ],
)
def test_a_download_failure_is_reported_and_the_app_stays_up(monkeypatch, error) -> None:
    # The distinction between these two lives in the message the dialog picks,
    # so what the controller owes both of them is the same: the exact exception
    # (not a string), nothing launched, and an app still running.
    built = _patch_installer(monkeypatch, download_error=error)
    controller = _Controller()
    controller._available_update = APPLICABLE
    outcome = _Outcome()

    _apply(controller, outcome)

    assert outcome.failures == [error]
    assert built[0].launched == 0
    assert outcome.launched == 0
    assert controller.frame.closes == []
    assert controller._update_installer is None


def test_cancelling_leaves_the_app_running(monkeypatch) -> None:
    # UpdateCancelled arrives by the same route as a real failure, and the app
    # must be indistinguishable afterwards from one that never started.
    cancelled = UpdateCancelled("Update cancelled")
    built = _patch_installer(monkeypatch, download_error=cancelled)
    controller = _Controller()
    controller._available_update = APPLICABLE
    outcome = _Outcome()

    handle = _apply(controller, outcome)
    handle.cancel()

    assert outcome.failures == [cancelled]
    assert built[0].cancelled == 1
    assert built[0].launched == 0
    assert controller.frame.closes == []
    assert controller.get_available_update() == APPLICABLE


def test_a_launch_failure_discards_the_installer_and_keeps_the_app_up(monkeypatch) -> None:
    error = LaunchFailed("Could not start the installer")
    built = _patch_installer(monkeypatch, launch_error=error)
    controller = _Controller()
    controller._available_update = APPLICABLE
    outcome = _Outcome()

    _apply(controller, outcome)

    assert outcome.failures == [error]
    assert outcome.launched == 0
    # Nothing started, so the download is litter rather than a running process's
    # working directory — this is the one post-download cleanup that is allowed.
    assert built[0].cleaned == 1
    assert controller.frame.closes == []


def test_the_app_still_exits_when_there_is_no_frame_to_close(monkeypatch) -> None:
    # The installer is running either way; staying up would only mean being
    # overwritten underneath ourselves.
    built = _patch_installer(monkeypatch)
    controller = _Controller()
    controller._available_update = APPLICABLE
    controller.frame = None
    outcome = _Outcome()

    _apply(controller, outcome)

    assert built[0].launched == 1
    assert outcome.launched == 1


def test_quitting_the_app_cancels_a_download_still_in_flight() -> None:
    """``shutdown`` joins every worker thread; a 175 MB transfer would hold it.

    Nothing else asks the download to stop — the dialog's Cancel is the user's
    route and closing the whole app bypasses it — so the handle the controller
    keeps is the only thing standing between "the user quit" and a ten-second
    hang on the way out.
    """
    from controllers.app_controller.lifecycle import LifecycleMixin

    class _Shutdownable(LifecycleMixin):
        def __init__(self) -> None:
            self._worker = _StubWorker()
            self.image_service = type("_S", (), {"shutdown": lambda self: None})()
            self._update_installer = _StubInstaller(APPLICABLE)

    controller = _Shutdownable()
    installer = controller._update_installer

    controller.shutdown(timeout=0.0)

    assert installer.cancelled == 1
    assert controller._worker.shutdowns == 1
