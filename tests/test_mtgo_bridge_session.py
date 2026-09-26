"""Tests for the long-lived bridge session (``MTGOBridge.exe serve``).

Every test drives a Python stub that speaks the newline-delimited JSON protocol,
so nothing here needs MTGO, MTGOSDK or the compiled bridge.
"""

from __future__ import annotations

import os
import queue
import stat
import sys
import textwrap
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

import services.mtgo_bridge_service as mtgo_bridge
from services.mtgo_bridge_service import session as bridge_session

# A stub that answers every request by echoing its argv, streams watch snapshots
# while subscribed, and exits when stdin closes.
#
# ``park`` is the scaffolding the concurrency tests are built on: a parked
# request is held unanswered until PARK_COUNT of them have arrived, and they are
# then answered in reverse arrival order. That is a barrier rather than a sleep
# -- no parked caller can come back until every one of them is in flight at the
# same time -- and answering them backwards is what makes an implementation that
# does not correlate on ``id`` fail rather than pass by luck.
_SERVE_STUB = r"""
import json, sys, threading, time

stop = threading.Event()
lock = threading.Lock()
parked = []


def emit(obj):
    with lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def emit_raw(text):
    with lock:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def answer(req):
    emit({
        "id": req["id"],
        "ok": True,
        "payload": {"argv": [req["command"]] + req.get("args", [])},
    })


def stream():
    n = 0
    while not stop.wait(0.05):
        n += 1
        emit({"event": "watch", "payload": {"challengeTimers": [], "tick": n}})


emit({"event": "ready", "payload": {"protocol": PROTOCOL, "pid": 0}})

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    command, args = req["command"], req.get("args", [])
    if command == "boom":
        emit({"id": req["id"], "ok": False, "error": "stub failure"})
        continue
    if command == "die":
        sys.exit(0)
    if command == "park":
        parked.append(req)
        if len(parked) >= PARK_COUNT:
            for held in reversed(parked):
                answer(held)
            del parked[:]
        continue
    if command == "garbage":
        emit_raw("{this is not JSON")
        answer(req)
        continue
    if command == "ghost":
        emit({"id": "no-such-request", "ok": True, "payload": {"argv": ["ghost"]}})
        answer(req)
        continue
    if command == "disconnect":
        emit({"event": "disconnected", "payload": {"reason": "MTGO closed"}})
        answer(req)
        continue
    if command == "watch":
        if args and args[0] == "stop":
            stop.set()
            emit({"id": req["id"], "ok": True, "payload": {"status": "watch.stopped"}})
        else:
            stop.clear()
            threading.Thread(target=stream, daemon=True).start()
            emit({"id": req["id"], "ok": True, "payload": {"status": "watch.started"}})
        continue
    answer(req)
"""

# A build that predates serve mode: unknown args make it return immediately.
_OLD_BUILD_STUB = "import sys\nsys.exit(0)\n"

# A build that starts, holds the pipe open, and never announces itself. Only the
# handshake budget can end a call against it; it still exits on stdin EOF, so the
# session's ordinary teardown reaps it without escalating.
_SILENT_STUB = r"""
import sys

sys.stdin.read()
"""

# A build that answers normally but treats stdin EOF as nothing at all -- the way
# a bridge wedged inside an MTGOSDK call would. The polite shutdown cannot reach
# it, so the terminate/kill ladder has to. The trailing sleep is bounded so the
# stub can never outlive the run that started it.
_DEAF_STUB = r"""
import json, sys, time


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


emit({"event": "ready", "payload": {"protocol": PROTOCOL, "pid": 0}})

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    emit({
        "id": req["id"],
        "ok": True,
        "payload": {"argv": [req["command"]] + req.get("args", [])},
    })

time.sleep(10)
"""


