"""Headless tests for TimerAlertFrame bridge watcher lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("wx")

import widgets.timer_alert as timer_alert

TimerAlertFrame = timer_alert.TimerAlertFrame


class _FakeThread:
    def __init__(self, target, args: tuple[object, ...]) -> None:
        self.target = target
        self.args = args
        self.daemon = True
        self.started = False

    def start(self) -> None:
        self.started = True


class _FakeWorker:
    def __init__(self) -> None:
        self.threads: list[_FakeThread] = []
        self.call_after_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []
        self.shutdown_calls: list[float] = []

    def submit(self, target, *args, name: str | None = None):  # noqa: ARG002, ANN001
        thread = _FakeThread(target, args)
        self.threads.append(thread)
        thread.start()
        return thread

    def call_after(self, func, *args, **kwargs) -> bool:  # noqa: ANN001
        self.call_after_calls.append((func, args, kwargs))
        return True

    def shutdown(self, timeout: float = 10.0) -> None:
        self.shutdown_calls.append(timeout)


def _make_frame() -> TimerAlertFrame:
    frame = TimerAlertFrame.__new__(TimerAlertFrame)
    frame.WATCH_INTERVAL_MS = 750
    frame.WATCH_RETRY_DELAY_MS = 5000
    frame._watcher = None
    frame._watch_start_pending = False
    frame._closed = False
    frame._worker = _FakeWorker()
    frame._watch_timer = MagicMock()
    frame._monitor_timer = MagicMock()
    frame._repeat_timer = MagicMock()
    frame._set_status = MagicMock()
    return frame


def test_start_watch_loop_runs_bridge_start_in_background(monkeypatch) -> None:
    frame = _make_frame()
    watcher = MagicMock()
    start_watch_calls: list[int] = []

    def fake_start_watch(*, interval_ms: int):
        start_watch_calls.append(interval_ms)
        return watcher

    monkeypatch.setattr(timer_alert.mtgo_bridge, "start_watch", fake_start_watch)

    TimerAlertFrame._start_watch_loop(frame)

    assert frame._watch_start_pending is True
    assert start_watch_calls == []
    assert len(frame._worker.threads) == 1
    assert frame._worker.threads[0].started is True
    assert frame._worker.threads[0].daemon is True

    frame._worker.threads[0].target(*frame._worker.threads[0].args)

    assert start_watch_calls == [frame.WATCH_INTERVAL_MS]
    assert frame._worker.call_after_calls == [(frame._complete_watch_start, (watcher,), {})]


def test_on_close_stops_existing_watcher_in_background(monkeypatch) -> None:
    frame = _make_frame()
    watcher = MagicMock()
    frame._watcher = watcher
    frame._watch_timer.IsRunning.return_value = True
    frame._monitor_timer.IsRunning.return_value = True
    frame._repeat_timer.IsRunning.return_value = True
    event = MagicMock()

    TimerAlertFrame.on_close(frame, event)

    assert frame._closed is True
    assert frame._watcher is None
    frame._watch_timer.Stop.assert_called_once_with()
    frame._monitor_timer.Stop.assert_called_once_with()
    frame._repeat_timer.Stop.assert_called_once_with()
    watcher.stop.assert_not_called()
    assert len(frame._worker.threads) == 1
    assert frame._worker.threads[0].started is True
    assert frame._worker.threads[0].daemon is True
    assert frame._worker.shutdown_calls == [2.0]

    frame._worker.threads[0].target(*frame._worker.threads[0].args)

    watcher.stop.assert_called_once_with()
    event.Skip.assert_called_once_with()
