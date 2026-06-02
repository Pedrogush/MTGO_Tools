from __future__ import annotations

import threading
import time

import pytest

from utils.background_worker import BackgroundWorker


@pytest.fixture(autouse=True)
def _synchronous_call_after(monkeypatch):
    """Run wx.CallAfter callbacks synchronously whenever wx is importable.

    The suite runs on a headless Windows CI runner where ``import wx`` succeeds
    but no ``wx.App`` exists, so the real ``wx.CallAfter`` raises
    "No wx.App created yet" and BackgroundWorker's callbacks never fire.
    Off-Windows wx is absent and ``BackgroundWorker._call_after`` already falls
    back to a direct call, so the stub is simply skipped there.
    """
    try:
        import wx
    except ImportError:
        return
    monkeypatch.setattr(wx, "CallAfter", lambda func, *args, **kwargs: func(*args, **kwargs))


def test_background_worker_submit():
    worker = BackgroundWorker()
    result = []
    done = threading.Event()

    def task():
        result.append(1)
        done.set()

    worker.submit(task)
    assert done.wait(timeout=1.0)

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
    done = threading.Event()

    with BackgroundWorker() as worker:

        def task():
            result.append(1)
            done.set()

        worker.submit(task)
        assert done.wait(timeout=1.0)

    assert result == [1]
    assert worker.is_stopped()


def test_background_worker_shutdown_waits_for_threads():
    worker = BackgroundWorker()
    completed = []
    started = threading.Event()

    def slow_task():
        started.set()
        while not worker.is_stopped():
            time.sleep(0.01)
        completed.append(1)

    worker.submit(slow_task)
    assert started.wait(timeout=1.0)

    worker.shutdown(timeout=2.0)

    assert completed == [1]


def test_background_worker_multiple_threads():
    worker = BackgroundWorker()
    results = []
    lock = threading.Lock()
    all_done = threading.Barrier(4, timeout=1.0)

    def task(value):
        with lock:
            results.append(value)
        all_done.wait()

    worker.submit(task, 1)
    worker.submit(task, 2)
    worker.submit(task, 3)

    all_done.wait()
    worker.shutdown()

    assert sorted(results) == [1, 2, 3]


def test_background_worker_shutdown_timeout():
    worker = BackgroundWorker()
    started = threading.Event()
    threads_seen = []

    def blocking_task():
        threads_seen.append(threading.current_thread())
        started.set()
        while True:
            time.sleep(0.1)

    worker.submit(blocking_task)
    assert started.wait(timeout=1.0)

    # shutdown must return promptly after the timeout instead of blocking
    # forever on the non-cooperative thread (which ignores is_stopped()).
    start = time.monotonic()
    worker.shutdown(timeout=0.2)
    elapsed = time.monotonic() - start

    assert worker.is_stopped()
    # join timed out rather than hung; allow generous slack for slow CI.
    assert elapsed < 2.0
    # the task ignored the stop flag, so its thread is still alive.
    assert threads_seen and threads_seen[0].is_alive()


def test_background_worker_on_success_receives_result():
    worker = BackgroundWorker()
    received = []
    done = threading.Event()

    def task():
        return 42

    def on_success(result):
        received.append(result)
        done.set()

    worker.submit(task, on_success=on_success)
    assert done.wait(timeout=1.0)
    worker.shutdown()

    assert received == [42]


def test_background_worker_on_error_receives_exception():
    worker = BackgroundWorker()
    errors = []
    success_called = []
    done = threading.Event()
    boom = ValueError("boom")

    def task():
        raise boom

    def on_success(result):
        success_called.append(result)

    def on_error(exc):
        errors.append(exc)
        done.set()

    worker.submit(task, on_success=on_success, on_error=on_error)
    assert done.wait(timeout=1.0)
    worker.shutdown()

    assert errors == [boom]
    assert success_called == []


def test_background_worker_forwards_args_and_kwargs():
    worker = BackgroundWorker()
    received = []
    done = threading.Event()

    def task(a, b, *, c):
        received.append((a, b, c))

    def on_success(_result):
        done.set()

    worker.submit(task, 1, 2, c=3, on_success=on_success)
    assert done.wait(timeout=1.0)
    worker.shutdown()

    assert received == [(1, 2, 3)]


def test_background_worker_error_without_on_error_is_swallowed():
    worker = BackgroundWorker()
    after = []
    done = threading.Event()

    def failing_task():
        raise RuntimeError("fail")

    def ok_task():
        after.append(1)
        done.set()

    # A failing task without on_error must not propagate or crash the worker;
    # a subsequent task still runs normally.
    worker.submit(failing_task)
    worker.submit(ok_task)
    assert done.wait(timeout=1.0)
    worker.shutdown()

    assert after == [1]


def test_background_worker_call_after_runs_synchronously():
    # The callback is marshalled synchronously: off-Windows wx is absent and
    # _call_after falls back to a direct call; on the headless CI runner the
    # _synchronous_call_after fixture stubs wx.CallAfter to the same effect.
    # Either way the callback runs in the worker thread before shutdown joins it.
    worker = BackgroundWorker()
    callback_thread = []

    def task():
        return threading.current_thread()

    def on_success(result):
        callback_thread.append((result, threading.current_thread()))

    worker.submit(task, on_success=on_success)
    worker.shutdown(timeout=2.0)

    # shutdown joins the worker thread; the synchronous fallback means the
    # callback already ran (in that same worker thread) by the time we assert.
    assert len(callback_thread) == 1
    worker_result, cb_thread = callback_thread[0]
    assert worker_result is cb_thread
