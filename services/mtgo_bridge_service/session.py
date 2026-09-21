"""Long-lived bridge session: one process, one request queue.

``MTGOBridge.exe`` used to be spawned once per command. Measured against a live
client that cost ~0.8s of .NET startup plus ~3.1s of MTGOSDK ``RemoteClient``
attach *before* any work happened — a three-command probe cycle spent ~90% of
its wall time on overhead — and several bridge processes attached at the same
time degraded per-call latency roughly 8x, because MTGOSDK marshals every remote
read onto MTGO's UI thread.

This module supervises a single ``MTGOBridge.exe serve`` process instead. It
speaks newline-delimited JSON over stdin/stdout with request-id correlation,
serialises every caller through that one pipe, fans the ``watch`` stream out to
subscribers, and transparently respawns when the bridge dies or MTGO restarts.

Callers do not use this directly: :mod:`services.mtgo_bridge_service` routes its
public API here and falls back to the one-shot transport in :mod:`.commands`
whenever a session cannot be established (an older bridge build, for instance).
"""

from __future__ import annotations

import atexit
import itertools
import json
import os
import queue
import subprocess  # nosec B404 - required to invoke the MTGO bridge executable
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from loguru import logger

from utils.constants import (
    BRIDGE_SESSION_DISABLE_ENV,
    BRIDGE_SESSION_HANDSHAKE_TIMEOUT_SECONDS,
    BRIDGE_SESSION_PROTOCOL_VERSION,
    BRIDGE_SESSION_REQUEST_TIMEOUT_SECONDS,
    BRIDGE_SESSION_SHUTDOWN_TIMEOUT_SECONDS,
    BRIDGE_SESSION_WATCH_INTERVAL_MS,
)

from .discovery import _require_bridge_path

_TRUTHY = {"1", "true", "yes", "on"}


class BridgeSessionError(RuntimeError):
    """A request was delivered to a live bridge session and came back failed."""


class BridgeSessionUnavailable(BridgeSessionError):
    """No usable session: the caller should fall back to a one-shot command."""


def session_enabled() -> bool:
    """Return False when the escape hatch env var disables the long-lived mode."""
    return os.getenv(BRIDGE_SESSION_DISABLE_ENV, "").strip().lower() not in _TRUTHY


def _queue_replace(sink: queue.Queue, item: Any) -> None:
    """Overwrite ``sink``'s single slot with ``item`` (latest-wins semantics)."""
    try:
        sink.get_nowait()
    except queue.Empty:
        pass
    try:
        sink.put_nowait(item)
    except queue.Full:
        logger.debug("Dropping bridge watch update because the subscriber queue is full.")