def _write_executable_bridge(tmp_path: Path, body: str) -> Path:
    """Create a directly-runnable stub bridge (the session invokes the path)."""
    program = tmp_path / "bridge_program.py"
    program.write_text(textwrap.dedent(body), encoding="utf-8")

    if os.name == "nt":
        launcher = tmp_path / "bridge.bat"
        launcher.write_text(
            f'@echo off\r\nset PYTHONUTF8=1\r\n"{sys.executable}" "{program}" %*\r\n'
        )
        return launcher

    launcher = tmp_path / "bridge.sh"
    launcher.write_text(f'#!/bin/sh\nPYTHONUTF8=1 exec "{sys.executable}" "{program}" "$@"\n')
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return launcher


def _serve_bridge(tmp_path: Path, protocol: int = 1, park_count: int = 2) -> Path:
    body = _SERVE_STUB.replace("PROTOCOL", str(protocol))
    return _write_executable_bridge(tmp_path, body.replace("PARK_COUNT", str(park_count)))


def _deaf_bridge(tmp_path: Path, protocol: int = 1) -> Path:
    return _write_executable_bridge(tmp_path, _DEAF_STUB.replace("PROTOCOL", str(protocol)))


def _wait_until(predicate: Callable[[], bool], message: str, timeout: float = 30.0) -> None:
    """Block until ``predicate`` holds, or fail saying what never happened."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(message)


class _BackgroundCall:
    """Run ``call`` on a thread and keep whatever it produced, error included."""

    def __init__(self, call: Callable[[], object]):
        self.result: object = None
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, args=(call,), daemon=True)
        self._thread.start()

    def _run(self, call: Callable[[], object]) -> None:
        try:
            self.result = call()
        except BaseException as exc:  # noqa: BLE001 - reported by the assertions
            self.error = exc

    def join(self, timeout: float = 60.0) -> _BackgroundCall:
        self._thread.join(timeout)
        assert not self._thread.is_alive(), "the background bridge call never finished"
        return self


def _record_escalation(process, *, ignore_terminate: bool = False) -> list[str]:
    """Record which rungs of the close/terminate/kill ladder ``process`` is put through.

    Both wrappers delegate, so the ladder still really ends the process. The one
    exception is ``ignore_terminate``, which makes the child survive a terminate
    -- the only way to reach the kill rung on Windows, where ``terminate`` and
    ``kill`` are the same call and no child can decline either.
    """
    rungs: list[str] = []
    terminate, kill = process.terminate, process.kill

    def on_terminate() -> None:
        rungs.append("terminate")
        if not ignore_terminate:
            terminate()

    def on_kill() -> None:
        rungs.append("kill")
        kill()

    process.terminate = on_terminate
    process.kill = on_kill
    return rungs


@pytest.fixture(autouse=True)
def clean_session_environment(monkeypatch):
    """No escape hatch, and no session left over for the next test.

    ``MTGO_BRIDGE_NO_SESSION`` is a documented escape hatch, so a developer
    debugging the one-shot transport has it set -- and every test here would
    then fail on an error message about their own environment. The process-wide
    session is cleared afterwards for the same reason in reverse: these tests
    are the only ones that install one.
    """
    monkeypatch.delenv(bridge_session.BRIDGE_SESSION_DISABLE_ENV, raising=False)
    yield
    bridge_session.shutdown_session()


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
def spawned(monkeypatch):
    """Every process the session starts, so a test can prove they were all reaped.

    A spy rather than a fake: it hands back the real ``Popen`` it just created.
    """
    real = bridge_session.subprocess.Popen
    started: list = []

    def spy(*args, **kwargs):
        process = real(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(bridge_session.subprocess, "Popen", spy)
    return started


# --- request/response correlation -------------------------------------------


def test_request_returns_payload(tmp_path: Path, session_factory) -> None:
    session = session_factory(_serve_bridge(tmp_path))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}


def test_request_forwards_subcommand_args(tmp_path: Path, session_factory) -> None:
    """``trade status`` must reach the bridge as the same argv a CLI run would."""
    session = session_factory(_serve_bridge(tmp_path))
    payload = session.request("trade", args=("status",), timeout=30)
    assert payload == {"argv": ["trade", "status"]}


def test_requests_are_correlated_by_id(tmp_path: Path, session_factory) -> None:
    """Three callers at once, answered backwards, each still gets its own answer.

    The module carries four locks for exactly this, so the callers have to be
    concurrent: run one after another, an implementation that ignored ``id`` and
    handed every waiter the next line off the pipe would pass. The stub parks all
    three requests until the last one arrives -- a barrier, so the test cannot
    pass by winning a race -- and then answers them in reverse arrival order, so
    an implementation that correlated by arrival would hand each caller somebody
    else's answer.
    """
    session = session_factory(_serve_bridge(tmp_path, park_count=3))
    names = ("alpha", "beta", "gamma")
    callers = [
        _BackgroundCall(lambda name=name: session.request("park", args=(name,), timeout=30))
        for name in names
    ]

    answers = {}
    for name, caller in zip(names, callers, strict=True):
        assert caller.join().error is None, f"{name} failed: {caller.error!r}"
        answers[name] = caller.result

    assert answers == {name: {"argv": ["park", name]} for name in names}


def test_concurrent_callers_share_one_pipe(tmp_path: Path, session_factory) -> None:
    """Eight callers writing at once must not shred each other's request lines.

    One process, one stdin: without the write lock two threads' JSON interleaves
    mid-line, the bridge fails to parse it and dies, and every caller comes back
    with a session error instead of its payload. The barrier holds all eight in
    flight together, which is what puts the lock under load rather than trusting
    the scheduler to have produced an overlap.
    """
    session = session_factory(_serve_bridge(tmp_path, park_count=8))
    payloads = [f"{index}-{'x' * 200}" for index in range(8)]
    callers = [
        _BackgroundCall(lambda arg=arg: session.request("park", args=(arg,), timeout=30))
        for arg in payloads
    ]

    for arg, caller in zip(payloads, callers, strict=True):
        assert caller.join().error is None, f"caller {arg[:2]} failed: {caller.error!r}"
        assert caller.result == {"argv": ["park", arg]}


def test_bridge_error_response_raises_and_does_not_retry(tmp_path: Path, session_factory) -> None:
    """An ``ok: false`` answer is a real failure, not a reason to fall back."""
    session = session_factory(_serve_bridge(tmp_path))
    with pytest.raises(bridge_session.BridgeSessionError, match="stub failure"):
        session.request("boom", timeout=30)
    # The session is still healthy: a failed command must not cost a respawn.
    process = session._process
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    assert session._process is process


# --- lifecycle / reconnection ------------------------------------------------


def test_old_build_without_ready_banner_is_marked_unsupported(
    tmp_path: Path, session_factory
) -> None:
    session = session_factory(_write_executable_bridge(tmp_path, _OLD_BUILD_STUB))
    with pytest.raises(bridge_session.BridgeSessionUnavailable, match="predates"):
        session.request("collection", timeout=30)
    # Sticky: the next call must fail immediately rather than spawn again.
    assert session._unsupported is True
    with pytest.raises(bridge_session.BridgeSessionUnavailable, match="does not support"):
        session.request("collection", timeout=30)


def test_protocol_mismatch_is_rejected(tmp_path: Path, session_factory) -> None:
    session = session_factory(_serve_bridge(tmp_path, protocol=999))
    with pytest.raises(bridge_session.BridgeSessionUnavailable, match="protocol"):
        session.request("collection", timeout=30)


def test_session_respawns_after_the_bridge_dies(tmp_path: Path, session_factory) -> None:
    """MTGO restarting kills the bridge; the next request must just work."""
    session = session_factory(_serve_bridge(tmp_path))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    first_pid = session._process.pid

    with pytest.raises(bridge_session.BridgeSessionUnavailable):
        # "die" exits without answering, and there is no second process to
        # retry against until the request loop respawns one.
        session.request("die", timeout=30)

    assert session.request("username", timeout=30) == {"argv": ["username"]}
    assert session._process.pid != first_pid


def test_a_bridge_that_never_announces_itself_does_not_hang_the_caller(
    tmp_path: Path, session_factory, spawned, monkeypatch
) -> None:
    """A ``serve`` process that starts and then says nothing must still be reaped.

    The stub is alive and holding the pipe open, so nothing but the handshake
    budget can end this call: without it ``request`` would wait on readiness for
    as long as the bridge stayed up, which for a hung MTGO attach is forever.

    Deliberately not asserted: *which* failure the session reports. It retries
    once, and on the pre-``_Handshake`` code the dead process's reader can reach
    the retry's readiness flag first and relabel a slow start as a build that
    predates ``serve`` mode. The guarantee that holds either way -- and the one
    that matters, because an orphan stays attached to MTGO -- is that the caller
    is released and every process the attempt started is dead.
    """
    monkeypatch.setattr(bridge_session, "BRIDGE_SESSION_HANDSHAKE_TIMEOUT_SECONDS", 0.25)
    session = session_factory(_write_executable_bridge(tmp_path, _SILENT_STUB))

    started = time.monotonic()
    with pytest.raises(bridge_session.BridgeSessionUnavailable):
        session.request("collection", timeout=30)
    elapsed = time.monotonic() - started

    assert elapsed < 20, "the handshake budget did not end the call; the request timeout did"
    assert spawned, "no bridge process was ever started"
    for process in spawned:
        assert process.poll() is not None, "a bridge that never announced itself was left running"
    assert session._process is None


def test_stop_terminates_the_process(tmp_path: Path, session_factory) -> None:
    session = session_factory(_serve_bridge(tmp_path))
    session.request("collection", timeout=30)
    process = session._process
    session.stop()
    assert process.poll() is not None
    assert session._process is None


def test_stop_terminates_a_bridge_that_ignores_stdin_eof(
    tmp_path: Path, session_factory, monkeypatch
) -> None:
    """Closing stdin is the polite shutdown; a wedged bridge never reads it.

    An orphaned ``serve`` process stays attached to MTGO and keeps marshalling
    reads onto its UI thread with nobody left to read the answers, so "stop"
    has to mean stopped rather than asked nicely.
    """
    monkeypatch.setattr(bridge_session, "BRIDGE_SESSION_SHUTDOWN_TIMEOUT_SECONDS", 0.5)
    session = session_factory(_deaf_bridge(tmp_path))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    process = session._process
    rungs = _record_escalation(process)

    session.stop()

    assert rungs == ["terminate"]
    assert process.poll() is not None
    assert session._process is None


def test_stop_kills_a_bridge_that_ignores_terminate(
    tmp_path: Path, session_factory, monkeypatch
) -> None:
    """The last rung of the ladder, with the child declining the one before it.

    A terminate a process can survive is a POSIX signal, which Windows has no
    equivalent of, so the refusal is injected rather than stubbed in the child:
    ``terminate`` is recorded and not delivered, and the real ``kill`` that
    follows still has to be what ends the process.
    """
    monkeypatch.setattr(bridge_session, "BRIDGE_SESSION_SHUTDOWN_TIMEOUT_SECONDS", 0.5)
    session = session_factory(_deaf_bridge(tmp_path))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    process = session._process
    rungs = _record_escalation(process, ignore_terminate=True)

    session.stop()

    assert rungs == ["terminate", "kill"]
    assert process.poll() is not None


# --- lines the session did not ask for ---------------------------------------


def test_a_malformed_line_is_skipped_rather_than_ending_the_session(
    tmp_path: Path, session_factory
) -> None:
    """One unparseable line must not cost the reader thread, or the process."""
    session = session_factory(_serve_bridge(tmp_path))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    process = session._process

    assert session.request("garbage", timeout=30) == {"argv": ["garbage"]}

    assert session._process is process
    assert session.request("username", timeout=30) == {"argv": ["username"]}


def test_an_answer_to_an_unknown_request_id_is_dropped(tmp_path: Path, session_factory) -> None:
    """A reply nobody is waiting for -- a timed-out caller's, say -- goes nowhere.

    It must not be handed to the next waiter: the request that follows asks a
    different question and would get this answer instead of its own.
    """
    session = session_factory(_serve_bridge(tmp_path))
    assert session.request("ghost", timeout=30) == {"argv": ["ghost"]}
    assert session.request("username", timeout=30) == {"argv": ["username"]}


def test_a_disconnected_event_is_not_the_end_of_the_session(
    tmp_path: Path, session_factory
) -> None:
    """MTGO going away is news about the client, not about the bridge process.

    Tearing the session down here would cost a respawn for something the bridge
    recovers from on its own.
    """
    session = session_factory(_serve_bridge(tmp_path))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    process = session._process

    assert session.request("disconnect", timeout=30) == {"argv": ["disconnect"]}

    assert session._process is process
    assert session.request("username", timeout=30) == {"argv": ["username"]}


# --- the process-wide session ------------------------------------------------


def test_get_session_reuses_one_bridge_and_closes_the_one_it_replaces(tmp_path: Path) -> None:
    """One attach at a time: asking twice must not start a second bridge.

    Several bridges attached at once is the state this whole module exists to
    avoid -- MTGOSDK marshals every remote read onto MTGO's UI thread, so the
    second attach makes the first one slower rather than the work faster.
    """
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_bridge, second_bridge = _serve_bridge(first_dir), _serve_bridge(second_dir)

    session = bridge_session.get_session(first_bridge)
    assert bridge_session.get_session(first_bridge) is session
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    replaced = session._process

    swapped = bridge_session.get_session(second_bridge)
    assert swapped is not session
    assert replaced.poll() is not None, "the bridge that was swapped out was left attached"
    assert swapped.request("username", timeout=30) == {"argv": ["username"]}
    live = swapped._process

    bridge_session.shutdown_session()

    assert live.poll() is not None
    # ...and the next caller builds a new session rather than reviving the dead one.
    assert bridge_session.get_session(first_bridge) is not swapped


def test_disable_env_refuses_the_session(tmp_path: Path, session_factory, monkeypatch) -> None:
    monkeypatch.setenv("MTGO_BRIDGE_NO_SESSION", "1")
    session = session_factory(_serve_bridge(tmp_path))
    assert bridge_session.session_enabled() is False
    with pytest.raises(bridge_session.BridgeSessionUnavailable, match="MTGO_BRIDGE_NO_SESSION"):
        session.request("collection", timeout=30)


# --- watch stream ------------------------------------------------------------


def test_watcher_receives_streamed_snapshots(tmp_path: Path, session_factory) -> None:
    session = session_factory(_serve_bridge(tmp_path))
    with bridge_session.SessionWatcher(session, interval_ms=100) as watcher:
        payload = watcher.latest(block=True, timeout=20)
    assert payload is not None
    assert payload["challengeTimers"] == []


def test_watch_stops_when_the_last_subscriber_leaves(tmp_path: Path, session_factory) -> None:
    session = session_factory(_serve_bridge(tmp_path))
    watcher = bridge_session.SessionWatcher(session, interval_ms=100)
    watcher.start()
    assert watcher.latest(block=True, timeout=20) is not None
    watcher.stop()
    assert session._watch_armed is False
    # The session survives losing its watcher; other commands keep working.
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}


def test_watch_is_re_armed_after_a_respawn(tmp_path: Path, session_factory) -> None:
    """A subscriber keeps receiving across a bridge restart without re-subscribing."""
    session = session_factory(_serve_bridge(tmp_path))
    watcher = bridge_session.SessionWatcher(session, interval_ms=100)
    watcher.start()
    assert watcher.latest(block=True, timeout=20) is not None

    with pytest.raises(bridge_session.BridgeSessionUnavailable):
        session.request("die", timeout=30)
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}

    assert watcher.latest(block=True, timeout=20) is not None


def test_queue_replace_keeps_only_the_latest_snapshot() -> None:
    sink: queue.Queue = queue.Queue(maxsize=1)
    bridge_session._queue_replace(sink, {"tick": 1})
    bridge_session._queue_replace(sink, {"tick": 2})
    assert sink.get_nowait() == {"tick": 2}
    assert sink.empty()


# --- futures -----------------------------------------------------------------


def test_request_future_resolves_and_reraises() -> None:
    assert bridge_session.SessionRequestFuture(lambda: {"ok": 1}).result(timeout=10) == {"ok": 1}

    def boom():
        raise bridge_session.BridgeSessionError("nope")

    future = bridge_session.SessionRequestFuture(boom)
    with pytest.raises(bridge_session.BridgeSessionError, match="nope"):
        future.result(timeout=10)


def test_cancelling_an_in_flight_request_leaves_the_shared_bridge_alone(
    tmp_path: Path, session_factory
) -> None:
    """``cancel`` stops the caller waiting; it must not stop the bridge.

    The old form of this asserted the return value of a function whose only
    statement is ``return None``, against no session at all. What the docstring
    promises is about a *shared* process: a caller that walks away must not take
    the challenge timer's watch stream and every other in-flight request with it,
    and the work it queued cannot be recalled from the bridge anyway.

    The request is genuinely in flight -- the stub holds it until a second one
    arrives -- so cancel lands in the window where a teardown would do damage.
    """
    session = session_factory(_serve_bridge(tmp_path, park_count=2))
    assert session.request("collection", timeout=30) == {"argv": ["collection"]}
    process = session._process

    cancelled = bridge_session.SessionRequestFuture(
        lambda: session.request("park", args=("alpha",), timeout=30)
    )
    _wait_until(lambda: bool(session._pending), "the cancelled request never reached the bridge")

    cancelled.cancel()

    assert process.poll() is None, "cancelling a request killed the shared bridge"
    assert session._process is process
    # The second park releases the barrier, so the abandoned request answers too:
    # cancel is a promise to the caller, not a recall.
    assert session.request("park", args=("beta",), timeout=30) == {"argv": ["park", "beta"]}
    assert cancelled.result(timeout=30) == {"argv": ["park", "alpha"]}


# --- facade wiring -----------------------------------------------------------


def test_facade_prefers_the_session(tmp_path: Path, monkeypatch) -> None:
    bridge = _serve_bridge(tmp_path)
    monkeypatch.setattr(mtgo_bridge.mtgo_bridge_client, "run_bridge_command", _must_not_run)
    try:
        assert mtgo_bridge._request("logfiles", bridge_path=str(bridge), timeout=30) == {
            "argv": ["logfiles"]
        }
    finally:
        bridge_session.shutdown_session()


def test_facade_falls_back_to_one_shot_when_no_session(tmp_path: Path, monkeypatch) -> None:
    """An old bridge build must keep working through the one-shot transport."""
    bridge = _write_executable_bridge(tmp_path, _OLD_BUILD_STUB)
    calls: list[tuple] = []

    def fake_run(mode, *, bridge_path=None, extra_args=None, timeout=None):
        calls.append((mode, extra_args))
        return {"fallback": mode}

    monkeypatch.setattr(mtgo_bridge.mtgo_bridge_client, "run_bridge_command", fake_run)
    try:
        payload = mtgo_bridge._request(
            "trade", args=("status",), bridge_path=str(bridge), timeout=30
        )
    finally:
        bridge_session.shutdown_session()

    assert payload == {"fallback": "trade"}
    assert calls == [("trade", ("status",))]


def test_facade_lets_a_missing_bridge_raise(tmp_path: Path) -> None:
    """``FileNotFoundError`` must reach callers, not be masked by a fallback."""
    with pytest.raises(FileNotFoundError):
        mtgo_bridge._request("collection", bridge_path=str(tmp_path / "nope.exe"))


def _must_not_run(*_args, **_kwargs):  # pragma: no cover - guard for the test above
    raise AssertionError("the one-shot transport must not be used when a session works")
