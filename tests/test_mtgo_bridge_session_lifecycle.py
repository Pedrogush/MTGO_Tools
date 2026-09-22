"""Regression tests for the bridge session's recovery and teardown paths.

A sibling of ``test_mtgo_bridge_session.py`` rather than an addition to it: these
tests need stubs that stall on purpose (a bridge that will not announce itself
until told, a bridge that serves strictly one request at a time), and the failure
they pin is an *interleaving* between two of the session's threads, which needs
its own scaffolding. Keeping that out of the main file leaves it readable and
keeps two people adding bridge tests out of each other's way.

Like its sibling, everything here drives a Python stub over real pipes, so no
test needs MTGO, MTGOSDK or the compiled bridge.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_mtgo_bridge_session import _write_executable_bridge

from controllers.app_controller import lifecycle
from controllers.app_controller.lifecycle import LifecycleMixin
from services.mtgo_bridge_service import session as bridge_session

# A bridge that stays silent until GATE_PATH exists, then behaves normally. The
# silence is the useful part: it parks ``_start_locked`` on the readiness record
# of that start for as long as a test needs to drive the other thread.
_DEFERRED_READY_STUB = r"""
import json, os, sys, time

GATE = "GATE_PATH"


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


# Bounded so a stub can never outlive the run that started it.
deadline = time.monotonic() + 60
while not os.path.exists(GATE):
    if time.monotonic() > deadline:
        sys.exit(0)
    time.sleep(0.01)

emit({"event": "ready", "payload": {"protocol": PROTOCOL, "pid": 0}})

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    emit({"id": req["id"], "ok": True, "payload": {"argv": [req["command"]] + req.get("args", [])}})
"""

# Shaped like the real serve loop: one thread reads the pipe, one worker runs
# requests strictly one at a time (the C# side's sdkLock), so a "slow" command
# genuinely holds up everything queued behind it while stdin EOF still ends the
# process immediately -- which matters, because the launcher is a shell script
# and the session's terminate() would otherwise only reach the shell.
_SERIAL_STUB = r"""
import json, os, queue, sys, threading, time

work = queue.Queue()


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def worker():
    while True:
        req = work.get()
        if req["command"] == "slow":
            time.sleep(SLOW_SECONDS)
        emit({
            "id": req["id"],
            "ok": True,
            "payload": {"argv": [req["command"]] + req.get("args", [])},
        })


threading.Thread(target=worker, daemon=True).start()

emit({"event": "ready", "payload": {"protocol": PROTOCOL, "pid": 0}})

for line in sys.stdin:
    line = line.strip()
    if line:
        work.put(json.loads(line))

