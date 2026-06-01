"""Streaming / challenge-watch transport for the MTGO bridge CLI.

Runs the bridge ``watch`` mode in a background process and exposes
``BridgeWatcher`` for streaming challenge timer / opponent snapshots.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess  # nosec B404 - required to invoke MTGO bridge executable
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full
from typing import Any

from loguru import logger

from utils.constants import BRIDGE_PROCESS_TERMINATE_TIMEOUT_SECONDS

from .discovery import _require_bridge_path


def _watch_worker(
    bridge_path: str,
    output_queue: mp.Queue,
    stop_event: mp.Event,
) -> None:
    cmd = [bridge_path, "watch"]
    logger.debug("Starting bridge watch subprocess: {}", cmd)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )  # nosec B603 - command is internal bridge watcher

    buffer = ""
    depth = 0
    in_string = False
    escape = False

    try:
        while True:
            if stop_event.is_set():
                break

            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue

            chunk = line.strip()
            if not chunk:
                continue

            if not buffer:
                buffer = chunk.lstrip("﻿")
            else:
                buffer += chunk

            for ch in chunk:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch in "{[":
                        depth += 1
                    elif ch in "}]":
                        if depth > 0:
                            depth -= 1

            if depth == 0 and not in_string and buffer:
                candidate = buffer.strip()
                if candidate:
                    try:
                        payload = json.loads(candidate)
                    except json.JSONDecodeError:
                        logger.debug("Skipping malformed watch payload: {}", candidate)
                    else:
                        _queue_replace(output_queue, payload)
                buffer = ""
                depth = 0
                in_string = False
                escape = False
    finally:
        if buffer.strip():
            try:
                payload = json.loads(buffer.strip())
            except json.JSONDecodeError:
                logger.debug("Skipping trailing malformed watch payload: {}", buffer.strip())
            else:
                _queue_replace(output_queue, payload)
        stop_event.set()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=BRIDGE_PROCESS_TERMINATE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            stderr_tail = process.stderr.read().strip()
            if stderr_tail:
                logger.debug("Bridge watch stderr: {}", stderr_tail)
            process.stderr.close()


def _queue_replace(queue: mp.Queue, item: Any) -> None:
    """Replace the current queue item with ``item`` (maxsize 1)."""
    try:
        queue.get_nowait()
    except Empty:
        pass
    try:
        queue.put_nowait(item)
    except Full:
        # If queue is full even after draining, drop the update.
        logger.debug("Dropping watch update because queue is full.")


@dataclass
class BridgeWatcher:
    """Background process that streams watch payloads."""

    bridge_path: Path
    interval_ms: int = 500
    context: mp.context.BaseContext = mp.get_context("spawn")

    def __post_init__(self) -> None:
        self._queue: mp.Queue = self.context.Queue(maxsize=1)
        self._stop_event: mp.Event = self.context.Event()
        self._process: mp.Process | None = None

    def start(self) -> None:
        if self._process and self._process.is_alive():
            return
        self._stop_event.clear()
        self._process = self.context.Process(
            target=_watch_worker,
            args=(str(self.bridge_path), self._queue, self._stop_event),
        )
        self._process.daemon = True
        self._process.start()

    def stop(self, timeout: float | None = 5) -> None:
        self._stop_event.set()
        if self._process and self._process.is_alive():
            self._process.join(timeout)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout)
        if self._queue:
            self._queue.close()

    def latest(self, *, block: bool = False, timeout: float | None = None) -> Any | None:
        if block:
            try:
                return self._queue.get(timeout=timeout)
            except Empty:
                return None
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def __enter__(self) -> BridgeWatcher:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def start_watch(
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    interval_ms: int = 500,
    context: mp.context.BaseContext | None = None,
) -> BridgeWatcher:
    """Convenience helper that instantiates and starts a watcher."""
    ctx = context or mp.get_context("spawn")
    watcher = BridgeWatcher(
        bridge_path=_require_bridge_path(bridge_path),
        interval_ms=interval_ms,
        context=ctx,
    )
    watcher.start()
    return watcher
