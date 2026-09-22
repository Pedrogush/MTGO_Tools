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
from pathlib import Path

import pytest

import services.mtgo_bridge_service as mtgo_bridge
from services.mtgo_bridge_service import session as bridge_session

# A stub that answers every request by echoing its argv, streams watch snapshots
# while subscribed, and exits when stdin closes.
_SERVE_STUB = r"""
import json, sys, threading, time

stop = threading.Event()
lock = threading.Lock()


def emit(obj):
    with lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


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
    if command == "watch":
        if args and args[0] == "stop":
            stop.set()
            emit({"id": req["id"], "ok": True, "payload": {"status": "watch.stopped"}})
        else:
            stop.clear()
            threading.Thread(target=stream, daemon=True).start()
            emit({"id": req["id"], "ok": True, "payload": {"status": "watch.started"}})
        continue
    emit({"id": req["id"], "ok": True, "payload": {"argv": [command] + args}})
"""

# A build that predates serve mode: unknown args make it return immediately.
_OLD_BUILD_STUB = "import sys\nsys.exit(0)\n"


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


def _serve_bridge(tmp_path: Path, protocol: int = 1) -> Path:
    return _write_executable_bridge(tmp_path, _SERVE_STUB.replace("PROTOCOL", str(protocol)))


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
    """Several commands over one pipe each get their own answer back."""
    session = session_factory(_serve_bridge(tmp_path))
    seen = [
        session.request(cmd, timeout=30)["argv"][0]
        for cmd in ("collection", "username", "logfiles")
    ]
    assert seen == ["collection", "username", "logfiles"]


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


def test_stop_terminates_the_process(tmp_path: Path, session_factory) -> None:
    session = session_factory(_serve_bridge(tmp_path))
    session.request("collection", timeout=30)
    process = session._process
    session.stop()
    assert process.poll() is not None
    assert session._process is None


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
    # cancel() is a no-op that must never tear the shared bridge down.
    assert future.cancel() is None


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
