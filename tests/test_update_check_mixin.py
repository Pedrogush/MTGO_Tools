"""Tests for the controller-side wiring of the update check (issue #142).

The mixin is exercised against a stub ``self`` rather than a real
``AppController``: the whole point of the mixin split is that it only touches
the handful of attributes declared on ``AppControllerProto``, and standing up
the full controller would drag in services and wx for no added coverage.
"""

from __future__ import annotations

from typing import Any

from controllers.app_controller.updates import UpdateCheckMixin
from services.update_service import UpdateInfo


class _StubWorker:
    """Runs submitted work inline so the test doesn't have to join a thread."""

    def __init__(self) -> None:
        self.submitted = 0

    def submit(self, func, *args, on_success=None, on_error=None, **kwargs) -> None:
        self.submitted += 1
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - mirrors BackgroundWorker
            if on_error:
                on_error(exc)
            return
        if on_success:
            on_success(result)


class _StubCallbacks:
    def __init__(self) -> None:
        self.updates: list[UpdateInfo] = []

    def on_update_available(self, info: UpdateInfo) -> None:
        self.updates.append(info)


class _Controller(UpdateCheckMixin):
    def __init__(self, *, enabled: bool = True, result: UpdateInfo | None = None) -> None:
        self._enabled = enabled
        self._result = result
        self._worker = _StubWorker()
        self._ui_callbacks = _StubCallbacks()
        self._available_update: UpdateInfo | None = None

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
