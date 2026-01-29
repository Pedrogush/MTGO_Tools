"""Process-based worker runner for heavy tasks."""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing import get_context
from multiprocessing.queues import Queue
from typing import Any

from loguru import logger

__all__ = ["ProcessHandle", "ProcessWorker"]


@dataclass(frozen=True)
class ProcessHandle:
    key: str
    process: Any
    queue: Queue


def _process_wrapper(target: Callable[..., Any], args: tuple[Any, ...], queue: Queue) -> None:
    try:
        payload = target(*args)
        queue.put({"ok": True, "payload": payload})
    except Exception as exc:
        queue.put(
            {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


class ProcessWorker:
    """Runs blocking work in a subprocess and reports results back to the caller."""

    def __init__(self) -> None:
        self._ctx = get_context("spawn")
        self._lock = threading.Lock()
        self._handles: dict[str, ProcessHandle] = {}

    def run_async(
        self,
        *,
        target: Callable[..., Any],
        args: tuple[Any, ...],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None],
        call_after: Callable[[Callable[..., Any], Any], None],
    ) -> ProcessHandle:
        queue: Queue = self._ctx.Queue()
        process = self._ctx.Process(
            target=_process_wrapper,
            args=(target, args, queue),
            daemon=True,
        )
        handle = ProcessHandle(key=str(uuid.uuid4()), process=process, queue=queue)
        with self._lock:
            self._handles[handle.key] = handle
        process.start()
        threading.Thread(
            target=self._watch_handle,
            args=(handle, on_success, on_error, call_after),
            daemon=True,
        ).start()
        return handle

    def terminate(self, handle: ProcessHandle) -> None:
        if handle.process.is_alive():
            handle.process.terminate()
        handle.process.join()
        try:
            handle.queue.close()
        except Exception:
            pass
        with self._lock:
            self._handles.pop(handle.key, None)

    def terminate_all(self) -> None:
        with self._lock:
            handles = list(self._handles.values())
        for handle in handles:
            self.terminate(handle)

    def _watch_handle(
        self,
        handle: ProcessHandle,
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None],
        call_after: Callable[[Callable[..., Any], Any], None],
    ) -> None:
        result: dict[str, Any] | None = None
        while True:
            try:
                result = handle.queue.get(timeout=0.2)
                break
            except Exception:
                if not handle.process.is_alive():
                    break

        handle.process.join()
        try:
            handle.queue.close()
        except Exception:
            pass
        with self._lock:
            self._handles.pop(handle.key, None)

        if result is None:
            msg = "Process exited without returning a result."
            logger.error(msg)
            call_after(on_error, msg)
            return

        if result.get("ok"):
            call_after(on_success, result.get("payload"))
            return

        msg = result.get("error") or "Process failed."
        tb = result.get("traceback")
        if tb:
            logger.error(tb)
        call_after(on_error, msg)
