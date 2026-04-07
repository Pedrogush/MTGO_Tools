from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace

from utils.background_worker import BackgroundWorker


def test_background_worker_submit():
    worker = BackgroundWorker()
    result = []

    def task():
        result.append(1)

    worker.submit(task)
    time.sleep(0.1)

    assert result == [1]
    worker.shutdown()


def test_background_worker_is_stopped():
    worker = BackgroundWorker()

    assert not worker.is_stopped()

    worker.shutdown()

    assert worker.is_stopped()


def test_background_worker_stops_loop():
    worker = BackgroundWorker()
    iterations = []

    def loop_task():
        while not worker.is_stopped():
            iterations.append(1)
            time.sleep(0.05)

    worker.submit(loop_task)
    time.sleep(0.2)

    worker.shutdown(timeout=2.0)

    initial_count = len(iterations)
    time.sleep(0.2)
    final_count = len(iterations)

    assert initial_count > 0
    assert initial_count == final_count


def test_background_worker_context_manager():
    result = []

    with BackgroundWorker() as worker:

        def task():
            result.append(1)

        worker.submit(task)
        time.sleep(0.1)

    assert result == [1]
    assert worker.is_stopped()


def test_background_worker_shutdown_waits_for_threads():
    worker = BackgroundWorker()
    completed = []

    def slow_task():
        while not worker.is_stopped():
            time.sleep(0.1)
        completed.append(1)

    worker.submit(slow_task)
    time.sleep(0.1)

    worker.shutdown(timeout=2.0)

    assert completed == [1]


def test_background_worker_multiple_threads():
    worker = BackgroundWorker()
    results = []

    def task(value):
        results.append(value)

    worker.submit(task, 1)
    worker.submit(task, 2)
    worker.submit(task, 3)

    time.sleep(0.2)
    worker.shutdown()

    assert sorted(results) == [1, 2, 3]


def test_background_worker_shutdown_timeout():
    worker = BackgroundWorker()
    started = threading.Event()

    def blocking_task():
        started.set()
        while True:
            time.sleep(0.1)

    worker.submit(blocking_task)
    started.wait(timeout=1.0)

    worker.shutdown(timeout=0.2)

    assert worker.is_stopped()


def test_background_worker_call_after_uses_wx_when_app_available(monkeypatch):
    worker = BackgroundWorker()
    calls = []

    fake_wx = SimpleNamespace(
        GetApp=lambda: object(),
        CallAfter=lambda callback, *args, **kwargs: calls.append((callback, args, kwargs)),
    )
    monkeypatch.setitem(sys.modules, "wx", fake_wx)

    callback = lambda value: value  # noqa: E731

    assert worker.call_after(callback, "ok") is True
    assert calls == [(callback, ("ok",), {})]

    worker.shutdown()


def test_background_worker_call_after_skips_when_wx_app_missing(monkeypatch):
    worker = BackgroundWorker()
    calls = []

    def fail_call_after(*_args, **_kwargs):
        raise AssertionError("wx.CallAfter should not be called without a wx app")

    fake_wx = SimpleNamespace(GetApp=lambda: None, CallAfter=fail_call_after)
    monkeypatch.setitem(sys.modules, "wx", fake_wx)

    assert worker.call_after(lambda: calls.append("called")) is False
    assert calls == []

    worker.shutdown()


def test_background_worker_call_after_skips_after_wx_teardown(monkeypatch):
    worker = BackgroundWorker()
    calls = []

    def raising_call_after(*_args, **_kwargs):
        raise RuntimeError("wrapped C/C++ object of type App has been deleted")

    fake_wx = SimpleNamespace(GetApp=lambda: object(), CallAfter=raising_call_after)
    monkeypatch.setitem(sys.modules, "wx", fake_wx)

    assert worker.call_after(lambda: calls.append("called")) is False
    assert calls == []

    worker.shutdown()
