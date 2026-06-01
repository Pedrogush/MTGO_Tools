"""Headless tests for TimerAlertFrame bridge watcher lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import widgets.frames.timer_alert as timer_alert

TimerAlertFrame = timer_alert.TimerAlertFrame


def _make_frame() -> TimerAlertFrame:
    frame = TimerAlertFrame.__new__(TimerAlertFrame)
    frame.WATCH_INTERVAL_MS = 750
    frame.WATCH_RETRY_DELAY_MS = 5000
    frame._watcher = None
    frame._watch_start_pending = False
    frame._closed = False
    frame._watch_timer = MagicMock()
    frame._monitor_timer = MagicMock()
    frame._repeat_timer = MagicMock()
    frame._set_status = MagicMock()
    frame.controller = MagicMock()
    return frame


def _make_fake_thread(threads: list[object]):
    class FakeThread:
        def __init__(self, *, target, daemon: bool, args: tuple[object, ...] = ()) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.started = False
            threads.append(self)

        def start(self) -> None:
            self.started = True

    return FakeThread


def _patch_call_after(
    monkeypatch, calls: list[tuple[object, tuple[object, ...], dict[str, object]]]
):
    monkeypatch.setattr(
        timer_alert.wx,
        "CallAfter",
        lambda func, *args, **kwargs: calls.append((func, args, kwargs)),
    )


def test_start_watch_loop_runs_bridge_start_in_background(monkeypatch) -> None:
    frame = _make_frame()
    watcher = MagicMock()
    start_watch_calls: list[int] = []
    call_after_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []
    threads: list[object] = []

    def fake_start_watch(*, interval_ms: int):
        start_watch_calls.append(interval_ms)
        return watcher

    frame.controller.mtgo_bridge_service.start_watch = fake_start_watch
    _patch_call_after(monkeypatch, call_after_calls)
    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))

    TimerAlertFrame._start_watch_loop(frame)

    assert frame._watch_start_pending is True
    assert start_watch_calls == []
    assert len(threads) == 1
    assert threads[0].started is True
    assert threads[0].daemon is True

    threads[0].target(*threads[0].args)

    assert start_watch_calls == [frame.WATCH_INTERVAL_MS]
    assert call_after_calls == [(frame._complete_watch_start, (watcher,), {})]

    # Medium finding: the success target was scheduled but never invoked, so its
    # effects (clearing the pending flag, storing the watcher, starting the
    # watch timer) went unverified. Invoke it and assert the outcome.
    TimerAlertFrame._complete_watch_start(frame, watcher)

    assert frame._watcher is watcher
    assert frame._watch_start_pending is False
    frame._watch_timer.Start.assert_called_once_with(frame.WATCH_INTERVAL_MS)


def test_on_close_stops_existing_watcher_in_background(monkeypatch) -> None:
    frame = _make_frame()
    watcher = MagicMock()
    frame._watcher = watcher
    frame._watch_timer.IsRunning.return_value = True
    frame._monitor_timer.IsRunning.return_value = True
    frame._repeat_timer.IsRunning.return_value = True
    threads: list[object] = []

    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))
    event = MagicMock()

    TimerAlertFrame.on_close(frame, event)

    assert frame._closed is True
    assert frame._watcher is None
    frame._watch_timer.Stop.assert_called_once_with()
    frame._monitor_timer.Stop.assert_called_once_with()
    frame._repeat_timer.Stop.assert_called_once_with()
    watcher.stop.assert_not_called()
    assert len(threads) == 1
    assert threads[0].started is True
    assert threads[0].daemon is True

    threads[0].target(*threads[0].args)

    watcher.stop.assert_called_once_with()
    event.Skip.assert_called_once_with()


@pytest.mark.parametrize(
    ("status_key", "exc"),
    [
        ("timer.status.bridge_missing", FileNotFoundError("bridge.exe")),
        ("timer.status.bridge_error", RuntimeError("boom")),
    ],
)
def test_watch_start_worker_schedules_failure_handler(monkeypatch, status_key, exc) -> None:
    """A FileNotFoundError / generic Exception in start_watch schedules the
    failure handler with the right status key and exception, off the main thread.
    """
    frame = _make_frame()
    call_after_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def fake_start_watch(*, interval_ms: int):
        raise exc

    frame.controller.mtgo_bridge_service.start_watch = fake_start_watch
    _patch_call_after(monkeypatch, call_after_calls)

    TimerAlertFrame._watch_start_worker(frame)

    assert call_after_calls == [(frame._handle_watch_start_failure, (status_key, exc), {})]


def test_watch_start_worker_skips_failure_handler_when_closed(monkeypatch) -> None:
    """If the frame closed during the failed start, no handler is scheduled."""
    frame = _make_frame()
    frame._closed = True
    call_after_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def fake_start_watch(*, interval_ms: int):
        raise FileNotFoundError("bridge.exe")

    frame.controller.mtgo_bridge_service.start_watch = fake_start_watch
    _patch_call_after(monkeypatch, call_after_calls)

    TimerAlertFrame._watch_start_worker(frame)

    assert call_after_calls == []


@pytest.mark.parametrize(
    ("status_key", "expected_kwargs"),
    [
        ("timer.status.bridge_missing", {}),
        ("timer.status.bridge_error", {"error": "passed-error"}),
    ],
)
def test_handle_watch_start_failure_sets_status_and_schedules_retry(
    monkeypatch, status_key, expected_kwargs
) -> None:
    """The failure handler clears the pending flag, surfaces the status, and
    schedules a retry of the watch loop after WATCH_RETRY_DELAY_MS.
    """
    frame = _make_frame()
    frame._watch_start_pending = True
    error = "passed-error"
    call_later_calls: list[tuple[int, object]] = []
    monkeypatch.setattr(
        timer_alert.wx,
        "CallLater",
        lambda delay, func, *a, **k: call_later_calls.append((delay, func)),
    )

    TimerAlertFrame._handle_watch_start_failure(frame, status_key, error)

    assert frame._watch_start_pending is False
    if expected_kwargs:
        frame._set_status.assert_called_once_with(status_key, error=error)
    else:
        frame._set_status.assert_called_once_with(status_key)
    assert call_later_calls == [(frame.WATCH_RETRY_DELAY_MS, frame._start_watch_loop)]


def test_handle_watch_start_failure_noops_when_closed(monkeypatch) -> None:
    """When already closed, the handler clears the pending flag but does not set
    status or schedule a retry.
    """
    frame = _make_frame()
    frame._watch_start_pending = True
    frame._closed = True
    call_later_calls: list[tuple[int, object]] = []
    monkeypatch.setattr(
        timer_alert.wx,
        "CallLater",
        lambda delay, func, *a, **k: call_later_calls.append((delay, func)),
    )

    TimerAlertFrame._handle_watch_start_failure(frame, "timer.status.bridge_error", RuntimeError())

    assert frame._watch_start_pending is False
    frame._set_status.assert_not_called()
    assert call_later_calls == []


@pytest.mark.parametrize(
    ("attr", "value"),
    [
        ("_closed", True),
        ("_watcher", MagicMock()),
        ("_watch_start_pending", True),
    ],
)
def test_start_watch_loop_guard_blocks_duplicate_start(monkeypatch, attr, value) -> None:
    """The early-return guard prevents spawning a watcher thread when closed,
    when a watcher already exists, or when a start is already pending.
    """
    frame = _make_frame()
    setattr(frame, attr, value)
    threads: list[object] = []
    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))

    TimerAlertFrame._start_watch_loop(frame)

    assert threads == []
    # The guard must not flip the pending flag (except where it was already set).
    if attr != "_watch_start_pending":
        assert frame._watch_start_pending is False


def test_watch_start_worker_stops_watcher_when_closed_after_success(monkeypatch) -> None:
    """If the frame closed while start_watch was running, the freshly-created
    watcher is stopped synchronously (no CallAfter) to avoid leaking it.
    """
    frame = _make_frame()
    frame._closed = True
    watcher = MagicMock()
    call_after_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    frame.controller.mtgo_bridge_service.start_watch = lambda *, interval_ms: watcher
    _patch_call_after(monkeypatch, call_after_calls)

    TimerAlertFrame._watch_start_worker(frame)

    watcher.stop.assert_called_once_with()
    assert call_after_calls == []


def test_complete_watch_start_stops_stale_watcher(monkeypatch) -> None:
    """If a different watcher is already installed, the incoming watcher is
    stopped and the existing one is left untouched.
    """
    frame = _make_frame()
    existing = MagicMock()
    incoming = MagicMock()
    frame._watcher = existing
    frame._watch_start_pending = True
    threads: list[object] = []
    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))

    TimerAlertFrame._complete_watch_start(frame, incoming)

    assert frame._watch_start_pending is False
    assert frame._watcher is existing
    frame._watch_timer.Start.assert_not_called()
    assert len(threads) == 1
    assert threads[0].args == (incoming,)
    threads[0].target(*threads[0].args)
    incoming.stop.assert_called_once_with()
    existing.stop.assert_not_called()


def test_complete_watch_start_stops_watcher_when_closed(monkeypatch) -> None:
    """If the frame closed before completion runs, the watcher is stopped and
    not installed.
    """
    frame = _make_frame()
    frame._closed = True
    frame._watch_start_pending = True
    watcher = MagicMock()
    threads: list[object] = []
    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))

    TimerAlertFrame._complete_watch_start(frame, watcher)

    assert frame._watch_start_pending is False
    assert frame._watcher is None
    frame._watch_timer.Start.assert_not_called()
    assert len(threads) == 1
    threads[0].target(*threads[0].args)
    watcher.stop.assert_called_once_with()