class BridgeSession:
    """Supervises one ``MTGOBridge.exe serve`` process."""

    def __init__(self, bridge_path: str | os.PathLike[str]):
        self.bridge_path = Path(bridge_path)
        # ``_state_lock`` guards the process lifecycle (spawn/teardown) and is
        # held across the ready handshake; the reader thread never takes it, so
        # the handshake cannot deadlock against the thread that completes it.
        self._state_lock = threading.RLock()
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._watch_lock = threading.Lock()

        self._process: subprocess.Popen[str] | None = None
        self._pending: dict[str, queue.Queue] = {}
        self._watch_queues: set[queue.Queue] = set()
        self._watch_interval_ms = BRIDGE_SESSION_WATCH_INTERVAL_MS
        # True once the bridge has been told to stream. Only then does a respawn
        # re-arm the stream, so the very first subscriber does not get a
        # duplicate start (its own request is already on the way).
        self._watch_armed = False
        self._ids = itertools.count(1)
        self._ready = threading.Event()
        self._ready_error: str | None = None
        # Sticky: a build that does not understand ``serve`` will never start to,
        # so we stop paying a spawn per request and let callers use one-shot mode.
        self._unsupported = False

    # ------------------------------------------------------------------ requests
    def request(
        self,
        command: str,
        *,
        args: Sequence[str] = (),
        timeout: float | None = None,
    ) -> Any:
        """Run ``command`` on the shared bridge and return its payload.

        The payload is byte-identical to what ``MTGOBridge.exe <command>`` prints,
        so callers parse session and one-shot results with the same code.
        """
        if not session_enabled():
            raise BridgeSessionUnavailable(f"{BRIDGE_SESSION_DISABLE_ENV} is set")

        wait = BRIDGE_SESSION_REQUEST_TIMEOUT_SECONDS if timeout is None else timeout
        last_error: str = "bridge session unavailable"
        # Two attempts: a session that died while idle (MTGO restarted, the user
        # killed the bridge) should cost one transparent respawn, not an error.
        for attempt in (1, 2):
            try:
                self._ensure_started()
                status, payload = self._exchange(command, args, wait)
            except BridgeSessionUnavailable as exc:
                last_error = str(exc)
                if self._unsupported:
                    break
                logger.debug("Bridge session attempt {} failed: {}", attempt, exc)
                self._teardown()
                continue

            if status == "ok":
                return payload
            if status == "closed":
                last_error = str(payload)
                logger.debug("Bridge session closed mid-request: {}", payload)
                self._teardown()
                continue
            raise BridgeSessionError(str(payload))

        raise BridgeSessionUnavailable(last_error)

    def _exchange(self, command: str, args: Sequence[str], timeout: float) -> tuple[str, Any]:
        request_id = str(next(self._ids))
        slot: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = slot
        try:
            self._write({"id": request_id, "command": command, "args": [str(a) for a in args]})
            try:
                return slot.get(timeout=timeout)
            except queue.Empty as exc:
                # A wedged SDK call cannot be cancelled remotely; drop the process
                # so the next caller gets a clean attach instead of queueing behind it.
                self._teardown()
                raise BridgeSessionUnavailable(
                    f"Bridge command {command!r} did not answer within {timeout} seconds."
                ) from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    # ------------------------------------------------------------------ watch stream
    def subscribe_watch(self, sink: queue.Queue, interval_ms: int) -> None:
        """Register ``sink`` for watch snapshots, starting the stream if needed."""
        with self._watch_lock:
            first = not self._watch_queues
            self._watch_queues.add(sink)
            self._watch_interval_ms = interval_ms
        if not first:
            return
        try:
            self.request("watch", args=("start", str(interval_ms)))
        except BridgeSessionError:
            # Do not leave a sink registered for a stream that never started;
            # the caller is about to fall back to a standalone watcher.
            with self._watch_lock:
                self._watch_queues.discard(sink)
            raise
        with self._watch_lock:
            self._watch_armed = True

    def unsubscribe_watch(self, sink: queue.Queue) -> None:
        """Drop ``sink``; the bridge stops streaming once nobody is listening."""
        with self._watch_lock:
            self._watch_queues.discard(sink)
            if self._watch_queues:
                return
            self._watch_armed = False
        try:
            self.request("watch", args=("stop",))
        except BridgeSessionError as exc:
            logger.debug("Failed to stop the bridge watch stream: {}", exc)

    # ------------------------------------------------------------------ lifecycle
    def _ensure_started(self) -> None:
        with self._state_lock:
            if self._unsupported:
                raise BridgeSessionUnavailable(
                    f"{self.bridge_path.name} does not support 'serve' mode"
                )
            process = self._process
            if process is not None and process.poll() is None:
                return
            self._start_locked()

    def _start_locked(self) -> None:
        self._ready = threading.Event()
        self._ready_error = None
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        logger.debug("Starting long-lived bridge session: {} serve", self.bridge_path)
        try:
            process = subprocess.Popen(  # nosec B603 - arguments are constructed internally
                [str(self.bridge_path), "serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise BridgeSessionUnavailable(f"Could not start the bridge session: {exc}") from exc

        self._process = process
        threading.Thread(
            target=self._read_loop,
            args=(process,),
            daemon=True,
            name="mtgo-bridge-session-reader",
        ).start()
        threading.Thread(
            target=self._drain_stderr,
            args=(process,),
            daemon=True,
            name="mtgo-bridge-session-stderr",
        ).start()

        if not self._ready.wait(BRIDGE_SESSION_HANDSHAKE_TIMEOUT_SECONDS):
            self._terminate_locked()
            raise BridgeSessionUnavailable(
                "Bridge session did not announce itself within "
                f"{BRIDGE_SESSION_HANDSHAKE_TIMEOUT_SECONDS} seconds."
            )
        if self._ready_error is not None:
            error = self._ready_error
            self._terminate_locked()
            raise BridgeSessionUnavailable(error)

        self._resume_watch_locked()

    def _resume_watch_locked(self) -> None:
        """Re-arm the watch stream after a respawn so subscribers keep receiving."""
        with self._watch_lock:
            if not (self._watch_armed and self._watch_queues):
                return
            interval_ms = self._watch_interval_ms
        try:
            self._write(
                {
                    "id": str(next(self._ids)),
                    "command": "watch",
                    "args": ["start", str(interval_ms)],
                }
            )
        except BridgeSessionUnavailable as exc:
            logger.debug("Could not re-arm the bridge watch stream: {}", exc)

    def _write(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise BridgeSessionUnavailable("Bridge session is not running.")
        line = json.dumps(message, separators=(",", ":")) + "\n"
        with self._write_lock:
            try:
                process.stdin.write(line)
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise BridgeSessionUnavailable(f"Bridge session pipe closed: {exc}") from exc

    def _read_loop(self, process: subprocess.Popen[str]) -> None:
        stdout = process.stdout
        assert stdout is not None  # nosec B101 - stdout=PIPE above guarantees it
        try:
            for line in stdout:
                payload = line.strip().lstrip("﻿")
                if not payload:
                    continue
                try:
                    message = json.loads(payload)
                except json.JSONDecodeError:
                    logger.debug("Skipping malformed bridge session line: {}", payload[:200])
                    continue
                if isinstance(message, dict):
                    self._dispatch(message)
        except (OSError, ValueError):  # pragma: no cover - pipe torn down mid-read
            pass
        finally:
            self._on_closed(process)

    def _dispatch(self, message: dict[str, Any]) -> None:
        event = message.get("event")
        if event is not None:
            self._handle_event(str(event), message.get("payload"))
            return

        request_id = message.get("id")
        if request_id is None:
            return
        with self._pending_lock:
            slot = self._pending.get(str(request_id))
        if slot is None:
            logger.debug("Bridge session answered unknown request id {}", request_id)
            return
        if message.get("ok"):
            _queue_replace(slot, ("ok", message.get("payload")))
        else:
            _queue_replace(slot, ("error", message.get("error") or "bridge reported no detail"))

    def _handle_event(self, event: str, payload: Any) -> None:
        if event == "ready":
            protocol = payload.get("protocol") if isinstance(payload, dict) else None
            if protocol != BRIDGE_SESSION_PROTOCOL_VERSION:
                self._unsupported = True
                self._ready_error = (
                    f"Bridge speaks serve protocol {protocol!r}, "
                    f"expected {BRIDGE_SESSION_PROTOCOL_VERSION}."
                )
            self._ready.set()
            return
        if event == "watch":
            with self._watch_lock:
                sinks = list(self._watch_queues)
            for sink in sinks:
                _queue_replace(sink, payload)
            return
        if event == "disconnected":
            reason = payload.get("reason") if isinstance(payload, dict) else payload
            logger.info("Bridge session disconnected: {}", reason)
            return
        logger.debug("Ignoring unknown bridge session event {!r}", event)

    def _drain_stderr(self, process: subprocess.Popen[str]) -> None:
        stderr = process.stderr
        if stderr is None:  # pragma: no cover - stderr=PIPE above guarantees it
            return
        try:
            for line in stderr:
                text = line.strip()
                if text:
                    logger.debug("Bridge session stderr: {}", text)
        except (OSError, ValueError):  # pragma: no cover - pipe torn down mid-read
            pass

    def _on_closed(self, process: subprocess.Popen[str]) -> None:
        """Fail every in-flight request once the bridge's stdout hits EOF."""
        if not self._ready.is_set():
            # Exited before announcing itself: the signature of a build that
            # predates ``serve`` (unknown modes make it return immediately).
            self._unsupported = True
            self._ready_error = (
                f"{self.bridge_path.name} exited without a ready banner; "
                "this build predates the long-lived 'serve' mode."
            )
            self._ready.set()

        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for slot in pending:
            _queue_replace(
                slot, ("closed", "Bridge session ended while the request was in flight.")
            )

        with self._state_lock:
            if self._process is process:
                self._process = None

    def _teardown(self) -> None:
        with self._state_lock:
            self._terminate_locked()

    def _terminate_locked(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        # Closing stdin is the documented shutdown: the serve loop's reader sees
        # EOF and exits cleanly, detaching from MTGO on its way out.
        try:
            if process.stdin is not None:
                process.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            process.wait(timeout=BRIDGE_SESSION_SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=BRIDGE_SESSION_SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                # Never leave an orphan attached: it would keep hammering MTGO's
                # UI thread with nobody reading the answers.
                process.kill()
                try:
                    process.wait(timeout=BRIDGE_SESSION_SHUTDOWN_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:  # pragma: no cover - kill ignored
                    logger.warning("Bridge session process {} would not die.", process.pid)

    def stop(self) -> None:
        """Shut the bridge process down and forget any watch subscribers."""
        with self._watch_lock:
            self._watch_queues.clear()
            self._watch_armed = False
        self._teardown()


class SessionRequestFuture:
    """``BridgeCommandFuture``-shaped handle over a request run on a thread.

    The async entry points predate the session and returned a handle backed by a
    whole worker *process*; that is exactly the second attach this change exists
    to remove, so the work now happens on a thread that talks to the shared
    session. ``cancel`` stops the caller waiting — a request already queued on
    the bridge cannot be recalled — and is safe to call after ``result``.
    """

    def __init__(self, call: Callable[[], Any]):
        self._value: Any = None
        self._error: BaseException | None = None
        self._done = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            args=(call,),
            daemon=True,
            name="mtgo-bridge-request",
        )
        self._thread.start()

    def _run(self, call: Callable[[], Any]) -> None:
        try:
            self._value = call()
        except BaseException as exc:  # noqa: BLE001 - re-raised in result()
            self._error = exc
        finally:
            self._done.set()

    def result(self, timeout: float | None = None) -> Any:
        if not self._done.wait(timeout):
            raise BridgeSessionError(
                f"Bridge command did not produce a result within {timeout} seconds."
            )
        if self._error is not None:
            raise self._error
        return self._value

    def cancel(self) -> None:
        # Nothing to kill: the worker is a daemon thread and the bridge process
        # is shared, so cancelling must not tear it down for other callers.
        return None


class SessionWatcher:
    """Watch stream served by the shared session, shaped like ``BridgeWatcher``."""

    def __init__(self, session: BridgeSession, interval_ms: int):
        self._session = session
        self.interval_ms = interval_ms
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._session.subscribe_watch(self._queue, self.interval_ms)
        self._started = True

    def stop(
        self, timeout: float | None = None
    ) -> None:  # noqa: ARG002 - parity with BridgeWatcher
        if not self._started:
            return
        self._started = False
        self._session.unsubscribe_watch(self._queue)

    def latest(self, *, block: bool = False, timeout: float | None = None) -> Any | None:
        if block:
            try:
                return self._queue.get(timeout=timeout)
            except queue.Empty:
                return None
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def __enter__(self) -> SessionWatcher:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


_session: BridgeSession | None = None
_session_lock = threading.Lock()


def get_session(bridge_path: str | os.PathLike[str] | None = None) -> BridgeSession:
    """Return the process-wide session for ``bridge_path``, starting nothing yet.

    Raises ``FileNotFoundError`` when the executable cannot be located, matching
    the one-shot transport so existing callers keep their error handling.
    """
    resolved = _require_bridge_path(bridge_path)
    global _session
    with _session_lock:
        if _session is not None and _session.bridge_path == resolved:
            return _session
        if _session is not None:
            _session.stop()
        _session = BridgeSession(resolved)
        return _session


def shutdown_session() -> None:
    """Tear down the process-wide session, if one was ever started."""
    global _session
    with _session_lock:
        session, _session = _session, None
    if session is not None:
        session.stop()


# Windows does not reap grandchildren when a parent dies, so make the normal
# interpreter exit path close the pipe explicitly.
atexit.register(shutdown_session)