os._exit(0)
"""


def _deferred_ready_bridge(tmp_path: Path, gate: Path, protocol: int = 1) -> Path:
    body = _DEFERRED_READY_STUB.replace("GATE_PATH", str(gate).replace("\\", "\\\\"))
    return _write_executable_bridge(tmp_path, body.replace("PROTOCOL", str(protocol)))


def _serial_bridge(tmp_path: Path, slow_seconds: float, protocol: int = 1) -> Path:
    body = _SERIAL_STUB.replace("SLOW_SECONDS", repr(slow_seconds))
    return _write_executable_bridge(tmp_path, body.replace("PROTOCOL", str(protocol)))


class _BackgroundCall:
    """Run ``call`` on a thread and keep whatever it produced, error included."""

    def __init__(self, call: Callable[[], Any]):
        self.result: Any = None
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, args=(call,), daemon=True)
        self._thread.start()

    def _run(self, call: Callable[[], Any]) -> None:
        try:
            self.result = call()
        except BaseException as exc:  # noqa: BLE001 - reported by the assertions
            self.error = exc

    def join(self, timeout: float = 60.0) -> _BackgroundCall:
        self._thread.join(timeout)
        assert not self._thread.is_alive(), "the background bridge call never finished"
        return self


def _wait_until(predicate: Callable[[], bool], message: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(message)


@pytest.fixture
def session_factory():
    """Build sessions and guarantee their processes are reaped afterwards."""
    built: list[bridge_session.BridgeSession] = []

    def make(bridge_path: Path) -> bridge_session.BridgeSession:
        session = bridge_session.BridgeSession(bridge_path)
        built.append(session)
        return session

    yield make
    for session in built:
        session.stop()


@pytest.fixture
def held_reader(monkeypatch):
    """Hold the first reader thread that reaches ``_on_closed`` until released.

    The bug this scaffolding exists for is a race -- the dead process's reader
    thread arriving after a respawn has already installed a fresh readiness
    record -- and a test that reproduces a race by winning one is worse than no
    test. So the interleaving is forced: the stale reader is parked at the door
    of ``_on_closed`` and let in at the exact moment the test chooses.

    Only the first call is held; every later one runs straight through, so the
    replacement process's own teardown is unaffected.
    """
    original = bridge_session.BridgeSession._on_closed
    taken = threading.Event()
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def gated(self, *args):
        if taken.is_set():
            original(self, *args)
            return
        taken.set()
        entered.set()
        release.wait(timeout=60)
        try:
            original(self, *args)
        finally:
            finished.set()

    monkeypatch.setattr(bridge_session.BridgeSession, "_on_closed", gated)
    return SimpleNamespace(entered=entered, release=release, finished=finished)


# --- A1: a late reader must not condemn the process it did not start ---------


def test_a_stale_reader_cannot_poison_the_respawn(tmp_path: Path, session_factory, held_reader):
    """The previous process's reader must not disable session mode for the run.

    ``_terminate_locked`` waits on the process, not on its reader thread, so the
    reader of a dead bridge can reach ``_on_closed`` after a respawn is already
    under way. It used to find the *new* start's readiness flag unset, conclude
    that this build predates ``serve`` mode, and record that verdict where the
    in-progress handshake would read it. The handshake then killed a perfectly
    healthy bridge, and because the verdict is sticky every later call fell back
    to a one-shot subprocess -- the per-command attach the session exists to
    remove -- silently, for the rest of the run, on the recovery path that only
    runs when something already went wrong.
    """
    announce = tmp_path / "announce"
    announce.write_text("go", encoding="utf-8")
    session = session_factory(_deferred_ready_bridge(tmp_path, announce))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    first = session._process

    # From here on a new process stays silent until the test says otherwise,
    # which is what keeps _start_locked parked on its fresh readiness record.
    announce.unlink()

    # End the bridge the way an MTGO restart does: the pipe goes away underneath
    # it. Its reader thread wakes on EOF and is caught at the door of _on_closed.
    first.stdin.close()
    _wait_until(lambda: first.poll() is not None, "the bridge process never exited")
    assert held_reader.entered.wait(30), "the dead process's reader never reached _on_closed"

    respawn = _BackgroundCall(lambda: session.request("username", timeout=30))
    _wait_until(
        lambda: session._process is not None and session._process is not first,
        "the session never started a replacement process",
    )
    second = session._process

    # A slot to watch the stale reader go past. _on_closed decides on readiness
    # first and fails the pending requests immediately after, and neither step
    # takes a lock, so this answer arriving is proof that the readiness decision
    # has already been made -- which is what makes the interleaving a hand-off
    # rather than a race. Waiting on the reader to *finish* would not work: its
    # last act is to take _state_lock, which the parked handshake is holding.
    watcher: queue.Queue = queue.Queue(maxsize=1)
    with session._pending_lock:
        session._pending["999999"] = watcher

    # The interleaving: let the stale reader through while the replacement is up
    # but has not announced itself yet.
    held_reader.release.set()
    assert watcher.get(timeout=30)[0] == "closed"
    announce.write_text("go", encoding="utf-8")

    respawn.join()
    assert respawn.error is None, f"the respawn was poisoned: {respawn.error!r}"
    assert respawn.result == {"argv": ["username"]}
    assert second.poll() is None, "a healthy replacement bridge was killed"
    assert session._unsupported is False
    # The sticky part: if the verdict had stuck, every later call would refuse.
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    assert held_reader.finished.wait(30), "the stale reader never finished"


# --- A2: the app shuts the bridge down, atexit is only the backstop ----------


def test_app_shutdown_closes_the_bridge_session(monkeypatch):
    """``LifecycleMixin.shutdown`` must close the session, not leave it to atexit."""
    order: list[str] = []

    class _StubImageService:
        def shutdown(self):
            order.append("images")

    class _StubWorker:
        def shutdown(self, timeout=None):
            order.append("worker")

    class _Controller(LifecycleMixin):
        def __init__(self):
            self.image_service = _StubImageService()
            self._worker = _StubWorker()

    monkeypatch.setattr(
        lifecycle.mtgo_bridge_service, "shutdown_session", lambda: order.append("bridge")
    )

    _Controller().shutdown(timeout=0.1)

    # After the worker join: the worker is what issues bridge commands, so
    # closing the session first would push its last calls onto one-shot spawns.
    assert order == ["images", "worker", "bridge"]


def test_shutting_down_without_a_session_is_free():
    """Exiting before anything touched the bridge must cost nothing and not raise.

    Also covers the double call the atexit backstop makes after a normal app
    shutdown has already closed the session.
    """
    bridge_session.shutdown_session()
    bridge_session.shutdown_session()
    assert bridge_session._session is None


# --- A7: the request timeout is a per-command budget ------------------------


def test_a_queued_request_does_not_tear_down_the_shared_session(tmp_path: Path, session_factory):
    """A caller must not be executed for the time an earlier command spent running.

    The bridge runs requests one at a time, so a command can sit in the queue for
    the whole of the one ahead of it. Charging that to the waiting caller made
    its expiry drop the shared process -- taking the challenge timer's watch
    stream and every other in-flight caller with it -- for the offence of being
    second in line.
    """
    session = session_factory(_serial_bridge(tmp_path, slow_seconds=3.0))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    process = session._process

    slow = _BackgroundCall(lambda: session.request("slow", timeout=30))
    _wait_until(lambda: bool(session._pending), "the slow command was never queued")

    # Half a second is nowhere near enough for a request behind a three-second
    # command -- but the budget does not start until the bridge can run it.
    assert session.request("queued", timeout=0.5) == {"argv": ["queued"]}
    assert session._process is process, "a queued caller's expiry killed the shared bridge"
    assert slow.join().result == {"argv": ["slow"]}


def test_a_wedged_command_still_drops_the_process(tmp_path: Path, session_factory):
    """The budget still bites once the caller's own command is the one running.

    The per-command budget must not turn into no budget: when nothing older is
    outstanding, an expiry means a wedged SDK call, which cannot be cancelled
    remotely, so the process has to go.
    """
    session = session_factory(_serial_bridge(tmp_path, slow_seconds=10.0))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    process = session._process

    with pytest.raises(bridge_session.BridgeSessionUnavailable, match="did not answer within"):
        session.request("slow", timeout=0.5)

    assert process.poll() is not None, "the wedged bridge process was left running"
