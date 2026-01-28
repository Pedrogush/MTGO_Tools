"""Multiprocessing-based helpers for interacting with the MTGO bridge CLI.

This module runs the compiled ``MTGOBridge.exe`` and exposes:

* ``submit_bridge_command`` / ``BridgeCommandFuture`` for one-shot commands
  (collection, history, all) without blocking the caller thread.
* ``BridgeWatcher`` for streaming challenge timer / opponent snapshots using
  the bridge ``watch`` mode in a background process.

Designed to be self-contained so it can replace the previous pythonnet-based
runtime without requiring MTGOSDK assemblies in-process.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess  # nosec B404 - required to invoke MTGO bridge executable
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full
from typing import Any

from loguru import logger

from utils.constants import BRIDGE_PROCESS_TERMINATE_TIMEOUT_SECONDS

# Default .NET publish locations we will probe for MTGOBridge.exe
_DEFAULT_BRIDGE_CANDIDATES = [
    Path("dotnet/MTGOBridge/bin/Release/net9.0-windows7.0/win-x64/publish/MTGOBridge.exe"),
    Path("dotnet/MTGOBridge/bin/Release/net9.0-windows7.0/MTGOBridge.exe"),
    Path("dotnet/MTGOBridge/bin/Debug/net9.0-windows7.0/win-x64/publish/MTGOBridge.exe"),
    Path("dotnet/MTGOBridge/bin/Debug/net9.0-windows7.0/MTGOBridge.exe"),
]


class BridgeCommandError(RuntimeError):
    """Raised when a bridge command fails or the executable cannot be run."""


def _resolve_bridge_path(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    if explicit:
        candidate = Path(explicit)
        if candidate.exists():
            return candidate
        return None

    env_path = os.getenv("MTGO_BRIDGE_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    for candidate in _DEFAULT_BRIDGE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _require_bridge_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    resolved = _resolve_bridge_path(explicit)
    if resolved is None:
        raise FileNotFoundError(
            "MTGO bridge executable not found. Set MTGO_BRIDGE_PATH or build the project."
        )
    return resolved


def _sanitize_json_payload(raw: str) -> Any:
    payload = raw.strip()
    if not payload:
        raise BridgeCommandError("Bridge produced no output.")
    # Handle UTF-8 BOM if present.
    payload = payload.lstrip("\ufeff")
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise BridgeCommandError(f"Invalid JSON payload from bridge: {exc}") from exc


def _command_worker(
    bridge_path: str,
    args: Sequence[str],
    queue: mp.Queue,
) -> None:
    try:
        completed = subprocess.run(
            [bridge_path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )  # nosec B603 - arguments are constructed internally
        if completed.returncode != 0:
            raise BridgeCommandError(
                f"Bridge exited with code {completed.returncode}: {completed.stderr.strip()}"
            )
        queue.put(("ok", _sanitize_json_payload(completed.stdout)))
    except Exception as exc:  # noqa: BLE001 - surface error to parent
        queue.put(("error", repr(exc)))


class BridgeCommandFuture:
    """Handle for a bridge command running in a separate process."""

    def __init__(self, process: mp.Process, queue: mp.Queue):
        self._process = process
        self._queue = queue

    def result(self, timeout: float | None = None) -> Any:
        """Wait for the command to finish and return the JSON payload."""
        status, payload = self._queue.get(timeout=timeout)
        self._queue.close()
        self._process.join(timeout)
        if status == "ok":
            return payload
        raise BridgeCommandError(payload)

    def cancel(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
            self._process.join()
        self._queue.close()


def submit_bridge_command(
    mode: str,
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    extra_args: Sequence[str] | None = None,
    context: mp.context.BaseContext | None = None,
) -> BridgeCommandFuture:
    """Run ``MTGOBridge.exe <mode>`` in a worker process and return a future."""
    executable = _require_bridge_path(bridge_path)
    ctx = context or mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    args: list[str] = [mode]
    if extra_args:
        args.extend(extra_args)
    process = ctx.Process(target=_command_worker, args=(str(executable), args, queue))
    process.start()
    return BridgeCommandFuture(process, queue)


def run_bridge_command(
    mode: str,
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    extra_args: Sequence[str] | None = None,
    timeout: float | None = None,
) -> Any:
    future = submit_bridge_command(mode, bridge_path=bridge_path, extra_args=extra_args)
    try:
        return future.result(timeout=timeout)
    finally:
        future.cancel()


def fetch_collection_snapshot_async(
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    context: mp.context.BaseContext | None = None,
) -> BridgeCommandFuture:
    return submit_bridge_command("collection", bridge_path=bridge_path, context=context)


def fetch_match_history_async(
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    context: mp.context.BaseContext | None = None,
) -> BridgeCommandFuture:
    return submit_bridge_command("history", bridge_path=bridge_path, context=context)


def fetch_collection_snapshot(
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    timeout: float | None = None,
) -> Mapping[str, Any]:
    return run_bridge_command("collection", bridge_path=bridge_path, timeout=timeout)


def fetch_match_history(
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    timeout: float | None = None,
) -> Mapping[str, Any]:
    return run_bridge_command("history", bridge_path=bridge_path, timeout=timeout)


def fetch_trade_snapshot(
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    timeout: float | None = None,
) -> Mapping[str, Any]:
    """Return the trade status payload emitted by the bridge."""
    return run_bridge_command(
        "trade",
        bridge_path=bridge_path,
        extra_args=("status",),
        timeout=timeout,
    )


def accept_trade(
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    timeout: float | None = None,
) -> Mapping[str, Any]:
    """Request that the bridge accept the currently active trade."""
    return run_bridge_command(
        "trade",
        bridge_path=bridge_path,
        extra_args=("accept",),
        timeout=timeout,
    )


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
                buffer = chunk.lstrip("\ufeff")
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
