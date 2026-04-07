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

    def __init__(self, *, thread_name_prefix: str = "background-worker") -> None:
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._thread_name_prefix = thread_name_prefix
        self._thread_counter = 0

    def submit(
        self,
        func: Callable[..., Any],
        *args: Any,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> threading.Thread | None:
        """Submit a task to run in a background thread.

        For long-running tasks, the function should periodically check self.is_stopped() and exit when True.
        """
        if self.is_stopped():
            logger.debug(f"Background worker stopped; ignoring task: {func.__name__}")
            return None

        def wrapper() -> None:
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                logger.exception(f"Background task failed: {exc}")
                if on_error:
                    self.call_after(on_error, exc)
            else:
                if on_success:
                    self.call_after(on_success, result)
            finally:
                self._remove_thread(threading.current_thread())

        thread = threading.Thread(target=wrapper, daemon=True, name=self._next_thread_name(name))
        with self._lock:
            self._threads.append(thread)
        thread.start()
        logger.debug(f"Started background thread: {thread.name}")
        return thread

    def call_after(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """Schedule a UI callback if the worker and wx app are still alive."""
        if self.is_stopped():
            return False
        try:
            import wx
        except ImportError:
            callback(*args, **kwargs)
            return True

        if not self._wx_app_available(wx):
            logger.debug("Skipping wx.CallAfter because the wx app is not available")
            return False

        try:
            wx.CallAfter(callback, *args, **kwargs)
        except RuntimeError as exc:
            logger.debug(f"Skipping wx.CallAfter after wx teardown: {exc}")
            return False
        return True

    @staticmethod
    def _wx_app_available(wx_module: Any) -> bool:
        get_app = getattr(wx_module, "GetApp", None)
        if get_app is None:
            return True
        try:
            app = get_app()
        except (RuntimeError, SystemError):
            return False
        if app is None:
            return False
        try:
            return bool(app)
        except (RuntimeError, SystemError):
            return False

    def _next_thread_name(self, name: str | None) -> str:
        if name:
            return name
        with self._lock:
            self._thread_counter += 1
            counter = self._thread_counter
        return f"{self._thread_name_prefix}-{counter}"

    def _remove_thread(self, thread: threading.Thread) -> None:
        with self._lock:
            if thread in self._threads:
                self._threads.remove(thread)

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def shutdown(self, timeout: float = 10.0) -> None:
        logger.info("Shutting down background worker...")
        self._stop_event.set()

        with self._lock:
            threads = list(self._threads)

        current_thread = threading.current_thread()
        for thread in threads:
            if thread is current_thread:
                continue
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
