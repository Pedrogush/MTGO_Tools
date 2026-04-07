from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from loguru import logger

__all__ = ["BackgroundWorker"]


class BackgroundWorker:
    """Manages background worker threads with lifecycle control and graceful shutdown.

    Run blocking work in threads and marshal callbacks onto the UI thread.
    """

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def submit(
        self,
        func: Callable[..., Any],
        *args: Any,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Submit a task to run in a background thread.

        For long-running tasks, the function should periodically check self.is_stopped() and exit when True.
        """

        def wrapper():
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                logger.exception(f"Background task failed: {exc}")
                if on_error:
                    self._call_after(on_error, exc)
                return

            if on_success:
                self._call_after(on_success, result)

        thread = threading.Thread(target=wrapper, daemon=True)
        with self._lock:
            self._threads.append(thread)
        thread.start()
        logger.debug(f"Started background thread: {func.__name__}")

    def _call_after(self, callback: Callable, *args: Any) -> None:
        """Marshal callback to UI thread if wx is available, otherwise call directly."""
        try:
            import wx

            wx.CallAfter(callback, *args)
        except ImportError:
            callback(*args)

    def is_stopped(self) -> bool:
        """Check if executor has been stopped."""
        return self._stop_event.is_set()

    def shutdown(self, timeout: float = 10.0) -> None:
        """Signal all threads to stop and wait for them to finish."""
        logger.info("Shutting down background worker...")
        self._stop_event.set()

        with self._lock:
            threads = list(self._threads)

        for thread in threads:
            if thread.is_alive():
                logger.debug(f"Waiting for thread {thread.name} to finish...")
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning(f"Thread {thread.name} did not finish within {timeout}s")

        logger.info("Background worker shutdown complete")

    def __enter__(self) -> BackgroundWorker:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()
