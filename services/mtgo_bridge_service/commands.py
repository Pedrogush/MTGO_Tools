"""One-shot command transport for the MTGO bridge CLI.

Runs ``MTGOBridge.exe <mode>`` in a worker process and exposes
``submit_bridge_command`` / ``BridgeCommandFuture`` for non-blocking
collection / history / trade commands.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess  # nosec B404 - required to invoke MTGO bridge executable
from collections.abc import Mapping, Sequence
from queue import Empty
from typing import Any

from utils.constants import BRIDGE_PROCESS_TERMINATE_TIMEOUT_SECONDS

from .discovery import _require_bridge_path


class BridgeCommandError(RuntimeError):
    """Raised when a bridge command fails or the executable cannot be run."""


def _sanitize_json_payload(raw: str) -> Any:
    payload = raw.strip()
    if not payload:
        raise BridgeCommandError("Bridge produced no output.")
    # Handle UTF-8 BOM if present.
    payload = payload.lstrip("﻿")
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise BridgeCommandError(f"Invalid JSON payload from bridge: {exc}") from exc


def _command_worker(
    bridge_path: str,
    args: Sequence[str],
    queue: mp.Queue,
    timeout: float | None = None,
) -> None:
    try:
        try:
            completed = subprocess.run(
                [bridge_path, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=timeout,
            )  # nosec B603 - arguments are constructed internally
        except subprocess.TimeoutExpired as exc:
            # subprocess.run already terminates the child on TimeoutExpired,
            # but surface an actionable error to the parent.
            raise BridgeCommandError(
                f"Bridge command {list(args)!r} timed out after {timeout} seconds."
            ) from exc
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
        try:
            status, payload = self._queue.get(timeout=timeout)
        except Empty as exc:
            # Wrapper thread timed out waiting on the bridge worker. Make sure
            # the child process is torn down so it can't outlive the request.
            self.cancel()
            raise BridgeCommandError(
                f"Bridge command did not produce a result within {timeout} seconds."
            ) from exc
        self._queue.close()
        self._process.join(timeout)
        if status == "ok":
            return payload
        raise BridgeCommandError(payload)

    def cancel(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(BRIDGE_PROCESS_TERMINATE_TIMEOUT_SECONDS)
            if self._process.is_alive():
                # On Windows ``terminate`` may not kill grandchildren; ``kill``
                # sends SIGKILL/TerminateProcess to guarantee teardown.
                self._process.kill()
                self._process.join(BRIDGE_PROCESS_TERMINATE_TIMEOUT_SECONDS)
        self._queue.close()


def submit_bridge_command(
    mode: str,
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    extra_args: Sequence[str] | None = None,
    context: mp.context.BaseContext | None = None,
    timeout: float | None = None,
) -> BridgeCommandFuture:
    """Run ``MTGOBridge.exe <mode>`` in a worker process and return a future.

    ``timeout`` is passed through to ``subprocess.run`` inside the worker so
    the bridge subprocess itself is bounded, not just the wrapper wait.
    """
    executable = _require_bridge_path(bridge_path)
    ctx = context or mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    args: list[str] = [mode]
    if extra_args:
        args.extend(extra_args)
    process = ctx.Process(target=_command_worker, args=(str(executable), args, queue, timeout))
    process.start()
    return BridgeCommandFuture(process, queue)


def run_bridge_command(
    mode: str,
    *,
    bridge_path: str | os.PathLike[str] | None = None,
    extra_args: Sequence[str] | None = None,
    timeout: float | None = None,
) -> Any:
    future = submit_bridge_command(
        mode, bridge_path=bridge_path, extra_args=extra_args, timeout=timeout
    )
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
